from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from html import escape
from pathlib import Path

import pandas as pd

EQUIPMENT_TYPES = [
    "Screw Conveyor",
    "Pump",
    "Motor",
    "Fan",
    "Compressor",
    "Gearbox",
    "Blower",
    "Conveyor",
    "Other",
]

FAILURE_MODES = [
    "Ribbon to Shaft Gap",
    "Wrong Inlet Orientation",
    "Metal to Metal Contact",
    "Not Aligned Screw",
    "Bearing Wear",
    "Seal Leak",
    "Imbalance",
    "Overheat",
    "Overload Trip",
    "Cavitation",
    "Corrosion",
    "Vibration Alarm",
]

SEVERITY_LEVELS = ["Critical", "High", "Medium", "Low", "Observation"]

DEFECT_LOCATIONS = [
    "Inlet",
    "Outlet",
    "Shaft",
    "Bearing Housing",
    "Seal Area",
    "Coupling",
    "Rotor/Impeller",
    "Frame/Support",
    "Drive End",
    "Non-Drive End",
    "Electrical Panel",
    "Other",
]

SEVERITY_PROFILE = {
    "Critical": {
        "downtime_hours": 12.0,
        "repair_hours": 8.0,
        "operating_hours": 120.0,
        "vibration_mm_s": 11.5,
        "temperature_c": 102.0,
        "load_pct": 95.0,
        "lubrication_gap_days": 34.0,
        "alignment_error_mm": 1.15,
    },
    "High": {
        "downtime_hours": 8.0,
        "repair_hours": 5.5,
        "operating_hours": 165.0,
        "vibration_mm_s": 9.2,
        "temperature_c": 92.0,
        "load_pct": 88.0,
        "lubrication_gap_days": 24.0,
        "alignment_error_mm": 0.82,
    },
    "Medium": {
        "downtime_hours": 4.0,
        "repair_hours": 3.0,
        "operating_hours": 225.0,
        "vibration_mm_s": 7.4,
        "temperature_c": 84.0,
        "load_pct": 79.0,
        "lubrication_gap_days": 18.0,
        "alignment_error_mm": 0.58,
    },
    "Low": {
        "downtime_hours": 1.8,
        "repair_hours": 1.2,
        "operating_hours": 260.0,
        "vibration_mm_s": 6.2,
        "temperature_c": 75.0,
        "load_pct": 72.0,
        "lubrication_gap_days": 12.0,
        "alignment_error_mm": 0.36,
    },
    "Observation": {
        "downtime_hours": 0.6,
        "repair_hours": 0.6,
        "operating_hours": 300.0,
        "vibration_mm_s": 5.4,
        "temperature_c": 70.0,
        "load_pct": 66.0,
        "lubrication_gap_days": 8.0,
        "alignment_error_mm": 0.22,
    },
}

ACTION_HINTS = {
    "bearing": "Inspect bearing fit, lubrication condition, and replace if wear exceeds tolerance.",
    "seal": "Inspect seal integrity and shaft sleeve condition, then replace seal if leakage persists.",
    "alignment": "Perform shaft/screw alignment correction before restart and verify runout.",
    "orientation": "Correct inlet/outlet orientation as per drawing and perform dry-run clearance check.",
    "metal": "Stop operation and remove metal-to-metal interference before further rotation.",
    "vibration": "Perform vibration route check and dynamic balancing where required.",
    "overheat": "Inspect cooling and load profile; verify thermal trip settings and airflow.",
    "overload": "Check process load, trip settings, and motor current profile before restart.",
    "cavitation": "Review suction conditions (NPSH), valve position, and piping restrictions.",
    "corrosion": "Assess corrosion depth, repair coating, and replace impacted components.",
}


@dataclass
class FieldDefect:
    failure_mode: str
    severity: str
    location: str
    notes: str = ""
    photo_path: str = ""
    caption: str = ""


@dataclass
class FieldInspection:
    equipment_type: str
    asset_id: str
    site_location: str
    inspector: str
    inspection_date: date
    shift: str = "Field"
    project_title: str = ""
    company_name: str = "Mechanical Reliability Services, Inc."
    company_tagline: str = "providing excellence in engineering works"
    owner: str = "Mechanical Reliability Team"
    defects: list[FieldDefect] = field(default_factory=list)


