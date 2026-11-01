"""The event ledger: runs/<run_id>/events.jsonl, append-only.

The daemon and the session hooks both append, so the daemon writes one line per
O_APPEND write and orders a stream by byte position. A line a hook wrote has no
seq, which is why a cursor is a position and not a seq.
"""

import json
import os
import threading
from dataclasses import dataclass
from pathlib import Path

from ..common import iso


class CursorInvalid(Exception):
    """The cursor cannot be honored, and the client refetches its snapshot."""


@dataclass(frozen=True)
class Entry:
    cursor: str
    line: dict


class Ledger:
    def __init__(self, run_dir, run_id, now):
        self.path = Path(run_dir) / "events.jsonl"
        self.run_id = run_id
        self.now = now
        self._lock = threading.Lock()
        self._seq = None

    def _last_seq(self):
        return max((e.line["seq"] for e in self.read() if isinstance(e.line.get("seq"), int)), default=0)

    def append(self, event, **fields):
        """Append one daemon line. Returns (seq, cursor)."""
        with self._lock:
            if self._seq is None:
                self._seq = self._last_seq()
            self._seq += 1
            line = {"ts": iso(self.now()), "event": event, "seq": self._seq, "run_id": self.run_id, **fields}
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
            try:
                os.write(fd, (json.dumps(line) + "\n").encode())
                position = os.lseek(fd, 0, os.SEEK_CUR)
            finally:
                os.close(fd)
            return self._seq, f"c-{position}"

    def _offset(self, cursor):
        if cursor is None:
            return 0
        try:
            offset = int(cursor.removeprefix("c-"))
        except (AttributeError, ValueError):
            raise CursorInvalid(cursor) from None
        size = self.path.stat().st_size if self.path.exists() else 0
        if offset < 0 or offset > size:
            raise CursorInvalid(cursor)
        if offset:
            with open(self.path, "rb") as fh:
                fh.seek(offset - 1)
                if fh.read(1) != b"\n":
                    raise CursorInvalid(cursor)
        return offset

    def read(self, after=None):
        """Every complete line after the cursor. A malformed line is skipped, and
        a partial last line waits for its newline."""
        offset = self._offset(after)
        if not self.path.exists():
            return
        with open(self.path, "rb") as fh:
            fh.seek(offset)
            for raw in fh:
                if not raw.endswith(b"\n"):
                    return
                offset += len(raw)
                try:
                    line = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if isinstance(line, dict):
                    yield Entry(f"c-{offset}", line)

    def head(self):
        """The cursor after the last complete line."""
        if not self.path.exists():
            return "c-0"
        data = self.path.read_bytes()
        return f"c-{data.rfind(b'\n') + 1}"
