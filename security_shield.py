"""Run an on-demand Microsoft Defender quick scan on Windows."""

import os
import subprocess
import time
from pathlib import Path


class SecurityShield:
    """Thin, read-only scan integration with the antivirus already on Windows."""

    def __init__(self, db_manager=None):
        self.db_manager = db_manager
        self._last_scan = None

    @staticmethod
    def _defender_cli():
        if os.name != "nt":
            return None
        roots = []
        program_data = os.environ.get("ProgramData")
        if program_data:
            roots.extend((Path(program_data) / "Microsoft/Windows Defender/Platform").glob("*/MpCmdRun.exe"))
        program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
        roots.append(Path(program_files) / "Windows Defender/MpCmdRun.exe")
        existing = [path for path in roots if path.is_file()]
        return max(existing, key=lambda path: path.stat().st_mtime) if existing else None

    def is_available(self):
        return self._defender_cli() is not None

    def run_quick_scan(self):
        """Run Defender's built-in quick scan; this call may take several minutes."""
        cli = self._defender_cli()
        if cli is None:
            raise RuntimeError("Microsoft Defender's scan tool was not found on this Windows system.")

        started = time.monotonic()
        result = subprocess.run(
            [str(cli), "-Scan", "-ScanType", "1"],
            capture_output=True,
            text=True,
            timeout=60 * 60,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        duration = time.monotonic() - started
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "Defender returned an error.").strip()
            raise RuntimeError(detail)

        self._last_scan = {
            "status": "completed",
            "duration_sec": duration,
            "message": "Microsoft Defender quick scan completed. Review Windows Security protection history for findings.",
        }
        return dict(self._last_scan)

    def get_status_summary(self):
        if self._last_scan:
            return {"available": True, **self._last_scan}
        return {
            "available": self.is_available(),
            "status": "ready" if self.is_available() else "unavailable",
            "message": "Microsoft Defender quick scan is ready." if self.is_available() else "Microsoft Defender scan tool was not found.",
        }
