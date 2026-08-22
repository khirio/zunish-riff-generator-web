export const BEATS_PER_BAR = 4.0; // mirrors zunish.theory.BEATS_PER_BAR (Python)
export const TICKS_PER_BEAT = 480; // mirrors zunish.midi_export.TICKS_PER_BEAT (Python)

// Piano keyboard layout, ported from zunish/gui.py.
export const KEY_LOW = 36; // C2
export const KEY_HIGH = 84; // C6

export const WHITE_PCS = new Set([0, 2, 4, 5, 7, 9, 11]);
export const WHITE_INDEX_IN_OCTAVE = { 0: 0, 2: 1, 4: 2, 5: 3, 7: 4, 9: 5, 11: 6 };
export const BLACK_OFFSET_IN_OCTAVE = { 1: 0.7, 3: 1.7, 6: 3.7, 8: 4.7, 10: 5.7 };

export const WHITE_KEY_WIDTH = 32;
export const WHITE_KEY_HEIGHT = 160;
export const BLACK_KEY_WIDTH = Math.trunc(WHITE_KEY_WIDTH * 0.6);
export const BLACK_KEY_HEIGHT = Math.trunc(WHITE_KEY_HEIGHT * 0.6);

export const DEFAULT_WHITE_FILL = "white";
export const DEFAULT_BLACK_FILL = "#222222";

// Highlight color keyed by the sorted, comma-joined set of channels currently
// sounding a pitch (channel 0 = right hand, channel 1 = left hand). Mirrors
// gui.py's CHANNEL_COLORS (there, keyed by frozenset; JS has no frozenset, so
// a canonical sorted-and-joined string is used as the key instead).
export const CHANNEL_COLORS = {
  "0": "#4C8BF5",
  "1": "#F5A623",
  "0,1": "#8E44AD",
};
export const FALLBACK_ACTIVE_FILL = "#8E44AD";
