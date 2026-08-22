import { test } from "node:test";
import assert from "node:assert/strict";
import { computeTargetTick, computeDurationMs, computeSetTimeoutDelayMs, BarScheduler } from "../../static/js/scheduler.js";

// Fakes out BarScheduler's `now`/`scheduleTimeout` hooks so tests never let a
// real setTimeout fire (mirrors tests/test_player.py's FakeClock pattern).
function makeFakeTimers() {
  let currentTimeMs = 0;
  const scheduled = [];
  return {
    now: () => currentTimeMs,
    scheduleTimeout: (fn, delayMs) => scheduled.push({ fn, delayMs }),
    scheduled,
    advance(ms) {
      currentTimeMs += ms;
    },
  };
}

test("computeTargetTick converts bar/beat position to an absolute tick offset from the anchor", () => {
  // 60 BPM => 1 beat == 1000ms. Bar 2, beat 1.5 => (2*4 + 1.5) beats = 9.5 beats = 9500ms after anchor.
  assert.equal(computeTargetTick(1000, 60, 2, 1.5), 1000 + 9500);
});

test("computeTargetTick returns the anchor itself for bar 0 beat 0", () => {
  assert.equal(computeTargetTick(5000, 120, 0, 0), 5000);
});

test("computeDurationMs converts a beat duration to milliseconds for the given tempo", () => {
  // 120 BPM => 1 beat == 500ms.
  assert.equal(computeDurationMs(120, 2), 1000);
});

test("computeSetTimeoutDelayMs converts an absolute tick to a wall-clock delay from now", () => {
  // Anchor: tick=1000 corresponds to wall-clock 50000ms. A target 500 ticks later
  // should fire 500ms after that same wall-clock moment.
  const delay = computeSetTimeoutDelayMs(1500, 1000, 50000, 50000);
  assert.equal(delay, 500);
});

test("computeSetTimeoutDelayMs never returns a negative delay for a moment already in the past", () => {
  const delay = computeSetTimeoutDelayMs(1000, 1000, 50000, 60000); // 10 seconds have already passed
  assert.equal(delay, 0);
});

test("BarScheduler establishes its tick/wall-clock anchor on the first scheduled bar only", async () => {
  const sentEvents = [];
  let tickCounter = 1000;
  const fakeSequencer = {
    async getTick() {
      return tickCounter;
    },
    sendEventAt(event, tick, isAbsolute) {
      sentEvents.push({ event, tick, isAbsolute });
    },
    removeAllEvents() {},
  };
  const fakeTimers = makeFakeTimers();
  const scheduler = new BarScheduler({
    sequencer: fakeSequencer,
    keyboard: { setNoteActive() {} },
    tempoBpm: 60,
    leadInSeconds: 0.2,
    now: fakeTimers.now,
    scheduleTimeout: fakeTimers.scheduleTimeout,
  });

  await scheduler.scheduleBar(0, [{ pitch: 60, start_beat: 0, duration_beat: 1, velocity: 100, channel: 0 }]);
  const anchorAfterFirstBar = scheduler.tickAtAnchor;
  assert.equal(anchorAfterFirstBar, 1000 + 200); // leadInSeconds=0.2 => 200ms

  tickCounter = 9999; // if scheduleBar re-read getTick(), the anchor would change
  await scheduler.scheduleBar(1, [{ pitch: 62, start_beat: 0, duration_beat: 1, velocity: 100, channel: 0 }]);
  assert.equal(scheduler.tickAtAnchor, anchorAfterFirstBar);
});

