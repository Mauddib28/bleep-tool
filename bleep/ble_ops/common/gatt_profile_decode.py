"""Decode GATT characteristic values for recognized Bluetooth SIG profiles.

Covers the deprecated BlueZ plugin profiles (Health Thermometer, Heart Rate,
Cycling Speed and Cadence, Proximity/Immediate Alert/Link Loss/Tx Power) that
were removed from BlueZ 5.48+.  The underlying GATT services still exist on
devices; this module provides structured value interpretation.

Spec references:
  - GATT Specification Supplement (GSS) v12+
  - Bluetooth SIG Assigned Numbers — characteristic formats
  - IEEE 11073-20601 FLOAT type (Temperature Measurement)
"""

from __future__ import annotations

import struct
from typing import Optional, Sequence, Union

from bleep.bt_ref.constants import (
    ALERT_LEVEL_CHR_UUID,
    BODY_SENSOR_LOCATION_CHR_UUID,
    CSC_FEATURE_CHR_UUID,
    CSC_MEASUREMENT_CHR_UUID,
    HR_MEASUREMENT_CHR_UUID,
    MEASUREMENT_INTERVAL_CHR_UUID,
    SENSOR_LOCATION_CHR_UUID,
    TEMP_MEASUREMENT_CHR_UUID,
    TEMP_TYPE_CHR_UUID,
    INTERMEDIATE_TEMP_CHR_UUID,
    TX_POWER_LEVEL_CHR_UUID,
)

# ---------------------------------------------------------------------------
# Enum tables
# ---------------------------------------------------------------------------

_ALERT_LEVELS = {0: "No Alert", 1: "Mild Alert", 2: "High Alert"}

_TEMPERATURE_TYPES = {
    1: "Armpit", 2: "Body (general)", 3: "Ear (usually tympanic)",
    4: "Finger", 5: "Gastrointestinal Tract", 6: "Mouth",
    7: "Rectum", 8: "Toe", 9: "Tympanum (ear drum)",
}

_BODY_SENSOR_LOCATIONS = {
    0: "Other", 1: "Chest", 2: "Wrist", 3: "Finger",
    4: "Hand", 5: "Ear Lobe", 6: "Foot",
}

_SENSOR_LOCATIONS = {
    0: "Other", 1: "Top of shoe", 2: "In shoe", 3: "Hip",
    4: "Front Wheel", 5: "Left Crank", 6: "Right Crank",
    7: "Left Pedal", 8: "Right Pedal", 9: "Front Hub",
    10: "Rear Dropout", 11: "Chainstay", 12: "Rear Wheel",
    13: "Rear Hub", 14: "Chest", 15: "Spider", 16: "Chain Ring",
}

# IEEE 11073 FLOAT special values (mantissa portion)
_FLOAT_NAN = 0x007FFFFF
_FLOAT_NRES = 0x00800000
_FLOAT_POS_INF = 0x007FFFFE
_FLOAT_NEG_INF = 0x00800002
_FLOAT_RESERVED = 0x00800001


# ---------------------------------------------------------------------------
# IEEE 11073 FLOAT decoder
# ---------------------------------------------------------------------------

def _decode_ieee11073_float(data: bytes) -> Optional[float]:
    """Decode a 4-byte IEEE 11073-20601 FLOAT to a Python float.

    Layout (little-endian): mantissa [23:0] (signed), exponent [31:24] (signed).
    Returns None for NaN / NRes / Reserved special values.
    """
    if len(data) != 4:
        return None
    raw = struct.unpack("<I", data)[0]
    mantissa = raw & 0x00FFFFFF
    if mantissa in (_FLOAT_NAN, _FLOAT_NRES, _FLOAT_POS_INF,
                    _FLOAT_NEG_INF, _FLOAT_RESERVED):
        return None
    # Sign-extend 24-bit mantissa
    if mantissa & 0x00800000:
        mantissa -= 0x01000000
    exponent = (raw >> 24) & 0xFF
    if exponent & 0x80:
        exponent -= 256
    return mantissa * (10 ** exponent)


# ---------------------------------------------------------------------------
# Individual characteristic decoders
# ---------------------------------------------------------------------------

def _decode_temperature_measurement(data: bytes) -> Optional[str]:
    """Decode Temperature Measurement (0x2A1C) or Intermediate Temperature (0x2A1E)."""
    if len(data) < 5:
        return None
    flags = data[0]
    unit = "°F" if flags & 0x01 else "°C"
    temp = _decode_ieee11073_float(data[1:5])
    if temp is None:
        return None
    parts = [f"{temp:.2f} {unit}"]
    offset = 5
    if flags & 0x02 and offset + 7 <= len(data):
        # Time Stamp present (7 bytes) — skip for display brevity
        offset += 7
    if flags & 0x04 and offset < len(data):
        ttype = _TEMPERATURE_TYPES.get(data[offset], f"Unknown ({data[offset]})")
        parts.append(f"Type: {ttype}")
    return ", ".join(parts)


def _decode_temp_type(data: bytes) -> Optional[str]:
    """Decode Temperature Type (0x2A1D)."""
    if len(data) < 1:
        return None
    return _TEMPERATURE_TYPES.get(data[0], f"Unknown ({data[0]})")


def _decode_measurement_interval(data: bytes) -> Optional[str]:
    """Decode Measurement Interval (0x2A21) — uint16 in seconds."""
    if len(data) < 2:
        return None
    interval = struct.unpack("<H", data[:2])[0]
    if interval == 0:
        return "No periodic measurement"
    return f"{interval} s"


