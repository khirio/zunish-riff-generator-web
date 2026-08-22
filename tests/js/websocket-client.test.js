import { test } from "node:test";
import assert from "node:assert/strict";
import { parseServerMessage } from "../../static/js/websocket-client.js";

test("parseServerMessage accepts a well-formed session_start message", () => {
  const message = parseServerMessage(
    JSON.stringify({ type: "session_start", tempo_bpm: 160, key: "A", seed: 42, modulation: true })
  );
  assert.deepEqual(message, { type: "session_start", tempo_bpm: 160, key: "A", seed: 42, modulation: true });
});

test("parseServerMessage rejects a session_start message whose modulation field is not a boolean", () => {
  assert.throws(() =>
    parseServerMessage(
      JSON.stringify({ type: "session_start", tempo_bpm: 160, key: "A", seed: 42, modulation: "true" })
    )
  );
});

test("parseServerMessage accepts a well-formed bar message", () => {
  const raw = JSON.stringify({
    type: "bar",
    bar_index: 3,
    key: "A",
    notes: [{ pitch: 60, start_beat: 0, duration_beat: 1, velocity: 100, channel: 0 }],
  });
  const message = parseServerMessage(raw);
  assert.equal(message.bar_index, 3);
  assert.equal(message.notes.length, 1);
});

test("parseServerMessage accepts a well-formed error message", () => {
  const message = parseServerMessage(JSON.stringify({ type: "error", message: "invalid key: 'Z'" }));
  assert.deepEqual(message, { type: "error", message: "invalid key: 'Z'" });
});

test("parseServerMessage rejects malformed JSON", () => {
  assert.throws(() => parseServerMessage("not json"));
});

test("parseServerMessage rejects an unrecognized message type", () => {
  assert.throws(() => parseServerMessage(JSON.stringify({ type: "unknown" })));
});

test("parseServerMessage rejects a session_start message missing required fields", () => {
  assert.throws(() => parseServerMessage(JSON.stringify({ type: "session_start", tempo_bpm: 160 })));
});

test("parseServerMessage rejects a bar message whose notes field is not an array", () => {
  assert.throws(() => parseServerMessage(JSON.stringify({ type: "bar", bar_index: 0, key: "A", notes: "oops" })));
});

test("parseServerMessage rejects a bar message whose notes array contains a malformed entry", () => {
  const raw = JSON.stringify({
    type: "bar",
    bar_index: 0,
    key: "A",
    notes: [{ pitch: 60, start_beat: 0, duration_beat: 1, velocity: 100, channel: 0 }, "oops"],
  });
  assert.throws(() => parseServerMessage(raw));
});
