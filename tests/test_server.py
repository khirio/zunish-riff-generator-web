import asyncio
from pathlib import Path

import pytest
from fastapi import WebSocketDisconnect
from fastapi.testclient import TestClient

from zunish.generator import NoteEvent
from zunish.server import REPO_ROOT, app, run_until_disconnected, stream_bars, websocket_endpoint


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


def test_run_until_disconnected_propagates_a_receive_error():
    async def never_ending_stream():
        await asyncio.sleep(1000)

    async def failing_receive():
        raise ConnectionResetError("transport gone")

    with pytest.raises(ConnectionResetError):
        asyncio.run(
            asyncio.wait_for(
                run_until_disconnected(never_ending_stream(), failing_receive), timeout=1.0
            )
        )


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
        assert session_start == {
            "type": "session_start",
            "tempo_bpm": 160.0,
            "key": "C",
            "seed": 42,
            "modulation": True,
        }

        bar0 = websocket.receive_json()
        assert bar0["type"] == "bar"
        assert bar0["bar_index"] == 0
        assert bar0["notes"]  # a bar always has at least the left-hand accompaniment

        bar1 = websocket.receive_json()
        assert bar1["bar_index"] == 1


def test_websocket_disables_modulation_when_requested():
    client = TestClient(app)
    with client.websocket_connect("/ws?key=C&seed=42&modulation=false") as websocket:
        session_start = websocket.receive_json()
        assert session_start["modulation"] is False


def test_websocket_sends_an_error_and_closes_on_an_invalid_modulation_value():
    client = TestClient(app)
    with client.websocket_connect("/ws?modulation=maybe") as websocket:
        message = websocket.receive_json()
        assert message["type"] == "error"
        with pytest.raises(WebSocketDisconnect):
            websocket.receive_json()


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


class FakeDisconnectingWebSocket:
    """A minimal stand-in for `fastapi.WebSocket` used to drive
    `websocket_endpoint` directly, so we can simulate the transport-level
    failure a *real* client disconnect produces (`WebSocketDisconnect`
    raised out of `send_json`) -- something FastAPI's `TestClient`, whose
    transport is in-process and never fails, cannot reproduce."""

    def __init__(self, *, fail_after_sends: int):
        self.fail_after_sends = fail_after_sends
        self.sent: list[dict] = []

    async def accept(self):
        pass

    async def send_json(self, message):
        if len(self.sent) >= self.fail_after_sends:
            raise WebSocketDisconnect(code=1006)
        self.sent.append(message)

    async def close(self, code=1000, reason=None):
        pass

    async def receive(self):
        # Never resolves: in these tests, the disconnect is discovered via
        # a failing send, not via a `websocket.receive` message.
        await asyncio.sleep(1000)


def test_websocket_endpoint_swallows_a_disconnect_that_happens_mid_stream():
    # session_start (1st send) succeeds; the first `bar` message (2nd send,
    # from inside stream_bars) raises WebSocketDisconnect, as a real send on
    # a closed transport does. websocket_endpoint must swallow it quietly
    # instead of letting it escape the ASGI call.
    websocket = FakeDisconnectingWebSocket(fail_after_sends=1)

    asyncio.run(asyncio.wait_for(websocket_endpoint(websocket, None, None, None), timeout=5.0))

    assert len(websocket.sent) == 1  # only session_start got through


def test_websocket_endpoint_swallows_a_disconnect_while_reporting_an_invalid_config():
    # The client is already gone by the time the server tries to send the
    # error message for its bad `key`, so even the error-reporting send
    # raises WebSocketDisconnect. That must be swallowed too.
    websocket = FakeDisconnectingWebSocket(fail_after_sends=0)

    asyncio.run(asyncio.wait_for(websocket_endpoint(websocket, None, "Z", None), timeout=5.0))

    assert websocket.sent == []


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
