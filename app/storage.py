from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

from app.io_utils import sqlite_db_path

DB_COLUMNS = [
    "event_date",
    "asset_id",
    "asset_type",
    "line",
    "shift",
    "failure_mode",
    "downtime_hours",
    "repair_hours",
    "operating_hours",
    "vibration_mm_s",
    "temperature_c",
    "load_pct",
    "lubrication_gap_days",
    "alignment_error_mm",
    "source_name",
    "imported_at",
]

NUMERIC_COLUMNS = [
    "downtime_hours",
    "repair_hours",
    "operating_hours",
    "vibration_mm_s",
    "temperature_c",
    "load_pct",
    "lubrication_gap_days",
    "alignment_error_mm",
]


class ReliabilityStore:
    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or sqlite_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _initialize(self) -> None:
        ddl = """
        CREATE TABLE IF NOT EXISTS maintenance_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_date TEXT,
            asset_id TEXT NOT NULL,
            asset_type TEXT,
            line TEXT,
            shift TEXT,
            failure_mode TEXT NOT NULL,
            downtime_hours REAL,
            repair_hours REAL,
            operating_hours REAL,
            vibration_mm_s REAL,
            temperature_c REAL,
            load_pct REAL,
            lubrication_gap_days REAL,
            alignment_error_mm REAL,
            source_name TEXT,
            imported_at TEXT
        );
        """
        with self._connect() as conn:
            conn.execute(ddl)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_maintenance_asset_date "
                "ON maintenance_records(asset_id, event_date);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_maintenance_imported_at "
                "ON maintenance_records(imported_at);"
            )

    def append_records(self, cleaned_df: pd.DataFrame, source_name: str = "") -> int:
        if cleaned_df.empty:
            return 0

        frame = cleaned_df.copy()
        for column in DB_COLUMNS:
            if column not in frame.columns:
                frame[column] = "" if column in ("asset_id", "asset_type", "line", "shift", "failure_mode") else 0.0

        frame["event_date"] = pd.to_datetime(frame["event_date"], errors="coerce").dt.strftime("%Y-%m-%d")
        frame["source_name"] = source_name
        frame["imported_at"] = pd.Timestamp.utcnow().isoformat()

        for column in NUMERIC_COLUMNS:
            frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0.0)

        with self._connect() as conn:
            frame[DB_COLUMNS].to_sql("maintenance_records", conn, if_exists="append", index=False)
        return int(len(frame))

    def load_records(self) -> pd.DataFrame:
        query = f"SELECT {', '.join(DB_COLUMNS)} FROM maintenance_records ORDER BY id ASC"
        with self._connect() as conn:
            frame = pd.read_sql_query(query, conn)
        if frame.empty:
            return frame

        frame["event_date"] = pd.to_datetime(frame["event_date"], errors="coerce")
        for column in NUMERIC_COLUMNS:
            frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0.0)
        for column in ("asset_id", "asset_type", "line", "shift", "failure_mode", "source_name"):
            frame[column] = frame[column].astype(str).str.strip()
        return frame
