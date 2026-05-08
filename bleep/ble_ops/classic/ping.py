"""bleep.ble_ops.classic_ping – reachability check via *l2ping*.

Uses the BlueZ userspace binary; falls back gracefully if missing.
"""

from __future__ import annotations

# noqa: D400,D401  # simple docstring style
import subprocess, shutil, re
from typing import Optional, List

from bleep.core.log import print_and_log, LOG__DEBUG

_L2PING = shutil.which("l2ping")
# Match both legacy "time 23.4ms" and parenthesised variants "(23.4 ms)"
_RTT_RE = re.compile(r"time\s*([0-9.]+)\s*ms|\(([0-9.]+)\s*ms\)", re.IGNORECASE)

__all__ = ["classic_l2ping"]


def classic_l2ping(mac: str, count: int = 3, timeout: int = 13) -> tuple[Optional[float], Optional[str]]:
    """Return (rtt_ms, error).  *rtt_ms* None when failed, *error* is brief cause."""
    if not _L2PING:
        msg = "l2ping binary not found"
        print_and_log(f"[classic_l2ping] {msg}", LOG__DEBUG)
        return None, msg
    mac = mac.strip().upper()
    cmd = [_L2PING, "-c", str(count), mac]
    print_and_log("[classic_l2ping] exec: " + " ".join(cmd), LOG__DEBUG)
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except Exception as exc:
        return None, str(exc)
    if res.returncode != 0:
        err = res.stderr.strip()
        if "Operation not permitted" in err or "Permission denied" in err:
            err = "requires CAP_NET_RAW (run with sudo)"
        print_and_log(f"[classic_l2ping] non-zero exit: {err}", LOG__DEBUG)
        return None, err
    # Log raw output for troubleshooting if debugging is enabled
    print_and_log("[classic_l2ping] stdout:\n" + res.stdout.strip(), LOG__DEBUG)
    if res.stderr:
        print_and_log("[classic_l2ping] stderr:\n" + res.stderr.strip(), LOG__DEBUG)

    # _RTT_RE returns tuples due to alternation – flatten & filter empties
    rtt_values: List[str] = []
    for t in _RTT_RE.findall(res.stdout):
        # each match is a tuple (group1, group2)
        rtt_values += [v for v in t if v]

    if rtt_values:
        vals = [float(v) for v in rtt_values]
        return sum(vals) / len(vals), None

    return None, "timeout (no RTT strings parsed – check CAP_NET_RAW / Bluetooth reachability)" 