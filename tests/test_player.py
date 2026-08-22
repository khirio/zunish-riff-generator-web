from zunish.generator import BEATS_PER_BAR, LEFT_HAND_CHANNEL, NoteEvent
from zunish.player import Player


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        if seconds > 0:
            self.now += seconds


class FakeSynth:
    def __init__(self, clock: FakeClock):
        self._clock = clock
        self.calls: list[tuple] = []

    def noteon(self, channel, pitch, velocity):
        self.calls.append(("on", channel, pitch, velocity, self._clock.now))

    def noteoff(self, channel, pitch):
        self.calls.append(("off", channel, pitch, self._clock.now))


def _make_player(monkeypatch, tempo_bpm=60.0):
    # 60 BPM => 1 beat == 1 second, for easy arithmetic.
    clock = FakeClock()
    monkeypatch.setattr("zunish.player.time.monotonic", clock.monotonic)
    monkeypatch.setattr("zunish.player.time.sleep", clock.sleep)
    synth = FakeSynth(clock)
    player = Player(synth, tempo_bpm)
    return player, synth, clock


def test_play_bar_does_not_turn_off_a_note_that_crosses_the_bar_line(monkeypatch):
    player, synth, _clock = _make_player(monkeypatch)
    crossing_note = NoteEvent(pitch=60, start_beat=3.5, duration_beat=1.0, velocity=90, channel=LEFT_HAND_CHANNEL)

    player.play_bar([crossing_note])

    assert ("on", LEFT_HAND_CHANNEL, 60, 90, 3.5) in synth.calls
    assert not any(call[0] == "off" and call[1:3] == (LEFT_HAND_CHANNEL, 60) for call in synth.calls)


def test_play_bar_turns_off_the_carried_over_note_early_in_the_next_bar(monkeypatch):
    player, synth, _clock = _make_player(monkeypatch)
    crossing_note = NoteEvent(pitch=60, start_beat=3.5, duration_beat=1.0, velocity=90, channel=LEFT_HAND_CHANNEL)

    player.play_bar([crossing_note])
    player.play_bar([])

    # The note crossed 0.5 beats into bar 2, so its note-off should fire 0.5s
    # (at 60 BPM) into the second play_bar call, i.e. at absolute time 4.5s.
    off_calls = [call for call in synth.calls if call[0] == "off" and call[1:3] == (LEFT_HAND_CHANNEL, 60)]
    assert len(off_calls) == 1
    assert off_calls[0][3] == BEATS_PER_BAR + 0.5


def test_play_bar_still_takes_a_full_bar_when_the_last_event_is_deferred(monkeypatch):
    player, _synth, clock = _make_player(monkeypatch)
    crossing_note = NoteEvent(pitch=60, start_beat=3.5, duration_beat=1.0, velocity=90, channel=LEFT_HAND_CHANNEL)

    player.play_bar([crossing_note])

    assert clock.now == BEATS_PER_BAR


def test_play_bar_suppresses_a_re_strike_when_the_next_bar_starts_on_the_carried_over_pitch(monkeypatch):
    player, synth, _clock = _make_player(monkeypatch)
    crossing_note = NoteEvent(pitch=60, start_beat=3.5, duration_beat=1.0, velocity=90, channel=LEFT_HAND_CHANNEL)
    colliding_note = NoteEvent(pitch=60, start_beat=0.0, duration_beat=4.0, velocity=100, channel=LEFT_HAND_CHANNEL)

    player.play_bar([crossing_note])
    player.play_bar([colliding_note])

    on_calls = [call for call in synth.calls if call[0] == "on" and call[1:3] == (LEFT_HAND_CHANNEL, 60)]
    off_calls = [call for call in synth.calls if call[0] == "off" and call[1:3] == (LEFT_HAND_CHANNEL, 60)]
    assert len(on_calls) == 1  # no re-strike for the colliding note-on
    assert len(off_calls) == 1
    # It should turn off when colliding_note's own duration ends (4.0s into bar 2),
    # not at the stale carried-over time (0.5s into bar 2).
    assert off_calls[0][3] == BEATS_PER_BAR + 4.0
