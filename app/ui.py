from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHeaderView,
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
    DEFAULT_CAD_PATH = Path(r"c:\Users\User\Downloads\gear-box-47.snapshot.3\rotating_equipment.obj")

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Reliability Dashboard - Rotating Equipment")
        self.resize(1600, 940)
        self.results: AnalysisResults | None = None
        self.current_cad_path: Path | None = None

        self.kpi_labels: dict[str, QLabel] = {}
        self.asset_table = QTableWidget()
        self.factor_table = QTableWidget()
        self.failure_fig = Figure(figsize=(7.2, 3.6), constrained_layout=True, dpi=110)
        self.failure_canvas = FigureCanvas(self.failure_fig)
        self.downtime_fig = Figure(figsize=(7.2, 3.6), constrained_layout=True, dpi=110)
        self.downtime_canvas = FigureCanvas(self.downtime_fig)
        self.cad_fig = Figure(figsize=(7.0, 3.8), constrained_layout=True, dpi=110)
        self.cad_canvas = FigureCanvas(self.cad_fig)
        self.cad_info_label = QLabel("No CAD loaded")
        self.cad_info_label.setStyleSheet("color: #32506D;")
        self.cad_info_label.setWordWrap(True)

        self._build_ui()
        self._try_load_default_cad()
        if self.current_cad_path is None:
            self.statusBar().showMessage("Ready")

    def _build_ui(self) -> None:
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(14, 14, 14, 14)
        root_layout.setSpacing(12)

        toolbar = QHBoxLayout()
        load_btn = QPushButton("Load CSV")
        sample_btn = QPushButton("Load Sample")
        cad_btn = QPushButton("Load CAD (OBJ)")
        export_btn = QPushButton("Export Excel")
        load_btn.clicked.connect(self.load_csv)
        sample_btn.clicked.connect(self.load_sample)
        cad_btn.clicked.connect(self.load_cad)
        export_btn.clicked.connect(self.export_excel)
        toolbar.addWidget(load_btn)
        toolbar.addWidget(sample_btn)
        toolbar.addWidget(cad_btn)
        toolbar.addWidget(export_btn)
        toolbar.addStretch(1)
        root_layout.addLayout(toolbar)

        root_layout.addWidget(self._build_kpi_box())

        self.asset_table.setMinimumHeight(340)
        self.factor_table.setMinimumHeight(170)
        self.failure_canvas.setMinimumHeight(300)
        self.downtime_canvas.setMinimumHeight(300)
        self.cad_canvas.setMinimumHeight(280)

        content = QGridLayout()
        content.setHorizontalSpacing(12)
        content.setVerticalSpacing(12)
        content.addWidget(self._wrap_widget("Asset Risk Ranking", self.asset_table), 0, 0, 2, 1)
        content.addWidget(
            self._wrap_widget("3D CAD Viewer (Units: mm | View: Isometric)", self._build_cad_panel()),
            0,
            1,
        )
        content.addWidget(self._wrap_widget("Factor Importance", self.factor_table), 1, 1)
        content.addWidget(self._wrap_widget("Failures by Mode", self.failure_canvas), 2, 0)
        content.addWidget(self._wrap_widget("Downtime by Asset (Top 10)", self.downtime_canvas), 2, 1)
        content.setColumnStretch(0, 3)
        content.setColumnStretch(1, 2)
        content.setRowStretch(0, 2)
        content.setRowStretch(1, 1)
        content.setRowStretch(2, 4)
        root_layout.addLayout(content)

        self.setCentralWidget(root)
        self._draw_cad_placeholder("CAD model not loaded")

    def _build_kpi_box(self) -> QGroupBox:
        box = QGroupBox("Plant Reliability Snapshot")
        layout = QGridLayout(box)
        layout.setHorizontalSpacing(18)
        layout.setVerticalSpacing(6)
        names = {
            "total_failures": "Total Failures",
            "total_downtime_hours": "Downtime (hrs)",
            "mttr_hours": "MTTR (hrs)",
            "mtbf_hours": "MTBF (hrs)",
            "availability_pct": "Availability (%)",
        }
        for i, (key, title) in enumerate(names.items()):
            name_label = QLabel(title)
            name_label.setStyleSheet("color: #294861; font-size: 12px; font-weight: 600;")
            value_label = QLabel("-")
            value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            value_label.setStyleSheet("font-size: 20px; font-weight: 700; color: #113355;")
            layout.addWidget(name_label, 0, i)
            layout.addWidget(value_label, 1, i)
            self.kpi_labels[key] = value_label
        return box

    def _wrap_widget(self, title: str, widget: QWidget) -> QGroupBox:
        box = QGroupBox(title)
        layout = QVBoxLayout(box)
        layout.addWidget(widget)
        return box

    def _build_cad_panel(self) -> QWidget:
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self.cad_canvas)
        layout.addWidget(self.cad_info_label)
        return wrapper

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

    def load_cad(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select CAD Model",
            "",
            "OBJ Files (*.obj);;All Files (*.*)",
        )
        if path:
            self._load_cad_path(Path(path))

    def _try_load_default_cad(self) -> None:
        if self.DEFAULT_CAD_PATH.exists():
            self._load_cad_path(self.DEFAULT_CAD_PATH)
        else:
            self.statusBar().showMessage("Ready | Default CAD model not found")

    def _load_cad_path(self, path: Path) -> None:
        try:
            self.statusBar().showMessage(f"Loading CAD: {path.name}")
            vertices, faces, source_face_count = self._read_obj_mesh(path, max_faces=35000)
            self._draw_cad_mesh(vertices, faces)
            self.current_cad_path = path
            self.cad_info_label.setText(
                (
                    f"File: {path.name} | Units: mm | View: isometric | "
                    f"Vertices: {len(vertices):,} | Faces shown: {len(faces):,} / {source_face_count:,}"
                )
            )
            self.statusBar().showMessage(f"Loaded CAD: {path.name}")
        except Exception as exc:  # pragma: no cover - UI boundary
            self._draw_cad_placeholder("CAD load failed")
            self.cad_info_label.setText(f"Failed to load CAD: {path.name}")
            QMessageBox.critical(self, "CAD load error", str(exc))
            self.statusBar().showMessage("CAD load failed")

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
        table.setSortingEnabled(False)
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

        table.setAlternatingRowColors(True)
        table.setWordWrap(False)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(26)
        header = table.horizontalHeader()
        header.setStretchLastSection(True)
        if frame.shape[1] <= 8:
            header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        else:
            header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        table.setSortingEnabled(True)

    def _draw_failure_modes(self, frame: pd.DataFrame) -> None:
        self.failure_fig.clear()
        ax = self.failure_fig.add_subplot(111)
        if frame.empty:
            ax.axis("off")
            ax.text(0.5, 0.5, "No failure mode data", ha="center", va="center", transform=ax.transAxes)
            self.failure_canvas.draw()
            return
        top = frame.head(8).copy()
        ax.barh(top["failure_mode"], top["failures"], color="#0B5FA5", height=0.68)
        ax.invert_yaxis()
        ax.set_xlabel("Failure Count", fontsize=11, labelpad=8)
        ax.set_ylabel("Failure Mode", fontsize=11, labelpad=8)
        ax.tick_params(axis="both", labelsize=10)
        ax.grid(axis="x", linestyle="--", alpha=0.28)
        ax.margins(y=0.12)
        self.failure_canvas.draw()

    def _draw_downtime_by_asset(self, frame: pd.DataFrame) -> None:
        self.downtime_fig.clear()
        ax = self.downtime_fig.add_subplot(111)
        if frame.empty:
            ax.axis("off")
            ax.text(0.5, 0.5, "No downtime data", ha="center", va="center", transform=ax.transAxes)
            self.downtime_canvas.draw()
            return
        top = frame.sort_values("downtime_hours", ascending=False).head(10).copy()
        ax.bar(top["asset_id"], top["downtime_hours"], color="#0E9C68", width=0.68)
        ax.set_ylabel("Downtime (hrs)", fontsize=11, labelpad=8)
        ax.set_xlabel("Asset", fontsize=11, labelpad=8)
        ax.tick_params(axis="y", labelsize=10)
        ax.tick_params(axis="x", labelsize=10, rotation=28)
        for label in ax.get_xticklabels():
            label.set_horizontalalignment("right")
        ax.grid(axis="y", linestyle="--", alpha=0.28)
        ax.margins(x=0.03)
        self.downtime_canvas.draw()

    def _draw_cad_placeholder(self, text: str) -> None:
        self.cad_fig.clear()
        ax = self.cad_fig.add_subplot(111)
        ax.axis("off")
        ax.text(
            0.5,
            0.5,
            text,
            ha="center",
            va="center",
            fontsize=12,
            color="#32506D",
            transform=ax.transAxes,
        )
        self.cad_canvas.draw()

    def _draw_cad_mesh(self, vertices: np.ndarray, faces: np.ndarray) -> None:
        self.cad_fig.clear()
        ax = self.cad_fig.add_subplot(111, projection="3d")

        tris = vertices[faces]
        mesh = Poly3DCollection(
            tris,
            facecolor="#8FA8C2",
            edgecolor="#2E4A66",
            linewidths=0.08,
            alpha=1.0,
        )
        ax.add_collection3d(mesh)

        mins = vertices.min(axis=0)
        maxs = vertices.max(axis=0)
        center = (mins + maxs) / 2.0
        max_span = float(np.max(maxs - mins))
        half = max_span / 2.0 if max_span > 0 else 1.0
        ax.set_xlim(center[0] - half, center[0] + half)
        ax.set_ylim(center[1] - half, center[1] + half)
        ax.set_zlim(center[2] - half, center[2] + half)
        ax.set_box_aspect((1, 1, 1))

        # User preference: millimeters + isometric view.
        ax.view_init(elev=35.264, azim=45)
        ax.set_xlabel("X (mm)")
        ax.set_ylabel("Y (mm)")
        ax.set_zlabel("Z (mm)")
        ax.grid(True, alpha=0.25)
        self.cad_canvas.draw()

    def _read_obj_mesh(self, path: Path, max_faces: int = 35000) -> tuple[np.ndarray, np.ndarray, int]:
        vertices: list[tuple[float, float, float]] = []
        all_faces: list[tuple[int, int, int]] = []

        with path.open("r", encoding="utf-8", errors="ignore") as file:
            for raw_line in file:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue

                if line.startswith("v "):
                    parts = line.split()
                    if len(parts) >= 4:
                        try:
                            vertices.append((float(parts[1]), float(parts[2]), float(parts[3])))
                        except ValueError:
                            continue
                    continue

                if not line.startswith("f "):
                    continue

                tokens = line.split()[1:]
                indices: list[int] = []
                for token in tokens:
                    ref = token.split("/")[0]
                    if not ref:
                        continue
                    try:
                        idx = int(ref)
                    except ValueError:
                        continue
                    if idx < 0:
                        idx = len(vertices) + idx
                    else:
                        idx = idx - 1
                    if idx >= 0:
                        indices.append(idx)

                if len(indices) < 3:
                    continue

                for i in range(1, len(indices) - 1):
                    tri = (indices[0], indices[i], indices[i + 1])
                    all_faces.append(tri)

        if not vertices or not all_faces:
            raise ValueError("No valid geometry found in OBJ file.")

        verts_array = np.asarray(vertices, dtype=float)
        faces_array = np.asarray(all_faces, dtype=int)
        valid = np.all((faces_array >= 0) & (faces_array < len(verts_array)), axis=1)
        faces_array = faces_array[valid]
        if len(faces_array) == 0:
            raise ValueError("OBJ face indices are invalid for the parsed vertices.")

        total_faces = len(faces_array)
        if total_faces > max_faces:
            # Evenly subsample across the full face range to preserve full model coverage.
            sample_idx = np.linspace(0, total_faces - 1, num=max_faces, dtype=int)
            faces_array = faces_array[sample_idx]

        return verts_array, faces_array, total_faces

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
