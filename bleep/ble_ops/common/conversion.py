"""bleep.ble_ops.conversion – utility helpers originally in Functions/conversion_functions.py.

We provide implementations of conversion functions needed by the refactored codebase.
"""
from __future__ import annotations

import binascii as _binascii
from typing import Any, Dict, List, Optional, Tuple, Union

from bleep.core import log as _log
from bleep.bt_ref import utils as _bt_utils

# ---------------------------------------------------------------------------
# Core conversion functions used throughout the codebase
# ---------------------------------------------------------------------------

def convert__hex_to_ascii(string_byte_array):  # noqa: D401
    """Return ASCII decode of D-Bus byte array *string_byte_array*."""
    if not string_byte_array:
        return ""
    # Convert to raw bytes then decode ignoring errors
    try:
        raw = bytes(string_byte_array)
    except TypeError:
        # Fallback for list[int]
        raw = bytes(int(b) for b in string_byte_array)
    return raw.decode("ascii", errors="replace")

def convert__dbus_to_hex(string_byte_array):  # noqa: D401
    """Return hex string (lowercase, no prefix) of byte-array."""
    if not string_byte_array:
        return ""
    return _binascii.hexlify(bytes(string_byte_array)).decode()

# ---------------------------------------------------------------------------
# Functions needed by debug.py
# ---------------------------------------------------------------------------

