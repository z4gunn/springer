#!/usr/bin/env python3
"""SPGR artifact validator.

Validates an artifact JSON file against the registered schema for its
artifact_type and schema_version. All schema files in this directory form the
registry. Per-type schemas compose _envelope-v1.json by absolute $id.

Usage:
    python3 schemas/validate.py <artifact.json> [artifact_type] [schema_version]
    python3 schemas/validate.py --self-check

If artifact_type and schema_version are omitted, they are read from the
artifact's own header. Exit code 0 means valid, 1 means invalid or error.

The five deterministic schema-touching skills (validate, read, write, version,
archive) call this script rather than re-implementing validation.
"""

import json
import os
import sys
from pathlib import Path

SCHEMA_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCHEMA_DIR.parent

# Re-exec into the project venv when jsonschema is not importable, so that
# `python3 schemas/validate.py ...` works regardless of which interpreter ran it.
try:
    import jsonschema  # noqa: F401
except ImportError:
    venv_py = REPO_ROOT / ".venv" / "bin" / "python"
    # Re-exec once into the venv interpreter (kept as the symlink so pyvenv.cfg is
    # honored). The sentinel prevents an infinite loop if the import still fails.
    if venv_py.exists() and not os.environ.get("SPGR_VALIDATE_REEXEC"):
        os.environ["SPGR_VALIDATE_REEXEC"] = "1"
        os.execv(str(venv_py), [str(venv_py), str(Path(__file__).resolve()), *sys.argv[1:]])
    sys.stderr.write(
        "jsonschema is not installed. Set up the project venv:\n"
        "    python3 -m venv .venv && .venv/bin/pip install jsonschema\n"
    )
    sys.exit(1)

from jsonschema import Draft202012Validator
from referencing import Registry, Resource


def load_registry():
    """Build a referencing Registry from every schema file in this directory."""
    resources = []
    for path in sorted(SCHEMA_DIR.glob("*.json")):
        schema = json.loads(path.read_text())
        sid = schema.get("$id")
        if not sid:
            continue
        resources.append((sid, Resource.from_contents(schema)))
    return Registry().with_resources(resources)


def schema_path_for(artifact_type, schema_version):
    return SCHEMA_DIR / f"{artifact_type}-{schema_version}.json"


def validate_artifact(artifact_path, artifact_type=None, schema_version=None):
    """Validate an artifact and return (issues, mode).

    issues is a list of human-readable strings, empty means valid. mode is
    "content" when a registered content schema was applied, or "envelope-only"
    when no content schema exists for the type yet, so only the shared envelope
    header is validated and content is treated as opaque until a schema is added.
    """
    try:
        artifact = json.loads(Path(artifact_path).read_text())
    except (OSError, json.JSONDecodeError) as exc:
        return [f"cannot read or parse artifact: {exc}"], "error"

    artifact_type = artifact_type or artifact.get("artifact_type")
    schema_version = schema_version or artifact.get("schema_version")
    if not artifact_type or not schema_version:
        return ["artifact_type and schema_version are required (in args or artifact header)"], "error"

    sp = schema_path_for(artifact_type, schema_version)
    mode = "content"
    if not sp.exists():
        sp = SCHEMA_DIR / "_envelope-v1.json"
        mode = "envelope-only"

    schema = json.loads(sp.read_text())
    registry = load_registry()
    validator = Draft202012Validator(schema, registry=registry)
    issues = []
    for err in sorted(validator.iter_errors(artifact), key=lambda e: list(e.path)):
        loc = "/".join(str(p) for p in err.path) or "(root)"
        issues.append(f"{loc}: {err.message}")
    return issues, mode


def self_check():
    """Check every schema compiles, refs resolve, and gating actually works."""
    registry = load_registry()
    failures = []
    type_files = [p for p in sorted(SCHEMA_DIR.glob("*.json")) if not p.name.startswith("_")]

    # 1. Every schema file is valid JSON Schema 2020-12.
    for path in sorted(SCHEMA_DIR.glob("*.json")):
        schema = json.loads(path.read_text())
        try:
            Draft202012Validator.check_schema(schema)
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{path.name}: invalid schema: {exc}")

    # 2. Every per-type schema's envelope $ref resolves (constructing + running
    #    the validator on a trivial instance forces resolution).
    for path in type_files:
        schema = json.loads(path.read_text())
        try:
            validator = Draft202012Validator(schema, registry=registry)
            list(validator.iter_errors({}))
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{path.name}: ref resolution failed: {exc}")

    # 3. Round-trip gating on a representative type: valid passes, invalid fails.
    valid = _sample_escalation()
    invalid = _sample_escalation()
    del invalid["producing_agent"]  # drop a required envelope field
    bad_enum = _sample_escalation()
    bad_enum["content"]["status"] = "not-a-status"

    valid_issues = _validate_object(valid, registry)
    if valid_issues:
        failures.append(f"valid escalation sample rejected: {valid_issues}")
    if not _validate_object(invalid, registry):
        failures.append("escalation missing required header field was accepted")
    if not _validate_object(bad_enum, registry):
        failures.append("escalation with bad status enum was accepted")

    if failures:
        print("SELF-CHECK FAILED:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"SELF-CHECK OK: {len(list(SCHEMA_DIR.glob('*.json')))} schema files, "
          f"{len(type_files)} artifact types, gating verified.")
    return 0


def _validate_object(obj, registry):
    sp = schema_path_for(obj["artifact_type"], obj["schema_version"])
    schema = json.loads(sp.read_text())
    validator = Draft202012Validator(schema, registry=registry)
    return [e.message for e in validator.iter_errors(obj)]


def _sample_escalation():
    return {
        "artifact_id": "ESC-20260602-0001",
        "artifact_type": "escalation",
        "schema_version": "v1",
        "producing_agent": "spgr-agent-architect",
        "timestamp": "2026-06-02T12:00:00Z",
        "parent_artifact_ref": None,
        "version": "v0.1-draft",
        "version_type": "draft",
        "confidence_map": {"escalation": "confirmed"},
        "decision_log": [],
        "content": {
            "escalation_id": "ESC-20260602-0001",
            "escalation_type": "missing-input",
            "description": "PRD status is not confirmed.",
            "artifact_ref": "prd-v1",
            "urgency": "urgent",
            "routing_target": "orchestrator",
            "originating_agent": "spgr-agent-architect",
            "status": "open",
        },
    }


def main(argv):
    if len(argv) == 2 and argv[1] == "--self-check":
        return self_check()
    if len(argv) < 2:
        sys.stderr.write(__doc__)
        return 1
    artifact_type = argv[2] if len(argv) > 2 else None
    schema_version = argv[3] if len(argv) > 3 else None
    issues, mode = validate_artifact(argv[1], artifact_type, schema_version)
    if issues:
        print(f"INVALID: {argv[1]}")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    suffix = " (envelope-only, no content schema registered for this type yet)" if mode == "envelope-only" else ""
    print(f"VALID: {argv[1]}{suffix}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
