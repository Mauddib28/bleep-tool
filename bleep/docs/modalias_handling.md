# Modalias Handling in BLEEP

This document describes the modalias handling system in BLEEP, which provides a centralized approach to parsing and interpreting modalias strings for Bluetooth devices.

## Overview

Modalias strings are used by the Linux kernel to match devices with drivers. In the context of Bluetooth devices, modalias strings contain valuable information about the device's vendor, product, and device ID. BLEEP uses this information to provide more detailed device information in the debug mode.

## Architecture

The modalias handling system consists of the following components:

1. **USB IDs Database**: A comprehensive database of USB vendor and product IDs, generated from the Linux USB IDs database.
2. **Modalias Parsing Utilities**: A set of utilities for parsing and interpreting modalias strings.
3. **Integration with Debug Mode**: Integration with the debug mode to display modalias information in a user-friendly format.

### USB IDs Database

The USB IDs database is generated from the official Linux USB IDs database at [linux-usb.org/usb.ids](http://www.linux-usb.org/usb.ids). This database contains thousands of vendor and product IDs, providing comprehensive coverage of USB devices.

The database is generated using the `update_usb_ids.py` script, which:

1. Downloads the USB IDs database from linux-usb.org
2. Parses the database into vendor and product dictionaries
3. Generates a Python module (`usb_ids.py`) with the dictionaries and helper functions

This approach is similar to the BT SIG UUID updater, ensuring consistent handling of external reference data.

### Modalias Parsing Utilities

The modalias parsing utilities are provided by the `bleep.ble_ops.modalias` module, which:

1. Parses modalias strings into their components (vendor ID, product ID, device ID)
2. Looks up vendor and product names in the USB IDs database
3. Formats modalias information for display

The module also provides a fallback implementation for when the USB IDs database hasn't been generated yet, ensuring robustness.

### Integration with Debug Mode

The modalias handling system is integrated with the debug mode to display modalias information in a user-friendly format. When the "detailed on" verbosity is enabled, modalias strings are parsed and displayed with vendor, product, and device ID information.

## Usage

### Updating the USB IDs Database

To update the USB IDs database, run:

```bash
python -m bleep.bt_ref.update_usb_ids
```

This will download the latest USB IDs database and generate the `usb_ids.py` module.

### Parsing Modalias Strings

To parse a modalias string, use the `parse_modalias` function from the `bleep.bt_ref.usb_ids` module:

```python
from bleep.bt_ref.usb_ids import parse_modalias

modalias = "usb:v05ACp820Ad0210"
info = parse_modalias(modalias)
print(info)
# {'vendor_id': '05ac', 'vendor_name': 'Apple, Inc.', 'product_id': '820a', 'product_name': 'Bluetooth HID Keyboard', 'device_id': '0210'}
```

### Formatting Modalias Information

To format modalias information for display, use the `format_modalias_info` function from the `bleep.ble_ops.modalias` module:

```python
from bleep.ble_ops.modalias import format_modalias_info

modalias = "usb:v05ACp820Ad0210"
formatted = format_modalias_info(modalias)
print(formatted)
# usb:v05ACp820Ad0210 (Vendor: Apple, Inc., Product: 0x820A, Device ID: 0x0210)
```

### Decoding PnP ID Vendor Information

To decode vendor information from a PnP ID, use the `decode_pnp_id_vendor` function from the `bleep.ble_ops.modalias` module:

```python
from bleep.ble_ops.modalias import decode_pnp_id_vendor

vendor_id_source = 2  # USB IF
vendor_id = 0x05ac  # Apple, Inc.
vendor_name = decode_pnp_id_vendor(vendor_id_source, vendor_id)
print(vendor_name)
# Apple, Inc.
```

## Modalias Format

The modalias format for USB devices follows this pattern:

```
usb:vVVVVpPPPPdDDDD
```

Where:
- `VVVV` is the vendor ID (e.g., "05ac" for Apple, Inc.)
- `PPPP` is the product ID (e.g., "820a" for a specific Apple product)
- `DDDD` is the device ID (e.g., "0210")

For more information on the modalias format, see the [ArchWiki Modalias page](https://wiki.archlinux.org/title/Modalias).

## References

- [Linux USB IDs Database](http://www.linux-usb.org/usb.ids)
- [ArchWiki Modalias](https://wiki.archlinux.org/title/Modalias)
- [Linux Kernel Documentation: Modalias](https://www.kernel.org/doc/html/latest/core-api/device_drivers.html#modalias)
