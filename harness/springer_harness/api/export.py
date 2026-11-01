"""Write the contract's machine-readable form: python -m springer_harness.api.export"""

import tempfile
import time
from pathlib import Path

from ..daemon import Daemon
from ..providers.mock import MockProvider, MockSourceHost
from ..providers.secrets import MemorySecrets
from ..scheduler.plan import CannedPlanner
from .app import create_app, export_openapi

OPENAPI_PATH = Path(__file__).resolve().parents[2] / "openapi.json"


def current():
    with tempfile.TemporaryDirectory() as home:
        daemon = Daemon(home, MockProvider(), MockSourceHost(), lambda *_: CannedPlanner([]), MemorySecrets(), time.time)
        return export_openapi(create_app(daemon))


if __name__ == "__main__":
    OPENAPI_PATH.write_text(current())
    print(f"wrote {OPENAPI_PATH}")
