"""
Secure storage for Bluetooth bonding information.

This module provides classes for securely storing and retrieving bonding information
for Bluetooth devices. It includes a generic secure storage mechanism, a device-specific
bond store, and an in-memory cache for frequently accessed data.
"""

from __future__ import annotations

import os
import stat
import json
import base64
import time
from typing import Any, Dict, List, Optional, Union

from bleep.core.log import print_and_log, LOG__DEBUG

try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False
    print_and_log(
        "[-] Warning: cryptography package not found, using unencrypted storage",
        LOG__DEBUG
    )

__all__ = ["SecureStorage", "DeviceBondStore", "PairingCache"]


class SecureStorage:
    """Secure storage for sensitive information."""
    
    def __init__(self, storage_path: str, encryption_key: Optional[str] = None):
        """Initialize secure storage.
        
        Parameters
        ----------
        storage_path : str
            Path to the storage directory
        encryption_key : str, optional
            Encryption key for securing the data. If None, a key will be generated
            and stored in the storage directory.
        """
        self._storage_path = storage_path
        os.makedirs(self._storage_path, exist_ok=True)
        
        # Set secure permissions on directory
        try:
            # 0o700 = user can read/write/execute, no permissions for group/others
            os.chmod(self._storage_path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
        except Exception as e:
            print_and_log(f"[-] Warning: Could not set secure permissions on storage directory: {str(e)}", LOG__DEBUG)
            
        # Initialize encryption
        self._encrypted = HAS_CRYPTO
        if self._encrypted:
            self._key_file = os.path.join(self._storage_path, ".key")
            self._encryption_key = self._initialize_encryption_key(encryption_key)
            self._cipher = Fernet(self._encryption_key)
        
    def _initialize_encryption_key(self, provided_key: Optional[str]) -> bytes:
        """Initialize or load the encryption key.
        
        Parameters
        ----------
        provided_key : str or None
            User-provided encryption key, or None to generate/load
            
        Returns
        -------
        bytes
            Encryption key
        """
        if provided_key:
            # Use provided key, but ensure it's valid for Fernet
            salt = b'bleep_pairing_agent'  # Fixed salt
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=100000,
            )
            key = base64.urlsafe_b64encode(kdf.derive(provided_key.encode()))
            return key
            
        # Try to load existing key
        if os.path.exists(self._key_file):
            with open(self._key_file, 'rb') as f:
                return f.read()
                
        # Generate new key
        key = Fernet.generate_key()
        with open(self._key_file, 'wb') as f:
            f.write(key)
            os.chmod(self._key_file, 0o600)  # Secure permissions
            
        return key
        
    def store(self, key: str, value: Any) -> None:
        """Store a value securely.
        
        Parameters
        ----------
        key : str
            Key to store the value under
        value : any
            Value to store (will be JSON-serialized)
        """
        # Convert value to JSON
        json_data = json.dumps(value)
        
        # Encrypt if possible
        if self._encrypted:
            encrypted_data = self._cipher.encrypt(json_data.encode('utf-8'))
            file_path = os.path.join(self._storage_path, f"{key}.bin")
            
            # Write to file
            with open(file_path, 'wb') as f:
                f.write(encrypted_data)
        else:
            # Store unencrypted (but still JSON)
            file_path = os.path.join(self._storage_path, f"{key}.json")
            
            # Write to file
            with open(file_path, 'w') as f:
                f.write(json_data)
                
        # Set secure permissions
        try:
            os.chmod(file_path, 0o600)  # User read/write only
        except Exception as e:
            print_and_log(f"[-] Warning: Could not set secure permissions on file {file_path}: {str(e)}", LOG__DEBUG)
            
    def retrieve(self, key: str) -> Optional[Any]:
        """Retrieve a stored value.
        
        Parameters
        ----------
        key : str
            Key to retrieve
            
        Returns
        -------
        any or None
            Retrieved value, or None if not found or invalid
        """
        # Check for encrypted file
        encrypted_path = os.path.join(self._storage_path, f"{key}.bin")
        unencrypted_path = os.path.join(self._storage_path, f"{key}.json")
        
        # Try encrypted first
        if self._encrypted and os.path.exists(encrypted_path):
            try:
                # Read and decrypt data
                with open(encrypted_path, 'rb') as f:
                    encrypted_data = f.read()
                    
                decrypted_data = self._cipher.decrypt(encrypted_data)
                return json.loads(decrypted_data.decode('utf-8'))
            except Exception as e:
                print_and_log(f"[-] Error retrieving encrypted data for key {key}: {str(e)}", LOG__DEBUG)
                return None
                
        # Try unencrypted file
        elif os.path.exists(unencrypted_path):
            try:
                with open(unencrypted_path, 'r') as f:
                    return json.loads(f.read())
            except Exception as e:
                print_and_log(f"[-] Error retrieving unencrypted data for key {key}: {str(e)}", LOG__DEBUG)
                return None
                
        # Not found
        return None
            
    def delete(self, key: str) -> bool:
        """Delete a stored value.
        
        Parameters
        ----------
        key : str
            Key to delete
            
        Returns
        -------
        bool
            True if deleted, False if not found
        """
        encrypted_path = os.path.join(self._storage_path, f"{key}.bin")
        unencrypted_path = os.path.join(self._storage_path, f"{key}.json")
        
        deleted = False
        
        if os.path.exists(encrypted_path):
            os.remove(encrypted_path)
            deleted = True
            
        if os.path.exists(unencrypted_path):
            os.remove(unencrypted_path)
            deleted = True
            
        return deleted
            
    def list_keys(self) -> List[str]:
        """List all stored keys.
        
        Returns
        -------
        List[str]
            List of keys
        """
        keys = set()
        
        # Find all .bin and .json files
        for filename in os.listdir(self._storage_path):
            if filename.endswith(".bin") and not filename.startswith("."):
                keys.add(filename[:-4])  # Remove '.bin' extension
            elif filename.endswith(".json") and not filename.startswith("."):
                keys.add(filename[:-5])  # Remove '.json' extension
                
        return list(keys)
        
    def clear_all(self) -> None:
        """Clear all stored values but keep the encryption key."""
        for key in self.list_keys():
            self.delete(key)


