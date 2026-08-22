# フロントエンド実装 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `WEB_DESIGN.md` 8章の設計に沿って、生成された小節を再生するブラウザ向けフロントエンド（Canvas鍵盤、js-synthesizerによる音声合成、絶対時刻スケジューリング、MIDIエクスポート）を実装する。

**Architecture:** ビルドステップなしのVanilla JS（ES Modules）で`static/`配下に実装する。ロジックを「純粋関数（Node.jsの組み込みテストランナーで単体テスト可能）」と「DOM/AudioContext/WebSocketに依存する薄い配線コード（ブラウザで手動確認）」に分離する。バックエンド側は`src/zunish/server.py`に静的ファイル配信のマウントを2つ追加するのみ（`/ws`エンドポイント自体は変更しない）。

**Tech Stack:** Vanilla JS（ES Modules、ビルドツールなし）、Node.js組み込みテストランナー（`node --test`、npm依存ゼロ）、js-synthesizer 1.13.0（FluidSynthのWebAssembly版、ベンダーイン）、既存のPython/FastAPI/pytest。

**Spec:** `WEB_DESIGN.md`（8章 フロントエンド設計）

## Global Constraints

- ビルドステップは導入しない。JSは`<script type="module">`で読み込むES Modulesとして書く。npmパッケージは一切インストールしない（依存ゼロ）。
- 純粋ロジック（DOM/AudioContext/WebSocket/Canvasに依存しない関数）はNode.js組み込みテストランナー（`node --test`）で単体テストする。テスト対象にするためリポジトリルートに`package.json`（`{"type": "module", "private": true}`のみ）を追加する。
- DOM操作・`AudioContext`・`WebSocket`・Canvas描画そのものに依存するコードは自動テスト対象外とし、各タスクの手動確認手順（ブラウザで実際に動かして確認）で検証する。
- `BEATS_PER_BAR = 4.0`（`zunish.theory.BEATS_PER_BAR`と同じ値）、`TICKS_PER_BEAT = 480`（`zunish.midi_export.TICKS_PER_BEAT`と同じ値）をJS側の定数として持つ。
- js-synthesizerは**バージョン1.13.0**を`https://cdn.jsdelivr.net/npm/js-synthesizer@1.13.0/`から取得し、`static/vendor/`に同梱する（外部CDN読み込みはしない）。`.sf3`（同梱サウンドフォントの形式）対応のため、`libfluidsynth-2.4.6-with-libsndfile.js`（`.wasm`バイナリをbase64で内包した単一ファイル、別途`.wasm`ファイルは存在しない）を使う。
- サウンドフォント（`assets/soundfonts/FluidR3Mono_GM.sf3`、23.7MB）は`static/`へコピーしない。既存の`assets/soundfonts/`を`/soundfonts`パスで直接マウントして配信する。
- js-synthesizerの実際のスケジューリングAPIは`ISequencer.sendEventAt(event, tick, isAbsolute)`（tickの既定タイムスケールは1 tick = 1ミリ秒）を使う。`ISynthesizer.midiNoteOn`/`midiNoteOff`は即時実行のみで時刻指定できないため使わない。
- 既存の`src/zunish/cli.py`・`player.py`・`gui.py`・`midi_export.py`・それらのテストは変更しない。
- 各タスク完了時点で、変更した言語のテスト（Python: `uv run pytest`、JS: `node --test`）がすべてグリーンであること。

---

### Task 1: 静的ファイル配信基盤

**Files:**
- Modify: `src/zunish/server.py`
- Create: `static/index.html`
- Test: `tests/test_server.py`

**Interfaces:**
- Produces: `zunish.server.REPO_ROOT: Path`（リポジトリルート）。`app`に`/soundfonts`と`/`の2つの`StaticFiles`マウントが追加される。

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_server.py`の先頭のimportブロックに`from pathlib import Path`を追加し（既存のimportの後、`from fastapi import ...`より前に）、`from zunish.server import app`を`from zunish.server import REPO_ROOT, app`に変更する。

ファイル末尾に追記:

```python
def test_static_root_serves_index_html():
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    assert "zunish" in response.text.lower()


