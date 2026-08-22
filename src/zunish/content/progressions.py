"""Chord progression registry.

Each progression is a sequence of roman-numeral tokens (see
:mod:`zunish.theory`) plus a ``follows`` weight map used by
:class:`~zunish.director.Director` to pick a musically natural next
progression once the current one finishes looping.

Each roman-numeral token has a parallel ``beats`` duration: either a whole
bar (``BEATS_PER_BAR``, the default) or a half bar. A run of chords whose
``beats`` sum to exactly ``BEATS_PER_BAR`` shares one bar (see
:mod:`zunish.director`); ``validate()`` enforces that every progression's
``romans``/``beats`` resolve cleanly into whole bars on their own, so a
half-bar chord's partner is always another chord from the very same
progression.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from zunish.registry import Registry
from zunish.theory import BEATS_PER_BAR

HALF_BAR_BEATS = BEATS_PER_BAR / 2
ALLOWED_CHORD_BEATS = (BEATS_PER_BAR, HALF_BAR_BEATS)


@dataclass(frozen=True)
class ChordProgression:
    id: str
    name: str
    romans: tuple[str, ...]
    beats: tuple[float, ...] = ()
    start_weight: float = 1.0
    follows: dict[str, float] = field(default_factory=dict)


progressions: Registry[ChordProgression] = Registry("progression")


def _register(
    entry_id: str,
    name: str,
    romans: tuple[str, ...],
    *,
    beats: tuple[float, ...] | None = None,
    start_weight: float = 1.0,
    follows: dict[str, float] | None = None,
) -> None:
    progressions.register(
        ChordProgression(
            id=entry_id,
            name=name,
            romans=romans,
            beats=beats if beats is not None else tuple(BEATS_PER_BAR for _ in romans),
            start_weight=start_weight,
            follows=follows or {},
        )
    )


_register(
    "iv_v_vim",
    "IV-V-VIm",
    ("IV", "V", "VIm"),
    start_weight=2.0,
    follows={
        "iv_v_vim": 1.0,
        "iv_v_vim_2bar": 2.0,
        "iv_v_vi_picardy": 0.8,
        "iv_v_vsus4_vi": 0.8,
        "oudou_tension_nuki": 1.0,
        "jado_shinkou": 0.6,
        "shidan_nagashi": 1.4,
        "avalanche_half": 0.9,
        "vim_v_iv": 1.0,
        "vim_v_iv_v": 0.5,
        "vim_v_ii": 0.4,
        "vim_iiim_ii": 0.4,
    },
)
_register(
    "vim_v_iv",
    "VIm-V-IV",
    ("VIm", "V", "IV"),
    follows={
        "iv_v_vim": 1.5,
        "vim_v_iv": 0.6,
        "vim_v_iv_2bar": 3.0,
        "shidan_nagashi": 0.5,
        "vim_v_ii": 0.3,
        "vim_iiim_ii": 0.3,
    },
)
_register(
    "vim_v_ii",
    "VIm-V-II",
    ("VIm", "V", "II"),
    start_weight=0.4,
    follows={
        "iv_v_vim": 0.8,
        "vim_v_iv": 0.3,
        "vim_v_ii_2bar": 1.8,
        "shidan_nagashi": 0.3,
    },
)
_register(
    "vim_iiim_ii",
    "VIm-IIIm-II",
    ("VIm", "IIIm", "II"),
    start_weight=0.4,
    follows={
        "iv_v_vim": 0.8,
        "vim_v_iv": 0.3,
        "vim_iiim_ii_2bar": 1.8,
        "shidan_nagashi": 0.3,
    },
)
_register(
    "vim_v_iv_v",
    "VIm-V-IV-V (Vターン)",
    ("VIm", "V", "IV", "V"),
    start_weight=0.4,
    follows={
        "iv_v_vim": 1.5,
        "vim_v_iv": 0.5,
        "shidan_nagashi": 0.4,
        "vim_v_ii": 0.3,
        "vim_iiim_ii": 0.3,
    },
)
_register(
    "iv_v_vi_picardy",
    "IV-V-VI (ピカルディ終止)",
    ("IV", "V", "VI"),
    follows={"iv_v_vim": 1.0, "iv_v_vi_picardy_2bar": 3.0, "shidan_nagashi": 0.5},
)
_register(
    "iv_v_vsus4_vi",
    "IV-V-VIsus4-VI",
    ("IV", "V", "VIsus4", "VI"),
    follows={"iv_v_vim": 1.0, "shidan_nagashi": 0.5},
)
_register(
    "oudou_tension_nuki",
    "IV-V-III-VIm (王道進行テンション抜き)",
    ("IV", "V", "III", "VIm"),
    follows={"iv_v_vim": 1.0, "jado_shinkou": 0.5, "shidan_nagashi": 0.5},
)
_register(
    "jado_shinkou",
    "IV-V-V#dim-VIm (邪道進行)",
    ("IV", "V", "V#dim", "VIm"),
    follows={"iv_v_vim": 1.0, "oudou_tension_nuki": 0.5, "shidan_nagashi": 0.5},
)
_register(
    "shidan_nagashi",
    "VIm-V-IV-III (四段流し)",
    ("VIm", "V", "IV", "III"),
    follows={"iv_v_vim": 1.0, "avalanche_full": 0.4, "avalanche_half": 0.4},
)
_register(
    "avalanche_full",
    "VIm-III-V-II-IV-I-IIm-III (雪崩クリシェ)",
    ("VIm", "III", "V", "II", "IV", "I", "IIm", "III"),
    follows={"iv_v_vim": 1.2, "shidan_nagashi": 0.5},
)
_register(
    "avalanche_half",
    "VIm-III-V-II (雪崩クリシェ前半)",
    ("VIm", "III", "V", "II"),
    follows={"iv_v_vim": 2.0, "iv_v_vi_picardy": 1.6, "iv_v_vsus4_vi": 1.6},
)
_register(
    "iv_v_vim_2bar",
    "IV-V-VIm (2コード/小節)",
    ("IV", "V", "VIm"),
    beats=(HALF_BAR_BEATS, HALF_BAR_BEATS, BEATS_PER_BAR),
    start_weight=2.0,
    follows={
        "iv_v_vim": 1.0,
        "iv_v_vim_2bar": 3.0,
        "iv_v_vi_picardy": 0.8,
        "iv_v_vsus4_vi": 0.8,
        "oudou_tension_nuki": 1.0,
        "jado_shinkou": 0.6,
        "shidan_nagashi": 1.4,
        "avalanche_half": 0.9,
        "vim_v_iv": 1.0,
        "vim_v_iv_v": 0.5,
        "vim_v_ii": 0.4,
        "vim_iiim_ii": 0.4,
    },
)
_register(
    "vim_v_iv_2bar",
    "VIm-V-IV (2コード/小節)",
    ("VIm", "V", "IV"),
    beats=(HALF_BAR_BEATS, HALF_BAR_BEATS, BEATS_PER_BAR),
    follows={
        "iv_v_vim": 1.5,
        "iv_v_vim_2bar": 4.0,
        "vim_v_iv": 0.6,
        "vim_v_iv_2bar": 5.0,
        "shidan_nagashi": 0.5,
        "vim_v_ii": 0.3,
        "vim_iiim_ii": 0.3,
    },
)
_register(
    "vim_v_ii_2bar",
    "VIm-V-II (2コード/小節)",
    ("VIm", "V", "II"),
    beats=(HALF_BAR_BEATS, HALF_BAR_BEATS, BEATS_PER_BAR),
    start_weight=0.4,
    follows={
        "iv_v_vim": 0.8,
        "iv_v_vim_2bar": 4.0,
        "vim_v_iv": 0.3,
        "vim_v_ii_2bar": 5.0,
        "shidan_nagashi": 0.3,
    },
)
_register(
    "vim_iiim_ii_2bar",
    "VIm-IIIm-II (2コード/小節)",
    ("VIm", "IIIm", "II"),
    beats=(HALF_BAR_BEATS, HALF_BAR_BEATS, BEATS_PER_BAR),
    start_weight=0.4,
    follows={
        "iv_v_vim": 0.8,
        "iv_v_vim_2bar": 4.0,
        "vim_v_iv": 0.3,
        "vim_iiim_ii_2bar": 5.0,
        "shidan_nagashi": 0.3,
    },
)
_register(
    "iv_v_vi_picardy_2bar",
    "IV-V-VI (ピカルディ終止, 2コード/小節)",
    ("IV", "V", "VI"),
    beats=(HALF_BAR_BEATS, HALF_BAR_BEATS, BEATS_PER_BAR),
    follows={
        "iv_v_vim": 1.0,
        "iv_v_vim_2bar": 4.0,
        "iv_v_vi_picardy_2bar": 5.0,
        "shidan_nagashi": 0.5,
    },
)


def _validate_beats(progression: ChordProgression) -> None:
    """Every chord's duration must be a whole or half bar, and consecutive
    chords must sum to exactly one bar before the next bar's worth begins —
    so a half-bar chord always pairs with another chord from the very same
    progression, never needing to borrow from a repeat or the next
    progression."""
    if len(progression.beats) != len(progression.romans):
        raise ValueError(
            f"progression {progression.id!r} has {len(progression.romans)} romans "
            f"but {len(progression.beats)} beats"
        )
    accumulated = 0.0
    for beats in progression.beats:
        if beats not in ALLOWED_CHORD_BEATS:
            raise ValueError(
                f"progression {progression.id!r} has an unsupported chord duration "
                f"{beats!r} (only {ALLOWED_CHORD_BEATS} are allowed)"
            )
        accumulated += beats
        if accumulated > BEATS_PER_BAR:
            raise ValueError(
                f"progression {progression.id!r} has a chord that overflows a bar "
                f"({accumulated} beats accumulated without hitting a bar boundary)"
            )
        if accumulated == BEATS_PER_BAR:
            accumulated = 0.0
    if accumulated != 0.0:
        raise ValueError(
            f"progression {progression.id!r} does not end on a bar boundary "
            f"({accumulated} beats left over)"
        )


def validate() -> None:
    """Ensure every ``follows`` target refers to a registered progression id,
    and every progression's chord durations resolve cleanly into whole bars."""
    for progression in progressions.all():
        for target_id in progression.follows:
            if target_id not in progressions:
                raise ValueError(
                    f"progression {progression.id!r} follows unknown id {target_id!r}"
                )
        _validate_beats(progression)


validate()
