import { TICKS_PER_BEAT } from "./constants.js";

/** Encode a non-negative integer as a MIDI variable-length quantity (array of bytes). */
export function encodeVariableLength(value) {
  const septets = [value & 0x7f];
  value = Math.floor(value / 128);
  while (value > 0) {
    septets.unshift((value & 0x7f) | 0x80);
    value = Math.floor(value / 128);
  }
  return septets;
}

function pushString(bytes, str) {
  for (let i = 0; i < str.length; i++) bytes.push(str.charCodeAt(i));
}

function pushUint32BE(bytes, value) {
  bytes.push((value >>> 24) & 0xff, (value >>> 16) & 0xff, (value >>> 8) & 0xff, value & 0xff);
}

function pushUint16BE(bytes, value) {
  bytes.push((value >>> 8) & 0xff, value & 0xff);
}

/**
 * Build a Standard MIDI File (format 0, single track) from accumulated notes.
 * `notes` items: { absoluteStartBeat, durationBeat, velocity, channel, pitch }.
 * Note-off events sort before note-on events at an identical tick, so a
 * pitch re-struck exactly when its previous instance ends never appears to
 * overlap itself in the file.
 */
export function buildMidiFile(notes, tempoBpm) {
  const events = [];
  for (const note of notes) {
    const startTick = Math.round(note.absoluteStartBeat * TICKS_PER_BEAT);
    const endTick = Math.round((note.absoluteStartBeat + note.durationBeat) * TICKS_PER_BEAT);
    events.push({ tick: startTick, priority: 1, bytes: [0x90 | note.channel, note.pitch, note.velocity] });
    events.push({ tick: endTick, priority: 0, bytes: [0x80 | note.channel, note.pitch, 0x00] });
  }
  events.sort((a, b) => a.tick - b.tick || a.priority - b.priority);

  const track = [];
  const microsecondsPerQuarter = Math.round(60000000 / tempoBpm);
  track.push(...encodeVariableLength(0));
  track.push(
    0xff, 0x51, 0x03,
    (microsecondsPerQuarter >>> 16) & 0xff,
    (microsecondsPerQuarter >>> 8) & 0xff,
    microsecondsPerQuarter & 0xff
  );

  let lastTick = 0;
  for (const event of events) {
    track.push(...encodeVariableLength(Math.max(0, event.tick - lastTick)));
    track.push(...event.bytes);
    lastTick = event.tick;
  }
  track.push(...encodeVariableLength(0), 0xff, 0x2f, 0x00);

  const bytes = [];
  pushString(bytes, "MThd");
  pushUint32BE(bytes, 6);
  pushUint16BE(bytes, 0); // format 0
  pushUint16BE(bytes, 1); // 1 track
  pushUint16BE(bytes, TICKS_PER_BEAT);
  pushString(bytes, "MTrk");
  pushUint32BE(bytes, track.length);
  for (let i = 0; i < track.length; i++) bytes.push(track[i]);

  return new Uint8Array(bytes);
}
