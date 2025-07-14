#! python3
# update_ble_uuids.py - Grab assigned numbers for BLE SIG UUIDs

### Imports

import requests, os, bs4
import yaml
from datetime import datetime

### Variables
# Service UUIDs
serv_uuid_url_api = 'https://api.bitbucket.org/2.0/repositories/bluetooth-SIG/public/src/main/assigned_numbers/uuids/service_uuids.yaml'
# Characteristic UUIDs
#characterstic_uuid_url = 'https://bitbucket.org/bluetooth-SIG/public/raw/86bc1ed40cee81b51044fc9a3c1b101d84b039aa/assigned_numbers/uuids/characteristic_uuids.yaml'
char_uuid_url = 'https://bitbucket.org/bluetooth-SIG/public/src/main/assigned_numbers/uuids/characteristic_uuids.yaml'
char_uuid_url_api = 'https://api.bitbucket.org/2.0/repositories/bluetooth-SIG/public/src/main/assigned_numbers/uuids/characteristic_uuids.yaml'
# Descriptor UUIDs
desc_uuid_url_api = 'https://api.bitbucket.org/2.0/repositories/bluetooth-SIG/public/src/main/assigned_numbers/uuids/descriptors.yaml'

# Member UUIDs
memb_uuid_url_api = 'https://api.bitbucket.org/2.0/repositories/bluetooth-SIG/public/src/main/assigned_numbers/uuids/member_uuids.yaml'

# SDO UUIDs
sdo_uuid_url_api = 'https://api.bitbucket.org/2.0/repositories/bluetooth-SIG/public/src/main/assigned_numbers/uuids/sdo_uuids.yaml'

# Service Class UUIDs
serv_class_uuid_url_api = 'https://api.bitbucket.org/2.0/repositories/bluetooth-SIG/public/src/main/assigned_numbers/uuids/service_class.yaml'

# Manufacturer / Company Identifiers
company_id_url_api = 'https://api.bitbucket.org/2.0/repositories/bluetooth-SIG/public/src/main/assigned_numbers/company_identifiers/company_identifiers.yaml'

# Advertising Flag Identifiers
advertising_flag_url_api = 'https://api.bitbucket.org/2.0/repositories/bluetooth-SIG/public/src/main/assigned_numbers/core/ad_types.yaml'

ble_sig_uuid_ending = "-0000-1000-8000-00805f9b34fb"    # Note: This formatting is BT SIG? And represents the rest of the 128-bit UUID (minus the first 8 hex characters)

output__char_uuids = 'bluetooth_uuids.py'

header_text = "#!/usr/bin/python3\n\n# Last Updated:     Update BLE UUIDs Script     -       {0}\n# Incorporated BLE CTF known flags\n# Included [Mesh] Agent path and interfaces\n\n".format(datetime.now().strftime("%Y-%m-%d"))
# Services UUID Dictionary Static Strings
uuid_dictionary_header__serv = "# Specification UUID Definitions\nSPEC_UUID_NAMES__SERV = {\n"
uuid_dictionary_tail__serv = "}\n\n"
# Characteristic UUID Dictionary Static Strings
uuid_dictionary_header__char = "# Specification UUID Definitions\nSPEC_UUID_NAMES__CHAR = {\n"
uuid_dictionary_tail__char = "}\n\n"
# Descriptor UUID Dictionary Static Strings
uuid_dictionary_header__desc = "# Specification UUID Definitions\nSPEC_UUID_NAMES__DESC = {\n"
uuid_dictionary_tail__desc = "}\n\n"

# Member UUID Dictionary Static Strings
uuid_dictionary_header__memb = "# Specification UUID Definitions\nSPEC_UUID_NAMES__MEMB = {\n"
uuid_dictionary_tail__memb = "}\n\n"

# SDO (??) UUID Dictionary Static Strings
uuid_dictionary_header__sdo = "# Specification UUID Definitions\nSPEC_UUID_NAMES__SDO = {\n"
uuid_dictionary_tail__sdo = "}\n\n"

# Service Class UUID Dictionary Static Strings
uuid_dictionary_header__serv_class = "# Specification UUID Definitions\nSPEC_UUID_NAMES__SERV_CLASS = {\n"
uuid_dictionary_tail__serv_class = "}\n\n"

# Company Identifier Dictionary Static Strings
id_dictionary_header__company_identifier = "# Specification ID Definitions\nSPEC_ID_NAMES__COMPANY_IDENTS = {\n"
id_dictionary_tail__company_identifier = "}\n\n"

# Advertising Flag Identifiers
id_dictionary_header__advertising_type = "# Specification ID Definitions\nSPEC_ID_NAMES__ADVERTISING_TYPES = {\n"
id_dictionary_tail__advertising_type = "}\n\n"

# Debug Bit
dbg = 0

### Functions

