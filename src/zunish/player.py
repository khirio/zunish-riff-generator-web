"""Real-time playback: schedules one bar's NoteEvents against a FluidSynth
synth instance using a simple event-timeline scheduler."""

from __future__ import annotations

import queue
import time
from collections.abc import Iterable

from zunish.generator import BEATS_PER_BAR, NoteEvent
from zunish.midi_export import MidiRecorder


class Player:
    def __init__(
        self,
        synth,
        tempo_bpm: float,
        recorder: MidiRecorder | None = None,
        event_sink: "queue.Queue | None" = None,
    ):
        self._synth = synth
        self._tempo_bpm = tempo_bpm
        self._recorder = recorder
        self._event_sink = event_sink
        self._active_notes: set[tuple[int, int]] = set()
        # (beat_time_into_next_bar, channel, pitch) for notes whose duration
        # (e.g. a left-hand anticipation) crosses the current bar's end.
        self._deferred_note_offs: list[tuple[float, int, int]] = []

    def _seconds_per_beat(self) -> float:
        return 60.0 / self._tempo_bpm

    def _note_on(self, channel: int, pitch: int, velocity: int) -> None:
        self._synth.noteon(channel, pitch, velocity)
        self._active_notes.add((channel, pitch))
        if self._recorder is not None:
            self._recorder.note_on(channel, pitch, velocity)
        if self._event_sink is not None:
            self._event_sink.put(("note", channel, pitch, True))

    def _note_off(self, channel: int, pitch: int) -> None:
        self._synth.noteoff(channel, pitch)
        self._active_notes.discard((channel, pitch))
        if self._recorder is not None:
            self._recorder.note_off(channel, pitch)
        if self._event_sink is not None:
            self._event_sink.put(("note", channel, pitch, False))

    def all_notes_off(self) -> None:
        for channel, pitch in list(self._active_notes):
            self._note_off(channel, pitch)

    def play_bar(self, events: Iterable[NoteEvent]) -> None:
        seconds_per_beat = self._seconds_per_beat()
        events = list(events)

        # Notes carried over from the previous bar (e.g. a left-hand
        # anticipation ringing past the bar line) are due at these offsets
        # into *this* bar. If this bar's own pattern re-strikes the same
        # pitch right where the carry-over is still sounding, drop both the
        # stale deferred note-off and the redundant note-on: the note just
        # keeps ringing, and turns off whenever the new event's own duration
        # says to.
        carry_over = self._deferred_note_offs
        self._deferred_note_offs = []
        suppressed_note_on_ids = set()
        remaining_carry_over: list[tuple[float, int, int]] = []
        for offset_beat, channel, pitch in carry_over:
            colliding = next(
                (
                    e
                    for e in events
                    if e.channel == channel and e.pitch == pitch and e.start_beat <= offset_beat + 1e-9
                ),
                None,
            )
            if colliding is not None:
                suppressed_note_on_ids.add(id(colliding))
            else:
                remaining_carry_over.append((offset_beat, channel, pitch))

        # (beat_time, sort_priority, is_note_on, channel, pitch, velocity);
        # note_off (priority 0) sorts before note_on (priority 1) at an
        # identical timestamp so a repeated pitch never gets cut by its own
        # re-trigger.
        timeline: list[tuple[float, int, bool, int, int, int]] = []
        for offset_beat, channel, pitch in remaining_carry_over:
            timeline.append((offset_beat, 0, False, channel, pitch, 0))
        for event in events:
            end_beat = event.start_beat + event.duration_beat
            if id(event) not in suppressed_note_on_ids:
                timeline.append((event.start_beat, 1, True, event.channel, event.pitch, event.velocity))
            if end_beat > BEATS_PER_BAR + 1e-9:
                # Rings past this bar: defer the note-off into the next play_bar call.
                self._deferred_note_offs.append((end_beat - BEATS_PER_BAR, event.channel, event.pitch))
            else:
                timeline.append((end_beat, 0, False, event.channel, event.pitch, 0))
        timeline.sort(key=lambda item: (item[0], item[1]))

        bar_start = time.monotonic()
        for beat_time, _priority, is_note_on, channel, pitch, velocity in timeline:
            target = bar_start + beat_time * seconds_per_beat
            remaining = target - time.monotonic()
            if remaining > 0:
                time.sleep(remaining)
            if is_note_on:
                self._note_on(channel, pitch, velocity)
            else:
                self._note_off(channel, pitch)

        # A deferred note-off (or a suppressed re-strike) can leave the
        # timeline "finishing" before the bar's nominal length; always wait
        # out the full bar so tempo doesn't drift.
        bar_end_target = bar_start + BEATS_PER_BAR * seconds_per_beat
        remaining = bar_end_target - time.monotonic()
        if remaining > 0:
            time.sleep(remaining)
