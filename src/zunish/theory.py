"""Pitch-class arithmetic, roman-numeral chord parsing, and scale/motif realization.

Key convention: the song key is stored as the *minor tonic* pitch class.
Chord roman numerals (``IV``, ``V``, ``VIm``, ``Vsus4``, ...) are written
relative to the *relative major* of that minor key, matching the
convention used in the source material (e.g. ``VIm`` denotes the minor
tonic chord itself: degree VI of the relative major == the minor tonic).
"""

from __future__ import annotations

NOTE_PITCH_CLASSES: dict[str, int] = {
    "C": 0, "C#": 1, "DB": 1,
    "D": 2, "D#": 3, "EB": 3,
    "E": 4,
    "F": 5, "F#": 6, "GB": 6,
    "G": 7, "G#": 8, "AB": 8,
    "A": 9, "A#": 10, "BB": 10,
    "B": 11,
}

DEGREE_SEMITONES: dict[str, int] = {
    "I": 0, "II": 2, "III": 4, "IV": 5, "V": 7, "VI": 9, "VII": 11,
}
_DEGREE_TOKENS_BY_LENGTH_DESC = sorted(DEGREE_SEMITONES, key=len, reverse=True)

CHORD_QUALITY_INTERVALS: dict[str, tuple[int, ...]] = {
    "": (0, 4, 7),        # major triad
    "m": (0, 3, 7),       # minor triad
    "sus4": (0, 5, 7),    # sus4 triad
    "dim": (0, 3, 6),     # diminished triad
}

DEGREE_ACCIDENTAL_SEMITONES: dict[str, int] = {"#": 1, "b": -1}

BEATS_PER_BAR: float = 4.0  # a 4/4 bar, in quarter-note beats; shared by content/progressions.py and generator.py

# Scale interval sets, expressed as semitone offsets from the minor tonic.
NATURAL_MINOR: tuple[int, ...] = (0, 2, 3, 5, 7, 8, 10)
HARMONIC_MINOR: tuple[int, ...] = (0, 2, 3, 5, 7, 10, 11)  # ZUN流「和声的短音階」: b6を欠きb7/maj7を両方含む（教科書的な和声的短音階とは異なる）
DORIAN_6: tuple[int, ...] = (0, 2, 3, 5, 7, 9, 10)          # natural minor with raised 6th
MINOR_6NUKI: tuple[int, ...] = (0, 2, 3, 5, 7, 10)          # natural minor, b6 omitted
MINOR_PENTATONIC_2_6NUKI: tuple[int, ...] = (0, 3, 5, 7, 10)  # natural minor, 2nd and b6 omitted


def note_name_to_pc(name: str) -> int:
    key = name.strip().upper()
    if key not in NOTE_PITCH_CLASSES:
        raise ValueError(f"unknown note name: {name!r}")
    return NOTE_PITCH_CLASSES[key]


PC_TO_NOTE_NAME: tuple[str, ...] = (
    "C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B",
)


def pc_to_note_name(pc: int) -> str:
    """Reverse-lookup a pitch class to its canonical (sharp-spelled) note name."""
    return PC_TO_NOTE_NAME[pc % 12]


def midi_note(pitch_class: int, octave: int) -> int:
    return pitch_class + (octave + 1) * 12


def parse_roman_numeral(token: str) -> tuple[int, str]:
    """Split a roman-numeral chord token into (degree_semitones, quality).

    An optional accidental (``#`` or ``b``) immediately after the degree
    raises/lowers the root by a semitone, e.g. ``V#dim`` is a diminished
    triad built on the raised fifth degree.
    """
    for degree_token in _DEGREE_TOKENS_BY_LENGTH_DESC:
        if token.startswith(degree_token):
            rest = token[len(degree_token):]
            semitones = DEGREE_SEMITONES[degree_token]
            if rest[:1] in DEGREE_ACCIDENTAL_SEMITONES:
                semitones += DEGREE_ACCIDENTAL_SEMITONES[rest[0]]
                rest = rest[1:]
            if rest not in CHORD_QUALITY_INTERVALS:
                raise ValueError(f"unknown chord quality suffix: {rest!r} in {token!r}")
            return semitones, rest
    raise ValueError(f"unrecognized roman numeral: {token!r}")


def relative_major_root(minor_tonic_pc: int) -> int:
    return (minor_tonic_pc + 3) % 12


def chord_root_pc(minor_tonic_pc: int, token: str) -> int:
    degree, _quality = parse_roman_numeral(token)
    return (relative_major_root(minor_tonic_pc) + degree) % 12


def chord_pitch_classes(minor_tonic_pc: int, token: str) -> list[int]:
    """Return [root, third, fifth] pitch classes for a roman-numeral token."""
    degree, quality = parse_roman_numeral(token)
    root = (relative_major_root(minor_tonic_pc) + degree) % 12
    return [(root + interval) % 12 for interval in CHORD_QUALITY_INTERVALS[quality]]


def chord_tones_midi(minor_tonic_pc: int, token: str, octave: int) -> list[int]:
    """Return an ascending, root-position MIDI voicing for a roman-numeral token."""
    pitch_classes = chord_pitch_classes(minor_tonic_pc, token)
    root_midi = midi_note(pitch_classes[0], octave)
    notes = [root_midi]
    for pc in pitch_classes[1:]:
        candidate = root_midi - (root_midi % 12) + pc
        while candidate <= notes[-1]:
            candidate += 12
        notes.append(candidate)
    return notes


def invert_voicing(notes: list[int], inversion: int) -> list[int]:
    """Rotate the lowest ``inversion`` notes up an octave each (0=root
    position, 1=first inversion, 2=second inversion, ...). Note: after
    inversion, list index no longer maps to root/3rd/5th — it maps to
    whatever ended up lowest."""
    notes = list(notes)
    for _ in range(inversion % len(notes)):
        notes.append(notes.pop(0) + 12)
    return notes


def raise_middle_voice(notes: list[int]) -> list[int]:
    """Raise the middle voice of a root-position triad by an octave (an open/spread voicing)."""
    notes = list(notes)
    notes[len(notes) // 2] += 12
    return notes


def scale_pitch_classes(minor_tonic_pc: int, degree_offsets: tuple[int, ...]) -> list[int]:
    return [(minor_tonic_pc + offset) % 12 for offset in degree_offsets]


def scale_midi_notes(
    minor_tonic_pc: int, degree_offsets: tuple[int, ...], low: int, high: int
) -> list[int]:
    """Return every MIDI note in [low, high] whose pitch class is in the scale."""
    pitch_classes = set(scale_pitch_classes(minor_tonic_pc, degree_offsets))
    return [note for note in range(low, high + 1) if note % 12 in pitch_classes]


def transpose_motif(intervals: tuple[int, ...], root_pc: int, octave: int) -> list[int]:
    """Realize a motif (semitone offsets from its root) at a target root/octave."""
    root_midi = midi_note(root_pc, octave)
    return [root_midi + interval for interval in intervals]
