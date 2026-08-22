# 1小節複数コード対応 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the generator so a bar can hold either one whole-bar chord (today's only case) or two half-bar chords, with the right hand free to phrase across the chord boundary and the left hand playing each chord independently within its own share of the bar.

**Architecture:** `ChordProgression` gains a `beats` tuple parallel to `romans` (defaulting to all-whole-bar for backward compatibility). `Director` groups the flat chord stream into bars (lists of `(roman_token, beats)` summing to one bar) instead of assuming one chord per bar. `generator.generate_bar` (renamed from `generate_slot`) takes that list: the right hand keys its riff/rhythm choice off the bar's first chord and may let notes/pitch-pools cross into a second chord; the left hand generates and time-scales each chord's accompaniment independently, then concatenates.

**Tech Stack:** Python 3.13, pytest, dataclasses (existing project conventions — see `RULES.md` for the music-theory rules already in force).

**Spec:** `docs/superpowers/specs/2026-08-14-multi-chord-bars-design.md`

## Global Constraints

- Chord durations are limited to exactly two values: a whole bar (`BEATS_PER_BAR` = 4 beats) or a half bar (2 beats). No other subdivisions.
- A progression's `romans`/`beats` must always resolve into whole bars *within that single progression* — a half-bar chord's pair partner is always the very next (or previous) chord in the same `romans` tuple, never a chord borrowed from a repeat boundary or the next progression.
- Riff motifs (7sus4 arpeggio, Alice arpeggio) are keyed off the bar's **first** chord only, and always render at their existing fixed full-bar length — a second, half-bar chord in the same bar never gates or shortens them.
- The right hand's rhythm pattern and scale choice apply to the whole bar regardless of how many chords it contains; only the chord-tone/decoration pools switch mid-bar.
- The left hand never crosses a chord-segment boundary within a bar (each chord gets its own accompaniment, time-scaled to its own share of the bar); the existing (currently unused/unwired) `_apply_left_hand_anticipation` and `next_minor_tonic_pc`/`next_roman_token` lookahead plumbing stay exactly as unwired as they are today — do not wire them up as part of this plan.
- Every task must leave `uv run pytest` fully green before moving to the next task.

---

### Task 1: Move `BEATS_PER_BAR` to `theory.py`

**Files:**
- Modify: `src/zunish/theory.py`
- Modify: `src/zunish/generator.py:1-33`
- Test: `tests/test_theory.py`

**Interfaces:**
- Produces: `zunish.theory.BEATS_PER_BAR: float` (value `4.0`). `zunish.generator.BEATS_PER_BAR` continues to exist (re-exported) so `player.py` and existing tests importing it from `generator` keep working unchanged.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_theory.py` (new test, anywhere in the file):

```python
def test_beats_per_bar_is_four_quarter_notes():
    assert theory.BEATS_PER_BAR == 4.0
```

Make sure `from zunish import theory` is already imported at the top of the file (it is, for the existing tests).

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_theory.py::test_beats_per_bar_is_four_quarter_notes -v`
Expected: FAIL with `AttributeError: module 'zunish.theory' has no attribute 'BEATS_PER_BAR'`

- [ ] **Step 3: Add the constant to `theory.py` and re-export it from `generator.py`**

In `src/zunish/theory.py`, add near the top-level constants (right after the `CHORD_QUALITY_INTERVALS` block, before the scale constants):

```python
BEATS_PER_BAR: float = 4.0  # a 4/4 bar, in quarter-note beats; shared by content/progressions.py and generator.py
```

In `src/zunish/generator.py`, replace the existing line:

```python
BEATS_PER_BAR = 4.0
```

with:

```python
from zunish.theory import BEATS_PER_BAR
```

placed among the existing imports at the top of the file (right after `from zunish import theory`). Leave every other line in the constants block (`RIGHT_HAND_CHANNEL`, etc.) untouched.

- [ ] **Step 4: Run test to verify it passes, then run the full suite**

Run: `uv run pytest tests/test_theory.py::test_beats_per_bar_is_four_quarter_notes -v`
Expected: PASS

Run: `uv run pytest`
Expected: all tests PASS (this is a pure relocation; nothing else should change)

- [ ] **Step 5: Commit**

```bash
git add src/zunish/theory.py src/zunish/generator.py tests/test_theory.py
git commit -m "BEATS_PER_BARをtheory.pyに移動しgenerator.pyから再エクスポート"
```

---

### Task 2: Add `beats` field and validation to `ChordProgression`

**Files:**
- Modify: `src/zunish/content/progressions.py`
- Test: `tests/test_content_registries.py`