test("BarScheduler schedules a combined note event with the correct channel/key/velocity/duration/tick", async () => {
  const sentEvents = [];
  const fakeSequencer = {
    async getTick() {
      return 0;
    },
    sendEventAt(event, tick, isAbsolute) {
      sentEvents.push({ event, tick, isAbsolute });
    },
    removeAllEvents() {},
  };
  const fakeTimers = makeFakeTimers();
  const scheduler = new BarScheduler({
    sequencer: fakeSequencer,
    keyboard: { setNoteActive() {} },
    tempoBpm: 60,
    leadInSeconds: 0,
    now: fakeTimers.now,
    scheduleTimeout: fakeTimers.scheduleTimeout,
  });

  await scheduler.scheduleBar(0, [{ pitch: 67, start_beat: 2, duration_beat: 0.5, velocity: 90, channel: 1 }]);

  // First two events are the defensive "allsoundsoff" sent on anchor establishment.
  assert.equal(sentEvents.length, 3);
  const noteEvent = sentEvents[2];
  assert.deepEqual(noteEvent.event, { type: "note", channel: 1, key: 67, vel: 90, duration: 498 });
  assert.equal(noteEvent.tick, 2000); // beat 2 at 60 BPM = 2000ms after a zero anchor
  assert.equal(noteEvent.isAbsolute, true);
});

test("BarScheduler defaults visualDelayMs to 0 (no extra delay) when omitted", async () => {
  const scheduledDelays = [];
  const fakeSequencer = {
    async getTick() {
      return 0;
    },
    sendEventAt() {},
    removeAllEvents() {},
  };
  const scheduler = new BarScheduler({
    sequencer: fakeSequencer,
    keyboard: { setNoteActive() {} },
    tempoBpm: 60,
    leadInSeconds: 0,
    now: () => 0,
    scheduleTimeout: (fn, delayMs) => scheduledDelays.push(delayMs),
  });

  await scheduler.scheduleBar(0, [{ pitch: 60, start_beat: 0, duration_beat: 1, velocity: 100, channel: 0 }]);

  assert.deepEqual(scheduledDelays, [0, 1000]);
});

test("BarScheduler.visualDelayMs shifts only the keyboard-highlight setTimeout delays, not the sequencer's tick/duration", async () => {
  const sentEvents = [];
  const scheduledDelays = [];
  const fakeSequencer = {
    async getTick() {
      return 0;
    },
    sendEventAt(event, tick, isAbsolute) {
      sentEvents.push({ event, tick, isAbsolute });
    },
    removeAllEvents() {},
  };
  const scheduler = new BarScheduler({
    sequencer: fakeSequencer,
    keyboard: { setNoteActive() {} },
    tempoBpm: 60,
    leadInSeconds: 0,
    now: () => 0,
    scheduleTimeout: (fn, delayMs) => scheduledDelays.push(delayMs),
    visualDelayMs: 50,
  });

  await scheduler.scheduleBar(0, [{ pitch: 60, start_beat: 0, duration_beat: 1, velocity: 100, channel: 0 }]);

  // Sequencer-side scheduling (audio) is unaffected by visualDelayMs.
  const noteEvent = sentEvents[2];
  assert.equal(noteEvent.tick, 0);
  assert.equal(noteEvent.event.duration, 998);

  // Both the note-on and note-off setTimeout delays are shifted by visualDelayMs.
  assert.deepEqual(scheduledDelays, [50, 1050]);

  // visualDelayMs is a plain mutable property, adjustable live between bars.
  scheduler.visualDelayMs = 200;
  await scheduler.scheduleBar(1, [{ pitch: 62, start_beat: 0, duration_beat: 1, velocity: 100, channel: 0 }]);
  assert.deepEqual(scheduledDelays.slice(2), [4200, 5200]);
});

test("BarScheduler calls removeAllEvents exactly once, when establishing the anchor", async () => {
  let removeAllEventsCallCount = 0;
  const fakeSequencer = {
    async getTick() {
      return 0;
    },
    sendEventAt() {},
    removeAllEvents() {
      removeAllEventsCallCount++;
    },
  };
  const fakeTimers = makeFakeTimers();
  const scheduler = new BarScheduler({
    sequencer: fakeSequencer,
    keyboard: { setNoteActive() {} },
    tempoBpm: 60,
    leadInSeconds: 0,
    now: fakeTimers.now,
    scheduleTimeout: fakeTimers.scheduleTimeout,
  });

  await scheduler.scheduleBar(0, []);
  await scheduler.scheduleBar(1, []);

  assert.equal(removeAllEventsCallCount, 1);
});
