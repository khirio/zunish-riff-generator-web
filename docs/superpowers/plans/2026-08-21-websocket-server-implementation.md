# WebSocketサーバー実装 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `WEB_DESIGN.md` 6章のWebSocketメッセージ仕様を実装する。クライアントの接続を受け付け、`session_start`/`bar`/`error`メッセージを先読みペース制御で送信するFastAPIサーバーを新設する。

**Architecture:** 新規モジュール2つを追加する。`ws_protocol.py`はI/Oを一切持たない純粋関数群（クエリパラメータのパース/検証、送信メッセージのdict組み立て）。`server.py`は`asyncio`ベースの先読み送信ロジック（`stream_bars`）・切断検知ロジック（`run_until_disconnected`）・それらを配線するFastAPIの`/ws`エンドポイントを持つ。既存の`player.py`/`cli.py`/`gui.py`/`midi_export.py`（CLI版の実行経路）は一切変更しない。

**Tech Stack:** Python 3.13, FastAPI, Uvicorn, pytest, httpx（`TestClient`用）。依存追加は`uv add`を使う。

**Spec:** `WEB_DESIGN.md`（6章 WebSocketメッセージ仕様）

## Global Constraints

- クエリパラメータ`tempo`/`key`/`seed`はすべて省略可能。省略時のデフォルトは`tempo=160.0`、`key="A"`、`seed`はサーバーが`random.randint(0, 2**31 - 1)`で採番する。
- `tempo`の許容範囲は`20.0`〜`400.0`（`TEMPO_MIN_BPM`/`TEMPO_MAX_BPM`）。範囲外・数値変換不能・`key`が`theory.note_name_to_pc`で解析不能・`seed`が整数変換不能、のいずれかの場合はサーバーが`{"type": "error", "message": ...}`を送信してからWebSocketを`code=1008`でクローズする。
- 送信メッセージは`session_start`（接続ごとに1回）と`bar`（小節ごと）の2種類。`bar`メッセージの`key`は毎回そのバーの調を含める（差分通知はしない）。
- 先読みペース制御：`bar_index`番目の小節の送信目標時刻は「セッション開始時刻 + `max(0.0, (bar_index - 1) * 1小節の秒数)`」。この式は`bar_index`が0でも1でも目標時刻が0になるため、「bar 0とbar 1を即座に連続送信し、以降は前の小節が始まる時刻に間に合うように送る」という6.4節の挙動を特別扱いなしに実現する。
- クライアント→サーバーのメッセージは実装しない（受信は切断検知のためだけに使う）。
- フロントエンドの静的ファイル配信・`render.yaml`などのデプロイ設定はこのプランのスコープ外（別プランで扱う）。
- 既存の`src/zunish/cli.py`・`player.py`・`gui.py`・`midi_export.py`・それらのテストは変更しない。
- 各タスク完了時点で`uv run pytest`がすべてグリーンであること。

---

### Task 1: `ws_protocol.py` — セッション設定のパースとメッセージ組み立て

**Files:**
- Create: `src/zunish/ws_protocol.py`
- Test: `tests/test_ws_protocol.py`

**Interfaces:**
- Consumes: `zunish.theory.note_name_to_pc`, `zunish.theory.pc_to_note_name`, `zunish.generator.NoteEvent`（既存）。
- Produces: `InvalidSessionConfig(ValueError)`、`SessionConfig`（frozen dataclass: `tempo_bpm: float`, `minor_tonic_pc: int`, `key_name: str`, `seed: int`）、`parse_session_config(raw_tempo: str | None, raw_key: str | None, raw_seed: str | None) -> SessionConfig`、`build_session_start_message(config: SessionConfig) -> dict`、`build_bar_message(bar_index: int, minor_tonic_pc: int, notes: list[NoteEvent]) -> dict`、`build_error_message(message: str) -> dict`、`note_event_to_dict(note: NoteEvent) -> dict`。これらはTask 2/3/4で`server.py`から使われる。

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_ws_protocol.py` を新規作成:

```python
import pytest

from zunish.generator import NoteEvent
from zunish.ws_protocol import (
    DEFAULT_KEY,
    DEFAULT_TEMPO_BPM,
    InvalidSessionConfig,
    SEED_MAX,
    TEMPO_MAX_BPM,
    TEMPO_MIN_BPM,
    build_bar_message,
    build_error_message,
    build_session_start_message,
    note_event_to_dict,
    parse_session_config,
)


