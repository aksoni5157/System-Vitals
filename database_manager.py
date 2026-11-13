"""
================================================================================
 System Vitals AI — Data Layer
 File: database_manager.py
================================================================================
 Purpose:
    Owns ALL interaction with the local SQLite datastore (`vitals_ecosystem.db`).
    No other module in this codebase should touch sqlite3 directly — every
    read/write path for persisted data flows through this class so that the
    schema, connection handling, and error handling live in exactly one place.

 Design notes:
    - Uses a single long-lived connection guarded by a threading.Lock because
      the telemetry engine writes from a background thread while the GUI
      reads from the main thread. sqlite3 connections are not safe to share
      across threads without `check_same_thread=False` + external locking,
      which is exactly what we do here.
    - WAL (Write-Ahead Logging) mode is enabled so concurrent reads (GUI)
      and writes (telemetry engine) don't block each other unnecessarily.
    - All public methods are defensive: they catch sqlite3.Error, log it,
      and return a safe fallback (None / empty list / False) rather than
      letting an exception bubble up and crash the GUI thread.
================================================================================
"""

import os
import sqlite3
import logging
import threading
from datetime import datetime, timedelta
from typing import List, Tuple, Optional, Dict, Any

# --------------------------------------------------------------------------
# Module-level logger. The rest of the app can attach handlers to this;
# by default it just logs to console so nothing is silently swallowed.
# --------------------------------------------------------------------------
logger = logging.getLogger("SystemVitalsAI.Database")
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(
        logging.Formatter("[%(asctime)s] [%(levelname)s] [DB] %(message)s")
    )
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)


