"""
Enumeration controller for multi-attempt device enumeration.

This module orchestrates enumeration attempts with proper error handling
and structured result annotations.  It wraps the low-level connect/enumerate
primitive and, for non-passive modes, delegates to the variant-specific
post-connect logic in ``bleep.ble_ops.le.scan`` (multi-read, write probes,
payload fuzzing).
"""

from __future__ import annotations

import time
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple

from bleep.core.log import print_and_log, LOG__GENERAL, LOG__DEBUG
from bleep.core.errors import (
    ConnectionError,
    NotAuthorizedError,
    DeviceNotFoundError,
    ServicesNotResolvedError,
)
from bleep.ble_ops.le.connect import connect_and_enumerate__bluetooth__low_energy

__all__ = [
    "EnumerationController",
    "EnumerationResult",
    "ConnectionAnnotation",
    "ErrorAction",
]


class ErrorAction(Enum):
    """Action to take based on error type."""
    RECONNECT = "reconnect"  # Timeout, disconnect - retry connection
    ANNOTATE_AND_CONTINUE = "annotate_continue"  # Auth rejection - log and retry
    GIVE_UP = "give_up"  # Agent required, repeated failures - stop trying


@dataclass
class ConnectionAnnotation:
    """Annotation for a connection attempt error."""
    timestamp: float
    error_type: str  # 'auth_required', 'rejected', 'timeout', 'disconnect', 'unknown'
    details: str
    attempted_solution: Optional[str]  # 'reconnect', 'agent_required', None


@dataclass
class EnumerationResult:
    """Result of enumeration attempt(s)."""
    success: bool
    data: Optional[Dict[str, Any]] = None  # Service/characteristic data
    annotations: List[ConnectionAnnotation] = field(default_factory=list)
    error_summary: Optional[str] = None
    attempts: int = 0
    device: Optional[Any] = None  # Device object if successful
    landmine_map: Optional[Dict[str, Any]] = None
    permission_map: Optional[Dict[str, Any]] = None

    @property
    def serialized_annotations(self) -> List[Dict[str, Any]]:
        """Return annotations as a JSON-serialisable list of dicts."""
        return [
            {
                "timestamp": a.timestamp,
                "error_type": a.error_type,
                "details": a.details,
                "attempted_solution": a.attempted_solution,
            }
            for a in self.annotations
        ]

    def persist_security_maps(self, mac: str, source: str = "enum-scan") -> None:
        """Persist landmine/permission maps and annotations to the observation DB.

        Safe to call unconditionally — silently returns if the observation
        module is unavailable or there is nothing to persist.
        """
        if not (self.landmine_map or self.permission_map or self.annotations):
            return
        try:
            from bleep.core import observations as _obs
            _obs.store_security_maps(
                mac,
                landmine_map=self.landmine_map,
                permission_map=self.permission_map,
                enumeration_annotations=self.serialized_annotations or None,
                source=source,
            )
        except Exception:
            pass


