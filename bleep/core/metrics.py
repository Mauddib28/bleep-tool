"""
Controller Health Metrics

This module provides functionality for tracking D-Bus call latency statistics
and error rates to detect potential issues before they cause significant problems.
"""

import time
import threading
from collections import defaultdict
from typing import Dict, List, Optional, Any, Tuple, Union

from bleep.core.log import print_and_log, LOG__DEBUG


class LatencyTracker:
    """
    Tracks latency statistics for D-Bus operations.
    
    This class maintains a rolling window of latency samples for different
    operation types and calculates statistics for early warning detection.
    """
    
    def __init__(self, window_size: int = 100):
        """
        Initialize latency tracker with specified window size.
        
        Parameters
        ----------
        window_size : int
            Number of samples to keep for each operation type
        """
        self._window_size = window_size
        self._samples: Dict[str, List[float]] = defaultdict(list)
        self._lock = threading.Lock()
    
    def record_latency(self, operation: str, latency: float) -> None:
        """
        Record a latency sample for an operation.
        
        Parameters
        ----------
        operation : str
            Type of operation (e.g., 'connect', 'read_characteristic')
        latency : float
            Latency in seconds
        """
        with self._lock:
            samples = self._samples[operation]
            samples.append(latency)
            
            # Keep only the most recent samples
            while len(samples) > self._window_size:
                samples.pop(0)
    
    def get_statistics(self, operation: str) -> Dict[str, float]:
        """
        Get statistics for an operation type.
        
        Parameters
        ----------
        operation : str
            Type of operation
            
        Returns
        -------
        Dict[str, float]
            Dictionary containing statistics:
            - 'min': Minimum latency
            - 'max': Maximum latency
            - 'avg': Average latency
            - 'p90': 90th percentile latency
            - 'p95': 95th percentile latency
            - 'p99': 99th percentile latency
            - 'count': Number of samples
        """
        with self._lock:
            samples = self._samples.get(operation, [])
            
            if not samples:
                return {
                    'min': 0.0,
                    'max': 0.0,
                    'avg': 0.0,
                    'p90': 0.0,
                    'p95': 0.0,
                    'p99': 0.0,
                    'count': 0
                }
            
            # Sort for percentile calculations
            sorted_samples = sorted(samples)
            count = len(sorted_samples)
            
            return {
                'min': sorted_samples[0],
                'max': sorted_samples[-1],
                'avg': sum(sorted_samples) / count,
                'p90': sorted_samples[int(count * 0.9)],
                'p95': sorted_samples[int(count * 0.95)],
                'p99': sorted_samples[int(count * 0.99)],
                'count': count
            }
    
    def get_all_statistics(self) -> Dict[str, Dict[str, float]]:
        """
        Get statistics for all operation types.
        
        Returns
        -------
        Dict[str, Dict[str, float]]
            Dictionary mapping operation types to their statistics
        """
        result = {}
        for operation in self._samples:
            result[operation] = self.get_statistics(operation)
        return result


class ErrorTracker:
    """
    Tracks error rates for D-Bus operations.
    
    This class maintains counts of successful and failed operations to
    calculate error rates for detecting systemic issues.
    """
    
    def __init__(self, window_period: float = 300.0):
        """
        Initialize error tracker with specified window period.
        
        Parameters
        ----------
        window_period : float
            Time window in seconds for calculating error rates
        """
        self._window_period = window_period
        self._operations: Dict[str, List[Tuple[float, bool]]] = defaultdict(list)
        self._lock = threading.Lock()
    
    def record_operation(self, operation: str, success: bool) -> None:
        """
        Record the outcome of an operation.
        
        Parameters
        ----------
        operation : str
            Type of operation
        success : bool
            Whether the operation was successful
        """
        with self._lock:
            timestamp = time.time()
            self._operations[operation].append((timestamp, success))
            self._prune_old_entries(operation, timestamp)
    
    def _prune_old_entries(self, operation: str, current_time: float) -> None:
        """
        Remove entries older than the window period.
        
        Parameters
        ----------
        operation : str
            Type of operation
        current_time : float
            Current timestamp
        """
        cutoff = current_time - self._window_period
        entries = self._operations[operation]
        
        # Find index of first entry within window
        i = 0
        while i < len(entries) and entries[i][0] < cutoff:
            i += 1
        
        # Remove old entries
        if i > 0:
            self._operations[operation] = entries[i:]
    
    def get_error_rate(self, operation: str) -> Tuple[float, int, int]:
        """
        Calculate error rate for an operation type.
        
        Parameters
        ----------
        operation : str
            Type of operation
            
        Returns
        -------
        Tuple[float, int, int]
            Tuple containing (error_rate, total_operations, failed_operations)
        """
        with self._lock:
            entries = self._operations.get(operation, [])
            if not entries:
                return 0.0, 0, 0
            
            total = len(entries)
            failures = sum(1 for _, success in entries if not success)
            
            return failures / total if total > 0 else 0.0, total, failures
    
    def get_all_error_rates(self) -> Dict[str, Tuple[float, int, int]]:
        """
        Get error rates for all operation types.
        
        Returns
        -------
        Dict[str, Tuple[float, int, int]]
            Dictionary mapping operation types to their error rates
        """
        with self._lock:
            current_time = time.time()
            result = {}
            
            for operation in list(self._operations.keys()):
                self._prune_old_entries(operation, current_time)
                result[operation] = self.get_error_rate(operation)
            
            return result


