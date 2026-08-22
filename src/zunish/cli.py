"""CLI entrypoint: wires the Director and Player together and drives
FluidSynth in real time until interrupted with Ctrl+C."""

from __future__ import annotations

import argparse
import queue
import random
import sys
import threading
from collections.abc import Sequence
from pathlib import Path

from zunish import theory
from zunish.director import Director
from zunish.gui import PianoGUI
from zunish.midi_export import MidiRecorder
from zunish.player import Player

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOUNDFONT = REPO_ROOT / "assets" / "soundfonts" / "FluidR3Mono_GM.sf3"

DEFAULT_TEMPO_BPM = 160.0
DEFAULT_KEY = "A"
DEFAULT_GAIN = 1.0
PIANO_BANK = 0
PIANO_PRESET = 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="zunish", description="Infinite ZUN-style piano riff generator (FluidSynth playback)."
    )
    parser.add_argument(
        "--soundfont",
        default=str(DEFAULT_SOUNDFONT),
        help=f"Path to a .sf2/.sf3 soundfont file with a piano patch (default: {DEFAULT_SOUNDFONT}).",
    )
    parser.add_argument("--tempo", type=float, default=DEFAULT_TEMPO_BPM, help="Tempo in BPM (fixed for the session).")
    parser.add_argument("--key", default=DEFAULT_KEY, help="Minor tonic note name, e.g. A, C#, Eb.")
    parser.add_argument(
        "--gain",
        type=float,
        default=DEFAULT_GAIN,
        help=f"FluidSynth output gain, 0.0-10.0 (default: {DEFAULT_GAIN}). Higher values may clip.",
    )
    parser.add_argument("--save", default=None, help="Optional path to save the performance as a .mid file.")
    parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducible generation.")
    return parser


def _playback_loop(
    director: Director, player: Player, stop_event: threading.Event, event_queue: "queue.Queue"
) -> None:
    """Generate-and-play loop; runs on a background thread so the GUI's
    Tk mainloop can own the main thread. Reports key changes (detected by
    polling ``director.minor_tonic_pc`` between bars) onto ``event_queue``."""
    last_key_pc = director.minor_tonic_pc
    for bar_events in director.bars():
        if stop_event.is_set():
            break
        if director.minor_tonic_pc != last_key_pc:
            last_key_pc = director.minor_tonic_pc
            event_queue.put(("key", last_key_pc))
        player.play_bar(bar_events)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        minor_tonic_pc = theory.note_name_to_pc(args.key)
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    if not Path(args.soundfont).is_file():
        print(f"error: soundfont not found: {args.soundfont}", file=sys.stderr)
        return 1

    if not 0.0 <= args.gain <= 10.0:
        print(f"error: --gain must be between 0.0 and 10.0 (got {args.gain})", file=sys.stderr)
        return 1

    import fluidsynth  # imported lazily so --help works without the FluidSynth library installed

    rng = random.Random(args.seed)
    director = Director(minor_tonic_pc, rng)
    recorder = MidiRecorder(args.tempo) if args.save else None

    synth = fluidsynth.Synth(gain=args.gain)
    synth.start()
    sfid = synth.sfload(args.soundfont)
    synth.program_select(0, sfid, PIANO_BANK, PIANO_PRESET)
    synth.program_select(1, sfid, PIANO_BANK, PIANO_PRESET)

    event_queue: queue.Queue = queue.Queue()
    player = Player(synth, args.tempo, recorder, event_sink=event_queue)
    stop_event = threading.Event()
    playback_thread = threading.Thread(
        target=_playback_loop, args=(director, player, stop_event, event_queue), daemon=True
    )

    def _cleanup() -> None:
        stop_event.set()
        playback_thread.join(timeout=5.0)
        player.all_notes_off()
        synth.delete()
        if recorder is not None:
            recorder.save(args.save)
            print(f"saved: {args.save}", file=sys.stderr)

    playback_thread.start()
    print("ウィンドウを閉じるか Ctrl+C で停止します。", file=sys.stderr)
    gui = PianoGUI(event_queue, tempo_bpm=args.tempo, initial_key_pc=minor_tonic_pc, on_close=stop_event.set)
    try:
        gui.run()
    except KeyboardInterrupt:
        pass
    finally:
        _cleanup()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