def test_parse_session_config_uses_defaults_when_everything_is_omitted():
    config = parse_session_config(None, None, None)
    assert config.tempo_bpm == DEFAULT_TEMPO_BPM
    assert config.key_name == DEFAULT_KEY
    assert config.minor_tonic_pc == 9  # A
    assert 0 <= config.seed <= SEED_MAX


def test_parse_session_config_parses_valid_values():
    config = parse_session_config("140", "C#", "123")
    assert config.tempo_bpm == 140.0
    assert config.key_name == "C#"
    assert config.minor_tonic_pc == 1
    assert config.seed == 123


def test_parse_session_config_normalizes_key_spelling_to_the_canonical_sharp_form():
    config = parse_session_config(None, "Eb", None)
    assert config.key_name == "D#"
    assert config.minor_tonic_pc == 3


def test_parse_session_config_rejects_a_non_numeric_tempo():
    with pytest.raises(InvalidSessionConfig):
        parse_session_config("fast", None, None)


def test_parse_session_config_rejects_a_tempo_outside_the_allowed_range():
    with pytest.raises(InvalidSessionConfig):
        parse_session_config(str(TEMPO_MAX_BPM + 1), None, None)
    with pytest.raises(InvalidSessionConfig):
        parse_session_config(str(TEMPO_MIN_BPM - 1), None, None)


def test_parse_session_config_rejects_an_unknown_key_name():
    with pytest.raises(InvalidSessionConfig):
        parse_session_config(None, "Z", None)


def test_parse_session_config_rejects_a_non_integer_seed():
    with pytest.raises(InvalidSessionConfig):
        parse_session_config(None, None, "not-a-number")


def test_build_session_start_message_shape():
    config = parse_session_config("140", "C#", "123")
    assert build_session_start_message(config) == {
        "type": "session_start",
        "tempo_bpm": 140.0,
        "key": "C#",
        "seed": 123,
    }


def test_build_error_message_shape():
    assert build_error_message("invalid key: 'Z'") == {"type": "error", "message": "invalid key: 'Z'"}


def test_note_event_to_dict_shape():
    note = NoteEvent(pitch=60, start_beat=0.5, duration_beat=1.0, velocity=100, channel=0)
    assert note_event_to_dict(note) == {
        "pitch": 60,
        "start_beat": 0.5,
        "duration_beat": 1.0,
        "velocity": 100,
        "channel": 0,
    }


def test_build_bar_message_shape():
    note = NoteEvent(pitch=60, start_beat=0.0, duration_beat=0.5, velocity=100, channel=0)
    message = build_bar_message(42, 9, [note])
    assert message == {
        "type": "bar",
        "bar_index": 42,
        "key": "A",
        "notes": [
            {"pitch": 60, "start_beat": 0.0, "duration_beat": 0.5, "velocity": 100, "channel": 0}
        ],
    }
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `uv run pytest tests/test_ws_protocol.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'zunish.ws_protocol'`

- [ ] **Step 3: `src/zunish/ws_protocol.py` を実装**

