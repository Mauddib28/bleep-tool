#!/usr/bin/python3

"""Utility functions for BLEEP core components."""

from typing import Any, Optional, TypeVar, Union, List, Dict, Callable
from bleep.core import log

logger = log.get_logger(__name__)

T = TypeVar('T')


def safe_getattr(obj: Any, attr: str, default: Optional[T] = None) -> Union[Any, T]:
    """
    Safely get an attribute from an object, returning default if
    the object is None or doesn't have the attribute.
    
    This utility helps prevent common AttributeError exceptions when
    working with objects that may be None or lack expected attributes,
    particularly useful when dealing with D-Bus objects that might
    become invalid after disconnection.
    
    Args:
        obj: Object to get attribute from
        attr: Attribute name
        default: Default value if attribute doesn't exist
        
    Returns:
        Attribute value or default
        
    Example:
        >>> device_name = safe_getattr(device, 'name', 'Unknown Device')
        >>> services = safe_getattr(device, 'services', [])
    """
    if obj is None:
        return default
    return getattr(obj, attr, default)


def safe_call(obj: Any, method_name: str, *args, **kwargs) -> Any:
    """
    Safely call a method on an object, handling the case where
    the object is None or doesn't have the requested method.
    
    Args:
        obj: Object to call method on
        method_name: Name of the method to call
        *args: Positional arguments to pass to the method
        **kwargs: Keyword arguments to pass to the method
        
    Returns:
        Result of method call or None if method doesn't exist
        
    Example:
        >>> result = safe_call(device, 'connect')
        >>> properties = safe_call(obj, 'GetAll', 'org.bluez.Device1')
    """
    if obj is None:
        logger.debug(f"Cannot call {method_name} - object is None")
        return None
        
    method = getattr(obj, method_name, None)
    if method is None or not callable(method):
        logger.debug(f"Object does not have callable method {method_name}")
        return None
        
    try:
        return method(*args, **kwargs)
    except Exception as e:
        logger.debug(f"Error calling {method_name}: {e}")
        return None


def defensive_property_access(obj: Any, properties: List[str]) -> Dict[str, Any]:
    """
    Safely access multiple properties from an object, handling missing attributes.
    
    Args:
        obj: Object to get properties from
        properties: List of property names to access
        
    Returns:
        Dictionary mapping property names to their values (or None if missing)
        
    Example:
        >>> props = defensive_property_access(device, ['address', 'name', 'services'])
        >>> address = props['address']  # No KeyError even if property was missing
    """
    result = {}
    for prop in properties:
        result[prop] = safe_getattr(obj, prop)
    return result


def retry_operation(max_attempts: int = 3, delay: float = 1.0) -> Callable:
    """
    Decorator to retry an operation a specified number of times with delay.
    
    Args:
        max_attempts: Maximum number of attempts (default: 3)
        delay: Delay between attempts in seconds (default: 1.0)
        
    Returns:
        Decorated function
        
    Example:
        >>> @retry_operation(max_attempts=2, delay=0.5)
        >>> def flaky_function():
        >>>     # function that might fail sometimes
        >>>     pass
    """
    import time
    
    def decorator(func):
        def wrapper(*args, **kwargs):
            attempts = 0
            last_error = None
            
            while attempts < max_attempts:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    attempts += 1
                    last_error = e
                    logger.debug(f"Attempt {attempts}/{max_attempts} failed: {e}")
                    
                    if attempts < max_attempts:
                        time.sleep(delay)
                    
            logger.warning(f"Operation failed after {max_attempts} attempts: {last_error}")
            raise last_error
            
        return wrapper
    return decorator
