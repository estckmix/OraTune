"""Top SQL Dashboard tab."""

from typing import TYPE_CHECKING, Callable

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QComboBox,
    QPushButton,
    QSplitter,
    QPlainTextEdit,
    QHeaderView,
    QFrame,
)
from PyQt6.QtCore import Qt

from services.db_service import OracleConnection, OracleRow
from services.top_sql_service import fetch_top_sql
from ui.widgets.live import LiveWorker

if TYPE_CHECKING:
    from ui.widgets.live.awr_trend_tab import AwrTrendTab
    from ui.widgets.live.explain_plan_tab import ExplainPlanTab


_COLS = [
    "Rank",
    "SQL ID",
    "Elapsed(s)",
    "Elapsed/Exec",
    "CPU%",
    "Buffer Gets",
    "Disk Reads",
    "Executions",
    "Module",
    "SQL Text",
]


class TopSqlTab(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._conn: OracleConnection | None = None
        self._worker: LiveWorker | None = None
        self._rows: list[OracleRow] = []
        self._explain_tab: ExplainPlanTab | None = None
        self._switch_to_explain: Callable[[], None] | None = None
        self._trend_tab: AwrTrendTab | None = None
        self._switch_to_trend: Callable[[], None] | None = None
        self._build_ui()

    def set_conn(self, conn: OracleConnection) -> None:
        self._conn = conn

    def set_explain_tab(
        self,
        tab: "ExplainPlanTab",
        switch_callback: Callable[[], None] | None = None,
    ) -> None:
        """Link to ExplainPlanTab so row click can pre-populate it and switch to it."""
        self._explain_tab = tab
        self._switch_to_explain = switch_callback

    def set_trend_tab(
        self, tab: "AwrTrendTab", switch_callback: Callable[[], None]
    ) -> None:
        """Link to AwrTrendTab; switch_callback navigates the live tab widget."""
        self._trend_tab = tab
        self._switch_to_trend = switch_callback

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        bar = QHBoxLayout()
        bar.addWidget(QLabel("Time range:"))
        self._range_combo = QComboBox()
        self._range_combo.addItems(["1h", "6h", "24h", "7d"])
        self._range_combo.setCurrentIndex(2)
        bar.addWidget(self._range_combo)
        bar.addWidget(QLabel("Sort by:"))
        self._sort_combo = QComboBox()
        self._sort_combo.addItems(
            ["elapsed", "cpu", "buffer_gets", "disk_reads", "executions"]
        )
        bar.addWidget(self._sort_combo)
        bar.addWidget(QLabel("Rows:"))
        self._limit_combo = QComboBox()
        self._limit_combo.addItems(["25", "50", "100"])
        bar.addWidget(self._limit_combo)
        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.setObjectName("primaryBtn")
        bar.addWidget(self._refresh_btn)
        self._source_lbl = QLabel("")
        bar.addWidget(self._source_lbl)
        bar.addStretch()
        layout.addLayout(bar)

        splitter = QSplitter(Qt.Orientation.Vertical)

        self._table = QTableWidget(0, len(_COLS))
        self._table.setHorizontalHeaderLabels(_COLS)
        table_header = self._table.horizontalHeader()
        assert table_header is not None
        table_header.setSectionResizeMode(
            len(_COLS) - 1, QHeaderView.ResizeMode.Stretch
        )
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        splitter.addWidget(self._table)

        splitter.addWidget(self._build_detail_pane())
        splitter.setSizes([400, 150])
        layout.addWidget(splitter, 1)

        self._refresh_btn.clicked.connect(self._on_refresh)
        self._table.currentCellChanged.connect(self._on_row_changed)
        self._explain_btn.clicked.connect(self._on_explain)
        self._trend_btn.clicked.connect(self._on_show_trend)

    def _build_detail_pane(self) -> QFrame:
        """SQL text viewer plus the explain/trend navigation buttons."""
        detail = QFrame()
        dl = QVBoxLayout(detail)
        dl.setContentsMargins(0, 4, 0, 0)
        lbl = QLabel("SQL TEXT")
        lbl.setObjectName("dimLabel")
        dl.addWidget(lbl)
        self._detail_text = QPlainTextEdit()
        self._detail_text.setReadOnly(True)
        dl.addWidget(self._detail_text)
        self._explain_btn = QPushButton("Open in Explain Plan tab →")
        dl.addWidget(self._explain_btn)
        self._trend_btn = QPushButton("Show Trend →")
        dl.addWidget(self._trend_btn)
        return detail

    def _on_refresh(self) -> None:
        if self._conn is None:
            return
        self._refresh_btn.setEnabled(False)
        self._source_lbl.setText("Loading…")
        self._worker = LiveWorker(
            fetch_top_sql,
            self._conn,
            sort_by=self._sort_combo.currentText(),
            time_range=self._range_combo.currentText(),
            limit=int(self._limit_combo.currentText()),
        )
        self._worker.finished.connect(self._on_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_done(self, result: tuple[list[OracleRow], str]) -> None:
        rows, source = result
        self._rows = rows
        self._refresh_btn.setEnabled(True)
        self._source_lbl.setText(f"Source: {'AWR' if source == 'awr' else 'V$SQL'}")
        self._table.setRowCount(0)
        for i, r in enumerate(rows):
            self._table.insertRow(i)
            vals: list[str] = [
                str(i + 1),
                r.get("sql_id", ""),
                str(r.get("elapsed_total_sec", "")),
                str(r.get("elapsed_per_exec_sec", "")),
                str(r.get("cpu_pct", "")),
                str(r.get("buffer_gets", "")),
                str(r.get("disk_reads", "")),
                str(r.get("executions", "")),
                r.get("module", ""),
                (r.get("sql_text") or "")[:80],
            ]
            for j, v in enumerate(vals):
                self._table.setItem(i, j, QTableWidgetItem(v))

    def _on_error(self, msg: str) -> None:
        self._refresh_btn.setEnabled(True)
        self._source_lbl.setText(f"Error: {msg[:60]}")

    def _on_row_changed(self, row: int, *_: int) -> None:
        if 0 <= row < len(self._rows):
            self._detail_text.setPlainText(self._rows[row].get("sql_text", ""))

    def _on_explain(self) -> None:
        if self._explain_tab is None:
            return
        row = self._table.currentRow()
        if 0 <= row < len(self._rows):
            self._explain_tab.set_sql(self._rows[row].get("sql_text", ""))
            if self._switch_to_explain:
                self._switch_to_explain()

    def _on_show_trend(self) -> None:
        if self._trend_tab is None:
            return
        row = self._table.currentRow()
        if 0 <= row < len(self._rows):
            sql_id = self._rows[row].get("sql_id", "")
            if sql_id:
                self._trend_tab.set_sql_id(sql_id)
                if self._switch_to_trend:
                    self._switch_to_trend()
