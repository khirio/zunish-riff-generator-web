"""Rhythm pattern registry, used when the generator falls back to a
scale-walk riff (i.e. no fixed motif was chosen for the current chord).

Each pattern is a sequence of note durations expressed in sixteenth-note
units within one bar (assumed 4/4, 16 sixteenths per bar).
"""

from __future__ import annotations

from dataclasses import dataclass

from zunish.registry import Registry


@dataclass(frozen=True)
class RhythmPattern:
    id: str
    name: str
    sixteenth_note_durations: tuple[int, ...]
    weight: float = 1.0

    def onsets_in_beats(self) -> list[tuple[float, float]]:
        """Return [(start_beat, duration_beat), ...] for one bar."""
        beat_per_sixteenth = 0.25
        onsets: list[tuple[float, float]] = []
        t = 0.0
        for duration in self.sixteenth_note_durations:
            duration_beat = duration * beat_per_sixteenth
            onsets.append((t, duration_beat))
            t += duration_beat
        return onsets


rhythms: Registry[RhythmPattern] = Registry("rhythm")


def _register(entry_id: str, name: str, sixteenth_note_durations: tuple[int, ...], *, weight: float = 1.0) -> None:
    rhythms.register(
        RhythmPattern(id=entry_id, name=name, sixteenth_note_durations=sixteenth_note_durations, weight=weight)
    )


# Tresillo: dotted-eighth + dotted-eighth + eighth == 6 + 6 + 4 sixteenth-note units.
_register("tresillo_16", "Tresillo", (6, 6, 4), weight=2.0)
_register("straight_sixteenths", "均等16分", (1,) * 16, weight=1.0)
_register("sixteenth_pickup", "16分ピックアップ", (1, 1, 2, 4, 2, 2, 2, 2), weight=2.0)
_register("gallop_16th", "ギャロップ", (1, 1, 2, 1, 1, 2, 4, 4), weight=1.5)
