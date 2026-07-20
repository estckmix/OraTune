"""DBMS_SCHEDULER Monitor tab — Jobs, Run History, Programs & Schedules."""

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QTabWidget,
    QComboBox,
    QSplitter,
    QPlainTextEdit,
)
from PyQt6.QtCore import Qt, QTimer

from services.db_service import OracleConnection, OracleRow
from services.scheduler_service import (
    list_jobs,
    list_run_history,
    run_job,
    stop_job,
    toggle_job,
    list_programs,
    list_schedules,
)
from ui.widgets.live import LiveWorker

_JOB_COLS = [
    "Owner",
    "Job Name",
    "Type",
    "State",
    "Last Run",
    "Next Run",
    "Failures",
    "Enabled",
]
_HIST_COLS = [
    "Owner",
    "Job Name",
    "Status",
    "Started",
    "Duration",
    "Error Code",
    "Error Message",
]
_PROG_COLS = ["Owner", "Program Name", "Type", "Enabled"]
_SCHED_COLS = ["Owner", "Schedule Name", "Repeat Interval", "Start Date"]


class SchedulerTab(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._conn: OracleConnection | None = None
        self._worker: LiveWorker | None = None
        self._jobs: list[OracleRow] = []
        self._hist_rows: list[OracleRow] = []
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_refresh_jobs)
        self._build_ui()

    def set_conn(self, conn: OracleConnection) -> None:
        self._conn = conn

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        top = QHBoxLayout()
        top.addWidget(QLabel("Auto-refresh:"))
        self._refresh_combo = QComboBox()
        self._refresh_combo.addItems(["Off", "30s", "60s", "5min"])
        top.addWidget(self._refresh_combo)
        top.addStretch()
        layout.addLayout(top)

        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_jobs_tab(), "Jobs")
        self._tabs.addTab(self._build_history_tab(), "Run History")
        self._tabs.addTab(self._build_programs_tab(), "Programs & Schedules")
        layout.addWidget(self._tabs, 1)

        self._refresh_combo.currentIndexChanged.connect(
            self._on_refresh_interval_changed
        )

    def _build_jobs_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 4, 0, 0)
        bar = QHBoxLayout()
        self._jobs_refresh = QPushButton("Refresh")
        self._jobs_refresh.setObjectName("primaryBtn")
        self._run_btn = QPushButton("Run Now")
        self._stop_btn = QPushButton("Stop")
        self._enable_btn = QPushButton("Enable")
        self._disable_btn = QPushButton("Disable")
        self._jobs_status = QLabel("")
        for w2 in [
            self._jobs_refresh,
            self._run_btn,
            self._stop_btn,
            self._enable_btn,
            self._disable_btn,
        ]:
            bar.addWidget(w2)
        bar.addWidget(self._jobs_status)
        bar.addStretch()
        layout.addLayout(bar)
        self._jobs_table = QTableWidget(0, len(_JOB_COLS))
        self._jobs_table.setHorizontalHeaderLabels(_JOB_COLS)
        jobs_header = self._jobs_table.horizontalHeader()
        assert jobs_header is not None
        jobs_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._jobs_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._jobs_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._jobs_table.setAlternatingRowColors(True)
        layout.addWidget(self._jobs_table)
        self._jobs_refresh.clicked.connect(self._on_refresh_jobs)
        self._run_btn.clicked.connect(self._on_run_job)
        self._stop_btn.clicked.connect(self._on_stop_job)
        self._enable_btn.clicked.connect(lambda: self._toggle(True))
        self._disable_btn.clicked.connect(lambda: self._toggle(False))
        return w

    def _build_history_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 4, 0, 0)
        bar = QHBoxLayout()
        bar.addWidget(QLabel("Job:"))
        self._hist_job = QLineEdit()
        self._hist_job.setPlaceholderText("filter by name")
        bar.addWidget(self._hist_job)
        bar.addWidget(QLabel("Status:"))
        self._hist_status = QComboBox()
        self._hist_status.addItems(["All", "SUCCEEDED", "FAILED", "STOPPED"])
        bar.addWidget(self._hist_status)
        self._hist_refresh = QPushButton("Refresh")
        self._hist_refresh.setObjectName("primaryBtn")
        bar.addWidget(self._hist_refresh)
        bar.addStretch()
        layout.addLayout(bar)
        splitter = QSplitter(Qt.Orientation.Vertical)
        self._hist_table = QTableWidget(0, len(_HIST_COLS))
        self._hist_table.setHorizontalHeaderLabels(_HIST_COLS)
        hist_header = self._hist_table.horizontalHeader()
        assert hist_header is not None
        hist_header.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        self._hist_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._hist_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._hist_table.setAlternatingRowColors(True)
        splitter.addWidget(self._hist_table)
        self._hist_detail = QPlainTextEdit()
        self._hist_detail.setReadOnly(True)
        splitter.addWidget(self._hist_detail)
        splitter.setSizes([400, 100])
        layout.addWidget(splitter)
        self._hist_refresh.clicked.connect(self._on_refresh_history)
        self._hist_table.currentCellChanged.connect(self._on_hist_row_changed)
        return w

    def _build_programs_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 4, 0, 0)
        self._prog_refresh = QPushButton("Refresh")
        self._prog_refresh.setObjectName("primaryBtn")
        layout.addWidget(self._prog_refresh)
        self._prog_table = QTableWidget(0, len(_PROG_COLS))
        self._prog_table.setHorizontalHeaderLabels(_PROG_COLS)
        prog_header = self._prog_table.horizontalHeader()
        assert prog_header is not None
        prog_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._prog_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self._prog_table)
        self._sched_table = QTableWidget(0, len(_SCHED_COLS))
        self._sched_table.setHorizontalHeaderLabels(_SCHED_COLS)
        sched_header = self._sched_table.horizontalHeader()
        assert sched_header is not None
        sched_header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._sched_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self._sched_table)
        self._prog_refresh.clicked.connect(self._on_refresh_programs)
        return w

    def _selected_job(self) -> OracleRow | None:
        row = self._jobs_table.currentRow()
        return self._jobs[row] if 0 <= row < len(self._jobs) else None

    def _on_refresh_jobs(self) -> None:
        if self._conn is None:
            return
        self._jobs_refresh.setEnabled(False)
        w = LiveWorker(list_jobs, self._conn)
        w.finished.connect(self._on_jobs_done)
        w.error.connect(self._on_jobs_error)
        w.start()
        self._worker = w

    def _on_jobs_error(self, m: str) -> None:
        self._jobs_refresh.setEnabled(True)
        self._jobs_status.setText(f"Error: {m[:60]}")

    def _on_jobs_done(self, rows: list[OracleRow]) -> None:
        self._jobs = rows
        self._jobs_refresh.setEnabled(True)
        self._jobs_status.setText(f"{len(rows)} job(s)")
        self._jobs_table.setRowCount(0)
        for i, r in enumerate(rows):
            self._jobs_table.insertRow(i)
            for j, v in enumerate(
                [
                    r.get("owner", ""),
                    r.get("job_name", ""),
                    r.get("job_type", ""),
                    r.get("state", ""),
                    str(r.get("last_start_date", "")),
                    str(r.get("next_run_date", "")),
                    str(r.get("failure_count", 0)),
                    str(r.get("enabled", "")),
                ]
            ):
                self._jobs_table.setItem(i, j, QTableWidgetItem(v))

    def _on_run_job(self) -> None:
        r = self._selected_job()
        if r is None or self._conn is None:
            return
        try:
            run_job(self._conn, r["owner"], r["job_name"])
            self._jobs_status.setText(f"Started {r['job_name']}")
        except Exception as e:
            self._jobs_status.setText(f"Error: {str(e)[:80]}")

    def _on_stop_job(self) -> None:
        r = self._selected_job()
        if r is None or self._conn is None:
            return
        try:
            stop_job(self._conn, r["owner"], r["job_name"])
            self._jobs_status.setText(f"Stopped {r['job_name']}")
        except Exception as e:
            self._jobs_status.setText(f"Error: {str(e)[:80]}")

    def _toggle(self, enable: bool) -> None:
        r = self._selected_job()
        if r is None or self._conn is None:
            return
        try:
            toggle_job(self._conn, r["owner"], r["job_name"], enable)
            self._on_refresh_jobs()
        except Exception as e:
            self._jobs_status.setText(f"Error: {str(e)[:80]}")

    def _on_refresh_history(self) -> None:
        if self._conn is None:
            return
        job = self._hist_job.text().strip() or None
        st = self._hist_status.currentText()
        status = None if st == "All" else st
        self._hist_refresh.setEnabled(False)
        w = LiveWorker(list_run_history, self._conn, job, status, 100)
        w.finished.connect(self._on_history_done)
        w.error.connect(lambda m: self._hist_refresh.setEnabled(True))
        w.start()

    def _on_history_done(self, rows: list[OracleRow]) -> None:
        self._hist_rows = rows
        self._hist_refresh.setEnabled(True)
        self._hist_table.setRowCount(0)
        for i, r in enumerate(rows):
            self._hist_table.insertRow(i)
            for j, v in enumerate(
                [
                    r.get("owner", ""),
                    r.get("job_name", ""),
                    r.get("status", ""),
                    str(r.get("actual_start_date", "")),
                    str(r.get("run_duration", "")),
                    str(r.get("error_code", "")),
                    (r.get("error_message") or "")[:80],
                ]
            ):
                self._hist_table.setItem(i, j, QTableWidgetItem(v))

    def _on_hist_row_changed(self, row: int, *_: int) -> None:
        if 0 <= row < len(self._hist_rows):
            self._hist_detail.setPlainText(
                self._hist_rows[row].get("error_message", "") or ""
            )

    def _on_refresh_programs(self) -> None:
        if self._conn is None:
            return
        w = LiveWorker(list_programs, self._conn)
        w.finished.connect(self._on_programs_done)
        w.start()
        w2 = LiveWorker(list_schedules, self._conn)
        w2.finished.connect(self._on_schedules_done)
        w2.start()

    def _on_programs_done(self, rows: list[OracleRow]) -> None:
        self._prog_table.setRowCount(0)
        for i, r in enumerate(rows):
            self._prog_table.insertRow(i)
            for j, v in enumerate(
                [
                    r.get("owner", ""),
                    r.get("program_name", ""),
                    r.get("program_type", ""),
                    str(r.get("enabled", "")),
                ]
            ):
                self._prog_table.setItem(i, j, QTableWidgetItem(v))

    def _on_schedules_done(self, rows: list[OracleRow]) -> None:
        self._sched_table.setRowCount(0)
        for i, r in enumerate(rows):
            self._sched_table.insertRow(i)
            for j, v in enumerate(
                [
                    r.get("owner", ""),
                    r.get("schedule_name", ""),
                    r.get("repeat_interval", ""),
                    str(r.get("start_date", "")),
                ]
            ):
                self._sched_table.setItem(i, j, QTableWidgetItem(v))

    def _on_refresh_interval_changed(self, idx: int) -> None:
        self._timer.stop()
        intervals = {"30s": 30000, "60s": 60000, "5min": 300000}
        key = self._refresh_combo.currentText()
        if key in intervals:
            self._timer.start(intervals[key])
