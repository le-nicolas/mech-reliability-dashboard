from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.analytics import run_analysis


def test_run_analysis_smoke() -> None:
    root = Path(__file__).resolve().parents[1]
    data_path = root / "sample_data" / "maintenance_log.csv"
    raw = pd.read_csv(data_path)

    result = run_analysis(raw)

    assert len(result.cleaned) > 0
    assert result.overview["total_failures"] == 40
    assert result.overview["total_downtime_hours"] > 0
    assert not result.asset_risk.empty
    assert not result.failure_modes.empty
    assert not result.factor_importance.empty


def test_asset_risk_sorted_desc() -> None:
    root = Path(__file__).resolve().parents[1]
    raw = pd.read_csv(root / "sample_data" / "maintenance_log.csv")
    risk = run_analysis(raw).asset_risk["risk_score"].tolist()
    assert risk == sorted(risk, reverse=True)