def _decode_hr_measurement(data: bytes) -> Optional[str]:
    """Decode Heart Rate Measurement (0x2A37)."""
    if len(data) < 2:
        return None
    flags = data[0]
    wide_hr = flags & 0x01
    offset = 1
    if wide_hr:
        if len(data) < 3:
            return None
        hr = struct.unpack("<H", data[1:3])[0]
        offset = 3
    else:
        hr = data[1]
        offset = 2

    parts = [f"{hr} bpm"]

    contact_bits = (flags >> 1) & 0x03
    if contact_bits == 2:
        parts.append("sensor contact: not detected")
    elif contact_bits == 3:
        parts.append("sensor contact: detected")

    if flags & 0x08 and offset + 2 <= len(data):
        energy = struct.unpack("<H", data[offset:offset + 2])[0]
        parts.append(f"energy: {energy} kJ")
        offset += 2

    rr_intervals = []
    if flags & 0x10:
        while offset + 2 <= len(data):
            rr_raw = struct.unpack("<H", data[offset:offset + 2])[0]
            rr_ms = round(rr_raw * 1000 / 1024)
            rr_intervals.append(f"{rr_ms} ms")
            offset += 2
    if rr_intervals:
        parts.append(f"RR: [{', '.join(rr_intervals)}]")

    return ", ".join(parts)


def _decode_body_sensor_location(data: bytes) -> Optional[str]:
    """Decode Body Sensor Location (0x2A38)."""
    if len(data) < 1:
        return None
    return _BODY_SENSOR_LOCATIONS.get(data[0], f"Unknown ({data[0]})")


def _decode_alert_level(data: bytes) -> Optional[str]:
    """Decode Alert Level (0x2A06)."""
    if len(data) < 1:
        return None
    return _ALERT_LEVELS.get(data[0], f"Unknown ({data[0]})")


def _decode_tx_power_level(data: bytes) -> Optional[str]:
    """Decode Tx Power Level (0x2A07) — int8 in dBm."""
    if len(data) < 1:
        return None
    power = struct.unpack("<b", data[:1])[0]
    return f"{power} dBm"


def _decode_csc_measurement(data: bytes) -> Optional[str]:
    """Decode CSC Measurement (0x2A5B)."""
    if len(data) < 1:
        return None
    flags = data[0]
    parts = []
    offset = 1

    if flags & 0x01:
        if offset + 6 > len(data):
            return None
        wheel_revs = struct.unpack("<I", data[offset:offset + 4])[0]
        wheel_time = struct.unpack("<H", data[offset + 4:offset + 6])[0]
        parts.append(f"wheel: {wheel_revs} rev @ {wheel_time}/1024 s")
        offset += 6

    if flags & 0x02:
        if offset + 4 > len(data):
            return None
        crank_revs = struct.unpack("<H", data[offset:offset + 2])[0]
        crank_time = struct.unpack("<H", data[offset + 2:offset + 4])[0]
        parts.append(f"crank: {crank_revs} rev @ {crank_time}/1024 s")
        offset += 4

    return ", ".join(parts) if parts else "No data fields present"


def _decode_csc_feature(data: bytes) -> Optional[str]:
    """Decode CSC Feature (0x2A5C) — uint16 bitmask."""
    if len(data) < 2:
        return None
    features = struct.unpack("<H", data[:2])[0]
    flags = []
    if features & 0x01:
        flags.append("Wheel Revolution")
    if features & 0x02:
        flags.append("Crank Revolution")
    if features & 0x04:
        flags.append("Multiple Sensor Locations")
    return ", ".join(flags) if flags else "None"


def _decode_sensor_location(data: bytes) -> Optional[str]:
    """Decode Sensor Location (0x2A5D)."""
    if len(data) < 1:
        return None
    return _SENSOR_LOCATIONS.get(data[0], f"Unknown ({data[0]})")


# ---------------------------------------------------------------------------
# Decoder registry
# ---------------------------------------------------------------------------

_DECODERS = {
    TEMP_MEASUREMENT_CHR_UUID: _decode_temperature_measurement,
    INTERMEDIATE_TEMP_CHR_UUID: _decode_temperature_measurement,
    TEMP_TYPE_CHR_UUID: _decode_temp_type,
    MEASUREMENT_INTERVAL_CHR_UUID: _decode_measurement_interval,
    HR_MEASUREMENT_CHR_UUID: _decode_hr_measurement,
    BODY_SENSOR_LOCATION_CHR_UUID: _decode_body_sensor_location,
    ALERT_LEVEL_CHR_UUID: _decode_alert_level,
    TX_POWER_LEVEL_CHR_UUID: _decode_tx_power_level,
    CSC_MEASUREMENT_CHR_UUID: _decode_csc_measurement,
    CSC_FEATURE_CHR_UUID: _decode_csc_feature,
    SENSOR_LOCATION_CHR_UUID: _decode_sensor_location,
}

DECODABLE_CHAR_UUIDS = frozenset(_DECODERS.keys())


# ---------------------------------------------------------------------------
# Public facade
# ---------------------------------------------------------------------------

def decode_characteristic_value(
    char_uuid: str,
    raw: Union[bytes, bytearray, Sequence[int]],
) -> Optional[str]:
    """Decode a GATT characteristic value if a profile-specific decoder exists.

    Parameters
    ----------
    char_uuid : str
        Full 128-bit UUID of the characteristic (lowercase, dashed).
    raw : bytes | bytearray | list[int]
        Raw bytes read from the characteristic.

    Returns
    -------
    str or None
        Human-readable decoded value, or *None* if UUID is not recognized
        or decoding fails.
    """
    decoder = _DECODERS.get(char_uuid.upper())
    if decoder is None:
        return None
    if isinstance(raw, (list, tuple)):
        raw = bytes(raw)
    try:
        return decoder(raw)
    except Exception:
        return None
