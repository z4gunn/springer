"""The source host contract. The harness is the only merger, so merge lives here."""

from typing import Protocol


class SourceHost(Protocol):
    def pr_state(self, project, number) -> str:
        """open, merged, or closed."""

    def merge(self, project, number) -> str:
        """Merge and return the merge sha."""

    def retarget(self, project, number, base) -> None:
        """Point a stacked PR at a new base after its parent merged."""

    def diff(self, project, number) -> str: ...