```python
"""Pure (no I/O) helpers for the WebSocket protocol described in
WEB_DESIGN.md section 6: parsing/validating a session's query parameters
and building the JSON-serializable message dicts sent to the client."""

from __future__ import annotations

import random
from dataclasses import dataclass

from zunish import theory
from zunish.generator import NoteEvent

DEFAULT_TEMPO_BPM = 160.0
DEFAULT_KEY = "A"
TEMPO_MIN_BPM = 20.0
TEMPO_MAX_BPM = 400.0
SEED_MAX = 2**31 - 1


class InvalidSessionConfig(ValueError):
    """Raised when a client-supplied query parameter fails validation. The
    message is safe to send back to the client as-is."""


@dataclass(frozen=True)
class SessionConfig:
    tempo_bpm: float
    minor_tonic_pc: int
    key_name: str
    seed: int


def parse_session_config(
    raw_tempo: str | None, raw_key: str | None, raw_seed: str | None
) -> SessionConfig:
    """Parse and validate the ``tempo``/``key``/``seed`` query parameters.

    Raises :class:`InvalidSessionConfig` on any invalid value. Omitted
    parameters (``None``) fall back to the same defaults as the CLI (see
    ``cli.py``), except ``seed`` which is randomized when omitted.
    """
    if raw_tempo is None:
        tempo_bpm = DEFAULT_TEMPO_BPM
    else:
        try:
            tempo_bpm = float(raw_tempo)
        except ValueError:
            raise InvalidSessionConfig(f"invalid tempo: {raw_tempo!r}") from None
        if not TEMPO_MIN_BPM <= tempo_bpm <= TEMPO_MAX_BPM:
            raise InvalidSessionConfig(
                f"tempo must be between {TEMPO_MIN_BPM} and {TEMPO_MAX_BPM} (got {tempo_bpm})"
            )

    key_name = DEFAULT_KEY if raw_key is None else raw_key
    try:
        minor_tonic_pc = theory.note_name_to_pc(key_name)
    except ValueError:
        raise InvalidSessionConfig(f"invalid key: {key_name!r}") from None

    if raw_seed is None:
        seed = random.randint(0, SEED_MAX)
    else:
        try:
            seed = int(raw_seed)
        except ValueError:
            raise InvalidSessionConfig(f"invalid seed: {raw_seed!r}") from None

    return SessionConfig(
        tempo_bpm=tempo_bpm,
        minor_tonic_pc=minor_tonic_pc,
        key_name=theory.pc_to_note_name(minor_tonic_pc),
        seed=seed,
    )


def build_session_start_message(config: SessionConfig) -> dict:
    return {
        "type": "session_start",
        "tempo_bpm": config.tempo_bpm,
        "key": config.key_name,
        "seed": config.seed,
    }


def build_error_message(message: str) -> dict:
    return {"type": "error", "message": message}


def note_event_to_dict(note: NoteEvent) -> dict:
    return {
        "pitch": note.pitch,
        "start_beat": note.start_beat,
        "duration_beat": note.duration_beat,
        "velocity": note.velocity,
        "channel": note.channel,
    }


def build_bar_message(bar_index: int, minor_tonic_pc: int, notes: list[NoteEvent]) -> dict:
    return {
        "type": "bar",
        "bar_index": bar_index,
        "key": theory.pc_to_note_name(minor_tonic_pc),
        "notes": [note_event_to_dict(note) for note in notes],
    }
```

- [ ] **Step 4: テストが通ることを確認し、全体のテストも流す**

Run: `uv run pytest tests/test_ws_protocol.py -v`
Expected: すべてPASS

Run: `uv run pytest`
Expected: すべてPASS（既存テストに影響なし）

- [ ] **Step 5: コミット**

```bash
git add src/zunish/ws_protocol.py tests/test_ws_protocol.py
git commit -m "WebSocketプロトコルのメッセージ組み立て・セッション設定パースを追加"
```

---

### Task 2: `server.py` — `stream_bars`（先読みペース制御）

**Files:**
- Create: `src/zunish/server.py`
- Test: `tests/test_server.py`

**Interfaces:**
- Consumes: `zunish.theory.BEATS_PER_BAR`（既存）、`zunish.ws_protocol.build_bar_message`（Task 1）。
- Produces: `stream_bars(send_json, bars, current_minor_tonic_pc, tempo_bpm, *, clock=time.monotonic, sleep=asyncio.sleep) -> None`（コルーチン）。`send_json: Callable[[dict], Awaitable[None]]`、`bars: Iterator[list[NoteEvent]]`、`current_minor_tonic_pc: Callable[[], int]`。Task 4でFastAPIの`WebSocket.send_json`/`Director.bars()`/`Director.minor_tonic_pc`と接続する。

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_server.py` を新規作成:

```python
import asyncio

import pytest

from zunish.generator import NoteEvent
from zunish.server import stream_bars


class FakeAsyncClock:
    """Async analogue of test_player.py's FakeClock: `sleep` advances the
    fake clock instead of actually waiting, so pacing tests run instantly."""

    def __init__(self):
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        if seconds > 0:
            self.now += seconds


def test_stream_bars_sends_bar_0_and_bar_1_immediately():
    clock = FakeAsyncClock()
    sent_at: list[float] = []

    async def send_json(message):
        sent_at.append(clock.now)

    asyncio.run(
        stream_bars(
            send_json, iter([[], [], []]), lambda: 0, tempo_bpm=60.0,
            clock=clock.monotonic, sleep=clock.sleep,
        )
    )

    assert sent_at[:2] == [0.0, 0.0]