def recommended_action(failure_mode: str) -> str:
    mode = failure_mode.lower()
    for keyword, action in ACTION_HINTS.items():
        if keyword in mode:
            return action
    return "Conduct targeted reliability inspection and execute corrective action per site standard."


def inspection_to_dataframe(inspection: FieldInspection) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    asset_id = inspection.asset_id.strip() or "FIELD-UNSPEC"
    asset_type = inspection.equipment_type.strip() or "Unknown"
    line = inspection.site_location.strip() or "Field"

    for defect in inspection.defects:
        severity = defect.severity if defect.severity in SEVERITY_PROFILE else "Medium"
        profile = dict(SEVERITY_PROFILE[severity])

        mode = defect.failure_mode.lower()
        if "alignment" in mode or "orientation" in mode:
            profile["alignment_error_mm"] = max(profile["alignment_error_mm"], 0.95)
        if "vibration" in mode or "imbalance" in mode:
            profile["vibration_mm_s"] = max(profile["vibration_mm_s"], 10.0)
        if "overheat" in mode:
            profile["temperature_c"] = max(profile["temperature_c"], 98.0)
        if "overload" in mode:
            profile["load_pct"] = max(profile["load_pct"], 92.0)

        rows.append(
            {
                "event_date": pd.Timestamp(inspection.inspection_date),
                "asset_id": asset_id,
                "asset_type": asset_type,
                "line": line,
                "shift": inspection.shift or "Field",
                "failure_mode": defect.failure_mode,
                "downtime_hours": profile["downtime_hours"],
                "repair_hours": profile["repair_hours"],
                "operating_hours": profile["operating_hours"],
                "vibration_mm_s": profile["vibration_mm_s"],
                "temperature_c": profile["temperature_c"],
                "load_pct": profile["load_pct"],
                "lubrication_gap_days": profile["lubrication_gap_days"],
                "alignment_error_mm": profile["alignment_error_mm"],
            }
        )

    return pd.DataFrame(rows)


def append_rows_to_csv(rows: pd.DataFrame, csv_path: Path) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not csv_path.exists()
    rows.to_csv(csv_path, mode="a", index=False, header=write_header)


def _photo_uri(photo_path: str) -> str:
    if not photo_path:
        return ""
    path = Path(photo_path)
    if not path.exists():
        return ""
    return path.resolve().as_uri()