def test_soundfont_is_served_directly_from_assets_without_copying():
    client = TestClient(app)
    response = client.get("/soundfonts/FluidR3Mono_GM.sf3")
    assert response.status_code == 200
    expected_size = (REPO_ROOT / "assets" / "soundfonts" / "FluidR3Mono_GM.sf3").stat().st_size
    assert response.headers["content-length"] == str(expected_size)
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `uv run pytest tests/test_server.py -k "static_root or soundfont_is_served" -v`
Expected: FAIL — `ImportError: cannot import name 'REPO_ROOT' from 'zunish.server'`

- [ ] **Step 3: 実装**

`src/zunish/server.py`のimportブロックを以下に置き換える（既存の`stream_bars`/`run_until_disconnected`/`websocket_endpoint`の本体はそのまま残す）:

```python
"""FastAPI WebSocket server implementing the protocol described in
WEB_DESIGN.md section 6."""

from __future__ import annotations

import asyncio
import random
import time
from collections.abc import Awaitable, Callable, Iterator
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from zunish.director import Director
from zunish.generator import NoteEvent
from zunish.theory import BEATS_PER_BAR
from zunish.ws_protocol import (
    InvalidSessionConfig,
    build_bar_message,
    build_error_message,
    build_session_start_message,
    parse_session_config,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

app = FastAPI()
```

ファイル末尾（`websocket_endpoint`関数の後）に追加:

```python
app.mount("/soundfonts", StaticFiles(directory=REPO_ROOT / "assets" / "soundfonts"), name="soundfonts")
app.mount("/", StaticFiles(directory=REPO_ROOT / "static", html=True), name="static")
```

`static/index.html`を新規作成（後続タスクで内容を差し替える最小限のプレースホルダー）:

```html
<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<title>zunish web</title>
</head>
<body>
<p>zunish riff generator (Web版) - 準備中</p>
</body>
</html>
```

- [ ] **Step 4: テストが通ることを確認し、全体のテストも流す**

Run: `uv run pytest tests/test_server.py -v`
Expected: すべてPASS

Run: `uv run pytest`
Expected: すべてPASS

- [ ] **Step 5: コミット**

```bash
git add src/zunish/server.py static/index.html tests/test_server.py
git commit -m "静的ファイル配信(/とサウンドフォント/soundfonts)のマウントを追加"
```

---

### Task 2: `constants.js` + `midi-writer.js`

**Files:**
- Create: `package.json`
- Create: `static/js/constants.js`
- Create: `static/js/midi-writer.js`
- Test: `tests/js/midi-writer.test.js`

**Interfaces:**
- Produces: `constants.js`が`BEATS_PER_BAR`, `TICKS_PER_BEAT`, `KEY_LOW`, `KEY_HIGH`, `WHITE_PCS`, `WHITE_INDEX_IN_OCTAVE`, `BLACK_OFFSET_IN_OCTAVE`, `WHITE_KEY_WIDTH`, `WHITE_KEY_HEIGHT`, `BLACK_KEY_WIDTH`, `BLACK_KEY_HEIGHT`, `DEFAULT_WHITE_FILL`, `DEFAULT_BLACK_FILL`, `CHANNEL_COLORS`, `FALLBACK_ACTIVE_FILL`をexport（Task 3で使用）。`midi-writer.js`が`encodeVariableLength(value: number): number[]`と`buildMidiFile(notes: {absoluteStartBeat, durationBeat, velocity, channel, pitch}[], tempoBpm: number): Uint8Array`をexport（Task 7で使用）。

- [ ] **Step 1: リポジトリルートに`package.json`を作成**

```json
{
  "name": "zunish-web-frontend",
  "private": true,
  "type": "module"
}
```

- [ ] **Step 2: 失敗するテストを書く**

`tests/js/midi-writer.test.js`を新規作成:

```javascript
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

function indexOfSubsequence(haystack, needle) {
  for (let i = 0; i <= haystack.length - needle.length; i++) {
    if (needle.every((value, offset) => haystack[i + offset] === value)) return i;
  }
  return -1;
}
```

- [ ] **Step 3: テストが失敗することを確認**

Run: `node --test`
Expected: FAIL — `Cannot find module '.../static/js/midi-writer.js'`

- [ ] **Step 4: `static/js/constants.js`を実装**

```javascript
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
```

- [ ] **Step 5: `static/js/midi-writer.js`を実装**

```javascript
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
  bytes.push(...track);

  return new Uint8Array(bytes);
}
```

