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
    assert config.enable_modulation is True


def test_parse_session_config_parses_valid_values():
    config = parse_session_config("140", "C#", "123", "false")
    assert config.tempo_bpm == 140.0
    assert config.key_name == "C#"
    assert config.minor_tonic_pc == 1
    assert config.seed == 123
    assert config.enable_modulation is False


def test_parse_session_config_accepts_modulation_true():
    config = parse_session_config(None, None, None, "true")
    assert config.enable_modulation is True


def test_parse_session_config_rejects_an_invalid_modulation_value():
    with pytest.raises(InvalidSessionConfig):
        parse_session_config(None, None, None, "maybe")


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


def test_parse_session_config_rejects_a_seed_outside_the_allowed_range():
    with pytest.raises(InvalidSessionConfig):
        parse_session_config(None, None, "-1")
    with pytest.raises(InvalidSessionConfig):
        parse_session_config(None, None, str(SEED_MAX + 1))


def test_build_session_start_message_shape():
    config = parse_session_config("140", "C#", "123")
    assert build_session_start_message(config) == {
        "type": "session_start",
        "tempo_bpm": 140.0,
        "key": "C#",
        "seed": 123,
        "modulation": True,
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
