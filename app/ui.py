from __future__ import annotations

from pathlib import Path

import pandas as pd
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.analytics import AnalysisResults, run_analysis
from app.io_utils import resource_path


class ReliabilityWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Reliability Dashboard - Rotating Equipment")
        self.resize(1366, 840)
        self.results: AnalysisResults | None = None

        self.kpi_labels: dict[str, QLabel] = {}
        self.asset_table = QTableWidget()
        self.factor_table = QTableWidget()
        self.failure_fig = Figure(figsize=(5.8, 3.0), tight_layout=True)
        self.failure_canvas = FigureCanvas(self.failure_fig)
        self.downtime_fig = Figure(figsize=(5.8, 3.0), tight_layout=True)
        self.downtime_canvas = FigureCanvas(self.downtime_fig)

        self._build_ui()
        self.statusBar().showMessage("Ready")

    def _build_ui(self) -> None:
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(10)

        toolbar = QHBoxLayout()
        load_btn = QPushButton("Load CSV")
        sample_btn = QPushButton("Load Sample")
        export_btn = QPushButton("Export Excel")
        load_btn.clicked.connect(self.load_csv)
        sample_btn.clicked.connect(self.load_sample)
        export_btn.clicked.connect(self.export_excel)
        toolbar.addWidget(load_btn)
        toolbar.addWidget(sample_btn)
        toolbar.addWidget(export_btn)
        toolbar.addStretch(1)
        root_layout.addLayout(toolbar)

        root_layout.addWidget(self._build_kpi_box())

        content = QGridLayout()
        content.setHorizontalSpacing(10)
        content.setVerticalSpacing(10)
        content.addWidget(self._wrap_widget("Asset Risk Ranking", self.asset_table), 0, 0)
        content.addWidget(self._wrap_widget("Factor Importance", self.factor_table), 0, 1)
        content.addWidget(self._wrap_widget("Failures by Mode", self.failure_canvas), 1, 0)
        content.addWidget(self._wrap_widget("Downtime by Asset (Top 10)", self.downtime_canvas), 1, 1)
        root_layout.addLayout(content)

        self.setCentralWidget(root)

    def _build_kpi_box(self) -> QGroupBox:
        box = QGroupBox("Plant Reliability Snapshot")
        layout = QGridLayout(box)
        names = {
            "total_failures": "Total Failures",
            "total_downtime_hours": "Downtime (hrs)",
            "mttr_hours": "MTTR (hrs)",
            "mtbf_hours": "MTBF (hrs)",
            "availability_pct": "Availability (%)",
        }
        for i, (key, title) in enumerate(names.items()):
            name_label = QLabel(title)
            value_label = QLabel("-")
            value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            value_label.setStyleSheet("font-size: 16px; font-weight: 600; color: #113355;")
            layout.addWidget(name_label, 0, i)
            layout.addWidget(value_label, 1, i)
            self.kpi_labels[key] = value_label
        return box

    def _wrap_widget(self, title: str, widget: QWidget) -> QGroupBox:
        box = QGroupBox(title)
        layout = QVBoxLayout(box)
        layout.addWidget(widget)
        return box

    def load_csv(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Maintenance Log CSV",
            "",
            "CSV Files (*.csv);;All Files (*.*)",
        )
        if path:
            self._analyze_path(Path(path))

    def load_sample(self) -> None:
        sample = resource_path("sample_data", "maintenance_log.csv")
        self._analyze_path(sample)

    def _analyze_path(self, path: Path) -> None:
        self.statusBar().showMessage(f"Loading: {path.name}")
        try:
            raw = pd.read_csv(path)
            self.results = run_analysis(raw)
            self._render_results(self.results)
            self.statusBar().showMessage(f"Loaded {path.name} | {len(self.results.cleaned)} records")
        except Exception as exc:  # pragma: no cover - UI boundary
            QMessageBox.critical(self, "Analysis error", str(exc))
            self.statusBar().showMessage("Load failed")

    def _render_results(self, results: AnalysisResults) -> None:
        self._set_kpis(results.overview)
        self._load_table(
            self.asset_table,
            results.asset_risk[
                [
                    "asset_id",
                    "asset_type",
                    "failures",
                    "downtime_hours",
                    "mtbf_hours",
                    "mttr_hours",
                    "risk_score",
                ]
            ].round(2),
        )
        self._load_table(self.factor_table, results.factor_importance.round(3))
        self._draw_failure_modes(results.failure_modes)
        self._draw_downtime_by_asset(results.asset_risk)

    def _set_kpis(self, metrics: dict[str, float]) -> None:
        formats = {
            "total_failures": "{:.0f}",
            "total_downtime_hours": "{:.1f}",
            "mttr_hours": "{:.2f}",
            "mtbf_hours": "{:.2f}",
            "availability_pct": "{:.2f}",
        }
        for key, label in self.kpi_labels.items():
            label.setText(formats[key].format(metrics.get(key, 0.0)))

    def _load_table(self, table: QTableWidget, frame: pd.DataFrame) -> None:
        table.clear()
        table.setRowCount(len(frame))
        table.setColumnCount(len(frame.columns))
        table.setHorizontalHeaderLabels([str(c) for c in frame.columns])

        for row_idx in range(len(frame)):
            for col_idx, col_name in enumerate(frame.columns):
                value = frame.iloc[row_idx][col_name]
                text = f"{value}"
                item = QTableWidgetItem(text)
                if isinstance(value, (int, float)):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                table.setItem(row_idx, col_idx, item)

        table.resizeColumnsToContents()
        table.setAlternatingRowColors(True)
        table.setSortingEnabled(True)

    def _draw_failure_modes(self, frame: pd.DataFrame) -> None:
        self.failure_fig.clear()
        ax = self.failure_fig.add_subplot(111)
        top = frame.head(8).copy()
        ax.barh(top["failure_mode"], top["failures"], color="#0B5FA5")
        ax.invert_yaxis()
        ax.set_xlabel("Failure Count")
        ax.set_ylabel("Failure Mode")
        ax.grid(axis="x", linestyle="--", alpha=0.3)
        self.failure_canvas.draw()

    def _draw_downtime_by_asset(self, frame: pd.DataFrame) -> None:
        self.downtime_fig.clear()
        ax = self.downtime_fig.add_subplot(111)
        top = frame.sort_values("downtime_hours", ascending=False).head(10).copy()
        ax.bar(top["asset_id"], top["downtime_hours"], color="#0E9C68")
        ax.set_ylabel("Downtime (hrs)")
        ax.set_xlabel("Asset")
        ax.tick_params(axis="x", rotation=35)
        ax.grid(axis="y", linestyle="--", alpha=0.3)
        self.downtime_canvas.draw()

    def export_excel(self) -> None:
        if self.results is None:
            QMessageBox.information(self, "No analysis", "Load data first before export.")
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Excel Report",
            "reliability_report.xlsx",
            "Excel Files (*.xlsx)",
        )
        if not path:
            return

        try:
            overview_df = pd.DataFrame(
                [{"metric": k, "value": v} for k, v in self.results.overview.items()]
            )
            with pd.ExcelWriter(path, engine="openpyxl") as writer:
                overview_df.to_excel(writer, sheet_name="Overview", index=False)
                self.results.asset_risk.to_excel(writer, sheet_name="AssetRisk", index=False)
                self.results.failure_modes.to_excel(writer, sheet_name="FailureModes", index=False)
                self.results.factor_importance.to_excel(writer, sheet_name="Factors", index=False)
                self.results.cleaned.to_excel(writer, sheet_name="CleanedData", index=False)
            self.statusBar().showMessage(f"Exported report: {Path(path).name}")
        except Exception as exc:  # pragma: no cover - UI boundary
            QMessageBox.critical(self, "Export error", str(exc))