def test_stream_bars_waits_a_full_bar_before_each_subsequent_bar():
    clock = FakeAsyncClock()
    sent_at: list[float] = []

    async def send_json(message):
        sent_at.append(clock.now)

    # 60 BPM => 1 beat == 1s => a 4-beat bar == 4s.
    asyncio.run(
        stream_bars(
            send_json, iter([[], [], [], []]), lambda: 0, tempo_bpm=60.0,
            clock=clock.monotonic, sleep=clock.sleep,
        )
    )

    assert sent_at == [0.0, 0.0, 4.0, 8.0]


def test_stream_bars_sends_bar_index_key_and_notes():
    clock = FakeAsyncClock()
    sent: list[dict] = []

    async def send_json(message):
        sent.append(message)

    note = NoteEvent(pitch=60, start_beat=0.0, duration_beat=1.0, velocity=100, channel=0)
    asyncio.run(
        stream_bars(
            send_json, iter([[note], []]), lambda: 9, tempo_bpm=60.0,
            clock=clock.monotonic, sleep=clock.sleep,
        )
    )

    assert sent[0]["bar_index"] == 0
    assert sent[0]["key"] == "A"  # pitch class 9 == A
    assert sent[0]["notes"] == [
        {"pitch": 60, "start_beat": 0.0, "duration_beat": 1.0, "velocity": 100, "channel": 0}
    ]
    assert sent[1]["bar_index"] == 1


def test_stream_bars_propagates_send_errors_so_a_disconnect_stops_an_infinite_stream():
    clock = FakeAsyncClock()

    async def send_json(message):
        raise ConnectionError("client gone")

    def infinite_bars():
        while True:
            yield []

    with pytest.raises(ConnectionError):
        asyncio.run(
            stream_bars(
                send_json, infinite_bars(), lambda: 0, tempo_bpm=60.0,
                clock=clock.monotonic, sleep=clock.sleep,
            )
        )
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `uv run pytest tests/test_server.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'zunish.server'`

- [ ] **Step 3: `src/zunish/server.py` を実装**

```python
"""FastAPI WebSocket server implementing the protocol described in
WEB_DESIGN.md section 6."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable, Iterator

from zunish.generator import NoteEvent
from zunish.theory import BEATS_PER_BAR
from zunish.ws_protocol import build_bar_message


async def stream_bars(
    send_json: Callable[[dict], Awaitable[None]],
    bars: Iterator[list[NoteEvent]],
    current_minor_tonic_pc: Callable[[], int],
    tempo_bpm: float,
    *,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> None:
    """Send one ``bar`` message per item in ``bars``, pacing transmission so
    the client always holds "the currently-playing bar + 1 lookahead bar"
    (see WEB_DESIGN.md 6.4). Bar 0 and bar 1 are sent immediately; every bar
    N afterwards is sent right as bar N-1 starts playing. Runs until ``bars``
    is exhausted or ``send_json`` raises (e.g. the client disconnected) —
    the caller is expected to let that exception propagate.
    """
    seconds_per_bar = BEATS_PER_BAR * 60.0 / tempo_bpm
    session_start = clock()
    for bar_index, notes in enumerate(bars):
        target = session_start + max(0.0, (bar_index - 1) * seconds_per_bar)
        remaining = target - clock()
        if remaining > 0:
            await sleep(remaining)
        await send_json(build_bar_message(bar_index, current_minor_tonic_pc(), notes))
```

- [ ] **Step 4: テストが通ることを確認し、全体のテストも流す**

Run: `uv run pytest tests/test_server.py -v`
Expected: すべてPASS

Run: `uv run pytest`
Expected: すべてPASS

- [ ] **Step 5: コミット**

```bash
git add src/zunish/server.py tests/test_server.py
git commit -m "小節の先読みペース制御(stream_bars)を追加"
```

---

### Task 3: `server.py` — `run_until_disconnected`（切断検知）

**Files:**
- Modify: `src/zunish/server.py`
- Test: `tests/test_server.py`

**Interfaces:**
- Consumes: なし（`asyncio`のみ）。
- Produces: `run_until_disconnected(stream_coro: Awaitable[None], receive: Callable[[], Awaitable[object]]) -> None`。Task 4でFastAPIの`WebSocket.receive()`と接続する。

