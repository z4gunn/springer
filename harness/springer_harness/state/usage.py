"""The usage window, per provider account, as ~/.springer/usage/<provider>.json.

Budget under subscription auth is a window and not dollars, so the scheduler lowers
concurrency as the window fills and parks until the reset when it is exhausted.
"""

from pathlib import Path

from ..common import iso, parse_iso, read_json, write_json

DEFAULT_WINDOW_SECONDS = 5 * 3600


def concurrency_for(used_fraction, maximum):
    """The dispatch rate for a used fraction. No signal means no reason to slow."""
    if used_fraction is None or used_fraction < 0.7:
        return maximum
    if used_fraction < 0.9:
        return max(1, maximum // 2)
    if used_fraction < 1:
        return 1
    return 0


class UsageWindow:
    def __init__(self, home, provider, now, maximum=2):
        self.path = Path(home) / "usage" / f"{provider}.json"
        self.provider = provider
        self.now = now
        self.maximum = maximum

    def read(self):
        record = read_json(self.path)
        if record is None or self.now() >= parse_iso(record["resets_at"]):
            start = self.now()
            record = {"artifact_type": "usage-window", "schema_version": "v1", "provider": self.provider,
                      "window_start": iso(start), "resets_at": iso(start + DEFAULT_WINDOW_SECONDS),
                      "used_fraction": None, "own_tokens": 0, "dispatch_rate": self.maximum}
            write_json(self.path, record)
        return record

    def sample(self, signal):
        """Apply the provider's usage signal, when it has one."""
        record = self.read()
        if signal is not None:
            record["used_fraction"] = signal["used_fraction"]
            if signal.get("resets_at"):
                record["resets_at"] = signal["resets_at"]
        record["dispatch_rate"] = concurrency_for(record["used_fraction"], self.maximum)
        write_json(self.path, record)
        return record

    def add_tokens(self, tokens):
        record = self.read()
        record["own_tokens"] += tokens
        write_json(self.path, record)

    def parked(self):
        record = self.read()
        return record["dispatch_rate"] == 0 and self.now() < parse_iso(record["resets_at"])
