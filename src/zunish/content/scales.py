"""Scale registry. All scales are expressed as semitone offsets from the
minor tonic (see :mod:`zunish.theory`)."""

from __future__ import annotations

from dataclasses import dataclass

from zunish import theory
from zunish.registry import Registry


@dataclass(frozen=True)
class Scale:
    id: str
    name: str
    degree_offsets: tuple[int, ...]
    weight: float = 1.0


scales: Registry[Scale] = Registry("scale")


def _register(entry_id: str, name: str, degree_offsets: tuple[int, ...], *, weight: float = 1.0) -> None:
    scales.register(Scale(id=entry_id, name=name, degree_offsets=degree_offsets, weight=weight))


_register("minor_pentatonic_2_6nuki", "短調2・6抜き（ペンタトニック）", theory.MINOR_PENTATONIC_2_6NUKI, weight=1.2)
_register("minor_6nuki", "短調6抜き", theory.MINOR_6NUKI, weight=1.5)
_register("harmonic_minor", "和声的短音階", theory.HARMONIC_MINOR, weight=1.0)
_register("dorian_6", "ドリアの6度", theory.DORIAN_6, weight=1.0)
