"""Left-hand block-chord voicing variant registry.

When an accompaniment pattern's ``kind == "block"`` sustains a triad for a
whole bar, always using the same close root-position voicing (in
``LEFT_HAND_OCTAVE``) makes the low left-hand register sound muddy. This
registry lets the generator pick among root position, its two inversions,
and an "open" voicing (root position with only the middle voice raised an
octave) each time a block chord is generated.
"""

from __future__ import annotations

from dataclasses import dataclass

from zunish.registry import Registry


@dataclass(frozen=True)
class VoicingVariant:
    id: str
    name: str
    kind: str  # "invert" or "open_middle"
    inversion: int = 0  # used when kind == "invert"
    weight: float = 1.0


voicings: Registry[VoicingVariant] = Registry("voicing")


def _register(
    entry_id: str,
    name: str,
    kind: str,
    *,
    inversion: int = 0,
    weight: float = 1.0,
) -> None:
    voicings.register(
        VoicingVariant(id=entry_id, name=name, kind=kind, inversion=inversion, weight=weight)
    )


_register("root_position", "基本形", "invert", inversion=0)
_register("first_inversion", "第一転回形", "invert", inversion=1)
_register("second_inversion", "第二転回形", "invert", inversion=2)
_register("open_middle_octave_up", "オープン(中声部オクターブ上げ)", "open_middle")
