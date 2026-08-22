import random

from zunish import generator
from zunish.content.accompaniment import AccompanimentPattern, accompaniment
from zunish.content.rhythms import RhythmPattern
from zunish.content.scales import scales
from zunish.generator import BEATS_PER_BAR, generate_bar

ROMAN_TOKENS = ("IV", "V", "VIm", "Vsus4", "III", "II", "IIm", "I", "VI")

MINOR_TONIC_PC = 9  # A minor

FOUR_QUARTER_NOTES = RhythmPattern(
    id="test_four_quarters", name="test", sixteenth_note_durations=(4, 4, 4, 4)
)


def test_apply_left_hand_anticipation_swaps_pitch_of_an_already_eighth_note_slot():
    # broken_root_fifth_third_fifth's last eighth note: root(0) at beat 3.5-4.0.
    # The pickup rings for a full quarter note, so it ends at 4.5 - crossing the bar line.
    old_voicing = [57, 61, 64]  # A2, C#3, E3 (A major, for shape)
    next_voicing = [55, 59, 62]  # G2, B2, D3
    events = [generator.NoteEvent(pitch=old_voicing[0], start_beat=3.5, duration_beat=0.5, velocity=78, channel=1)]

    result = generator._apply_left_hand_anticipation(events, old_voicing, next_voicing)

    assert len(result) == 1
    assert result[0].pitch == next_voicing[0]
    assert result[0].start_beat == 3.5
    assert result[0].duration_beat == 1.0


def test_apply_left_hand_anticipation_truncates_a_sustained_block_chord():
    old_voicing = [57, 61, 64]
    next_voicing = [55, 59, 62]
    events = [
        generator.NoteEvent(pitch=pitch, start_beat=0.0, duration_beat=4.0, velocity=78, channel=1)
        for pitch in old_voicing
    ]

    result = generator._apply_left_hand_anticipation(events, old_voicing, next_voicing)

    assert len(result) == 6  # each of the 3 tones: a truncated sustain + a pickup note
    truncated = sorted((e for e in result if e.start_beat == 0.0), key=lambda e: e.pitch)
    pickups = sorted((e for e in result if e.start_beat == 3.5), key=lambda e: e.pitch)
    assert {e.pitch for e in truncated} == set(old_voicing)
    assert all(e.duration_beat == 3.5 for e in truncated)
    assert {e.pitch for e in pickups} == set(next_voicing)
    # A quarter note straddling the bar line: ends at 4.5, half a beat into the next bar.
    assert all(e.duration_beat == 1.0 for e in pickups)


def test_apply_left_hand_anticipation_leaves_earlier_notes_untouched():
    old_voicing = [57, 61, 64]
    next_voicing = [55, 59, 62]
    early_note = generator.NoteEvent(pitch=old_voicing[1], start_beat=0.0, duration_beat=1.0, velocity=78, channel=1)

    result = generator._apply_left_hand_anticipation([early_note], old_voicing, next_voicing)

    assert result == [early_note]


def test_apply_right_hand_anticipation_swaps_pitch_of_an_already_eighth_note_slot():
    events = [generator.NoteEvent(pitch=60, start_beat=3.5, duration_beat=0.5, velocity=100, channel=0)]
    next_chord_tone_pool = [58, 65, 70]  # nearest to 60 is 58

    result = generator._apply_right_hand_anticipation(events, next_chord_tone_pool)

    assert len(result) == 1
    assert result[0].pitch == 58
    assert result[0].start_beat == 3.5
    assert result[0].duration_beat == 1.0
    assert result[0].channel == 0
    assert result[0].velocity == 100


def test_apply_right_hand_anticipation_truncates_a_note_that_starts_before_the_pickup():
    events = [generator.NoteEvent(pitch=60, start_beat=3.0, duration_beat=1.0, velocity=100, channel=0)]
    next_chord_tone_pool = [64]

    result = generator._apply_right_hand_anticipation(events, next_chord_tone_pool)

    assert len(result) == 2
    truncated = next(e for e in result if e.start_beat == 3.0)
    pickup = next(e for e in result if e.start_beat == 3.5)
    assert truncated.duration_beat == 0.5
    assert truncated.pitch == 60
    assert pickup.pitch == 64
    assert pickup.duration_beat == 1.0


