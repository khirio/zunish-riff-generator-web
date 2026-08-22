import {
  KEY_LOW,
  KEY_HIGH,
  WHITE_PCS,
  WHITE_INDEX_IN_OCTAVE,
  BLACK_OFFSET_IN_OCTAVE,
  WHITE_KEY_WIDTH,
  WHITE_KEY_HEIGHT,
  BLACK_KEY_WIDTH,
  BLACK_KEY_HEIGHT,
  DEFAULT_WHITE_FILL,
  DEFAULT_BLACK_FILL,
  CHANNEL_COLORS,
  FALLBACK_ACTIVE_FILL,
} from "./constants.js";

/** Position of a MIDI note along the keyboard, in white-key-width units. Ported from gui.py's _white_key_units. */
export function whiteKeyUnits(pitch) {
  const pc = pitch % 12;
  const octave = Math.floor(pitch / 12) - 1;
  if (pc in WHITE_INDEX_IN_OCTAVE) return octave * 7 + WHITE_INDEX_IN_OCTAVE[pc];
  return octave * 7 + BLACK_OFFSET_IN_OCTAVE[pc];
}

export function buildKeyLayout() {
  const units = [];
  for (let pitch = KEY_LOW; pitch <= KEY_HIGH; pitch++) units.push(whiteKeyUnits(pitch));
  const minUnits = Math.min(...units);
  const maxUnits = Math.max(...units);
  const canvasWidth = Math.round((maxUnits - minUnits + 1) * WHITE_KEY_WIDTH);

  const keys = [];
  for (let pitch = KEY_LOW; pitch <= KEY_HIGH; pitch++) {
    const isWhite = WHITE_PCS.has(pitch % 12);
    keys.push({
      pitch,
      isWhite,
      x: (whiteKeyUnits(pitch) - minUnits) * WHITE_KEY_WIDTH,
      width: isWhite ? WHITE_KEY_WIDTH : BLACK_KEY_WIDTH,
      height: isWhite ? WHITE_KEY_HEIGHT : BLACK_KEY_HEIGHT,
    });
  }
  return { keys, keysByPitch: new Map(keys.map((k) => [k.pitch, k])), canvasWidth, canvasHeight: WHITE_KEY_HEIGHT };
}

/** Ported from gui.py's CHANNEL_COLORS.get(frozenset(channels), "#8E44AD") lookup. */
export function colorForActiveChannels(channels) {
  if (channels.size === 0) return null;
  const key = [...channels].sort().join(",");
  return CHANNEL_COLORS[key] ?? FALLBACK_ACTIVE_FILL;
}

export function fillColorForKey(key, activeChannels) {
  const activeColor = colorForActiveChannels(activeChannels);
  if (activeColor) return activeColor;
  return key.isWhite ? DEFAULT_WHITE_FILL : DEFAULT_BLACK_FILL;
}

export function drawKey(ctx, key, activeChannels) {
  ctx.fillStyle = fillColorForKey(key, activeChannels);
  ctx.fillRect(key.x, 0, key.width, key.height);
  ctx.strokeStyle = "black";
  ctx.strokeRect(key.x, 0, key.width, key.height);
}

export function drawKeyboard(ctx, layout) {
  ctx.clearRect(0, 0, layout.canvasWidth, layout.canvasHeight);
  const empty = new Set();
  for (const key of layout.keys) if (key.isWhite) drawKey(ctx, key, empty);
  for (const key of layout.keys) if (!key.isWhite) drawKey(ctx, key, empty);
}

/**
 * Redraws all keys (white layer, then black layer) using each key's current
 * active-channel state. Black keys visually overlap their neighboring white
 * keys, so repainting only a single changed key can erase a sliver of an
 * adjacent black key; always redrawing the full keyboard avoids that.
 */
export function drawKeyboardWithState(ctx, layout, activeByPitch) {
  ctx.clearRect(0, 0, layout.canvasWidth, layout.canvasHeight);
  for (const key of layout.keys) {
    if (key.isWhite) drawKey(ctx, key, activeByPitch.get(key.pitch) ?? new Set());
  }
  for (const key of layout.keys) {
    if (!key.isWhite) drawKey(ctx, key, activeByPitch.get(key.pitch) ?? new Set());
  }
}

/** Live piano keyboard bound to a <canvas>. Mirrors gui.py's PianoGUI keyboard drawing. */
export class PianoKeyboard {
  constructor(canvas) {
    this.layout = buildKeyLayout();
    this.ctx = canvas.getContext("2d");
    this.activeByPitch = new Map();
    canvas.width = this.layout.canvasWidth;
    canvas.height = this.layout.canvasHeight;
    canvas.style.background = "#555555";
    drawKeyboardWithState(this.ctx, this.layout, this.activeByPitch);
  }

  setNoteActive(pitch, channel, isOn) {
    const key = this.layout.keysByPitch.get(pitch);
    if (!key) return;
    let channels = this.activeByPitch.get(pitch);
    if (!channels) {
      channels = new Set();
      this.activeByPitch.set(pitch, channels);
    }
    if (isOn) channels.add(channel);
    else channels.delete(channel);
    drawKeyboardWithState(this.ctx, this.layout, this.activeByPitch);
  }

  reset() {
    this.activeByPitch.clear();
    drawKeyboardWithState(this.ctx, this.layout, this.activeByPitch);
  }
}