def decode_class_of_device(class_value: int) -> Tuple[List[str], List[str], List[str], Optional[bool]]:
    """Decode Class of Device value into its component parts.
    
    This is a direct port of the decode__class_of_device function from the original codebase.
    It extracts the major service classes, major device class, minor device class, and fixed bits
    from a Class of Device value according to Bluetooth specifications.
    
    Parameters:
    -----------
    class_value : int
        The Class of Device value to decode
        
    Returns:
    --------
    Tuple[List[str], List[str], List[str], Optional[bool]]
        A tuple containing:
        - List of major service classes
        - List of major device classes
        - List of minor device classes
        - Fixed bits check result
    """
    # Log debug message
    _log.print_and_log("[*] Decoding Class of Device", _log.LOG__DEBUG)
    
    # Check bit length (expecting 23 bits, 0-23)
    if class_value.bit_length() != 23:
        output_log_string = "[-] Class Device bits are not of expected length (23-0); Number of bits is..."
        if class_value.bit_length() > 23:
            output_log_string += "More"
        elif class_value.bit_length() < 23:
            output_log_string += "Less"
        else:
            output_log_string += "Unknown"
        output_log_string += f"\t-\t{class_value.bit_length()}"
        _log.print_and_log(output_log_string, _log.LOG__DEBUG)
    else:
        _log.print_and_log(f"[+] Class Device bits are of expected length (23-0); Number of bits is...\t-\t{class_value.bit_length()}", _log.LOG__DEBUG)

    # Create string of only the binary information
    class_binary_string = format(class_value, 'b').zfill(24)  # Extend to 24 bits
    
    # Extract the different parts
    major_service_classes = class_binary_string[0:11]  # Bits 23 to 13
    major_device_class = class_binary_string[11:16]    # Bits 12 to 8
    minor_device_class = class_binary_string[16:22]    # Bits 7 to 2
    fixed_value_bits = class_binary_string[22:24]      # Bits 1 to 0
    
    # Debug output if needed
    debug_output = f"[?] Extraction Check:\n\tFull Binary String:\t{class_binary_string}\n\tMajor Service Classes:\t{major_service_classes}\n\tMajor Device Class:\t{major_device_class}\n\tMinor Device Class:\t{minor_device_class}\n\tFixed Bits Data:\t{fixed_value_bits}"
    _log.print_and_log(debug_output, _log.LOG__DEBUG)
    
    # Setup Variables
    list__major_service_classes = []
    list__major_device_class = []
    list__minor_device_class = []
    fixed_bits_check = None
    
    # Convert binary strings to integer from base 2
    int__major_service_classes = int(major_service_classes, 2)
    int__major_device_class = int(major_device_class, 2)
    int__minor_device_class = int(minor_device_class, 2)
    
    # Major Service Classes
    if int__major_service_classes & 0b00000000001:  # Limited Discoverable Mode [ bit 13 ]
        list__major_service_classes.append('Limited Discoverable Mode')
    if int__major_service_classes & 0b00000000010:  # LE Audio [ bit 14 ]
        list__major_service_classes.append('LE Audio')
    if int__major_service_classes & 0b00000000100:  # Reserved for Future Use [ bit 15 ]
        list__major_service_classes.append('Reserved for Future Use')
    if int__major_service_classes & 0b00000001000:  # Positioning (Location identification) [ bit 16 ]
        list__major_service_classes.append('Positioning (Location identification)')
    if int__major_service_classes & 0b00000010000:  # Networking (LAN, Ad hoc, ...) [ bit 17 ]
        list__major_service_classes.append('Networking (LAN, Ad hoc, ...)')
    if int__major_service_classes & 0b00000100000:  # Rendering (Printing, Speakers, ...) [ bit 18 ]
        list__major_service_classes.append('Rendering (Printing, Speakers, ...)')
    if int__major_service_classes & 0b00001000000:  # Capturing (Scanner, Microphone, ...) [ bit 19 ]
        list__major_service_classes.append('Capturing (Scanner, Microphone, ...)')
    if int__major_service_classes & 0b00010000000:  # Object Transfer (v-Inbox, v-Folder, ...) [ bit 20 ]
        list__major_service_classes.append('Object Transfer (v-Inbox, v-Folder, ...)')
    if int__major_service_classes & 0b00100000000:  # Audio (Speaker, Microphone, Headset service, ...) [ bit 21 ]
        list__major_service_classes.append('Audio (Speaker, Microphone, Headset service, ...)')
    if int__major_service_classes & 0b01000000000:  # Telephony (Cordless telephony, Modem, Headset service, ...) [ bit 22 ]
        list__major_service_classes.append('Telephony (Cordless telephony, Modem, Headset service, ...)')
    if int__major_service_classes & 0b10000000000:  # Information (WEB-server, WAP-server, ...) [ bit 23 ]
        list__major_service_classes.append('Information (WEB-server, WAP-server, ...)')
    
    # Major Device Classes; NOTE: Should be only one Major Device Class
    if int__major_device_class == 0b11111:  # Uncategorized (device code not specified) [ all bits ]
        list__major_device_class.append('Uncategorized (device code not specified)')
    if int__major_device_class == 0b00001:  # Computer (desktop, notebook, PDA, organizer, ...) [ bit 8 ]
        list__major_device_class.append('Computer (desktop, notebook, PDA, organizer, ...)')
    if int__major_device_class == 0b00010:  # Phone (cellular, cordless, pay phone, modem, ...) [ bit 9 ]
        list__major_device_class.append('Phone (cellular, cordless, pay phone, modem, ...)')
    if int__major_device_class == 0b00011:  # LAN/Network Access Point [ bits 9 + 8 ]
        list__major_device_class.append('LAN/Network Access Point')
    if int__major_device_class == 0b00100:  # Audio/Video (headset, speaker, stereo, video display, VCR, ...) [ bit 10 ]
        list__major_device_class.append('Audio/Video (headset, speaker, stereo, video display, VCR, ...)')
    if int__major_device_class == 0b00101:  # Peripheral (mouse, joystick, keyboard, ...) [ bits 10 + 8 ]
        list__major_device_class.append('Peripheral (mouse, joystick, keyboard, ...)')
    if int__major_device_class == 0b00110:  # Imaging (printer, scanner, camera, display, ...) [ bits 10 + 9 ]
        list__major_device_class.append('Imaging (printer, scanner, camera, display, ...)')
    if int__major_device_class == 0b00111:  # Wearable [ bits 10 + 9 + 8 ]
        list__major_device_class.append('Wearable')
    if int__major_device_class == 0b01000:  # Toy [ bit 11 ]
        list__major_device_class.append('Toy')
    if int__major_device_class == 0b01001:  # Health [ bit 11 + 8 ]
        list__major_device_class.append('Health')
    if not int__major_device_class:  # Miscellaneous [ none of the bits ]
        list__major_device_class.append('Miscellaneous')
    
    ## Minor Device Classes - depends on Major Device Class
    if 'Computer (desktop, notebook, PDA, organizer, ...)' in list__major_device_class:
        if not int__minor_device_class:  # Uncategorized
            list__minor_device_class.append('Uncategorized (code for device not assigned)')
        if int__minor_device_class == 0b000001:  # Desktop Workstation
            list__minor_device_class.append('Desktop Workstation')
        if int__minor_device_class == 0b000010:  # Server-class Computer
            list__minor_device_class.append('Server-class Computer')
        if int__minor_device_class == 0b000011:  # Laptop
            list__minor_device_class.append('Laptop')
        if int__minor_device_class == 0b000100:  # Handheld PC/PDA (clamshell)
            list__minor_device_class.append('Handheld PC/PDA (clamshell)')
        if int__minor_device_class == 0b000101:  # Palm-size PC/PDA
            list__minor_device_class.append('Palm-size PC/PDA')
        if int__minor_device_class == 0b000110:  # Wearable Computer (watch size)
            list__minor_device_class.append('Wearable Computer (watch size)')
        if int__minor_device_class == 0b000111:  # Tablet
            list__minor_device_class.append('Tablet')
    elif 'Phone (cellular, cordless, pay phone, modem, ...)' in list__major_device_class:
        if not int__minor_device_class:  # Uncategorized
            list__minor_device_class.append('Uncategorized (code for device not assigned)')
        if int__minor_device_class == 0b000001:  # Cellular
            list__minor_device_class.append('Cellular')
        if int__minor_device_class == 0b000010:  # Cordless
            list__minor_device_class.append('Cordless')
        if int__minor_device_class == 0b000011:  # Smartphone
            list__minor_device_class.append('Smartphone')
        if int__minor_device_class == 0b000100:  # Wired Modem or Voice Gateway
            list__minor_device_class.append('Wired Modem or Voice Gateway')
        if int__minor_device_class == 0b000101:  # Common ISDN Access
            list__minor_device_class.append('Common ISDN Access')
    elif 'LAN/Network Access Point' in list__major_device_class:
        # Minor Device Classes for LAN/Network Access Point Major Class
        if not int__minor_device_class:  # Fully Available + Uncategorized
            list__minor_device_class.append('Fully available')
        # Creating minor and sub-minor bit strings
        minor_string = minor_device_class[0:3]  # Bits 7 + 6 + 5
        sub_minor_string = minor_device_class[3:6]  # Bits 4 + 3 + 2
        int__minor_string = int(minor_string, 2)
        int__sub_minor_string = int(sub_minor_string, 2)
        
        # Rest of LAN/Network Access Point Minor Device Classes
        if int__minor_string == 0b001:  # 1% to 17% utilized [ bit 5 ]
            list__minor_device_class.append('1% to 17% utilized')
        if int__minor_string == 0b010:  # 17% to 33% utilized [ bit 6 ]
            list__minor_device_class.append('17% to 33% utilized')
        if int__minor_string == 0b011:  # 33% to 50% utilized [ bits 6 + 5 ]
            list__minor_device_class.append('33% to 50% utilized')
        if int__minor_string == 0b100:  # 50% to 67% utilized [ bit 7 ]
            list__minor_device_class.append('50% to 67% utilized')
        if int__minor_string == 0b101:  # 67% to 83% utilized [ bits 7 + 5 ]
            list__minor_device_class.append('67% to 83% utilized')
        if int__minor_string == 0b110:  # 83% to 99% utilized [ bits 7 + 6 ]
            list__minor_device_class.append('83% to 99% utilized')
        if int__minor_string == 0b111:  # No service available [ bits 7 + 6 + 5 ]
            list__minor_device_class.append('No service available')
            
        # Sub Minor Device Classes
        if not int__sub_minor_string:  # Uncategorized (use this value if no others apply) [ none of the bits ]
            list__minor_device_class.append('Uncategorized (use this value if no others apply)')
    elif 'Audio/Video (headset, speaker, stereo, video display, VCR, ...)' in list__major_device_class:
        if not int__minor_device_class:  # Uncategorized
            list__minor_device_class.append('Uncategorized (code not assigned)')
        if int__minor_device_class == 0b000001:  # Wearable Headset Device
            list__minor_device_class.append('Wearable Headset Device')
        if int__minor_device_class == 0b000010:  # Hands-free Device
            list__minor_device_class.append('Hands-free Device')
        if int__minor_device_class == 0b000011:  # Reserved for Future Use
            list__minor_device_class.append('Reserved for Future Use')
        if int__minor_device_class == 0b000100:  # Microphone
            list__minor_device_class.append('Microphone')
        if int__minor_device_class == 0b000101:  # Loudspeaker
            list__minor_device_class.append('Loudspeaker')
        if int__minor_device_class == 0b000110:  # Headphones
            list__minor_device_class.append('Headphones')
        if int__minor_device_class == 0b000111:  # Portable Audio
            list__minor_device_class.append('Portable Audio')
        if int__minor_device_class == 0b001000:  # Car Audio
            list__minor_device_class.append('Car Audio')
        if int__minor_device_class == 0b001001:  # Set-top box
            list__minor_device_class.append('Set-top box')
        if int__minor_device_class == 0b001010:  # HiFi Audio Device
            list__minor_device_class.append('HiFi Audio Device')
        if int__minor_device_class == 0b001011:  # VCR
            list__minor_device_class.append('VCR')
        if int__minor_device_class == 0b001100:  # Video Camera
            list__minor_device_class.append('Video Camera')
        if int__minor_device_class == 0b001101:  # Camcorder
            list__minor_device_class.append('Camcorder')
        if int__minor_device_class == 0b001110:  # Video Monitor
            list__minor_device_class.append('Video Monitor')
        if int__minor_device_class == 0b001111:  # Video Display and Loudspeaker
            list__minor_device_class.append('Video Display and Loudspeaker')
        if int__minor_device_class == 0b010000:  # Video Conferencing
            list__minor_device_class.append('Video Conferencing')
        if int__minor_device_class == 0b010001:  # Reserved for Future Use
            list__minor_device_class.append('Reserved for Future Use')
        if int__minor_device_class == 0b010010:  # Gaming/Toy
            list__minor_device_class.append('Gaming/Toy')
    
    return list__major_service_classes, list__major_device_class, list__minor_device_class, fixed_bits_check


