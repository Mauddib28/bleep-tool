"""
Compatibility module for legacy code.

This module provides backward compatibility for code that hasn't been updated
to use the new package structure.
"""

import warnings
from typing import Dict

from .bt_ref import constants, exceptions, utils, uuids
from .core import config, log

# Re-export all the legacy names
__all__ = [
    # Config
    "dbg",
    "general_logging",
    "debug_logging",
    "enumerate_logging",
    "usermode_logging",
    "agent_logging",
    "database_logging",
    "LOG__GENERAL",
    "LOG__DEBUG",
    "LOG__ENUM",
    "LOG__USER",
    "LOG__AGENT",
    "LOG__DATABASE",
    # Logging functions
    "logging__debug_log",
    "logging__general_log",
    "logging__enumeration_log",
    "logging__usermode_log",
    "logging__agent_log",
    "logging__database_log",
    "logging__log_event",
    "print_and_log",
]

# Config variables
dbg = config.dbg
general_logging = config.general_logging
debug_logging = config.debug_logging
enumerate_logging = config.enumerate_logging
usermode_logging = config.usermode_logging
agent_logging = config.agent_logging
database_logging = config.database_logging

# Log type constants
LOG__GENERAL = log.LOG__GENERAL
LOG__DEBUG = log.LOG__DEBUG
LOG__ENUM = log.LOG__ENUM
LOG__USER = log.LOG__USER
LOG__AGENT = log.LOG__AGENT
LOG__DATABASE = log.LOG__DATABASE

# Logging functions
logging__debug_log = log.logging__debug_log
logging__general_log = log.logging__general_log
logging__enumeration_log = log.logging__enumeration_log
logging__usermode_log = log.logging__usermode_log
logging__agent_log = log.logging__agent_log
logging__database_log = log.logging__database_log
logging__log_event = log.logging__log_event
print_and_log = log.print_and_log

# Emit deprecation warning
warnings.warn(
    "The bleep.compat module is deprecated. Use bleep.core.log and bleep.core.config instead.",
    DeprecationWarning,
    stacklevel=2,
)
