"""ALSA / BlueALSA configuration management for Bluetooth audio.

Provides helpers to read, modify, and restore ALSA configuration files
(``/etc/asound.conf`` or ``~/.asoundrc``) for BlueALSA PCM device entries.

BlueALSA convention: ``address 00:00:00:00:00:00`` targets the most
recently connected device.
"""

from __future__ import annotations

import os
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from bleep.core.log import print_and_log, LOG__DEBUG, LOG__GENERAL

# Candidate config file paths, checked in order
_SYSTEM_CONF = Path("/etc/asound.conf")
_USER_CONF = Path.home() / ".asoundrc"


@dataclass
class AsoundEntry:
    """A parsed PCM or CTL block from an ALSA configuration file."""
    name: str
    block_type: str  # "pcm" | "ctl"
    body: str  # raw text inside the braces
    mac: Optional[str] = None  # extracted Bluetooth MAC (if bluealsa)


@dataclass
class TunnelConfig:
    """Describes an ALSA loopback/dmix routing between two BT devices."""
    source_mac: str
    sink_mac: str
    source_pcm: str
    sink_pcm: str
    loopback_device: str = "hw:Loopback,0"


# ---------------------------------------------------------------------------
# Read / parse
# ---------------------------------------------------------------------------

def _resolve_config_path() -> Path:
    """Return the first existing ALSA config path, defaulting to user conf."""
    if _SYSTEM_CONF.exists():
        return _SYSTEM_CONF
    return _USER_CONF


def read_asound_conf(path: Optional[str] = None) -> Dict[str, AsoundEntry]:
    """Parse an ALSA configuration file into named entries.

    Parameters
    ----------
    path : str | None
        Override config path; defaults to system/user detection.

    Returns
    -------
    dict[str, AsoundEntry]
        Keyed by block name (e.g. ``"pcm.bluealsa_sink"``).
    """
    conf = Path(path) if path else _resolve_config_path()
    if not conf.exists():
        print_and_log(f"[alsa-config] No config file found at {conf}", LOG__DEBUG)
        return {}

    text = conf.read_text(encoding="utf-8", errors="replace")
    entries: Dict[str, AsoundEntry] = {}

    # Match top-level blocks: pcm.name { ... } or ctl.name { ... }
    pattern = re.compile(
        r"^(pcm|ctl)\.(\S+)\s*\{([^}]*)\}",
        re.MULTILINE | re.DOTALL,
    )
    for m in pattern.finditer(text):
        btype, bname, body = m.group(1), m.group(2), m.group(3)
        full_name = f"{btype}.{bname}"
        mac = _extract_mac(body)
        entries[full_name] = AsoundEntry(
            name=full_name, block_type=btype, body=body.strip(), mac=mac
        )

    print_and_log(f"[alsa-config] Parsed {len(entries)} entries from {conf}", LOG__DEBUG)
    return entries


def _extract_mac(body: str) -> Optional[str]:
    """Extract a Bluetooth MAC address from a config block body."""
    m = re.search(r"(?i)(?:device|address)\s+([0-9A-Fa-f:]{17})", body)
    return m.group(1).upper() if m else None


# ---------------------------------------------------------------------------
# Write helpers
# ---------------------------------------------------------------------------

def backup_and_restore(action: str = "backup", path: Optional[str] = None) -> Optional[str]:
    """Backup or restore the ALSA configuration file.

    Parameters
    ----------
    action : str
        ``"backup"`` to create a timestamped backup, ``"restore"`` to restore
        the latest backup.
    path : str | None
        Override config path.

    Returns
    -------
    str | None
        Path of the backup file created, or ``None`` on restore.
    """
    conf = Path(path) if path else _resolve_config_path()

    if action == "backup":
        if not conf.exists():
            print_and_log(f"[alsa-config] Nothing to back up ({conf})", LOG__DEBUG)
            return None
        ts = int(time.time())
        backup = conf.with_suffix(f".bak.{ts}")
        shutil.copy2(conf, backup)
        print_and_log(f"[alsa-config] Backup created: {backup}", LOG__GENERAL)
        return str(backup)

    if action == "restore":
        # Find latest .bak.* file
        backups = sorted(conf.parent.glob(f"{conf.name}.bak.*"), reverse=True)
        if not backups:
            print_and_log("[alsa-config] No backups found", LOG__GENERAL)
            return None
        shutil.copy2(backups[0], conf)
        print_and_log(f"[alsa-config] Restored from {backups[0]}", LOG__GENERAL)
        return None

    raise ValueError(f"Unknown action: {action!r} (expected 'backup' or 'restore')")