- [ ] **Step 6: テストが通ることを確認**

Run: `node --test`
Expected: すべてPASS

- [ ] **Step 7: コミット**

```bash
git add package.json static/js/constants.js static/js/midi-writer.js tests/js/midi-writer.test.js
git commit -m "共有定数(constants.js)と自前MIDI書き出し(midi-writer.js)を追加"
```

---

### Task 3: `keyboard.js`（Canvas鍵盤描画、`gui.py`の移植）

**Files:**
- Create: `static/js/keyboard.js`
- Test: `tests/js/keyboard.test.js`

**Interfaces:**
- Consumes: `constants.js`の鍵盤レイアウト定数（Task 2）。
- Produces: `buildKeyLayout(): {keys, keysByPitch, canvasWidth, canvasHeight}`、`colorForActiveChannels(channels: Set<number>): string | null`、`fillColorForKey(key, activeChannels): string`（すべて純粋関数、テスト対象）。`PianoKeyboard`クラス（`constructor(canvas)`, `setNoteActive(pitch, channel, isOn)`, `reset()`）と`drawKeyboard(ctx, layout)`/`drawKey(ctx, key, activeChannels)`（Canvas描画、ブラウザでのみ動作）。Task 7で`PianoKeyboard`を使う。

- [ ] **Step 1: 失敗するテストを書く**

`tests/js/keyboard.test.js`を新規作成:

```javascript
import { test } from "node:test";
import assert from "node:assert/strict";
import { KEY_LOW, KEY_HIGH } from "../../static/js/constants.js";
import { buildKeyLayout, colorForActiveChannels, fillColorForKey } from "../../static/js/keyboard.js";

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
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `node --test`
Expected: FAIL — `Cannot find module '.../static/js/keyboard.js'`

- [ ] **Step 3: 実装**

`static/js/keyboard.js`を新規作成:

```javascript
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

/** Live piano keyboard bound to a <canvas>. Mirrors gui.py's PianoGUI keyboard drawing. */
export class PianoKeyboard {
  constructor(canvas) {
    this.layout = buildKeyLayout();
    this.ctx = canvas.getContext("2d");
    this.activeByPitch = new Map();
    canvas.width = this.layout.canvasWidth;
    canvas.height = this.layout.canvasHeight;
    canvas.style.background = "#555555";
    drawKeyboard(this.ctx, this.layout);
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
    drawKey(this.ctx, key, channels);
  }

  reset() {
    this.activeByPitch.clear();
    drawKeyboard(this.ctx, this.layout);
  }
}
```

- [ ] **Step 4: テストが通ることを確認**

Run: `node --test`
Expected: すべてPASS

- [ ] **Step 5: コミット**

```bash
git add static/js/keyboard.js tests/js/keyboard.test.js
git commit -m "Canvas鍵盤描画(keyboard.js)を追加(gui.pyの移植)"
```

---

### Task 4: `scheduler.js`（絶対時刻/tickベースのスケジューリング）

**Files:**
- Create: `static/js/scheduler.js`
- Test: `tests/js/scheduler.test.js`

**Interfaces:**
- Consumes: `BEATS_PER_BAR`（Task 2）、`PianoKeyboard`（Task 3、`setNoteActive`メソッドのみ使用）。
- Produces: `computeTargetTick(tickAtAnchor, tempoBpm, barIndex, startBeat): number`、`computeDurationMs(tempoBpm, durationBeat): number`、`computeSetTimeoutDelayMs(targetTick, tickAtAnchor, wallClockAtAnchorMs, nowMs): number`（すべて純粋関数、テスト対象）。`BarScheduler`クラス（`constructor({sequencer, keyboard, tempoBpm, leadInSeconds})`, `async scheduleBar(barIndex, notes)`）。Task 7で使用。`sequencer`は`{getTick(): Promise<number>, sendEventAt(event, tick, isAbsolute): void, removeAllEvents(): void}`を満たすオブジェクト（js-synthesizerの`ISequencer`、Task 6で生成）。

- [ ] **Step 1: 失敗するテストを書く**

`tests/js/scheduler.test.js`を新規作成:

```javascript
import { test } from "node:test";
import assert from "node:assert/strict";
import { computeTargetTick, computeDurationMs, computeSetTimeoutDelayMs, BarScheduler } from "../../static/js/scheduler.js";

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
  const scheduler = new BarScheduler({ sequencer: fakeSequencer, keyboard: { setNoteActive() {} }, tempoBpm: 60, leadInSeconds: 0.2 });

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
  const scheduler = new BarScheduler({ sequencer: fakeSequencer, keyboard: { setNoteActive() {} }, tempoBpm: 60, leadInSeconds: 0 });

  await scheduler.scheduleBar(0, [{ pitch: 67, start_beat: 2, duration_beat: 0.5, velocity: 90, channel: 1 }]);

  assert.equal(sentEvents.length, 1);
  assert.deepEqual(sentEvents[0].event, { type: "note", channel: 1, key: 67, vel: 90, duration: 500 });
  assert.equal(sentEvents[0].tick, 2000); // beat 2 at 60 BPM = 2000ms after a zero anchor
  assert.equal(sentEvents[0].isAbsolute, true);
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
  const scheduler = new BarScheduler({ sequencer: fakeSequencer, keyboard: { setNoteActive() {} }, tempoBpm: 60, leadInSeconds: 0 });

  await scheduler.scheduleBar(0, []);
  await scheduler.scheduleBar(1, []);

  assert.equal(removeAllEventsCallCount, 1);
});
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `node --test`
Expected: FAIL — `Cannot find module '.../static/js/scheduler.js'`

