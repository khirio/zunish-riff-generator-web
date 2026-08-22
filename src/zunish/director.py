"""Infinite progression walker.

Owns the current key and current chord progression, and yields one bar's
worth of :class:`~zunish.generator.NoteEvent` at a time forever. Each
progression is looped a random number of times, after which a modulation
(±3 semitones) may trigger before a musically-connected next progression is
chosen from the ``follows`` weight graph.
"""

from __future__ import annotations

import random
from collections.abc import Iterator

from zunish.content.progressions import ChordProgression, progressions
from zunish.generator import BEATS_PER_BAR, NoteEvent, generate_bar
from zunish.registry import weighted_choice

MIN_PROGRESSION_REPEATS = 2
MAX_PROGRESSION_REPEATS = 4
MODULATION_PROBABILITY = 0.3
MODULATION_SEMITONES = 3


class Director:
    def __init__(
        self,
        minor_tonic_pc: int,
        rng: random.Random | None = None,
        enable_modulation: bool = True,
    ):
        self.minor_tonic_pc = minor_tonic_pc % 12
        self._walk_tonic_pc = self.minor_tonic_pc
        self._rng = rng or random.Random()
        self._enable_modulation = enable_modulation
        self._current: ChordProgression = weighted_choice(
            self._rng, [(p, p.start_weight) for p in progressions.all()]
        )

    def _maybe_modulate(self) -> None:
        if not self._enable_modulation:
            return
        if self._rng.random() < MODULATION_PROBABILITY:
            direction = self._rng.choice((1, -1))
            self._walk_tonic_pc = (self._walk_tonic_pc + direction * MODULATION_SEMITONES) % 12

    def _advance_progression(self) -> None:
        self._maybe_modulate()
        candidates = [
            (progressions.get(next_id), weight) for next_id, weight in self._current.follows.items()
        ]
        if not candidates:
            candidates = [(p, p.start_weight) for p in progressions.all()]
        self._current = weighted_choice(self._rng, candidates)

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

    def bars(self) -> Iterator[list[NoteEvent]]:
        """Yield one bar's NoteEvents at a time, forever.

        Looks one bar ahead and passes that lookahead through to
        ``generate_bar``, but neither hand actually uses it today; it's
        reserved for a future right-hand melody feature.
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