# Function for Obtaining a YAML Content Return from a Provided URL API
def grab_online_record(url_string):
    # Attempt to download the remote page
    url_response = requests.get(url_string)
    # Check for issues
    try:
        url_response.raise_for_status()
    except Exception as exc:
        print("[!] There was a problem:\t{0}".format(exc))
    # Debugging
    if dbg != 0:
        print("Length of Response:\t{0}".format(len(url_response.text)))
        print("Headers:\t{0}".format(url_response.headers))
        print("Encoding:\t{0}".format(url_response.encoding))
        #print("Text:\t{0}".format(url_response.text))
        print("JSON:\t{0}".format(url_response.json))
        print("Content:\t{0}".format(url_response.content))
    
    # Convert the content
    content = url_response.content.decode("utf-8")
    # Load the YAML file
    yaml_content = yaml.safe_load(content)
    #yaml_content = yaml.safe_load(content, Loader=yaml.BaseLoader)
    
    if dbg != 0:
        print("Content Convert:\t{0}".format(content))
        print("YAML:\t{0}".format(yaml_content))

    # Return the YAML Conect
    return yaml_content

# Function for Generating the BT SIG Service UUIDs
#   - Note: Assuming the file is already open
def generate_uuids__serv(output_file, yaml_content):
    # Add start of UUID Dictionary Structure
    output_file.write(uuid_dictionary_header__serv)

    # Print out each Service UUID Recovered
    for item in yaml_content['uuids']:
        if dbg != 0:
            print("UUID:\t{3:08x}{4} (0x{0:04x})\t-\t{1}\t-\t{2}".format(item['uuid'], item['name'], item['id'], item['uuid'], ble_sig_uuid_ending))
        output_file.write("\t\"{0:08x}{1}\" : \"{2}\",\n".format(item['uuid'], ble_sig_uuid_ending, item['name']))

    # Write the end of the UUID Dictionary Structure
    output_file.write(uuid_dictionary_tail__serv)

# Function for Generating the BT SIG Characteristic UUIDs
#   - Note: Assuming the file is already open
def generate_uuids__char(output_file, yaml_content):
    # Add start of UUID Dictionary Structure
    output_file.write(uuid_dictionary_header__char)
    
    # Print out each Characteristic UUID recovered
    for item in yaml_content['uuids']:
        if dbg != 0:
            print("UUID:\t{3:08x}{4} (0x{0:04x})\t-\t{1}\t-\t{2}".format(item['uuid'], item['name'], item['id'], item['uuid'], ble_sig_uuid_ending))
        output_file.write("\t\"{0:08x}{1}\" : \"{2}\",\n".format(item['uuid'], ble_sig_uuid_ending, item['name']))
    
    # Write the end to the UUID Dictionary Structure
    output_file.write(uuid_dictionary_tail__char)

# Function for Generating the BT SIG Descriptor UUIDs
#   - Note: Assuming the file is already open
def generate_uuids__desc(output_file, yaml_content):
    # Add start of UUID Dictionary Structure
    output_file.write(uuid_dictionary_header__desc)

    # Print out each Service UUID Recovered
    for item in yaml_content['uuids']:
        if dbg != 0:
            print("UUID:\t{3:08x}{4} (0x{0:04x})\t-\t{1}\t-\t{2}".format(item['uuid'], item['name'], item['id'], item['uuid'], ble_sig_uuid_ending))
        output_file.write("\t\"{0:08x}{1}\" : \"{2}\",\n".format(item['uuid'], ble_sig_uuid_ending, item['name']))

    # Write the end of the UUID Dictionary Structure
    output_file.write(uuid_dictionary_tail__desc)

# Function for Generating the BT SIG UUIDs for Services, Characteristics, and Descriptors
def generate_uuids__scd(output_file):
    ## Generate Services
    # Obtain the Service YAML Information
    yaml_content__serv = grab_online_record(serv_uuid_url_api)
    # Generate the UUID information
    generate_uuids__serv(output_file, yaml_content__serv)
    
    ## Generate Characteristics
    # Obtain the Characteristic YAML Information
    yaml_content__char = grab_online_record(char_uuid_url_api)
    # Generate the UUID information
    generate_uuids__char(output_file, yaml_content__char)
    
    ## Generate Descriptors
    # Obtain the Descriptor YAML Information
    yaml_content__desc = grab_online_record(desc_uuid_url_api)
    # Generate the UUID information
    generate_uuids__desc(output_file, yaml_content__desc)

# Function for Generating the BT SIG Member UUIDs
#   - Note: Assuming the file is already open
def generate_uuids__memb(output_file):
    # Obtain the Members YAML Information
    yaml_content = grab_online_record(memb_uuid_url_api)

    # Add start of UUID Dictionary Structure
    output_file.write(uuid_dictionary_header__memb)

    # Print out each Service UUID Recovered
    for item in yaml_content['uuids']:
        if dbg != 0:
            print("UUID:\t0x{0:04x} ({3})\t-\t{1}\t-\t{2}".format(item['uuid'], item['name'], item['id']), item['uuid'])
        # Add escape for JSON entries that contain a duoble quote
        if "\"" in item['name']:
            output_file.write("\t\"0x{0:04x}\" : \"{1}\",\n".format(item['uuid'], item['name'].replace('"', '\\"')))
        else:
            output_file.write("\t\"0x{0:04x}\" : \"{1}\",\n".format(item['uuid'], item['name']))

    # Write the end of the UUID Dictionary Structure
    output_file.write(uuid_dictionary_tail__memb)

