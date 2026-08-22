import { test } from "node:test";
import assert from "node:assert/strict";
import { encodeVariableLength, buildMidiFile } from "../../static/js/midi-writer.js";

test("encodeVariableLength encodes values under 128 as a single byte", () => {
  assert.deepEqual(encodeVariableLength(0), [0x00]);
  assert.deepEqual(encodeVariableLength(127), [0x7f]);
});

test("encodeVariableLength encodes multi-byte values with continuation bits", () => {
  assert.deepEqual(encodeVariableLength(128), [0x81, 0x00]);
  assert.deepEqual(encodeVariableLength(480), [0x83, 0x60]);
});

test("buildMidiFile produces the exact expected bytes for a single note", () => {
  const notes = [
    { absoluteStartBeat: 0, durationBeat: 1, velocity: 100, channel: 0, pitch: 60 },
  ];
  const bytes = buildMidiFile(notes, 120);

  // tempo=120 BPM => 500000 microseconds per quarter note (0x07A120).
  // 1 beat at 480 ticks/beat => note-off is 480 ticks (VLQ: 0x83 0x60) after note-on.
  const expected = Uint8Array.from([
    // MThd header: length=6, format=0, ntrks=1, division=480
    0x4d, 0x54, 0x68, 0x64, 0x00, 0x00, 0x00, 0x06, 0x00, 0x00, 0x00, 0x01, 0x01, 0xe0,
    // MTrk header: length=20
    0x4d, 0x54, 0x72, 0x6b, 0x00, 0x00, 0x00, 0x14,
    // delta=0, set_tempo meta event (500000 us/quarter = 0x07A120)
    0x00, 0xff, 0x51, 0x03, 0x07, 0xa1, 0x20,
    // delta=0, note_on channel 0, pitch 60, velocity 100
    0x00, 0x90, 0x3c, 0x64,
    // delta=480 (VLQ 0x83 0x60), note_off channel 0, pitch 60
    0x83, 0x60, 0x80, 0x3c, 0x00,
    // delta=0, end_of_track meta event
    0x00, 0xff, 0x2f, 0x00,
  ]);
  assert.deepEqual(bytes, expected);
});

test("buildMidiFile sorts overlapping notes by tick, note-off before note-on at the same tick", () => {
  // A pitch re-struck exactly when the previous instance of the same pitch ends:
  // the note-off for the first must be emitted before the note-on for the second.
  const notes = [
    { absoluteStartBeat: 0, durationBeat: 1, velocity: 100, channel: 0, pitch: 60 },
    { absoluteStartBeat: 1, durationBeat: 1, velocity: 90, channel: 0, pitch: 60 },
  ];
  const bytes = buildMidiFile(notes, 120);
  // Find the two events at tick 480 (delta 480 from tick 0, then delta 0 for the second):
  // ... 0x83 0x60 (delta 480) 0x80 0x3c 0x00 (note off) 0x00 (delta 0) 0x90 0x3c 0x5a (note on) ...
  const bytesArray = Array.from(bytes);
  const deltaAndOff = [0x83, 0x60, 0x80, 0x3c, 0x00];
  const offIndex = indexOfSubsequence(bytesArray, deltaAndOff);
  assert.notEqual(offIndex, -1, "expected a note-off event 480 ticks after the start");
  const onIndex = indexOfSubsequence(bytesArray, [0x00, 0x90, 0x3c, 0x5a]);
  assert.notEqual(onIndex, -1, "expected a note-on event for the second note (velocity 90 = 0x5a)");
  assert.ok(offIndex < onIndex, "note-off must be emitted before the re-triggering note-on at the same tick");
});

test("buildMidiFile does not throw for a very large number of notes", () => {
  const notes = [];
  for (let i = 0; i < 20000; i++) {
    notes.push({ absoluteStartBeat: i, durationBeat: 1, velocity: 100, channel: 0, pitch: 60 + (i % 12) });
  }
  assert.doesNotThrow(() => buildMidiFile(notes, 120));
});

function indexOfSubsequence(haystack, needle) {
  for (let i = 0; i <= haystack.length - needle.length; i++) {
    if (needle.every((value, offset) => haystack[i + offset] === value)) return i;
  }
  return -1;
}
