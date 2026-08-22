import { test } from "node:test";
import assert from "node:assert/strict";
import { KEY_LOW, KEY_HIGH, WHITE_KEY_WIDTH, BLACK_KEY_WIDTH } from "../../static/js/constants.js";
import { buildKeyLayout, colorForActiveChannels, fillColorForKey, drawKeyboardWithState } from "../../static/js/keyboard.js";

function makeFakeCtx() {
  const calls = [];
  return {
    calls,
    fillRect(x, y, w, h) { calls.push({ op: "fillRect", x, y, w, h }); },
    strokeRect() {},
    clearRect() {},
    set fillStyle(v) { this._fillStyle = v; },
    get fillStyle() { return this._fillStyle; },
    set strokeStyle(v) {},
  };
}

test("buildKeyLayout produces one entry per MIDI note from KEY_LOW to KEY_HIGH", () => {
  const layout = buildKeyLayout();
  assert.equal(layout.keys.length, KEY_HIGH - KEY_LOW + 1);
  assert.equal(layout.keysByPitch.size, KEY_HIGH - KEY_LOW + 1);
  assert.equal(layout.keysByPitch.get(60).pitch, 60);
});

test("buildKeyLayout marks white/black keys correctly for one octave", () => {
  const layout = buildKeyLayout();
  // C4=60 (white) through B4=71 (white); C#4=61, D#4=63, F#4=66, G#4=68, A#4=70 are black.
  const whitePitches = new Set([60, 62, 64, 65, 67, 69, 71]);
  for (let pitch = 60; pitch <= 71; pitch++) {
    assert.equal(layout.keysByPitch.get(pitch).isWhite, whitePitches.has(pitch), `pitch ${pitch}`);
  }
});

test("buildKeyLayout places white keys left-to-right in ascending pitch order", () => {
  const layout = buildKeyLayout();
  const whiteKeysInPitchOrder = layout.keys.filter((k) => k.isWhite);
  for (let i = 1; i < whiteKeysInPitchOrder.length; i++) {
    assert.ok(
      whiteKeysInPitchOrder[i].x > whiteKeysInPitchOrder[i - 1].x,
      `white key ${whiteKeysInPitchOrder[i].pitch} should be right of ${whiteKeysInPitchOrder[i - 1].pitch}`
    );
  }
});

test("colorForActiveChannels returns null when nothing is active", () => {
  assert.equal(colorForActiveChannels(new Set()), null);
});

test("colorForActiveChannels matches gui.py's CHANNEL_COLORS for single and combined channels", () => {
  assert.equal(colorForActiveChannels(new Set([0])), "#4C8BF5");
  assert.equal(colorForActiveChannels(new Set([1])), "#F5A623");
  assert.equal(colorForActiveChannels(new Set([0, 1])), "#8E44AD");
  assert.equal(colorForActiveChannels(new Set([1, 0])), "#8E44AD"); // order-independent
});

test("fillColorForKey falls back to the key's own default fill when inactive", () => {
  const layout = buildKeyLayout();
  const whiteKey = layout.keysByPitch.get(60);
  const blackKey = layout.keysByPitch.get(61);
  assert.equal(fillColorForKey(whiteKey, new Set()), "white");
  assert.equal(fillColorForKey(blackKey, new Set()), "#222222");
});

test("fillColorForKey uses the active channel color when a channel is sounding", () => {
  const layout = buildKeyLayout();
  const key = layout.keysByPitch.get(60);
  assert.equal(fillColorForKey(key, new Set([0])), "#4C8BF5");
});

test("drawKeyboardWithState always draws black keys after white keys, preserving z-order on every redraw", () => {
  const layout = buildKeyLayout();
  const ctx = makeFakeCtx();
  const activeByPitch = new Map([[60, new Set([0])]]); // pretend C4 is sounding
  drawKeyboardWithState(ctx, layout, activeByPitch);

  const whiteKeyCount = layout.keys.filter((k) => k.isWhite).length;
  const blackKeyCount = layout.keys.filter((k) => !k.isWhite).length;
  assert.equal(ctx.calls.length, whiteKeyCount + blackKeyCount);

  // Every black key's fillRect call must come after every white key's fillRect call,
  // so a black key can never be painted over by a later white key redraw. Inspect the
  // actual recorded fillRect call order (classified by width, since white and black
  // keys are drawn with different widths) rather than just the counts.
  const fillRectCalls = ctx.calls.filter((c) => c.op === "fillRect");
  assert.equal(fillRectCalls.length, layout.keys.length);

  const lastWhiteCallIndex = fillRectCalls.reduce(
    (lastIndex, call, index) => (call.w === WHITE_KEY_WIDTH ? index : lastIndex),
    -1
  );
  const firstBlackCallIndex = fillRectCalls.findIndex((call) => call.w === BLACK_KEY_WIDTH);

  assert.ok(lastWhiteCallIndex !== -1, "expected at least one white-key fillRect call");
  assert.ok(firstBlackCallIndex !== -1, "expected at least one black-key fillRect call");
  assert.ok(
    lastWhiteCallIndex < firstBlackCallIndex,
    `every white-key fillRect call must come before every black-key fillRect call (last white at index ${lastWhiteCallIndex}, first black at index ${firstBlackCallIndex})`
  );
});
