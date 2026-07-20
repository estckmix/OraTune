"""Connection info tab — shows active connection profile and DB version."""

import oracledb
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QFormLayout,
    QLabel,
    QPushButton,
)
from PyQt6.QtCore import Qt, pyqtSignal
from services.db_service import OracleConnection


class ConnectionTab(QWidget):
    disconnect_requested = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        title = QLabel("ACTIVE CONNECTION")
        title.setObjectName("sectionHeader")
        layout.addWidget(title)

        self._form = QFormLayout()
        self._type_lbl = QLabel("—")
        self._host_lbl = QLabel("—")
        self._user_lbl = QLabel("—")
        self._ver_lbl = QLabel("—")
        self._time_lbl = QLabel("—")
        for label, widget in [
            ("Type:", self._type_lbl),
            ("Connection:", self._host_lbl),
            ("Username:", self._user_lbl),
            ("DB Version:", self._ver_lbl),
            ("Connected at:", self._time_lbl),
        ]:
            lbl = QLabel(label)
            lbl.setObjectName("dimLabel")
            self._form.addRow(lbl, widget)
        layout.addLayout(self._form)

        self._disconnect_btn = QPushButton("DISCONNECT")
        self._disconnect_btn.clicked.connect(self.disconnect_requested)
        layout.addWidget(self._disconnect_btn, alignment=Qt.AlignmentFlag.AlignLeft)

    def refresh(self, conn: OracleConnection) -> None:
        p = conn.profile
        if p is None:
            return
        self._type_lbl.setText(
            "Direct" if p.connection_type == "direct" else "TNS Alias"
        )
        if p.connection_type == "direct":
            self._host_lbl.setText(f"{p.host}:{p.port}/{p.service}")
        else:
            self._host_lbl.setText(p.alias)
        self._user_lbl.setText(p.username)
        try:
            ver = conn.get_db_version()
            self._ver_lbl.setText(ver[:80])
        except (oracledb.Error, RuntimeError):
            self._ver_lbl.setText("Unknown")
        from datetime import datetime

        self._time_lbl.setText(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
