from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from app.io_utils import model_store_dir

try:  # pragma: no cover - optional runtime dependency import boundary
    import joblib
except Exception:  # pragma: no cover - optional runtime dependency import boundary
    joblib = None

try:  # pragma: no cover - optional runtime dependency import boundary
    from sklearn.ensemble import IsolationForest
except Exception:  # pragma: no cover - optional runtime dependency import boundary
    IsolationForest = None

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
    "line": "line",
    "line_id": "line",
    "production_line": "line",
    "productionline": "line",
    "shift": "shift",
    "work_shift": "shift",
    "crew_shift": "shift",
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

SENSOR_COLUMNS = [
    "vibration_mm_s",
    "temperature_c",
    "load_pct",
    "lubrication_gap_days",
    "alignment_error_mm",
]

RISK_POINT_WEIGHTS = {
    "points_failures": 20.0,
    "points_downtime": 30.0,
    "points_failure_mode": 25.0,
    "points_vibration": 17.0,
    "points_temperature": 4.0,
    "points_alignment": 4.0,
}

RISK_POINT_LABELS = {
    "points_failures": "Frequent failures",
    "points_downtime": "High downtime",
    "points_failure_mode": "Frequent failure mode",
    "points_vibration": "Elevated vibration",
    "points_temperature": "Elevated temperature",
    "points_alignment": "Misalignment",
}

FORECAST_COLUMNS = [
    "asset_id",
    "asset_type",
    "predicted_failure_days",
    "trigger",
    "suggested_action",
    "anomaly_score",
    "at_risk",
]


@dataclass
class AnalysisResults:
    cleaned: pd.DataFrame
    overview: dict[str, float]
    asset_risk: pd.DataFrame
    failure_modes: pd.DataFrame
    factor_importance: pd.DataFrame
    rolling_metrics: pd.DataFrame
    trend_summary: pd.DataFrame
    forecast_alerts: pd.DataFrame


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
    if "line" not in df.columns:
        df["line"] = "Unknown"
    if "shift" not in df.columns:
        df["shift"] = "Unknown"

    for col in NUMERIC_COLUMNS:
        if col not in df.columns:
            df[col] = 0.0

    for col in ("asset_id", "asset_type", "failure_mode", "line", "shift"):
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


def _build_risk_explanation(row: pd.Series) -> str:
    score = float(row.get("risk_score", 0.0))
    components = [
        (label, float(row.get(col, 0.0)))
        for col, label in RISK_POINT_LABELS.items()
    ]
    components = sorted(components, key=lambda item: item[1], reverse=True)
    parts = [f"{label} ({points:.0f}pts)" for label, points in components if points > 0][:3]
    if not parts:
        parts = ["No elevated factors (0pts)"]
    return f"Score = {score:.0f} because: " + " + ".join(parts)


def _dominant_failure_mode(df: pd.DataFrame) -> pd.DataFrame:
    counts = (
        df.groupby(["asset_id", "failure_mode"], as_index=False)
        .size()
        .rename(columns={"size": "mode_failures"})
    )
    if counts.empty:
        return pd.DataFrame(
            columns=[
                "asset_id",
                "dominant_failure_mode",
                "dominant_failure_count",
                "dominant_failure_share",
            ]
        )

    counts = counts.sort_values(
        ["asset_id", "mode_failures", "failure_mode"],
        ascending=[True, False, True],
    )
    dominant = counts.groupby("asset_id", as_index=False).first()
    totals = counts.groupby("asset_id", as_index=False)["mode_failures"].sum().rename(
        columns={"mode_failures": "total_failures"}
    )
    dominant = dominant.merge(totals, on="asset_id", how="left")
    dominant["dominant_failure_share"] = dominant.apply(
        lambda r: float(r["mode_failures"]) / float(r["total_failures"]) if r["total_failures"] else 0.0,
        axis=1,
    )
    dominant = dominant.rename(
        columns={
            "failure_mode": "dominant_failure_mode",
            "mode_failures": "dominant_failure_count",
        }
    )
    return dominant[
        ["asset_id", "dominant_failure_mode", "dominant_failure_count", "dominant_failure_share"]
    ]