def extract__class_of_device__service_and_class_info(
    major_service_class_info: List[str], 
    major_device_class_info: List[str], 
    minor_device_class_info: List[str], 
    device_class__fixed_bits_check: Optional[bool]
) -> Tuple[str, str, str]:
    """Format the device class information into user-friendly strings.
    
    This function takes the output from decode_class_of_device and formats it into
    human-readable service, major device, and minor device class information.
    
    Parameters:
    -----------
    major_service_class_info : List[str]
        List of major service classes
    major_device_class_info : List[str]
        List of major device classes
    minor_device_class_info : List[str]
        List of minor device classes
    device_class__fixed_bits_check : Optional[bool]
        Fixed bits check result from decode_class_of_device
        
    Returns:
    --------
    Tuple[str, str, str]
        A tuple containing (device_services, major_device, minor_device) as formatted strings
    """
    device_services, major_device, minor_device = "", "", ""
    
    # Internal Function to Extract Major and Minor Class Names
    def extract__class_name__high_level(class_name_info):
        # Grab the info before the sub-information and strip out white space
        return class_name_info.split('(')[0].rstrip()
        
    # Extract Device's Major Class
    if len(major_device_class_info) == 1 and len(minor_device_class_info) == 1:
        major_device = extract__class_name__high_level(major_device_class_info[0])
        minor_device = extract__class_name__high_level(minor_device_class_info[0])
    elif len(major_device_class_info) > 1 and len(minor_device_class_info) == 1:
        # Extract and Append Each Major Device Class Name
        for major_class_name in major_device_class_info:
            major_device += f"{extract__class_name__high_level(major_class_name)},"
        # Strip Extra Comma from End of Major Device Class Name
        major_device = major_device.rstrip(',')
        # Extract Minor Device Class
        minor_device = extract__class_name__high_level(minor_device_class_info[0])
    elif len(major_device_class_info) > 1 and len(minor_device_class_info) > 1:
        # Extract and Append Each Major Device Class Name
        for major_class_name in major_device_class_info:
            major_device += f"{extract__class_name__high_level(major_class_name)},"
        # Strip Extra Comma from End of Major Device Class Name
        major_device = major_device.rstrip(',')
        # Extract and Append Each Minor Device Class Name
        for minor_class_name in minor_device_class_info:
            minor_device += f"{extract__class_name__high_level(minor_class_name)},"
        # Strip Extra Comma from End of Minor Device Class Name
        minor_device = minor_device.rstrip(',')
    else:
        # Major and Minor Class Info were Length Zero (Does not exist)
        major_device = "-=UNKNOWN=-"
        minor_device = "-=UNKNOWN=-"

    # Extract Device's Major Services
    if len(major_service_class_info) > 0:
        # Extract and Append Each Major Device Service Name
        for major_service_name in major_service_class_info:
            device_services += f"{extract__class_name__high_level(major_service_name)},"
        # Strip Extra Comma from End of Major Device Service Name
        device_services = device_services.rstrip(',')
    else:
        # Major Service Info was Length Zero (Does not exist)
        device_services = "-=UNKNOWN=-"
    
    # Return the Extracted Information
    return device_services, major_device, minor_device