# Function for Generating the BT SIG SDO UUIDs
#   - Note: Assuming the file is already open
def generate_uuids__sdo(output_file):
    # Obtain the SDOs YAML Information
    yaml_content = grab_online_record(sdo_uuid_url_api)

    # Add start of UUID Dictionary Structure
    output_file.write(uuid_dictionary_header__sdo)

    # Print out each Service UUID Recovered
    for item in yaml_content['uuids']:
        if dbg != 0:
            print("UUID:\t0x{0:04x} ({3})\t-\t{1}\t-\t{2}".format(item['uuid'], item['name'], item['id']), item['uuid'])
        output_file.write("\t\"0x{0:04x}\" : \"{1}\",\n".format(item['uuid'], item['name']))

    # Write the end of the UUID Dictionary Structure
    output_file.write(uuid_dictionary_tail__sdo)

# Function for Generating the BT SIG Service Class UUIDs
#   - Note: Assuming the file is already open
def generate_uuids__serv_class(output_file):
    # Obtain the Service Class YAML Information
    yaml_content = grab_online_record(serv_class_uuid_url_api)

    # Add start of UUID Dictionary Structure
    output_file.write(uuid_dictionary_header__serv_class)

    # Print out each Service UUID Recovered
    for item in yaml_content['uuids']:
        if dbg != 0:
            print("UUID:\t0x{0:04x} ({3})\t-\t{1}\t-\t{2}".format(item['uuid'], item['name'], item['id']), item['uuid'])
        output_file.write("\t\"0x{0:04x}\" : \"{1}\",\n".format(item['uuid'], item['name']))

    # Write the end of the UUID Dictionary Structure
    output_file.write(uuid_dictionary_tail__serv_class)

# Function for Generating the BT SIG Company Identifiers
def generate_ids__company_identifiers(output_file):
    # Obtain the Company Identifier YAML Information
    yaml_content = grab_online_record(company_id_url_api)

    # Add start of Company Identifiers Structure
    output_file.write(id_dictionary_header__company_identifier)

    # Print out each Company Identifier Recovered
    for item in yaml_content['company_identifiers']:
        if dbg != 0:
            print("Company ID:\t0x{0:04x} ({1})\t-\t{2}".format(item['value'], item['value'], item['name']))
        #test_name = item['name']
        if "\"" in item['name']:
            #test_name = test_name.replace('"', '\\"')
            #print("Company ID:\t0x{0:04x} ({1})\t-\t{2}".format(item['value'], item['value'], test_name))
            output_file.write("\t\"0x{0:04x}\" : \"{1}\",\n".format(item['value'], item['name'].replace('"', '\\"')))
        else:
            output_file.write("\t\"0x{0:04x}\" : \"{1}\",\n".format(item['value'], item['name']))

    # Write the end of the Company Identifier Structure
    output_file.write(id_dictionary_tail__company_identifier)

# Function for Generating the BT SIG Advertising Flag Type Identifiers
def generate_ids__advertising_types(output_file):
    # Obtain the Company Identifier YAML Information
    yaml_content = grab_online_record(advertising_flag_url_api)

    # Add start of Advertising Flag Type Identifiers Structure
    output_file.write(id_dictionary_header__advertising_type)

    # Print out each Advertising Type Identifier Recovered
    for item in yaml_content['ad_types']:
        if dbg != 0:
            print("Advertising ID:\t0x{0:04x} ({1})\t-\t{2}".format(item['value'], item['value'], item['name']))
        #test_name = item['name']
        if "\"" in item['name']:
            #test_name = test_name.replace('"', '\\"')
            #print("Company ID:\t0x{0:04x} ({1})\t-\t{2}".format(item['value'], item['value'], test_name))
            output_file.write("\t\"0x{0:04x}\" : \"{1}\",\n".format(item['value'], item['name'].replace('"', '\\"')))
        else:
            output_file.write("\t\"0x{0:04x}\" : \"{1}\",\n".format(item['value'], item['name']))

    # Write the end of the Company Identifier Structure
    output_file.write(id_dictionary_tail__advertising_type)

### Main Loop

## Clear and Generate Header
# Create a Blank file
open(output__char_uuids, 'w').close()
# Add the header information
uuid_file = open(output__char_uuids, 'a')
uuid_file.write(header_text)

## Generate BT SIG UUIDs
# Generate Services, Characteristic, and Descriptor UUIDs
generate_uuids__scd(uuid_file)
# Generate Member UUIDs
generate_uuids__memb(uuid_file)
# Generate SDO UUIDs
generate_uuids__sdo(uuid_file)
# Generate Service Class UUIDs
generate_uuids__serv_class(uuid_file)

## Generate BT SIG Identifiers
# Generate Company Identifiers
generate_ids__company_identifiers(uuid_file)

# Generate Advertising Type Identifiers
generate_ids__advertising_types(uuid_file)

## End Generation and Close the File
# Close the file
uuid_file.close()

#soup = bs4.BeautifulSoup(char_uuid_res.text)
#soup = bs4.BeautifulSoup(char_uuid_res.text, features=lxml)

#print(soup)