def _bluealsa_pcm_block(name: str, mac: str, profile: str = "a2dp", direction: str = "sink") -> str:
    """Generate an ALSA config block for a BlueALSA PCM device."""
    return (
        f"pcm.{name} {{\n"
        f"    type bluealsa\n"
        f"    device \"{mac}\"\n"
        f"    profile \"{profile}\"\n"
        f"    delay 20000\n"
        f"}}\n"
    )


def _bluealsa_ctl_block(name: str, mac: str) -> str:
    """Generate an ALSA CTL block for a BlueALSA device."""
    return (
        f"ctl.{name} {{\n"
        f"    type bluealsa\n"
        f"}}\n"
    )


def configure_bluealsa_device(
    mac: str,
    device_type: str = "sink",
    *,
    config_path: Optional[str] = None,
    auto_backup: bool = True,
) -> bool:
    """Add a BlueALSA PCM device entry to the ALSA config.

    Parameters
    ----------
    mac : str
        Bluetooth MAC address (``"00:00:00:00:00:00"`` for most-recent device).
    device_type : str
        ``"sink"`` (playback) or ``"source"`` (capture).
    config_path : str | None
        Override config file path.
    auto_backup : bool
        Create a backup before modification.

    Returns
    -------
    bool
        ``True`` if the entry was written successfully.
    """
    mac = mac.strip().upper()
    conf = Path(config_path) if config_path else _USER_CONF
    safe_mac = mac.replace(":", "_")
    pcm_name = f"bt_{safe_mac}_{device_type}"

    if auto_backup:
        backup_and_restore("backup", str(conf))

    profile = "a2dp" if device_type == "sink" else "sco"
    block = _bluealsa_pcm_block(pcm_name, mac, profile=profile, direction=device_type)
    ctl = _bluealsa_ctl_block(f"bt_{safe_mac}", mac)

    existing = conf.read_text(encoding="utf-8") if conf.exists() else ""

    # Avoid duplicates
    if f"pcm.{pcm_name}" in existing:
        print_and_log(f"[alsa-config] Entry pcm.{pcm_name} already exists", LOG__GENERAL)
        return True

    with conf.open("a", encoding="utf-8") as f:
        f.write(f"\n# BLEEP: BlueALSA {device_type} for {mac}\n")
        f.write(block)
        if f"ctl.bt_{safe_mac}" not in existing:
            f.write(ctl)

    print_and_log(f"[alsa-config] Added pcm.{pcm_name} → {conf}", LOG__GENERAL)
    return True


def remove_bluealsa_device(mac: str, *, config_path: Optional[str] = None, auto_backup: bool = True) -> bool:
    """Remove BlueALSA PCM/CTL entries for a specific MAC address.

    Returns ``True`` if any entries were removed.
    """
    mac = mac.strip().upper()
    conf = Path(config_path) if config_path else _resolve_config_path()
    if not conf.exists():
        return False

    if auto_backup:
        backup_and_restore("backup", str(conf))

    text = conf.read_text(encoding="utf-8")
    safe_mac = mac.replace(":", "_")

    # Remove BLEEP-tagged blocks for this MAC
    pattern = re.compile(
        rf"# BLEEP:.*?{re.escape(mac)}.*?\n(?:(?:pcm|ctl)\.bt_{re.escape(safe_mac)}\S*\s*\{{[^}}]*\}}\n?)+",
        re.DOTALL,
    )
    new_text, count = pattern.subn("", text)

    if count == 0:
        print_and_log(f"[alsa-config] No BLEEP entries found for {mac}", LOG__GENERAL)
        return False

    conf.write_text(new_text, encoding="utf-8")
    print_and_log(f"[alsa-config] Removed {count} block(s) for {mac} from {conf}", LOG__GENERAL)
    return True


def create_audio_tunnel(
    source_mac: str,
    sink_mac: str,
    *,
    config_path: Optional[str] = None,
) -> TunnelConfig:
    """Configure ALSA loopback routing between two Bluetooth devices.

    Creates PCM entries for both devices and a loopback/dmix configuration
    that routes audio from ``source_mac`` through ``sink_mac``.

    Returns a :class:`TunnelConfig` describing the setup.
    """
    source_mac = source_mac.strip().upper()
    sink_mac = sink_mac.strip().upper()

    configure_bluealsa_device(source_mac, "source", config_path=config_path, auto_backup=True)
    configure_bluealsa_device(sink_mac, "sink", config_path=config_path, auto_backup=False)

    src_safe = source_mac.replace(":", "_")
    snk_safe = sink_mac.replace(":", "_")
    tunnel = TunnelConfig(
        source_mac=source_mac,
        sink_mac=sink_mac,
        source_pcm=f"bt_{src_safe}_source",
        sink_pcm=f"bt_{snk_safe}_sink",
    )
    print_and_log(
        f"[alsa-config] Tunnel configured: {source_mac} → loopback → {sink_mac}",
        LOG__GENERAL,
    )
    return tunnel
