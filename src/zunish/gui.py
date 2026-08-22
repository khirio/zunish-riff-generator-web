"""Tkinter piano-keyboard visualizer.

Renders a live 4-octave keyboard (MIDI 36-84, C2-C6, centered on C4=60)
plus tempo/key readouts. Driven entirely by events pushed onto a
thread-safe queue from the playback thread; this module never touches
FluidSynth or the generator/director directly.
"""

from __future__ import annotations

import queue
import tkinter as tk
from collections.abc import Callable

from zunish import theory

KEY_LOW = 36  # C2
KEY_HIGH = 84  # C6

WHITE_PCS = {0, 2, 4, 5, 7, 9, 11}
WHITE_INDEX_IN_OCTAVE = {0: 0, 2: 1, 4: 2, 5: 3, 7: 4, 9: 5, 11: 6}
BLACK_OFFSET_IN_OCTAVE = {1: 0.7, 3: 1.7, 6: 3.7, 8: 4.7, 10: 5.7}

WHITE_KEY_WIDTH = 32
WHITE_KEY_HEIGHT = 160
BLACK_KEY_WIDTH = int(WHITE_KEY_WIDTH * 0.6)
BLACK_KEY_HEIGHT = int(WHITE_KEY_HEIGHT * 0.6)

DEFAULT_WHITE_FILL = "white"
DEFAULT_BLACK_FILL = "#222222"

# Highlight color keyed by the set of channels currently sounding a pitch.
# channel 0 = right hand, channel 1 = left hand.
CHANNEL_COLORS: dict[frozenset[int], str] = {
    frozenset({0}): "#4C8BF5",
    frozenset({1}): "#F5A623",
    frozenset({0, 1}): "#8E44AD",
}

POLL_INTERVAL_MS = 16


def _white_key_units(pitch: int) -> float:
    """Position of a MIDI note along the keyboard, in white-key-width units."""
    pc = pitch % 12
    octave = pitch // 12 - 1
    if pc in WHITE_INDEX_IN_OCTAVE:
        return octave * 7 + WHITE_INDEX_IN_OCTAVE[pc]
    return octave * 7 + BLACK_OFFSET_IN_OCTAVE[pc]


class PianoGUI:
    def __init__(
        self,
        event_queue: "queue.Queue",
        tempo_bpm: float,
        initial_key_pc: int,
        on_close: Callable[[], None] | None = None,
    ):
        self._queue = event_queue
        self._on_close = on_close
        self._active: dict[int, set[int]] = {}

        self._root = tk.Tk()
        self._root.title("zunish - live piano")
        self._root.protocol("WM_DELETE_WINDOW", self._handle_close)

        header = tk.Frame(self._root)
        header.pack(fill="x", padx=8, pady=6)
        self._tempo_var = tk.StringVar()
        self._key_var = tk.StringVar()
        tk.Label(header, textvariable=self._tempo_var, font=("TkDefaultFont", 12, "bold")).pack(side="left")
        tk.Label(header, textvariable=self._key_var, font=("TkDefaultFont", 12, "bold")).pack(
            side="left", padx=(24, 0)
        )

        self._min_units = min(_white_key_units(p) for p in range(KEY_LOW, KEY_HIGH + 1))
        max_units = max(_white_key_units(p) for p in range(KEY_LOW, KEY_HIGH + 1))
        canvas_width = int((max_units - self._min_units + 1) * WHITE_KEY_WIDTH)

        self._canvas = tk.Canvas(
            self._root, width=canvas_width, height=WHITE_KEY_HEIGHT, bg="#555555", highlightthickness=0
        )
        self._canvas.pack(padx=8, pady=(0, 8))

        self._key_rects: dict[int, int] = {}
        self._key_is_white: dict[int, bool] = {}
        self._draw_keys()

        self.update_tempo(tempo_bpm)
        self.update_key(initial_key_pc)

    def _x_for(self, pitch: int) -> float:
        return (_white_key_units(pitch) - self._min_units) * WHITE_KEY_WIDTH

    def _draw_keys(self) -> None:
        for pitch in range(KEY_LOW, KEY_HIGH + 1):
            if pitch % 12 not in WHITE_PCS:
                continue
            x = self._x_for(pitch)
            rect = self._canvas.create_rectangle(
                x, 0, x + WHITE_KEY_WIDTH, WHITE_KEY_HEIGHT, fill=DEFAULT_WHITE_FILL, outline="black"
            )
            self._key_rects[pitch] = rect
            self._key_is_white[pitch] = True

        for pitch in range(KEY_LOW, KEY_HIGH + 1):
            if pitch % 12 in WHITE_PCS:
                continue
            x = self._x_for(pitch)
            rect = self._canvas.create_rectangle(
                x, 0, x + BLACK_KEY_WIDTH, BLACK_KEY_HEIGHT, fill=DEFAULT_BLACK_FILL, outline="black"
            )
            self._key_rects[pitch] = rect
            self._key_is_white[pitch] = False

    def update_tempo(self, tempo_bpm: float) -> None:
        self._tempo_var.set(f"Tempo: {tempo_bpm:.0f} BPM")

    def update_key(self, minor_tonic_pc: int) -> None:
        name = theory.pc_to_note_name(minor_tonic_pc)
        self._key_var.set(f"Key: {name}m")

    def _set_key_fill(self, pitch: int, channels: set[int]) -> None:
        rect = self._key_rects.get(pitch)
        if rect is None:
            return
        if channels:
            color = CHANNEL_COLORS.get(frozenset(channels), "#8E44AD")
        else:
            color = DEFAULT_WHITE_FILL if self._key_is_white[pitch] else DEFAULT_BLACK_FILL
        self._canvas.itemconfig(rect, fill=color)

    def _handle_note_event(self, channel: int, pitch: int, is_on: bool) -> None:
        channels = self._active.setdefault(pitch, set())
        if is_on:
            channels.add(channel)
        else:
            channels.discard(channel)
        self._set_key_fill(pitch, channels)

    def _poll_queue(self) -> None:
        try:
            while True:
                item = self._queue.get_nowait()
                if item[0] == "note":
                    _, channel, pitch, is_on = item
                    self._handle_note_event(channel, pitch, is_on)
                elif item[0] == "key":
                    _, minor_tonic_pc = item
                    self.update_key(minor_tonic_pc)
        except queue.Empty:
            pass
        self._root.after(POLL_INTERVAL_MS, self._poll_queue)

    def _handle_close(self) -> None:
        if self._on_close is not None:
            self._on_close()
        self._root.destroy()

    def run(self) -> None:
        self._poll_queue()
        self._root.mainloop()
