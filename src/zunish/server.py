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
        await asyncio.shield(asyncio.gather(stream_task, receive_task, return_exceptions=True))

    for task in (stream_task, receive_task):
        if task.done() and not task.cancelled():
            task.result()  # re-raise, if this side failed


@app.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    tempo: str | None = None,
    key: str | None = None,
    seed: str | None = None,
    modulation: str | None = None,
) -> None:
    await websocket.accept()
    try:
        config = parse_session_config(tempo, key, seed, modulation)
    except InvalidSessionConfig as error:
        try:
            await websocket.send_json(build_error_message(str(error)))
            await websocket.close(code=1008)
        except WebSocketDisconnect:
            # The client sent a bad tempo/key/seed and is already gone by the
            # time we try to tell it so -- an ordinary disconnect, not a bug.
            pass
        return

    try:
        await websocket.send_json(build_session_start_message(config))
        director = Director(config.minor_tonic_pc, random.Random(config.seed), config.enable_modulation)
        stream_coro = stream_bars(
            websocket.send_json, director.bars(), lambda: director.minor_tonic_pc, config.tempo_bpm
        )
        await run_until_disconnected(stream_coro, websocket.receive)
    except WebSocketDisconnect:
        # The client disconnected (e.g. closed the tab, or a mobile client
        # was dropped by a ping timeout) while a bar was mid-send. Starlette
        # surfaces this as WebSocketDisconnect(code=1006) from send_json; it
        # is an expected, routine event and must not be logged as an
        # unhandled ASGI exception.
        pass


app.mount("/soundfonts", StaticFiles(directory=REPO_ROOT / "assets" / "soundfonts"), name="soundfonts")
app.mount("/", StaticFiles(directory=REPO_ROOT / "static", html=True), name="static")
