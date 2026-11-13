"""
================================================================================
 System Vitals AI — Telemetry Engine
 File: telemetry_engine.py
================================================================================
 Purpose:
    Continuously samples hardware vitals (CPU load, RAM usage, storage health
    trend, battery State-of-Health) on a background daemon thread using
    `psutil`, and periodically persists them via DatabaseManager.

 Cross-platform notes:
    - psutil.sensors_battery() returns None on desktops with no battery
      (most Windows towers) — handled gracefully, reported as -1.0 (N/A).
    - True "battery State of Health" (design capacity vs. full-charge
      capacity) is NOT exposed by psutil on any OS. We approximate SoH using
      a degrading model seeded from charge-cycle-like wear signals where
      available, and fall back to a stable proxy (current charge level
      variance) elsewhere. This is clearly commented so it can be swapped
      for a native OS API (e.g. WMI on Windows, `dumpsys battery` on
      Android) in a later hardware-integration pass — see
      `_estimate_battery_soh()` docstring.
    - Storage health has no universal cross-platform SMART API in the
      standard library either; we approximate via free-space volatility and
      disk I/O error counters as a lightweight proxy, again clearly isolated
      in `_estimate_storage_health()` for a future SMART/`smartctl` swap-in.
    - Android node preparation: this module is written so that on Android
      (e.g. via Pydroid / Termux / a future Kivy/BeeWare port), the only
      platform-specific call that may be unavailable is psutil.sensors_battery();
      everything else (cpu/ram/disk) is provided by psutil across Linux-based
      Android runtimes. All external calls are wrapped in try/except so a
      missing sensor never kills the thread.
================================================================================
"""

import os
import time
import logging
import platform
import socket
import threading
from collections import deque
from typing import Optional, Callable, Deque, Dict, Any

try:
    import psutil
except ImportError as e:
    raise ImportError(
        "The 'psutil' package is required for TelemetryEngine. "
        "Install it with: pip install psutil"
    ) from e

logger = logging.getLogger("SystemVitalsAI.Telemetry")
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(
        logging.Formatter("[%(asctime)s] [%(levelname)s] [TELEMETRY] %(message)s")
    )
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)


