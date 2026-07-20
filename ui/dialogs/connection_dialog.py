"""Connection Dialog — Oracle DB connect/test modal."""

import json

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QButtonGroup,
    QFormLayout,
    QStackedWidget,
    QWidget,
    QSpinBox,
)

from core.models import ConnectionProfile
from services.ai_service import SETTINGS_PATH as _SETTINGS
from services.db_service import OracleConnection


class ConnectionDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Connect to Oracle Database")
        self.setModal(True)
        self.setMinimumWidth(440)
        self._profile: ConnectionProfile | None = None
        self._build_ui()
        self._load_saved()

    def profile(self) -> ConnectionProfile | None:
        return self._profile

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        type_row = QHBoxLayout()
        self._direct_radio = QRadioButton("Direct  (Host / Port / Service)")
        self._tns_radio = QRadioButton("TNS Alias")
        self._direct_radio.setChecked(True)
        grp = QButtonGroup(self)
        grp.addButton(self._direct_radio)
        grp.addButton(self._tns_radio)
        type_row.addWidget(self._direct_radio)
        type_row.addWidget(self._tns_radio)
        layout.addLayout(type_row)

        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_direct_page())
        self._stack.addWidget(self._build_tns_page())
        layout.addWidget(self._stack)

        auth = QFormLayout()
        self._user = QLineEdit()
        self._pass = QLineEdit()
        self._pass.setEchoMode(QLineEdit.EchoMode.Password)
        auth.addRow("Username:", self._user)
        auth.addRow("Password:", self._pass)
        layout.addLayout(auth)

        self._status = QLabel("")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)

        btn_row = QHBoxLayout()
        self._test_btn = QPushButton("Test")
        self._connect_btn = QPushButton("Connect")
        self._connect_btn.setObjectName("primaryBtn")
        cancel_btn = QPushButton("Cancel")
        btn_row.addWidget(self._test_btn)
        btn_row.addStretch()
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(self._connect_btn)
        layout.addLayout(btn_row)

        self._direct_radio.toggled.connect(
            lambda checked: self._stack.setCurrentIndex(0 if checked else 1)
        )
        self._test_btn.clicked.connect(self._on_test)
        self._connect_btn.clicked.connect(self._on_connect)
        cancel_btn.clicked.connect(self.reject)

    def _build_direct_page(self) -> QWidget:
        direct_page = QWidget()
        df = QFormLayout(direct_page)
        self._host = QLineEdit()
        self._host.setPlaceholderText("db.example.com")
        self._port = QSpinBox()
        self._port.setRange(1, 65535)
        self._port.setValue(1521)
        self._service = QLineEdit()
        self._service.setPlaceholderText("ORCL")
        df.addRow("Host:", self._host)
        df.addRow("Port:", self._port)
        df.addRow("Service:", self._service)
        return direct_page

    def _build_tns_page(self) -> QWidget:
        tns_page = QWidget()
        tf = QFormLayout(tns_page)
        self._alias = QLineEdit()
        self._alias.setPlaceholderText("MYDB")
        tf.addRow("TNS Alias:", self._alias)
        return tns_page

    def _current_profile(self) -> ConnectionProfile:
        if self._direct_radio.isChecked():
            return ConnectionProfile(
                name=f"{self._user.text()}@{self._host.text()}",
                connection_type="direct",
                host=self._host.text().strip(),
                port=self._port.value(),
                service=self._service.text().strip(),
                username=self._user.text().strip(),
                password=self._pass.text(),
            )
        return ConnectionProfile(
            name=f"{self._user.text()}@{self._alias.text()}",
            connection_type="tns",
            alias=self._alias.text().strip(),
            username=self._user.text().strip(),
            password=self._pass.text(),
        )

    def _set_status(self, text: str, ok: bool | None = None) -> None:
        colors = {True: "#2ea043", False: "#f85149", None: "#888888"}
        self._status.setText(text)
        self._status.setStyleSheet(
            f"color: {colors[ok]}; background: transparent; font-size: 11px;"
        )

    def _on_test(self) -> None:
        self._set_status("Testing…")
        self._test_btn.setEnabled(False)
        self._connect_btn.setEnabled(False)
        ok, msg = OracleConnection().test_connection(self._current_profile())
        self._test_btn.setEnabled(True)
        self._connect_btn.setEnabled(True)
        self._set_status("✓ Connection successful" if ok else f"✗ {msg}", ok)

    def _on_connect(self) -> None:
        self._set_status("Connecting…")
        self._test_btn.setEnabled(False)
        self._connect_btn.setEnabled(False)
        profile = self._current_profile()
        ok, msg = OracleConnection().test_connection(profile)
        if ok:
            self._profile = profile
            self._save(profile)
            self.accept()
        else:
            self._test_btn.setEnabled(True)
            self._connect_btn.setEnabled(True)
            self._set_status(f"✗ {msg}", False)

    def _save(self, p: ConnectionProfile) -> None:
        try:
            data: dict[str, object] = {}
            if _SETTINGS.exists():
                data = json.loads(_SETTINGS.read_text())
            data["last_connection"] = {
                "connection_type": p.connection_type,
                "host": p.host,
                "port": p.port,
                "service": p.service,
                "alias": p.alias,
                "username": p.username,
            }
            _SETTINGS.write_text(json.dumps(data, indent=2))
        except (OSError, json.JSONDecodeError):
            pass  # Remembering the last connection is best-effort only

    def _load_saved(self) -> None:
        try:
            if not _SETTINGS.exists():
                return
            last = json.loads(_SETTINGS.read_text()).get("last_connection", {})
            if not last:
                return
            if last.get("connection_type") == "tns":
                self._tns_radio.setChecked(True)
                self._alias.setText(last.get("alias", ""))
            else:
                self._direct_radio.setChecked(True)
                self._host.setText(last.get("host", ""))
                self._port.setValue(last.get("port", 1521))
                self._service.setText(last.get("service", ""))
            self._user.setText(last.get("username", ""))
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            pass  # Corrupt saved connection — start with a blank form
