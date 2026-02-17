from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

# Alternate input names mapped to canonical fields.
CANONICAL_MAP = {
    "date": "event_date",
    "event_date": "event_date",
    "timestamp": "event_date",
    "asset": "asset_id",
    "asset_id": "asset_id",
    "asset_name": "asset_id",
    "equipment_id": "asset_id",
    "equipment": "asset_id",
    "asset_type": "asset_type",
    "equipment_type": "asset_type",
    "failure_mode": "failure_mode",
    "failure": "failure_mode",
    "failure_code": "failure_mode",
    "downtime": "downtime_hours",
    "downtime_hour": "downtime_hours",
    "downtime_hours": "downtime_hours",
    "repair_time": "repair_hours",
    "repair_hours": "repair_hours",
    "mttr_hours": "repair_hours",
    "operating_hours": "operating_hours",
    "runtime_hours": "operating_hours",
    "vibration": "vibration_mm_s",
    "vibration_mm_s": "vibration_mm_s",
    "temperature": "temperature_c",
    "temperature_c": "temperature_c",
    "load": "load_pct",
    "load_pct": "load_pct",
    "lubrication_gap_days": "lubrication_gap_days",
    "lube_gap_days": "lubrication_gap_days",
    "alignment_error_mm": "alignment_error_mm",
    "alignment_mm": "alignment_error_mm",
}

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

BASE_REQUIRED = {"asset_id", "failure_mode", "downtime_hours", "repair_hours"}

RISK_FACTOR_COLUMNS = [
    "vibration_mm_s",
    "temperature_c",
    "load_pct",
    "lubrication_gap_days",
    "alignment_error_mm",
]


@dataclass
class AnalysisResults:
    cleaned: pd.DataFrame
    overview: dict[str, float]
    asset_risk: pd.DataFrame
    failure_modes: pd.DataFrame
    factor_importance: pd.DataFrame


def _sanitize_col(name: str) -> str:
    key = name.strip().lower().replace(" ", "_").replace("-", "_")
    return CANONICAL_MAP.get(key, key)


def _minmax(series: pd.Series) -> pd.Series:
    if series.empty:
        return series
    min_val = float(series.min())
    max_val = float(series.max())
    if max_val - min_val == 0:
        return pd.Series(np.zeros(len(series)), index=series.index, dtype=float)
    return (series - min_val) / (max_val - min_val)


def standardize_dataframe(raw_df: pd.DataFrame) -> pd.DataFrame:
    df = raw_df.copy()
    df.columns = [_sanitize_col(c) for c in df.columns]

    if "asset_type" not in df.columns:
        df["asset_type"] = "Unknown"
    if "event_date" not in df.columns:
        df["event_date"] = pd.NaT

    for col in NUMERIC_COLUMNS:
        if col not in df.columns:
            df[col] = 0.0

    for col in ("asset_id", "asset_type", "failure_mode"):
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].astype(str).str.strip()

    df["event_date"] = pd.to_datetime(df["event_date"], errors="coerce")

    for col in NUMERIC_COLUMNS:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    missing = BASE_REQUIRED - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    df = df[(df["asset_id"] != "") & (df["failure_mode"] != "")]
    df = df[df["downtime_hours"] >= 0]
    df = df[df["repair_hours"] >= 0]
    df = df.reset_index(drop=True)
    return df


def compute_overview(df: pd.DataFrame) -> dict[str, float]:
    failures = float(len(df))
    downtime = float(df["downtime_hours"].sum())
    repair = float(df["repair_hours"].sum())
    operating = float(df["operating_hours"].sum())

    mttr = repair / failures if failures else 0.0
    mtbf = operating / failures if failures else 0.0
    availability = operating / (operating + downtime) if (operating + downtime) else 0.0

    return {
        "total_failures": failures,
        "total_downtime_hours": downtime,
        "total_operating_hours": operating,
        "mttr_hours": mttr,
        "mtbf_hours": mtbf,
        "availability_pct": availability * 100.0,
    }


