"""bleep.gatt – GATT operation helpers (refactoring target).

This package is the intended destination for GATT-related logic currently
spread across ``bleep/dbuslayer/`` (service.py, characteristic.py,
descriptor.py) and ``bleep/ble_ops/le/`` (scan.py, scan_modes.py,
connect.py).  Breaking those into smaller, focused modules under this
package is planned for a future refactor to keep individual files under
~300 LOC.

Current GATT wrappers remain functional in their existing locations:
- ``bleep.dbuslayer.service`` — GattService1 D-Bus wrapper
- ``bleep.dbuslayer.characteristic`` — GattCharacteristic1 D-Bus wrapper
- ``bleep.dbuslayer.descriptor`` — GattDescriptor1 D-Bus wrapper

As modules are migrated here, they will be re-exported from this
__init__.py for backward compatibility.
"""

__all__: list = []
