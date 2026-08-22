# 左手リズムパターン多様化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the left-hand accompaniment generator (`AccompanimentPattern` in `src/zunish/content/accompaniment.py`) enough rhythmic vocabulary (32nd-note resolution) to add two new bar-aligned patterns matching the original work's common left-hand rhythms: a dotted-2.5-beat→sixteenth-walk→eighth figure, and a tresillo grouping ornamented with sixteenth/thirty-second notes.

**Architecture:** Left-hand-only change, and fully bar-local. `AccompanimentPattern` moves from 8-per-bar (eighth-note) duration units to 32-per-bar (32nd-note) units and gains `None` (rest) support in `note_order`. No chord anticipation, no cross-bar lookahead, no `Director`/`generate_slot` signature changes — every left-hand note stays inside its own bar and uses only that bar's own chord, exactly as today. (Syncopation/anticipation that reaches into a neighboring bar's harmony is being handled on the right-hand/melody side instead, and is explicitly out of scope here.) The right-hand fallback rhythm registry (`content/rhythms.py`) is untouched.

**Tech Stack:** Python 3, pytest, dataclasses (no new dependencies).

**Spec:** `docs/superpowers/specs/2026-08-13-left-hand-rhythm-variety-design.md`

## Global Constraints

- Left-hand accompaniment duration unit is 32nd notes, 32 units per bar (replaces the old 8-per-bar eighth-note unit). Right-hand `content/rhythms.py` stays at 8-per-bar eighth-note units — do not touch it.
- Every left-hand note must start at or after beat 0 and end at or before `BEATS_PER_BAR` (4.0) of its own bar, using only that bar's own chord voicing. No cross-bar anticipation, no negative `start_beat`, no changes to `Director` or `generate_slot`'s signature.

---

### Task 1: 32nd-note resolution + rest support on `AccompanimentPattern`

**Files:**
- Modify: `src/zunish/content/accompaniment.py` (whole file, 59 lines)
- Test: `tests/test_content_registries.py:44-47`

**Interfaces:**
- Consumes: nothing new (pure data-model change).
- Produces: `AccompanimentPattern` with fields `note_order: tuple[int | None, ...]` (widened to allow `None` = rest) and `thirty_second_note_durations: tuple[int, ...]` (replaces `eighth_note_durations`, 32 units == one bar). `_register(...)`'s keyword arg is renamed from `eighth_note_durations` to `thirty_second_note_durations`. Task 2 (generator.py) reads these two fields by these exact names.

- [ ] **Step 1: Write the failing tests**

Replace the accompaniment-related test in `tests/test_content_registries.py` (currently lines 44-47) and add one more, so the file's accompaniment section reads:

```python
def test_accompaniment_broken_patterns_have_matching_lengths():
    for pattern in accompaniment.all():
        if pattern.kind == "broken":
            assert len(pattern.note_order) == len(pattern.thirty_second_note_durations)


def test_accompaniment_broken_patterns_fill_exactly_one_bar():
    for pattern in accompaniment.all():
        if pattern.kind == "broken":
            assert sum(pattern.thirty_second_note_durations) == 32
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_content_registries.py -v`
Expected: `test_accompaniment_broken_patterns_have_matching_lengths` fails with `AttributeError: 'AccompanimentPattern' object has no attribute 'thirty_second_note_durations'` (the field doesn't exist yet — it's still named `eighth_note_durations`). `test_accompaniment_broken_patterns_fill_exactly_one_bar` fails the same way.

- [ ] **Step 3: Rewrite `src/zunish/content/accompaniment.py`**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_content_registries.py -v`
Expected: all 8 tests pass (the 6 pre-existing progression/scale/riff/rhythm tests, unaffected, plus the 2 accompaniment tests above — note `test_rhythm_durations_fill_exactly_one_bar` for the *right-hand* `rhythms` registry is untouched and still passes at its own 8-per-bar unit).

- [ ] **Step 5: Commit**

```bash
git add src/zunish/content/accompaniment.py tests/test_content_registries.py
git commit -m "feat: move left-hand accompaniment durations to 32nd-note resolution"
```

---

### Task 2: Rest support in the generator

**Files:**
- Modify: `src/zunish/generator.py:122-159` (`_left_hand_events`)
- Test: `tests/test_generator.py`

**Interfaces:**
- Consumes: `AccompanimentPattern.note_order` (`tuple[int | None, ...]`) and `.thirty_second_note_durations` from Task 1.
- Produces: no signature changes — `generate_slot(rng, minor_tonic_pc, roman_token) -> list[NoteEvent]` stays exactly as it is today. `_left_hand_events`'s internal duration-unit math changes (32nds instead of eighths) and it now skips emitting a `NoteEvent` when `note_order` holds `None`, while still advancing time.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_generator.py`:

