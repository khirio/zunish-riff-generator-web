import random

from zunish import director as director_module
from zunish.director import Director, MODULATION_SEMITONES
from zunish.generator import (
    BEATS_PER_BAR,
    LEFT_HAND_ANTICIPATION_LEAD_BEAT,
    LEFT_HAND_ANTICIPATION_SOUNDING_BEAT,
    LEFT_HAND_CHANNEL,
    RIGHT_HAND_ANTICIPATION_LEAD_BEAT,
    RIGHT_HAND_ANTICIPATION_SOUNDING_BEAT,
)
from zunish.content.progressions import progressions

# Either hand may push its last eighth note into a barline-crossing quarter
# note (an anticipation of the next bar/chord segment's opening tone),
# overshooting the bar by up to that note's sounding length minus its lead-in.
LEFT_HAND_MAX_OVERSHOOT_BEAT = LEFT_HAND_ANTICIPATION_SOUNDING_BEAT - LEFT_HAND_ANTICIPATION_LEAD_BEAT
RIGHT_HAND_MAX_OVERSHOOT_BEAT = RIGHT_HAND_ANTICIPATION_SOUNDING_BEAT - RIGHT_HAND_ANTICIPATION_LEAD_BEAT


def test_director_produces_well_formed_bars():
    director = Director(minor_tonic_pc=9, rng=random.Random(3))
    bars_iterator = director.bars()
    for _ in range(50):
        bar_events = next(bars_iterator)
        assert bar_events
        for event in bar_events:
            assert 0 <= event.pitch <= 127
            overshoot = LEFT_HAND_MAX_OVERSHOOT_BEAT if event.channel == LEFT_HAND_CHANNEL else RIGHT_HAND_MAX_OVERSHOOT_BEAT
            max_end_beat = BEATS_PER_BAR + overshoot
            assert event.start_beat + event.duration_beat <= max_end_beat + 1e-9


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


def test_bars_over_a_forced_two_chord_progression_are_well_formed():
    director = Director(minor_tonic_pc=9, rng=random.Random(1))
    director._current = progressions.get("vim_v_ii_2bar")
    bars_iterator = director.bars()

    # vim_v_ii_2bar's romans/beats start with VIm(2 beats), V(2 beats), so
    # the very first bar out of bars() is deterministically the split bar
    # (VIm 0-2, V 2-4), regardless of how many times the progression repeats.
    # Each chord segment's left-hand events must stay confined to its own
    # half rather than straddling the mid-bar chord boundary at beat 2.0 -
    # this exercises generate_bar's per-segment time-scaling through the
    # public bars() API, not just _bar_stream's grouping or generate_bar
    # called directly.
    first_bar_events = next(bars_iterator)
    left_hand_events = [event for event in first_bar_events if event.channel == LEFT_HAND_CHANNEL]
    assert left_hand_events
    for event in left_hand_events:
        end_beat = event.start_beat + event.duration_beat
        if event.start_beat < 2.0 - 1e-9:
            assert end_beat <= 2.0 + 1e-9
        else:
            assert event.start_beat >= 2.0 - 1e-9

    for _ in range(60):
        bar_events = next(bars_iterator)
        assert bar_events
        for event in bar_events:
            assert 0 <= event.pitch <= 127
            overshoot = LEFT_HAND_MAX_OVERSHOOT_BEAT if event.channel == LEFT_HAND_CHANNEL else RIGHT_HAND_MAX_OVERSHOOT_BEAT
            max_end_beat = BEATS_PER_BAR + overshoot
            assert event.start_beat + event.duration_beat <= max_end_beat + 1e-9


def test_director_modulates_only_by_the_configured_step():
    director = Director(minor_tonic_pc=0, rng=random.Random(11))
    bars_iterator = director.bars()
    seen_tonics = {director.minor_tonic_pc}
    for _ in range(200):
        next(bars_iterator)
        seen_tonics.add(director.minor_tonic_pc)
    for tonic in seen_tonics:
        assert (tonic - 0) % MODULATION_SEMITONES == 0


def test_director_never_modulates_when_disabled():
    director = Director(minor_tonic_pc=0, rng=random.Random(11), enable_modulation=False)
    bars_iterator = director.bars()
    for _ in range(200):
        next(bars_iterator)
        assert director.minor_tonic_pc == 0
