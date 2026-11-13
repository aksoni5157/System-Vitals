"""Lightweight system cleanup and process-priority controls."""

import os
import tempfile
import time
from pathlib import Path

try:
    import psutil
except ImportError as exc:
    raise ImportError("Cooling mode requires psutil. Install it with: pip install psutil") from exc


class TempFileCleaner:
    """Scan and remove files from the current user's OS temp directory."""

    def __init__(self):
        self.root = Path(tempfile.gettempdir()).resolve()
        self._lifetime_bytes_freed = 0

    def _files(self):
        """Yield regular files without following directory symlinks."""
        if not self.root.is_dir():
            return
        for current, dirs, names in os.walk(self.root, topdown=True, followlinks=False):
            dirs[:] = [name for name in dirs
                       if not (Path(current) / name).is_symlink()]
            for name in names:
                path = Path(current) / name
                try:
                    if path.is_file() and not path.is_symlink():
                        yield path
                except OSError:
                    continue

    def scan_temp_files(self):
        count = 0
        size = 0
        for path in self._files():
            try:
                size += path.stat().st_size
                count += 1
            except OSError:
                continue
        return {"temp_files_found": count, "total_size_mb": size / (1024 * 1024)}

    def purge_temp_files(self):
        started = time.perf_counter()
        deleted = 0
        freed = 0
        for path in self._files():
            try:
                size = path.stat().st_size
                path.unlink()
                deleted += 1
                freed += size
            except OSError:
                # Windows commonly keeps active temporary files locked.
                continue
        # Remove empty directories only; never remove the temp root itself.
        for current, dirs, _names in os.walk(self.root, topdown=False, followlinks=False):
            for name in dirs:
                folder = Path(current) / name
                if folder.is_symlink():
                    continue
                try:
                    folder.rmdir()
                except OSError:
                    pass
        self._lifetime_bytes_freed += freed
        return {
            "files_deleted": deleted,
            "bytes_freed": freed,
            "mb_freed": freed / (1024 * 1024),
            "duration_sec": time.perf_counter() - started,
            "total_lifetime_cleaned_mb": self._lifetime_bytes_freed / (1024 * 1024),
        }


class CoolingController:
    """Reduce this app's scheduling priority, then restore it when disabled."""

    def __init__(self):
        self._process = psutil.Process()
        self._original_priority = None
        self.is_active = False

    def activate(self):
        if self.is_active:
            return {"processes_throttled": 1}
        self._original_priority = self._process.nice()
        try:
            lower_priority = (psutil.BELOW_NORMAL_PRIORITY_CLASS
                              if hasattr(psutil, "BELOW_NORMAL_PRIORITY_CLASS") else 10)
            self._process.nice(lower_priority)
            self.is_active = True
            return {"processes_throttled": 1}
        except Exception:
            self._original_priority = None
            raise

    def deactivate(self):
        if not self.is_active:
            return {"processes_restored": 0}
        try:
            self._process.nice(self._original_priority)
            self.is_active = False
            self._original_priority = None
            return {"processes_restored": 1}
        except Exception:
            # Keep the active state if the OS could not restore the priority.
            raise


class OptimizerEngine:
    """Expose the cooling controller through the existing dashboard API."""

    def __init__(self, db_manager=None):
        self.db_manager = db_manager
        self.cooling = CoolingController()
        self.cleaner = TempFileCleaner()

    def get_status(self):
        return {"cooling_active": self.cooling.is_active}