class DBusMetricsCollector:
    """
    Collects metrics for D-Bus operations.
    
    This class combines latency tracking and error tracking to provide
    a comprehensive view of D-Bus operation health.
    """
    
    def __init__(self, latency_window_size: int = 100, error_window_period: float = 300.0):
        """
        Initialize metrics collector.
        
        Parameters
        ----------
        latency_window_size : int
            Number of samples to keep for latency statistics
        error_window_period : float
            Time window in seconds for error rate calculation
        """
        self._latency_tracker = LatencyTracker(window_size=latency_window_size)
        self._error_tracker = ErrorTracker(window_period=error_window_period)
    
    def record_operation(self, operation: str, latency: float, success: bool) -> None:
        """
        Record metrics for an operation.
        
        Parameters
        ----------
        operation : str
            Type of operation
        latency : float
            Operation latency in seconds
        success : bool
            Whether the operation was successful
        """
        self._latency_tracker.record_latency(operation, latency)
        self._error_tracker.record_operation(operation, success)
    
    def get_metrics(self, operation: Optional[str] = None) -> Dict[str, Any]:
        """
        Get metrics for one or all operation types.
        
        Parameters
        ----------
        operation : Optional[str]
            Operation type to get metrics for, or None for all
            
        Returns
        -------
        Dict[str, Any]
            Dictionary containing metrics
        """
        if operation:
            return {
                'latency': self._latency_tracker.get_statistics(operation),
                'error_rate': self._error_tracker.get_error_rate(operation)
            }
        else:
            return {
                'latency': self._latency_tracker.get_all_statistics(),
                'error_rate': self._error_tracker.get_all_error_rates()
            }
    
    def detect_issues(self, thresholds: Dict[str, Dict[str, float]] = None) -> Dict[str, List[str]]:
        """
        Detect potential issues based on metrics.
        
        Parameters
        ----------
        thresholds : Optional[Dict[str, Dict[str, float]]]
            Dictionary mapping operation types to threshold dictionaries:
            {
                'operation_type': {
                    'p95_latency': 0.5,  # 500ms threshold for p95 latency
                    'error_rate': 0.05   # 5% threshold for error rate
                }
            }
            
        Returns
        -------
        Dict[str, List[str]]
            Dictionary mapping operation types to lists of detected issues
        """
        thresholds = thresholds or {}
        default_thresholds = {
            'p95_latency': 1.0,  # 1 second
            'error_rate': 0.1    # 10%
        }
        
        issues = {}
        
        # Check all operations
        latency_stats = self._latency_tracker.get_all_statistics()
        error_rates = self._error_tracker.get_all_error_rates()
        
        for operation in set(list(latency_stats.keys()) + list(error_rates.keys())):
            operation_issues = []
            
            # Get thresholds for this operation or use defaults
            op_thresholds = thresholds.get(operation, default_thresholds)
            
            # Check latency
            if operation in latency_stats:
                stats = latency_stats[operation]
                if stats['count'] >= 5:  # Only consider operations with enough samples
                    if stats['p95'] > op_thresholds.get('p95_latency', default_thresholds['p95_latency']):
                        operation_issues.append(
                            f"High latency: P95={stats['p95']:.3f}s"
                        )
            
            # Check error rate
            if operation in error_rates:
                error_rate, total, failures = error_rates[operation]
                if total >= 5:  # Only consider operations with enough samples
                    if error_rate > op_thresholds.get('error_rate', default_thresholds['error_rate']):
                        operation_issues.append(
                            f"High error rate: {error_rate:.1%} ({failures}/{total})"
                        )
            
            if operation_issues:
                issues[operation] = operation_issues
        
        return issues
    
    def log_metrics_summary(self) -> None:
        """Log a summary of current metrics."""
        metrics = self.get_metrics()
        issues = self.detect_issues()
        
        if issues:
            print_and_log(
                "[!] D-Bus metrics issues detected:",
                LOG__DEBUG
            )
            for operation, operation_issues in issues.items():
                for issue in operation_issues:
                    print_and_log(
                        f"[!] {operation}: {issue}",
                        LOG__DEBUG
                    )
        
        # Log detailed metrics at debug level
        print_and_log(
            f"[DEBUG] D-Bus metrics: {metrics}",
            LOG__DEBUG
        )


# Singleton instance
_metrics_collector = DBusMetricsCollector()


def get_metrics_collector() -> DBusMetricsCollector:
    """
    Get the singleton metrics collector instance.
    
    Returns
    -------
    DBusMetricsCollector
        Singleton metrics collector instance
    """
    return _metrics_collector


def record_operation(operation: str, latency: float, success: bool) -> None:
    """
    Record metrics for an operation.
    
    Parameters
    ----------
    operation : str
        Type of operation
    latency : float
        Operation latency in seconds
    success : bool
        Whether the operation was successful
    """
    _metrics_collector.record_operation(operation, latency, success)


def get_metrics(operation: Optional[str] = None) -> Dict[str, Any]:
    """
    Get metrics for one or all operation types.
    
    Parameters
    ----------
    operation : Optional[str]
        Operation type to get metrics for, or None for all
        
    Returns
    -------
    Dict[str, Any]
        Dictionary containing metrics
    """
    return _metrics_collector.get_metrics(operation)


def detect_issues(thresholds: Dict[str, Dict[str, float]] = None) -> Dict[str, List[str]]:
    """
    Detect potential issues based on metrics.
    
    Parameters
    ----------
    thresholds : Optional[Dict[str, Dict[str, float]]]
        Dictionary mapping operation types to threshold dictionaries
        
    Returns
    -------
    Dict[str, List[str]]
        Dictionary mapping operation types to lists of detected issues
    """
    return _metrics_collector.detect_issues(thresholds)


def log_metrics_summary() -> None:
    """Log a summary of current metrics."""
    _metrics_collector.log_metrics_summary()