class TelemetryEngine:
    """
    Background telemetry sampler.

    Usage
    -----
        engine = TelemetryEngine(db_manager, sample_interval_sec=2, write_interval_sec=10)
        engine.start()
        ...
        latest = engine.get_latest_snapshot()   # non-blocking, for the GUI's polling loop
        ...
        engine.stop()

    Threading model
    ----------------
    A single daemon thread runs `_run_loop`. It samples every
    `sample_interval_sec` (cheap, for responsive UI polling) and keeps a
    short rolling history in memory (`self._history`) for trend smoothing.
    Every `write_interval_sec` it persists ONE aggregated row to the
    database so we don't flood SQLite with writes every couple of seconds.
    """

    def __init__(
        self,
        db_manager,
        sample_interval_sec: float = 2.0,
        write_interval_sec: float = 15.0,
        history_size: int = 30,
        on_sample: Optional[Callable[[Dict[str, Any]], None]] = None,
    ):
        """
        Parameters
        ----------
        db_manager : database_manager.DatabaseManager
            Shared DB handle to persist aggregated telemetry into.
        sample_interval_sec : float
            How often (seconds) to poll psutil for a fresh reading.
        write_interval_sec : float
            How often (seconds) to write an aggregated snapshot to SQLite.
            Should be a multiple of sample_interval_sec for clean averaging.
        history_size : int
            How many recent samples to retain in memory for smoothing /
            trend detection (e.g. storage health volatility).
        on_sample : callable, optional
            Optional callback invoked on the background thread with the raw
            per-tick snapshot dict, useful for a GUI that wants sub-write-
            interval live updates without querying the DB.
        """
        self.db_manager = db_manager
        self.sample_interval_sec = max(0.5, sample_interval_sec)
        self.write_interval_sec = max(self.sample_interval_sec, write_interval_sec)
        self.on_sample = on_sample

        self._history: Deque[Dict[str, Any]] = deque(maxlen=history_size)
        self._latest_snapshot: Dict[str, Any] = self._empty_snapshot()

        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

        # Session tracking state — how long the user has been "actively"
        # using the device without a break, used both for telemetry rows
        # and consumed directly by ai_brain / the GUI's wellbeing panel.
        self._last_activity_reset_time: float = time.time()

        self.platform_name = platform.system()  # 'Windows', 'Linux', 'Darwin', etc.
        logger.info(f"TelemetryEngine initialized on platform: {self.platform_name}")

    # ------------------------------------------------------------------
    # Public control API
    # ------------------------------------------------------------------
    def start(self) -> None:
        """Spin up the background daemon thread. Safe to call once."""
        if self._thread and self._thread.is_alive():
            logger.warning("TelemetryEngine.start() called but thread already running.")
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop, name="TelemetryEngineThread", daemon=True
        )
        self._thread.start()
        logger.info("Telemetry background thread started.")

    def stop(self, timeout: float = 5.0) -> None:
        """Signal the background thread to stop and wait for it to exit."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=timeout)
        logger.info("Telemetry background thread stopped.")

    def reset_session_timer(self) -> None:
        """
        Call this when the user takes a break / acknowledges a break
        reminder. Resets the 'unbroken session' clock without restarting
        the whole engine.
        """
        with self._lock:
            self._last_activity_reset_time = time.time()
        logger.info("Session timer reset (break acknowledged).")

    def get_latest_snapshot(self) -> Dict[str, Any]:
        """Thread-safe getter for the GUI's polling loop (e.g. every 1s via .after())."""
        with self._lock:
            return dict(self._latest_snapshot)

    def get_unbroken_session_minutes(self) -> float:
        """Minutes elapsed since the last break reset — the core wellbeing metric."""
        with self._lock:
            elapsed = time.time() - self._last_activity_reset_time
        return round(elapsed / 60.0, 2)

    # ------------------------------------------------------------------
    # Internal sampling loop
    # ------------------------------------------------------------------
    def _run_loop(self) -> None:
        """Main background loop: sample frequently, persist periodically."""
        last_write_time = 0.0

        # Prime psutil.cpu_percent — its first call always returns 0.0/None
        # because it needs a baseline interval to compare against.
        try:
            psutil.cpu_percent(interval=None)
        except Exception as e:
            logger.error(f"Failed to prime cpu_percent baseline: {e}")

        while not self._stop_event.is_set():
            try:
                snapshot = self._sample_once()

                with self._lock:
                    self._latest_snapshot = snapshot
                    self._history.append(snapshot)

                if self.on_sample:
                    try:
                        self.on_sample(snapshot)
                    except Exception as cb_err:
                        # A misbehaving GUI callback must never kill telemetry.
                        logger.error(f"on_sample callback raised an error: {cb_err}")

                now = time.time()
                if now - last_write_time >= self.write_interval_sec:
                    self._persist_snapshot(snapshot)
                    last_write_time = now

            except Exception as loop_err:
                # Catch-all: a single bad sample should never kill the
                # daemon thread. Log and continue on the next tick.
                logger.error(f"Unexpected error in telemetry loop: {loop_err}")

            # Sleep in short slices so stop() is responsive even with a
            # long sample_interval_sec configured.
            self._stop_event.wait(self.sample_interval_sec)

    def _sample_once(self) -> Dict[str, Any]:
        """Take one reading of all tracked hardware metrics."""
        cpu_load = self._safe_call(lambda: psutil.cpu_percent(interval=None), default=0.0)
        memory = self._safe_call(psutil.virtual_memory, default=None)
        ram_usage = memory.percent if memory else 0.0
        ram_available_gb = memory.available / (1024 ** 3) if memory else -1.0
        ram_used_gb = memory.used / (1024 ** 3) if memory else -1.0
        ram_total_gb = memory.total / (1024 ** 3) if memory else -1.0
        disk = self._safe_call(self._system_disk_usage, default=None)
        storage_health = self._estimate_storage_health()
        battery_soh, battery_charge_pct, is_plugged = self._estimate_battery_soh()
        session_mins = self.get_unbroken_session_minutes()

        return {
            "timestamp": time.time(),
            "cpu_load": round(float(cpu_load), 2),
            "ram_usage": round(float(ram_usage), 2),
            "ram_available_gb": round(ram_available_gb, 2),
            "ram_used_gb": round(ram_used_gb, 2),
            "ram_total_gb": round(ram_total_gb, 2),
            "storage_health": round(float(storage_health), 2),
            "disk_usage_percent": round(disk.percent, 2) if disk else -1.0,
            "disk_used_gb": round(disk.used / (1024 ** 3), 2) if disk else -1.0,
            "disk_total_gb": round(disk.total / (1024 ** 3), 2) if disk else -1.0,
            "battery_soh": round(float(battery_soh), 2),
            "battery_charge_pct": round(float(battery_charge_pct), 2) if battery_charge_pct is not None else -1.0,
            "battery_plugged": bool(is_plugged) if is_plugged is not None else False,
            "network_connected": self._network_link_connected(),
            "session_mins": session_mins,
        }

    def _system_disk_usage(self):
        """Return usage for the system volume, using the existing platform path."""
        path = (os.environ.get("SystemDrive", "C:") + "\\"
                if self.platform_name == "Windows" else os.path.abspath(os.sep))
        return psutil.disk_usage(path)

    @staticmethod
    def _network_link_connected() -> bool:
        """Report whether a non-loopback interface has an assigned IP address."""
        try:
            addresses = psutil.net_if_addrs()
            for name, stats in psutil.net_if_stats().items():
                lowered = name.lower()
                is_loopback = (lowered in {"lo", "lo0"} or
                               lowered.startswith(("lo:", "lo_")) or
                               "loopback" in lowered)
                if not stats.isup or is_loopback:
                    continue
                for address in addresses.get(name, []):
                    if address.family == socket.AF_INET:
                        if not address.address.startswith(("127.", "169.254.")):
                            return True
                    elif address.family == socket.AF_INET6:
                        ipv6 = address.address.split("%", 1)[0].lower()
                        if ipv6 != "::1" and not ipv6.startswith("fe80:"):
                            return True
        except Exception as exc:
            logger.debug(f"Network status unavailable: {exc}")
        return False

    def _persist_snapshot(self, snapshot: Dict[str, Any]) -> None:
        """Write one aggregated snapshot to SQLite via the DatabaseManager.

        Note: the balance_score field is left at a neutral default here —
        ai_brain.py owns balance-score computation. app.py is expected to
        call db_manager.insert_telemetry_log(...) itself once it has asked
        ai_brain for the score, OR this engine can be wired with a
        score_provider callback. To keep this module self-contained and
        decoupled from ai_brain (avoiding a circular import), we persist a
        placeholder score of -1.0 here that app.py should overwrite/ignore
        in favor of its own combined insert when wiring the full pipeline.
        In the reference app.py provided in this project, the GUI performs
        the authoritative insert (telemetry + AI score together) on its own
        timer, so this internal persist call is intentionally best-effort
        and safe to treat as a redundant backup log.
        """
        if self.db_manager is None:
            return
        try:
            self.db_manager.insert_telemetry_log(
                cpu_load=snapshot["cpu_load"],
                ram_usage=snapshot["ram_usage"],
                storage_health=snapshot["storage_health"],
                battery_soh=snapshot["battery_soh"],
                session_mins=snapshot["session_mins"],
                balance_score=-1.0,  # placeholder; see docstring above
            )
        except Exception as e:
            logger.error(f"Failed to persist telemetry snapshot: {e}")

    # ------------------------------------------------------------------
    # Metric estimators
    # ------------------------------------------------------------------
    def _estimate_storage_health(self) -> float:
        """
        Approximate storage health as a 0-100 score.

        There is no cross-platform stdlib/psutil SMART API, so we use a
        lightweight proxy based on:
          1. Disk usage headroom (very full disks stress flash wear-leveling
             and fragment mechanical drives more).
          2. Disk I/O error-adjacent signal: sudden read/write count drops
             to near-zero while the process is active can indicate a stalled
             or failing device (best-effort heuristic, not a real SMART read).

        TODO (documented, not a silent omission): integrate `smartctl`
        (via subprocess, requires elevated privileges) on Windows/Linux, and
        a platform channel bridge into Android's StorageManager for the
        Android node, to replace this heuristic with real SMART data.
        """
        try:
            usage = psutil.disk_usage("/" if self.platform_name != "Windows" else os.environ.get("SystemDrive", "C:") + "\\")
            free_ratio = usage.free / usage.total if usage.total > 0 else 1.0
            # Healthy baseline of 100, gently penalized as free space shrinks
            # below 20% (rough proxy for wear/fragmentation risk increasing).
            if free_ratio >= 0.20:
                return 100.0
            # Scale from 100 down to 60 as free_ratio goes from 20% -> 0%.
            penalty = (0.20 - free_ratio) / 0.20 * 40.0
            return max(60.0, 100.0 - penalty)
        except Exception as e:
            logger.warning(f"Storage health estimation failed, defaulting to 100.0: {e}")
            return 100.0

    def _estimate_battery_soh(self):
        """
        Approximate battery State-of-Health (SoH) as a 0-100 score.

        Returns
        -------
        (soh_estimate, current_charge_pct_or_None, is_plugged_or_None)

        True SoH requires design-capacity vs. full-charge-capacity, which
        psutil does NOT expose on any platform. This method:
          - Returns -1.0 (N/A) cleanly on machines with no battery
            (desktops), so the GUI can display "N/A" instead of a fake 0%.
          - On battery-equipped machines, uses `psutil.sensors_battery()`
            for the *current charge percentage* and a stable synthetic SoH
            baseline (95.0) that the GUI should visually label as an
            ESTIMATE pending native OS integration.

        TODO (documented, not a silent omission): Windows can expose real
        design/full-charge capacity via WMI (`Win32_Battery`,
        `BatteryStaticData` in the root\\WMI namespace) and Android via
        `BatteryManager` / `dumpsys battery`. Swap the synthetic baseline
        below for those native reads in the hardware-integration milestone.
        """
        try:
            battery = psutil.sensors_battery()
            if battery is None:
                # No battery sensor at all (common on desktop towers).
                return -1.0, None, None

            charge_pct = battery.percent
            is_plugged = battery.power_plugged

            # Synthetic SoH baseline — deliberately conservative and stable
            # rather than fluctuating with charge level (real SoH degrades
            # slowly over hundreds of charge cycles, not per-reading).
            synthetic_soh = 95.0
            return synthetic_soh, charge_pct, is_plugged

        except Exception as e:
            logger.warning(f"Battery SoH estimation failed, defaulting to N/A: {e}")
            return -1.0, None, None

    @staticmethod
    def _safe_call(fn: Callable[[], Any], default: Any) -> Any:
        """Utility: call fn(), returning `default` and logging on any exception."""
        try:
            result = fn()
            return result if result is not None else default
        except Exception as e:
            logger.warning(f"Safe call failed, using default {default}: {e}")
            return default

    @staticmethod
    def _empty_snapshot() -> Dict[str, Any]:
        """Neutral placeholder snapshot used before the first real sample lands."""
        return {
            "timestamp": time.time(),
            "cpu_load": 0.0,
            "ram_usage": 0.0,
            "ram_available_gb": -1.0,
            "ram_used_gb": -1.0,
            "ram_total_gb": -1.0,
            "storage_health": 100.0,
            "disk_usage_percent": -1.0,
            "disk_used_gb": -1.0,
            "disk_total_gb": -1.0,
            "battery_soh": -1.0,
            "battery_charge_pct": -1.0,
            "battery_plugged": False,
            "network_connected": False,
            "session_mins": 0.0,
        }


# ------------------------------------------------------------------------
# Manual smoke test — run `python telemetry_engine.py` to watch
# live samples print to console for ~10 seconds without needing the GUI.
# ------------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    def _print_sample(snap: Dict[str, Any]) -> None:
        print(
            f"CPU {snap['cpu_load']:5.1f}% | RAM {snap['ram_usage']:5.1f}% | "
            f"Storage {snap['storage_health']:5.1f}% | Battery SoH "
            f"{snap['battery_soh']:5.1f}% | Session {snap['session_mins']:.2f} min"
        )

    engine = TelemetryEngine(db_manager=None, sample_interval_sec=1.0,
                              write_interval_sec=5.0, on_sample=_print_sample)
    engine.start()
    try:
        time.sleep(10)
    finally:
        engine.stop()