- [ ] **Step 3: 実装**

`static/js/scheduler.js`を新規作成:

```javascript
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
  constructor({ sequencer, keyboard, tempoBpm, leadInSeconds = 0.3 }) {
    this.sequencer = sequencer;
    this.keyboard = keyboard;
    this.tempoBpm = tempoBpm;
    this.leadInSeconds = leadInSeconds;
    this.tickAtAnchor = null;
    this.wallClockAtAnchorMs = null;
  }

  async scheduleBar(barIndex, notes) {
    if (this.tickAtAnchor === null) {
      this.sequencer.removeAllEvents();
      this.tickAtAnchor = (await this.sequencer.getTick()) + this.leadInSeconds * 1000;
      this.wallClockAtAnchorMs = performance.now();
    }
    for (const note of notes) {
      const targetTick = computeTargetTick(this.tickAtAnchor, this.tempoBpm, barIndex, note.start_beat);
      const durationMs = computeDurationMs(this.tempoBpm, note.duration_beat);
      this.sequencer.sendEventAt(
        { type: "note", channel: note.channel, key: note.pitch, vel: note.velocity, duration: durationMs },
        targetTick,
        true
      );

      const onDelay = computeSetTimeoutDelayMs(targetTick, this.tickAtAnchor, this.wallClockAtAnchorMs, performance.now());
      const offDelay = computeSetTimeoutDelayMs(
        targetTick + durationMs,
        this.tickAtAnchor,
        this.wallClockAtAnchorMs,
        performance.now()
      );
      setTimeout(() => this.keyboard.setNoteActive(note.pitch, note.channel, true), onDelay);
      setTimeout(() => this.keyboard.setNoteActive(note.pitch, note.channel, false), offDelay);
    }
  }
}
```

- [ ] **Step 4: テストが通ることを確認**

Run: `node --test`
Expected: すべてPASS

- [ ] **Step 5: コミット**

```bash
git add static/js/scheduler.js tests/js/scheduler.test.js
git commit -m "絶対tickベースの音符スケジューリング(scheduler.js)を追加"
```

---

### Task 5: `websocket-client.js`

**Files:**
- Create: `static/js/websocket-client.js`
- Test: `tests/js/websocket-client.test.js`

**Interfaces:**
- Produces: `parseServerMessage(raw: string): object`（純粋関数、不正な入力は`Error`を投げる、テスト対象）。`connect({tempo, key, seed, onSessionStart, onBar, onError, onClose}): WebSocket`（ブラウザでのみ動作、`WebSocket`と`location`に依存）。Task 7で`connect`を使う。

- [ ] **Step 1: 失敗するテストを書く**

`tests/js/websocket-client.test.js`を新規作成:

