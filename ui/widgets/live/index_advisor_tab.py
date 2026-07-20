"""Index Advisor tab — Unused Indexes and Missing Index Candidates sub-tabs."""

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QComboBox,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QTabWidget,
    QDialog,
    QPlainTextEdit,
    QApplication,
)

from services.db_service import OracleConnection, OracleRow
from services.index_advisor_service import (
    fetch_unused_indexes,
    fetch_missing_index_candidates,
)
from ui.widgets.live import LiveWorker


class _DropScriptDialog(QDialog):
    def __init__(self, script: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("DROP INDEX Script")
        self.resize(500, 300)
        layout = QVBoxLayout(self)
        self._text = QPlainTextEdit(script)
        self._text.setReadOnly(True)
        layout.addWidget(self._text)
        btn_row = QHBoxLayout()
        copy_btn = QPushButton("Copy to Clipboard")
        close_btn = QPushButton("Close")
        btn_row.addWidget(copy_btn)
        btn_row.addStretch()
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)
        copy_btn.clicked.connect(lambda: self._copy_to_clipboard(script))
        close_btn.clicked.connect(self.accept)

    def _copy_to_clipboard(self, script: str) -> None:
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(script)


class _UnusedTab(QWidget):
    _COLS = [
        "Owner",
        "Index Name",
        "Table Name",
        "Type",
        "Unique",
        "Last Used",
        "Accesses",
    ]
    _DAYS = {"7 days": 7, "30 days": 30, "90 days": 90, "180 days": 180}

    def __init__(self) -> None:
        super().__init__()
        self._conn: OracleConnection | None = None
        self._worker: LiveWorker | None = None
        self._rows: list[OracleRow] = []
        self._build_ui()

    def set_conn(self, conn: OracleConnection) -> None:
        self._conn = conn

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(6)

        bar = QHBoxLayout()
        bar.addWidget(QLabel("Not used in last:"))
        self._days_combo = QComboBox()
        self._days_combo.addItems(list(self._DAYS.keys()))
        self._days_combo.setCurrentIndex(1)  # 30 days default
        bar.addWidget(self._days_combo)
        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.setObjectName("primaryBtn")
        bar.addWidget(self._refresh_btn)
        self._drop_btn = QPushButton("Generate DROP Script")
        self._drop_btn.setEnabled(False)
        bar.addWidget(self._drop_btn)
        self._status_lbl = QLabel("")
        bar.addWidget(self._status_lbl)
        bar.addStretch()
        layout.addLayout(bar)

        self._priv_lbl = QLabel("")
        self._priv_lbl.setWordWrap(True)
        self._priv_lbl.hide()
        layout.addWidget(self._priv_lbl)

        self._table = QTableWidget(0, len(self._COLS))
        self._table.setHorizontalHeaderLabels(self._COLS)
        table_header = self._table.horizontalHeader()
        assert table_header is not None
        table_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        layout.addWidget(self._table, 1)

        self._refresh_btn.clicked.connect(self._on_refresh)
        self._drop_btn.clicked.connect(self._on_drop_script)
        self._table.itemSelectionChanged.connect(self._on_selection_changed)

    def _on_selection_changed(self) -> None:
        self._drop_btn.setEnabled(bool(self._table.selectedItems()))

    def _on_refresh(self) -> None:
        if self._conn is None:
            return
        self._refresh_btn.setEnabled(False)
        self._priv_lbl.hide()
        days = self._DAYS[self._days_combo.currentText()]
        self._worker = LiveWorker(fetch_unused_indexes, self._conn, days)
        self._worker.finished.connect(self._on_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_done(self, rows: list[OracleRow]) -> None:
        self._rows = rows
        self._refresh_btn.setEnabled(True)
        self._status_lbl.setText(f"{len(rows)} index(es)")
        self._table.setRowCount(0)
        for i, r in enumerate(rows):
            self._table.insertRow(i)
            for j, v in enumerate(
                [
                    r.get("owner", ""),
                    r.get("index_name", ""),
                    r.get("table_name", ""),
                    r.get("index_type", ""),
                    r.get("uniqueness", ""),
                    str(r.get("last_used") or "Never"),
                    str(r.get("total_access_count", 0)),
                ]
            ):
                self._table.setItem(i, j, QTableWidgetItem(v))

    def _on_error(self, msg: str) -> None:
        self._refresh_btn.setEnabled(True)
        if "ORA-00942" in msg or "insufficient privileges" in msg.lower():
            self._priv_lbl.setText(
                "⚠ Privilege required: SELECT on DBA_INDEX_USAGE — ask your DBA."
            )
            self._priv_lbl.setStyleSheet("color: #e3b341; background: transparent;")
            self._priv_lbl.show()
        else:
            self._status_lbl.setText(f"Error: {msg[:80]}")

    def _on_drop_script(self) -> None:
        selected_rows = sorted({idx.row() for idx in self._table.selectedIndexes()})
        lines = [
            f"DROP INDEX {self._rows[r]['owner']}.{self._rows[r]['index_name']};"
            for r in selected_rows
            if r < len(self._rows)
        ]
        if lines:
            _DropScriptDialog("\n".join(lines), self).exec()


class _MissingTab(QWidget):
    _COLS = [
        "Schema",
        "Table Name",
        "Rows",
        "SQL ID",
        "Elapsed (s)",
        "Filter Predicates",
    ]
    _MIN_ROWS = {
        "1,000": 1_000,
        "10,000": 10_000,
        "100,000": 100_000,
        "1,000,000": 1_000_000,
    }

    def __init__(self) -> None:
        super().__init__()
        self._conn: OracleConnection | None = None
        self._worker: LiveWorker | None = None
        self._rows: list[OracleRow] = []
        self._build_ui()

    def set_conn(self, conn: OracleConnection) -> None:
        self._conn = conn

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(6)

        bar = QHBoxLayout()
        bar.addWidget(QLabel("Min table rows:"))
        self._rows_combo = QComboBox()
        self._rows_combo.addItems(list(self._MIN_ROWS.keys()))
        self._rows_combo.setCurrentIndex(1)  # 10,000 default
        bar.addWidget(self._rows_combo)
        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.setObjectName("primaryBtn")
        bar.addWidget(self._refresh_btn)
        self._status_lbl = QLabel("")
        bar.addWidget(self._status_lbl)
        bar.addStretch()
        layout.addLayout(bar)

        hint = QLabel(
            "⚠ Heuristic suggestions — full table scans on large tables in your "
            "AWR workload. Review before creating indexes."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #e3b341; background: transparent; font-size: 11px;")
        layout.addWidget(hint)

        self._priv_lbl = QLabel("")
        self._priv_lbl.setWordWrap(True)
        self._priv_lbl.hide()
        layout.addWidget(self._priv_lbl)

        self._table = QTableWidget(0, len(self._COLS))
        self._table.setHorizontalHeaderLabels(self._COLS)
        table_header = self._table.horizontalHeader()
        assert table_header is not None
        table_header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        layout.addWidget(self._table, 1)

        self._refresh_btn.clicked.connect(self._on_refresh)

    def _on_refresh(self) -> None:
        if self._conn is None:
            return
        self._refresh_btn.setEnabled(False)
        self._priv_lbl.hide()
        min_rows = self._MIN_ROWS[self._rows_combo.currentText()]
        self._worker = LiveWorker(fetch_missing_index_candidates, self._conn, min_rows)
        self._worker.finished.connect(self._on_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_done(self, rows: list[OracleRow]) -> None:
        self._rows = rows
        self._refresh_btn.setEnabled(True)
        self._status_lbl.setText(f"{len(rows)} candidate(s)")
        self._table.setRowCount(0)
        for i, r in enumerate(rows):
            self._table.insertRow(i)
            for j, v in enumerate(
                [
                    r.get("schema_name", ""),
                    r.get("table_name", ""),
                    f"{r.get('num_rows', 0):,}",
                    r.get("sql_id", ""),
                    str(r.get("elapsed_total_sec", "")),
                    (r.get("filter_predicates") or "")[:200],
                ]
            ):
                self._table.setItem(i, j, QTableWidgetItem(v))

    def _on_error(self, msg: str) -> None:
        self._refresh_btn.setEnabled(True)
        if "ORA-00942" in msg or "insufficient privileges" in msg.lower():
            self._priv_lbl.setText(
                "⚠ Privilege required: SELECT on DBA_HIST_SQL_PLAN / "
                "DBA_HIST_SQLSTAT — ask your DBA."
            )
        else:
            self._priv_lbl.setText(f"⚠ Error: {msg[:200]}")
        self._priv_lbl.setStyleSheet("color: #e3b341; background: transparent;")
        self._priv_lbl.show()


class IndexAdvisorTab(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._unused = _UnusedTab()
        self._missing = _MissingTab()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        tabs = QTabWidget()
        tabs.addTab(self._unused, "Unused Indexes")
        tabs.addTab(self._missing, "Missing Index Candidates")
        layout.addWidget(tabs, 1)

    def set_conn(self, conn: OracleConnection) -> None:
        self._unused.set_conn(conn)
        self._missing.set_conn(conn)
