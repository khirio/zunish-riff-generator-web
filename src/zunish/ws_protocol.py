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
    enable_modulation: bool


def parse_session_config(
    raw_tempo: str | None, raw_key: str | None, raw_seed: str | None, raw_modulation: str | None = None
) -> SessionConfig:
    """Parse and validate the ``tempo``/``key``/``seed``/``modulation`` query
    parameters.

    Raises :class:`InvalidSessionConfig` on any invalid value. Omitted
    parameters (``None``) fall back to the same defaults as the CLI (see
    ``cli.py``), except ``seed`` which is randomized when omitted and
    ``modulation`` which defaults to enabled.
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
        if not 0 <= seed <= SEED_MAX:
            raise InvalidSessionConfig(f"seed must be between 0 and {SEED_MAX} (got {seed})")

    if raw_modulation is None:
        enable_modulation = True
    elif raw_modulation.lower() == "true":
        enable_modulation = True
    elif raw_modulation.lower() == "false":
        enable_modulation = False
    else:
        raise InvalidSessionConfig(f"invalid modulation: {raw_modulation!r}")

    return SessionConfig(
        tempo_bpm=tempo_bpm,
        minor_tonic_pc=minor_tonic_pc,
        key_name=theory.pc_to_note_name(minor_tonic_pc),
        seed=seed,
        enable_modulation=enable_modulation,
    )


def build_session_start_message(config: SessionConfig) -> dict:
    return {
        "type": "session_start",
        "tempo_bpm": config.tempo_bpm,
        "key": config.key_name,
        "seed": config.seed,
        "modulation": config.enable_modulation,
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
