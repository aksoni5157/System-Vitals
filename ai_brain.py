"""
================================================================================
 System Vitals AI — AI Reasoning Layer
 File: ai_brain.py
================================================================================
 Purpose:
    The "brain" of the ecosystem. Two cooperating reasoning personas:

      1. Device Doctor   — diagnoses hardware stress (CPU throttling risk,
                            RAM pressure, storage/battery concerns) and turns
                            raw numbers into plain-language findings.

      2. Wellness Coach   — diagnoses digital wellbeing risk from unbroken
                            session duration and correlates it with hardware
                            stress (e.g. "you've been pushing the CPU hard
                            for 90 minutes straight without a break").

    Both personas feed into a single, EXPLAINABLE "Life Balance Score"
    (0-100): explainable means every point deducted is traceable to a named
    factor, returned alongside the score so the GUI can show *why* the score
    is what it is instead of a black-box number.

 Design notes:
    - Pure logic module: no GUI imports, no direct DB imports. It receives
      plain numbers/dicts and returns plain numbers/dicts/strings. This
      keeps it independently unit-testable and reusable on a future
      Android node without dragging CustomTkinter along.
    - All thresholds are defined as class-level constants at the top of
      AIBrain so they're easy to tune/calibrate without hunting through
      method bodies.
================================================================================
"""

import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

logger = logging.getLogger("SystemVitalsAI.AIBrain")
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(
        logging.Formatter("[%(asctime)s] [%(levelname)s] [AI_BRAIN] %(message)s")
    )
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)


@dataclass
class ScoreFactor:
    """
    One explainable component of the Life Balance Score.
    `impact` is negative for penalties, positive for bonuses (rare), so the
    GUI can render a simple "+/-" breakdown list.
    """
    name: str
    impact: float
    reason: str


@dataclass
class Diagnosis:
    """
    Full output bundle from AIBrain.analyze() — everything app.py needs to
    render the Right Panel in one shot.
    """
    balance_score: float
    score_factors: List[ScoreFactor] = field(default_factory=list)
    device_doctor_messages: List[str] = field(default_factory=list)
    wellness_coach_messages: List[str] = field(default_factory=list)
    severity: str = "good"  # one of: 'good', 'moderate', 'warning', 'critical'


