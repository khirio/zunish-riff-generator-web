import { BEATS_PER_BAR } from "./constants.js";

export function computeTargetTick(tickAtAnchor, tempoBpm, barIndex, startBeat) {
  const secondsPerBeat = 60 / tempoBpm;
  return tickAtAnchor + (barIndex * BEATS_PER_BAR + startBeat) * secondsPerBeat * 1000;
}

export function computeDurationMs(tempoBpm, durationBeat) {
  const secondsPerBeat = 60 / tempoBpm;
  return durationBeat * secondsPerBeat * 1000;
}

export function computeSetTimeoutDelayMs(targetTick, tickAtAnchor, wallClockAtAnchorMs, nowMs) {
  return Math.max(0, wallClockAtAnchorMs + (targetTick - tickAtAnchor) - nowMs);
}

/**
 * Schedules a bar's notes onto a js-synthesizer ISequencer (sample-accurate
 * audio timing) and, in parallel, onto setTimeout (millisecond-accurate
 * visual keyboard highlighting). See WEB_DESIGN.md 8.3.
 */
export class BarScheduler {
  constructor({
    sequencer,
    keyboard,
    tempoBpm,
    leadInSeconds = 0.3,
    now = () => performance.now(),
    scheduleTimeout = (fn, delayMs) => setTimeout(fn, delayMs),
    visualDelayMs = 0,
  }) {
    this.sequencer = sequencer;
    this.keyboard = keyboard;
    this.tempoBpm = tempoBpm;
    this.leadInSeconds = leadInSeconds;
    this.now = now;
    this.scheduleTimeout = scheduleTimeout;
    // Extra delay applied only to the keyboard-highlight setTimeout calls, to
    // compensate for audio output's inherent hardware/buffering latency
    // (which the setTimeout-scheduled visual has no equivalent of). A plain
    // mutable property so the UI can adjust it live while playing.
    this.visualDelayMs = visualDelayMs;
    this.tickAtAnchor = null;
    this.wallClockAtAnchorMs = null;
  }

  async scheduleBar(barIndex, notes) {
    if (this.tickAtAnchor === null) {
      this.sequencer.removeAllEvents();
      const currentTick = await this.sequencer.getTick();
      // Defensive: silence anything still sounding from a previous session
      // before removeAllEvents() drops its pending note-offs.
      this.sequencer.sendEventAt({ type: "allsoundsoff", channel: 0 }, currentTick, true);
      this.sequencer.sendEventAt({ type: "allsoundsoff", channel: 1 }, currentTick, true);
      this.tickAtAnchor = currentTick + this.leadInSeconds * 1000;
      this.wallClockAtAnchorMs = this.now();
    }
    for (const note of notes) {
      const targetTick = computeTargetTick(this.tickAtAnchor, this.tempoBpm, barIndex, note.start_beat);
      const durationMs = computeDurationMs(this.tempoBpm, note.duration_beat);
      const sequencerDurationMs = Math.max(1, durationMs - 2);
      this.sequencer.sendEventAt(
        { type: "note", channel: note.channel, key: note.pitch, vel: note.velocity, duration: sequencerDurationMs },
        targetTick,
        true
      );

      const onDelay =
        computeSetTimeoutDelayMs(targetTick, this.tickAtAnchor, this.wallClockAtAnchorMs, this.now()) +
        this.visualDelayMs;
      const offDelay =
        computeSetTimeoutDelayMs(
          targetTick + durationMs,
          this.tickAtAnchor,
          this.wallClockAtAnchorMs,
          this.now()
        ) + this.visualDelayMs;
      this.scheduleTimeout(() => this.keyboard.setNoteActive(note.pitch, note.channel, true), onDelay);
      this.scheduleTimeout(() => this.keyboard.setNoteActive(note.pitch, note.channel, false), offDelay);
    }
  }
}
