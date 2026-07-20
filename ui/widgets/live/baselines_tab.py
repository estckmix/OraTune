"""SQL Plan Baseline Manager tab."""

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QInputDialog,
    QMessageBox,
)

from services.db_service import OracleConnection, OracleRow
from services.baselines_service import (
    list_baselines,
    alter_baseline,
    drop_baseline,
    promote_from_cursor,
)
from ui.widgets.live import LiveWorker

_COLS = [
    "SQL Handle",
    "Plan Name",
    "SQL Text",
    "Enabled",
    "Accepted",
    "Fixed",
    "Origin",
    "Created",
]


class BaselinesTab(QWidget):
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
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        bar = QHBoxLayout()
        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.setObjectName("primaryBtn")
        self._promote_btn = QPushButton("Promote from Cursor Cache…")
        self._enable_btn = QPushButton("Enable")
        self._disable_btn = QPushButton("Disable")
        self._drop_btn = QPushButton("Drop")
        self._status_lbl = QLabel("")
        for w in [
            self._refresh_btn,
            self._promote_btn,
            self._enable_btn,
            self._disable_btn,
            self._drop_btn,
        ]:
            bar.addWidget(w)
        bar.addWidget(self._status_lbl)
        bar.addStretch()
        layout.addLayout(bar)

        self._priv_lbl = QLabel("")
        self._priv_lbl.setWordWrap(True)
        self._priv_lbl.hide()
        layout.addWidget(self._priv_lbl)

        self._table = QTableWidget(0, len(_COLS))
        self._table.setHorizontalHeaderLabels(_COLS)
        table_header = self._table.horizontalHeader()
        assert table_header is not None
        table_header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        layout.addWidget(self._table, 1)

        self._refresh_btn.clicked.connect(self._on_refresh)
        self._promote_btn.clicked.connect(self._on_promote)
        self._enable_btn.clicked.connect(lambda: self._alter_selected("enabled", "YES"))
        self._disable_btn.clicked.connect(lambda: self._alter_selected("enabled", "NO"))
        self._drop_btn.clicked.connect(self._on_drop)

    def _on_refresh(self) -> None:
        if self._conn is None:
            return
        self._refresh_btn.setEnabled(False)
        self._worker = LiveWorker(list_baselines, self._conn)
        self._worker.finished.connect(self._on_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_done(self, rows: list[OracleRow]) -> None:
        self._rows = rows
        self._refresh_btn.setEnabled(True)
        self._status_lbl.setText(f"{len(rows)} baseline(s)")
        self._table.setRowCount(0)
        for i, r in enumerate(rows):
            self._table.insertRow(i)
            vals: list[str] = [
                r.get("sql_handle", ""),
                r.get("plan_name", ""),
                (r.get("sql_text") or "")[:60],
                r.get("enabled", ""),
                r.get("accepted", ""),
                r.get("fixed", ""),
                r.get("origin", ""),
                str(r.get("created", "")),
            ]
            for j, v in enumerate(vals):
                self._table.setItem(i, j, QTableWidgetItem(v))

    def _on_error(self, msg: str) -> None:
        self._refresh_btn.setEnabled(True)
        if (
            "ADMINISTER SQL MANAGEMENT OBJECT" in msg
            or "insufficient privileges" in msg.lower()
        ):
            self._priv_lbl.setText(
                "⚠ Privilege required: ADMINISTER SQL MANAGEMENT OBJECT — ask your DBA."
            )
            self._priv_lbl.setStyleSheet("color: #e3b341; background: transparent;")
            self._priv_lbl.show()
        else:
            self._status_lbl.setText(f"Error: {msg[:80]}")

    def _selected_row(self) -> OracleRow | None:
        row = self._table.currentRow()
        return self._rows[row] if 0 <= row < len(self._rows) else None

    def _alter_selected(self, attribute: str, value: str) -> None:
        r = self._selected_row()
        if r is None or self._conn is None:
            return
        try:
            n = alter_baseline(
                self._conn, r["sql_handle"], r["plan_name"], attribute, value
            )
            self._status_lbl.setText(f"Modified {n} plan(s)")
            self._on_refresh()
        except Exception as e:
            self._on_error(str(e))

    def _on_drop(self) -> None:
        r = self._selected_row()
        if r is None or self._conn is None:
            return
        reply = QMessageBox.question(
            self,
            "Drop Baseline",
            f"Drop baseline '{r['plan_name']}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                drop_baseline(self._conn, r["sql_handle"], r["plan_name"])
                self._on_refresh()
            except Exception as e:
                self._on_error(str(e))

    def _on_promote(self) -> None:
        if self._conn is None:
            return
        sql_id, ok = QInputDialog.getText(
            self, "Promote from Cursor Cache", "Enter SQL ID:"
        )
        if ok and sql_id.strip():
            try:
                n = promote_from_cursor(self._conn, sql_id.strip())
                self._status_lbl.setText(
                    f"Loaded {n} plan(s) for SQL ID {sql_id.strip()}"
                )
                self._on_refresh()
            except Exception as e:
                self._on_error(str(e))