def test_apply_right_hand_anticipation_leaves_earlier_notes_untouched():
    early_note = generator.NoteEvent(pitch=60, start_beat=0.0, duration_beat=1.0, velocity=100, channel=0)

    result = generator._apply_right_hand_anticipation([early_note], [64])

    assert result == [early_note]


def test_melody_chord_tone_pcs_excludes_banned_sixth_for_iv_root():
    # IV = F,A,C ; F is the banned b6 relative to A minor and must be dropped.
    pcs = generator._melody_chord_tone_pcs(MINOR_TONIC_PC, "IV")
    assert set(pcs) == {9, 0}  # A, C only


def test_melody_chord_tone_pcs_excludes_banned_sixth_for_iim_third():
    # IIm = D,F,A ; F is the banned b6 and is this chord's third.
    pcs = generator._melody_chord_tone_pcs(MINOR_TONIC_PC, "IIm")
    assert set(pcs) == {2, 9}  # D, A only


def test_melody_chord_tone_pcs_keeps_all_three_when_no_banned_tone():
    # V = G,B,D ; none of these is the banned b6.
    pcs = generator._melody_chord_tone_pcs(MINOR_TONIC_PC, "V")
    assert set(pcs) == {7, 11, 2}


def test_melody_decoration_pcs_never_includes_banned_sixth():
    dorian = scales.get("dorian_6")
    chord_tone_pcs = generator._melody_chord_tone_pcs(MINOR_TONIC_PC, "V")
    decoration = generator._melody_decoration_pcs(MINOR_TONIC_PC, dorian, chord_tone_pcs)
    banned_pc = (MINOR_TONIC_PC + generator.BANNED_DEGREE_OFFSET) % 12
    assert banned_pc not in decoration


def test_melody_decoration_pcs_excludes_dorian_sixth_when_chord_lacks_it():
    # IV's chord tones don't include F# (the dorian 6th), so it must not
    # leak into the decoration pool either.
    dorian = scales.get("dorian_6")
    chord_tone_pcs = generator._melody_chord_tone_pcs(MINOR_TONIC_PC, "IV")
    decoration = generator._melody_decoration_pcs(MINOR_TONIC_PC, dorian, chord_tone_pcs)
    dorian_pc = (MINOR_TONIC_PC + generator.DORIAN_SIXTH_OFFSET) % 12
    assert dorian_pc not in decoration


def test_melody_decoration_pcs_excludes_dorian_sixth_even_when_chord_has_it():
    # II's third IS F# (the dorian 6th); it reaches the melody via the
    # chord-tone pool, so decoration must not duplicate it.
    dorian = scales.get("dorian_6")
    chord_tone_pcs = generator._melody_chord_tone_pcs(MINOR_TONIC_PC, "II")
    dorian_pc = (MINOR_TONIC_PC + generator.DORIAN_SIXTH_OFFSET) % 12
    assert dorian_pc in chord_tone_pcs
    decoration = generator._melody_decoration_pcs(MINOR_TONIC_PC, dorian, chord_tone_pcs)
    assert dorian_pc not in decoration


def test_pick_neighbor_tone_returns_none_when_pool_is_empty():
    rng = random.Random(1)
    assert generator._pick_neighbor_tone(rng, 64, []) is None


def test_pick_neighbor_tone_returns_the_only_candidate_when_one_side_is_empty():
    rng = random.Random(1)
    assert generator._pick_neighbor_tone(rng, 64, [66]) == 66
    assert generator._pick_neighbor_tone(rng, 64, [62]) == 62


def test_pick_neighbor_tone_picks_nearest_above_or_below():
    pool = [60, 62, 66, 69]  # within a whole step of 64: 62 (below), 66 (above)
    seen = set()
    for seed in range(20):
        seen.add(generator._pick_neighbor_tone(random.Random(seed), 64, pool))
    assert seen == {62, 66}


