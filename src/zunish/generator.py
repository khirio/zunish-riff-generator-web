"""Per-bar note generation.

Combines the current bar's chord(s)/scale with the riff, rhythm, and
accompaniment registries to produce a flat list of :class:`NoteEvent` for
one bar. A bar normally holds one whole-bar chord, but may instead hold two
half-bar chords (see :mod:`zunish.content.progressions`): the right hand
treats the bar as one continuous phrase that may cross the chord boundary,
while the left hand plays each chord independently within its own share of
the bar.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass, replace

from zunish import theory
from zunish.theory import BEATS_PER_BAR
from zunish.content.accompaniment import AccompanimentPattern, accompaniment
from zunish.content.rhythms import RhythmPattern, rhythms
from zunish.content.riffs import RiffMotif, riffs
from zunish.content.scales import scales
from zunish.content.voicings import VoicingVariant, voicings
from zunish.registry import weighted_choice

RIGHT_HAND_CHANNEL = 0
LEFT_HAND_CHANNEL = 1

RIGHT_HAND_BASE_VELOCITY = 100
LEFT_HAND_BASE_VELOCITY = 78
VELOCITY_JITTER = 5

SCALE_WALK_LOW_MIDI = 60
SCALE_WALK_HIGH_MIDI = 81
LEFT_HAND_OCTAVE = 2

BANNED_DEGREE_OFFSET = 8   # b6 (F in A minor) - never used in the melody, even as a chord tone
DORIAN_SIXTH_OFFSET = 9    # raised 6th (F# in A minor) - only when it matches a chord tone this bar
LEADING_TONE_OFFSET = 11   # harmonic_minor's raised 7th (G# in A minor) - only ever decorates the tonic (offset 0)

MAX_NON_CHORD_TONES_PER_BAR = 2
APPOGGIATURA_MIN_DURATION_BEAT = 0.5  # eighth note or longer
APPOGGIATURA_PROBABILITY = 0.5

DYAD_MIN_DURATION_BEAT = 0.5  # eighth note or longer
DYAD_PROBABILITY = 0.35

NEIGHBOR_TONE_MAX_STEP = 2  # semitones; a real appoggiatura is a whole step or less away

LEFT_HAND_ANTICIPATION_LEAD_BEAT = 0.5  # the last eighth note of the bar is where the push begins
LEFT_HAND_ANTICIPATION_SOUNDING_BEAT = 1.0  # quarter note total, straddling the bar line
LEFT_HAND_ANTICIPATION_PROBABILITY = 0.3

RIGHT_HAND_ANTICIPATION_LEAD_BEAT = 0.5  # the last eighth note of the bar is where the push begins
RIGHT_HAND_ANTICIPATION_SOUNDING_BEAT = 1.0  # quarter note total, straddling the bar line
RIGHT_HAND_ANTICIPATION_PROBABILITY = 1.0 / 3.0


@dataclass(frozen=True)
class NoteEvent:
    pitch: int
    start_beat: float
    duration_beat: float
    velocity: int
    channel: int


def _jittered_velocity(rng: random.Random, base: int) -> int:
    value = base + rng.randint(-VELOCITY_JITTER, VELOCITY_JITTER)
    return max(1, min(127, value))


def _pick_riff_or_none(rng: random.Random, quality: str) -> RiffMotif | None:
    compatible = [riff for riff in riffs.all() if quality in riff.compatible_qualities]
    if not compatible:
        return None
    candidates: list[tuple[RiffMotif | None, float]] = [(riff, riff.weight) for riff in compatible]
    fallback_weight = max(sum(weight for _, weight in candidates), 1.0)
    candidates.append((None, fallback_weight))
    return weighted_choice(rng, candidates)


def _riff_note_events(rng: random.Random, notes: list[int]) -> list[NoteEvent]:
    eighth = 0.5
    events: list[NoteEvent] = []
    t = 0.0
    last_index = len(notes) - 1
    for i, pitch in enumerate(notes):
        if t >= BEATS_PER_BAR:
            break
        remaining = BEATS_PER_BAR - t
        duration = remaining if i == last_index else min(eighth, remaining)
        events.append(
            NoteEvent(
                pitch=pitch,
                start_beat=t,
                duration_beat=duration,
                velocity=_jittered_velocity(rng, RIGHT_HAND_BASE_VELOCITY),
                channel=RIGHT_HAND_CHANNEL,
            )
        )
        t += eighth
    return events


def _melody_chord_tone_pcs(minor_tonic_pc: int, roman_token: str) -> list[int]:
    """Chord tones (root/3rd/5th) usable by the melody: the banned b6 is dropped
    even when it's literally one of this chord's own tones."""
    banned_pc = (minor_tonic_pc + BANNED_DEGREE_OFFSET) % 12
    return [pc for pc in theory.chord_pitch_classes(minor_tonic_pc, roman_token) if pc != banned_pc]


def _melody_decoration_pcs(minor_tonic_pc: int, scale, chord_tone_pcs: list[int]) -> list[int]:
    """Non-chord-tone scale degrees available for passing/neighbor decoration.

    The banned b6 is always excluded. The dorian raised 6th is excluded here
    unconditionally: it only ever reaches the melody via ``chord_tone_pcs``,
    i.e. when it's actually a tone of the current bar's chord.
    """
    banned_pc = (minor_tonic_pc + BANNED_DEGREE_OFFSET) % 12
    dorian_pc = (minor_tonic_pc + DORIAN_SIXTH_OFFSET) % 12
    allowed = []
    for pc in theory.scale_pitch_classes(minor_tonic_pc, scale.degree_offsets):
        if pc in chord_tone_pcs or pc == banned_pc or pc == dorian_pc:
            continue
        allowed.append(pc)
    return allowed


def _midi_pool(pitch_classes) -> list[int]:
    pcs = set(pitch_classes)
    return [note for note in range(SCALE_WALK_LOW_MIDI, SCALE_WALK_HIGH_MIDI + 1) if note % 12 in pcs]


def _nearest_above_and_below(pitch: int, pool: list[int]) -> tuple[int | None, int | None]:
    above = min((n for n in pool if n > pitch), default=None)
    below = max((n for n in pool if n < pitch), default=None)
    return above, below


def _pick_neighbor_tone(
    rng: random.Random, pitch: int, decoration_pool: list[int], minor_tonic_pc: int = 0
) -> int | None:
    """Pick a scale-step neighbor of ``pitch`` from ``decoration_pool``, above or below.

    Only a genuine step (<= a whole tone) counts; wider gaps (e.g. across a
    pentatonic scale's missing degree) wouldn't sound like an appoggiatura.

    The harmonic_minor leading tone (``LEADING_TONE_OFFSET``, e.g. G# in A
    minor) is excluded unless it would decorate the tonic (offset 0): it's
    meant strictly as an appoggiatura resolving up to the tonic, never a
    free neighbor of some other scale degree (e.g. the b7 a semitone below
    it). It still reaches the melody normally as an actual chord tone (e.g.
    III's third or V#dim's root) - that path bypasses ``decoration_pool``
    entirely (see ``_melody_decoration_pcs``), so this restriction doesn't
    apply there.
    """
    leading_tone_pc = (minor_tonic_pc + LEADING_TONE_OFFSET) % 12
    tonic_pc = minor_tonic_pc % 12
    above, below = _nearest_above_and_below(pitch, decoration_pool)
    candidates = [
        n
        for n in (above, below)
        if n is not None
        and abs(n - pitch) <= NEIGHBOR_TONE_MAX_STEP
        and (n % 12 != leading_tone_pc or pitch % 12 == tonic_pc)
    ]
    if not candidates:
        return None
    return rng.choice(candidates)


def _pick_harmony_tone(rng: random.Random, pitch: int, chord_tone_pool: list[int]) -> int | None:
    """Pick a chord tone of a different pitch class than ``pitch`` to sound alongside it."""
    others = [n for n in chord_tone_pool if n % 12 != pitch % 12]
    above, below = _nearest_above_and_below(pitch, others)
    candidates = [n for n in (above, below) if n is not None]
    if not candidates:
        return None
    return rng.choice(candidates)


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


def _is_strong_beat(start_beat: float) -> bool:
    return abs(start_beat - round(start_beat)) < 1e-9


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
        neighbor = _pick_neighbor_tone(rng, pitch, segment.decoration_pool, minor_tonic_pc) if eligible else None
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


def _apply_right_hand_anticipation(
    events: list[NoteEvent], next_chord_tone_pool: list[int]
) -> list[NoteEvent]:
    """Push the bar's last eighth note early onto the next bar's leading
    chord tone (a "kick"/anticipation), picking whichever tone in
    ``next_chord_tone_pool`` is closest to the note being pushed so the
    melody keeps stepping smoothly. The pushed note rings for a full quarter
    note, straddling the bar line, so the syncopation reads clearly instead
    of getting cut off at the bar edge."""
    pickup_start = BEATS_PER_BAR - RIGHT_HAND_ANTICIPATION_LEAD_BEAT
    result: list[NoteEvent] = []
    for event in events:
        end_beat = event.start_beat + event.duration_beat
        if end_beat <= pickup_start:
            result.append(event)
            continue
        pickup_pitch = min(next_chord_tone_pool, key=lambda n: abs(n - event.pitch))
        if event.start_beat < pickup_start:
            result.append(replace(event, duration_beat=pickup_start - event.start_beat))
        result.append(
            replace(
                event,
                pitch=pickup_pitch,
                start_beat=pickup_start,
                duration_beat=RIGHT_HAND_ANTICIPATION_SOUNDING_BEAT,
            )
        )
    return result


def _right_hand_events(
    rng: random.Random,
    minor_tonic_pc: int,
    chords: list[tuple[str, float]],
    next_minor_tonic_pc: int | None = None,
    next_roman_token: str | None = None,
) -> list[NoteEvent]:
    lead_roman_token, _lead_beats = chords[0]
    _degree, quality = theory.parse_roman_numeral(lead_roman_token)
    riff = _pick_riff_or_none(rng, quality)
    if riff is not None:
        root_pc = theory.chord_root_pc(minor_tonic_pc, lead_roman_token)
        notes = theory.transpose_motif(riff.intervals, root_pc, riff.root_octave)
        return _riff_note_events(rng, notes)

    rhythm = weighted_choice(rng, [(r, r.weight) for r in rhythms.all()])
    events = _melody_note_events(rng, minor_tonic_pc, chords, rhythm)

    if (
        next_minor_tonic_pc is not None
        and next_roman_token is not None
        and rng.random() < RIGHT_HAND_ANTICIPATION_PROBABILITY
    ):
        next_chord_tone_pool = _midi_pool(_melody_chord_tone_pcs(next_minor_tonic_pc, next_roman_token)) or [69]
        events = _apply_right_hand_anticipation(events, next_chord_tone_pool)

    return events


def _apply_left_hand_anticipation(
    events: list[NoteEvent], old_voicing: list[int], next_voicing: list[int]
) -> list[NoteEvent]:
    """Push the bar's last eighth note early onto the next chord (a "kick"/
    anticipation), preserving each note's voice (root/3rd/5th) in the new chord.
    The pushed note rings for a full quarter note, straddling the bar line, so
    the syncopation reads clearly instead of getting cut off at the bar edge."""
    pickup_start = BEATS_PER_BAR - LEFT_HAND_ANTICIPATION_LEAD_BEAT
    result: list[NoteEvent] = []
    for event in events:
        end_beat = event.start_beat + event.duration_beat
        if end_beat <= pickup_start:
            result.append(event)
            continue
        voice = old_voicing.index(event.pitch) if event.pitch in old_voicing else 0
        pickup_pitch = next_voicing[voice % len(next_voicing)]
        if event.start_beat < pickup_start:
            result.append(replace(event, duration_beat=pickup_start - event.start_beat))
        result.append(
            replace(
                event,
                pitch=pickup_pitch,
                start_beat=pickup_start,
                duration_beat=LEFT_HAND_ANTICIPATION_SOUNDING_BEAT,
            )
        )
    return result


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
    following bar's first chord. The right hand uses them to occasionally
    anticipate that chord on the bar's last eighth note (see
    ``_apply_right_hand_anticipation``); the left hand does not use them yet.
    """
    return _right_hand_events(
        rng, minor_tonic_pc, chords, next_minor_tonic_pc, next_roman_token
    ) + _left_hand_events_for_bar(rng, minor_tonic_pc, chords)
