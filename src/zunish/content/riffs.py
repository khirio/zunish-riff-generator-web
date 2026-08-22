"""Famous fixed riff motifs. Each motif is stored as semitone offsets from
its own root note; :func:`zunish.theory.transpose_motif` places it at the
current chord's root/octave. ``compatible_qualities`` lists the chord
quality suffixes (see :mod:`zunish.theory`, e.g. ``""``=major, ``"m"``=minor,
``"sus4"``) that this motif may be dropped onto.
"""

from __future__ import annotations

from dataclasses import dataclass

from zunish.registry import Registry


@dataclass(frozen=True)
class RiffMotif:
    id: str
    name: str
    intervals: tuple[int, ...]
    compatible_qualities: tuple[str, ...]
    root_octave: int = 3
    weight: float = 1.0


riffs: Registry[RiffMotif] = Registry("riff")


def _register(
    entry_id: str,
    name: str,
    intervals: tuple[int, ...],
    compatible_qualities: tuple[str, ...],
    *,
    root_octave: int = 3,
    weight: float = 1.0,
) -> None:
    riffs.register(
        RiffMotif(
            id=entry_id,
            name=name,
            intervals=intervals,
            compatible_qualities=compatible_qualities,
            root_octave=root_octave,
            weight=weight,
        )
    )


# 7sus4 arpeggio: A3-D4-E4-G4-E4-D4-A3-D4 -> semitone offsets from A3.
_register("sus4_seventh_arpeggio", "7sus4アルペジオ", (0, 5, 7, 10, 7, 5, 0, 5), compatible_qualities=("sus4",))

# Alice arpeggio: A3-E4-D4-E4-C4-E4-B3-E4 -> semitone offsets from A3.
_register("alice_arpeggio", "アリスアルペジオ", (0, 7, 5, 7, 3, 7, 2, 7), compatible_qualities=("m",))
