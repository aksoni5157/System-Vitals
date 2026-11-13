'''chat_engine.py - Simple rule‑based chat assistant for System Vitals AI.

Provides a ChatEngine class with a single public method `respond(snapshot, diagnosis)`
that returns a short textual answer based on the current telemetry snapshot and
the Diagnosis object produced by ai_brain.AIBrain. The implementation is offline
and does not require external API keys or network access.
'''

from typing import Dict, Any

try:
    from ai_brain import Diagnosis  # type: ignore
except Exception:  # pragma: no cover
    Diagnosis = object  # fallback placeholder for type checking only


class ChatEngine:
    """A minimal rule‑based chat engine.

    The engine looks for a handful of keywords in the user's query and builds a
    response using the latest telemetry snapshot and the current AI diagnosis.
    It is intentionally simple – you can extend it with more sophisticated
    intent parsing or plug‑in a real LLM later.
    """

    def __init__(self):
        # Mapping of simple keywords to handler methods
        self._handlers = {
            "cpu": self._cpu_status,
            "ram": self._ram_status,
            "memory": self._ram_status,
            "storage": self._storage_status,
            "disk": self._storage_status,
            "battery": self._battery_status,
            "score": self._score_summary,
            "balance": self._score_summary,
            "break": self._break_advice,
            "help": self._general_help,
        }

    def respond(self, snapshot: Dict[str, Any], diagnosis: "Diagnosis") -> str:
        """Return a generic overview response string."""
        lines = [
            "🤖 Hello! Here’s a quick overview of your device:",
            f"- CPU load: {snapshot.get('cpu_load', 'N/A'):.0f}%",
            f"- RAM usage: {snapshot.get('ram_usage', 'N/A'):.0f}%",
            f"- Storage health: {snapshot.get('storage_health', 'N/A'):.0f}%",
            f"- Battery health: {snapshot.get('battery_soh', 'N/A'):.0f}%",
            f"- Life‑Balance score: {getattr(diagnosis, 'balance_score', 'N/A'):.0f} ({getattr(diagnosis, 'severity', 'unknown')})",
        ]
        return "\n".join(lines)

    # Helper handlers (currently unused by respond but kept for future expansion)
    def _dispatch(self, query: str, snapshot: Dict[str, Any], diagnosis: "Diagnosis") -> str:
        q = query.lower()
        for kw, handler in self._handlers.items():
            if kw in q:
                return handler(snapshot, diagnosis)
        return self._general_help(snapshot, diagnosis)

    def _cpu_status(self, snapshot: Dict[str, Any], diagnosis: "Diagnosis") -> str:
        load = snapshot.get('cpu_load')
        return f"Your CPU load is currently at {load:.0f}% which is {'healthy' if load < 80 else 'high'}."

    def _ram_status(self, snapshot: Dict[str, Any], diagnosis: "Diagnosis") -> str:
        ram = snapshot.get('ram_usage')
        return f"RAM usage stands at {ram:.0f}% – {'consider closing some apps' if ram > 85 else 'all good'}."

    def _storage_status(self, snapshot: Dict[str, Any], diagnosis: "Diagnosis") -> str:
        storage = snapshot.get('storage_health')
        return f"Disk health is {storage:.0f}% – {'you have plenty of free space' if storage > 30 else 'you might want to clean up'}."

    def _battery_status(self, snapshot: Dict[str, Any], diagnosis: "Diagnosis") -> str:
        soh = snapshot.get('battery_soh')
        charge = snapshot.get('battery_charge_pct', 'N/A')
        return f"Battery SoH: {soh:.0f}%, charge level {charge:.0f}%."

    def _score_summary(self, snapshot: Dict[str, Any], diagnosis: "Diagnosis") -> str:
        score = getattr(diagnosis, 'balance_score', 'N/A')
        sev = getattr(diagnosis, 'severity', 'unknown')
        return f"Your Life‑Balance score is {score:.0f} ({sev})."

    def _break_advice(self, snapshot: Dict[str, Any], diagnosis: "Diagnosis") -> str:
        mins = snapshot.get('session_mins', 0)
        if mins >= 45:
            return "You’ve been active for a while – a short break would be beneficial."
        return "You’re still within a safe focus window. Keep it up!"

    def _general_help(self, snapshot: Dict[str, Any], diagnosis: "Diagnosis") -> str:
        return (
            "I can provide information about CPU, RAM, storage, battery, "
            "your current Life‑Balance score, or give break suggestions. "
            "Try asking something like ‘How’s my CPU?’ or ‘What’s my score?’"
        )