class DeviceBondStore:
    """Store and manage device bonding information."""
    
    def __init__(self, storage_path: Optional[str] = None, encryption_key: Optional[str] = None):
        """Initialize device bond store.
        
        Parameters
        ----------
        storage_path : str, optional
            Path to the storage directory, defaults to ~/.bleep/bonds
        encryption_key : str, optional
            Encryption key for securing the data
        """
        if storage_path is None:
            home = os.path.expanduser("~")
            storage_path = os.path.join(home, ".bleep", "bonds")
            
        self._storage = SecureStorage(storage_path, encryption_key)
        
    def save_device_bond(self, device_path: str, bond_info: Dict[str, Any]) -> None:
        """Save bonding information for a device.
        
        Parameters
        ----------
        device_path : str
            D-Bus path of the device
        bond_info : dict
            Bonding information to save. Should include at least:
            - address: MAC address of the device
            - name: Device name
            - paired: Whether the device is paired
            - trusted: Whether the device is trusted
            - timestamps: Dictionary with 'first_paired' and 'last_paired'
            - capabilities: Device pairing capabilities
            - keys: Dictionary of bonding keys (if applicable)
        """
        # Ensure required fields exist
        if "address" not in bond_info:
            raise ValueError("Bond info must include device address")
            
        # Add timestamps if not present
        if "timestamps" not in bond_info:
            bond_info["timestamps"] = {}
            
        if "first_paired" not in bond_info["timestamps"]:
            bond_info["timestamps"]["first_paired"] = time.time()
            
        bond_info["timestamps"]["last_paired"] = time.time()
        
        # Add metadata
        bond_info["device_path"] = device_path
        bond_info["storage_version"] = 1
        
        # Convert device_path to a safe key
        key = self._path_to_key(device_path)
        self._storage.store(key, bond_info)
        
        # Also store by MAC address for easier lookup
        if "address" in bond_info:
            addr_key = f"addr_{bond_info['address'].replace(':', '')}"
            self._storage.store(addr_key, {"device_path": device_path})
        
    def load_device_bond(self, device_path: str) -> Optional[Dict[str, Any]]:
        """Load bonding information for a device.
        
        Parameters
        ----------
        device_path : str
            D-Bus path of the device
            
        Returns
        -------
        dict or None
            Bonding information, or None if not found
        """
        key = self._path_to_key(device_path)
        return self._storage.retrieve(key)
        
    def load_device_bond_by_address(self, address: str) -> Optional[Dict[str, Any]]:
        """Load bonding information for a device by its MAC address.
        
        Parameters
        ----------
        address : str
            MAC address of the device
            
        Returns
        -------
        dict or None
            Bonding information, or None if not found
        """
        # First look up the device path
        addr_key = f"addr_{address.replace(':', '')}"
        path_info = self._storage.retrieve(addr_key)
        
        if not path_info or "device_path" not in path_info:
            return None
            
        # Then load the bond info
        return self.load_device_bond(path_info["device_path"])
        
    def delete_device_bond(self, device_path: str) -> bool:
        """Delete bonding information for a device.
        
        Parameters
        ----------
        device_path : str
            D-Bus path of the device
            
        Returns
        -------
        bool
            True if deleted, False if not found
        """
        # First load the bond info to get the MAC address
        bond_info = self.load_device_bond(device_path)
        
        if not bond_info:
            return False
            
        # Delete the bond info
        key = self._path_to_key(device_path)
        self._storage.delete(key)
        
        # Also delete the address lookup
        if "address" in bond_info:
            addr_key = f"addr_{bond_info['address'].replace(':', '')}"
            self._storage.delete(addr_key)
            
        return True
        
    def list_bonded_devices(self) -> List[Dict[str, Any]]:
        """List all bonded devices.
        
        Returns
        -------
        List[dict]
            List of bonded devices with their information
        """
        result = []
        for key in self._storage.list_keys():
            # Skip address lookup keys
            if key.startswith("addr_"):
                continue
                
            bond_info = self._storage.retrieve(key)
            if bond_info:
                result.append(bond_info)
        return result
        
    def is_device_bonded(self, device_path: str) -> bool:
        """Check if a device is bonded.
        
        Parameters
        ----------
        device_path : str
            D-Bus path of the device
            
        Returns
        -------
        bool
            True if the device is bonded, False otherwise
        """
        return self.load_device_bond(device_path) is not None
        
    def is_device_bonded_by_address(self, address: str) -> bool:
        """Check if a device is bonded by its MAC address.
        
        Parameters
        ----------
        address : str
            MAC address of the device
            
        Returns
        -------
        bool
            True if the device is bonded, False otherwise
        """
        return self.load_device_bond_by_address(address) is not None
        
    def update_device_bond(self, device_path: str, updates: Dict[str, Any]) -> bool:
        """Update bonding information for a device.
        
        Parameters
        ----------
        device_path : str
            D-Bus path of the device
        updates : dict
            Dictionary of updates to apply
            
        Returns
        -------
        bool
            True if updated, False if not found
        """
        # Load existing bond info
        bond_info = self.load_device_bond(device_path)
        
        if not bond_info:
            return False
            
        # Apply updates (deep merge)
        self._deep_update(bond_info, updates)
        
        # Update timestamp
        if "timestamps" not in bond_info:
            bond_info["timestamps"] = {}
        bond_info["timestamps"]["last_updated"] = time.time()
        
        # Save updated bond info
        self.save_device_bond(device_path, bond_info)
        return True
        
    def _path_to_key(self, device_path: str) -> str:
        """Convert D-Bus path to a storage key.
        
        Parameters
        ----------
        device_path : str
            D-Bus path of the device
            
        Returns
        -------
        str
            Storage key for the device
        """
        # Remove leading/trailing slashes and replace internal slashes with underscores
        key = device_path.strip('/')
        key = key.replace('/', '_')
        return key
        
    def _deep_update(self, target: Dict, source: Dict) -> None:
        """Deep update a nested dictionary.
        
        Parameters
        ----------
        target : dict
            Target dictionary to update
        source : dict
            Source dictionary with updates
        """
        for key, value in source.items():
            if key in target and isinstance(target[key], dict) and isinstance(value, dict):
                self._deep_update(target[key], value)
            else:
                target[key] = value


