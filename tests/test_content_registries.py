import pytest

from zunish import theory
from zunish.content.accompaniment import accompaniment
from zunish.content.progressions import (
    ALLOWED_CHORD_BEATS,
    ChordProgression,
    _validate_beats,
    progressions,
)
from zunish.content.rhythms import rhythms
from zunish.content.riffs import riffs
from zunish.content.scales import scales
from zunish.content.voicings import voicings


def test_all_progression_romans_parse():
    for progression in progressions.all():
        for token in progression.romans:
            theory.parse_roman_numeral(token)  # should not raise


def test_progression_follows_reference_known_ids():
    known_ids = set(progressions.ids())
    for progression in progressions.all():
        for target_id in progression.follows:
            assert target_id in known_ids


def test_avalanche_half_connects_strongly_to_iv_v_vim():
    half = progressions.get("avalanche_half")
    assert half.follows["iv_v_vim"] > 0


def test_avalanche_half_only_resolves_to_iv_v_endings():
    half = progressions.get("avalanche_half")
    assert set(half.follows) == {"iv_v_vim", "iv_v_vi_picardy", "iv_v_vsus4_vi"}
    assert all(weight > 0 for weight in half.follows.values())


def test_vim_v_iv_v_romans_and_reachable_from_iv_v_vim():
    v_turn = progressions.get("vim_v_iv_v")
    assert v_turn.romans == ("VIm", "V", "IV", "V")
    assert progressions.get("iv_v_vim").follows["vim_v_iv_v"] > 0
    assert progressions.get("iv_v_vim_2bar").follows["vim_v_iv_v"] > 0


def test_oudou_tension_nuki_and_jado_shinkou_romans():
    oudou = progressions.get("oudou_tension_nuki")
    assert oudou.romans == ("IV", "V", "III", "VIm")

    jado = progressions.get("jado_shinkou")
    assert jado.romans == ("IV", "V", "V#dim", "VIm")
    assert jado.follows["oudou_tension_nuki"] > 0
    assert oudou.follows["jado_shinkou"] > 0


def test_scales_have_no_duplicate_pitch_classes():
    for scale in scales.all():
        pitch_classes = theory.scale_pitch_classes(0, scale.degree_offsets)
        assert len(set(pitch_classes)) == len(scale.degree_offsets)


def test_riff_compatible_qualities_are_known():
    known_qualities = {"", "m", "sus4"}
    for riff in riffs.all():
        assert set(riff.compatible_qualities) <= known_qualities


def test_rhythm_durations_fill_exactly_one_bar():
    for rhythm in rhythms.all():
        assert sum(rhythm.sixteenth_note_durations) == 16


def test_accompaniment_broken_patterns_have_matching_lengths():
    for pattern in accompaniment.all():
        if pattern.kind == "broken":
            assert len(pattern.note_order) == len(pattern.thirty_second_note_durations)


def test_accompaniment_broken_patterns_fill_exactly_one_bar():
    for pattern in accompaniment.all():
        if pattern.kind == "broken":
            assert sum(pattern.thirty_second_note_durations) == 32


def test_voicing_variants_cover_root_and_both_inversions():
    inversions = {v.inversion for v in voicings.all() if v.kind == "invert"}
    assert inversions == {0, 1, 2}


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
    bad = ChordProgression(id="x", name="x", romans=("I",), beats=(2.0,))
    with pytest.raises(ValueError):
        _validate_beats(bad)


def test_validate_beats_accepts_a_half_and_whole_bar_mix():
    ok = ChordProgression(id="x", name="x", romans=("I", "II", "III"), beats=(2.0, 2.0, 4.0))
    _validate_beats(ok)  # must not raise


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
