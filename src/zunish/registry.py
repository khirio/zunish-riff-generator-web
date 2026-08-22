"""Generic registry used by every extensible content library (progressions,
scales, riffs, rhythms, accompaniment patterns).

Adding a new element to any of those libraries means adding one call to
``register()`` in the relevant ``content/*.py`` module — no changes to core
logic (generator/director) are needed.
"""

from __future__ import annotations

import random
from typing import Generic, Protocol, TypeVar


class HasId(Protocol):
    @property
    def id(self) -> str: ...


T = TypeVar("T", bound=HasId)
Item = TypeVar("Item")


class Registry(Generic[T]):
    def __init__(self, kind: str):
        self._kind = kind
        self._entries: dict[str, T] = {}

    def register(self, entry: T) -> T:
        if entry.id in self._entries:
            raise ValueError(f"duplicate {self._kind} id: {entry.id!r}")
        self._entries[entry.id] = entry
        return entry

    def get(self, entry_id: str) -> T:
        return self._entries[entry_id]

    def all(self) -> list[T]:
        return list(self._entries.values())

    def ids(self) -> list[str]:
        return list(self._entries.keys())

    def __len__(self) -> int:
        return len(self._entries)

    def __contains__(self, entry_id: str) -> bool:
        return entry_id in self._entries


def weighted_choice(rng: random.Random, candidates: list[tuple[Item, float]]) -> Item:
    """Pick one candidate from explicit ``(item, weight)`` pairs."""
    total = sum(weight for _, weight in candidates)
    if total <= 0:
        raise ValueError("weighted_choice requires at least one positive weight")
    threshold = rng.uniform(0, total)
    cumulative = 0.0
    for item, weight in candidates:
        cumulative += weight
        if threshold <= cumulative:
            return item
    return candidates[-1][0]