class AIBrain:
    """
    Stateless-per-call reasoning engine (holds only tunable thresholds as
    instance config, no mutable session state — the caller passes in
    everything relevant each time via analyze()).
    """

    # ---------------- Device Doctor thresholds ----------------
    CPU_HIGH_THRESHOLD = 80.0        # % sustained load considered "high"
    CPU_CRITICAL_THRESHOLD = 92.0    # % load considered throttling-risk territory
    RAM_HIGH_THRESHOLD = 85.0        # % usage considered "high"
    RAM_CRITICAL_THRESHOLD = 95.0    # % usage considered critical
    STORAGE_LOW_HEALTH_THRESHOLD = 75.0
    BATTERY_LOW_SOH_THRESHOLD = 80.0  # below this, battery is "aging"
    BATTERY_LOW_CHARGE_THRESHOLD = 15.0  # % charge, unplugged, considered urgent

    # ---------------- Wellness Coach thresholds ----------------
    SESSION_SOFT_LIMIT_MIN = 45.0    # gentle reminder threshold
    SESSION_HARD_LIMIT_MIN = 90.0    # strong warning threshold
    SESSION_CRITICAL_LIMIT_MIN = 150.0  # urgent — ignored multiple reminders

    def __init__(self):
        logger.info("AIBrain reasoning engine initialized.")

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------
    def analyze(
        self,
        cpu_load: float,
        ram_usage: float,
        storage_health: float,
        battery_soh: float,
        battery_charge_pct: Optional[float],
        battery_plugged: bool,
        session_mins: float,
        breaks_ignored_count: int = 0,
    ) -> Diagnosis:
        """
        Run both personas over the current telemetry + session state and
        produce a single explainable Diagnosis.

        Parameters mirror the fields produced by TelemetryEngine snapshots
        plus a `breaks_ignored_count` the GUI tracks (how many break
        reminders have fired and been dismissed without a real pause).
        """
        factors: List[ScoreFactor] = []
        device_messages: List[str] = []
        wellness_messages: List[str] = []

        # ---------------- Device Doctor reasoning ----------------
        self._diagnose_cpu(cpu_load, factors, device_messages)
        self._diagnose_ram(ram_usage, factors, device_messages)
        self._diagnose_storage(storage_health, factors, device_messages)
        self._diagnose_battery(
            battery_soh, battery_charge_pct, battery_plugged, factors, device_messages
        )

        # ---------------- Wellness Coach reasoning ----------------
        self._diagnose_session(session_mins, breaks_ignored_count, factors, wellness_messages)

        # ---------------- Cross-domain correlation ----------------
        # This is the "explainable AI" flourish: detecting a COMBINATION of
        # hardware stress + ignored wellbeing signals, which is worse than
        # the sum of its parts because it suggests the user is pushing
        # through fatigue on a struggling machine.
        self._diagnose_combined_risk(
            cpu_load, session_mins, breaks_ignored_count, factors, wellness_messages
        )

        if not device_messages:
            device_messages.append(
                "Device Doctor: All hardware vitals are within healthy operating ranges."
            )
        if not wellness_messages:
            wellness_messages.append(
                "Wellness Coach: Your current session length looks sustainable. Keep it up."
            )

        score = self._compute_balance_score(factors)
        severity = self._severity_from_score(score)

        return Diagnosis(
            balance_score=score,
            score_factors=factors,
            device_doctor_messages=device_messages,
            wellness_coach_messages=wellness_messages,
            severity=severity,
        )

    # ------------------------------------------------------------------
    # Device Doctor sub-diagnoses
    # ------------------------------------------------------------------
    def _diagnose_cpu(self, cpu_load: float, factors: List[ScoreFactor], messages: List[str]) -> None:
        if cpu_load >= self.CPU_CRITICAL_THRESHOLD:
            factors.append(ScoreFactor(
                "cpu_critical", -20.0,
                f"CPU load at {cpu_load:.0f}% — sustained levels this high risk thermal throttling."
            ))
            messages.append(
                f"Device Doctor: CPU load is critically high at {cpu_load:.0f}%. "
                "Consider closing background apps or enabling Cooling Mode to prevent throttling."
            )
        elif cpu_load >= self.CPU_HIGH_THRESHOLD:
            factors.append(ScoreFactor(
                "cpu_high", -10.0,
                f"CPU load at {cpu_load:.0f}% is elevated above the {self.CPU_HIGH_THRESHOLD:.0f}% comfort threshold."
            ))
            messages.append(
                f"Device Doctor: CPU load is running high ({cpu_load:.0f}%). "
                "Your system is under noticeable strain."
            )

    def _diagnose_ram(self, ram_usage: float, factors: List[ScoreFactor], messages: List[str]) -> None:
        if ram_usage >= self.RAM_CRITICAL_THRESHOLD:
            factors.append(ScoreFactor(
                "ram_critical", -15.0,
                f"RAM usage at {ram_usage:.0f}% — the system is near memory exhaustion."
            ))
            messages.append(
                f"Device Doctor: Memory usage is critical at {ram_usage:.0f}%. "
                "Expect slowdowns or app crashes; close unused tabs/programs."
            )
        elif ram_usage >= self.RAM_HIGH_THRESHOLD:
            factors.append(ScoreFactor(
                "ram_high", -8.0,
                f"RAM usage at {ram_usage:.0f}% is above the {self.RAM_HIGH_THRESHOLD:.0f}% comfort threshold."
            ))
            messages.append(
                f"Device Doctor: Memory usage is elevated ({ram_usage:.0f}%). "
                "Multitasking is starting to strain available RAM."
            )

    def _diagnose_storage(self, storage_health: float, factors: List[ScoreFactor], messages: List[str]) -> None:
        if storage_health < self.STORAGE_LOW_HEALTH_THRESHOLD:
            factors.append(ScoreFactor(
                "storage_low", -8.0,
                f"Storage health estimate at {storage_health:.0f}% suggests low free space or wear."
            ))
            messages.append(
                f"Device Doctor: Storage health estimate is {storage_health:.0f}%. "
                "Free up disk space soon to avoid performance degradation."
            )

    def _diagnose_battery(
        self,
        battery_soh: float,
        battery_charge_pct: Optional[float],
        battery_plugged: bool,
        factors: List[ScoreFactor],
        messages: List[str],
    ) -> None:
        # -1.0 is the sentinel for "no battery present" (desktop) — skip entirely.
        if battery_soh is None or battery_soh < 0:
            return

        if battery_soh < self.BATTERY_LOW_SOH_THRESHOLD:
            factors.append(ScoreFactor(
                "battery_aging", -6.0,
                f"Battery State-of-Health estimate at {battery_soh:.0f}% indicates aging capacity."
            ))
            messages.append(
                f"Device Doctor: Battery health is estimated at {battery_soh:.0f}%. "
                "Consider a battery calibration check or replacement planning."
            )

        if (
            battery_charge_pct is not None
            and battery_charge_pct >= 0
            and battery_charge_pct <= self.BATTERY_LOW_CHARGE_THRESHOLD
            and not battery_plugged
        ):
            factors.append(ScoreFactor(
                "battery_low_charge", -5.0,
                f"Battery charge at {battery_charge_pct:.0f}% and unplugged."
            ))
            messages.append(
                f"Device Doctor: Battery charge is low ({battery_charge_pct:.0f}%) and not "
                "plugged in. Consider enabling Battery Saver."
            )

    # ------------------------------------------------------------------
    # Wellness Coach sub-diagnosis
    # ------------------------------------------------------------------
    def _diagnose_session(
        self,
        session_mins: float,
        breaks_ignored_count: int,
        factors: List[ScoreFactor],
        messages: List[str],
    ) -> None:
        if session_mins >= self.SESSION_CRITICAL_LIMIT_MIN:
            factors.append(ScoreFactor(
                "session_critical", -25.0,
                f"{session_mins:.0f} minutes of unbroken screen time — well beyond healthy limits."
            ))
            messages.append(
                f"Wellness Coach: You've been active for {session_mins:.0f} minutes straight "
                f"({breaks_ignored_count} reminder(s) dismissed). Please step away for at least 10 minutes."
            )
        elif session_mins >= self.SESSION_HARD_LIMIT_MIN:
            factors.append(ScoreFactor(
                "session_hard", -15.0,
                f"{session_mins:.0f} minutes of unbroken screen time exceeds the recommended 90-minute limit."
            ))
            messages.append(
                f"Wellness Coach: {session_mins:.0f} minutes without a break is starting to add up. "
                "A short walk or stretch would help your focus."
            )
        elif session_mins >= self.SESSION_SOFT_LIMIT_MIN:
            factors.append(ScoreFactor(
                "session_soft", -6.0,
                f"{session_mins:.0f} minutes of continuous session time — approaching the 45-minute guideline."
            ))
            messages.append(
                f"Wellness Coach: You're at {session_mins:.0f} minutes of focused time. "
                "Consider a short break coming up soon."
            )

    # ------------------------------------------------------------------
    # Cross-domain correlation — the "explainable AI" highlight feature
    # ------------------------------------------------------------------
    def _diagnose_combined_risk(
        self,
        cpu_load: float,
        session_mins: float,
        breaks_ignored_count: int,
        factors: List[ScoreFactor],
        messages: List[str],
    ) -> None:
        """
        Detects the specific pattern called out in the project brief:
        CPU throttling risk COMBINED WITH ignored break reminders. This is
        treated as a distinct, additional penalty beyond the two individual
        factors because it represents compounding risk (user pushing a
        struggling machine through fatigue).
        """
        cpu_is_stressed = cpu_load >= self.CPU_HIGH_THRESHOLD
        session_is_long = session_mins >= self.SESSION_HARD_LIMIT_MIN
        breaks_being_ignored = breaks_ignored_count >= 2

        if cpu_is_stressed and session_is_long and breaks_being_ignored:
            factors.append(ScoreFactor(
                "combined_fatigue_and_thermal_risk", -12.0,
                "Compounding pattern: sustained high CPU load coincides with a long, "
                "unbroken session and multiple dismissed break reminders."
            ))
            messages.append(
                "Wellness Coach + Device Doctor: We're seeing high CPU load AND a long "
                f"session ({session_mins:.0f} min) where {breaks_ignored_count} break "
                "reminders were dismissed. This combination often means both you and your "
                "device are being pushed past a healthy limit at the same time — please "
                "pause now."
            )

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------
    def _compute_balance_score(self, factors: List[ScoreFactor]) -> float:
        """
        Start at a perfect 100 and apply every factor's impact. Clamped to
        [0, 100]. Because every deduction is a named ScoreFactor, the GUI
        can render a transparent breakdown — this is what makes the score
        "explainable" rather than an opaque model output.
        """
        score = 100.0
        for factor in factors:
            score += factor.impact
        return round(max(0.0, min(100.0, score)), 1)

    @staticmethod
    def _severity_from_score(score: float) -> str:
        """Maps the numeric score to a UI-friendly severity bucket + color hint."""
        if score >= 80:
            return "good"       # green
        elif score >= 60:
            return "moderate"   # yellow
        elif score >= 40:
            return "warning"    # orange
        else:
            return "critical"   # red

    @staticmethod
    def severity_to_color(severity: str) -> str:
        """
        Central color mapping so app.py never hardcodes hex values that
        could drift out of sync with the severity logic above.
        """
        return {
            "good": "#2ECC71",       # green
            "moderate": "#F1C40F",   # yellow
            "warning": "#E67E22",    # orange
            "critical": "#E74C3C",   # red
        }.get(severity, "#95A5A6")   # grey fallback


# ------------------------------------------------------------------------
# Manual smoke test — run `python ai_brain.py` to see example
# diagnoses for a healthy vs. a stressed scenario without any other module.
# ------------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    brain = AIBrain()

    print("=== Healthy scenario ===")
    result = brain.analyze(
        cpu_load=35.0, ram_usage=50.0, storage_health=95.0,
        battery_soh=92.0, battery_charge_pct=80.0, battery_plugged=True,
        session_mins=20.0, breaks_ignored_count=0,
    )
    print("Score:", result.balance_score, "| Severity:", result.severity)
    for m in result.device_doctor_messages + result.wellness_coach_messages:
        print(" -", m)

    print("\n=== Stressed scenario (throttling risk + ignored breaks) ===")
    result = brain.analyze(
        cpu_load=94.0, ram_usage=88.0, storage_health=70.0,
        battery_soh=74.0, battery_charge_pct=12.0, battery_plugged=False,
        session_mins=120.0, breaks_ignored_count=3,
    )
    print("Score:", result.balance_score, "| Severity:", result.severity)
    for m in result.device_doctor_messages + result.wellness_coach_messages:
        print(" -", m)
    print("Factors:")
    for f in result.score_factors:
        print(f"   {f.name}: {f.impact} — {f.reason}")