def test_pick_neighbor_tone_ignores_candidates_beyond_a_whole_step():
    # A real appoggiatura is a scale step away; a minor-third-or-wider gap
    # (e.g. across a pentatonic scale's missing degree) shouldn't be used.
    rng = random.Random(1)
    assert generator._pick_neighbor_tone(rng, 64, [60, 70]) is None


def test_pick_neighbor_tone_excludes_leading_tone_unless_resolving_to_tonic():
    # G#4 (68) sits a semitone below both A4/the tonic (69) and G4/the b7 (67).
    # It must only ever decorate the tonic, never the b7 a semitone below it.
    leading_tone_pitch = 68
    rng = random.Random(1)
    assert generator._pick_neighbor_tone(rng, 67, [leading_tone_pitch], MINOR_TONIC_PC) is None
    assert generator._pick_neighbor_tone(rng, 69, [leading_tone_pitch], MINOR_TONIC_PC) == leading_tone_pitch


def test_pick_neighbor_tone_leading_tone_filter_ignores_unrelated_pitch_classes():
    # The leading-tone filter shouldn't affect ordinary decoration candidates.
    rng = random.Random(1)
    assert generator._pick_neighbor_tone(rng, 64, [66], MINOR_TONIC_PC) == 66


def test_pick_harmony_tone_avoids_same_pitch_class():
    chord_tone_pool = generator._midi_pool([0, 4, 7])  # C major triad tones across the range
    for seed in range(20):
        pitch = 64  # E4, pc 4
        harmony = generator._pick_harmony_tone(random.Random(seed), pitch, chord_tone_pool)
        assert harmony is not None
        assert harmony % 12 != pitch % 12
        assert harmony in chord_tone_pool


def test_pick_harmony_tone_returns_none_when_no_other_pitch_class_available():
    rng = random.Random(1)
    assert generator._pick_harmony_tone(rng, 64, [64, 76]) is None


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


def test_melody_note_events_leading_tone_only_resolves_to_tonic_when_not_a_chord_tone():
    # When harmonic_minor's leading tone (offset 11, G# in A minor) reaches
    # the melody as a decoration (i.e. the current chord doesn't already
    # contain it, e.g. III's third or V#dim's root), it must always resolve
    # stepwise up to the tonic (offset 0) - never to some other neighbor
    # like the b7 a semitone below it.
    tonic_pc = MINOR_TONIC_PC % 12
    leading_tone_pc = (MINOR_TONIC_PC + generator.LEADING_TONE_OFFSET) % 12
    for token in ROMAN_TOKENS:
        chord_tone_pcs = set(generator._melody_chord_tone_pcs(MINOR_TONIC_PC, token))
        if leading_tone_pc in chord_tone_pcs:
            continue
        for seed in range(200):
            events = generator._melody_note_events(
                random.Random(seed), MINOR_TONIC_PC, [(token, BEATS_PER_BAR)], FOUR_QUARTER_NOTES
            )
            for first, second in zip(events, events[1:]):
                if first.pitch % 12 != leading_tone_pc:
                    continue
                if first.start_beat + first.duration_beat != second.start_beat:
                    continue
                assert second.pitch % 12 == tonic_pc


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
        # Find a pair of back-to-back events that split one quarter-note onset in half.
        for first, second in zip(events, events[1:]):
            if first.pitch % 12 in chord_tone_pcs or second.pitch % 12 not in chord_tone_pcs:
                continue
            if first.start_beat + first.duration_beat != second.start_beat:
                continue
            found_a_split = True
            assert first.duration_beat == second.duration_beat
            assert abs(first.pitch - second.pitch) <= 2  # adjacent scale step, resolves stepwise
    assert found_a_split


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


def test_melody_decoration_pcs_excludes_chord_tones():
    dorian = scales.get("dorian_6")
    chord_tone_pcs = generator._melody_chord_tone_pcs(MINOR_TONIC_PC, "V")
    decoration = generator._melody_decoration_pcs(MINOR_TONIC_PC, dorian, chord_tone_pcs)
    assert not (set(decoration) & set(chord_tone_pcs))