class DatabaseManager:
    """
    Thread-safe SQLite wrapper for System Vitals AI.

    Tables
    ------
    telemetry_logs:
        id              INTEGER PRIMARY KEY AUTOINCREMENT
        timestamp       TEXT      (ISO-8601, e.g. 2026-08-23T10:15:00)
        cpu_load        REAL      (percentage, 0-100)
        ram_usage       REAL      (percentage, 0-100)
        storage_health  REAL      (percentage estimate of drive health, 0-100)
        battery_soh     REAL      (State of Health percentage, 0-100; -1 if N/A e.g. desktop)
        session_mins    REAL      (minutes of unbroken active digital session at log time)
        balance_score   REAL      (0-100 "Life Balance Score" computed by ai_brain)

    session_logs:
        id              INTEGER PRIMARY KEY AUTOINCREMENT
        start_time      TEXT      (ISO-8601)
        end_time        TEXT      (ISO-8601, nullable while session is ongoing)
        duration_mins   REAL
        break_taken     INTEGER   (0/1 — whether the user acknowledged a break prompt)
        session_type    TEXT      (e.g. 'focus', 'idle', 'break')
    """

    def __init__(self, db_path: str = "vitals_ecosystem.db"):
        # Resolve to an absolute path next to the project root by default so
        # the DB file location is deterministic regardless of the current
        # working directory the app is launched from.
        self.db_path = os.path.abspath(db_path)
        self._lock = threading.Lock()
        self._connection: Optional[sqlite3.Connection] = None

        try:
            self._connect()
            self._initialize_schema()
            logger.info(f"Database ready at: {self.db_path}")
        except sqlite3.Error as e:
            # If the DB truly cannot be opened (e.g. permissions issue on a
            # locked-down Android node), we log loudly but do not crash the
            # constructor — calling code checks self.is_ready().
            logger.error(f"Failed to initialize database: {e}")

    # ----------------------------------------------------------------
    # Connection lifecycle
    # ----------------------------------------------------------------
    def _connect(self) -> None:
        """Open the SQLite connection with cross-platform-safe pragmas."""
        self._connection = sqlite3.connect(
            self.db_path,
            check_same_thread=False,   # we manage thread-safety manually via self._lock
            timeout=10.0,              # wait up to 10s on a locked DB before raising
        )
        self._connection.row_factory = sqlite3.Row
        cursor = self._connection.cursor()
        # WAL mode allows concurrent readers + a single writer without
        # "database is locked" errors under normal desktop/Android usage.
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA synchronous=NORMAL;")
        cursor.execute("PRAGMA foreign_keys=ON;")
        self._connection.commit()

    def is_ready(self) -> bool:
        """Quick health check used by the GUI before attempting queries."""
        return self._connection is not None

    def _initialize_schema(self) -> None:
        """Create tables/indexes if they do not already exist. Idempotent."""
        if not self._connection:
            raise sqlite3.Error("No active connection to initialize schema on.")

        with self._lock:
            cursor = self._connection.cursor()

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS telemetry_logs (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp       TEXT    NOT NULL,
                    cpu_load        REAL    NOT NULL,
                    ram_usage       REAL    NOT NULL,
                    storage_health  REAL    NOT NULL DEFAULT 100.0,
                    battery_soh     REAL    NOT NULL DEFAULT -1.0,
                    session_mins    REAL    NOT NULL DEFAULT 0.0,
                    balance_score   REAL    NOT NULL DEFAULT 100.0
                );
                """
            )

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS session_logs (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    start_time      TEXT    NOT NULL,
                    end_time        TEXT,
                    duration_mins   REAL    NOT NULL DEFAULT 0.0,
                    break_taken     INTEGER NOT NULL DEFAULT 0,
                    session_type    TEXT    NOT NULL DEFAULT 'focus'
                );
                """
            )

            # Index on timestamp dramatically speeds up the analytics range
            # queries (e.g. "last 24 hours") used by the dashboard charts.
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_telemetry_timestamp "
                "ON telemetry_logs (timestamp);"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_session_start "
                "ON session_logs (start_time);"
            )

            self._connection.commit()

    def close(self) -> None:
        """Cleanly close the connection. Call this on app shutdown."""
        with self._lock:
            if self._connection:
                try:
                    self._connection.close()
                    logger.info("Database connection closed cleanly.")
                except sqlite3.Error as e:
                    logger.error(f"Error closing database connection: {e}")
                finally:
                    self._connection = None

    # ----------------------------------------------------------------
    # WRITE METHODS
    # ----------------------------------------------------------------
    def insert_telemetry_log(
        self,
        cpu_load: float,
        ram_usage: float,
        storage_health: float,
        battery_soh: float,
        session_mins: float,
        balance_score: float,
        timestamp: Optional[str] = None,
    ) -> bool:
        """
        Insert a single telemetry snapshot row.

        Returns True on success, False on failure (never raises — callers,
        especially the background telemetry thread, should not crash the
        app because of a transient DB hiccup).
        """
        if not self._connection:
            logger.warning("insert_telemetry_log called with no active connection.")
            return False

        ts = timestamp or datetime.now().isoformat(timespec="seconds")

        try:
            with self._lock:
                cursor = self._connection.cursor()
                cursor.execute(
                    """
                    INSERT INTO telemetry_logs
                        (timestamp, cpu_load, ram_usage, storage_health,
                         battery_soh, session_mins, balance_score)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (ts, cpu_load, ram_usage, storage_health,
                     battery_soh, session_mins, balance_score),
                )
                self._connection.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"Failed to insert telemetry log: {e}")
            return False

    def start_session_log(self, session_type: str = "focus") -> Optional[int]:
        """
        Record the start of a new digital-wellbeing session.
        Returns the new row's id (used later to close it out), or None on failure.
        """
        if not self._connection:
            return None
        try:
            with self._lock:
                cursor = self._connection.cursor()
                cursor.execute(
                    """
                    INSERT INTO session_logs (start_time, duration_mins, break_taken, session_type)
                    VALUES (?, 0.0, 0, ?)
                    """,
                    (datetime.now().isoformat(timespec="seconds"), session_type),
                )
                self._connection.commit()
                return cursor.lastrowid
        except sqlite3.Error as e:
            logger.error(f"Failed to start session log: {e}")
            return None

    def end_session_log(
        self, session_id: int, duration_mins: float, break_taken: bool
    ) -> bool:
        """Close out a previously started session log with final stats."""
        if not self._connection or session_id is None:
            return False
        try:
            with self._lock:
                cursor = self._connection.cursor()
                cursor.execute(
                    """
                    UPDATE session_logs
                    SET end_time = ?, duration_mins = ?, break_taken = ?
                    WHERE id = ?
                    """,
                    (
                        datetime.now().isoformat(timespec="seconds"),
                        duration_mins,
                        1 if break_taken else 0,
                        session_id,
                    ),
                )
                self._connection.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"Failed to end session log: {e}")
            return False

    # ----------------------------------------------------------------
    # READ / ANALYTICS METHODS
    # ----------------------------------------------------------------
    def fetch_recent_telemetry(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Fetch the most recent N telemetry rows, oldest-first (good for charts)."""
        if not self._connection:
            return []
        try:
            with self._lock:
                cursor = self._connection.cursor()
                cursor.execute(
                    """
                    SELECT * FROM (
                        SELECT * FROM telemetry_logs
                        ORDER BY id DESC
                        LIMIT ?
                    ) sub
                    ORDER BY sub.id ASC
                    """,
                    (limit,),
                )
                rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except sqlite3.Error as e:
            logger.error(f"Failed to fetch recent telemetry: {e}")
            return []

    def fetch_telemetry_since(self, since_hours: float = 24.0) -> List[Dict[str, Any]]:
        """Fetch all telemetry rows newer than `since_hours` ago."""
        if not self._connection:
            return []
        cutoff = (datetime.now() - timedelta(hours=since_hours)).isoformat(timespec="seconds")
        try:
            with self._lock:
                cursor = self._connection.cursor()
                cursor.execute(
                    """
                    SELECT * FROM telemetry_logs
                    WHERE timestamp >= ?
                    ORDER BY timestamp ASC
                    """,
                    (cutoff,),
                )
                rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except sqlite3.Error as e:
            logger.error(f"Failed to fetch telemetry since {since_hours}h: {e}")
            return []

    def fetch_average_balance_score(self, since_hours: float = 24.0) -> float:
        """Convenience aggregate: mean Life Balance Score over a time window."""
        if not self._connection:
            return 0.0
        cutoff = (datetime.now() - timedelta(hours=since_hours)).isoformat(timespec="seconds")
        try:
            with self._lock:
                cursor = self._connection.cursor()
                cursor.execute(
                    """
                    SELECT AVG(balance_score) as avg_score
                    FROM telemetry_logs
                    WHERE timestamp >= ?
                      AND balance_score >= 0
                    """,
                    (cutoff,),
                )
                result = cursor.fetchone()
            if result and result["avg_score"] is not None:
                return round(float(result["avg_score"]), 2)
            return 0.0
        except sqlite3.Error as e:
            logger.error(f"Failed to compute average balance score: {e}")
            return 0.0

    def fetch_session_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Fetch the most recent session logs, newest-first."""
        if not self._connection:
            return []
        try:
            with self._lock:
                cursor = self._connection.cursor()
                cursor.execute(
                    """
                    SELECT * FROM session_logs
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (limit,),
                )
                rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except sqlite3.Error as e:
            logger.error(f"Failed to fetch session history: {e}")
            return []

    def fetch_full_analytics_export(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Bundles all telemetry + session history for the
        'Export Ecosystem Analytics Report' feature in app.py.
        """
        return {
            "telemetry_logs": self.fetch_telemetry_since(since_hours=24 * 30),  # last 30 days
            "session_logs": self.fetch_session_history(limit=1000),
        }

    def purge_old_logs(self, older_than_days: int = 90) -> bool:
        """
        Housekeeping method: deletes telemetry rows older than N days so the
        local DB doesn't grow unbounded on long-running installs. Not called
        automatically — expose this later via a settings/maintenance panel.
        """
        if not self._connection:
            return False
        cutoff = (datetime.now() - timedelta(days=older_than_days)).isoformat(timespec="seconds")
        try:
            with self._lock:
                cursor = self._connection.cursor()
                cursor.execute(
                    "DELETE FROM telemetry_logs WHERE timestamp < ?", (cutoff,)
                )
                self._connection.commit()
            logger.info(f"Purged telemetry logs older than {older_than_days} days.")
            return True
        except sqlite3.Error as e:
            logger.error(f"Failed to purge old logs: {e}")
            return False


# ------------------------------------------------------------------------
# Manual smoke test — run `python database_manager.py` directly to
# sanity-check schema creation + a round-trip insert/fetch without needing
# the full GUI or telemetry engine running.
# ------------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    db = DatabaseManager("vitals_ecosystem_test.db")
    ok = db.insert_telemetry_log(
        cpu_load=42.5, ram_usage=61.2, storage_health=97.0,
        battery_soh=88.0, session_mins=35.0, balance_score=76.0,
    )
    print("Insert successful:", ok)
    print("Recent rows:", db.fetch_recent_telemetry(limit=5))
    db.close()