```python
from zunish.content.accompaniment import AccompanimentPattern


def test_left_hand_broken_pattern_skips_rests(monkeypatch):
    rest_pattern = AccompanimentPattern(
        id="test_rest",
        name="test",
        kind="broken",
        note_order=(0, None, 0),
        thirty_second_note_durations=(8, 16, 8),
    )
    monkeypatch.setattr("zunish.generator.accompaniment.all", lambda: [rest_pattern])

    events = generate_slot(random.Random(1), minor_tonic_pc=9, roman_token="IV")
    left_hand_events = [event for event in events if event.channel == 1]

    assert len(left_hand_events) == 2
    assert left_hand_events[0].start_beat == 0.0
    assert left_hand_events[1].start_beat == 3.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_generator.py -v -k skips_rests`
Expected: FAIL. Today's `_left_hand_events` reads `duration_eighths` in eighth-note units (`beat_per_eighth = 0.5`) and does `for tone_index, duration_eighths in zip(pattern.note_order, pattern.eighth_note_durations)`, always creating a `NoteEvent` for every `tone_index` — it will crash with `voicing[tone_index % len(voicing)]` raising `TypeError: unsupported operand type(s) for %: 'NoneType' and 'int'` because `tone_index` is `None`, and it also still references the now-renamed `pattern.eighth_note_durations` attribute (`AttributeError`) once Task 1 lands. Either failure confirms the code needs updating.

- [ ] **Step 3: Update `_left_hand_events` in `src/zunish/generator.py`**

Replace the existing broken-pattern branch (the part of `_left_hand_events` after the `if pattern.kind == "block": ... return events` block, i.e. current lines 143-159) with:

```python
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

The full function should now read:

```python
def _left_hand_events(
    rng: random.Random, minor_tonic_pc: int, roman_token: str
) -> list[NoteEvent]:
    pattern: AccompanimentPattern = weighted_choice(rng, [(p, p.weight) for p in accompaniment.all()])
    voicing = theory.chord_tones_midi(minor_tonic_pc, roman_token, LEFT_HAND_OCTAVE)

    events: list[NoteEvent] = []
    if pattern.kind == "block":
        velocity = _jittered_velocity(rng, LEFT_HAND_BASE_VELOCITY)
        for tone_index in pattern.note_order:
            events.append(
                NoteEvent(
                    pitch=voicing[tone_index % len(voicing)],
                    start_beat=0.0,
                    duration_beat=BEATS_PER_BAR,
                    velocity=velocity,
                    channel=LEFT_HAND_CHANNEL,
                )
            )
        return events

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

No other function in `generator.py` changes — `generate_slot` and `_right_hand_events` stay exactly as they are.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_generator.py tests/test_content_registries.py -v`
Expected: all tests pass, including the pre-existing `test_generate_slot_events_are_well_formed`, `test_generate_slot_is_deterministic_given_seed`, and `test_generate_slot_uses_both_hand_channels` (unchanged).

- [ ] **Step 5: Commit**

```bash
git add src/zunish/generator.py tests/test_generator.py
git commit -m "feat: support rests in left-hand broken patterns"
```

---

### Task 3: Add the two new left-hand patterns

**Files:**
- Modify: `src/zunish/content/accompaniment.py` (append 2 `_register` calls)
- Test: `tests/test_content_registries.py`

**Interfaces:**
- Consumes: `_register(...)` from Task 1 (`note_order`, `thirty_second_note_durations` keyword args).
- Produces: two new registry entries with ids `dotted_walk` and `tresillo_ornamented`, available to `_left_hand_events` via `accompaniment.all()`. No new production symbols for later tasks to consume.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_content_registries.py`:

```python
def test_new_left_hand_patterns_are_registered():
    dotted_walk = accompaniment.get("dotted_walk")
    assert sum(dotted_walk.thirty_second_note_durations) == 32
    assert len(dotted_walk.note_order) == len(dotted_walk.thirty_second_note_durations)

    tresillo_ornamented = accompaniment.get("tresillo_ornamented")
    assert sum(tresillo_ornamented.thirty_second_note_durations) == 32
    assert len(tresillo_ornamented.note_order) == len(tresillo_ornamented.thirty_second_note_durations)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_content_registries.py -v -k new_left_hand_patterns`
Expected: `KeyError` (from `Registry.get`) since `dotted_walk` isn't registered yet.

- [ ] **Step 3: Append to `src/zunish/content/accompaniment.py`**

Add after the existing two `_register(...)` calls:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/ -v`
Expected: all tests pass, including Task 1's generic `test_accompaniment_broken_patterns_have_matching_lengths` / `test_accompaniment_broken_patterns_fill_exactly_one_bar`, which now also cover these two new entries.

- [ ] **Step 5: Commit**

```bash
git add src/zunish/content/accompaniment.py tests/test_content_registries.py
git commit -m "feat: add dotted-walk and ornamented-tresillo left-hand patterns"
```

---

## Final Check

- [ ] Run the full suite once more: `pytest tests/ -v` — all green.
- [ ] Manually sanity-check by running the CLI for ~30 seconds (`python -m zunish.cli` or however this project is normally launched — check `src/zunish/__main__.py`/README for the exact invocation) and listening for the two new left-hand patterns turning up in the mix alongside the original whole-note/straight-eighths ones.
