from __future__ import annotations

"""High-level helpers for repeated reads and brute-force writes.

These build on the public read/write methods of the device wrappers so no new
D-Bus logic is duplicated here.
"""

from typing import Dict, Any, List, Union, Tuple, Optional
import time

from bleep.core.log import print_and_log, LOG__DEBUG
from bleep.core import errors as _errors

__all__ = [
    "multi_read_characteristic",
    "multi_read_all",
    "small_write_probe",
    "build_payload_iterator",
    "brute_write_range",
]


def multi_read_characteristic(
    device,
    char_uuid: str,
    *,
    repeats: int = 10,
    delay: float = 0.2,
) -> List[Union[bytes, str]]:
    """Read *char_uuid* *repeats* times.

    Returns list of values (or error strings) in chronological order.
    """
    values: List[Union[bytes, str]] = []
    for i in range(repeats):
        try:
            val = device.read_characteristic(char_uuid)
            values.append(val)
            print_and_log(f"[multi-read] {char_uuid}  round {i+1}/{repeats}: {val}", LOG__DEBUG)
        except Exception as exc:
            values.append(f"ERROR: {exc}")
            print_and_log(f"[multi-read] {char_uuid}  round {i+1}/{repeats}: ERROR {exc}", LOG__DEBUG)
        time.sleep(delay)
    return values