def decode_appearance(appearance_value: int) -> str:
    """Decode Bluetooth appearance value.
    
    Parameters:
    -----------
    appearance_value : int
        The appearance value to decode
        
    Returns:
    --------
    str
        The decoded appearance description
    """
    # Common appearance values based on Bluetooth SIG
    appearance_map = {
        0: "Unknown",
        64: "Generic Phone",
        128: "Generic Computer",
        192: "Generic Watch",
        193: "Watch: Sports Watch",
        256: "Generic Clock",
        320: "Generic Display",
        384: "Generic Remote Control",
        448: "Generic Eye-glasses",
        512: "Generic Tag",
        576: "Generic Keyring",
        640: "Generic Media Player",
        704: "Generic Barcode Scanner",
        768: "Generic Thermometer",
        769: "Thermometer: Ear",
        832: "Generic Heart Rate Sensor",
        833: "Heart Rate Sensor: Heart Rate Belt",
        896: "Generic Blood Pressure",
        897: "Blood Pressure: Arm",
        898: "Blood Pressure: Wrist",
        960: "Human Interface Device",
        961: "HID: Keyboard",
        962: "HID: Mouse",
        963: "HID: Joystick",
        964: "HID: Gamepad",
        965: "HID: Digitizer Tablet",
        966: "HID: Card Reader",
        967: "HID: Digital Pen",
        968: "HID: Barcode Scanner",
        1024: "Generic Glucose Meter",
        1088: "Generic Running Walking Sensor",
        1089: "Running Walking Sensor: In-Shoe",
        1090: "Running Walking Sensor: On-Shoe",
        1091: "Running Walking Sensor: On-Hip",
        1152: "Generic Cycling",
        1153: "Cycling: Cycling Computer",
        1154: "Cycling: Speed Sensor",
        1155: "Cycling: Cadence Sensor",
        1156: "Cycling: Power Sensor",
        1157: "Cycling: Speed and Cadence Sensor",
        1216: "Generic Control Device",
        1217: "Control Device: Switch",
        1218: "Control Device: Multi-switch",
        1219: "Control Device: Button",
        1220: "Control Device: Slider",
        1221: "Control Device: Rotary",
        1222: "Control Device: Touch-panel",
        1280: "Generic Network Device",
        1281: "Network Device: Access Point",
        1344: "Generic Sensor",
        1345: "Sensor: Air Quality",
        1346: "Sensor: Temperature",
        1347: "Sensor: Humidity",
        1348: "Sensor: Leak",
        1349: "Sensor: Smoke",
        1350: "Sensor: Occupancy",
        1351: "Sensor: Contact",
        1352: "Sensor: Carbon Monoxide",
        1353: "Sensor: Carbon Dioxide",
        1354: "Sensor: Ambient Light",
        1355: "Sensor: Energy",
        1356: "Sensor: Color Light",
        1357: "Sensor: Rain",
        1358: "Sensor: Fire",
        1359: "Sensor: Wind",
        1360: "Sensor: Proximity",
        1361: "Sensor: Multi-Sensor",
        1408: "Generic Light Fixtures",
        1409: "Light Fixtures: Wall Light",
        1410: "Light Fixtures: Ceiling Light",
        1411: "Light Fixtures: Floor Light",
        1412: "Light Fixtures: Cabinet Light",
        1413: "Light Fixtures: Desk Light",
        1414: "Light Fixtures: Troffer Light",
        1415: "Light Fixtures: Pendant Light",
        1416: "Light Fixtures: In-ground Light",
        1417: "Light Fixtures: Flood Light",
        1418: "Light Fixtures: Underwater Light",
        1419: "Light Fixtures: Bollard with Light",
        1420: "Light Fixtures: Pathway Light",
        1421: "Light Fixtures: Garden Light",
        1422: "Light Fixtures: Pole-top Light",
        1423: "Light Fixtures: Spotlight",
        1424: "Light Fixtures: Linear Light",
        1425: "Light Fixtures: Street Light",
        1426: "Light Fixtures: Shelves Light",
        1427: "Light Fixtures: High-bay / Low-bay Light",
        1428: "Light Fixtures: Emergency Exit Light",
        1472: "Generic Fan",
        1473: "Fan: Ceiling Fan",
        1474: "Fan: Axial Fan",
        1475: "Fan: Exhaust Fan",
        1476: "Fan: Pedestal Fan",
        1477: "Fan: Desk Fan",
        1478: "Fan: Wall Fan",
        1536: "Generic HVAC",
        1537: "HVAC: Thermostat",
        1600: "Generic Air Conditioning",
        1664: "Generic Humidifier",
        1728: "Generic Heating",
        1729: "Heating: Radiator",
        1730: "Heating: Boiler",
        1731: "Heating: Heat Pump",
        1732: "Heating: Infrared Heater",
        1733: "Heating: Radiant Panel Heater",
        1734: "Heating: Fan Heater",
        1735: "Heating: Air Curtain",
        1792: "Generic Access Control",
        1793: "Access Control: Access Door",
        1794: "Access Control: Garage Door",
        1795: "Access Control: Emergency Exit Door",
        1796: "Access Control: Access Lock",
        1797: "Access Control: Elevator",
        1798: "Access Control: Window",
        1799: "Access Control: Entrance Gate",
        1856: "Generic Motorized Device",
        1857: "Motorized Device: Motorized Gate",
        1858: "Motorized Device: Awning",
        1859: "Motorized Device: Blinds or Shades",
        1860: "Motorized Device: Curtains",
        1861: "Motorized Device: Screen",
        1920: "Generic Power Device",
        1921: "Power Device: Power Outlet",
        1922: "Power Device: Power Strip",
        1923: "Power Device: Plug",
        1924: "Power Device: Power Supply",
        1925: "Power Device: LED Driver",
        1926: "Power Device: Fluorescent Lamp Gear",
        1927: "Power Device: HID Lamp Gear",
        1984: "Generic Light Source",
        1985: "Light Source: Incandescent Light Bulb",
        1986: "Light Source: LED Lamp",
        1987: "Light Source: HID Lamp",
        1988: "Light Source: Fluorescent Lamp",
        1989: "Light Source: LED Array",
        1990: "Light Source: Multi-Color LED Array",
        3136: "Generic: Pulse Oximeter",
        3137: "Pulse Oximeter: Fingertip",
        3138: "Pulse Oximeter: Wrist Worn",
        3152: "Generic: Weight Scale",
        3184: "Generic: Personal Mobility Device",
        3185: "Personal Mobility Device: Powered Wheelchair",
        3186: "Personal Mobility Device: Mobility Scooter",
        3200: "Generic: Continuous Glucose Monitor",
        3264: "Generic: Insulin Pump",
        3265: "Insulin Pump: Insulin Pump, durable",
        3266: "Insulin Pump: Insulin Pump, patch",
        3267: "Insulin Pump: Insulin Pen",
        3280: "Generic: Medication Delivery",
        3296: "Generic: Spirometer",
        3297: "Spirometer: Handheld Spirometer",
    }
    
    result = appearance_map.get(appearance_value)
    if result:
        return result
    # Fall back to SIG table (category / subcategory hierarchy)
    sig_name = _resolve_appearance_sig(appearance_value)
    if sig_name:
        return sig_name
    return f"Unknown (0x{appearance_value:04x})"


