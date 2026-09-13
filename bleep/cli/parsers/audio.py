"""Audio-related subparsers."""

import argparse


def register(subparsers, _subparser_map):
    audio_profiles = subparsers.add_parser("audio-profiles", help="List Bluetooth audio profiles via ALSA correlation")
    audio_profiles.add_argument("--device", help="Filter by device MAC address")

    audio_play = subparsers.add_parser("audio-play", help="Play audio file to Bluetooth device")
    audio_play.add_argument("device", help="Target device MAC address")
    audio_play.add_argument("file", help="Audio file path")
    audio_play.add_argument("--volume", type=int, help="Volume (0-127)")
    audio_play.add_argument("--codec", choices=["SBC", "MP3", "AAC"], help="Codec preference (if supported)")
    audio_play.add_argument("--direct", action="store_true", help="Acquire an existing transport directly instead of registering a BLEEP-owned endpoint (requires audio daemon stopped)")
    audio_play.add_argument("--system", action="store_true", help="Play via system audio tools (paplay/pw-play/aplay) through the host audio daemon — no D-Bus transport acquisition needed")
    audio_play.add_argument("--force-endpoint", action="store_true", help="Bypass the MediaEndpoint1 contention pre-flight (use when a competing daemon is known to release the endpoint during the cycle)")

    audio_record = subparsers.add_parser("audio-record", help="Record audio from Bluetooth device")
    audio_record.add_argument("device", help="Source device MAC address")
    audio_record.add_argument("output", help="Output file path")
    audio_record.add_argument("--duration", type=int, help="Duration in seconds")
    audio_record.add_argument("--direct", action="store_true", help="Acquire an existing transport directly instead of registering a BLEEP-owned endpoint (requires audio daemon stopped)")
    audio_record.add_argument("--system", action="store_true", help="Record via system audio tools (parecord/pw-record/arecord) through the host audio daemon — no D-Bus transport acquisition needed")
    audio_record.add_argument("--hfp", action="store_true", help="Capture the HFP/HSP microphone (SCO source): switch the device's card to a headset/hands-free profile and record the mic via system audio tools. Voice-grade mono. Implies system-tool capture.")
    audio_record.add_argument("--keep-profile", action="store_true", help="With --hfp: do not restore the card's previous audio profile after recording")
    audio_record.add_argument("--force-endpoint", action="store_true", help="Bypass the MediaEndpoint1 contention pre-flight (use when a competing daemon is known to release the endpoint during the cycle)")

    audio_recon = subparsers.add_parser("audio-recon", help="Audio recon: enumerate BlueZ cards/profiles, play test file, record, analyse with sox")
    audio_recon.add_argument("--device", help="Filter by device MAC address")
    audio_recon.add_argument("--test-file", help="Path to test audio file for playback to sinks")
    audio_recon.add_argument("--no-play", action="store_true", help="Skip playing test file to sinks")
    audio_recon.add_argument("--no-record", action="store_true", help="Skip recording from sources/sinks")
    audio_recon.add_argument("--out", dest="output_json", help="Write structured result to JSON file")
    audio_recon.add_argument("--record-dir", default="/tmp", help="Directory for recordings (default: /tmp)")
    audio_recon.add_argument("--duration", type=int, default=8, help="Recording duration per interface in seconds (default: 8)")

    amusica_parser = subparsers.add_parser(
        "amusica", help="Amusica: scan, connect, recon, and manipulate Bluetooth audio targets",
    )
    amusica_parser.add_argument(
        "amusica_args", nargs=argparse.REMAINDER,
        help="Subcommand and arguments (scan, halt, control, inject, record, status). Use 'bleep amusica --help' for details.",
    )

    audo_conf = subparsers.add_parser("audio-config", help="Manage ALSA/BlueALSA configuration for Bluetooth audio")
    audo_sub = audo_conf.add_subparsers(dest="action", help="Configuration action")

    audo_show = audo_sub.add_parser("show", help="Show current ALSA config entries")
    audo_show.add_argument("--path", default=None, help="Override config file path")

    audo_add = audo_sub.add_parser("add", help="Add a BlueALSA PCM device entry")
    audo_add.add_argument("address", help="Bluetooth MAC (00:00:00:00:00:00 for most-recent)")
    audo_add.add_argument("--type", dest="device_type", default="sink", choices=["sink", "source"], help="Device type (default: sink)")
    audo_add.add_argument("--path", default=None, help="Override config file path")

    audo_rm = audo_sub.add_parser("remove", help="Remove BlueALSA entries for a MAC")
    audo_rm.add_argument("address", help="Bluetooth MAC to remove")
    audo_rm.add_argument("--path", default=None, help="Override config file path")

    audo_tunnel = audo_sub.add_parser("tunnel", help="Create audio tunnel between two BT devices")
    audo_tunnel.add_argument("source", help="Source device MAC")
    audo_tunnel.add_argument("sink", help="Sink device MAC")
    audo_tunnel.add_argument("--path", default=None, help="Override config file path")

    audo_backup = audo_sub.add_parser("backup", help="Backup current ALSA config")
    audo_backup.add_argument("--path", default=None, help="Override config file path")

    audo_restore = audo_sub.add_parser("restore", help="Restore ALSA config from latest backup")
    audo_restore.add_argument("--path", default=None, help="Override config file path")

    aint_parser = subparsers.add_parser(
        "audio-intercept",
        help="Capture and optionally transcribe audio from a Bluetooth device",
    )
    aint_parser.add_argument("address", help="Source device MAC address")
    aint_parser.add_argument("--duration", type=int, default=10, help="Capture duration in seconds (default: 10)")
    aint_parser.add_argument("--output-dir", default="/tmp", help="Directory for captured WAV (default: /tmp)")
    aint_parser.add_argument("--pcm", default=None, help="ALSA PCM device (auto-derived if omitted)")
    aint_parser.add_argument("--no-transcribe", action="store_true", help="Skip transcription step")
    aint_parser.add_argument("--engine", choices=["whisper", "vosk"], default=None,
                             help="Force transcription engine")
    _subparser_map["audio-intercept"] = aint_parser
