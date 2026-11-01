"""Small helpers every layer shares: time, atomic files, and the artifact header."""

import json
import os
import tempfile
import time
from pathlib import Path


def iso(epoch):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def parse_iso(text):
    return time.mktime(time.strptime(text, "%Y-%m-%dT%H:%M:%SZ")) - time.timezone


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError):
        return default


def write_json(path, obj):
    """Write through a temporary file, so a crash never leaves half a record."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    with os.fdopen(fd, "w") as fh:
        fh.write(json.dumps(obj, indent=2) + "\n")
    os.replace(tmp, path)


def write_text(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    with os.fdopen(fd, "w") as fh:
        fh.write(text)
    os.replace(tmp, path)


def next_id(prefix, existing):
    """The next id in a prefix-nnnn series, given the ids that already exist."""
    numbers = [int(e.rsplit("-", 1)[1]) for e in existing if e.rsplit("-", 1)[1].isdigit()]
    return f"{prefix}-{max(numbers, default=0) + 1:04d}"


def artifact_header(artifact_id, artifact_type, section, schema_version, epoch):
    return {
        "artifact_id": artifact_id,
        "artifact_type": artifact_type,
        "schema_version": schema_version,
        "producing_agent": "springer-harness",
        "timestamp": iso(epoch),
        "parent_artifact_ref": None,
        "version": "v1.0",
        "version_type": "approved",
        "confidence_map": {section: "confirmed"},
        "decision_log": [],
    }