def _need_mapping(device, mapping: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if mapping is not None:
        return mapping
    mapping = getattr(device, "ble_device__mapping", {})
    if not mapping:
        _ = device.services_resolved(deep=False)
        mapping = getattr(device, "ble_device__mapping", {})
    return mapping


def multi_read_all(
    device,
    mapping: Dict[str, Any] | None = None,
    *,
    rounds: int = 3,
    delay: float = 0.05,
) -> Dict[int, Dict[str, Union[bytes, str]]]:
    """Perform *rounds* passes over every readable characteristic.

    Returns dict keyed by round number → label/value map.
    """
    mapping = _need_mapping(device, mapping)
    result: Dict[int, Dict[str, Union[bytes, str]]] = {}
    from bleep.ble_ops.brute import brute_read_all  # reuse

    for r in range(1, rounds + 1):
        result[r] = brute_read_all(device, mapping=mapping, delay=delay)
        # persist values if observation db available
        try:
            from bleep.core import observations as _obs  # type: ignore
        except Exception:
            _obs = None  # type: ignore
        if _obs is not None:
            mac = getattr(device, "address", None) or getattr(device, "get_address", lambda: None)()
            if mac:
                for svc_uuid, svc_data in mapping.items():
                    for char_uuid, char_data in svc_data.get("chars", {}).items():
                        label = char_data.get("label", char_uuid)
                        val = result[r].get(label)
                        if isinstance(val, (bytes, bytearray)):
                            try:
                                _obs.insert_char_history(mac, svc_uuid, char_uuid, bytes(val))  # type: ignore[attr-defined]
                            except Exception:
                                pass
    return result

# ---------------------------------------------------------------------------
# Small write probe (pokey enum) --------------------------------------------
# ---------------------------------------------------------------------------


def small_write_probe(
    device,
    mapping: Dict[str, Any],
    *,
    delay: float = 0.1,
    verify: bool = False,
):
    """Write 0x00 and 0x01 to every *writable characteristic* (skips descriptors).

    Reads back once after writes when *verify* is True.  All operations are
    logged; errors are swallowed so enumeration continues.
    """
    from bleep.ble_ops.ctf import _to_bytearray

    zero = _to_bytearray([0x00])
    one = _to_bytearray([0x01])

    for svc_uuid, svc_data in mapping.items():
        for char_uuid, char_data in svc_data.get("chars", {}).items():
            # Skip descriptors (heuristic: char_uuid contains "desc" key alias)
            if char_uuid.lower().startswith("desc"):
                continue
            props = char_data.get("properties", {})
            if not props.get("write", False):
                continue
            label = char_data.get("label", char_uuid)
            for payload in (zero, one):
                try:
                    device.write_characteristic(char_uuid, payload)
                    print_and_log(f"[pokey-write] {label} => {list(payload)}", LOG__DEBUG)
                    if verify:
                        val = device.read_characteristic(char_uuid)
                        print_and_log(f"[pokey-read ] {label} <= {val}", LOG__DEBUG)
                except Exception as exc:
                    print_and_log(f"[pokey-write] {label}: ERROR {exc}", LOG__DEBUG)
                time.sleep(delay)


# ---------------------------------------------------------------------------
# Payload iterator builder for brute ---------------------------------------
# ---------------------------------------------------------------------------


def _ascii_patterns():
    ascii_set = [ord(c) for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"]
    for b in ascii_set:
        yield bytes([b])


def _increment_patterns(max_len: int = 4):
    seq = b"\x00"
    while len(seq) <= max_len:
        yield seq
        seq += bytes([len(seq) & 0xFF])


def build_payload_iterator(
    *,
    value_range: tuple[int, int] | None = (0x00, 0xFF),
    patterns: List[str] | None = None,
    file_bytes: bytes | None = None,
) -> List[bytes]:
    """Return list of payloads according to CLI flags."""
    payloads: List[bytes] = []
    if value_range:
        start, end = value_range
        payloads.extend(bytes([v]) for v in range(start, end + 1))
    if patterns:
        for p in patterns:
            if p == "ascii":
                payloads.extend(_ascii_patterns())
            elif p in {"inc", "increment"}:
                payloads.extend(_increment_patterns())
            elif p == "alt":
                # Alternating 0xAA / 0x55 single-byte patterns – good for bit-flip tests
                payloads.extend([b"\xAA", b"\x55"])
            elif p.startswith("repeat:"):
                # repeat:<byte>:<len>  → e.g. repeat:ff:4  generates 0xFF repeated length
                try:
                    _, byte_hex, length_str = p.split(":", 2)
                    length = int(length_str, 0)
                    bval = int(byte_hex, 16) & 0xFF
                    payloads.append(bytes([bval]) * length)
                except Exception:
                    continue  # ignore malformed pattern
            elif p.startswith("hex:"):
                # hex:<deadbeef>  → raw bytes 0xDE 0xAD 0xBE 0xEF
                try:
                    hexstr = p.split(":", 1)[1]
                    payloads.append(bytes.fromhex(hexstr))
                except Exception:
                    continue
    if file_bytes:
        payloads.append(file_bytes)
    # deduplicate while preserving order
    seen = set()
    uniq: List[bytes] = []
    for pl in payloads:
        if pl not in seen:
            uniq.append(pl)
            seen.add(pl)
    return uniq


def multi_write_all(
    device,
    mapping: Dict[str, Any],
    *,
    payloads: List[bytes],
    delay: float = 0.05,
    verify: bool = False,
    respect_roeng: bool = True,
    landmine_map: Optional[Dict[str, List[str]]] = None,
):
    """Write *payloads* to every writable characteristic in *mapping*.

    Raises
    ------
    RuntimeError
        When *device* object does not expose ``write_characteristic`` – an
        indicator that the native BlueZ/GI runtime is not available in the
        current environment.  This mirrors the guard in ``ble_ops.scan`` and
        avoids silently failing in headless test environments.
    """
    if not hasattr(device, "write_characteristic"):
        raise RuntimeError(
            "Device object missing write_characteristic – native BlueZ stack not "
            "loaded or incorrect object passed to multi_write_all()."
        )


    write_res: Dict[str, Dict[bytes, str]] = {}
    for svc_uuid, svc_data in mapping.items():
        for char_uuid, char_data in svc_data.get("chars", {}).items():
            props = char_data.get("properties", {})
            if not props.get("write", False):
                continue
            label = char_data.get("label", char_uuid)
            if respect_roeng and landmine_map and label in landmine_map.get("landmines", []):
                continue
            try:
                res = brute_write_range(
                    device,
                    char_uuid,
                    payloads=payloads,
                    delay=delay,
                    verify=verify,
                    respect_roeng=respect_roeng,
                    landmine_map=landmine_map,
                )
                write_res[label] = res
            except Exception as exc:
                print_and_log(f"[multi-write] {label}: ERROR {exc}", LOG__DEBUG)
    return write_res


def brute_write_range(
    device,
    char_uuid: str,
    *,
    payloads: List[bytes],
    delay: float = 0.05,
    verify: bool = False,
    respect_roeng: bool = True,
    landmine_map: Optional[Dict[str, List[str]]] = None,
) -> Dict[bytes, str]:
    """Write each payload to *char_uuid*.

    ``payloads`` is produced by ``build_payload_iterator``.
    Returns ``{payload: 'OK'|'ERROR:…'}`` mapping (payload as bytes key).
    """

    if respect_roeng and landmine_map:
        if char_uuid in landmine_map.get("landmine", []) or char_uuid in landmine_map.get("permission", []):
            print_and_log(f"[brute-skip] {char_uuid} flagged by ROE – skipping", LOG__DEBUG)
            return {b"": "SKIP"}

    from bleep.ble_ops.ctf import _to_bytearray

    results: Dict[bytes, str] = {}
    for pl in payloads:
        ba = _to_bytearray(pl)
        try:
            device.write_characteristic(char_uuid, ba)
            status = "OK"
            if verify:
                _ = device.read_characteristic(char_uuid)
            results[bytes(pl)] = status
        except Exception as exc:
            results[bytes(pl)] = f"ERROR: {exc}"
        time.sleep(delay)
    return results 