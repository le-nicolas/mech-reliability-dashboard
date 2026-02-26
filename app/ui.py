from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.analytics import AnalysisResults, run_analysis, standardize_dataframe
from app.field_dialog import FieldInspectionDialog
from app.io_utils import resource_path
from app.storage import ReliabilityStore


class MplCanvas(FigureCanvas):
    def __init__(self, is_3d: bool = False) -> None:
        fig = Figure(figsize=(5, 3), tight_layout=True)
        self.axes = fig.add_subplot(111, projection="3d" if is_3d else None)
        super().__init__(fig)
        self.setMinimumHeight(220)


class ReliabilityWindow(QMainWindow):
    KPI = {
        "total_failures": "Total Failures",
        "total_downtime_hours": "Downtime (hrs)",
        "mttr_hours": "MTTR (hrs)",
        "mtbf_hours": "MTBF (hrs)",
        "availability_pct": "Availability (%)",
        "total_operating_hours": "Operating (hrs)",
    }
    FACTORS = {
        "vibration_mm_s": "Vibration (mm/s)",
        "temperature_c": "Temperature (C)",
        "load_pct": "Load (%)",
        "lubrication_gap_days": "Lubrication gap (days)",
        "alignment_error_mm": "Alignment error (mm)",
    }

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Mechanical Reliability Accomplishment Dashboard")
        self.resize(1640, 960)
        self.setMinimumSize(1220, 760)

        self.store = ReliabilityStore()
        self.results: AnalysisResults | None = None
        self.meta: dict[str, QLabel] = {}
        self.kpi: dict[str, QLabel] = {}

        self._build_ui()
        self._apply_styles()
        self._plot_cad_placeholder()
        self._load_default()

    def _build_ui(self) -> None:
        root = QWidget(self)
        v = QVBoxLayout(root)
        v.setContentsMargins(14, 14, 14, 12)
        v.setSpacing(10)

        header = QFrame()
        header.setObjectName("header")
        hv = QVBoxLayout(header)
        hv.setContentsMargins(0, 0, 0, 8)
        hv.setSpacing(7)
        stripe = QFrame()
        stripe.setObjectName("stripe")
        stripe.setFixedHeight(14)
        hv.addWidget(stripe)
        tr = QHBoxLayout()
        self.title = QLabel("ACCOMPLISHMENT RELIABILITY REPORT")
        self.title.setObjectName("title")
        self.date_lbl = QLabel("Report Date: --")
        self.date_lbl.setObjectName("date")
        tr.addWidget(self.title, 1)
        tr.addWidget(self.date_lbl, 0, Qt.AlignmentFlag.AlignRight)
        hv.addLayout(tr)
        meta_grid = QGridLayout()
        self._meta_field(meta_grid, 0, 0, "Job Title", "job")
        self._meta_field(meta_grid, 0, 2, "Owner", "owner")
        self._meta_field(meta_grid, 1, 0, "Location", "location")
        self._meta_field(meta_grid, 1, 2, "Source", "source")
        hv.addLayout(meta_grid)
        v.addWidget(header)

        c = QHBoxLayout()
        self.load_csv_btn = QPushButton("Load CSV")
        self.load_sample_btn = QPushButton("Load Sample")
        self.load_cad_btn = QPushButton("Load CAD (OBJ)")
        self.field_btn = QPushButton("Field Inspection")
        self.export_btn = QPushButton("Export Excel")
        self.load_csv_btn.clicked.connect(self._on_load_csv)
        self.load_sample_btn.clicked.connect(self._on_load_sample)
        self.load_cad_btn.clicked.connect(self._on_load_cad)
        self.field_btn.clicked.connect(self._on_open_field_module)
        self.export_btn.clicked.connect(self._on_export)
        c.addWidget(self.load_csv_btn)
        c.addWidget(self.load_sample_btn)
        c.addWidget(self.load_cad_btn)
        c.addWidget(self.field_btn)
        c.addWidget(self.export_btn)
        c.addStretch(1)
        v.addLayout(c)

        kpi_strip = QFrame()
        kpi_strip.setObjectName("kpiStrip")
        kg = QGridLayout(kpi_strip)
        kg.setContentsMargins(10, 8, 10, 8)
        kg.setSpacing(8)
        for i, (key, text) in enumerate(self.KPI.items()):
            card = QFrame()
            card.setObjectName("card")
            cv = QVBoxLayout(card)
            cv.setContentsMargins(10, 8, 10, 8)
            name = QLabel(text)
            name.setObjectName("kpiName")
            val = QLabel("--")
            val.setObjectName("kpiVal")
            cv.addWidget(name)
            cv.addWidget(val)
            kg.addWidget(card, i // 3, i % 3)
            self.kpi[key] = val
        v.addWidget(kpi_strip)

        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(False)

        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(8)

        asset_g = QGroupBox("Work Priority Register")
        ag = QVBoxLayout(asset_g)
        ag.setContentsMargins(8, 16, 8, 8)
        self.asset_hint = QLabel("Yellow rows indicate immediate field action.")
        self.asset_hint.setObjectName("hint")
        self.asset_tbl = QTableWidget()
        self._setup_table(
            self.asset_tbl,
            [
                "Item",
                "Asset",
                "Type",
                "Line",
                "Failures",
                "Downtime",
                "MTBF",
                "MTTR",
                "Risk",
                "Status",
                "Action",
                "Quality Reason",
            ],
        )
        ag.addWidget(self.asset_hint)
        ag.addWidget(self.asset_tbl)
        lv.addWidget(asset_g, 5)

        fcast_g = QGroupBox("Forecast Alerts")
        fg = QVBoxLayout(fcast_g)
        fg.setContentsMargins(8, 16, 8, 8)
        self.fcast_tbl = QTableWidget()
        self._setup_table(
            self.fcast_tbl,
            ["Asset", "Type", "Days", "At Risk", "Trigger", "Suggested Action"],
        )
        fg.addWidget(self.fcast_tbl)
        lv.addWidget(fcast_g, 3)

        charts = QHBoxLayout()
        fail_g = QGroupBox("Failures by Mode")
        fd = QVBoxLayout(fail_g)
        fd.setContentsMargins(8, 16, 8, 8)
        self.fail_canvas = MplCanvas()
        fd.addWidget(self.fail_canvas)
        down_g = QGroupBox("Downtime by Asset")
        dd = QVBoxLayout(down_g)
        dd.setContentsMargins(8, 16, 8, 8)
        self.down_canvas = MplCanvas()
        dd.addWidget(self.down_canvas)
        charts.addWidget(fail_g, 1)
        charts.addWidget(down_g, 1)
        lv.addLayout(charts, 3)

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(8)

        cad_g = QGroupBox("3D CAD Evidence (OBJ)")
        cd = QVBoxLayout(cad_g)
        cd.setContentsMargins(8, 16, 8, 8)
        self.cad_canvas = MplCanvas(is_3d=True)
        self.cad_info = QLabel("No CAD loaded.")
        self.cad_info.setObjectName("hint")
        cd.addWidget(self.cad_canvas)
        cd.addWidget(self.cad_info)
        rv.addWidget(cad_g, 5)

        fact_g = QGroupBox("Risk Driver Matrix")
        fm = QVBoxLayout(fact_g)
        fm.setContentsMargins(8, 16, 8, 8)
        self.factor_tbl = QTableWidget()
        self._setup_table(self.factor_tbl, ["Factor", "High", "Low", "Lift", "Importance"])
        fm.addWidget(self.factor_tbl)
        rv.addWidget(fact_g, 2)

        note_g = QGroupBox("Quality Issue Brief")
        nm = QVBoxLayout(note_g)
        nm.setContentsMargins(8, 16, 8, 8)
        self.notes = QTextEdit()
        self.notes.setReadOnly(True)
        nm.addWidget(self.notes)
        rv.addWidget(note_g, 3)

        split.addWidget(left)
        split.addWidget(right)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        v.addWidget(split, 1)

        self.footer = QLabel("No dataset loaded.")
        self.footer.setObjectName("footer")
        v.addWidget(self.footer)
        self.setCentralWidget(root)
        self.statusBar().showMessage("Ready.")

    def _meta_field(self, g: QGridLayout, r: int, c: int, txt: str, key: str) -> None:
        l = QLabel(f"{txt}:")
        l.setObjectName("metaL")
        v = QLabel("--")
        v.setObjectName("metaV")
        g.addWidget(l, r, c)
        g.addWidget(v, r, c + 1)
        self.meta[key] = v

    def _setup_table(self, table: QTableWidget, headers: list[str]) -> None:
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        header = table.horizontalHeader()
        header.setStretchLastSection(True)
        for i in range(max(0, len(headers) - 1)):
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow { background: #f3efe4; color: #1f1f1f; }
            QFrame#header, QFrame#kpiStrip { background: #fffdf7; border: 1px solid #8d8678; }
            QFrame#stripe { background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #dfc146, stop:0.5 #f3dd7b, stop:1 #dfc146); border: none; }
            QLabel#title { font-family: "Times New Roman"; font-size: 24px; font-weight: 700; letter-spacing: 1px; }
            QLabel#date { font-size: 11pt; font-weight: 600; }
            QLabel#metaL { font-size: 9pt; font-weight: 600; color: #4b463c; }
            QLabel#metaV { font-size: 9.5pt; }
            QPushButton { background: #2b2b2b; color: #f8f8f8; border: 1px solid #4b4b4b; border-radius: 3px; padding: 6px 10px; min-width: 112px; font-weight: 600; }
            QPushButton:hover { background: #3a3a3a; }
            QFrame#card { background: #fdf7de; border: 1px solid #998f77; }
            QLabel#kpiName { font-size: 9pt; font-weight: 600; color: #4a4439; }
            QLabel#kpiVal { font-size: 16pt; font-weight: 700; }
            QGroupBox { background: #fffdf7; border: 1px solid #8d8678; margin-top: 10px; font-size: 10pt; font-weight: 600; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
            QTableWidget { background: #ffffff; alternate-background-color: #f5f1e5; gridline-color: #8d8678; border: 1px solid #8d8678; selection-background-color: #f5dc66; selection-color: #1d1d1d; font-size: 9pt; }
            QHeaderView::section { background: #ece2c2; border: 1px solid #8d8678; padding: 4px; font-weight: 700; }
            QTextEdit { background: #fffdf7; border: 1px solid #8d8678; font-family: "Segoe UI"; font-size: 9.5pt; }
            QLabel#hint, QLabel#footer { color: #3f3a30; font-size: 9pt; }
            """
        )
        self.title.setFont(QFont("Times New Roman", 24, QFont.Weight.Bold))

    def _load_default(self) -> None:
        sample = resource_path("sample_data", "maintenance_log.csv")
        if sample.exists():
            self._load_dataset(sample, "sample_data/maintenance_log.csv", persist=False)
        else:
            self.statusBar().showMessage("Ready. Load a CSV file to begin.")

    def _on_load_csv(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Load maintenance CSV", str(Path.home()), "CSV files (*.csv);;All files (*.*)")
        if path:
            self._load_dataset(Path(path), Path(path).name, persist=True)

    def _on_load_sample(self) -> None:
        sample = resource_path("sample_data", "maintenance_log.csv")
        if sample.exists():
            self._load_dataset(sample, "sample_data/maintenance_log.csv", persist=False)
        else:
            QMessageBox.warning(self, "Sample Missing", f"Sample not found:\n{sample}")

    def _on_open_field_module(self) -> None:
        logo = resource_path("assets", "company-logo.png")
        dlg = FieldInspectionDialog(
            self,
            on_commit=self._ingest_field_rows,
            logo_path=logo if logo.exists() else None,
            csv_sink=resource_path("sample_data", "field_inspection_log.csv"),
        )
        dlg.exec()

    def _load_dataset(self, path: Path, source: str, persist: bool) -> None:
        try:
            raw = pd.read_csv(path)
            cleaned = standardize_dataframe(raw)
            if cleaned.empty:
                raise ValueError("No valid rows after cleaning.")
            res = run_analysis(cleaned)
        except Exception as exc:
            QMessageBox.critical(self, "Analysis Failed", str(exc))
            return

        if persist:
            try:
                self.store.append_records(cleaned, source_name=source)
            except Exception:
                pass

        self.results = res
        self._refresh(res, source)

    def _ingest_field_rows(self, rows: pd.DataFrame, source_label: str) -> None:
        cleaned = standardize_dataframe(rows)
        if cleaned.empty:
            raise ValueError("Field inspection rows are empty after cleaning.")

        self.store.append_records(cleaned, source_name=source_label)

        if self.results is not None and not self.results.cleaned.empty:
            combined = pd.concat([self.results.cleaned, cleaned], ignore_index=True)
        else:
            combined = cleaned

        updated = run_analysis(combined)
        self.results = updated
        self._refresh(updated, f"{source_label} (field)")

    def _refresh(self, res: AnalysisResults, source: str) -> None:
        cleaned = res.cleaned
        types = [t for t in cleaned["asset_type"].replace("", "Unknown").value_counts().index.tolist() if t != "Unknown"][:3]
        lines = [l for l in cleaned["line"].replace("", "Unknown").value_counts().index.tolist() if l != "Unknown"][:2]
        self.meta["job"].setText("Rotating Equipment Reliability Review" + (f" ({', '.join(types)})" if types else ""))
        self.meta["owner"].setText("Mechanical Reliability Team")
        self.meta["location"].setText(", ".join(lines) if lines else "Plant-wide")
        self.meta["source"].setText(source)
        date = pd.to_datetime(cleaned["event_date"]).max() if cleaned["event_date"].notna().any() else pd.Timestamp.utcnow()
        self.date_lbl.setText(f"Report Date: {date.strftime('%d %b %Y')}")

        for key, lbl in self.kpi.items():
            value = float(res.overview.get(key, 0))
            lbl.setText(f"{value:,.2f}%" if key == "availability_pct" else (f"{value:,.0f}" if key == "total_failures" else f"{value:,.1f}"))

        self._fill_asset_table(res.asset_risk)
        self._fill_forecast_table(res.forecast_alerts)
        self._fill_factor_table(res.factor_importance)
        self._draw_failures(res.failure_modes)
        self._draw_downtime(res.asset_risk)
        self._fill_notes(res)

        self.footer.setText(f"Source: {source} | Records: {len(cleaned):,} | Assets: {cleaned['asset_id'].nunique():,}")
        self.statusBar().showMessage(f"Analysis complete for {len(cleaned):,} records.")

    def _risk_status(self, score: float, scores: pd.Series) -> str:
        return "CRITICAL" if score >= float(scores.quantile(0.75)) else ("WATCH" if score >= float(scores.quantile(0.45)) else "NORMAL")

    def _action(self, mode: str) -> str:
        t = str(mode).lower()
        if "bearing" in t:
            return "Bearing inspection and lubrication audit"
        if "seal" in t:
            return "Seal replacement and leak check"
        if "alignment" in t:
            return "Shaft alignment correction"
        if "cavitation" in t:
            return "Suction line and NPSH verification"
        if "overheat" in t or "temperature" in t:
            return "Cooling and load balancing review"
        return "Targeted reliability inspection"

    def _fill_asset_table(self, frame: pd.DataFrame) -> None:
        t = self.asset_tbl
        t.setRowCount(0)
        if frame.empty:
            return
        t.setRowCount(len(frame))
        scores = pd.to_numeric(frame["risk_score"], errors="coerce").fillna(0.0)
        for r, (_, row) in enumerate(frame.iterrows()):
            score = float(row.get("risk_score", 0))
            status = self._risk_status(score, scores)
            values = [r + 1, row.get("asset_id", ""), row.get("asset_type", ""), row.get("line", ""), f"{float(row.get('failures', 0)):,.0f}", f"{float(row.get('downtime_hours', 0)):,.1f}", f"{float(row.get('mtbf_hours', 0)):,.1f}", f"{float(row.get('mttr_hours', 0)):,.1f}", f"{score:,.1f}", status, self._action(str(row.get("dominant_failure_mode", ""))), row.get("risk_explanation", "")]
            bg = QColor("#f5de73") if status == "CRITICAL" else (QColor("#f8ebba") if status == "WATCH" else QColor())
            for c, v in enumerate(values):
                it = QTableWidgetItem(str(v))
                if c in {0, 4, 5, 6, 7, 8}:
                    it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if status in {"CRITICAL", "WATCH"}:
                    it.setBackground(bg)
                t.setItem(r, c, it)
        h = t.horizontalHeader()
        for i in range(t.columnCount()):
            h.setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch if i >= t.columnCount() - 2 else QHeaderView.ResizeMode.ResizeToContents)

    def _fill_forecast_table(self, frame: pd.DataFrame) -> None:
        t = self.fcast_tbl
        t.setRowCount(0)
        if frame.empty:
            return
        t.setRowCount(len(frame))
        for r, (_, row) in enumerate(frame.iterrows()):
            at = bool(row.get("at_risk", False))
            vals = [row.get("asset_id", ""), row.get("asset_type", ""), f"{float(row.get('predicted_failure_days', 0)):,.1f}", "YES" if at else "No", row.get("trigger", ""), row.get("suggested_action", "")]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(str(v))
                if c == 2:
                    it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if at:
                    it.setBackground(QColor("#f6e39a"))
                t.setItem(r, c, it)
        h = t.horizontalHeader()
        for i in range(t.columnCount()):
            h.setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch if i >= t.columnCount() - 2 else QHeaderView.ResizeMode.ResizeToContents)

    def _fill_factor_table(self, frame: pd.DataFrame) -> None:
        t = self.factor_tbl
        t.setRowCount(0)
        if frame.empty:
            return
        t.setRowCount(len(frame))
        for r, (_, row) in enumerate(frame.iterrows()):
            vals = [self.FACTORS.get(str(row.get("factor", "")), str(row.get("factor", "")).replace("_", " ")), f"{float(row.get('high_risk_mean', 0)):,.3f}", f"{float(row.get('low_risk_mean', 0)):,.3f}", f"{float(row.get('lift', 0)):,.3f}", f"{float(row.get('importance', 0)):,.3f}"]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(str(v))
                if c > 0:
                    it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                t.setItem(r, c, it)

    def _draw_failures(self, frame: pd.DataFrame) -> None:
        ax = self.fail_canvas.axes
        ax.clear()
        ax.set_facecolor("#fffdf7")
        self.fail_canvas.figure.set_facecolor("#fffdf7")
        if frame.empty:
            ax.text(0.5, 0.5, "No failure-mode data", ha="center", va="center", transform=ax.transAxes)
            ax.set_axis_off()
        else:
            d = frame.head(8).sort_values("failures")
            ax.barh(d["failure_mode"], d["failures"], color="#e2b93f", edgecolor="#4a402b")
            ax.set_title("Failures by Mode", fontsize=10.5, fontweight="bold")
            ax.set_xlabel("Failure Count")
            ax.grid(axis="x", linestyle="--", alpha=0.35, color="#8f8a7a")
        self.fail_canvas.draw_idle()

    def _draw_downtime(self, frame: pd.DataFrame) -> None:
        ax = self.down_canvas.axes
        ax.clear()
        ax.set_facecolor("#fffdf7")
        self.down_canvas.figure.set_facecolor("#fffdf7")
        if frame.empty:
            ax.text(0.5, 0.5, "No downtime data", ha="center", va="center", transform=ax.transAxes)
            ax.set_axis_off()
        else:
            d = frame.sort_values("downtime_hours", ascending=False).head(8)
            ax.bar(d["asset_id"], d["downtime_hours"], color="#3c7e71", edgecolor="#21453e")
            ax.set_title("Downtime by Asset", fontsize=10.5, fontweight="bold")
            ax.set_ylabel("Downtime (hrs)")
            ax.grid(axis="y", linestyle="--", alpha=0.35, color="#8f8a7a")
            ax.tick_params(axis="x", labelrotation=22, labelsize=8.5)
        self.down_canvas.draw_idle()

    def _fill_notes(self, res: AnalysisResults) -> None:
        lines = ["QUALITY ISSUE BRIEF", "", "Priority observations:"]
        top = res.asset_risk.head(3)
        if top.empty:
            lines.append("- No asset-level risk observations yet.")
        else:
            for _, row in top.iterrows():
                lines.append(f"- {row.get('asset_id', 'Unknown')}: {row.get('risk_explanation', '')}")
        alerts = res.forecast_alerts[res.forecast_alerts["at_risk"]].head(4)
        lines += ["", "Near-term risk alerts:"]
        if alerts.empty:
            lines.append("- No anomaly-triggered alerts in the latest run.")
        else:
            for _, row in alerts.iterrows():
                lines.append(f"- {row.get('asset_id', 'Unknown')}: ~{float(row.get('predicted_failure_days', 0)):.0f} day(s), trigger: {row.get('trigger', '')}.")
        lines += ["", "Suggested site actions:", "- Verify alignment and lubrication on top-risk assets.", "- Use yellow-highlighted rows as first-pass field checklist items."]
        self.notes.setPlainText("\n".join(lines))

    def _on_load_cad(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Load CAD OBJ", str(Path.home()), "Wavefront OBJ (*.obj);;All files (*.*)")
        if not path:
            return
        try:
            vertices, faces = self._parse_obj(Path(path))
            self._plot_cad(vertices, faces)
            span = vertices.max(axis=0) - vertices.min(axis=0)
            self.cad_info.setText(f"{Path(path).name} | Vertices: {len(vertices):,} | Faces: {len(faces):,} | Span (mm): {span[0]:.1f} x {span[1]:.1f} x {span[2]:.1f}")
        except Exception as exc:
            QMessageBox.critical(self, "CAD Load Failed", str(exc))

    @staticmethod
    def _parse_obj(path: Path) -> tuple[np.ndarray, np.ndarray]:
        vertices: list[tuple[float, float, float]] = []
        faces: list[tuple[int, int, int]] = []
        with path.open("r", encoding="utf-8", errors="ignore") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                p = line.split()
                if p[0] == "v" and len(p) >= 4:
                    vertices.append((float(p[1]), float(p[2]), float(p[3])))
                elif p[0] == "f" and len(p) >= 4:
                    poly: list[int] = []
                    for tok in p[1:]:
                        idx = tok.split("/")[0]
                        if not idx:
                            continue
                        n = int(idx)
                        n = len(vertices) + n if n < 0 else n - 1
                        poly.append(n)
                    if len(poly) >= 3:
                        for i in range(1, len(poly) - 1):
                            faces.append((poly[0], poly[i], poly[i + 1]))
        if not vertices:
            raise ValueError("No vertices found in OBJ.")
        v = np.asarray(vertices, dtype=float)
        f = np.asarray(faces, dtype=int) if faces else np.empty((0, 3), dtype=int)
        if len(f):
            ok = (f >= 0).all(axis=1) & (f < len(v)).all(axis=1)
            f = f[ok]
        return v, f

    def _plot_cad_placeholder(self) -> None:
        ax = self.cad_canvas.axes
        ax.clear()
        ax.set_facecolor("#fffdf7")
        self.cad_canvas.figure.set_facecolor("#fffdf7")
        ax.text2D(0.5, 0.5, "Load a .obj file to review geometry.", transform=ax.transAxes, ha="center", va="center", fontsize=10, color="#3f3a30")
        ax.set_axis_off()
        self.cad_canvas.draw_idle()

    def _plot_cad(self, vertices: np.ndarray, faces: np.ndarray) -> None:
        ax = self.cad_canvas.axes
        ax.clear()
        ax.set_facecolor("#fffdf7")
        self.cad_canvas.figure.set_facecolor("#fffdf7")
        if len(vertices) == 0:
            self._plot_cad_placeholder()
            return
        if len(faces):
            use = faces[:: max(1, len(faces) // 9000)] if len(faces) > 9000 else faces
            mesh = Poly3DCollection(vertices[use], facecolor="#e8c04f", edgecolor="#464136", linewidths=0.12, alpha=0.57)
            ax.add_collection3d(mesh)
        else:
            ax.scatter(vertices[:, 0], vertices[:, 1], vertices[:, 2], s=1.5, c="#2b7b73", alpha=0.65)
        mins, maxs = vertices.min(axis=0), vertices.max(axis=0)
        center = (mins + maxs) / 2.0
        r = max(float((maxs - mins).max()) / 2.0, 1.0)
        ax.set_xlim(center[0] - r, center[0] + r)
        ax.set_ylim(center[1] - r, center[1] + r)
        ax.set_zlim(center[2] - r, center[2] + r)
        try:
            ax.set_box_aspect((1.0, 1.0, 0.85))
        except Exception:
            pass
        ax.set_title("CAD View (Isometric)", fontsize=10.5, fontweight="bold")
        ax.set_xlabel("X (mm)")
        ax.set_ylabel("Y (mm)")
        ax.set_zlabel("Z (mm)")
        ax.view_init(elev=24, azim=36)
        self.cad_canvas.draw_idle()

    def _on_export(self) -> None:
        if self.results is None:
            QMessageBox.information(self, "Nothing to Export", "Run an analysis first.")
            return
        default = f"reliability_report_{pd.Timestamp.utcnow():%Y%m%d_%H%M}.xlsx"
        target, _ = QFileDialog.getSaveFileName(self, "Export Analysis to Excel", str(Path.home() / default), "Excel Workbook (*.xlsx)")
        if not target:
            return
        try:
            with pd.ExcelWriter(Path(target), engine="openpyxl") as w:
                pd.DataFrame([{"metric": k, "value": v} for k, v in self.results.overview.items()]).to_excel(w, sheet_name="overview", index=False)
                self.results.cleaned.to_excel(w, sheet_name="cleaned_records", index=False)
                self.results.asset_risk.to_excel(w, sheet_name="asset_risk", index=False)
                self.results.failure_modes.to_excel(w, sheet_name="failure_modes", index=False)
                self.results.factor_importance.to_excel(w, sheet_name="factor_importance", index=False)
                self.results.forecast_alerts.to_excel(w, sheet_name="forecast_alerts", index=False)
                self.results.trend_summary.to_excel(w, sheet_name="trend_summary", index=False)
                self.results.rolling_metrics.to_excel(w, sheet_name="rolling_metrics", index=False)
            QMessageBox.information(self, "Export Complete", f"Saved:\n{target}")
            self.statusBar().showMessage(f"Exported Excel report to {Path(target).name}.")
        except Exception as exc:
            QMessageBox.critical(self, "Export Failed", str(exc))
