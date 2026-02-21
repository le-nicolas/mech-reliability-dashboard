from __future__ import annotations

import os
import sys
from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def resource_path(*parts: str) -> Path:
    """
    Resolve paths both from source and from PyInstaller bundles.
    """
    if hasattr(sys, "_MEIPASS"):
        base = Path(getattr(sys, "_MEIPASS"))
    else:
        base = project_root()
    return base.joinpath(*parts)


def app_data_dir() -> Path:
    """
    Writable application-data directory for persisted records/models.
    """
    local_app_data = os.getenv("LOCALAPPDATA")
    if local_app_data:
        base = Path(local_app_data)
    else:
        base = project_root() / ".app_data"
    target = base / "MechReliabilityDashboard"
    target.mkdir(parents=True, exist_ok=True)
    return target


def sqlite_db_path() -> Path:
    db = app_data_dir() / "reliability.sqlite"
    db.parent.mkdir(parents=True, exist_ok=True)
    return db


def model_store_dir() -> Path:
    models = app_data_dir() / "models"
    models.mkdir(parents=True, exist_ok=True)
    return models
