"""A fingerprint of this package's code. The daemon reports it, and the springer command
compares it, so a TUI never talks to a daemon still running older code."""

import hashlib
from pathlib import Path


def build_id():
    digest = hashlib.sha256()
    root = Path(__file__).resolve().parent
    for path in sorted(root.rglob("*.py")):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()[:12]
