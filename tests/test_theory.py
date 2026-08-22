from zunish import theory


def test_note_name_to_pc():
    assert theory.note_name_to_pc("C") == 0
    assert theory.note_name_to_pc("a") == 9
    assert theory.note_name_to_pc("C#") == 1
    assert theory.note_name_to_pc("Db") == 1


def test_pc_to_note_name_round_trip():
    for pc in range(12):
        assert theory.note_name_to_pc(theory.pc_to_note_name(pc)) == pc
        assert theory.pc_to_note_name(pc) == theory.PC_TO_NOTE_NAME[pc]
    assert theory.pc_to_note_name(0) == "C"
    assert theory.pc_to_note_name(9) == "A"
    assert theory.pc_to_note_name(1) == "C#"
    assert theory.pc_to_note_name(12) == "C"  # wraps modulo 12


def test_midi_note():
    assert theory.midi_note(0, 4) == 60  # C4
    assert theory.midi_note(9, 3) == 57  # A3


def test_parse_roman_numeral():
    assert theory.parse_roman_numeral("IV") == (5, "")
    assert theory.parse_roman_numeral("V") == (7, "")
    assert theory.parse_roman_numeral("VIm") == (9, "m")
    assert theory.parse_roman_numeral("Vsus4") == (7, "sus4")
    assert theory.parse_roman_numeral("IIm") == (2, "m")


def test_parse_roman_numeral_with_accidental():
    assert theory.parse_roman_numeral("V#dim") == (8, "dim")
    assert theory.parse_roman_numeral("IIb") == (1, "")


def test_dim_chord_pitch_classes():
    # A minor (tonic pc 9): relative major root is C (pc 0). V#dim's root is
    # G#/Ab (7 + 1 semitones from C), forming a G#-B-D diminished triad.
    assert theory.chord_pitch_classes(9, "V#dim") == [8, 11, 2]


def test_vim_root_equals_minor_tonic():
    # VIm must resolve to the minor tonic itself, for every possible tonic.
    for minor_tonic_pc in range(12):
        assert theory.chord_root_pc(minor_tonic_pc, "VIm") == minor_tonic_pc


def test_chord_pitch_classes_quality():
    # A minor tonic (9) -> relative major C (0). IV of C major = F (major triad).
    pcs = theory.chord_pitch_classes(9, "IV")
    assert pcs == [5, 9, 0]  # F, A, C

    # VIm of A minor -> A minor triad (A, C, E).
    pcs = theory.chord_pitch_classes(9, "VIm")
    assert pcs == [9, 0, 4]  # A, C, E

    # Vsus4 -> sus4 triad on the V degree.
    pcs = theory.chord_pitch_classes(9, "Vsus4")
    assert pcs == [7, 0, 2]  # G, C, D


def test_chord_tones_midi_is_ascending():
    notes = theory.chord_tones_midi(9, "IV", octave=3)
    assert notes == sorted(notes)
    assert notes[0] % 12 == 5  # F


def test_scale_midi_notes_within_range():
    notes = theory.scale_midi_notes(9, theory.HARMONIC_MINOR, 60, 71)
    assert all(60 <= n <= 71 for n in notes)
    assert all(n % 12 in set(theory.scale_pitch_classes(9, theory.HARMONIC_MINOR)) for n in notes)


def test_invert_voicing_zero_is_root_position():
    notes = theory.chord_tones_midi(9, "IV", octave=2)
    assert theory.invert_voicing(notes, 0) == notes


def test_invert_voicing_first_inversion_puts_third_in_bass():
    notes = theory.chord_tones_midi(9, "IV", octave=2)  # [root, third, fifth]
    assert theory.invert_voicing(notes, 1) == [notes[1], notes[2], notes[0] + 12]


def test_invert_voicing_second_inversion_puts_fifth_in_bass():
    notes = theory.chord_tones_midi(9, "IV", octave=2)
    assert theory.invert_voicing(notes, 2) == [notes[2], notes[0] + 12, notes[1] + 12]


def test_invert_voicing_does_not_mutate_its_input():
    notes = theory.chord_tones_midi(9, "IV", octave=2)
    original = list(notes)
    theory.invert_voicing(notes, 1)
    assert notes == original


def test_raise_middle_voice_moves_the_third_up_an_octave():
    notes = theory.chord_tones_midi(9, "IV", octave=2)  # [root, third, fifth]
    assert theory.raise_middle_voice(notes) == [notes[0], notes[1] + 12, notes[2]]


def test_transpose_motif():
    # 7sus4 arpeggio intervals from root, transposed to A3 should reproduce
    # the example A3-D4-E4-G4-E4-D4.
    intervals = (0, 5, 7, 10, 7, 5)
    notes = theory.transpose_motif(intervals, root_pc=9, octave=3)
    assert notes == [57, 62, 64, 67, 64, 62]


def test_beats_per_bar_is_four_quarter_notes():
    assert theory.BEATS_PER_BAR == 4.0