```javascript
import { test } from "node:test";
import assert from "node:assert/strict";
import { parseServerMessage } from "../../static/js/websocket-client.js";

test("parseServerMessage accepts a well-formed session_start message", () => {
  const message = parseServerMessage(JSON.stringify({ type: "session_start", tempo_bpm: 160, key: "A", seed: 42 }));
  assert.deepEqual(message, { type: "session_start", tempo_bpm: 160, key: "A", seed: 42 });
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
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `node --test`
Expected: FAIL — `Cannot find module '.../static/js/websocket-client.js'`

- [ ] **Step 3: 実装**

`static/js/websocket-client.js`を新規作成:

```javascript
/**
 * Parse and validate one raw WebSocket text frame from the server, per the
 * protocol in WEB_DESIGN.md section 6.3. Throws on anything malformed or
 * unrecognized.
 */
export function parseServerMessage(raw) {
  let data;
  try {
    data = JSON.parse(raw);
  } catch {
    throw new Error(`invalid JSON from server: ${raw}`);
  }

  if (
    data &&
    data.type === "session_start" &&
    typeof data.tempo_bpm === "number" &&
    typeof data.key === "string" &&
    typeof data.seed === "number"
  ) {
    return data;
  }
  if (
    data &&
    data.type === "bar" &&
    typeof data.bar_index === "number" &&
    typeof data.key === "string" &&
    Array.isArray(data.notes)
  ) {
    return data;
  }
  if (data && data.type === "error" && typeof data.message === "string") {
    return data;
  }
  throw new Error(`unrecognized server message: ${raw}`);
}

/**
 * Open a WebSocket connection to /ws with the given (optional) query
 * parameters, dispatching parsed messages to the given callbacks. A parse
 * failure for one message is logged and skipped rather than closing the
 * connection (WEB_DESIGN.md doesn't specify this case; failing open on a
 * single bad frame is safer than tearing down an otherwise-healthy session).
 */
export function connect({ tempo, key, seed, onSessionStart, onBar, onError, onClose }) {
  const params = new URLSearchParams();
  if (tempo) params.set("tempo", tempo);
  if (key) params.set("key", key);
  if (seed) params.set("seed", seed);
  const protocol = location.protocol === "https:" ? "wss:" : "ws:";
  const query = params.toString();
  const url = `${protocol}//${location.host}/ws${query ? "?" + query : ""}`;

  const ws = new WebSocket(url);
  ws.addEventListener("message", (event) => {
    let message;
    try {
      message = parseServerMessage(event.data);
    } catch (error) {
      console.error(error);
      return;
    }
    if (message.type === "session_start") onSessionStart(message);
    else if (message.type === "bar") onBar(message);
    else if (message.type === "error") onError(message);
  });
  ws.addEventListener("close", onClose);
  return ws;
}
```

- [ ] **Step 4: テストが通ることを確認**

Run: `node --test`
Expected: すべてPASS

- [ ] **Step 5: コミット**

```bash
git add static/js/websocket-client.js tests/js/websocket-client.test.js
git commit -m "/ws接続とメッセージパース(websocket-client.js)を追加"
```

---

### Task 6: `synth.js`（js-synthesizerの導入・初期化）

**Files:**
- Create: `static/vendor/js-synthesizer.js`（ダウンロード）
- Create: `static/vendor/libfluidsynth-2.4.6-with-libsndfile.js`（ダウンロード）
- Create: `static/vendor/LICENSE.js-synthesizer.txt`（ダウンロード）
- Create: `static/vendor/LICENSE.fluidsynth.txt`（ダウンロード）
- Create: `static/js/synth.js`
- Modify: `THIRD_PARTY_NOTICES.md`

**Interfaces:**
- Produces: `createSynthEngine(audioContext, outputNode): Promise<{synth, sequencer}>`（ブラウザでのみ動作。`sequencer`はTask 4の`BarScheduler`が要求する`{getTick, sendEventAt, removeAllEvents}`を満たす）。Task 7で使用。

このタスクに自動テストはない（js-synthesizerの初期化はAudioContext・WebAssembly・ネットワーク越しのファイル取得に依存し、Node.js上で意味のある形で再現できないため）。ブラウザでの手動確認で検証する。

- [ ] **Step 1: vendorファイルをダウンロード**

```bash
mkdir -p static/vendor
curl -sL -o static/vendor/js-synthesizer.js "https://cdn.jsdelivr.net/npm/js-synthesizer@1.13.0/dist/js-synthesizer.js"
curl -sL -o static/vendor/libfluidsynth-2.4.6-with-libsndfile.js "https://cdn.jsdelivr.net/npm/js-synthesizer@1.13.0/externals/libfluidsynth-2.4.6-with-libsndfile.js"
curl -sL -o static/vendor/LICENSE.js-synthesizer.txt "https://raw.githubusercontent.com/jet2jet/js-synthesizer/v1.13.0/LICENSE"
curl -sL -o static/vendor/LICENSE.fluidsynth.txt "https://raw.githubusercontent.com/jet2jet/js-synthesizer/v1.13.0/externals/LICENSE.fluidsynth.txt"
```

ダウンロード後、ファイルサイズを確認する（壊れたダウンロードでないことの目視確認）:

Run: `ls -la static/vendor/`
Expected: `js-synthesizer.js`が約82KB、`libfluidsynth-2.4.6-with-libsndfile.js`が約2.3MB、2つのLICENSEファイルがそれぞれ数KB程度であること。

- [ ] **Step 2: `THIRD_PARTY_NOTICES.md`にライセンス表記を追加**

ファイル末尾に追記:

```markdown