def _html_table_rows(defects: list[FieldDefect]) -> str:
    rows: list[str] = []
    for idx, defect in enumerate(defects, start=1):
        rows.append(
            "<tr>"
            f"<td>{idx}</td>"
            f"<td>{escape(defect.failure_mode)}</td>"
            f"<td>{escape(defect.severity)}</td>"
            f"<td>{escape(defect.location)}</td>"
            f"<td>{escape(defect.notes or '-')}</td>"
            f"<td>{escape(recommended_action(defect.failure_mode))}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def _html_picture_blocks(defects: list[FieldDefect]) -> str:
    blocks: list[str] = []
    picture_no = 1
    for defect in defects:
        uri = _photo_uri(defect.photo_path)
        if not uri:
            continue
        caption = defect.caption.strip() or f"{defect.failure_mode} - {defect.location}"
        blocks.append(
            '<figure class="pic">'
            f'<img src="{escape(uri)}" alt="Picture {picture_no}"/>'
            f"<figcaption>Picture {picture_no}: {escape(caption)}</figcaption>"
            "</figure>"
        )
        picture_no += 1

    if not blocks:
        return '<p class="no-photo">No field photos attached for this inspection.</p>'
    return "\n".join(blocks)


def build_report_html(inspection: FieldInspection, logo_path: Path | None = None) -> str:
    report_date = inspection.inspection_date.strftime("%B %d, %Y")
    logo_uri = logo_path.resolve().as_uri() if logo_path and logo_path.exists() else ""
    logo_html = (
        f'<img class="logo" src="{escape(logo_uri)}" alt="Company Logo"/>'
        if logo_uri
        else '<div class="logo logo-fallback">LOGO</div>'
    )
    title = inspection.project_title.strip() or f"{inspection.equipment_type} Inspection"
    picture_blocks = _html_picture_blocks(inspection.defects)
    table_rows = _html_table_rows(inspection.defects)

    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>Inspection Report - {escape(inspection.asset_id)}</title>
  <style>
    @page {{ size: A4; margin: 14mm; }}
    body {{ font-family: Arial, sans-serif; color: #1c1c1c; margin: 0; }}
    .bar {{ height: 14px; background: linear-gradient(90deg,#dfc146,#f3dd7b,#dfc146); margin-bottom: 8px; }}
    .header {{ display: flex; gap: 12px; align-items: center; border-bottom: 1px solid #8d8678; padding-bottom: 8px; }}
    .logo {{ width: 84px; height: 60px; object-fit: contain; border: 1px solid #8d8678; }}
    .logo-fallback {{ display: flex; align-items: center; justify-content: center; background: #f5f1e5; font-weight: bold; }}
    .h1 {{ font-family: "Times New Roman", serif; font-size: 28px; font-weight: 700; margin: 2px 0; }}
    .sub {{ font-style: italic; color: #3a3a3a; margin: 0; }}
    .meta {{ margin-top: 8px; font-size: 13px; border: 1px solid #8d8678; border-collapse: collapse; width: 100%; }}
    .meta td {{ border: 1px solid #8d8678; padding: 6px 8px; }}
    .section-title {{ margin: 16px 0 8px 0; font-size: 18px; font-weight: 700; }}
    .table {{ width: 100%; border-collapse: collapse; font-size: 12.5px; }}
    .table th, .table td {{ border: 1px solid #8d8678; padding: 6px; vertical-align: top; }}
    .table th {{ background: #ece2c2; text-align: left; }}
    .pic-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0,1fr)); gap: 10px; }}
    .pic {{ border: 1px solid #8d8678; margin: 0; padding: 6px; }}
    .pic img {{ width: 100%; max-height: 250px; object-fit: contain; }}
    .pic figcaption {{ margin-top: 6px; font-size: 12px; font-weight: 600; }}
    .no-photo {{ font-style: italic; color: #555; }}
    .sign {{ margin-top: 28px; display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
    .line {{ border-top: 1px solid #1f1f1f; margin-top: 26px; padding-top: 4px; font-size: 12px; }}
  </style>
</head>
<body>
  <div class="bar"></div>
  <div class="header">
    {logo_html}
    <div>
      <div class="h1">{escape(inspection.company_name)}</div>
      <p class="sub">{escape(inspection.company_tagline)}</p>
      <p style="margin:6px 0 0 0;font-size:13px;"><strong>FIELD INSPECTION REPORT</strong></p>
    </div>
  </div>

  <table class="meta">
    <tr>
      <td><strong>Job Title</strong><br/>{escape(title)}</td>
      <td><strong>Owner</strong><br/>{escape(inspection.owner)}</td>
      <td><strong>Date</strong><br/>{escape(report_date)}</td>
    </tr>
    <tr>
      <td><strong>Equipment</strong><br/>{escape(inspection.equipment_type)}</td>
      <td><strong>Asset ID</strong><br/>{escape(inspection.asset_id)}</td>
      <td><strong>Location</strong><br/>{escape(inspection.site_location or "Field")}</td>
    </tr>
    <tr>
      <td><strong>Inspector</strong><br/>{escape(inspection.inspector or "N/A")}</td>
      <td><strong>Shift</strong><br/>{escape(inspection.shift)}</td>
      <td><strong>Total Defects</strong><br/>{len(inspection.defects)}</td>
    </tr>
  </table>

  <div class="section-title">Defect Summary</div>
  <table class="table">
    <thead>
      <tr>
        <th style="width:38px;">#</th>
        <th style="width:130px;">Failure Mode</th>
        <th style="width:78px;">Severity</th>
        <th style="width:110px;">Location</th>
        <th>Inspector Notes</th>
        <th>Recommended Corrective Action</th>
      </tr>
    </thead>
    <tbody>
      {table_rows}
    </tbody>
  </table>

  <div class="section-title">Picture Evidence</div>
  <div class="pic-grid">
    {picture_blocks}
  </div>

  <div class="sign">
    <div class="line">Prepared by (Inspector Signature / Date)</div>
    <div class="line">Approved by (Supervisor Signature / Date)</div>
  </div>
</body>
</html>
"""


def save_html_report(html: str, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
