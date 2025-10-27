"""
D-Bus Connection Pool

This module provides connection pooling for D-Bus operations to improve
performance and reliability for high-volume operations.

Based on best practices from BlueZ documentation and example scripts.
"""

import time
import threading
from enum import Enum
from typing import Dict, List, Set, Optional, Any, Union, Callable

import dbus
import dbus.exceptions
import dbus.mainloop.glib
from gi.repository import GLib

from bleep.core.log import print_and_log, LOG__DEBUG, LOG__GENERAL
from bleep.core.metrics import record_operation

# Initialize GLib mainloop for async operations if not already done
dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)


class ConnectionState(Enum):
    """Enum representing possible states of a pooled connection."""
    IDLE = 1      # Connection is available for use
    IN_USE = 2    # Connection is currently in use
    UNHEALTHY = 3 # Connection has failed health check
    CLOSED = 4    # Connection has been closed


class PooledConnection:
    """
    Represents a connection in the connection pool.
    
    This class wraps a D-Bus connection with metadata about its state
    and usage.
    """
    
    def __init__(self, connection: dbus.Bus, bus_type: str):
        """
        Initialize a pooled connection.
        
        Parameters
        ----------
        connection : dbus.Bus
            D-Bus connection to wrap
        bus_type : str
            Type of bus this connection is for
        """
        self.connection = connection
        self.bus_type = bus_type
        self.state = ConnectionState.IDLE
        self.last_used = time.time()
        self.created = time.time()
        self.uses = 0
    
    def mark_used(self) -> None:
        """Mark the connection as in use."""
        self.state = ConnectionState.IN_USE
        self.last_used = time.time()
        self.uses += 1
    
    def mark_idle(self) -> None:
        """Mark the connection as idle (available for use)."""
        self.state = ConnectionState.IDLE
        self.last_used = time.time()
    
    def mark_unhealthy(self) -> None:
        """Mark the connection as unhealthy."""
        self.state = ConnectionState.UNHEALTHY
    
    def mark_closed(self) -> None:
        """Mark the connection as closed."""
        self.state = ConnectionState.CLOSED
    
    def is_idle(self) -> bool:
        """Check if connection is idle (available for use)."""
        return self.state == ConnectionState.IDLE
    
    def is_in_use(self) -> bool:
        """Check if connection is in use."""
        return self.state == ConnectionState.IN_USE
    
    def is_unhealthy(self) -> bool:
        """Check if connection is unhealthy."""
        return self.state == ConnectionState.UNHEALTHY
    
    def is_closed(self) -> bool:
        """Check if connection is closed."""
        return self.state == ConnectionState.CLOSED
    
    def close(self) -> None:
        """Close the connection."""
        try:
            self.connection.close()
        except Exception as e:
            print_and_log(
                f"[-] Error closing D-Bus connection: {e}",
                LOG__DEBUG
            )
        self.mark_closed()