## `static/vendor/js-synthesizer.js`（BSD 3-Clause License）

[js-synthesizer](https://github.com/jet2jet/js-synthesizer) 1.13.0（`dist/js-synthesizer.js`）を、フロントエンドでのブラウザ内音声合成のために同梱しています。

```
Copyright (C) 2018 jet
All rights reserved.
```

ライセンス全文は [static/vendor/LICENSE.js-synthesizer.txt](static/vendor/LICENSE.js-synthesizer.txt) を参照してください。

## `static/vendor/libfluidsynth-2.4.6-with-libsndfile.js`（GNU Lesser General Public License v2.1）

[js-synthesizer](https://github.com/jet2jet/js-synthesizer) が配布する [fluidsynth-emscripten](https://github.com/jet2jet/fluidsynth-emscripten)（FluidSynthをWebAssemblyへ移植したもの、`.sf3`読み込みのため`libsndfile`込みでビルドされた版）を同梱しています。FluidSynth本体およびfluidsynth-emscriptenはGNU Lesser General Public License v2.1の下で配布されています。

ライセンス全文は [static/vendor/LICENSE.fluidsynth.txt](static/vendor/LICENSE.fluidsynth.txt) を参照してください。ソースコードは [fluidsynth-emscripten](https://github.com/jet2jet/fluidsynth-emscripten) および [js-synthesizer](https://github.com/jet2jet/js-synthesizer) のリポジトリで公開されています。
```

- [ ] **Step 3: `static/js/synth.js`を実装**

```javascript
const SOUNDFONT_URL = "/soundfonts/FluidR3Mono_GM.sf3";
const RENDER_BUFFER_FRAMES = 8192;

let scriptsLoadedPromise = null;

function loadScript(src) {
  return new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = src;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error(`failed to load script: ${src}`));
    document.head.appendChild(script);
  });
}

function ensureScriptsLoaded() {
  if (!scriptsLoadedPromise) {
    scriptsLoadedPromise = loadScript("vendor/libfluidsynth-2.4.6-with-libsndfile.js")
      .then(() => loadScript("vendor/js-synthesizer.js"))
      .then(() => window.JSSynth.waitForReady());
  }
  return scriptsLoadedPromise;
}

/**
 * Create (once per page load) a js-synthesizer Synthesizer + Sequencer pair,
 * loaded with the bundled soundfont and connected to `outputNode`. See
 * WEB_DESIGN.md 8.1/8.3 for why the ScriptProcessorNode-based `Synthesizer`
 * (not `AudioWorkletNodeSynthesizer`) and the tick-based `ISequencer` are
 * used.
 */
