"""
Core logging functionality for BLEEP.

This module provides a centralized logging system that maintains backward compatibility
with the original logging implementation while providing a cleaner interface.
"""

import logging
import sys
from pathlib import Path
from typing import Dict, Optional, Union
from . import config

# Re-export log type constants for external modules
LOG__GENERAL = config.LOG__GENERAL
LOG__DEBUG = config.LOG__DEBUG
LOG__ENUM = config.LOG__ENUM
LOG__USER = config.LOG__USER
LOG__AGENT = config.LOG__AGENT
LOG__DATABASE = config.LOG__DATABASE

# Legacy paths for backward compatibility
_LEGACY_PATHS: Dict[str, str] = {
    LOG__GENERAL: "/tmp/bti__logging__general.txt",
    LOG__DEBUG: "/tmp/bti__logging__debug.txt",
    LOG__ENUM: "/tmp/bti__logging__enumeration.txt",
    LOG__USER: "/tmp/bti__logging__usermode.txt",
    LOG__AGENT: "/tmp/bti__logging__agent.txt",
    LOG__DATABASE: "/tmp/bti__logging__database.txt",
}

# ---------------------------------------------------------------------------
# Internal file locations & legacy symlinks  (restores original design)
# ---------------------------------------------------------------------------
# Actual log records are stored under the per-user data directory to avoid
# littering /tmp.  We keep backward-compatibility by creating symlinks at the
# legacy paths that point at these real files.
_INTERNAL_PATHS: Dict[str, Path] = {
    LOG__GENERAL: config.LOG_DIR / "general.log",
    LOG__DEBUG: config.LOG_DIR / "debug.log",
    LOG__ENUM: config.LOG_DIR / "enumeration.log",
    LOG__USER: config.LOG_DIR / "usermode.log",
    LOG__AGENT: config.LOG_DIR / "agent.log",
    LOG__DATABASE: config.LOG_DIR / "database.log",
}

for _log_type, _internal_path in _INTERNAL_PATHS.items():
    # Ensure the target directory exists and the file is present so
    # Path.exists() on the symlink returns True immediately.
    _internal_path.parent.mkdir(parents=True, exist_ok=True)
    _internal_path.touch(exist_ok=True)

    _legacy_path = Path(_LEGACY_PATHS[_log_type])
    try:
        if _legacy_path.is_symlink() or _legacy_path.exists():
            # Remove stale file/symlink before recreating to ensure it points at
            # the correct, current target.
            _legacy_path.unlink()
        _legacy_path.symlink_to(_internal_path)
    except Exception:
        # As a fallback (e.g., no permission to symlink on some filesystems) we
        # create a plain file at the legacy location so code that expects it
        # can still write or at least detect its presence.
        _legacy_path.touch(exist_ok=True)

# Use the internal paths for all logging handlers going forward
_LOG_PATHS: Dict[str, Path] = _INTERNAL_PATHS

# Formatter identical to legacy (raw message only)
_formatter = logging.Formatter("%(message)s")

# Create and configure handlers
_handlers: Dict[str, logging.Handler] = {}
for log_type, path in _LOG_PATHS.items():
    handler = logging.FileHandler(path, mode="a", encoding="utf-8")
    handler.setFormatter(_formatter)
    _handlers[log_type] = handler

# Root logger for BLEEP
_logger = logging.getLogger("bleep")
_logger.setLevel(logging.INFO)
for handler in _handlers.values():
    _logger.addHandler(handler)

# Clean up temporary variables
del log_type, path, handler


def _emit(line: str, log_type: str) -> None:
    """Internal helper to emit log records without altering the original message."""
    if not line.endswith("\n"):
        line += "\n"
    record = logging.LogRecord(
        name=f"bleep.{log_type.lower()}",
        level=logging.INFO,
        pathname=__file__,
        lineno=0,
        msg=line.rstrip("\n"),
        args=(),
        exc_info=None,
    )
    _handlers.get(log_type, _handlers[LOG__GENERAL]).handle(record)


# Legacy-compatible logging functions
def logging__debug_log(msg: str) -> None:
    """Write to debug log."""
    _emit(msg, LOG__DEBUG)


def logging__general_log(msg: str) -> None:
    """Write to general log."""
    _emit(msg, LOG__GENERAL)


def logging__enumeration_log(msg: str) -> None:
    """Write to enumeration log."""
    _emit(msg, LOG__ENUM)


def logging__usermode_log(msg: str) -> None:
    """Write to usermode log."""
    _emit(msg, LOG__USER)


def logging__agent_log(msg: str) -> None:
    """Write to agent log."""
    _emit(msg, LOG__AGENT)


def logging__database_log(msg: str) -> None:
    """Write to database log."""
    _emit(msg, LOG__DATABASE)


# Map log type to function for convenience
_log_func_map = {
    LOG__GENERAL: logging__general_log,
    LOG__DEBUG: logging__debug_log,
    LOG__ENUM: logging__enumeration_log,
    LOG__USER: logging__usermode_log,
    LOG__AGENT: logging__agent_log,
    LOG__DATABASE: logging__database_log,
}


def logging__log_event(log_type: str, string_to_log: str) -> None:
    """Log an event to the specified log type."""
    _log_func_map.get(log_type, logging__general_log)(string_to_log)


def print_and_log(output_string: str, log_type: str = LOG__GENERAL) -> None:
    """Print to stdout and log to the specified log type."""
    if log_type not in (LOG__DEBUG, LOG__ENUM):
        print(output_string)
    logging__log_event(log_type, output_string)


# Modern interface
def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Get a logger with the specified name.

    This is the preferred way to get a logger in new code.
    The logger will automatically handle writing to the appropriate log files.
    """
    if name:
        return _logger.getChild(name)
    return _logger