def decode_pnp_id(pnp_data: bytes) -> str:
    """Decode PnP ID characteristic value.
    
    PnP ID format (7 bytes):
    - Byte 0: Vendor ID Source (1=Bluetooth SIG, 2=USB Implementers Forum)
    - Bytes 1-2: Vendor ID (little-endian)
    - Bytes 3-4: Product ID (little-endian)
    - Bytes 5-6: Device ID (little-endian)
    
    Parameters:
    -----------
    pnp_data : bytes
        The raw PnP ID data (should be 7 bytes)
        
    Returns:
    --------
    str
        Decoded PnP ID information
    """
    if not pnp_data or len(pnp_data) != 7:
        return f"Invalid PnP ID data (expected 7 bytes, got {len(pnp_data) if pnp_data else 0})"
    
    # Extract fields
    vendor_id_source = pnp_data[0]
    vendor_id = int.from_bytes(pnp_data[1:3], byteorder='little')
    product_id = int.from_bytes(pnp_data[3:5], byteorder='little')
    # The Device ID bytes are interpreted in little-endian order
    # to convert to a 16-bit integer
    device_id = int.from_bytes(pnp_data[5:7], byteorder='little')
    
    # Decode vendor ID source
    source_names = {
        1: "Bluetooth SIG",
        2: "USB Implementers Forum"
    }
    source_name = source_names.get(vendor_id_source, f"Unknown ({vendor_id_source})")
    
    # Look up vendor name based on source
    # Import here to avoid circular dependency
    from bleep.ble_ops.common.modalias import decode_pnp_id_vendor
    vendor_name = decode_pnp_id_vendor(vendor_id_source, vendor_id)
    
    # The last 2 bytes (bytes 5-6) represent the device ID
    # Simply display as a hexadecimal value without any special interpretation
    device_id = int.from_bytes(pnp_data[5:7], byteorder='little')
    device_id_str = f"0x{device_id:04x}"
    
    return (f"Vendor: {vendor_name} ({source_name}), "
            f"Product ID: 0x{product_id:04x}, "
            f"Device ID: {device_id_str}")


def format_device_class(class_value: int) -> str:
    """Format device class for display based on the golden reference implementation.
    
    Parameters:
    -----------
    class_value : int
        The Class of Device value to decode
        
    Returns:
    --------
    str
        A properly formatted string with full class and service details
    """
    if class_value is None:
        return "Not available"
        
    # Use the reference functions to decode the class value
    list__major_service_classes, list__major_device_class, list__minor_device_class, fixed_bits_check = decode_class_of_device(class_value)
    device_services, major_device, minor_device = extract__class_of_device__service_and_class_info(
        list__major_service_classes, list__major_device_class, list__minor_device_class, fixed_bits_check
    )
    
    # Format the output according to the golden reference format
    if major_device != "-=UNKNOWN=-" and device_services != "-=UNKNOWN=-":
        return f"Services: {device_services} | Device class: {major_device} | Minor class: {minor_device}"
    elif major_device != "-=UNKNOWN=-":
        return f"Device class: {major_device} | Minor class: {minor_device}"
    elif device_services != "-=UNKNOWN=-":
        return f"Services: {device_services}"
    else:
        return f"Unknown class: 0x{class_value:06x}"

def format_hex_ascii(data, indent: str = "") -> str:
    """Format raw bytes as separate Hex and ASCII lines.

    Non-printable bytes (outside 0x20–0x7E) are rendered as the Unicode
    replacement character (U+FFFD) in the ASCII line, consistent with
    ``convert__hex_to_ascii`` behaviour.

    Parameters
    ----------
    data
        Byte-like iterable (``bytes``, ``bytearray``, or ``list[int]``).
    indent
        String prepended to each output line.
    """
    if not data:
        return f"{indent}Hex: (empty)\n{indent}ASCII: (empty)"

    if not isinstance(data, (bytes, bytearray)):
        data = bytes(data)

    hex_str = " ".join(f"{b:02x}" for b in data)
    ascii_str = "".join(chr(b) if 0x20 <= b <= 0x7E else "\ufffd" for b in data)

    return f"{indent}Hex: {hex_str}\n{indent}ASCII: {ascii_str}"