export async function createSynthEngine(audioContext, outputNode) {
  await ensureScriptsLoaded();
  const JSSynth = window.JSSynth;

  const synth = new JSSynth.Synthesizer();
  synth.init(audioContext.sampleRate);
  const node = synth.createAudioNode(audioContext, RENDER_BUFFER_FRAMES);
  node.connect(outputNode);

  const soundfontResponse = await fetch(SOUNDFONT_URL);
  const soundfontBuffer = await soundfontResponse.arrayBuffer();
  await synth.loadSFont(soundfontBuffer);

  const sequencer = await JSSynth.Synthesizer.createSequencer();
  await sequencer.registerSynthesizer(synth);

  return { synth, sequencer };
}
```

- [ ] **Step 4: 手動確認**

ブラウザ検証用の最小限の一時HTMLを用意し、動作を目視・耳で確認する（`static/index.html`本体の統合はTask 7で行うため、ここでは検証専用の一時ファイルを使い、確認後に削除する）。

`static/_manual_test_synth.html`を一時的に作成:

```html
<!doctype html>
<html><head><meta charset="utf-8"><title>synth.js manual test</title></head>
<body>
<button id="play">Cで1音鳴らす</button>
<script type="module">
  import { createSynthEngine } from "./js/synth.js";
  document.getElementById("play").addEventListener("click", async () => {
    const ctx = new AudioContext();
    await ctx.resume();
    const gain = ctx.createGain();
    gain.connect(ctx.destination);
    const { sequencer } = await createSynthEngine(ctx, gain);
    const tick = await sequencer.getTick();
    sequencer.sendEventAt({ type: "note", channel: 0, key: 60, vel: 100, duration: 1000 }, tick, true);
  });
</script>
</body></html>
```

Run: `uv run uvicorn zunish.server:app --reload`（別ターミナルで起動）してから、ブラウザで`http://localhost:8000/_manual_test_synth.html`を開き、「Cで1音鳴らす」を押す。

Expected: ピアノのC4の音が1秒間鳴る。ブラウザの開発者コンソールにエラーが出ていないことも確認する。

確認後、一時ファイルを削除する:

```bash
rm static/_manual_test_synth.html
```

- [ ] **Step 5: コミット**

```bash
git add static/vendor/ static/js/synth.js THIRD_PARTY_NOTICES.md
git commit -m "js-synthesizerを導入し音声合成の初期化(synth.js)を追加"
```

---

### Task 7: `index.html` + `style.css` + `main.js`（統合）

**Files:**
- Modify: `static/index.html`
- Create: `static/css/style.css`
- Create: `static/js/main.js`

**Interfaces:**
- Consumes: `BEATS_PER_BAR`（Task 2）、`buildMidiFile`（Task 2）、`PianoKeyboard`（Task 3）、`BarScheduler`（Task 4）、`connect`（Task 5）、`createSynthEngine`（Task 6）。

このタスクに自動テストはない（DOM配線・ユーザー操作の統合であり、Node.js上で意味のある形で再現できないため）。ブラウザでの手動確認がこのタスクの検証手段そのものである。

- [ ] **Step 1: `static/index.html`を最終版に差し替え**

Task 1で作成したプレースホルダーを、以下の内容に置き換える:

```html
<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<title>zunish web</title>
<link rel="stylesheet" href="css/style.css">
</head>
<body>
<h1>zunish riff generator (Web版)</h1>

<form id="connection-form">
  <label>Tempo (BPM) <input type="number" id="tempo-input" min="20" max="400" step="1" placeholder="160"></label>
  <label>Key <input type="text" id="key-input" placeholder="A"></label>
  <label>Seed <input type="number" id="seed-input" placeholder="(random)"></label>
  <button type="submit" id="start-button">開始</button>
  <button type="button" id="stop-button" disabled>停止</button>
  <button type="button" id="reconnect-button" hidden>再接続</button>
</form>

<p id="status">未接続</p>
<p>Tempo: <span id="tempo-display">-</span> BPM / Key: <span id="key-display">-</span>m / Seed: <span id="seed-display">-</span></p>

<canvas id="keyboard-canvas"></canvas>

<p>
  <label>音量 <input type="range" id="gain-input" min="0" max="2" step="0.01" value="1"></label>
  <button type="button" id="download-button" disabled>MIDIをダウンロード</button>
</p>

<script type="module" src="js/main.js"></script>
</body>
</html>
```

- [ ] **Step 2: `static/css/style.css`を作成**

```css
body {
  font-family: system-ui, sans-serif;
  max-width: 640px;
  margin: 2rem auto;
  padding: 0 1rem;
}

form {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
  align-items: end;
  margin-bottom: 1rem;
}

label {
  display: flex;
  flex-direction: column;
  font-size: 0.85rem;
}

input[type="number"],
input[type="text"] {
  width: 6rem;
}

#status {
  font-weight: bold;
}

#keyboard-canvas {
  display: block;
  margin: 1rem 0;
  border: 1px solid #333;
}
```

