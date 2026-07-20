"""Batch Analysis panel — two folder pickers, sequential multi-pair analysis."""

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QFileDialog,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QTextEdit,
)
from PyQt6.QtGui import QColor

from core.models import Finding
from services.batch_analysis_service import match_pairs, BatchWorker
from ui.app_theme import SEVERITY_COLORS as _SEVERITY_COLORS


class BatchPanel(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._baseline_dir = ""
        self._current_dir = ""
        self._pairs: list[tuple[str, str]] = []
        self._worker: BatchWorker | None = None
        self._completed = 0
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        self._build_folder_pickers(layout)
        # ── Controls row ──────────────────────────────────────────────────────
        ctrl = QHBoxLayout()
        self._match_lbl = QLabel("Select both folders to begin.")
        self._match_lbl.setStyleSheet(
            "color: #888888; font-size: 11px; background: transparent;"
        )
        ctrl.addWidget(self._match_lbl)
        ctrl.addStretch()
        self._analyze_btn = QPushButton("ANALYZE ALL")
        self._analyze_btn.setObjectName("primaryBtn")
        self._analyze_btn.setEnabled(False)
        self._analyze_btn.clicked.connect(self._on_analyze)
        ctrl.addWidget(self._analyze_btn)
        self._progress_lbl = QLabel("")
        self._progress_lbl.setStyleSheet(
            "color: #888888; font-size: 11px; background: transparent;"
        )
        ctrl.addWidget(self._progress_lbl)
        layout.addLayout(ctrl)

        # ── Unmatched warning ─────────────────────────────────────────────────
        self._unmatched_lbl = QLabel("")
        self._unmatched_lbl.setWordWrap(True)
        self._unmatched_lbl.setStyleSheet(
            "color: #e3b341; background: transparent; font-size: 11px;"
        )
        self._unmatched_lbl.hide()
        layout.addWidget(self._unmatched_lbl)

        self._build_results_area(layout)

    def _build_folder_pickers(self, layout: QVBoxLayout) -> None:
        # ── Folder pickers ────────────────────────────────────────────────────
        b_row = QHBoxLayout()
        b_lbl = QLabel("BASELINE FOLDER")
        b_lbl.setFixedWidth(140)
        b_lbl.setStyleSheet(
            "color: #2ea043; font-size: 11px; font-weight: bold; "
            "letter-spacing: 1px; background: transparent;"
        )
        b_row.addWidget(b_lbl)
        self._baseline_edit = QLineEdit()
        self._baseline_edit.setReadOnly(True)
        self._baseline_edit.setPlaceholderText("Select baseline folder…")
        b_row.addWidget(self._baseline_edit, 1)
        b_browse = QPushButton("Browse…")
        b_browse.clicked.connect(self._browse_baseline)
        b_row.addWidget(b_browse)
        layout.addLayout(b_row)

        c_row = QHBoxLayout()
        c_lbl = QLabel("CURRENT FOLDER")
        c_lbl.setFixedWidth(140)
        c_lbl.setStyleSheet(
            "color: #C41200; font-size: 11px; font-weight: bold; "
            "letter-spacing: 1px; background: transparent;"
        )
        c_row.addWidget(c_lbl)
        self._current_edit = QLineEdit()
        self._current_edit.setReadOnly(True)
        self._current_edit.setPlaceholderText("Select current / degraded folder…")
        c_row.addWidget(self._current_edit, 1)
        c_browse = QPushButton("Browse…")
        c_browse.clicked.connect(self._browse_current)
        c_row.addWidget(c_browse)
        layout.addLayout(c_row)

    def _build_results_area(self, layout: QVBoxLayout) -> None:
        # ── Findings table ────────────────────────────────────────────────────
        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["Severity", "File Pair", "Finding"])
        hdr = self._table.horizontalHeader()
        assert hdr is not None
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        layout.addWidget(self._table, 1)

        # ── AI batch summary ──────────────────────────────────────────────────
        self._summary_lbl = QLabel("AI Batch Summary")
        self._summary_lbl.setStyleSheet(
            "color: #C41200; font-weight: bold; font-size: 12px; background: transparent;"
        )
        self._summary_lbl.hide()
        layout.addWidget(self._summary_lbl)

        self._summary_text = QTextEdit()
        self._summary_text.setReadOnly(True)
        self._summary_text.setFixedHeight(120)
        self._summary_text.hide()
        layout.addWidget(self._summary_text)

    # ── Folder browsing ───────────────────────────────────────────────────────

    def _browse_baseline(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Select Baseline Folder")
        if d:
            self._baseline_dir = d
            self._baseline_edit.setText(d)
            self._scan_pairs()

    def _browse_current(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Select Current Folder")
        if d:
            self._current_dir = d
            self._current_edit.setText(d)
            self._scan_pairs()

    def _scan_pairs(self) -> None:
        if not self._baseline_dir or not self._current_dir:
            return
        self._pairs, unmatched = match_pairs(self._baseline_dir, self._current_dir)
        n = len(self._pairs)
        self._match_lbl.setText(f"Matched pairs: {n}    Unmatched: {len(unmatched)}")
        self._analyze_btn.setEnabled(n > 0)
        if unmatched:
            self._unmatched_lbl.setText(f"⚠ Unmatched files: {', '.join(unmatched)}")
            self._unmatched_lbl.show()
        else:
            self._unmatched_lbl.hide()

    # ── Analysis ──────────────────────────────────────────────────────────────

    def _on_analyze(self) -> None:
        self._analyze_btn.setEnabled(False)
        self._table.setRowCount(0)
        self._summary_lbl.hide()
        self._summary_text.hide()
        self._completed = 0
        self._progress_lbl.setText(f"0 / {len(self._pairs)}")

        self._worker = BatchWorker(self._pairs)
        self._worker.pair_done.connect(self._on_pair_done)
        self._worker.pair_error.connect(self._on_pair_error)
        self._worker.batch_done.connect(self._on_batch_done)
        self._worker.start()

    def _on_pair_done(self, index: int, filename: str, findings: list[Finding]) -> None:
        self._completed += 1
        self._progress_lbl.setText(f"{self._completed} / {len(self._pairs)}")
        for f in findings:
            self._add_row(f.severity, filename, f.title)

    def _on_pair_error(self, index: int, filename: str, error_msg: str) -> None:
        self._completed += 1
        self._progress_lbl.setText(f"{self._completed} / {len(self._pairs)}")
        self._add_row("ERROR", filename, f"Error: {error_msg[:120]}")

    def _on_batch_done(self, summary: str) -> None:
        self._analyze_btn.setEnabled(True)
        self._progress_lbl.setText(f"Done — {len(self._pairs)} pair(s) analyzed")
        if summary:
            self._summary_text.setPlainText(summary)
            self._summary_lbl.show()
            self._summary_text.show()

    def _add_row(self, severity: str, filename: str, title: str) -> None:
        row = self._table.rowCount()
        self._table.insertRow(row)
        sev_item = QTableWidgetItem(severity)
        sev_item.setForeground(QColor(_SEVERITY_COLORS.get(severity, "#888888")))
        self._table.setItem(row, 0, sev_item)
        self._table.setItem(row, 1, QTableWidgetItem(filename))
        self._table.setItem(row, 2, QTableWidgetItem(title))
