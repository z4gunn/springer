"""Secret storage. Project secrets live in the OS keyring, and a builder sees test
values only. The value crosses this contract and nothing else."""

from typing import Protocol


class SecretStore(Protocol):
    def set(self, project, name, value) -> None: ...

    def has(self, project, name) -> bool: ...


class KeyringSecrets:
    SERVICE = "springer"

    def _keyring(self):
        import keyring
        return keyring

    def set(self, project, name, value):
        self._keyring().set_password(self.SERVICE, f"{project}/{name}", value)

    def has(self, project, name):
        return self._keyring().get_password(self.SERVICE, f"{project}/{name}") is not None


class MemorySecrets:
    def __init__(self):
        self.values = {}

    def set(self, project, name, value):
        self.values[(project, name)] = value

    def has(self, project, name):
        return (project, name) in self.values