- [ ] **Step 3: `static/js/main.js`を実装**

```javascript
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
const startButton = document.getElementById("start-button");
const stopButton = document.getElementById("stop-button");
const reconnectButton = document.getElementById("reconnect-button");
const statusEl = document.getElementById("status");
const tempoDisplay = document.getElementById("tempo-display");
const keyDisplay = document.getElementById("key-display");
const seedDisplay = document.getElementById("seed-display");
const downloadButton = document.getElementById("download-button");
const gainInput = document.getElementById("gain-input");
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

function setStatus(text) {
  statusEl.textContent = text;
}

function setFormEnabled(enabled) {
  tempoInput.disabled = !enabled;
  keyInput.disabled = !enabled;
  seedInput.disabled = !enabled;
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
  reconnectButton.hidden = true;
  setFormEnabled(false);
  stopButton.disabled = false;
  downloadButton.disabled = true;
  noteBuffer = [];
  sessionTempoBpm = null;
  keyboard.reset();
  setStatus("接続中…");

  const engine = await ensureSynthEngine();
  scheduler = null; // created once session_start confirms the tempo

  ws = connect({
    tempo: tempoInput.value,
    key: keyInput.value,
    seed: seedInput.value,
    onSessionStart: (message) => {
      sessionTempoBpm = message.tempo_bpm;
      scheduler = new BarScheduler({ sequencer: engine.sequencer, keyboard, tempoBpm: message.tempo_bpm });
      tempoDisplay.textContent = message.tempo_bpm;
      keyDisplay.textContent = message.key;
      seedDisplay.textContent = message.seed;
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
      scheduler.scheduleBar(message.bar_index, message.notes);
    },
    onError: (message) => {
      setStatus(`エラー: ${message.message}`);
      setFormEnabled(true);
      stopButton.disabled = true;
      reconnectButton.hidden = true;
    },
    onClose: () => {
      if (!stoppedByUser) {
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
  setStatus("停止");
  if (ws) ws.close();
  setFormEnabled(true);
  stopButton.disabled = true;
});

reconnectButton.addEventListener("click", () => {
  startSession();
});

gainInput.addEventListener("input", () => {
  if (gainNode) gainNode.gain.value = Number(gainInput.value);
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
```

- [ ] **Step 4: 自動テストを確認**

Run: `uv run pytest`
Expected: すべてPASS（Task 1で追加した静的配信のテストを含む）

Run: `node --test`
Expected: すべてPASS

- [ ] **Step 5: 手動確認（ブラウザでの結合テスト）**

Run: `uv run uvicorn zunish.server:app --reload`

ブラウザで`http://localhost:8000/`を開き、以下を確認する:

1. 「開始」を押すと数秒以内に鍵盤が光り始め、対応する音が鳴る（右手＝青、左手＝オレンジ、重なりは紫）。
2. 接続状態表示が「未接続」→「接続中…」→「再生中」と遷移し、テンポ・キー・シードが表示される。
3. 音量スライダーを動かすと音量が変わる。
4. 「停止」を押すと状態表示が「停止」になり、既にスケジュール済みの音は鳴り終わるまで再生され、フォームが再度入力可能になる。
5. しばらく再生した状態で「MIDIをダウンロード」を押すと`zunish.mid`がダウンロードされ、手元のDAWや`ffplay`等で開いて演奏内容が再生できる。
6. 「開始」を再度押す（seedを変えて）と、鍵盤・MIDIバッファがリセットされ新しい演奏が始まる。
7. ブラウザの開発者コンソールにエラー・警告が出ていないこと。

- [ ] **Step 6: コミット**

```bash
git add static/index.html static/css/style.css static/js/main.js
git commit -m "フロントエンドのUI配線(index.html/style.css/main.js)を実装し結合"
```

---

## 完了後の状態

- ブラウザで`http://localhost:8000/`を開けば、無限に生成されるZUN風ピアノリフをリアルタイムで聴きながら、鍵盤のハイライトを見て、MIDIとしてダウンロードできる状態になる。
- Render.comへのデプロイ設定（`render.yaml`など）は次のプランで扱う（`WEB_DESIGN.md`「7. 実装状況」参照）。
