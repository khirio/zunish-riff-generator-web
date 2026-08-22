"""Optional recorder that mirrors real-time-played events into a standard
.mid file. Only active when the CLI is given ``--save``."""

from __future__ import annotations

import time

import mido

TICKS_PER_BEAT = 480


class MidiRecorder:
    def __init__(self, tempo_bpm: float):
        self._tempo_bpm = tempo_bpm
        self._start_time = time.monotonic()
        self._events: list[tuple[float, mido.Message]] = []

    def note_on(self, channel: int, pitch: int, velocity: int) -> None:
        self._record(mido.Message("note_on", channel=channel, note=pitch, velocity=velocity))

    def note_off(self, channel: int, pitch: int) -> None:
        self._record(mido.Message("note_off", channel=channel, note=pitch, velocity=0))

    def _record(self, message: mido.Message) -> None:
        elapsed = time.monotonic() - self._start_time
        self._events.append((elapsed, message))

    def save(self, path: str) -> None:
        midi_file = mido.MidiFile(ticks_per_beat=TICKS_PER_BEAT)
        track = mido.MidiTrack()
        midi_file.tracks.append(track)
        track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(self._tempo_bpm)))

        seconds_per_tick = (60.0 / self._tempo_bpm) / TICKS_PER_BEAT
        last_tick = 0
        for elapsed, message in self._events:
            tick = round(elapsed / seconds_per_tick)
            message.time = max(0, tick - last_tick)
            last_tick = tick
            track.append(message)

        midi_file.save(path)