def test_left_hand_events_reads_thirty_second_note_durations():
    # broken_root_fifth_third_fifth: 8 equal thirty-second-note groups of 4
    # units each (an eighth note), root-5th-3rd-5th-root-5th-3rd-5th.
    events = generator._left_hand_events(random.Random(1), MINOR_TONIC_PC, "IV")
    left_hand = [e for e in events if e.channel == generator.LEFT_HAND_CHANNEL]
    assert left_hand
    assert all(abs(e.duration_beat - 0.5) < 1e-9 or e.duration_beat == BEATS_PER_BAR for e in left_hand)


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


def test_left_hand_block_chord_bass_varies_across_voicing_variants(monkeypatch):
    monkeypatch.setattr(generator.accompaniment, "all", lambda: [accompaniment.get("block_chord")])
    iv_pcs = set(generator.theory.chord_pitch_classes(MINOR_TONIC_PC, "IV"))
    seen_bass_pcs = set()
    for seed in range(300):
        events = generator._left_hand_events(random.Random(seed), MINOR_TONIC_PC, "IV")
        seen_bass_pcs.add(min(e.pitch for e in events) % 12)
    assert seen_bass_pcs == iv_pcs  # root, 3rd, and 5th each appear in the bass


def test_left_hand_block_chord_open_voicing_spreads_the_third(monkeypatch):
    monkeypatch.setattr(generator.accompaniment, "all", lambda: [accompaniment.get("block_chord")])
    monkeypatch.setattr(
        generator.voicings, "all", lambda: [generator.voicings.get("open_middle_octave_up")]
    )
    events = generator._left_hand_events(random.Random(1), MINOR_TONIC_PC, "IV")
    pitches = sorted(e.pitch for e in events)
    root_position = generator.theory.chord_tones_midi(MINOR_TONIC_PC, "IV", generator.LEFT_HAND_OCTAVE)
    assert pitches == sorted([root_position[0], root_position[2], root_position[1] + 12])


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


def test_right_hand_events_anticipates_next_bars_chord_when_triggered():
    # IV={A,C} (b6 excluded), V={G,B,D}: no overlapping pitch classes, so a
    # pickup landing on one of V's classes proves the lookahead fired.
    iv_pcs = set(generator._melody_chord_tone_pcs(MINOR_TONIC_PC, "IV"))
    v_pcs = set(generator._melody_chord_tone_pcs(MINOR_TONIC_PC, "V"))
    assert not (iv_pcs & v_pcs)
    found = False
    for seed in range(500):
        events = generator._right_hand_events(
            random.Random(seed),
            MINOR_TONIC_PC,
            [("IV", BEATS_PER_BAR)],
            next_minor_tonic_pc=MINOR_TONIC_PC,
            next_roman_token="V",
        )
        pickup = [e for e in events if e.start_beat == 3.5 and e.duration_beat == 1.0]
        if pickup and all(e.pitch % 12 in v_pcs for e in pickup):
            found = True
            break
    assert found


def test_right_hand_events_anticipation_is_not_applied_every_bar():
    found_without = False
    for seed in range(500):
        events = generator._right_hand_events(
            random.Random(seed),
            MINOR_TONIC_PC,
            [("IV", BEATS_PER_BAR)],
            next_minor_tonic_pc=MINOR_TONIC_PC,
            next_roman_token="V",
        )
        pickup = [e for e in events if e.start_beat == 3.5 and e.duration_beat == 1.0]
        if not pickup:
            found_without = True
            break
    assert found_without


def test_right_hand_events_riff_bars_do_not_anticipate_next_chord():
    # Same fixed 7sus4 quotation as the riff-only tests; the arpeggio must
    # stay exactly as written even when lookahead into a different chord
    # ("IV") is available, since riffs are exempt from anticipation.
    expected_pitches = [55, 60, 62, 65, 62, 60, 55, 60]
    for seed in range(200):
        events = generator._right_hand_events(
            random.Random(seed),
            MINOR_TONIC_PC,
            [("Vsus4", BEATS_PER_BAR)],
            next_minor_tonic_pc=MINOR_TONIC_PC,
            next_roman_token="IV",
        )
        if [e.pitch for e in events] == expected_pitches:
            break
    else:
        raise AssertionError("expected the 7sus4 arpeggio to remain unaffected by lookahead")


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
