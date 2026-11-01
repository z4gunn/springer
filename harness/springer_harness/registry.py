"""~/.springer: the project registry, the harness configuration, and the audit log."""

import json
import os
import secrets
from pathlib import Path

from .common import iso, read_json, write_json
from .errors import NotFound


class Home:
    def __init__(self, root):
        self.root = Path(root)

    @property
    def projects_path(self):
        return self.root / "projects.json"

    @property
    def config_path(self):
        return self.root / "config.json"

    @property
    def audit_path(self):
        return self.root / "audit.jsonl"

    @property
    def token_path(self):
        return self.root / "api-token"

    def token(self):
        """Created once, readable only by the owner."""
        if not self.token_path.exists():
            self.root.mkdir(parents=True, exist_ok=True)
            fd = os.open(self.token_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as fh:
                fh.write(secrets.token_urlsafe(32))
        return self.token_path.read_text().strip()

    def write_port(self, port):
        write_json(self.root / "daemon.json", {"port": port, "pid": os.getpid()})

    def projects(self):
        return read_json(self.projects_path, {})

    def project(self, slug):
        record = self.projects().get(slug)
        if record is None:
            raise NotFound(f"no project {slug}")
        return record

    def save_project(self, slug, record):
        projects = self.projects()
        projects[slug] = record
        write_json(self.projects_path, projects)

    def config(self):
        return read_json(self.config_path, {"role_models": {}, "gate_channels": {}, "staging_hosts": []})

    def save_config(self, config):
        write_json(self.config_path, config)

    def audit(self, entry, epoch):
        self.root.mkdir(parents=True, exist_ok=True)
        with open(self.audit_path, "a") as fh:
            fh.write(json.dumps({"at": iso(epoch), **entry}) + "\n")

    def audit_lines(self):
        if not self.audit_path.exists():
            return []
        return [json.loads(line) for line in self.audit_path.read_text().splitlines() if line.strip()]
