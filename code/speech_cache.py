"""Provider-independent cache contract for immutable speech clips."""

from pathlib import Path
from typing import Protocol


class SpeechCache(Protocol):
    """Per-clip cache keyed by the existing deterministic MP3 filename."""

    def fetch(self, key: str, destination: Path) -> bool:
        """Materialize only key; on miss return False without changing destination."""
        ...

    def store(self, key: str, source: Path) -> None:
        """Store a finished clip without overwriting an existing immutable key.

        If another writer already stored key, materialize its canonical clip
        back at source before returning. Raise if reconciliation fails; callers
        must not silently render a competing local variant.
        """
        ...