**Interfaces:**
- Consumes: `zunish.theory.BEATS_PER_BAR` (Task 1).
- Produces: `ChordProgression.beats: tuple[float, ...]` (parallel to `romans`, auto-filled to all-`BEATS_PER_BAR` when `_register()` isn't given an explicit `beats=`). `zunish.content.progressions.HALF_BAR_BEATS: float` (`2.0`) and `ALLOWED_CHORD_BEATS: tuple[float, float]` (`(BEATS_PER_BAR, HALF_BAR_BEATS)`). `_validate_beats(progression: ChordProgression) -> None` (raises `ValueError` on any violation).

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_content_registries.py` (add the new imports to the existing `from zunish.content.progressions import progressions` line, and add these tests):

```python
import pytest

from zunish.content.progressions import (
    ALLOWED_CHORD_BEATS,
    ChordProgression,
    _validate_beats,
    progressions,
)


def test_progression_beats_are_parallel_to_romans():
    for progression in progressions.all():
        assert len(progression.beats) == len(progression.romans)


def test_progression_beats_are_whole_or_half_bar_only():
    for progression in progressions.all():
        for beats in progression.beats:
            assert beats in ALLOWED_CHORD_BEATS


def test_existing_progressions_default_to_whole_bar_chords():
    # None of the 9 original progressions specify `beats=`, so every chord
    # should default to a full bar.
    for entry_id in (
        "iv_v_vim", "vim_v_iv", "vim_v_ii", "vim_iiim_ii",
        "iv_v_vi_picardy", "iv_v_vsus4_vi", "shidan_nagashi",
        "avalanche_full", "avalanche_half",
    ):
        progression = progressions.get(entry_id)
        assert progression.beats == (4.0,) * len(progression.romans)


def test_validate_beats_rejects_mismatched_lengths():
    bad = ChordProgression(id="x", name="x", romans=("I", "II"), beats=(4.0,))
    with pytest.raises(ValueError):
        _validate_beats(bad)


def test_validate_beats_rejects_unsupported_duration():
    bad = ChordProgression(id="x", name="x", romans=("I",), beats=(3.0,))
    with pytest.raises(ValueError):
        _validate_beats(bad)


def test_validate_beats_rejects_a_chord_that_overflows_a_bar():
    # 2 + 4 overflows the first bar boundary instead of landing on it.
    bad = ChordProgression(id="x", name="x", romans=("I", "II", "III"), beats=(2.0, 4.0, 2.0))
    with pytest.raises(ValueError):
        _validate_beats(bad)


def test_validate_beats_rejects_leftover_beats_at_the_end():
    bad = ChordProgression(id="x", name="x", romans=("I", "II"), beats=(2.0, 4.0))
    with pytest.raises(ValueError):
        _validate_beats(bad)


def test_validate_beats_accepts_a_half_and_whole_bar_mix():
    ok = ChordProgression(id="x", name="x", romans=("I", "II", "III"), beats=(2.0, 2.0, 4.0))
    _validate_beats(ok)  # must not raise
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_content_registries.py -v`
Expected: FAIL — `ImportError: cannot import name 'ALLOWED_CHORD_BEATS'` (and similar) since none of this exists yet.

- [ ] **Step 3: Implement in `src/zunish/content/progressions.py`**

Replace the whole file's content from the imports through the end of `_register()` (currently lines 1–44) with:

```python
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
```

Leave every `_register(...)` call below this (the existing 9 progressions) untouched — none of them pass `beats=`, so they all default to all-whole-bar automatically.

Then replace the existing `validate()` function (near the end of the file) with:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass, then run the full suite**

Run: `uv run pytest tests/test_content_registries.py -v`
Expected: all PASS

Run: `uv run pytest`
Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/zunish/content/progressions.py tests/test_content_registries.py
git commit -m "ChordProgressionにbeatsフィールドと拍数検証を追加"
```

---

### Task 3: Add the five "2コード/小節" sibling progressions

**Files:**
- Modify: `src/zunish/content/progressions.py`
- Test: `tests/test_content_registries.py`

**Interfaces:**
- Consumes: `ChordProgression`, `_register()`, `HALF_BAR_BEATS`, `BEATS_PER_BAR` (Task 2).
- Produces: five new registered progressions with ids `iv_v_vim_2bar`, `vim_v_iv_2bar`, `vim_v_ii_2bar`, `vim_iiim_ii_2bar`, `iv_v_vi_picardy_2bar`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_content_registries.py`:

```python
TWO_BAR_VARIANT_BASE_IDS = ("iv_v_vim", "vim_v_iv", "vim_v_ii", "vim_iiim_ii", "iv_v_vi_picardy")


def test_two_bar_variants_exist_with_the_expected_beat_layout():
    for base_id in TWO_BAR_VARIANT_BASE_IDS:
        base = progressions.get(base_id)
        variant = progressions.get(f"{base_id}_2bar")
        assert variant.romans == base.romans
        assert variant.beats == (2.0, 2.0, 4.0)


def test_original_progressions_can_transition_into_their_two_bar_variant():
    for base_id in TWO_BAR_VARIANT_BASE_IDS:
        base = progressions.get(base_id)
        assert base.follows[f"{base_id}_2bar"] > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_content_registries.py -k two_bar -v`
Expected: FAIL — `KeyError` (variant id not registered).

- [ ] **Step 3: Implement**

In `src/zunish/content/progressions.py`, edit the five existing `_register(...)` calls to add a sibling `follows` entry each, then append the five new `_register(...)` calls right after them (still before `def validate():`).

Change the `iv_v_vim` registration's `follows` dict from:

```python
    follows={
        "iv_v_vim": 1.0,
        "iv_v_vi_picardy": 0.6,
        "iv_v_vsus4_vi": 0.6,
        "shidan_nagashi": 0.8,
        "avalanche_half": 0.6,
        "vim_v_iv": 0.8,
        "vim_v_ii": 0.3,
        "vim_iiim_ii": 0.3,
    },
```

to:

```python
    follows={
        "iv_v_vim": 1.0,
        "iv_v_vim_2bar": 0.6,
        "iv_v_vi_picardy": 0.6,
        "iv_v_vsus4_vi": 0.6,
        "shidan_nagashi": 0.8,
        "avalanche_half": 0.6,
        "vim_v_iv": 0.8,
        "vim_v_ii": 0.3,
        "vim_iiim_ii": 0.3,
    },
```

Change `vim_v_iv`'s `follows` from:

```python
    follows={
        "iv_v_vim": 1.5,
        "vim_v_iv": 0.6,
        "shidan_nagashi": 0.5,
        "vim_v_ii": 0.3,
        "vim_iiim_ii": 0.3,
    },
```

to:

```python
    follows={
        "iv_v_vim": 1.5,
        "vim_v_iv": 0.6,
        "vim_v_iv_2bar": 0.5,
        "shidan_nagashi": 0.5,
        "vim_v_ii": 0.3,
        "vim_iiim_ii": 0.3,
    },
```

Change `vim_v_ii`'s `follows` from:

```python
    follows={
        "iv_v_vim": 0.8,
        "vim_v_iv": 0.3,
        "shidan_nagashi": 0.3,
    },
)
_register(
    "vim_iiim_ii",
```

to (note this only touches the `vim_v_ii` block, immediately followed by the unchanged `vim_iiim_ii` registration header — match on the full block to avoid ambiguity with `vim_iiim_ii`'s identical `follows` dict below it):

```python
    follows={
        "iv_v_vim": 0.8,
        "vim_v_iv": 0.3,
        "vim_v_ii_2bar": 0.3,
        "shidan_nagashi": 0.3,
    },
)
_register(
    "vim_iiim_ii",
```

Change `vim_iiim_ii`'s `follows` (the one immediately preceding the `iv_v_vi_picardy` registration) from:

```python
    follows={
        "iv_v_vim": 0.8,
        "vim_v_iv": 0.3,
        "shidan_nagashi": 0.3,
    },
)
_register(
    "iv_v_vi_picardy",
```

to:

```python
    follows={
        "iv_v_vim": 0.8,
        "vim_v_iv": 0.3,
        "vim_iiim_ii_2bar": 0.3,
        "shidan_nagashi": 0.3,
    },
)
_register(
    "iv_v_vi_picardy",
```

Change `iv_v_vi_picardy`'s `follows` from:

```python
    follows={"iv_v_vim": 1.0, "shidan_nagashi": 0.5},
)
_register(
    "iv_v_vsus4_vi",
```

to:

```python
    follows={"iv_v_vim": 1.0, "iv_v_vi_picardy_2bar": 0.5, "shidan_nagashi": 0.5},
)
_register(
    "iv_v_vsus4_vi",
```

Then, right after the `avalanche_half` registration and before `def validate():`, append:

```python
_register(
    "iv_v_vim_2bar",
    "IV-V-VIm (2コード/小節)",
    ("IV", "V", "VIm"),
    beats=(HALF_BAR_BEATS, HALF_BAR_BEATS, BEATS_PER_BAR),
    start_weight=2.0,
    follows={
        "iv_v_vim": 1.0,
        "iv_v_vi_picardy": 0.6,
        "iv_v_vsus4_vi": 0.6,
        "shidan_nagashi": 0.8,
        "avalanche_half": 0.6,
        "vim_v_iv": 0.8,
        "vim_v_ii": 0.3,
        "vim_iiim_ii": 0.3,
    },
)
_register(
    "vim_v_iv_2bar",
    "VIm-V-IV (2コード/小節)",
    ("VIm", "V", "IV"),
    beats=(HALF_BAR_BEATS, HALF_BAR_BEATS, BEATS_PER_BAR),
    follows={
        "iv_v_vim": 1.5,
        "vim_v_iv": 0.6,
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
        "vim_v_iv": 0.3,
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
        "vim_v_iv": 0.3,
        "shidan_nagashi": 0.3,
    },
)
_register(
    "iv_v_vi_picardy_2bar",
    "IV-V-VI (ピカルディ終止, 2コード/小節)",
    ("IV", "V", "VI"),
    beats=(HALF_BAR_BEATS, HALF_BAR_BEATS, BEATS_PER_BAR),
    follows={"iv_v_vim": 1.0, "shidan_nagashi": 0.5},
)
```

- [ ] **Step 4: Run tests to verify they pass, then run the full suite**

Run: `uv run pytest tests/test_content_registries.py -v`
Expected: all PASS

Run: `uv run pytest`
Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/zunish/content/progressions.py tests/test_content_registries.py
git commit -m "3コード進行5つに2コード/小節の姉妹進行を追加"
```

---

### Task 4: Make `_add_dyads` pool-lookup-aware

**Files:**
- Modify: `src/zunish/generator.py` (the `_add_dyads` function and its one call site inside `_melody_note_events`)
- Test: `tests/test_generator.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `_add_dyads(rng, events, chord_tone_pool_at: Callable[[float], list[int]]) -> list[NoteEvent]` — the third parameter changes from a static `list[int]` to a callable that resolves the active chord-tone pool for a given `start_beat`. This lets later tasks pick a different pool per event once a bar can hold more than one chord.

- [ ] **Step 1: Write the failing tests**

In `tests/test_generator.py`, replace the two existing `_add_dyads` tests:

```python
def test_add_dyads_never_doubles_notes_shorter_than_an_eighth_note():
    short_note = generator.NoteEvent(pitch=60, start_beat=0.0, duration_beat=0.25, velocity=100, channel=0)
    chord_tone_pool = generator._midi_pool([0, 4, 7])
    for seed in range(50):
        result = generator._add_dyads(random.Random(seed), [short_note], lambda _start_beat: chord_tone_pool)
        assert len(result) == 1


def test_add_dyads_adds_a_different_pitch_class_chord_tone_for_long_notes():
    long_note = generator.NoteEvent(pitch=64, start_beat=0.0, duration_beat=1.0, velocity=100, channel=0)
    chord_tone_pool = generator._midi_pool([0, 4, 7])
    triggered = False
    for seed in range(50):
        result = generator._add_dyads(random.Random(seed), [long_note], lambda _start_beat: chord_tone_pool)
        assert len(result) in (1, 2)
        if len(result) == 2:
            triggered = True
            assert result[0].start_beat == result[1].start_beat == 0.0
            assert result[0].duration_beat == result[1].duration_beat == 1.0
            assert result[0].channel == result[1].channel == 0
            assert result[0].pitch % 12 != result[1].pitch % 12
    assert triggered
```

and add a new test right after them:

```python
def test_add_dyads_looks_up_the_pool_active_at_each_events_own_start_beat():
    early_note = generator.NoteEvent(pitch=60, start_beat=0.0, duration_beat=1.0, velocity=100, channel=0)
    late_note = generator.NoteEvent(pitch=60, start_beat=2.0, duration_beat=1.0, velocity=100, channel=0)
    early_pool = generator._midi_pool([0, 4, 7])
    late_pool = generator._midi_pool([2, 5, 9])

    def pool_at(start_beat):
        return early_pool if start_beat < 2.0 else late_pool

    triggered_late = False
    for seed in range(100):
        result = generator._add_dyads(random.Random(seed), [early_note, late_note], pool_at)
        late_dyad = [e for e in result if e.start_beat == 2.0 and e.pitch != 60]
        if late_dyad:
            triggered_late = True
            assert late_dyad[0].pitch % 12 in {2, 5, 9}
    assert triggered_late
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_generator.py -k add_dyads -v`
Expected: FAIL — `TypeError: 'list' object is not callable` (the current `_add_dyads` calls `_pick_harmony_tone(rng, event.pitch, chord_tone_pool)` where `chord_tone_pool` would now be the lambda, but the *old* implementation still expects a plain list — the failure mode is the lambda being iterated/indexed as if it were a list, e.g. `TypeError` from `_pick_harmony_tone`'s list comprehension over a function).

- [ ] **Step 3: Implement**

In `src/zunish/generator.py`, find `_add_dyads` (currently around line 157) and its call site inside `_melody_note_events` (currently the last line of that function, around line 239: `return _add_dyads(rng, events, chord_tone_pool)`).

Replace the `_add_dyads` function:

```python
def _add_dyads(rng: random.Random, events: list[NoteEvent], chord_tone_pool: list[int]) -> list[NoteEvent]:
    """Double eighth-note-or-longer notes with a second, harmonizing chord tone."""
    result: list[NoteEvent] = []
    for event in events:
        result.append(event)
        if event.duration_beat < DYAD_MIN_DURATION_BEAT or rng.random() >= DYAD_PROBABILITY:
            continue
        harmony_pitch = _pick_harmony_tone(rng, event.pitch, chord_tone_pool)
        if harmony_pitch is None:
            continue
        result.append(
            NoteEvent(
                pitch=harmony_pitch,
                start_beat=event.start_beat,
                duration_beat=event.duration_beat,
                velocity=_jittered_velocity(rng, RIGHT_HAND_BASE_VELOCITY),
                channel=event.channel,
            )
        )
    return result
```

with:

```python
def _add_dyads(
    rng: random.Random,
    events: list[NoteEvent],
    chord_tone_pool_at: Callable[[float], list[int]],
) -> list[NoteEvent]:
    """Double eighth-note-or-longer notes with a second, harmonizing chord
    tone, drawn from whichever chord is active at that note's own start beat
    (``chord_tone_pool_at``) — relevant once a bar can hold more than one
    chord."""
    result: list[NoteEvent] = []
    for event in events:
        result.append(event)
        if event.duration_beat < DYAD_MIN_DURATION_BEAT or rng.random() >= DYAD_PROBABILITY:
            continue
        harmony_pitch = _pick_harmony_tone(rng, event.pitch, chord_tone_pool_at(event.start_beat))
        if harmony_pitch is None:
            continue
        result.append(
            NoteEvent(
                pitch=harmony_pitch,
                start_beat=event.start_beat,
                duration_beat=event.duration_beat,
                velocity=_jittered_velocity(rng, RIGHT_HAND_BASE_VELOCITY),
                channel=event.channel,
            )
        )
    return result
```

Add `from collections.abc import Callable` to the imports at the top of `generator.py` (alongside the existing `import random` / `from dataclasses import ...` lines).

Update the call site inside `_melody_note_events` from:

```python
    return _add_dyads(rng, events, chord_tone_pool)
```

to:

```python
    return _add_dyads(rng, events, lambda _start_beat: chord_tone_pool)
```

(This is a temporary single-pool wrapper; Task 5 replaces it with a real per-segment lookup once `_melody_note_events` becomes chord-list-aware. `_melody_note_events`'s own external signature is untouched in this task.)

- [ ] **Step 4: Run tests to verify they pass, then run the full suite**

Run: `uv run pytest tests/test_generator.py -v`
Expected: all PASS

Run: `uv run pytest`
Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/zunish/generator.py tests/test_generator.py
git commit -m "_add_dyadsをコードトーンプールのcallable受け取りに変更"
```

---

### Task 5: Make melody generation chord-segment-aware

**Files:**
- Modify: `src/zunish/generator.py` (new `_MelodySegment`, `_build_melody_segments`, `_segment_at`, `_nearest_pool_index`; rewritten `_melody_note_events`; the one call site inside `_right_hand_events`)
- Test: `tests/test_generator.py`

**Interfaces:**
- Consumes: `_add_dyads(rng, events, chord_tone_pool_at)` (Task 4).
- Produces: `_melody_note_events(rng, minor_tonic_pc, chords: list[tuple[str, float]], rhythm) -> list[NoteEvent]` — its third parameter changes from a single `roman_token: str` to a `chords` list of `(roman_token, beats)` pairs summing to `BEATS_PER_BAR`. Also produces `_build_melody_segments(minor_tonic_pc, chords, scale) -> list[_MelodySegment]` and `_segment_at(segments, start_beat) -> _MelodySegment`, usable directly in tests.

- [ ] **Step 1: Write the failing tests**

In `tests/test_generator.py`, every existing direct call to `generator._melody_note_events(rng, MINOR_TONIC_PC, token, rhythm)` must wrap `token` into a single-chord list. Update these five existing tests (find each by name):

```python
def test_melody_note_events_never_produces_banned_sixth():
    banned_pc = (MINOR_TONIC_PC + generator.BANNED_DEGREE_OFFSET) % 12
    for token in ROMAN_TOKENS:
        for seed in range(50):
            events = generator._melody_note_events(
                random.Random(seed), MINOR_TONIC_PC, [(token, BEATS_PER_BAR)], FOUR_QUARTER_NOTES
            )
            assert all(event.pitch % 12 != banned_pc for event in events)


def test_melody_note_events_dorian_sixth_only_when_chord_tone():
    dorian_pc = (MINOR_TONIC_PC + generator.DORIAN_SIXTH_OFFSET) % 12
    for token in ROMAN_TOKENS:
        chord_tone_pcs = generator._melody_chord_tone_pcs(MINOR_TONIC_PC, token)
        if dorian_pc in chord_tone_pcs:
            continue
        for seed in range(50):
            events = generator._melody_note_events(
                random.Random(seed), MINOR_TONIC_PC, [(token, BEATS_PER_BAR)], FOUR_QUARTER_NOTES
            )
            assert all(event.pitch % 12 != dorian_pc for event in events)


def test_melody_note_events_respects_non_chord_tone_budget():
    for token in ROMAN_TOKENS:
        chord_tone_pcs = set(generator._melody_chord_tone_pcs(MINOR_TONIC_PC, token))
        for seed in range(100):
            events = generator._melody_note_events(
                random.Random(seed), MINOR_TONIC_PC, [(token, BEATS_PER_BAR)], FOUR_QUARTER_NOTES
            )
            non_chord_tone_count = sum(1 for event in events if event.pitch % 12 not in chord_tone_pcs)
            assert non_chord_tone_count <= generator.MAX_NON_CHORD_TONES_PER_BAR


def test_melody_note_events_appoggiatura_resolves_stepwise_onto_a_chord_tone():
    chord_tone_pcs = set(generator._melody_chord_tone_pcs(MINOR_TONIC_PC, "V"))
    found_a_split = False
    for seed in range(300):
        events = generator._melody_note_events(
            random.Random(seed), MINOR_TONIC_PC, [("V", BEATS_PER_BAR)], FOUR_QUARTER_NOTES
        )
        if len(events) <= len(FOUR_QUARTER_NOTES.sixteenth_note_durations):
            continue
        for first, second in zip(events, events[1:]):
            if first.pitch % 12 in chord_tone_pcs or second.pitch % 12 not in chord_tone_pcs:
                continue
            if first.start_beat + first.duration_beat != second.start_beat:
                continue
            found_a_split = True
            assert first.duration_beat == second.duration_beat
            assert abs(first.pitch - second.pitch) <= 2
    assert found_a_split
```

(`test_melody_decoration_pcs_excludes_chord_tones` and the other `_melody_chord_tone_pcs`/`_melody_decoration_pcs`/`_pick_neighbor_tone`/`_pick_harmony_tone` tests are untouched — those helpers themselves don't change.)

Add `BEATS_PER_BAR` to the existing `from zunish.generator import BEATS_PER_BAR, generate_slot` import line at the top of the file (it's likely already imported; if not, add it).

Then add new tests for the segment-building helpers and the multi-chord behavior, anywhere after the existing melody tests:

```python
def test_build_melody_segments_splits_the_bar_by_chord():
    scale = scales.get("harmonic_minor")
    chords = [("IV", 2.0), ("V", 2.0)]
    segments = generator._build_melody_segments(MINOR_TONIC_PC, chords, scale)
    assert [(s.start_beat, s.end_beat) for s in segments] == [(0.0, 2.0), (2.0, 4.0)]
    iv_pcs = set(generator._melody_chord_tone_pcs(MINOR_TONIC_PC, "IV"))
    v_pcs = set(generator._melody_chord_tone_pcs(MINOR_TONIC_PC, "V"))
    assert {p % 12 for p in segments[0].chord_tone_pool} == iv_pcs
    assert {p % 12 for p in segments[1].chord_tone_pool} == v_pcs


def test_segment_at_picks_the_covering_segment_including_the_final_edge():
    scale = scales.get("harmonic_minor")
    chords = [("IV", 2.0), ("V", 2.0)]
    segments = generator._build_melody_segments(MINOR_TONIC_PC, chords, scale)
    assert generator._segment_at(segments, 0.0) is segments[0]
    assert generator._segment_at(segments, 1.99) is segments[0]
    assert generator._segment_at(segments, 2.0) is segments[1]
    assert generator._segment_at(segments, 3.99) is segments[1]


def test_melody_note_events_with_two_chords_never_produces_banned_sixth():
    banned_pc = (MINOR_TONIC_PC + generator.BANNED_DEGREE_OFFSET) % 12
    chords = [("IV", 2.0), ("V", 2.0)]
    for seed in range(50):
        events = generator._melody_note_events(random.Random(seed), MINOR_TONIC_PC, chords, FOUR_QUARTER_NOTES)
        assert all(event.pitch % 12 != banned_pc for event in events)


def test_melody_note_events_uses_the_second_chords_tones_after_the_switch():
    # IV = {A, C} (b6/F excluded); V = {G, B, D}. No overlap, so any note
    # landing on beat >= 2.0 with one of V's pitch classes proves the walk
    # actually switched pools rather than continuing to use IV's.
    iv_pcs = set(generator._melody_chord_tone_pcs(MINOR_TONIC_PC, "IV"))
    v_only_pcs = set(generator._melody_chord_tone_pcs(MINOR_TONIC_PC, "V")) - iv_pcs
    chords = [("IV", 2.0), ("V", 2.0)]
    found = False
    for seed in range(100):
        events = generator._melody_note_events(random.Random(seed), MINOR_TONIC_PC, chords, FOUR_QUARTER_NOTES)
        for event in events:
            if event.start_beat >= 2.0 and event.pitch % 12 in v_only_pcs:
                found = True
    assert found
```

Make sure `from zunish.content.scales import scales` is already imported at the top of the test file (it is).

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_generator.py -v`
Expected: FAIL — the wrapped-token melody tests fail with a `TypeError`/`ValueError` from inside `_melody_chord_tone_pcs` (called with a list instead of a string), and the new segment tests fail with `AttributeError: module has no attribute '_build_melody_segments'`.

- [ ] **Step 3: Implement**

In `src/zunish/generator.py`, add these two new helpers right before `_melody_note_events` (which currently starts around line 183):

```python
@dataclass(frozen=True)
class _MelodySegment:
    start_beat: float
    end_beat: float
    chord_tone_pool: list[int]
    decoration_pool: list[int]


def _build_melody_segments(minor_tonic_pc: int, chords: list[tuple[str, float]], scale) -> list[_MelodySegment]:
    segments: list[_MelodySegment] = []
    t = 0.0
    for roman_token, beats in chords:
        chord_tone_pcs = _melody_chord_tone_pcs(minor_tonic_pc, roman_token)
        chord_tone_pool = _midi_pool(chord_tone_pcs) or [69]
        decoration_pcs = _melody_decoration_pcs(minor_tonic_pc, scale, chord_tone_pcs)
        decoration_pool = _midi_pool(decoration_pcs)
        segments.append(_MelodySegment(t, t + beats, chord_tone_pool, decoration_pool))
        t += beats
    return segments


def _segment_at(segments: list[_MelodySegment], start_beat: float) -> _MelodySegment:
    for segment in segments:
        if segment.start_beat <= start_beat < segment.end_beat - 1e-9:
            return segment
    return segments[-1]


def _nearest_pool_index(pool: list[int], pitch: int) -> int:
    return min(range(len(pool)), key=lambda i: abs(pool[i] - pitch))
```

Then replace the whole `_melody_note_events` function with:

```python
def _melody_note_events(
    rng: random.Random, minor_tonic_pc: int, chords: list[tuple[str, float]], rhythm: RhythmPattern
) -> list[NoteEvent]:
    scale = weighted_choice(rng, [(s, s.weight) for s in scales.all()])
    segments = _build_melody_segments(minor_tonic_pc, chords, scale)

    pitch: int | None = None
    non_chord_tone_budget = MAX_NON_CHORD_TONES_PER_BAR
    events: list[NoteEvent] = []
    for start_beat, duration_beat in rhythm.onsets_in_beats():
        segment = _segment_at(segments, start_beat)
        pool = segment.chord_tone_pool
        if pitch is None:
            index = rng.randrange(len(pool))
        else:
            index = _nearest_pool_index(pool, pitch)
            step = rng.choices((-2, -1, 1, 2), weights=(1, 3, 3, 1))[0]
            index = max(0, min(len(pool) - 1, index + step))
        pitch = pool[index]

        eligible = (
            duration_beat >= APPOGGIATURA_MIN_DURATION_BEAT
            and _is_strong_beat(start_beat)
            and non_chord_tone_budget > 0
            and segment.decoration_pool
        )
        neighbor = _pick_neighbor_tone(rng, pitch, segment.decoration_pool) if eligible else None
        if neighbor is not None and rng.random() < APPOGGIATURA_PROBABILITY:
            half = duration_beat / 2
            events.append(
                NoteEvent(
                    pitch=neighbor,
                    start_beat=start_beat,
                    duration_beat=half,
                    velocity=_jittered_velocity(rng, RIGHT_HAND_BASE_VELOCITY),
                    channel=RIGHT_HAND_CHANNEL,
                )
            )
            events.append(
                NoteEvent(
                    pitch=pitch,
                    start_beat=start_beat + half,
                    duration_beat=half,
                    velocity=_jittered_velocity(rng, RIGHT_HAND_BASE_VELOCITY),
                    channel=RIGHT_HAND_CHANNEL,
                )
            )
            non_chord_tone_budget -= 1
        else:
            events.append(
                NoteEvent(
                    pitch=pitch,
                    start_beat=start_beat,
                    duration_beat=duration_beat,
                    velocity=_jittered_velocity(rng, RIGHT_HAND_BASE_VELOCITY),
                    channel=RIGHT_HAND_CHANNEL,
                )
            )

    def chord_tone_pool_at(start_beat: float) -> list[int]:
        return _segment_at(segments, start_beat).chord_tone_pool

    return _add_dyads(rng, events, chord_tone_pool_at)
```

Update the one call site inside `_right_hand_events` (currently near the bottom of that function) from:

```python
    rhythm = weighted_choice(rng, [(r, r.weight) for r in rhythms.all()])
    return _melody_note_events(rng, minor_tonic_pc, roman_token, rhythm)
```

to:

```python
    rhythm = weighted_choice(rng, [(r, r.weight) for r in rhythms.all()])
    return _melody_note_events(rng, minor_tonic_pc, [(roman_token, BEATS_PER_BAR)], rhythm)
```

(This keeps `_right_hand_events`'s own external signature — still `roman_token: str` — unchanged for this task; Task 6 threads a real `chords` list all the way through it.)

- [ ] **Step 4: Run tests to verify they pass, then run the full suite**

Run: `uv run pytest tests/test_generator.py -v`
Expected: all PASS

Run: `uv run pytest`
Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/zunish/generator.py tests/test_generator.py
git commit -m "メロディ生成をコード区間(chords)対応にリファクタリング"
```

---

### Task 6: Thread `chords` through `_right_hand_events`

**Files:**
- Modify: `src/zunish/generator.py` (`_right_hand_events` and its one call site inside `generate_slot`)
- Test: `tests/test_generator.py`

**Interfaces:**
- Consumes: `_melody_note_events(rng, minor_tonic_pc, chords, rhythm)` (Task 5).
- Produces: `_right_hand_events(rng, minor_tonic_pc, chords: list[tuple[str, float]]) -> list[NoteEvent]` — its third parameter changes from `roman_token: str` to a `chords` list; riff eligibility/root is keyed off `chords[0]` only.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_generator.py`:

```python
def test_right_hand_events_riff_keys_off_the_first_chord_only():
    # Same fixed 7sus4 quotation as the single-chord case (root G3=55); a
    # trailing half-bar "IV" chord in the same bar must not gate or alter it.
    expected_pitches = [55, 60, 62, 65, 62, 60, 55, 60]
    for seed in range(200):
        events = generator._right_hand_events(random.Random(seed), MINOR_TONIC_PC, [("Vsus4", 2.0), ("IV", 2.0)])
        if [e.pitch for e in events] == expected_pitches:
            break
    else:
        raise AssertionError("expected the 7sus4 arpeggio to trigger off the first (half-bar) chord")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_generator.py -k riff_keys_off -v`
Expected: FAIL — `TypeError` from `theory.parse_roman_numeral` receiving a list instead of a string (current `_right_hand_events` still takes a bare `roman_token`).

- [ ] **Step 3: Implement**

Replace `_right_hand_events` (currently):

```python
def _right_hand_events(
    rng: random.Random, minor_tonic_pc: int, roman_token: str
) -> list[NoteEvent]:
    _degree, quality = theory.parse_roman_numeral(roman_token)
    riff = _pick_riff_or_none(rng, quality)
    if riff is not None:
        root_pc = theory.chord_root_pc(minor_tonic_pc, roman_token)
        notes = theory.transpose_motif(riff.intervals, root_pc, riff.root_octave)
        return _riff_note_events(rng, notes)

    rhythm = weighted_choice(rng, [(r, r.weight) for r in rhythms.all()])
    return _melody_note_events(rng, minor_tonic_pc, [(roman_token, BEATS_PER_BAR)], rhythm)
```

with:

```python
def _right_hand_events(
    rng: random.Random, minor_tonic_pc: int, chords: list[tuple[str, float]]
) -> list[NoteEvent]:
    lead_roman_token, _lead_beats = chords[0]
    _degree, quality = theory.parse_roman_numeral(lead_roman_token)
    riff = _pick_riff_or_none(rng, quality)
    if riff is not None:
        root_pc = theory.chord_root_pc(minor_tonic_pc, lead_roman_token)
        notes = theory.transpose_motif(riff.intervals, root_pc, riff.root_octave)
        return _riff_note_events(rng, notes)

    rhythm = weighted_choice(rng, [(r, r.weight) for r in rhythms.all()])
    return _melody_note_events(rng, minor_tonic_pc, chords, rhythm)
```

Update the one call site inside `generate_slot` (still named `generate_slot` at this point — its own signature isn't touched until Task 8) from:

```python
    return _right_hand_events(rng, minor_tonic_pc, roman_token) + _left_hand_events(
        rng, minor_tonic_pc, roman_token
    )
```

to:

```python
    return _right_hand_events(rng, minor_tonic_pc, [(roman_token, BEATS_PER_BAR)]) + _left_hand_events(
        rng, minor_tonic_pc, roman_token
    )
```

- [ ] **Step 4: Run tests to verify they pass, then run the full suite**

Run: `uv run pytest tests/test_generator.py -v`
Expected: all PASS

Run: `uv run pytest`
Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/zunish/generator.py tests/test_generator.py
git commit -m "_right_hand_eventsをchordsリスト対応にし、リフ判定を先頭コードに固定"
```

---

### Task 7: Make `_left_hand_events` duration/offset-parametrized, add `_left_hand_events_for_bar`

**Files:**
- Modify: `src/zunish/generator.py` (`_left_hand_events`, new `_left_hand_events_for_bar`, and the one call site inside `generate_slot`)
- Test: `tests/test_generator.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `_left_hand_events(rng, minor_tonic_pc, roman_token, duration_beats=BEATS_PER_BAR, start_offset_beat=0.0) -> list[NoteEvent]` (two new optional parameters, defaults preserve today's behavior exactly). `_left_hand_events_for_bar(rng, minor_tonic_pc, chords: list[tuple[str, float]]) -> list[NoteEvent]` (new function: calls `_left_hand_events` once per chord segment and concatenates with the right offsets).

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_generator.py`:

```python
def test_left_hand_events_scales_a_block_chord_to_a_half_bar_segment(monkeypatch):
    monkeypatch.setattr(generator.accompaniment, "all", lambda: [accompaniment.get("block_chord")])
    events = generator._left_hand_events(
        random.Random(1), MINOR_TONIC_PC, "IV", duration_beats=2.0, start_offset_beat=2.0
    )
    assert events
    for event in events:
        assert event.start_beat == 2.0
        assert event.duration_beat == 2.0


def test_left_hand_events_scales_a_broken_pattern_to_a_half_bar_segment(monkeypatch):
    monkeypatch.setattr(generator.accompaniment, "all", lambda: [accompaniment.get("broken_root_fifth_third_fifth")])
    events = generator._left_hand_events(
        random.Random(1), MINOR_TONIC_PC, "IV", duration_beats=2.0, start_offset_beat=2.0
    )
    assert events
    # Each of the pattern's 8 equal eighth-note slots (0.5 beat at full-bar
    # scale) becomes a sixteenth note (0.25 beat) when squeezed into half a bar.
    assert all(abs(e.duration_beat - 0.25) < 1e-9 for e in events)
    assert min(e.start_beat for e in events) == 2.0
    assert max(e.start_beat + e.duration_beat for e in events) <= 4.0 + 1e-9


def test_left_hand_events_for_bar_concatenates_each_chords_own_segment(monkeypatch):
    monkeypatch.setattr(generator.accompaniment, "all", lambda: [accompaniment.get("block_chord")])
    monkeypatch.setattr(generator.voicings, "all", lambda: [generator.voicings.get("root_position")])
    chords = [("IV", 2.0), ("V", 2.0)]
    events = generator._left_hand_events_for_bar(random.Random(1), MINOR_TONIC_PC, chords)

    early = [e for e in events if e.start_beat == 0.0]
    late = [e for e in events if e.start_beat == 2.0]
    assert early and late
    assert all(e.duration_beat == 2.0 for e in events)
    iv_pcs = set(generator.theory.chord_pitch_classes(MINOR_TONIC_PC, "IV"))
    v_pcs = set(generator.theory.chord_pitch_classes(MINOR_TONIC_PC, "V"))
    assert {e.pitch % 12 for e in early} == iv_pcs
    assert {e.pitch % 12 for e in late} == v_pcs
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_generator.py -k "half_bar_segment or events_for_bar" -v`
Expected: FAIL — `TypeError: _left_hand_events() got an unexpected keyword argument 'duration_beats'` and `AttributeError: module 'zunish.generator' has no attribute '_left_hand_events_for_bar'`.

- [ ] **Step 3: Implement**

Replace `_left_hand_events` (currently the function right before `generate_slot`):

```python
def _left_hand_events(
    rng: random.Random, minor_tonic_pc: int, roman_token: str
) -> list[NoteEvent]:
    pattern: AccompanimentPattern = weighted_choice(rng, [(p, p.weight) for p in accompaniment.all()])
    voicing = theory.chord_tones_midi(minor_tonic_pc, roman_token, LEFT_HAND_OCTAVE)

    events: list[NoteEvent] = []
    if pattern.kind == "block":
        variant: VoicingVariant = weighted_choice(rng, [(v, v.weight) for v in voicings.all()])
        block_voicing = (
            theory.invert_voicing(voicing, variant.inversion)
            if variant.kind == "invert"
            else theory.raise_middle_voice(voicing)
        )
        velocity = _jittered_velocity(rng, LEFT_HAND_BASE_VELOCITY)
        for tone_index in pattern.note_order:
            events.append(
                NoteEvent(
                    pitch=block_voicing[tone_index % len(block_voicing)],
                    start_beat=0.0,
                    duration_beat=BEATS_PER_BAR,
                    velocity=velocity,
                    channel=LEFT_HAND_CHANNEL,
                )
            )
    else:
        beat_per_unit = 1.0 / 8.0  # one 32nd note in beats (32 units == BEATS_PER_BAR)
        t = 0.0
        for tone_index, duration_units in zip(pattern.note_order, pattern.thirty_second_note_durations):
            if t >= BEATS_PER_BAR:
                break
            duration_beat = min(duration_units * beat_per_unit, BEATS_PER_BAR - t)
            if tone_index is not None:
                events.append(
                    NoteEvent(
                        pitch=voicing[tone_index % len(voicing)],
                        start_beat=t,
                        duration_beat=duration_beat,
                        velocity=_jittered_velocity(rng, LEFT_HAND_BASE_VELOCITY),
                        channel=LEFT_HAND_CHANNEL,
                    )
                )
            t += duration_beat

    return events
```

with:

```python
def _left_hand_events(
    rng: random.Random,
    minor_tonic_pc: int,
    roman_token: str,
    duration_beats: float = BEATS_PER_BAR,
    start_offset_beat: float = 0.0,
) -> list[NoteEvent]:
    """Generate one chord's left-hand accompaniment, scaled to fit in
    ``duration_beats`` (a whole or half bar) and placed starting at
    ``start_offset_beat`` within the bar."""
    pattern: AccompanimentPattern = weighted_choice(rng, [(p, p.weight) for p in accompaniment.all()])
    voicing = theory.chord_tones_midi(minor_tonic_pc, roman_token, LEFT_HAND_OCTAVE)

    events: list[NoteEvent] = []
    if pattern.kind == "block":
        variant: VoicingVariant = weighted_choice(rng, [(v, v.weight) for v in voicings.all()])
        block_voicing = (
            theory.invert_voicing(voicing, variant.inversion)
            if variant.kind == "invert"
            else theory.raise_middle_voice(voicing)
        )
        velocity = _jittered_velocity(rng, LEFT_HAND_BASE_VELOCITY)
        for tone_index in pattern.note_order:
            events.append(
                NoteEvent(
                    pitch=block_voicing[tone_index % len(block_voicing)],
                    start_beat=start_offset_beat,
                    duration_beat=duration_beats,
                    velocity=velocity,
                    channel=LEFT_HAND_CHANNEL,
                )
            )
    else:
        scale_factor = duration_beats / BEATS_PER_BAR
        beat_per_unit = scale_factor / 8.0  # one 32nd note in beats, scaled to this segment's share of the bar
        t = 0.0
        for tone_index, duration_units in zip(pattern.note_order, pattern.thirty_second_note_durations):
            if t >= duration_beats:
                break
            duration_beat = min(duration_units * beat_per_unit, duration_beats - t)
            if tone_index is not None:
                events.append(
                    NoteEvent(
                        pitch=voicing[tone_index % len(voicing)],
                        start_beat=start_offset_beat + t,
                        duration_beat=duration_beat,
                        velocity=_jittered_velocity(rng, LEFT_HAND_BASE_VELOCITY),
                        channel=LEFT_HAND_CHANNEL,
                    )
                )
            t += duration_beat

    return events


def _left_hand_events_for_bar(
    rng: random.Random, minor_tonic_pc: int, chords: list[tuple[str, float]]
) -> list[NoteEvent]:
    """Generate left-hand accompaniment for a whole bar: each chord segment
    is generated independently (its own pattern/voicing pick) and time-scaled
    to its own share of the bar, then concatenated in order."""
    events: list[NoteEvent] = []
    t = 0.0
    for roman_token, beats in chords:
        events.extend(_left_hand_events(rng, minor_tonic_pc, roman_token, beats, t))
        t += beats
    return events
```

Update the one call site inside `generate_slot` from:

```python
    return _right_hand_events(rng, minor_tonic_pc, [(roman_token, BEATS_PER_BAR)]) + _left_hand_events(
        rng, minor_tonic_pc, roman_token
    )
```

to:

```python
    chords = [(roman_token, BEATS_PER_BAR)]
    return _right_hand_events(rng, minor_tonic_pc, chords) + _left_hand_events_for_bar(
        rng, minor_tonic_pc, chords
    )
```

- [ ] **Step 4: Run tests to verify they pass, then run the full suite**

Run: `uv run pytest tests/test_generator.py -v`
Expected: all PASS

Run: `uv run pytest`
Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/zunish/generator.py tests/test_generator.py
git commit -m "左手伴奏をduration_beats/start_offset_beat対応にし、_left_hand_events_for_barを追加"
```

---

### Task 8: Rename `generate_slot` to `generate_bar`, take a `chords` list, wire `Director`'s bar-grouping

**Files:**
- Modify: `src/zunish/generator.py` (rename + signature change of `generate_slot`)
- Modify: `src/zunish/director.py`
- Test: `tests/test_generator.py`
- Test: `tests/test_director.py`

**Interfaces:**
- Consumes: `_right_hand_events(rng, minor_tonic_pc, chords)` (Task 6), `_left_hand_events_for_bar(rng, minor_tonic_pc, chords)` (Task 7), `ChordProgression.beats` (Task 2).
- Produces: `zunish.generator.generate_bar(rng, minor_tonic_pc, chords: list[tuple[str, float]], next_minor_tonic_pc=None, next_roman_token=None) -> list[NoteEvent]` (replaces `generate_slot`). `Director.bars()` keeps its existing public shape (`Iterator[list[NoteEvent]]`); internally it now groups the chord stream into bars of one-or-two `(roman_token, beats)` chords before calling `generate_bar`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_generator.py`:

1. Update the import line `from zunish.generator import BEATS_PER_BAR, generate_slot` to `from zunish.generator import BEATS_PER_BAR, generate_bar`.
2. Rename and update every test that calls `generate_slot(...)` with a bare `roman_token=` kwarg to call `generate_bar(...)` with `chords=[(token, BEATS_PER_BAR)]` instead. Specifically:

```python
def test_left_hand_broken_pattern_skips_rests(monkeypatch):
    rest_pattern = AccompanimentPattern(
        id="test_rest",
        name="test",
        kind="broken",
        note_order=(0, None, 0),
        thirty_second_note_durations=(8, 16, 8),
    )
    monkeypatch.setattr(generator.accompaniment, "all", lambda: [rest_pattern])

    events = generate_bar(random.Random(1), minor_tonic_pc=9, chords=[("IV", BEATS_PER_BAR)])
    left_hand_events = [event for event in events if event.channel == generator.LEFT_HAND_CHANNEL]

    assert len(left_hand_events) == 2
    assert left_hand_events[0].start_beat == 0.0
    assert left_hand_events[1].start_beat == 3.0


def test_generate_bar_events_are_well_formed():
    rng = random.Random(42)
    for token in ROMAN_TOKENS:
        events = generate_bar(rng, minor_tonic_pc=9, chords=[(token, BEATS_PER_BAR)])
        assert events
        for event in events:
            assert event.start_beat >= 0
            assert event.duration_beat > 0
            assert event.start_beat + event.duration_beat <= BEATS_PER_BAR + 1e-9
            assert 0 <= event.pitch <= 127
            assert 1 <= event.velocity <= 127


def test_generate_bar_is_deterministic_given_seed():
    events_a = generate_bar(random.Random(7), minor_tonic_pc=9, chords=[("IV", BEATS_PER_BAR)])
    events_b = generate_bar(random.Random(7), minor_tonic_pc=9, chords=[("IV", BEATS_PER_BAR)])
    assert events_a == events_b


def test_generate_bar_right_hand_never_exceeds_two_simultaneous_notes():
    rng = random.Random(3)
    for token in ROMAN_TOKENS:
        for _ in range(30):
            events = [e for e in generate_bar(rng, minor_tonic_pc=9, chords=[(token, BEATS_PER_BAR)]) if e.channel == 0]
            boundaries = sorted({e.start_beat for e in events} | {e.start_beat + e.duration_beat for e in events})
            for point in boundaries[:-1]:
                sounding = [
                    e for e in events if e.start_beat <= point < e.start_beat + e.duration_beat - 1e-9
                ]
                assert len(sounding) <= 2
                if len(sounding) == 2:
                    assert all(e.duration_beat >= 0.5 for e in sounding)


def test_generate_bar_riff_motifs_are_unchanged():
    # 7sus4 arpeggio over Vsus4 (root G3=55): G,C,D,F,D,C,G,C - a fixed quotation,
    # exempt from the new melody constraints (it even contains the banned F).
    expected_pitches = [55, 60, 62, 65, 62, 60, 55, 60]
    for seed in range(200):
        events = [
            e for e in generate_bar(random.Random(seed), minor_tonic_pc=9, chords=[("Vsus4", BEATS_PER_BAR)])
            if e.channel == 0
        ]
        if [e.pitch for e in events] == expected_pitches:
            break
    else:
        raise AssertionError("expected the 7sus4 arpeggio to appear over Vsus4 at least once")


def test_generate_bar_uses_both_hand_channels():
    rng = random.Random(5)
    channels = set()
    for token in ROMAN_TOKENS:
        for event in generate_bar(rng, minor_tonic_pc=9, chords=[(token, BEATS_PER_BAR)]):
            channels.add(event.channel)
    assert channels == {0, 1}
```

3. Add two new integration tests for the multi-chord-bar case, anywhere after the renamed tests:

```python
def test_generate_bar_with_two_half_bar_chords_is_well_formed():
    rng = random.Random(7)
    for chords in ([("IV", 2.0), ("V", 2.0)], [("VIm", 2.0), ("II", 2.0)]):
        events = generate_bar(rng, minor_tonic_pc=9, chords=chords)
        assert events
        for event in events:
            assert event.start_beat >= 0
            assert event.duration_beat > 0
            assert event.start_beat + event.duration_beat <= BEATS_PER_BAR + 1e-9
            assert 0 <= event.pitch <= 127


def test_generate_bar_riff_ignores_a_trailing_half_bar_chord():
    expected_pitches = [55, 60, 62, 65, 62, 60, 55, 60]
    for seed in range(200):
        events = [
            e for e in generate_bar(random.Random(seed), minor_tonic_pc=9, chords=[("Vsus4", 2.0), ("IV", 2.0)])
            if e.channel == 0
        ]
        if [e.pitch for e in events] == expected_pitches:
            break
    else:
        raise AssertionError("expected the 7sus4 arpeggio to still appear at full length")
```

In `tests/test_director.py`, update the import line from `from zunish.generator import (BEATS_PER_BAR, LEFT_HAND_ANTICIPATION_LEAD_BEAT, LEFT_HAND_ANTICIPATION_SOUNDING_BEAT, LEFT_HAND_CHANNEL)` — no change needed to that specific line (it doesn't import `generate_slot`). Add a new import: `from zunish.content.progressions import progressions`.

Update `test_director_bars_pass_next_chord_lookahead_to_generate_slot` and `test_director_minor_tonic_pc_matches_the_bar_just_yielded` (both currently `monkeypatch.setattr(director_module, "generate_slot", ...)`):

```python
def test_director_bars_pass_next_chord_lookahead_to_generate_bar(monkeypatch):
    calls = []

    def fake_generate_bar(rng, minor_tonic_pc, chords, next_minor_tonic_pc=None, next_roman_token=None):
        calls.append((minor_tonic_pc, chords, next_minor_tonic_pc, next_roman_token))
        return []

    monkeypatch.setattr(director_module, "generate_bar", fake_generate_bar)

    director = Director(minor_tonic_pc=9, rng=random.Random(3))
    bars_iterator = director.bars()
    for _ in range(30):
        next(bars_iterator)

    assert len(calls) == 30
    for current_call, following_call in zip(calls, calls[1:]):
        _, _, next_tonic, next_token = current_call
        following_tonic, following_chords, _, _ = following_call
        assert next_tonic == following_tonic
        assert next_token == following_chords[0][0]


def test_director_minor_tonic_pc_matches_the_bar_just_yielded(monkeypatch):
    def fake_generate_bar(rng, minor_tonic_pc, chords, next_minor_tonic_pc=None, next_roman_token=None):
        return minor_tonic_pc

    monkeypatch.setattr(director_module, "generate_bar", fake_generate_bar)

    director = Director(minor_tonic_pc=9, rng=random.Random(3))
    bars_iterator = director.bars()
    for _ in range(100):
        yielded_tonic = next(bars_iterator)
        assert director.minor_tonic_pc == yielded_tonic
```

Add a new test for the bar-grouping itself:

```python
def test_bar_stream_groups_half_note_chords_into_one_bar():
    director = Director(minor_tonic_pc=9, rng=random.Random(1))
    director._current = progressions.get("iv_v_vim_2bar")
    bar_stream = director._bar_stream()

    tonic, chords = next(bar_stream)
    assert tonic == 9
    assert chords == [("IV", 2.0), ("V", 2.0)]

    tonic, chords = next(bar_stream)
    assert tonic == 9
    assert chords == [("VIm", 4.0)]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_generator.py tests/test_director.py -v`
Expected: FAIL — `ImportError: cannot import name 'generate_bar'` and `AttributeError: 'Director' object has no attribute '_bar_stream'`.

- [ ] **Step 3: Implement**

In `src/zunish/generator.py`, replace the final function (currently `generate_slot`, at the bottom of the file):

```python
def generate_slot(
    rng: random.Random,
    minor_tonic_pc: int,
    roman_token: str,
    next_minor_tonic_pc: int | None = None,
    next_roman_token: str | None = None,
) -> list[NoteEvent]:
    """Generate one bar's worth of NoteEvents (right hand + left hand) for a chord.

    ``next_minor_tonic_pc``/``next_roman_token`` optionally describe the
    following bar's chord. The left hand doesn't use them (it always stays
    within its own bar); they exist so ``Director`` can supply lookahead for
    a future right-hand melody feature.
    """
    chords = [(roman_token, BEATS_PER_BAR)]
    return _right_hand_events(rng, minor_tonic_pc, chords) + _left_hand_events_for_bar(
        rng, minor_tonic_pc, chords
    )
```

with:

```python
def generate_bar(
    rng: random.Random,
    minor_tonic_pc: int,
    chords: list[tuple[str, float]],
    next_minor_tonic_pc: int | None = None,
    next_roman_token: str | None = None,
) -> list[NoteEvent]:
    """Generate one bar's worth of NoteEvents (right hand + left hand).

    ``chords`` is a list of ``(roman_token, beats)`` pairs whose ``beats``
    sum to ``BEATS_PER_BAR`` — usually a single whole-bar chord, but it may
    instead hold two half-bar chords. The right hand treats the bar as one
    continuous phrase: its riff/rhythm choice is keyed off ``chords[0]``
    only, and its melody may freely cross into a second chord. The left
    hand plays each chord independently, time-scaled to its own share of
    the bar (see ``_left_hand_events_for_bar``).

    ``next_minor_tonic_pc``/``next_roman_token`` optionally describe the
    following bar's first chord. Neither hand uses them today; they exist
    so ``Director`` can supply lookahead for a future right-hand melody
    feature.
    """
    return _right_hand_events(rng, minor_tonic_pc, chords) + _left_hand_events_for_bar(
        rng, minor_tonic_pc, chords
    )
```

Also update the module-level docstring at the very top of `generator.py` from:

```python
"""Per-slot (one chord, one bar) note generation.

Combines the current chord/scale with the riff, rhythm, and accompaniment
registries to produce a flat list of :class:`NoteEvent` for one bar.
"""
```

to:

```python
"""Per-bar note generation.

Combines the current bar's chord(s)/scale with the riff, rhythm, and
accompaniment registries to produce a flat list of :class:`NoteEvent` for
one bar. A bar normally holds one whole-bar chord, but may instead hold two
half-bar chords (see :mod:`zunish.content.progressions`): the right hand
treats the bar as one continuous phrase that may cross the chord boundary,
while the left hand plays each chord independently within its own share of
the bar.
"""
```

In `src/zunish/director.py`, update the import line from:

```python
from zunish.generator import NoteEvent, generate_slot
```

to:

```python
from zunish.generator import BEATS_PER_BAR, NoteEvent, generate_bar
```

Replace `_chord_stream`:

```python
    def _chord_stream(self) -> Iterator[tuple[int, str]]:
        """Advance the progression/tonic walk, yielding (tonic, roman_token) forever."""
        while True:
            repeats = self._rng.randint(MIN_PROGRESSION_REPEATS, MAX_PROGRESSION_REPEATS)
            for _ in range(repeats):
                for roman_token in self._current.romans:
                    yield self._walk_tonic_pc, roman_token
            self._advance_progression()
```

with:

```python
    def _chord_stream(self) -> Iterator[tuple[int, str, float]]:
        """Advance the progression/tonic walk, yielding (tonic, roman_token, beats) forever."""
        while True:
            repeats = self._rng.randint(MIN_PROGRESSION_REPEATS, MAX_PROGRESSION_REPEATS)
            for _ in range(repeats):
                for roman_token, beats in zip(self._current.romans, self._current.beats):
                    yield self._walk_tonic_pc, roman_token, beats
            self._advance_progression()

    def _bar_stream(self) -> Iterator[tuple[int, list[tuple[str, float]]]]:
        """Group the chord stream into bars: (tonic, chords), where ``chords``
        is a list of (roman_token, beats) pairs summing to BEATS_PER_BAR.
        ``ChordProgression.validate()`` guarantees this grouping always
        completes within a single progression's own romans/beats, so it
        never needs to straddle a repeat or progression boundary."""
        chord_stream = self._chord_stream()
        bar_tonic: int | None = None
        bar_chords: list[tuple[str, float]] = []
        accumulated = 0.0
        for tonic, roman_token, beats in chord_stream:
            if bar_tonic is None:
                bar_tonic = tonic
            bar_chords.append((roman_token, beats))
            accumulated += beats
            if accumulated >= BEATS_PER_BAR:
                yield bar_tonic, bar_chords
                bar_tonic = None
                bar_chords = []
                accumulated = 0.0
```

Replace `bars()`:

```python
    def bars(self) -> Iterator[list[NoteEvent]]:
        """Yield one bar's NoteEvents at a time, forever.

        Looks one bar ahead so the left hand can anticipate the next chord;
        ``self.minor_tonic_pc`` is only updated in sync with the bar actually
        being yielded (not the lookahead bar), so callers polling it for key
        changes (e.g. the GUI) stay aligned with playback.
        """
        stream = self._chord_stream()
        current_tonic, current_token = next(stream)
        self.minor_tonic_pc = current_tonic
        for next_tonic, next_token in stream:
            yield generate_slot(self._rng, current_tonic, current_token, next_tonic, next_token)
            current_tonic, current_token = next_tonic, next_token
            self.minor_tonic_pc = current_tonic
```

with:

```python
    def bars(self) -> Iterator[list[NoteEvent]]:
        """Yield one bar's NoteEvents at a time, forever.

        Looks one bar ahead so the left hand can anticipate the next chord;
        ``self.minor_tonic_pc`` is only updated in sync with the bar actually
        being yielded (not the lookahead bar), so callers polling it for key
        changes (e.g. the GUI) stay aligned with playback.
        """
        bar_stream = self._bar_stream()
        current_tonic, current_chords = next(bar_stream)
        self.minor_tonic_pc = current_tonic
        for next_tonic, next_chords in bar_stream:
            next_roman_token = next_chords[0][0]
            yield generate_bar(self._rng, current_tonic, current_chords, next_tonic, next_roman_token)
            current_tonic, current_chords = next_tonic, next_chords
            self.minor_tonic_pc = current_tonic
```

- [ ] **Step 4: Run tests to verify they pass, then run the full suite**

Run: `uv run pytest tests/test_generator.py tests/test_director.py -v`
Expected: all PASS

Run: `uv run pytest`
Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/zunish/generator.py src/zunish/director.py tests/test_generator.py tests/test_director.py
git commit -m "generate_slotをgenerate_barに改名しchordsリストを受け取るようにし、Directorの小節グループ化を実装"
```

---

### Task 9: Update `RULES.md` and `README.md`

**Files:**
- Modify: `RULES.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: nothing (documentation only).
- Produces: nothing (documentation only).

- [ ] **Step 1: Update `RULES.md`**

In the "コード進行（`content/progressions.py`）" section, after the existing progression table, add:

```markdown
各コードには小節内での音価（`beats`）があり、デフォルトは全音符（1コード=1小節）。3コードの進行5つ（`iv_v_vim`, `vim_v_iv`, `vim_v_ii`, `vim_iiim_ii`, `iv_v_vi_picardy`）には、1・2番目のコードを2分音符、3番目を全音符とする「2コード/小節」の姉妹進行（`iv_v_vim_2bar` など）が追加で登録されており、元の進行の `follows` からランダムに遷移してくる。2分音符のコードは常に同じ進行内の隣接コードとペアになり、1小節分を完結させる（`validate()` がこれを保証する）。
```

In the "進行の連結・転調ロジック（`director.py`）" 段, add after the existing bullet points:

```markdown
- コード列は拍数（`beats`）が`BEATS_PER_BAR`（4拍）に達するたびに1小節としてグループ化される。1小節に収まるコードは1つ（全音符）または2つ（2分音符×2）。
```

In the "右手メロディ生成（スケールウォーク時、`generator.py`）" section, add a new bullet after the existing ones:

```markdown
- **1小節に2コードある場合**: リズムパターン・スケールの抽選は小節全体で1回のみ（コードの境目を考慮しない）。各拍のコードトーン・装飾音プールは、その拍がどちらのコード区間に属するかで切り替わる。コードが変わった直後は、直前のピッチに最も近い新コードの音へ滑らかに乗り継いでウォークを続けるため、メロディがコードの境目を自然に跨ぐ。
```

Also add a note to the "著名リフ・アルペジオ" section, right after the existing paragraph:

```markdown
1小節に2コードある場合、リフの発動判定・ルート/オクターブは小節内の**先頭コード**のみを見る。リフが発動したときは、2つ目のコードの有無にかかわらず、これまでと同じ固定の長さ（8分音符×8＝1小節分）でそのまま鳴らす。
```

In the "左手伴奏パターン（`content/accompaniment.py` / `generator.py`）" section, replace the sentence "左手のノートは常に現在の小節・現在の和音の範囲内で完結し、次の小節の和音を先取りする（シンコペーションする）ことはありません（そちらは将来的に右手側で対応予定）。" with:

```markdown
左手のノートは常に現在のコード区間の範囲内で完結する。1小節に2コードある場合は、各コード区間ごとに伴奏パターン（block/broken）とボイシングを個別に抽選し、その区間の拍数（2拍または4拍）に比例縮小して演奏する（例: 通常8分音符のパターンは2拍区間では16分音符相当に圧縮される）。次の小節の和音を先取りする（シンコペーションする）ことはない（そちらは将来的に右手側で対応予定）。
```

- [ ] **Step 2: Update `README.md`**

In the 特徴 bullet list, change the line:

```markdown
- 単一の連続進行ストリームを無限に生成（セクション分けなし）。進行は2〜4回ループごとに接続グラフの重みに従って次の進行へ、一定確率で短三度（±3半音）転調。
```

to:

```markdown
- 単一の連続進行ストリームを無限に生成（セクション分けなし）。進行は2〜4回ループごとに接続グラフの重みに従って次の進行へ、一定確率で短三度（±3半音）転調。一部の進行には、1小節に2つのコード（2分音符×2）が入る変化形も用意されている（詳細は[RULES.md](RULES.md)を参照）。
```

- [ ] **Step 3: Run the full test suite one more time (docs shouldn't affect it, but confirm nothing regressed)**

Run: `uv run pytest`
Expected: all tests PASS

- [ ] **Step 4: Commit**

```bash
git add RULES.md README.md
git commit -m "1小節複数コード対応をRULES.md/README.mdに反映"
```
