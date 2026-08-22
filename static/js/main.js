import { BEATS_PER_BAR } from "./constants.js";
import { PianoKeyboard } from "./keyboard.js";
import { BarScheduler } from "./scheduler.js";
import { connect } from "./websocket-client.js";
import { createSynthEngine } from "./synth.js";
import { buildMidiFile } from "./midi-writer.js";

const form = document.getElementById("connection-form");
const tempoInput = document.getElementById("tempo-input");
const keyInput = document.getElementById("key-input");
const seedInput = document.getElementById("seed-input");
const modulationToggle = document.getElementById("modulation-toggle");
const startButton = document.getElementById("start-button");
const stopButton = document.getElementById("stop-button");
const reconnectButton = document.getElementById("reconnect-button");
const statusEl = document.getElementById("status");
const tempoDisplay = document.getElementById("tempo-display");
const keyDisplay = document.getElementById("key-display");
const seedDisplay = document.getElementById("seed-display");
const modulationDisplay = document.getElementById("modulation-display");
const downloadButton = document.getElementById("download-button");
const gainInput = document.getElementById("gain-input");
const visualDelayInput = document.getElementById("visual-delay-input");
const visualDelayDisplay = document.getElementById("visual-delay-display");
const canvas = document.getElementById("keyboard-canvas");

const keyboard = new PianoKeyboard(canvas);

let audioContext = null;
let gainNode = null;
let synthEngine = null; // { synth, sequencer }; created once and reused across sessions
let scheduler = null;
let ws = null;
let noteBuffer = [];
let sessionTempoBpm = null;
let stoppedByUser = false;
let sessionGeneration = 0;
let errorAlreadyShown = false;
let modulationEnabled = true;

function setStatus(text) {
  statusEl.textContent = text;
}

function setFormEnabled(enabled) {
  tempoInput.disabled = !enabled;
  keyInput.disabled = !enabled;
  seedInput.disabled = !enabled;
  modulationToggle.disabled = !enabled;
  startButton.disabled = !enabled;
}

async function ensureSynthEngine() {
  if (!audioContext) {
    audioContext = new AudioContext();
    gainNode = audioContext.createGain();
    gainNode.gain.value = Number(gainInput.value);
    gainNode.connect(audioContext.destination);
  }
  await audioContext.resume();
  if (!synthEngine) {
    synthEngine = await createSynthEngine(audioContext, gainNode);
  }
  return synthEngine;
}

async function startSession() {
  stoppedByUser = false;
  errorAlreadyShown = false;
  const myGeneration = ++sessionGeneration;
  reconnectButton.hidden = true;
  setFormEnabled(false);
  stopButton.disabled = false;
  downloadButton.disabled = true;
  noteBuffer = [];
  sessionTempoBpm = null;
  keyboard.reset();
  setStatus("音源を読み込み中…");

  let engine;
  try {
    engine = await ensureSynthEngine();
  } catch (error) {
    console.error("failed to initialize synth engine", error);
    if (myGeneration !== sessionGeneration) return;
    setStatus(`エラー: 音源の初期化に失敗しました (${error.message})`);
    setFormEnabled(true);
    stopButton.disabled = true;
    return;
  }
  if (myGeneration !== sessionGeneration) return; // Stop (or a newer Start) happened while we were awaiting
  scheduler = null; // created once session_start confirms the tempo

  setStatus("接続中…");
  ws = connect({
    tempo: tempoInput.value,
    key: keyInput.value,
    seed: seedInput.value,
    modulation: modulationEnabled,
    onSessionStart: (message) => {
      sessionTempoBpm = message.tempo_bpm;
      scheduler = new BarScheduler({
        sequencer: engine.sequencer,
        keyboard,
        tempoBpm: message.tempo_bpm,
        visualDelayMs: Number(visualDelayInput.value),
      });
      tempoDisplay.textContent = message.tempo_bpm;
      keyDisplay.textContent = message.key;
      seedDisplay.textContent = message.seed;
      modulationDisplay.textContent = message.modulation ? "ON" : "OFF";
      setStatus("再生中");
    },
    onBar: (message) => {
      keyDisplay.textContent = message.key;
      for (const note of message.notes) {
        noteBuffer.push({
          absoluteStartBeat: message.bar_index * BEATS_PER_BAR + note.start_beat,
          durationBeat: note.duration_beat,
          velocity: note.velocity,
          channel: note.channel,
          pitch: note.pitch,
        });
      }
      downloadButton.disabled = noteBuffer.length === 0;
      if (scheduler) {
        scheduler.scheduleBar(message.bar_index, message.notes).catch((error) => {
          console.error("failed to schedule bar", error);
        });
      }
    },
    onError: (message) => {
      errorAlreadyShown = true;
      setStatus(`エラー: ${message.message}`);
      setFormEnabled(true);
      stopButton.disabled = true;
      reconnectButton.hidden = true;
    },
    onClose: () => {
      if (!stoppedByUser && !errorAlreadyShown) {
        setStatus("切断されました");
        reconnectButton.hidden = false;
      }
      setFormEnabled(true);
      stopButton.disabled = true;
    },
  });
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  startSession();
});

stopButton.addEventListener("click", () => {
  stoppedByUser = true;
  sessionGeneration++;
  setStatus("停止");
  if (ws) ws.close();
  ws = null;
  setFormEnabled(true);
  stopButton.disabled = true;
});

reconnectButton.addEventListener("click", () => {
  startSession();
});

modulationToggle.addEventListener("click", () => {
  modulationEnabled = !modulationEnabled;
  modulationToggle.textContent = `転調: ${modulationEnabled ? "ON" : "OFF"}`;
  modulationToggle.setAttribute("aria-pressed", String(modulationEnabled));
});

gainInput.addEventListener("input", () => {
  if (gainNode) gainNode.gain.value = Number(gainInput.value);
});

visualDelayInput.addEventListener("input", () => {
  visualDelayDisplay.textContent = visualDelayInput.value;
  if (scheduler) scheduler.visualDelayMs = Number(visualDelayInput.value);
});

downloadButton.addEventListener("click", () => {
  const bytes = buildMidiFile(noteBuffer, sessionTempoBpm ?? 160);
  const blob = new Blob([bytes], { type: "audio/midi" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "zunish.mid";
  link.click();
  URL.revokeObjectURL(url);
});
