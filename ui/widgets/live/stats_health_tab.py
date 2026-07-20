"""Statistics Health Check tab."""

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QHeaderView,
)
from PyQt6.QtGui import QBrush, QColor

from services.db_service import OracleConnection
from services.stats_service import run_health_check, StatsFinding
from ui.app_theme import SEVERITY_COLORS
from ui.widgets.live import LiveWorker

_SEVERITY_ICON = {"critical": "🔴", "warning": "🟡"}
_SEVERITY_COLOR = {
    "critical": SEVERITY_COLORS["CRITICAL"],
    "warning": SEVERITY_COLORS["HIGH"],
}

_CHECK_LABELS = {
    "stale": "Stale Statistics",
    "missing": "Missing Statistics",
    "locked": "Locked Statistics",
    "partition": "Missing Partition Stats",
    "system": "System Statistics",
}


class StatsHealthTab(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._conn: OracleConnection | None = None
        self._worker: LiveWorker | None = None
        self._build_ui()

    def set_conn(self, conn: OracleConnection) -> None:
        self._conn = conn

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        bar = QHBoxLayout()
        bar.addWidget(QLabel("Schemas (comma-separated, empty = all):"))
        self._schema_edit = QLineEdit()
        self._schema_edit.setPlaceholderText("HR, SCOTT, MYAPP")
        bar.addWidget(self._schema_edit, 1)
        self._run_btn = QPushButton("Run Health Check")
        self._run_btn.setObjectName("primaryBtn")
        bar.addWidget(self._run_btn)
        self._status_lbl = QLabel("")
        bar.addWidget(self._status_lbl)
        layout.addLayout(bar)

        self._tree = QTreeWidget()
        self._tree.setColumnCount(3)
        self._tree.setHeaderLabels(["Object", "Detail", "Severity"])
        tree_header = self._tree.header()
        assert tree_header is not None
        tree_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._tree.setAlternatingRowColors(True)
        layout.addWidget(self._tree, 1)

        self._run_btn.clicked.connect(self._on_run)

    def _on_run(self) -> None:
        if self._conn is None:
            return
        schemas = [s.strip() for s in self._schema_edit.text().split(",") if s.strip()]
        self._run_btn.setEnabled(False)
        self._status_lbl.setText("Running…")
        self._worker = LiveWorker(run_health_check, self._conn, schemas)
        self._worker.finished.connect(self._on_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_done(self, findings: list[StatsFinding]) -> None:
        self._run_btn.setEnabled(True)
        n = len(findings)
        self._status_lbl.setText(f"{n} finding{'s' if n != 1 else ''}")
        self._tree.clear()

        groups: dict[str, list[StatsFinding]] = {}
        for f in findings:
            groups.setdefault(f.check, []).append(f)

        for check, items in groups.items():
            top = QTreeWidgetItem([_CHECK_LABELS.get(check, check), "", ""])
            for f in items:
                icon = _SEVERITY_ICON.get(f.severity, "⚪")
                obj = f"{f.owner}.{f.object_name}" if f.owner else f.object_name
                child = QTreeWidgetItem([f"{icon} {obj}", f.detail, f.severity.upper()])
                color = _SEVERITY_COLOR.get(f.severity, "#888888")
                for col in range(3):
                    child.setForeground(col, QBrush(QColor(color)))
                top.addChild(child)
            self._tree.addTopLevelItem(top)
            top.setExpanded(True)

    def _on_error(self, msg: str) -> None:
        self._run_btn.setEnabled(True)
        self._status_lbl.setText(f"Error: {msg[:80]}")
