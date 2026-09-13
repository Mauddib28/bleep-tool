"""Health Device Profile (HDP) stub (BZ-17).

BlueZ provided ``org.bluez.HealthManager1``, ``org.bluez.HealthDevice1``, and
``org.bluez.HealthChannel1`` interfaces for the Bluetooth Health Device Profile
(IEEE 11073).  These were **removed from BlueZ mainline** in BlueZ 5.50+.

BLEEP does not implement HDP via D-Bus because the interfaces no longer exist
in modern BlueZ builds.  If HDP support is needed in the future, it would
require either:
  1. A custom BlueZ build with the HDP plugin re-enabled, or
  2. Direct L2CAP/MCAP channel management bypassing BlueZ D-Bus entirely.

This module exists solely as documentation and to prevent confusion when
searching for HDP support in the codebase.

Reference: ``workDir/BlueZDocs/health-api.txt`` (legacy).
"""

# Legacy interface names for reference (not usable on modern BlueZ)
HEALTH_MANAGER_INTERFACE = "org.bluez.HealthManager1"
HEALTH_DEVICE_INTERFACE = "org.bluez.HealthDevice1"
HEALTH_CHANNEL_INTERFACE = "org.bluez.HealthChannel1"

HDP_SUPPORTED = False
HDP_REMOVAL_NOTE = (
    "HDP D-Bus interfaces were removed in BlueZ 5.50+. "
    "BLEEP does not support HDP via D-Bus on modern BlueZ installations."
)