def format_device_info_block(
    props: dict,
    device_name: str | None = None,
    mac: str | None = None,
) -> str:
    """Format Device1 D-Bus properties as a human-readable info block.

    Renders ManufacturerData keys as hex + decimal, values as Hex/ASCII
    lines.  ServiceData UUIDs are resolved to known names where possible.
    The output style mirrors ``_print_unified_props`` in
    ``modes/debug_connect.py`` so CLI output remains visually consistent.

    Parameters
    ----------
    props
        Dictionary returned by ``Properties.GetAll("org.bluez.Device1")``.
        D-Bus wrapper types are handled transparently.
    device_name
        Friendly name shown in the section header.
    mac
        Bluetooth address shown in the section header.
    """
    from bleep.bt_ref.utils import get_name_from_uuid

    lines: list[str] = []

    header = "Device Information"
    if device_name:
        header += f" \u2014 {device_name}"
    if mac:
        header += f" [{mac}]"
    lines.append(header)
    lines.append("=" * len(header))

    _SKIP = {"Address", "Adapter", "Alias", "Name", "_Battery1", "_Input1"}
    _LABEL = {
        "AddressType": "Address Type",
        "TxPower": "TX Power",
        "ManufacturerData": "Manufacturer Data",
        "ServiceData": "Service Data",
        "LegacyPairing": "Legacy Pairing",
        "ServicesResolved": "Services Resolved",
        "WakeAllowed": "Wake Allowed",
        "AdvertisingFlags": "Advertising Flags",
        "AdvertisingData": "Advertising Data",
    }
    _BOOL_KEYS = {
        "Blocked", "Bonded", "Connected", "LegacyPairing", "Paired",
        "Trusted", "ServicesResolved", "WakeAllowed",
    }
    _ORDERED = [
        "AddressType", "RSSI", "TxPower", "Connected", "Paired", "Bonded",
        "Trusted", "Blocked", "WakeAllowed", "LegacyPairing",
        "ServicesResolved", "Icon", "Appearance", "Class",
        "Modalias", "ManufacturerData", "ServiceData",
        "AdvertisingFlags", "AdvertisingData", "UUIDs",
    ]

    displayed: set[str] = set()

    for key in _ORDERED:
        if key not in props or key in _SKIP:
            continue
        displayed.add(key)
        label = _LABEL.get(key, key)
        value = props[key]

        if key in _BOOL_KEYS:
            lines.append(f"  {label + ':':<20s} {bool(value)}")
            continue

        if key in ("RSSI", "TxPower"):
            lines.append(f"  {label + ':':<20s} {int(value)} dBm")
            continue

        if key == "Class":
            class_str = format_device_class(int(value))
            lines.append(f"  {label + ':':<20s} 0x{int(value):06X} ({class_str})")
            continue

        if key == "Appearance":
            app_str = decode_appearance(int(value))
            lines.append(f"  {label + ':':<20s} {app_str} ({int(value)})")
            continue

        if key == "ManufacturerData":
            lines.append(f"  {label}:")
            for mfr_key in value:
                k_int = int(mfr_key)
                company = _resolve_company_name(k_int)
                if company:
                    lines.append(f"    Key: 0x{k_int:04x} ({k_int}) — {company}")
                else:
                    lines.append(f"    Key: 0x{k_int:04x} ({k_int})")
                raw = bytes(value[mfr_key])
                lines.append("    Value:")
                lines.append(format_hex_ascii(raw, indent="      "))
            continue

        if key == "ServiceData":
            lines.append(f"  {label}:")
            for sd_uuid in value:
                uuid_str = str(sd_uuid)
                name = get_name_from_uuid(uuid_str)
                if name and name != "Unknown":
                    lines.append(f"    UUID: {uuid_str} ({name})")
                else:
                    lines.append(f"    UUID: {uuid_str}")
                raw = bytes(value[sd_uuid])
                lines.append("    Value:")
                lines.append(format_hex_ascii(raw, indent="      "))
            continue

        if key == "AdvertisingFlags":
            raw = bytes(value) if not isinstance(value, (bytes, bytearray)) else value
            lines.append(f"  {label}:")
            lines.append(format_hex_ascii(raw, indent="    "))
            continue

        if key == "AdvertisingData":
            lines.append(f"  {label}:")
            for ad_key in value:
                k_int = int(ad_key)
                ad_name = _resolve_ad_type_name(k_int)
                if ad_name:
                    lines.append(f"    Type: 0x{k_int:02x} ({k_int}) — {ad_name}")
                else:
                    lines.append(f"    Type: 0x{k_int:02x} ({k_int})")
                raw = bytes(value[ad_key])
                lines.append(format_hex_ascii(raw, indent="      "))
            continue

        if key == "UUIDs":
            uuid_list = [str(u) for u in value]
            lines.append(f"  {label + ':':<20s} {len(uuid_list)} service(s)")
            for u in uuid_list:
                name = get_name_from_uuid(u)
                if name and name != "Unknown":
                    lines.append(f"    {u} ({name})")
                else:
                    lines.append(f"    {u}")
            continue

        lines.append(f"  {label + ':':<20s} {value}")

    for key in sorted(props.keys()):
        if key in displayed or key in _SKIP:
            continue
        label = _LABEL.get(key, key)
        value = props[key]
        if key in _BOOL_KEYS:
            lines.append(f"  {label + ':':<20s} {bool(value)}")
        else:
            lines.append(f"  {label + ':':<20s} {value}")

    # Battery1 interface (if collected)
    battery = props.get("_Battery1")
    if battery:
        lines.append("")
        lines.append("  Battery:")
        pct = battery.get("Percentage")
        if pct is not None:
            lines.append(f"    Percentage:       {int(pct)}%")
        src = battery.get("Source")
        if src is not None:
            lines.append(f"    Source:           {src}")

    # Input1 / HID classification
    input1 = props.get("_Input1")
    hid_context = dict(props)
    if input1:
        hid_context["_Input1"] = input1
    try:
        from bleep.analysis.device_type_classifier import classify_hid
        hid = classify_hid(hid_context)
    except Exception:
        hid = None

    if hid:
        lines.append("")
        lines.append("  HID Classification:")
        lines.append(f"    Type:            {hid.hid_type}")
        lines.append(f"    Subclass:        {hid.subclass_label}")
        if hid.reconnect_mode:
            _MODE_NOTES = {
                "none": "device does not automatically reconnect",
                "host": "host-initiated reconnection only",
                "device": "device-initiated reconnection only",
                "any": "accepts connections from any source",
            }
            note = _MODE_NOTES.get(hid.reconnect_mode, "")
            rm_display = f"{hid.reconnect_mode} ({note})" if note else hid.reconnect_mode
            lines.append(f"    Reconnect Mode:  {rm_display}")
    elif input1:
        lines.append("")
        lines.append("  Input:")
        rmode = input1.get("ReconnectMode")
        if rmode is not None:
            mode_str = str(rmode)
            _MODE_NOTES = {
                "none": "device does not automatically reconnect",
                "host": "host-initiated reconnection only",
                "device": "device-initiated reconnection only",
                "any": "accepts connections from any source",
            }
            note = _MODE_NOTES.get(mode_str.lower(), "")
            display = f"{mode_str} ({note})" if note else mode_str
            lines.append(f"    Reconnect Mode:  {display}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# SIG data resolution helpers (M5)
# ---------------------------------------------------------------------------

_COMPANY_IDENTS_CACHE: Optional[Dict] = None
_AD_TYPES_CACHE: Optional[Dict] = None
_APPEARANCE_SIG_CACHE: Optional[Dict] = None


def _resolve_company_name(company_id: int) -> Optional[str]:
    """Resolve a 16-bit company identifier to its BT SIG registered name."""
    global _COMPANY_IDENTS_CACHE
    if _COMPANY_IDENTS_CACHE is None:
        try:
            from bleep.bt_ref.uuids import SPEC_ID_NAMES__COMPANY_IDENTS
            _COMPANY_IDENTS_CACHE = SPEC_ID_NAMES__COMPANY_IDENTS
        except ImportError:
            _COMPANY_IDENTS_CACHE = {}
    key = f"0x{company_id:04x}"
    return _COMPANY_IDENTS_CACHE.get(key)


def _resolve_ad_type_name(ad_type: int) -> Optional[str]:
    """Resolve an Advertising Data type code to its BT SIG name."""
    global _AD_TYPES_CACHE
    if _AD_TYPES_CACHE is None:
        try:
            from bleep.bt_ref.uuids import SPEC_ID_NAMES__ADVERTISING_TYPES
            _AD_TYPES_CACHE = SPEC_ID_NAMES__ADVERTISING_TYPES
        except ImportError:
            _AD_TYPES_CACHE = {}
    key = f"0x{ad_type:04x}"
    return _AD_TYPES_CACHE.get(key)


def _resolve_appearance_sig(appearance_value: int) -> Optional[str]:
    """Resolve a 16-bit appearance value through the SIG table.

    The SIG table uses category-level string keys (``"0x0002"`` = Computer).
    The 16-bit appearance encodes ``category << 6 | subcategory``.  We try
    the exact value first, then fall back to the category.
    """
    global _APPEARANCE_SIG_CACHE
    if _APPEARANCE_SIG_CACHE is None:
        try:
            from bleep.bt_ref.uuids import SPEC_ID_NAMES__APPEARANCE_VALUES
            _APPEARANCE_SIG_CACHE = SPEC_ID_NAMES__APPEARANCE_VALUES
        except ImportError:
            _APPEARANCE_SIG_CACHE = {}
    exact = f"0x{appearance_value:04x}"
    hit = _APPEARANCE_SIG_CACHE.get(exact)
    if hit:
        return hit
    # Fall back to category (top 10 bits)
    category = appearance_value >> 6
    cat_key = f"0x{category:04x}"
    return _APPEARANCE_SIG_CACHE.get(cat_key)


__all__ = [
    "convert__hex_to_ascii",
    "convert__dbus_to_hex",
    "decode_class_of_device",
    "decode_appearance",
    "decode_pnp_id",
    "format_device_class",
    "extract__class_of_device__service_and_class_info",
    "format_hex_ascii",
    "format_device_info_block",
    "format_gatt_tree",
    "handle_hex_to_int",
] 

# ---------------------------------------------------------------------------
# Handle conversion helpers (int ↔︎ "0xHHHH")
# ---------------------------------------------------------------------------


def handle_int_to_hex(handle: int) -> str:  # noqa: D401
    """Return *handle* as a four-digit hexadecimal string prefixed with **0x**.

    The refactor keeps legacy **int** handles in the device-mapping for
    backward compatibility, but some tooling (CLI pretty-prints, log output)
    prefers the human-friendly hex representation.  Centralising the
    conversion avoids ad-hoc f-strings sprinkled across the codebase and
    provides a single point of change when we eventually migrate fully to
    the richer mapping structure.
    """

    if handle < 0 or handle > 0xFFFF:
        raise ValueError("Handle must be in range 0x0000-0xFFFF")
    return f"0x{handle:04x}"


def handle_hex_to_int(handle_str: str) -> int:  # noqa: D401
    """Parse *handle_str* like ``"0x004A"`` (case-insensitive) → **int**.

    Accepts strings **with** the ``0x`` prefix or **plain** hex digits.
    Raises ``ValueError`` if the input is malformed or out of range.
    """

    if not isinstance(handle_str, str):
        raise TypeError("handle_hex_to_int expects a string input")

    s = handle_str.lower().strip()
    if s.startswith("0x"):
        s = s[2:]

    if len(s) == 0 or len(s) > 4 or any(ch not in "0123456789abcdef" for ch in s):
        raise ValueError(f"Invalid handle hex string: {handle_str}")

    value = int(s, 16)
    if value > 0xFFFF:
        raise ValueError("Handle value exceeds 0xFFFF")
    return value


# ---------------------------------------------------------------------------
# Human-readable GATT tree formatter
# ---------------------------------------------------------------------------

def format_gatt_tree(
    mapping: Dict[str, Any],
    mine_map: Dict[str, Any] | None = None,
    perm_map: Dict[str, Any] | None = None,
    device_name: str | None = None,
    mac: str | None = None,
    changed_chars: set[str] | None = None,
    device_props: dict | None = None,
) -> str:
    """Render a GATT mapping as a human-readable tree string.

    Handles both the lowercase (``chars``) format produced by
    ``services_resolved(deep=False)`` and the uppercase (``Characteristics``)
    format produced by ``_enumerate_gatt_values(deep=True)``.

    When *device_props* is supplied (a ``Properties.GetAll("org.bluez.Device1")``
    dict), a ``Device Information`` block is prepended before the GATT tree.
    """
    from bleep.bt_ref.utils import get_name_from_uuid

    lines: list[str] = []

    if device_props:
        lines.append(format_device_info_block(device_props, device_name, mac))
        lines.append("")

    header = "GATT Profile"
    if device_name:
        header += f" — {device_name}"
    if mac:
        header += f" [{mac}]"
    lines.append(header)
    lines.append("=" * len(header))

    svc_keys = list(mapping.keys())
    for si, svc_uuid in enumerate(svc_keys):
        svc_data = mapping[svc_uuid]
        svc_name = get_name_from_uuid(svc_uuid)
        svc_prefix = "└── " if si == len(svc_keys) - 1 else "├── "
        svc_cont   = "    " if si == len(svc_keys) - 1 else "│   "
        svc_primary = svc_data.get("Primary")
        svc_handle = svc_data.get("Handle") or svc_data.get("start_handle")
        svc_includes = svc_data.get("Includes") or []

        svc_label = f"{svc_prefix}Service: {svc_uuid}"
        if svc_handle:
            svc_label += f" (Handle: {svc_handle})"
        if svc_primary is not None:
            svc_label += f"  [{('Primary' if svc_primary else 'Secondary')}]"
        lines.append(svc_label)
        if svc_name and svc_name != "Unknown":
            lines.append(f"{svc_cont}  ↳ {svc_name}")
        if svc_includes:
            inc_strs = []
            for inc_path in svc_includes:
                inc_uuid_part = inc_path.rsplit("/", 1)[-1] if "/" in str(inc_path) else str(inc_path)
                inc_strs.append(inc_uuid_part)
            lines.append(f"{svc_cont}  Includes: {', '.join(inc_strs)}")

        # Support both mapping formats
        chars = svc_data.get("Characteristics") or svc_data.get("chars") or {}
        char_keys = list(chars.keys())
        for ci, char_uuid in enumerate(char_keys):
            char_data = chars[char_uuid]
            char_name = get_name_from_uuid(char_uuid)
            ch_prefix = "└── " if ci == len(char_keys) - 1 else "├── "
            ch_cont   = "    " if ci == len(char_keys) - 1 else "│   "

            handle = char_data.get("Handle") or char_data.get("handle") or ""
            if handle:
                handle = f" (Handle: {handle})"
            lines.append(f"{svc_cont}{ch_prefix}Char: {char_uuid}{handle}")
            if char_name and char_name != "Unknown":
                lines.append(f"{svc_cont}{ch_cont}  ↳ {char_name}")

            flags = char_data.get("Flags") or list((char_data.get("properties") or {}).keys())
            if flags:
                lines.append(f"{svc_cont}{ch_cont}  Properties: {', '.join(flags)}")

            ch_mtu = char_data.get("MTU")
            if ch_mtu is not None:
                lines.append(f"{svc_cont}{ch_cont}  MTU: {ch_mtu}")

            ch_notifying = char_data.get("Notifying")
            if ch_notifying:
                lines.append(f"{svc_cont}{ch_cont}  Notifying: Yes")

            ch_write_acq = char_data.get("WriteAcquired")
            if ch_write_acq:
                lines.append(f"{svc_cont}{ch_cont}  WriteAcquired: Yes")

            ch_notify_acq = char_data.get("NotifyAcquired")
            if ch_notify_acq:
                lines.append(f"{svc_cont}{ch_cont}  NotifyAcquired: Yes")

            raw = char_data.get("Raw") or char_data.get("raw")
            value = char_data.get("Value") or char_data.get("value")
            if raw is not None:
                hex_str = " ".join(f"{b:02x}" for b in raw)
                ascii_str = "".join(chr(b) if 0x20 <= b <= 0x7E else "\ufffd" for b in raw)
                lines.append(f"{svc_cont}{ch_cont}  Hex: {hex_str}")
                lines.append(f"{svc_cont}{ch_cont}  ASCII: {ascii_str}")
            elif value is not None:
                lines.append(f"{svc_cont}{ch_cont}  ASCII: {value}")
            else:
                lines.append(f"{svc_cont}{ch_cont}  Value: <not read>")

            if changed_chars and char_uuid in changed_chars:
                lines.append(f"{svc_cont}{ch_cont}  ** value changed across reads — use 'bleep db timeline {mac or ''}' for details **")

            # Descriptors
            descs = char_data.get("Descriptors") or char_data.get("descriptors") or {}
            desc_keys = list(descs.keys())
            for di, desc_uuid in enumerate(desc_keys):
                desc_data = descs[desc_uuid]
                d_prefix = "└── " if di == len(desc_keys) - 1 else "├── "
                d_cont   = "    " if di == len(desc_keys) - 1 else "│   "
                d_name = get_name_from_uuid(desc_uuid)
                d_handle = desc_data.get("Handle") or desc_data.get("handle")
                d_label = f"{svc_cont}{ch_cont}{d_prefix}Desc: {desc_uuid}"
                if d_handle:
                    d_label += f" (Handle: {d_handle})"
                lines.append(d_label)
                if d_name and d_name != "Unknown":
                    lines.append(f"{svc_cont}{ch_cont}{d_cont}  ↳ {d_name}")
                d_flags = desc_data.get("Flags") or desc_data.get("flags") or []
                if d_flags:
                    lines.append(f"{svc_cont}{ch_cont}{d_cont}  Flags: {', '.join(d_flags)}")
                d_raw = desc_data.get("Raw") or desc_data.get("raw")
                d_val = desc_data.get("Value") or desc_data.get("value")
                if d_raw is not None:
                    d_hex = " ".join(f"{b:02x}" for b in d_raw)
                    d_ascii = "".join(chr(b) if 0x20 <= b <= 0x7E else "\ufffd" for b in d_raw)
                    lines.append(f"{svc_cont}{ch_cont}{d_cont}  Hex: {d_hex}")
                    lines.append(f"{svc_cont}{ch_cont}{d_cont}  ASCII: {d_ascii}")
                elif d_val is not None:
                    lines.append(f"{svc_cont}{ch_cont}{d_cont}  ASCII: {d_val}")

    # Append mine/permission summaries if present
    if mine_map and any(v for v in mine_map.values() if v):
        lines.append("")
        lines.append("Landmine Map:")
        for cat, uuids in mine_map.items():
            if uuids:
                lines.append(f"  {cat}: {uuids}")

    if perm_map and any(v for v in perm_map.values() if v):
        lines.append("")
        lines.append("Permission Map:")
        for cat, uuids in perm_map.items():
            if uuids:
                lines.append(f"  {cat}: {uuids}")

    return "\n".join(lines)