"""Explain Plan tab — SQL editor + live EXPLAIN PLAN runner."""

import re

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QButtonGroup,
    QSplitter,
    QFrame,
)
from PyQt6.QtCore import Qt

from core.models import PlanNode
from parsers.xplan_parser import parse_xplan_rows
from services.db_service import OracleConnection
from ui.widgets.live import LiveWorker
from ui.widgets.plan_view import PlanTree


_ESTIMATED_FETCH = "SELECT * FROM TABLE(DBMS_XPLAN.DISPLAY())"
_ACTUAL_FETCH = (
    "SELECT * FROM TABLE(DBMS_XPLAN.DISPLAY_CURSOR(FORMAT => 'ALLSTATS LAST'))"
)


class ExplainPlanTab(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._conn: OracleConnection | None = None
        self._worker: LiveWorker | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        bar = QHBoxLayout()
        self._est_radio = QRadioButton("Estimated")
        self._act_radio = QRadioButton("Actual")
        self._est_radio.setChecked(True)
        grp = QButtonGroup(self)
        grp.addButton(self._est_radio)
        grp.addButton(self._act_radio)
        self._run_btn = QPushButton("▶  Run Explain Plan")
        self._run_btn.setObjectName("primaryBtn")
        self._status_lbl = QLabel("")
        bar.addWidget(QLabel("Plan type:"))
        bar.addWidget(self._est_radio)
        bar.addWidget(self._act_radio)
        bar.addSpacing(16)
        bar.addWidget(self._run_btn)
        bar.addWidget(self._status_lbl)
        bar.addStretch()
        layout.addLayout(bar)

        splitter = QSplitter(Qt.Orientation.Vertical)

        editor_frame = QFrame()
        ef = QVBoxLayout(editor_frame)
        ef.setContentsMargins(0, 0, 0, 0)
        ef.addWidget(QLabel("SQL:"))
        self._editor = QPlainTextEdit()
        self._editor.setPlaceholderText("Paste or type your SQL query here…")
        ef.addWidget(self._editor)
        splitter.addWidget(editor_frame)

        self._tree = PlanTree("PLAN", "#79c0ff")
        splitter.addWidget(self._tree)
        splitter.setSizes([200, 400])
        layout.addWidget(splitter, 1)

        self._run_btn.clicked.connect(self._on_run)

    def set_conn(self, conn: OracleConnection) -> None:
        self._conn = conn

    def set_sql(self, sql: str) -> None:
        """Pre-populate the editor (called from Top SQL tab row click)."""
        self._editor.setPlainText(sql)

    def _on_run(self) -> None:
        if self._conn is None:
            return
        sql = self._editor.toPlainText().strip()
        if not sql:
            return
        self._run_btn.setEnabled(False)
        self._status_lbl.setText("Running…")
        estimated = self._est_radio.isChecked()
        self._worker = LiveWorker(self._fetch_plan, sql, estimated)
        self._worker.finished.connect(self._on_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _fetch_plan(self, sql: str, estimated: bool) -> list[PlanNode]:
        conn = self._conn
        if conn is None:
            raise RuntimeError("Not connected")
        # Normalise: unify line endings, strip trailing semicolons/slashes
        clean = sql.strip().replace("\r\n", "\n").replace("\r", "\n")
        clean = clean.rstrip(";").rstrip("/").strip()
        if not clean:
            raise ValueError("SQL is empty")
        if estimated:
            stmt = "EXPLAIN PLAN FOR " + clean
            try:
                conn.execute_ddl(stmt)
            except Exception as e:
                raise RuntimeError(f"{e}  [sent: {clean[:150]!r}]") from None
            rows = conn.execute_query(_ESTIMATED_FETCH)
        else:
            # Replace bind variables with NULL (values not available here)
            clean_exec = re.sub(r":\w+", "NULL", clean)
            # Inject gather_plan_statistics hint so Oracle records actual row counts.
            # DISPLAY_CURSOR(NULL) picks up the last cursor in the session,
            # which only works when SQL is executed directly (not inside PL/SQL).
            upper = clean_exec.lstrip().upper()
            if upper.startswith("SELECT"):
                idx = clean_exec.lower().index("select")
                hinted = (
                    clean_exec[: idx + 6]
                    + " /*+ gather_plan_statistics */"
                    + clean_exec[idx + 6 :]
                )
            else:
                hinted = clean_exec
            try:
                conn.execute_for_plan(hinted)
            except Exception as e:
                raise RuntimeError(f"{e}  [sent: {hinted[:150]!r}]") from None
            rows = conn.execute_query(_ACTUAL_FETCH)
        return parse_xplan_rows(rows)

    def _on_done(self, nodes: list[PlanNode]) -> None:
        self._run_btn.setEnabled(True)
        self._status_lbl.setText(f"{len(nodes)} plan node(s)")
        self._tree.load_plan(nodes)

    def _on_error(self, msg: str) -> None:
        self._run_btn.setEnabled(True)
        self._status_lbl.setText(f"Error: {msg[:300]}")
        self._status_lbl.setToolTip(msg)