class DBusConnectionPool:
    """
    Pool of D-Bus connections for reuse.
    
    This class maintains a pool of D-Bus connections to improve performance
    and reliability for high-volume operations.
    """
    
    def __init__(
        self, 
        min_system_connections: int = 1,
        max_system_connections: int = 5,
        min_session_connections: int = 0,
        max_session_connections: int = 2,
        max_idle_time: float = 300.0,
        max_connection_age: float = 3600.0,
        health_check_interval: float = 60.0
    ):
        """
        Initialize the connection pool.
        
        Parameters
        ----------
        min_system_connections : int
            Minimum number of system bus connections to maintain
        max_system_connections : int
            Maximum number of system bus connections to allow
        min_session_connections : int
            Minimum number of session bus connections to maintain
        max_session_connections : int
            Maximum number of session bus connections to allow
        max_idle_time : float
            Maximum time in seconds to keep an idle connection
        max_connection_age : float
            Maximum age in seconds for a connection
        health_check_interval : float
            Interval in seconds between health checks
        """
        self._min_connections = {
            'system': min_system_connections,
            'session': min_session_connections,
        }
        self._max_connections = {
            'system': max_system_connections,
            'session': max_session_connections,
        }
        self._max_idle_time = max_idle_time
        self._max_connection_age = max_connection_age
        self._health_check_interval = health_check_interval
        
        self._connections = {
            'system': [],
            'session': [],
        }
        self._last_health_check = 0.0
        self._maintenance_lock = threading.RLock()
        self._proxy_cache = {}
        
        # Initialize the pool with minimum connections
        self._initialize_pool()
        
        # Start maintenance thread
        self._maintenance_thread = threading.Thread(
            target=self._maintenance_loop,
            daemon=True
        )
        self._maintenance_thread.start()
    
    def _initialize_pool(self) -> None:
        """Initialize the connection pool with minimum connections."""
        for bus_type in ['system', 'session']:
            for _ in range(self._min_connections[bus_type]):
                try:
                    self._create_connection(bus_type)
                except Exception as e:
                    print_and_log(
                        f"[-] Error creating initial D-Bus connection for {bus_type}: {e}",
                        LOG__DEBUG
                    )
    
    def _create_connection(self, bus_type: str) -> PooledConnection:
        """
        Create a new connection.
        
        Parameters
        ----------
        bus_type : str
            Type of bus to connect to ('system' or 'session')
            
        Returns
        -------
        PooledConnection
            New pooled connection
        """
        start_time = time.time()
        
        try:
            # Convert string bus_type to actual dbus type
            if bus_type == 'system':
                bus = dbus.SystemBus()
            elif bus_type == 'session':
                bus = dbus.SessionBus()
            else:
                raise ValueError(f"Unknown bus type: {bus_type}")
                
            pooled_conn = PooledConnection(bus, bus_type)
            
            with self._maintenance_lock:
                self._connections[bus_type].append(pooled_conn)
            
            elapsed = time.time() - start_time
            record_operation("dbus_connection_create", elapsed, True)
            
            print_and_log(
                f"[+] Created new D-Bus connection for {bus_type} ({elapsed:.3f}s)",
                LOG__DEBUG
            )
            
            return pooled_conn
        except Exception as e:
            elapsed = time.time() - start_time
            record_operation("dbus_connection_create", elapsed, False)
            
            print_and_log(
                f"[-] Failed to create D-Bus connection for {bus_type}: {e}",
                LOG__GENERAL
            )
            raise
    
    def _get_connection_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the connection pool.
        
        Returns
        -------
        Dict[str, Any]
            Dictionary containing statistics
        """
        with self._maintenance_lock:
            stats = {
                "system": {
                    "total": len(self._connections['system']),
                    "idle": sum(1 for c in self._connections['system'] if c.is_idle()),
                    "in_use": sum(1 for c in self._connections['system'] if c.is_in_use()),
                    "unhealthy": sum(1 for c in self._connections['system'] if c.is_unhealthy()),
                    "closed": sum(1 for c in self._connections['system'] if c.is_closed()),
                },
                "session": {
                    "total": len(self._connections['session']),
                    "idle": sum(1 for c in self._connections['session'] if c.is_idle()),
                    "in_use": sum(1 for c in self._connections['session'] if c.is_in_use()),
                    "unhealthy": sum(1 for c in self._connections['session'] if c.is_unhealthy()),
                    "closed": sum(1 for c in self._connections['session'] if c.is_closed()),
                },
            }
            return stats
    
    def _check_connection_health(self, conn: PooledConnection) -> bool:
        """
        Check if a connection is healthy.
        
        Parameters
        ----------
        conn : PooledConnection
            Connection to check
            
        Returns
        -------
        bool
            True if connection is healthy, False otherwise
        """
        if conn.is_closed():
            return False
        
        try:
            # Try simple D-Bus operation
            conn.connection.get_name_owner("org.freedesktop.DBus")
            return True
        except Exception:
            return False
    
    def _maintenance_loop(self) -> None:
        """Maintenance loop for the connection pool."""
        while True:
            try:
                time.sleep(10)  # Check every 10 seconds
                
                current_time = time.time()
                
                # Skip health check if not time yet
                if current_time - self._last_health_check < self._health_check_interval:
                    continue
                
                self._last_health_check = current_time
                
                with self._maintenance_lock:
                    # Report stats
                    stats = self._get_connection_stats()
                    print_and_log(
                        f"[DEBUG] D-Bus connection pool stats: {stats}",
                        LOG__DEBUG
                    )
                    
                    for bus_type in ['system', 'session']:
                        # Check if we need to create more connections
                        idle_count = sum(1 for c in self._connections[bus_type]
                                        if c.is_idle() and not c.is_closed())
                        
                        if idle_count < self._min_connections[bus_type]:
                            needed = self._min_connections[bus_type] - idle_count
                            print_and_log(
                                f"[*] Creating {needed} new D-Bus {bus_type} connections to meet minimum",
                                LOG__DEBUG
                            )
                            
                            for _ in range(needed):
                                try:
                                    self._create_connection(bus_type)
                                except Exception as e:
                                    print_and_log(
                                        f"[-] Error creating D-Bus connection: {e}",
                                        LOG__DEBUG
                                    )
                        
                        # Check connection health
                        for conn in list(self._connections[bus_type]):
                            if conn.is_closed():
                                continue
                            
                            # Check if connection is too old
                            if current_time - conn.created > self._max_connection_age:
                                if conn.is_idle():
                                    print_and_log(
                                        f"[*] Closing D-Bus connection that exceeded max age",
                                        LOG__DEBUG
                                    )
                                    conn.close()
                                    continue
                                else:
                                    # Flag for replacement but don't close while in use
                                    conn.mark_unhealthy()
                            
                            # Check if idle connection has been idle too long
                            if conn.is_idle() and current_time - conn.last_used > self._max_idle_time:
                                # Only close if we have enough idle connections
                                idle_conns = [c for c in self._connections[bus_type]
                                            if c.is_idle() and not c.is_closed()]
                                
                                if len(idle_conns) > self._min_connections[bus_type]:
                                    print_and_log(
                                        f"[*] Closing idle D-Bus connection that exceeded max idle time",
                                        LOG__DEBUG
                                    )
                                    conn.close()
                                    continue
                            
                            # Check health of connection
                            if not self._check_connection_health(conn):
                                print_and_log(
                                    f"[*] Marking unhealthy D-Bus connection for replacement",
                                    LOG__DEBUG
                                )
                                conn.mark_unhealthy()
                        
                        # Remove closed connections
                        self._connections[bus_type] = [
                            c for c in self._connections[bus_type] if not c.is_closed()
                        ]
                
            except Exception as e:
                print_and_log(
                    f"[-] Error in connection pool maintenance loop: {e}",
                    LOG__DEBUG
                )
    
    def get_connection(self, bus_type: str = 'system', timeout: float = 5.0) -> dbus.Bus:
        """
        Get a connection from the pool.
        
        Parameters
        ----------
        bus_type : str
            Type of bus to get a connection for
        timeout : float
            Maximum time in seconds to wait for a connection
            
        Returns
        -------
        dbus.Bus
            D-Bus connection
            
        Raises
        ------
        TimeoutError
            If no connection is available within the timeout
        """
        start_time = time.time()
        
        while True:
            # Check if we've timed out
            if time.time() - start_time > timeout:
                record_operation("dbus_connection_get", timeout, False)
                raise TimeoutError(f"Timed out waiting for D-Bus connection ({timeout}s)")
            
            with self._maintenance_lock:
                # First, try to find an idle connection
                for conn in self._connections[bus_type]:
                    if conn.is_idle():
                        conn.mark_used()
                        elapsed = time.time() - start_time
                        record_operation("dbus_connection_get", elapsed, True)
                        return conn.connection
                
                # If no idle connection is available, check if we can create a new one
                if len(self._connections[bus_type]) < self._max_connections[bus_type]:
                    try:
                        new_conn = self._create_connection(bus_type)
                        new_conn.mark_used()
                        elapsed = time.time() - start_time
                        record_operation("dbus_connection_get", elapsed, True)
                        return new_conn.connection
                    except Exception as e:
                        print_and_log(
                            f"[-] Error creating new D-Bus connection: {e}",
                            LOG__DEBUG
                        )
            
            # If we can't create a new connection, wait a bit before retrying
            time.sleep(0.1)
    
    def release_connection(self, connection: dbus.Bus) -> None:
        """
        Release a connection back to the pool.
        
        Parameters
        ----------
        connection : dbus.Bus
            Connection to release
        """
        with self._maintenance_lock:
            # Find the connection in our pool
            for bus_type in ['system', 'session']:
                for conn in self._connections[bus_type]:
                    if conn.connection is connection:
                        conn.mark_idle()
                        return
            
            # If we get here, the connection wasn't found
            print_and_log(
                "[-] Attempted to release unknown D-Bus connection",
                LOG__DEBUG
            )
    
    def get_proxy(
        self, bus_type: str, 
        service_name: str, object_path: str, 
        interface_name: str, timeout: float = 5.0
    ) -> dbus.Interface:
        """
        Get a D-Bus proxy from the cache or create a new one.
        
        Parameters
        ----------
        bus_type : str
            Type of bus to get a proxy for
        service_name : str
            D-Bus service name
        object_path : str
            D-Bus object path
        interface_name : str
            D-Bus interface name
        timeout : float
            Maximum time in seconds to wait for a connection
            
        Returns
        -------
        dbus.Interface
            D-Bus proxy interface
        """
        # Create cache key
        cache_key = (bus_type, service_name, object_path, interface_name)
        
        # Check if we have a cached proxy
        if cache_key in self._proxy_cache:
            proxy_info = self._proxy_cache[cache_key]
            
            # Check if proxy is still valid
            if time.time() - proxy_info['created'] < self._max_connection_age:
                return proxy_info['proxy']
            
            # Remove expired proxy from cache
            del self._proxy_cache[cache_key]
        
        # Create new proxy
        connection = self.get_connection(bus_type, timeout)
        obj = connection.get_object(service_name, object_path)
        proxy = dbus.Interface(obj, interface_name)
        
        # Cache the proxy
        self._proxy_cache[cache_key] = {
            'proxy': proxy,
            'created': time.time(),
        }
        
        return proxy
    
    def invalidate_proxy(
        self, bus_type: str, 
        service_name: str, object_path: str, 
        interface_name: str
    ) -> None:
        """
        Invalidate a cached proxy.
        
        Parameters
        ----------
        bus_type : str
            Type of bus the proxy is for
        service_name : str
            D-Bus service name
        object_path : str
            D-Bus object path
        interface_name : str
            D-Bus interface name
        """
        # Create cache key
        cache_key = (bus_type, service_name, object_path, interface_name)
        
        # Remove from cache if present
        if cache_key in self._proxy_cache:
            del self._proxy_cache[cache_key]
    
    def clear_proxy_cache(self) -> None:
        """Clear the proxy cache."""
        self._proxy_cache = {}
    
    def cleanup(self) -> None:
        """Close all connections in the pool."""
        with self._maintenance_lock:
            for bus_type in ['system', 'session']:
                for conn in self._connections[bus_type]:
                    conn.close()
                self._connections[bus_type] = []
            
            self._proxy_cache = {}


class DBusConnectionManager:
    """
    Context manager for D-Bus connections from the pool.
    
    This class provides a convenient way to get a connection from the pool
    and ensure it is released when done.
    """
    
    def __init__(
        self, pool: DBusConnectionPool,
        bus_type: str = 'system',
        timeout: float = 5.0
    ):
        """
        Initialize the connection manager.
        
        Parameters
        ----------
        pool : DBusConnectionPool
            Connection pool to get connections from
        bus_type : str
            Type of bus to get a connection for
        timeout : float
            Maximum time in seconds to wait for a connection
        """
        self._pool = pool
        self._bus_type = bus_type
        self._timeout = timeout
        self._connection = None
    
    def __enter__(self) -> dbus.Bus:
        """
        Get a connection from the pool.
        
        Returns
        -------
        dbus.Bus
            D-Bus connection
        """
        self._connection = self._pool.get_connection(self._bus_type, self._timeout)
        return self._connection
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """
        Release the connection back to the pool.
        
        Parameters
        ----------
        exc_type : type
            Exception type if an exception was raised in the with block
        exc_val : Exception
            Exception value if an exception was raised in the with block
        exc_tb : traceback
            Exception traceback if an exception was raised in the with block
        """
        if self._connection:
            self._pool.release_connection(self._connection)
            self._connection = None


# Singleton instance
_connection_pool = DBusConnectionPool()


def get_connection_pool() -> DBusConnectionPool:
    """
    Get the singleton connection pool.
    
    Returns
    -------
    DBusConnectionPool
        Singleton connection pool
    """
    return _connection_pool


def get_connection(
    bus_type: str = 'system',
    timeout: float = 5.0
) -> dbus.Bus:
    """
    Get a connection from the pool.
    
    Parameters
    ----------
    bus_type : str
        Type of bus to get a connection for
    timeout : float
        Maximum time in seconds to wait for a connection
        
    Returns
    -------
    dbus.Bus
        D-Bus connection
    """
    return _connection_pool.get_connection(bus_type, timeout)


def release_connection(connection: dbus.Bus) -> None:
    """
    Release a connection back to the pool.
    
    Parameters
    ----------
    connection : dbus.Bus
        Connection to release
    """
    _connection_pool.release_connection(connection)


def get_proxy(
    bus_type: str, 
    service_name: str, object_path: str, 
    interface_name: str, timeout: float = 5.0
) -> dbus.Interface:
    """
    Get a D-Bus proxy from the cache or create a new one.
    
    Parameters
    ----------
    bus_type : str
        Type of bus to get a proxy for
    service_name : str
        D-Bus service name
    object_path : str
        D-Bus object path
    interface_name : str
        D-Bus interface name
    timeout : float
        Maximum time in seconds to wait for a connection
        
    Returns
    -------
    dbus.Interface
        D-Bus proxy interface
    """
    return _connection_pool.get_proxy(
        bus_type, service_name, object_path, interface_name, timeout
    )


def invalidate_proxy(
    bus_type: str, 
    service_name: str, object_path: str, 
    interface_name: str
) -> None:
    """
    Invalidate a cached proxy.
    
    Parameters
    ----------
    bus_type : str
        Type of bus the proxy is for
    service_name : str
        D-Bus service name
    object_path : str
        D-Bus object path
    interface_name : str
        D-Bus interface name
    """
    _connection_pool.invalidate_proxy(bus_type, service_name, object_path, interface_name)


def cleanup() -> None:
    """Close all connections in the pool."""
    _connection_pool.cleanup()


def connection_manager(
    bus_type: str = 'system',
    timeout: float = 5.0
) -> DBusConnectionManager:
    """
    Create a connection manager for use in a with statement.
    
    Parameters
    ----------
    bus_type : str
        Type of bus to get a connection for
    timeout : float
        Maximum time in seconds to wait for a connection
        
    Returns
    -------
    DBusConnectionManager
        Connection manager
        
    Example
    -------
    >>> with connection_manager() as bus:
    ...     obj = bus.get_object("org.freedesktop.DBus", "/")
    ...     # Do something with obj
    """
    return DBusConnectionManager(_connection_pool, bus_type, timeout)