**Why this task exists:** `/ws`エンドポイントはクライアントに送信するだけで、クライアントからのメッセージを待ち受けない。ASGIサーバーは`receive()`を呼ばない限り切断を通知しないため、`stream_bars`だけを`await`していると、クライアントが去った後もタスクが残り続けてしまう（無限生成ループのサーバーではリソースリークになる）。`websocket.receive()`を裏で並行して待たせておき、どちらか一方が終わった時点でもう一方をキャンセルする。

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_server.py`先頭の`from zunish.server import stream_bars`を`from zunish.server import run_until_disconnected, stream_bars`に変更し、ファイル末尾に追記:

```python
def test_run_until_disconnected_cancels_the_stream_when_receive_resolves_first():
    stream_cancelled = False

    async def never_ending_stream():
        nonlocal stream_cancelled
        try:
            await asyncio.sleep(1000)
        except asyncio.CancelledError:
            stream_cancelled = True
            raise

    async def immediate_receive():
        return {"type": "websocket.disconnect"}

    asyncio.run(
        asyncio.wait_for(
            run_until_disconnected(never_ending_stream(), immediate_receive), timeout=1.0
        )
    )

    assert stream_cancelled


def test_run_until_disconnected_cancels_the_receive_wait_when_the_stream_finishes_first():
    receive_cancelled = False

    async def quick_stream():
        return None

    async def never_resolving_receive():
        nonlocal receive_cancelled
        try:
            await asyncio.sleep(1000)
        except asyncio.CancelledError:
            receive_cancelled = True
            raise

    asyncio.run(
        asyncio.wait_for(
            run_until_disconnected(quick_stream(), never_resolving_receive), timeout=1.0
        )
    )

    assert receive_cancelled


def test_run_until_disconnected_propagates_a_stream_error():
    async def failing_stream():
        raise ConnectionError("client gone")

    async def never_resolving_receive():
        await asyncio.sleep(1000)

    with pytest.raises(ConnectionError):
        asyncio.run(
            asyncio.wait_for(
                run_until_disconnected(failing_stream(), never_resolving_receive), timeout=1.0
            )
        )
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `uv run pytest tests/test_server.py -k run_until_disconnected -v`
Expected: FAIL — `ImportError: cannot import name 'run_until_disconnected'`

- [ ] **Step 3: 実装**

`src/zunish/server.py`の`stream_bars`の後ろに追加:

```python
async def run_until_disconnected(
    stream_coro: Awaitable[None], receive: Callable[[], Awaitable[object]]
) -> None:
    """Run ``stream_coro`` until it finishes on its own, or ``receive()``
    resolves first (the client disconnected, or sent something — this
    endpoint expects no client messages, so either case just means "stop").
    Whichever side doesn't finish first is cancelled. A ``stream_coro``
    failure (e.g. the send raising because the client is gone) propagates.
    """
    stream_task = asyncio.ensure_future(stream_coro)
    receive_task = asyncio.ensure_future(receive())
    try:
        await asyncio.wait({stream_task, receive_task}, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for task in (stream_task, receive_task):
            if not task.done():
                task.cancel()
        await asyncio.gather(stream_task, receive_task, return_exceptions=True)

    if stream_task.done() and not stream_task.cancelled():
        stream_task.result()  # re-raise, if stream_coro failed
```

- [ ] **Step 4: テストが通ることを確認し、全体のテストも流す**

Run: `uv run pytest tests/test_server.py -v`
Expected: すべてPASS

Run: `uv run pytest`
Expected: すべてPASS

- [ ] **Step 5: コミット**

```bash
git add src/zunish/server.py tests/test_server.py
git commit -m "受信待機と競合させる切断検知(run_until_disconnected)を追加"
```

---

### Task 4: FastAPI依存追加 + `/ws`エンドポイント実装

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/zunish/server.py`
- Test: `tests/test_server.py`

**Interfaces:**
- Consumes: `parse_session_config`, `InvalidSessionConfig`, `build_session_start_message`, `build_error_message`（Task 1）、`stream_bars`（Task 2）、`run_until_disconnected`（Task 3）、`zunish.director.Director`（既存）。
- Produces: `zunish.server.app`（`FastAPI`インスタンス、`/ws`エンドポイントを持つ）。

- [ ] **Step 1: 依存を追加**

```bash
uv add fastapi "uvicorn[standard]"
uv add --group dev httpx
```

Run: `git diff pyproject.toml uv.lock` で`fastapi`/`uvicorn`/`httpx`が追加されたことを確認する。

- [ ] **Step 2: 失敗するテストを書く**

`tests/test_server.py`の先頭に以下のimportを追加:

```python
from fastapi import WebSocketDisconnect
from fastapi.testclient import TestClient