def compute_asset_risk(df: pd.DataFrame) -> pd.DataFrame:
    grouped = (
        df.groupby("asset_id", as_index=False)
        .agg(
            asset_type=("asset_type", lambda s: s.mode().iat[0] if not s.mode().empty else "Unknown"),
            failures=("failure_mode", "size"),
            downtime_hours=("downtime_hours", "sum"),
            avg_repair_hours=("repair_hours", "mean"),
            operating_hours=("operating_hours", "sum"),
            vibration_mm_s=("vibration_mm_s", "mean"),
            temperature_c=("temperature_c", "mean"),
            load_pct=("load_pct", "mean"),
            lubrication_gap_days=("lubrication_gap_days", "mean"),
            alignment_error_mm=("alignment_error_mm", "mean"),
        )
        .fillna(0.0)
    )

    grouped["mtbf_hours"] = grouped.apply(
        lambda r: r["operating_hours"] / r["failures"] if r["failures"] else 0.0,
        axis=1,
    )
    grouped["mttr_hours"] = grouped["avg_repair_hours"]

    risk = (
        0.35 * _minmax(grouped["failures"])
        + 0.25 * _minmax(grouped["downtime_hours"])
        + 0.15 * _minmax(grouped["vibration_mm_s"])
        + 0.10 * _minmax(grouped["temperature_c"])
        + 0.10 * _minmax(grouped["lubrication_gap_days"])
        + 0.05 * _minmax(grouped["alignment_error_mm"])
    )
    grouped["risk_score"] = (risk * 100.0).round(1)

    grouped = grouped.sort_values("risk_score", ascending=False).reset_index(drop=True)
    return grouped


def compute_failure_modes(df: pd.DataFrame) -> pd.DataFrame:
    failure_modes = (
        df.groupby("failure_mode", as_index=False)
        .agg(
            failures=("asset_id", "size"),
            downtime_hours=("downtime_hours", "sum"),
        )
        .sort_values(["failures", "downtime_hours"], ascending=False)
        .reset_index(drop=True)
    )
    return failure_modes


def compute_factor_importance(asset_risk: pd.DataFrame) -> pd.DataFrame:
    if asset_risk.empty:
        return pd.DataFrame(columns=["factor", "high_risk_mean", "low_risk_mean", "lift", "importance"])

    threshold = asset_risk["risk_score"].quantile(0.75)
    high = asset_risk[asset_risk["risk_score"] >= threshold]
    low = asset_risk[asset_risk["risk_score"] < threshold]
    if low.empty:
        low = asset_risk.copy()

    rows: list[dict[str, float | str]] = []
    for col in RISK_FACTOR_COLUMNS:
        high_mean = float(high[col].mean())
        low_mean = float(low[col].mean())
        lift = high_mean - low_mean
        denom = float(asset_risk[col].std()) if float(asset_risk[col].std()) > 0 else 1.0
        importance = abs(lift / denom)
        rows.append(
            {
                "factor": col,
                "high_risk_mean": high_mean,
                "low_risk_mean": low_mean,
                "lift": lift,
                "importance": importance,
            }
        )

    factors = pd.DataFrame(rows).sort_values("importance", ascending=False).reset_index(drop=True)
    return factors


def run_analysis(raw_df: pd.DataFrame) -> AnalysisResults:
    cleaned = standardize_dataframe(raw_df)
    if cleaned.empty:
        raise ValueError("No valid rows after cleaning. Check your CSV content.")

    overview = compute_overview(cleaned)
    asset_risk = compute_asset_risk(cleaned)
    failure_modes = compute_failure_modes(cleaned)
    factor_importance = compute_factor_importance(asset_risk)
    return AnalysisResults(
        cleaned=cleaned,
        overview=overview,
        asset_risk=asset_risk,
        failure_modes=failure_modes,
        factor_importance=factor_importance,
    )

