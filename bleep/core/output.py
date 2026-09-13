"""Structured output protocol for BLEEP CLI modes.

Provides the ``OutputContext`` dataclass that formalizes how modes emit
structured data (results) vs. progress/status messages.  The reference
implementation is Survey Mode, which routes data to stdout/file and
progress to stderr.

Usage::

    from bleep.core.output import OutputContext, output_from_args

    output = output_from_args(args)
    output.emit_progress("[scan] Starting...")
    output.emit_result({"devices": [...]})
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from typing import Any, IO, Literal

import argparse

__all__ = ["OutputMode", "OutputContext", "output_from_args"]

OutputMode = Literal["terminal", "json", "quiet"]


@dataclass
class OutputContext:
    """Controls how a CLI mode emits output.

    Attributes
    ----------
    mode:
        ``"terminal"`` — human-readable output (default, modes handle own printing).
        ``"json"`` — structured JSON to ``stream``; progress to ``progress``.
        ``"quiet"`` — suppress progress; only emit structured results.
    stream:
        Destination for structured data (default: stdout).
    progress:
        Destination for progress/status messages (default: stderr).
    """

    mode: OutputMode = "terminal"
    stream: IO[str] = field(default_factory=lambda: sys.stdout)
    progress: IO[str] = field(default_factory=lambda: sys.stderr)

    def emit_result(self, data: Any) -> None:
        """Emit structured result data.

        In ``json`` mode, serializes ``data`` as a single JSON line.
        In ``quiet`` mode, same behavior (results are never suppressed).
        In ``terminal`` mode, this is a no-op — modes handle their own
        terminal formatting.

        ``data`` may be a dict, list, or any JSON-serializable value.
        """
        if self.mode in ("json", "quiet"):
            self.stream.write(json.dumps(data, default=str, ensure_ascii=False) + "\n")
            self.stream.flush()

    def emit_progress(self, msg: str) -> None:
        """Emit a progress/status message.

        Writes to ``progress`` stream (stderr) unless mode is ``quiet``.
        """
        if self.mode != "quiet":
            self.progress.write(msg + "\n")
            self.progress.flush()

    @property
    def is_terminal(self) -> bool:
        """True when running in default human-readable terminal mode."""
        return self.mode == "terminal"

    @property
    def is_json(self) -> bool:
        """True when structured JSON output is requested."""
        return self.mode == "json"

    @property
    def is_quiet(self) -> bool:
        """True when progress output is suppressed."""
        return self.mode == "quiet"

    def close(self) -> None:
        """Close the output stream if it was opened to a file."""
        if self.stream not in (sys.stdout, sys.stderr):
            try:
                self.stream.close()
            except Exception:
                pass


def output_from_args(args: argparse.Namespace) -> OutputContext:
    """Construct an OutputContext from parsed CLI arguments.

    Expects ``args.output_mode`` to be set by the global ``--json``/``--quiet``
    flags added to the top-level parser.  Falls back to ``"terminal"`` if the
    attribute is missing (backward compatibility with modes that don't yet
    pass through the global flags).

    When in json/quiet mode and the args contain a file output path (checked
    via ``args.output`` or ``args.out``), the ``stream`` is opened to that
    file so ``emit_result()`` writes structured data there automatically.
    Callers that handle file output themselves (e.g. survey with format
    selection) should NOT pass a file arg or should set ``stream`` after
    construction.
    """
    mode: OutputMode = getattr(args, "output_mode", "terminal") or "terminal"
    stream: IO[str] = sys.stdout

    if mode in ("json", "quiet"):
        out_path = getattr(args, "output", None) or getattr(args, "out", None)
        if out_path:
            from pathlib import Path
            p = Path(out_path) if not isinstance(out_path, Path) else out_path
            p.parent.mkdir(parents=True, exist_ok=True)
            stream = open(p, "w", encoding="utf-8")  # noqa: SIM115

    return OutputContext(mode=mode, stream=stream)
