"""Left-hand accompaniment pattern registry.

``kind == "block"`` sustains every chord tone for the whole bar.
``kind == "broken"`` plays chord tones one at a time; ``note_order`` indexes
into the ascending chord voicing (0=root, 1=third, 2=fifth, wrapping via
modulo for patterns that revisit a tone), or is ``None`` for a rest (the
slot's duration still elapses, but no note sounds). ``thirty_second_note_durations``
gives each slot's length in 32nd-note units (1 bar == 32 units; e.g. an eighth
note is 4, a sixteenth is 2, a 32nd is 1) and must be the same length as
``note_order``. Every note is drawn from the current bar's own chord only —
there is no cross-bar anticipation here.
"""

from __future__ import annotations

from dataclasses import dataclass

from zunish.registry import Registry


@dataclass(frozen=True)
class AccompanimentPattern:
    id: str
    name: str
    kind: str
    note_order: tuple[int | None, ...] = (0, 1, 2)
    thirty_second_note_durations: tuple[int, ...] = (32,)
    weight: float = 1.0


accompaniment: Registry[AccompanimentPattern] = Registry("accompaniment")


def _register(
    entry_id: str,
    name: str,
    kind: str,
    *,
    note_order: tuple[int | None, ...] = (0, 1, 2),
    thirty_second_note_durations: tuple[int, ...] = (32,),
    weight: float = 1.0,
) -> None:
    accompaniment.register(
        AccompanimentPattern(
            id=entry_id,
            name=name,
            kind=kind,
            note_order=note_order,
            thirty_second_note_durations=thirty_second_note_durations,
            weight=weight,
        )
    )


_register("block_chord", "ブロックコード", "block", note_order=(0, 1, 2), thirty_second_note_durations=(32,))
_register(
    "broken_root_fifth_third_fifth",
    "ブロークン(root-5th-3rd-5th)",
    "broken",
    note_order=(0, 2, 1, 2, 0, 2, 1, 2),
    thirty_second_note_durations=(4, 4, 4, 4, 4, 4, 4, 4),
)
_register(
    "dotted_walk",
    "付点2.5拍→16分ウォーク→8分",
    "broken",
    note_order=(0, 0, 1, 2, 0, 0),
    thirty_second_note_durations=(20, 2, 2, 2, 2, 4),
)
_register(
    "tresillo_ornamented",
    "Tresillo複合(16分/32分装飾)",
    "broken",
    note_order=(0, 2, 0, 2, 0, 1, 2, 0),
    thirty_second_note_durations=(1, 1, 10, 12, 2, 2, 2, 2),
)
