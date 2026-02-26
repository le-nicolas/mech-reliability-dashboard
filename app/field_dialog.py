from __future__ import annotations

from collections.abc import Callable
from datetime import date
from pathlib import Path

import pandas as pd
from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QPageSize, QTextDocument
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDateEdit,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.field_pipeline import (
    DEFECT_LOCATIONS,
    EQUIPMENT_TYPES,
    FAILURE_MODES,
    SEVERITY_LEVELS,
    FieldDefect,
    FieldInspection,
    append_rows_to_csv,
    build_report_html,
    inspection_to_dataframe,
    recommended_action,
    save_html_report,
)
from app.io_utils import project_root


class FieldInspectionDialog(QDialog):
    def __init__(
        self,
        parent: QWidget | None = None,
        on_commit: Callable[[pd.DataFrame, str], None] | None = None,
        logo_path: Path | None = None,
        csv_sink: Path | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Field Inspection Pipeline")
        self.resize(1100, 830)
        self.setMinimumSize(980, 720)

        self.on_commit = on_commit
        self.logo_path = logo_path
        self.csv_sink = csv_sink or (project_root() / "sample_data" / "field_inspection_log.csv")
        self.reports_dir = project_root() / "reports"
        self.defects: list[FieldDefect] = []

        self._build_ui()
        self._apply_styles()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 12)
        root.setSpacing(10)

        info = QLabel(
            "Capture field defects, auto-generate a print-ready report, then push rows into the reliability analytics dataset."
        )
        info.setWordWrap(True)
        info.setObjectName("hint")
        root.addWidget(info)

        hdr_group = QGroupBox("Inspection Header")
        hdr_layout = QFormLayout(hdr_group)
        hdr_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        hdr_layout.setHorizontalSpacing(12)
        hdr_layout.setVerticalSpacing(8)

        self.company_edit = QLineEdit("Mechanical Reliability Services, Inc.")
        self.tagline_edit = QLineEdit("providing excellence in engineering works")
        self.project_edit = QLineEdit("Field Reliability Inspection")
        self.equipment_combo = QComboBox()
        self.equipment_combo.addItems(EQUIPMENT_TYPES)
        self.asset_edit = QLineEdit()
        self.asset_edit.setPlaceholderText("Example: SCR-213")
        self.location_edit = QLineEdit()
        self.location_edit.setPlaceholderText("Plant / Line / Area")
        self.inspector_edit = QLineEdit()
        self.inspector_edit.setPlaceholderText("Inspector Name")
        self.owner_edit = QLineEdit("Mechanical Reliability Team")
        self.shift_combo = QComboBox()
        self.shift_combo.addItems(["Field", "Day", "Night"])
        self.date_edit = QDateEdit(QDate.currentDate())
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("dd MMM yyyy")

        grid = QGridLayout()
        grid.addWidget(QLabel("Company"), 0, 0)
        grid.addWidget(self.company_edit, 0, 1)
        grid.addWidget(QLabel("Tagline"), 0, 2)
        grid.addWidget(self.tagline_edit, 0, 3)
        grid.addWidget(QLabel("Project"), 1, 0)
        grid.addWidget(self.project_edit, 1, 1)
        grid.addWidget(QLabel("Owner"), 1, 2)
        grid.addWidget(self.owner_edit, 1, 3)
        grid.addWidget(QLabel("Equipment"), 2, 0)
        grid.addWidget(self.equipment_combo, 2, 1)
        grid.addWidget(QLabel("Asset ID"), 2, 2)
        grid.addWidget(self.asset_edit, 2, 3)
        grid.addWidget(QLabel("Location"), 3, 0)
        grid.addWidget(self.location_edit, 3, 1)
        grid.addWidget(QLabel("Inspector"), 3, 2)
        grid.addWidget(self.inspector_edit, 3, 3)
        grid.addWidget(QLabel("Shift"), 4, 0)
        grid.addWidget(self.shift_combo, 4, 1)
        grid.addWidget(QLabel("Date"), 4, 2)
        grid.addWidget(self.date_edit, 4, 3)
        hdr_layout.addRow(grid)
        root.addWidget(hdr_group)

        defect_group = QGroupBox("Defect Input")
        defect_layout = QVBoxLayout(defect_group)
        form_grid = QGridLayout()
        form_grid.setHorizontalSpacing(10)
        form_grid.setVerticalSpacing(8)

        self.mode_combo = QComboBox()
        self.mode_combo.setEditable(True)
        self.mode_combo.addItems(FAILURE_MODES)
        self.severity_combo = QComboBox()
        self.severity_combo.addItems(SEVERITY_LEVELS)
        self.location_combo = QComboBox()
        self.location_combo.setEditable(True)
        self.location_combo.addItems(DEFECT_LOCATIONS)
        self.caption_edit = QLineEdit()
        self.caption_edit.setPlaceholderText("Picture caption (optional)")
        self.photo_edit = QLineEdit()
        self.photo_edit.setPlaceholderText("Optional photo path")
        self.photo_browse_btn = QPushButton("Browse Photo")
        self.photo_browse_btn.clicked.connect(self._browse_photo)
        self.notes_edit = QTextEdit()
        self.notes_edit.setPlaceholderText("Inspection notes")
        self.notes_edit.setMinimumHeight(72)

        form_grid.addWidget(QLabel("Failure mode"), 0, 0)
        form_grid.addWidget(self.mode_combo, 0, 1)
        form_grid.addWidget(QLabel("Severity"), 0, 2)
        form_grid.addWidget(self.severity_combo, 0, 3)
        form_grid.addWidget(QLabel("Equipment location"), 1, 0)
        form_grid.addWidget(self.location_combo, 1, 1)
        form_grid.addWidget(QLabel("Picture caption"), 1, 2)
        form_grid.addWidget(self.caption_edit, 1, 3)
        form_grid.addWidget(QLabel("Photo"), 2, 0)
        form_grid.addWidget(self.photo_edit, 2, 1, 1, 2)
        form_grid.addWidget(self.photo_browse_btn, 2, 3)
        defect_layout.addLayout(form_grid)
        defect_layout.addWidget(self.notes_edit)

        action_row = QHBoxLayout()
        self.add_btn = QPushButton("Add Defect")
        self.remove_btn = QPushButton("Remove Selected")
        self.add_btn.clicked.connect(self._add_defect)
        self.remove_btn.clicked.connect(self._remove_defect)
        action_row.addWidget(self.add_btn)
        action_row.addWidget(self.remove_btn)
        action_row.addStretch(1)
        defect_layout.addLayout(action_row)

        self.defect_tbl = QTableWidget()
        self.defect_tbl.setColumnCount(8)
        self.defect_tbl.setHorizontalHeaderLabels(
            ["#", "Failure Mode", "Severity", "Location", "Caption", "Notes", "Photo", "Action"]
        )
        self.defect_tbl.setAlternatingRowColors(True)
        self.defect_tbl.verticalHeader().setVisible(False)
        self.defect_tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.defect_tbl.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.defect_tbl.horizontalHeader().setStretchLastSection(True)
        for i in range(7):
            self.defect_tbl.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
        defect_layout.addWidget(self.defect_tbl)
        root.addWidget(defect_group, 1)

        output_group = QGroupBox("Output")
        output_layout = QVBoxLayout(output_group)
        self.csv_path_lbl = QLabel(f"CSV sink: {self.csv_sink}")
        self.csv_path_lbl.setObjectName("hint")
        output_layout.addWidget(self.csv_path_lbl)
        output_btn_row = QHBoxLayout()
        self.report_btn = QPushButton("Generate Print Report")
        self.save_btn = QPushButton("Save Inspection to Analytics")
        self.close_btn = QPushButton("Close")
        self.report_btn.clicked.connect(self._generate_report)
        self.save_btn.clicked.connect(self._save_to_analytics)
        self.close_btn.clicked.connect(self.close)
        output_btn_row.addWidget(self.report_btn)
        output_btn_row.addWidget(self.save_btn)
        output_btn_row.addStretch(1)
        output_btn_row.addWidget(self.close_btn)
        output_layout.addLayout(output_btn_row)
        root.addWidget(output_group)

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QDialog { background: #f3efe4; color: #1f1f1f; }
            QGroupBox { background: #fffdf7; border: 1px solid #8d8678; margin-top: 10px; font-size: 10pt; font-weight: 600; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
            QLineEdit, QComboBox, QDateEdit, QTextEdit {
                background: #ffffff;
                border: 1px solid #9a927f;
                padding: 4px;
                font-size: 9.5pt;
            }
            QPushButton {
                background: #2b2b2b;
                color: #f8f8f8;
                border: 1px solid #4b4b4b;
                border-radius: 3px;
                padding: 6px 10px;
                min-width: 118px;
                font-weight: 600;
            }
            QPushButton:hover { background: #3a3a3a; }
            QTableWidget {
                background: #ffffff;
                alternate-background-color: #f5f1e5;
                border: 1px solid #8d8678;
                gridline-color: #8d8678;
                selection-background-color: #f5dc66;
                selection-color: #1d1d1d;
            }
            QHeaderView::section {
                background: #ece2c2;
                border: 1px solid #8d8678;
                padding: 4px;
                font-weight: 700;
            }
            QLabel#hint { color: #3f3a30; font-size: 9pt; }
            """
        )

    def _browse_photo(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select defect photo",
            str(Path.home()),
            "Images (*.png *.jpg *.jpeg *.bmp *.webp);;All files (*.*)",
        )
        if path:
            self.photo_edit.setText(path)

    def _add_defect(self) -> None:
        mode = self.mode_combo.currentText().strip()
        severity = self.severity_combo.currentText().strip()
        location = self.location_combo.currentText().strip()
        caption = self.caption_edit.text().strip()
        notes = self.notes_edit.toPlainText().strip()
        photo = self.photo_edit.text().strip()

        if not mode:
            QMessageBox.warning(self, "Missing Field", "Failure mode is required.")
            return
        if not severity:
            QMessageBox.warning(self, "Missing Field", "Severity is required.")
            return
        if not location:
            location = "Other"

        self.defects.append(
            FieldDefect(
                failure_mode=mode,
                severity=severity,
                location=location,
                notes=notes,
                photo_path=photo,
                caption=caption,
            )
        )
        self._refresh_defect_table()
        self.caption_edit.clear()
        self.notes_edit.clear()
        self.photo_edit.clear()
        self.mode_combo.setFocus()

    def _remove_defect(self) -> None:
        row = self.defect_tbl.currentRow()
        if row < 0 or row >= len(self.defects):
            return
        self.defects.pop(row)
        self._refresh_defect_table()

    def _refresh_defect_table(self) -> None:
        self.defect_tbl.setRowCount(len(self.defects))
        for idx, defect in enumerate(self.defects, start=1):
            values = [
                idx,
                defect.failure_mode,
                defect.severity,
                defect.location,
                defect.caption or "-",
                defect.notes or "-",
                Path(defect.photo_path).name if defect.photo_path else "-",
                recommended_action(defect.failure_mode),
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if col == 0:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if defect.severity in {"Critical", "High"}:
                    item.setBackground(Qt.GlobalColor.yellow)
                self.defect_tbl.setItem(idx - 1, col, item)

    def _build_inspection(self) -> FieldInspection | None:
        asset_id = self.asset_edit.text().strip()
        if not asset_id:
            QMessageBox.warning(self, "Missing Field", "Asset ID is required.")
            return None
        if not self.defects:
            QMessageBox.warning(self, "No Defects", "Add at least one defect entry.")
            return None

        inspection_date = self.date_edit.date().toPython()
        if not isinstance(inspection_date, date):
            inspection_date = date.today()

        return FieldInspection(
            equipment_type=self.equipment_combo.currentText().strip() or "Unknown",
            asset_id=asset_id,
            site_location=self.location_edit.text().strip(),
            inspector=self.inspector_edit.text().strip(),
            inspection_date=inspection_date,
            shift=self.shift_combo.currentText().strip() or "Field",
            project_title=self.project_edit.text().strip(),
            company_name=self.company_edit.text().strip() or "Mechanical Reliability Services, Inc.",
            company_tagline=self.tagline_edit.text().strip() or "providing excellence in engineering works",
            owner=self.owner_edit.text().strip() or "Mechanical Reliability Team",
            defects=list(self.defects),
        )

    def _safe_stem(self, text: str, fallback: str) -> str:
        clean = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in text).strip("_")
        return clean or fallback

    def _generate_report(self) -> None:
        inspection = self._build_inspection()
        if inspection is None:
            return

        self.reports_dir.mkdir(parents=True, exist_ok=True)
        stem = f"inspection_{self._safe_stem(inspection.asset_id, 'asset')}_{inspection.inspection_date:%Y%m%d}"
        html_default = self.reports_dir / f"{stem}.html"
        out_html, _ = QFileDialog.getSaveFileName(
            self,
            "Save inspection report",
            str(html_default),
            "HTML report (*.html)",
        )
        if not out_html:
            return

        html_path = Path(out_html)
        html = build_report_html(inspection, logo_path=self.logo_path)
        try:
            save_html_report(html, html_path)
        except Exception as exc:
            QMessageBox.critical(self, "Report Save Failed", str(exc))
            return

        pdf_path = html_path.with_suffix(".pdf")
        pdf_ok = self._save_pdf(html, pdf_path)
        msg = f"Report saved:\n{html_path}"
        if pdf_ok:
            msg += f"\n\nPDF saved:\n{pdf_path}"
        else:
            msg += "\n\nPDF export was skipped (HTML remains print-ready)."
        QMessageBox.information(self, "Report Generated", msg)

    def _save_pdf(self, html: str, output_pdf: Path) -> bool:
        try:
            output_pdf.parent.mkdir(parents=True, exist_ok=True)
            doc = QTextDocument()
            doc.setHtml(html)

            printer = QPrinter(QPrinter.PrinterMode.HighResolution)
            printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
            printer.setOutputFileName(str(output_pdf))
            printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))

            doc.print_(printer)
            return output_pdf.exists()
        except Exception:
            return False

    def _save_to_analytics(self) -> None:
        inspection = self._build_inspection()
        if inspection is None:
            return

        rows = inspection_to_dataframe(inspection)
        if rows.empty:
            QMessageBox.warning(self, "No Rows", "No rows generated from current inspection.")
            return

        try:
            append_rows_to_csv(rows, self.csv_sink)
        except Exception as exc:
            QMessageBox.critical(self, "CSV Write Failed", str(exc))
            return

        source_label = (
            f"field-inspection-{self._safe_stem(inspection.asset_id, 'asset')}-"
            f"{inspection.inspection_date:%Y%m%d}"
        )
        if self.on_commit is not None:
            try:
                self.on_commit(rows, source_label)
            except Exception as exc:
                QMessageBox.critical(
                    self,
                    "Analytics Push Failed",
                    f"Rows were written to CSV but could not be pushed to live analytics.\n\n{exc}",
                )
                return

        QMessageBox.information(
            self,
            "Inspection Saved",
            f"Saved {len(rows)} row(s) to:\n{self.csv_sink}\n\nSource label: {source_label}",
        )