class PairingCache:
    """In-memory cache for pairing information."""
    
    def __init__(self, ttl: int = 300):
        """Initialize pairing cache.
        
        Parameters
        ----------
        ttl : int
            Time-to-live for cache entries in seconds
        """
        self._cache = {}
        self._ttl = ttl
        
    def set(self, device_path: str, data: Dict[str, Any]) -> None:
        """Set data in the cache.
        
        Parameters
        ----------
        device_path : str
            D-Bus path of the device
        data : dict
            Data to cache
        """
        self._cache[device_path] = {
            "data": data,
            "timestamp": time.time()
        }
        
    def get(self, device_path: str) -> Optional[Dict[str, Any]]:
        """Get data from the cache.
        
        Parameters
        ----------
        device_path : str
            D-Bus path of the device
            
        Returns
        -------
        dict or None
            Cached data, or None if not found or expired
        """
        if device_path not in self._cache:
            return None
            
        entry = self._cache[device_path]
        
        # Check if expired
        if time.time() - entry["timestamp"] > self._ttl:
            del self._cache[device_path]
            return None
            
        return entry["data"]
        
    def delete(self, device_path: str) -> bool:
        """Delete data from the cache.
        
        Parameters
        ----------
        device_path : str
            D-Bus path of the device
            
        Returns
        -------
        bool
            True if deleted, False if not found
        """
        if device_path in self._cache:
            del self._cache[device_path]
            return True
        return False
        
    def clear(self) -> None:
        """Clear all data from the cache."""
        self._cache.clear()
        
    def cleanup(self) -> int:
        """Remove expired entries from the cache.
        
        Returns
        -------
        int
            Number of entries removed
        """
        now = time.time()
        expired = [k for k, v in self._cache.items() if now - v["timestamp"] > self._ttl]
        
        for key in expired:
            del self._cache[key]
            
        return len(expired)