def compute_asset_risk(df: pd.DataFrame) -> pd.DataFrame:
    grouped = (
        df.groupby("asset_id", as_index=False)
        .agg(
            asset_type=("asset_type", lambda s: s.mode().iat[0] if not s.mode().empty else "Unknown"),
            line=("line", lambda s: s.mode().iat[0] if not s.mode().empty else "Unknown"),
            shift=("shift", lambda s: s.mode().iat[0] if not s.mode().empty else "Unknown"),
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
    grouped = grouped.merge(_dominant_failure_mode(df), on="asset_id", how="left")
    grouped["dominant_failure_mode"] = grouped["dominant_failure_mode"].fillna("Unknown")
    grouped["dominant_failure_share"] = grouped["dominant_failure_share"].fillna(0.0)

    grouped["mtbf_hours"] = grouped.apply(
        lambda r: r["operating_hours"] / r["failures"] if r["failures"] else 0.0,
        axis=1,
    )
    grouped["mttr_hours"] = grouped["avg_repair_hours"]

    grouped["points_failures"] = RISK_POINT_WEIGHTS["points_failures"] * _minmax(grouped["failures"])
    grouped["points_downtime"] = RISK_POINT_WEIGHTS["points_downtime"] * _minmax(grouped["downtime_hours"])
    grouped["points_failure_mode"] = RISK_POINT_WEIGHTS["points_failure_mode"] * _minmax(
        grouped["dominant_failure_share"]
    )
    grouped["points_vibration"] = RISK_POINT_WEIGHTS["points_vibration"] * _minmax(grouped["vibration_mm_s"])
    grouped["points_temperature"] = RISK_POINT_WEIGHTS["points_temperature"] * _minmax(grouped["temperature_c"])
    grouped["points_alignment"] = RISK_POINT_WEIGHTS["points_alignment"] * _minmax(
        grouped["alignment_error_mm"]
    )
    risk_columns = list(RISK_POINT_WEIGHTS.keys())
    grouped["risk_score"] = grouped[risk_columns].sum(axis=1).round(1)
    grouped["risk_explanation"] = grouped.apply(_build_risk_explanation, axis=1)

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


def compute_rolling_mtbf_mttr(df: pd.DataFrame, windows: tuple[int, int] = (30, 90)) -> pd.DataFrame:
    columns = ["asset_id", "asset_type", "event_date"]
    for window in windows:
        columns.extend([f"failures_{window}d", f"mtbf_{window}d", f"mttr_{window}d"])

    if df.empty or df["event_date"].dropna().empty:
        return pd.DataFrame(columns=columns)

    dated = df.dropna(subset=["event_date"]).sort_values(["asset_id", "event_date"]).reset_index(drop=True)
    rows: list[dict[str, float | str | pd.Timestamp]] = []
    for asset_id, asset_frame in dated.groupby("asset_id", sort=False):
        asset_frame = asset_frame.sort_values("event_date").reset_index(drop=True)
        asset_type = (
            asset_frame["asset_type"].mode().iat[0]
            if not asset_frame["asset_type"].mode().empty
            else "Unknown"
        )
        for _, row in asset_frame.iterrows():
            current_date = row["event_date"]
            metrics: dict[str, float | str | pd.Timestamp] = {
                "asset_id": asset_id,
                "asset_type": asset_type,
                "event_date": current_date,
            }
            for window in windows:
                start = current_date - pd.Timedelta(days=window - 1)
                window_frame = asset_frame[
                    (asset_frame["event_date"] >= start) & (asset_frame["event_date"] <= current_date)
                ]
                failures = float(len(window_frame))
                operating = float(window_frame["operating_hours"].sum())
                repair = float(window_frame["repair_hours"].sum())
                metrics[f"failures_{window}d"] = failures
                metrics[f"mtbf_{window}d"] = operating / failures if failures else 0.0
                metrics[f"mttr_{window}d"] = repair / failures if failures else 0.0
            rows.append(metrics)

    if not rows:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(rows).sort_values(["asset_id", "event_date"]).reset_index(drop=True)


def _fit_slope(dates: pd.Series, values: pd.Series) -> float:
    valid = (~dates.isna()) & (~values.isna())
    if int(valid.sum()) < 3:
        return 0.0
    x = (dates[valid] - dates[valid].min()).dt.days.to_numpy(dtype=float)
    y = values[valid].to_numpy(dtype=float)
    if len(np.unique(x)) < 2:
        return 0.0
    return float(np.polyfit(x, y, deg=1)[0])


def compute_trend_summary(rolling_metrics: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "asset_id",
        "asset_type",
        "latest_mtbf_30d",
        "latest_mttr_30d",
        "latest_mtbf_90d",
        "latest_mttr_90d",
        "mtbf_slope_30d",
        "mttr_slope_30d",
        "mtbf_trend",
        "trend_note",
    ]
    if rolling_metrics.empty:
        return pd.DataFrame(columns=columns)

    rows: list[dict[str, float | str]] = []
    for asset_id, asset_frame in rolling_metrics.groupby("asset_id", sort=False):
        asset_frame = asset_frame.sort_values("event_date").reset_index(drop=True)
        asset_type = (
            asset_frame["asset_type"].mode().iat[0]
            if not asset_frame["asset_type"].mode().empty
            else "Unknown"
        )
        latest = asset_frame.iloc[-1]
        recent = asset_frame
        if pd.notna(latest["event_date"]):
            start = latest["event_date"] - pd.Timedelta(days=90)
            recent = asset_frame[asset_frame["event_date"] >= start]
            if recent.empty:
                recent = asset_frame.tail(min(len(asset_frame), 5))

        mtbf_slope = _fit_slope(recent["event_date"], recent["mtbf_30d"])
        mttr_slope = _fit_slope(recent["event_date"], recent["mttr_30d"])
        if mtbf_slope < -0.05:
            mtbf_trend = "Shrinking"
        elif mtbf_slope > 0.05:
            mtbf_trend = "Improving"
        else:
            mtbf_trend = "Stable"

        period_days = 0
        if pd.notna(recent["event_date"].min()) and pd.notna(recent["event_date"].max()):
            period_days = int((recent["event_date"].max() - recent["event_date"].min()).days)
        period_months = max(1, int(np.ceil(period_days / 30.0))) if period_days > 0 else 1
        if mtbf_trend == "Shrinking":
            trend_note = (
                f"{asset_id}'s MTBF has been shrinking for about {period_months} month(s), "
                "trending toward failure."
            )
        elif mtbf_trend == "Improving":
            trend_note = f"{asset_id}'s MTBF is improving over the recent operating window."
        else:
            trend_note = f"{asset_id}'s MTBF is currently stable."

        rows.append(
            {
                "asset_id": asset_id,
                "asset_type": asset_type,
                "latest_mtbf_30d": float(latest.get("mtbf_30d", 0.0)),
                "latest_mttr_30d": float(latest.get("mttr_30d", 0.0)),
                "latest_mtbf_90d": float(latest.get("mtbf_90d", 0.0)),
                "latest_mttr_90d": float(latest.get("mttr_90d", 0.0)),
                "mtbf_slope_30d": mtbf_slope,
                "mttr_slope_30d": mttr_slope,
                "mtbf_trend": mtbf_trend,
                "trend_note": trend_note,
            }
        )

    if not rows:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(rows).sort_values("mtbf_slope_30d").reset_index(drop=True)


def _safe_asset_filename(asset_id: str) -> str:
    chars = [c if c.isalnum() or c in ("-", "_") else "_" for c in asset_id]
    return "".join(chars).strip("_") or "asset"


def _recent_percent_change(series: pd.Series, window: int = 3) -> float:
    values = pd.to_numeric(series, errors="coerce").dropna()
    if len(values) < window * 2:
        return 0.0
    recent = float(values.tail(window).mean())
    previous = float(values.iloc[-(window * 2) : -window].mean())
    if previous == 0:
        return 0.0
    return ((recent - previous) / abs(previous)) * 100.0


def _estimate_days_to_failure(
    asset_frame: pd.DataFrame,
    reference_date: pd.Timestamp,
    is_anomaly: bool,
    vibration_change_pct: float,
) -> float:
    dated = asset_frame.dropna(subset=["event_date"]).sort_values("event_date")
    if len(dated) >= 2:
        intervals = dated["event_date"].diff().dt.days.dropna()
        baseline_interval = float(intervals.median()) if not intervals.empty else 30.0
    else:
        baseline_interval = 30.0

    downtime = pd.to_numeric(asset_frame["downtime_hours"], errors="coerce").fillna(0.0)
    if len(downtime) >= 3:
        x = np.arange(len(downtime), dtype=float)
        slope = float(np.polyfit(x, downtime.to_numpy(dtype=float), deg=1)[0])
        degradation = max(0.0, slope / (float(downtime.mean()) + 1e-6))
    else:
        degradation = 0.0

    penalty = degradation
    if is_anomaly:
        penalty += 0.35
    if vibration_change_pct > 0:
        penalty += min(0.60, vibration_change_pct / 100.0)

    adjusted_interval = baseline_interval / (1.0 + penalty)
    if dated.empty:
        return max(1.0, adjusted_interval)

    days_since_last = float((reference_date - dated["event_date"].max()).days)
    remaining = adjusted_interval - days_since_last
    return max(1.0, remaining)


def _suggest_action(failure_mode: str) -> str:
    text = str(failure_mode).lower()
    if "bearing" in text:
        return "Bearing inspection"
    if "seal" in text:
        return "Seal integrity check"
    if "valve" in text:
        return "Valve clearance verification"
    if "cavitation" in text:
        return "Suction line and NPSH check"
    if "alignment" in text:
        return "Shaft alignment correction"
    if "overheat" in text or "temperature" in text:
        return "Cooling system and load review"
    if "overload" in text:
        return "Load balancing and trip setting review"
    return "Targeted reliability inspection"


def _fit_or_load_isolation_forest(
    asset_id: str,
    features: pd.DataFrame,
    models_path: Path,
    min_rows: int = 5,
) -> IsolationForest | None:
    model_file = models_path / f"{_safe_asset_filename(asset_id)}.joblib"

    if IsolationForest is not None and len(features) >= min_rows:
        model = IsolationForest(
            n_estimators=140,
            contamination=0.15,
            random_state=42,
        )
        model.fit(features)
        if joblib is not None:
            try:  # pragma: no cover - filesystem boundary
                joblib.dump(model, model_file)
            except Exception:
                pass
        return model

    if joblib is not None and model_file.exists():
        try:  # pragma: no cover - filesystem boundary
            loaded = joblib.load(model_file)
            return loaded if isinstance(loaded, IsolationForest) else None
        except Exception:
            return None
    return None


def compute_health_forecast(df: pd.DataFrame, models_path: Path | None = None) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=FORECAST_COLUMNS)

    if models_path is None:
        models_path = model_store_dir()
    models_path.mkdir(parents=True, exist_ok=True)

    dated = df.copy()
    reference_date = pd.Timestamp.utcnow().normalize()
    if dated["event_date"].notna().any():
        reference_date = dated["event_date"].dropna().max()

    rows: list[dict[str, float | str | bool]] = []
    for asset_id, asset_frame in dated.groupby("asset_id", sort=False):
        asset_frame = asset_frame.sort_values("event_date").reset_index(drop=True)
        asset_type = (
            asset_frame["asset_type"].mode().iat[0]
            if not asset_frame["asset_type"].mode().empty
            else "Unknown"
        )
        dominant_mode = (
            asset_frame["failure_mode"].mode().iat[0]
            if not asset_frame["failure_mode"].mode().empty
            else "Unknown"
        )

        features = asset_frame[SENSOR_COLUMNS].copy()
        for col in SENSOR_COLUMNS:
            features[col] = pd.to_numeric(features[col], errors="coerce").fillna(0.0)

        model = _fit_or_load_isolation_forest(asset_id, features, models_path)

        anomaly_score = 0.0
        is_anomaly = False
        if model is not None and not features.empty:
            scores = model.decision_function(features)
            anomaly_score = float(scores[-1])
            threshold = float(np.quantile(scores, 0.15))
            is_anomaly = anomaly_score < threshold
        elif not features.empty:
            centered = (features.tail(1) - features.mean()) / features.std(ddof=0).replace(0.0, 1.0)
            z_sum = float(centered.abs().sum(axis=1).iloc[0])
            anomaly_score = -z_sum
            is_anomaly = z_sum >= 6.0

        vibration_change_pct = _recent_percent_change(asset_frame["vibration_mm_s"], window=3)
        temperature_change_pct = _recent_percent_change(asset_frame["temperature_c"], window=3)
        predicted_days = _estimate_days_to_failure(
            asset_frame,
            reference_date=reference_date,
            is_anomaly=is_anomaly,
            vibration_change_pct=vibration_change_pct,
        )

        trigger_parts: list[str] = []
        if vibration_change_pct >= 15.0:
            trigger_parts.append(f"vibration trending +{vibration_change_pct:.0f}% over 3 weeks")
        if temperature_change_pct >= 10.0:
            trigger_parts.append(f"temperature trending +{temperature_change_pct:.0f}% over 3 weeks")
        if is_anomaly:
            trigger_parts.append("sensor envelope anomaly")
        if not trigger_parts:
            trigger_parts.append("downtime degradation trend")

        at_risk = bool(is_anomaly or vibration_change_pct >= 15.0 or predicted_days <= 21.0)
        rows.append(
            {
                "asset_id": asset_id,
                "asset_type": asset_type,
                "predicted_failure_days": float(predicted_days),
                "trigger": " + ".join(trigger_parts),
                "suggested_action": _suggest_action(dominant_mode),
                "anomaly_score": float(anomaly_score),
                "at_risk": at_risk,
            }
        )

    if not rows:
        return pd.DataFrame(columns=FORECAST_COLUMNS)
    forecast = pd.DataFrame(rows)
    return forecast.sort_values(
        ["at_risk", "predicted_failure_days", "anomaly_score"],
        ascending=[False, True, True],
    ).reset_index(drop=True)


def run_analysis(raw_df: pd.DataFrame, models_path: Path | None = None) -> AnalysisResults:
    cleaned = standardize_dataframe(raw_df)
    if cleaned.empty:
        raise ValueError("No valid rows after cleaning. Check your CSV content.")

    overview = compute_overview(cleaned)
    asset_risk = compute_asset_risk(cleaned)
    failure_modes = compute_failure_modes(cleaned)
    factor_importance = compute_factor_importance(asset_risk)
    rolling_metrics = compute_rolling_mtbf_mttr(cleaned)
    trend_summary = compute_trend_summary(rolling_metrics)
    if not trend_summary.empty:
        asset_risk = asset_risk.merge(
            trend_summary[["asset_id", "mtbf_trend", "trend_note", "latest_mtbf_30d", "latest_mttr_30d"]],
            on="asset_id",
            how="left",
        )
    forecast_alerts = compute_health_forecast(cleaned, models_path=models_path)

    return AnalysisResults(
        cleaned=cleaned,
        overview=overview,
        asset_risk=asset_risk,
        failure_modes=failure_modes,
        factor_importance=factor_importance,
        rolling_metrics=rolling_metrics,
        trend_summary=trend_summary,
        forecast_alerts=forecast_alerts,
    )
