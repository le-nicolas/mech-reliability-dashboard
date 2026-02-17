from __future__ import annotations

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