class EnumerationController:
    """Orchestrates multi-attempt enumeration with error annotations.

    For ``passive`` mode the controller calls
    ``connect_and_enumerate__bluetooth__low_energy`` directly (base connect +
    service resolution).

    For ``naggy``, ``pokey``, and ``brute``/``bruteforce`` modes the controller
    delegates to the corresponding ``scan.py`` variant function which runs
    variant-specific post-connect logic (multi-read, write probes, or payload
    fuzzing) on top of the same base connect path.

    All modes benefit from the controller's retry loop (up to ``MAX_ATTEMPTS``)
    and typed ``ConnectionAnnotation`` error tracking.
    """

    MAX_ATTEMPTS = 3

    # Maps caller-facing mode names to scan.py variant functions.
    # 'bruteforce' is accepted as an alias for 'brute'.
    _VARIANT_MODES = frozenset({"naggy", "pokey", "brute", "bruteforce"})

    def __init__(self, target_mac: str, *, adapter_name: str | None = None, skip_scan: bool = False):
        """
        Parameters
        ----------
        target_mac : str
            Target device MAC address.
        adapter_name : str | None
            BlueZ controller to use for connect/enumerate (e.g. ``"hci1"``);
            ``None`` keeps the default (``ADAPTER_NAME``). Threaded from
            ``enum-scan --adapter`` (F5b).
        skip_scan : bool
            Skip PRE-FLIGHT discovery in the connect primitive (Device1 already
            exists on this adapter).
        """
        self.target_mac = target_mac.upper()
        self.adapter_name = adapter_name
        self.skip_scan = skip_scan
        self.attempts = 0
        self.annotations: List[ConnectionAnnotation] = []

    # ------------------------------------------------------------------
    # Variant dispatch helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _run_naggy(target: str, *, adapter_name: str | None = None, skip_scan: bool = False) -> Tuple[Any, Dict, Dict, Dict, Dict]:
        """Naggy variant: base connect + 3-round multi-read."""
        from bleep.ble_ops.le.scan import naggy_enum
        result = naggy_enum(target, adapter_name=adapter_name, skip_scan=skip_scan)
        changed = result.get("changed_chars")
        return (
            result.get("device"),
            result.get("mapping", {}),
            result.get("mine_map", {}),
            result.get("perm_map", {}),
            {
                "multi_read": result.get("multi_read"),
                "changed_chars": sorted(changed) if isinstance(changed, set) else changed,
                "device_props": result.get("device_props"),
            },
        )

    @staticmethod
    def _run_pokey(target: str, *, adapter_name: str | None = None, skip_scan: bool = False, **kwargs) -> Tuple[Any, Dict, Dict, Dict, Dict]:
        """Pokey variant: multi-round reconnect + write probes."""
        from bleep.ble_ops.le.scan import pokey_enum
        result = pokey_enum(target, adapter_name=adapter_name, skip_scan=skip_scan, **kwargs)
        return (
            result.get("device"),
            result.get("mapping", {}),
            result.get("mine_map", {}),
            result.get("perm_map", {}),
            {
                "rounds": result.get("rounds"),
                "device_props": result.get("device_props"),
            },
        )

    @staticmethod
    def _run_brute(target: str, *, adapter_name: str | None = None, skip_scan: bool = False, **kwargs) -> Tuple[Any, Dict, Dict, Dict, Dict]:
        """Brute variant: base connect + payload fuzzing."""
        from bleep.ble_ops.le.scan import brute_enum
        result = brute_enum(target, adapter_name=adapter_name, skip_scan=skip_scan, **kwargs)
        return (
            result.get("device"),
            result.get("mapping", {}),
            result.get("mine_map", {}),
            result.get("perm_map", {}),
            {
                "device_props": result.get("device_props"),
            },
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def enumerate(
        self,
        mode: str = "passive",
        *,
        timeout: Optional[int] = None,
        max_attempts: Optional[int] = None,
        **variant_kwargs,
    ) -> EnumerationResult:
        """Perform enumeration with up to *MAX_ATTEMPTS* attempts.

        Parameters
        ----------
        mode : str
            ``'passive'`` (default) — base connect + service resolution only.
            ``'naggy'`` — base connect + 3-round multi-read for value-change
            detection.
            ``'pokey'`` — multi-round reconnect + write probes.  Accepts
            ``rounds`` and ``verify`` kwargs.
            ``'brute'`` / ``'bruteforce'`` — base connect + payload fuzzing.
            Requires ``write_char``; accepts ``value_range``, ``patterns``,
            ``payload_file``, ``force``, ``verify``, ``deep``.
        timeout : int, optional
            Per-phase timeout (seconds) applied to the base-connect path
            (``passive`` mode): bounds both the connect wait and service
            resolution. ``None`` (default) keeps the connect helper's own
            defaults. Ignored by the variant modes (they run their own timing).
        max_attempts : int, optional
            Override the retry-loop bound for this call. ``None`` (default)
            uses the class ``MAX_ATTEMPTS``. Used e.g. to cap seeded ``dual``
            targets to a single LE attempt before falling through to SDP, since
            the Classic half will not answer an LE connect.
        **variant_kwargs
            Forwarded to the variant function (ignored for ``passive``).

        Returns
        -------
        EnumerationResult
            Structured result with data, error annotations, and maps.
        """
        limit = max_attempts if max_attempts and max_attempts > 0 else self.MAX_ATTEMPTS

        print_and_log(
            f"[*] Starting enumeration controller for {self.target_mac} "
            f"(mode={mode}, max {limit} attempts)",
            LOG__GENERAL,
        )

        while self.attempts < limit:
            self.attempts += 1
            print_and_log(
                f"[*] Enumeration attempt {self.attempts}/{limit} "
                f"for {self.target_mac}",
                LOG__GENERAL,
            )

            try:
                extra: Dict[str, Any] = {}
                if mode in self._VARIANT_MODES:
                    device, mapping, landmine_map, perm_map, extra = (
                        self._dispatch_variant(mode, **variant_kwargs)
                    )
                else:
                    connect_kwargs: Dict[str, Any] = {}
                    if timeout is not None:
                        connect_kwargs["timeout_connect"] = timeout
                        connect_kwargs["timeout_services"] = timeout
                    device, mapping, landmine_map, perm_map = (
                        connect_and_enumerate__bluetooth__low_energy(
                            self.target_mac,
                            adapter_name=self.adapter_name,
                            skip_scan=self.skip_scan,
                            **connect_kwargs,
                        )
                    )

                print_and_log(
                    f"[+] Enumeration successful for {self.target_mac} "
                    f"on attempt {self.attempts}",
                    LOG__GENERAL,
                )

                result_data = dict(mapping) if mapping else {}
                if extra:
                    result_data["_variant_extra"] = extra

                return EnumerationResult(
                    success=True,
                    data=result_data,
                    annotations=self.annotations.copy(),
                    attempts=self.attempts,
                    device=device,
                    landmine_map=landmine_map,
                    permission_map=perm_map,
                )

            except Exception as e:
                error_action = self._handle_error(e)
                annotation = self._create_annotation(e, error_action)
                self.annotations.append(annotation)

                if error_action == ErrorAction.GIVE_UP:
                    print_and_log(
                        f"[-] Giving up enumeration for {self.target_mac} "
                        f"after {self.attempts} attempts",
                        LOG__GENERAL,
                    )
                    break
                elif error_action == ErrorAction.RECONNECT:
                    print_and_log(
                        f"[*] Will retry connection for {self.target_mac}",
                        LOG__DEBUG,
                    )
                    time.sleep(1.0)
                elif error_action == ErrorAction.ANNOTATE_AND_CONTINUE:
                    print_and_log(
                        f"[*] Annotated error, will retry for {self.target_mac}",
                        LOG__DEBUG,
                    )
                    time.sleep(0.5)

        error_summary = self._generate_error_summary()
        return EnumerationResult(
            success=False,
            annotations=self.annotations.copy(),
            error_summary=error_summary,
            attempts=self.attempts,
        )

    def _dispatch_variant(
        self, mode: str, **kwargs
    ) -> Tuple[Any, Dict, Dict, Dict, Dict]:
        """Route to the appropriate scan.py variant function."""
        if mode == "naggy":
            return self._run_naggy(
                self.target_mac, adapter_name=self.adapter_name, skip_scan=self.skip_scan
            )
        elif mode == "pokey":
            return self._run_pokey(
                self.target_mac, adapter_name=self.adapter_name, skip_scan=self.skip_scan, **kwargs
            )
        elif mode in ("brute", "bruteforce"):
            return self._run_brute(
                self.target_mac, adapter_name=self.adapter_name, skip_scan=self.skip_scan, **kwargs
            )
        raise ValueError(f"Unknown variant mode: {mode!r}")
    
    def _handle_error(self, error: Exception) -> ErrorAction:
        """
        Determine action based on error type.
        
        Parameters
        ----------
        error : Exception
            The error that occurred
        
        Returns
        -------
        ErrorAction
            Action to take
        """
        # Timeout or connection errors - retry
        if isinstance(error, (ConnectionError, ServicesNotResolvedError)):
            return ErrorAction.RECONNECT
        
        # Authorization errors - annotate and continue (up to limit)
        if isinstance(error, NotAuthorizedError):
            if self.attempts >= 2:
                # After 2 attempts, likely need agent
                return ErrorAction.GIVE_UP
            return ErrorAction.ANNOTATE_AND_CONTINUE
        
        # Device not found - give up (won't appear by retrying)
        if isinstance(error, DeviceNotFoundError):
            return ErrorAction.GIVE_UP
        
        # Check for timeout/disconnect in error message
        error_str = str(error).lower()
        if any(keyword in error_str for keyword in ['timeout', 'disconnect', 'connection']):
            return ErrorAction.RECONNECT
        
        # Check for auth/rejection in error message
        if any(keyword in error_str for keyword in ['auth', 'reject', 'not authorized', 'permission']):
            if self.attempts >= 2:
                return ErrorAction.GIVE_UP
            return ErrorAction.ANNOTATE_AND_CONTINUE
        
        # Unknown error - give up after first attempt to avoid infinite loops
        if self.attempts >= 2:
            return ErrorAction.GIVE_UP
        
        return ErrorAction.RECONNECT
    
    def _create_annotation(self, error: Exception, action: ErrorAction) -> ConnectionAnnotation:
        """
        Create annotation from error.
        
        Parameters
        ----------
        error : Exception
            The error that occurred
        action : ErrorAction
            Action determined for this error
        
        Returns
        -------
        ConnectionAnnotation
            Annotation object
        """
        error_type = "unknown"
        if isinstance(error, ConnectionError):
            error_type = "disconnect"
        elif isinstance(error, NotAuthorizedError):
            error_type = "auth_required"
        elif isinstance(error, ServicesNotResolvedError):
            error_type = "timeout"
        elif isinstance(error, DeviceNotFoundError):
            error_type = "not_found"
        
        attempted_solution = None
        if action == ErrorAction.RECONNECT:
            attempted_solution = "reconnect"
        elif action == ErrorAction.GIVE_UP:
            attempted_solution = "agent_required" if isinstance(error, NotAuthorizedError) else "max_attempts"
        
        return ConnectionAnnotation(
            timestamp=time.time(),
            error_type=error_type,
            details=str(error),
            attempted_solution=attempted_solution,
        )
    
    def _generate_error_summary(self) -> str:
        """
        Generate human-readable error summary.
        
        Returns
        -------
        str
            Summary of errors encountered
        """
        if not self.annotations:
            return "No errors recorded"
        
        error_counts: Dict[str, int] = {}
        for annotation in self.annotations:
            error_counts[annotation.error_type] = error_counts.get(annotation.error_type, 0) + 1
        
        summary_parts = [f"Failed after {self.attempts} attempt(s)"]
        
        for error_type, count in error_counts.items():
            summary_parts.append(f"{error_type}: {count}")
        
        # Add recommendations
        if any(a.error_type == "auth_required" for a in self.annotations):
            summary_parts.append("Recommendation: Agent may be required for pairing")
        
        if any(a.error_type == "timeout" for a in self.annotations):
            summary_parts.append("Recommendation: Device may be out of range or unresponsive")
        
        return "; ".join(summary_parts)