from zunish.server import app
```

`tests/test_server.py`の末尾に追記:

```python
def test_websocket_uses_defaults_when_no_query_params_are_given():
    client = TestClient(app)
    with client.websocket_connect("/ws") as websocket:
        session_start = websocket.receive_json()
        assert session_start["type"] == "session_start"
        assert session_start["tempo_bpm"] == 160.0
        assert session_start["key"] == "A"
        assert isinstance(session_start["seed"], int)


def test_websocket_sends_session_start_then_bar_0_and_bar_1():
    client = TestClient(app)
    with client.websocket_connect("/ws?tempo=160&key=C&seed=42") as websocket:
        session_start = websocket.receive_json()
        assert session_start == {"type": "session_start", "tempo_bpm": 160.0, "key": "C", "seed": 42}

        bar0 = websocket.receive_json()
        assert bar0["type"] == "bar"
        assert bar0["bar_index"] == 0
        assert bar0["notes"]  # a bar always has at least the left-hand accompaniment

        bar1 = websocket.receive_json()
        assert bar1["bar_index"] == 1


def test_websocket_sends_an_error_and_closes_on_an_invalid_key():
    client = TestClient(app)
    with client.websocket_connect("/ws?key=Z") as websocket:
        message = websocket.receive_json()
        assert message["type"] == "error"
        assert "Z" in message["message"]
        with pytest.raises(WebSocketDisconnect):
            websocket.receive_json()


def test_websocket_sends_an_error_and_closes_on_a_tempo_outside_the_allowed_range():
    client = TestClient(app)
    with client.websocket_connect("/ws?tempo=999") as websocket:
        message = websocket.receive_json()
        assert message["type"] == "error"
        with pytest.raises(WebSocketDisconnect):
            websocket.receive_json()
```

- [ ] **Step 3: テストが失敗することを確認**

Run: `uv run pytest tests/test_server.py -v`
Expected: FAIL — `ImportError: cannot import name 'app' from 'zunish.server'`

- [ ] **Step 4: `src/zunish/server.py`にエンドポイントを実装**

ファイル先頭のimportブロックを以下に置き換える（既存の`stream_bars`/`run_until_disconnected`はそのまま残す）:

```python
"""FastAPI WebSocket server implementing the protocol described in
WEB_DESIGN.md section 6."""

from __future__ import annotations

import asyncio
import random
import time
from collections.abc import Awaitable, Callable, Iterator

from fastapi import FastAPI, WebSocket

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

app = FastAPI()
```

`run_until_disconnected`関数の後ろ（ファイル末尾）に追加:

```python
@app.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    tempo: str | None = None,
    key: str | None = None,
    seed: str | None = None,
) -> None:
    await websocket.accept()
    try:
        config = parse_session_config(tempo, key, seed)
    except InvalidSessionConfig as error:
        await websocket.send_json(build_error_message(str(error)))
        await websocket.close(code=1008)
        return

    await websocket.send_json(build_session_start_message(config))
    director = Director(config.minor_tonic_pc, random.Random(config.seed))
    stream_coro = stream_bars(
        websocket.send_json, director.bars(), lambda: director.minor_tonic_pc, config.tempo_bpm
    )
    await run_until_disconnected(stream_coro, websocket.receive)
```

- [ ] **Step 5: テストが通ることを確認し、全体のテストも流す**

Run: `uv run pytest tests/test_server.py -v`
Expected: すべてPASS

Run: `uv run pytest`
Expected: すべてPASS（CLI版の既存テストも含めて全緑）

- [ ] **Step 6: コミット**

```bash
git add pyproject.toml uv.lock src/zunish/server.py tests/test_server.py
git commit -m "FastAPIの/wsエンドポイントを実装しWebSocketサーバーを追加"
```

---

## 完了後の状態

- `uv run uvicorn zunish.server:app --reload` でローカル起動し、`wss://localhost:8000/ws?tempo=160&key=A&seed=1` に接続すれば`session_start`に続けて`bar`メッセージが流れてくる状態になる。
- 静的ファイル配信・フロントエンド実装・Render.comへのデプロイ設定は次のプランで扱う（`WEB_DESIGN.md`「7. 次のステップ」参照）。
