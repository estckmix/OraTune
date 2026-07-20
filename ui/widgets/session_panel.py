"""Session history sidebar — collapsible panel showing past analyses."""

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
)
from PyQt6.QtCore import Qt, pyqtSignal

import json

from services import session_service


class SessionPanel(QWidget):
    session_selected = pyqtSignal(str)  # emits session id
    collapsed_changed = pyqtSignal(bool)  # emits True when collapsed

    _EXPANDED_WIDTH = 220
    _COLLAPSED_WIDTH = 32

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._collapsed = False
        self.setFixedWidth(self._EXPANDED_WIDTH)
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        header = QWidget()
        header.setFixedHeight(36)
        header.setStyleSheet("background: #161616; border-bottom: 1px solid #2A2A2A;")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(10, 0, 6, 0)

        self._title = QLabel("SESSION HISTORY")
        self._title.setStyleSheet(
            "color: #888888; font-size: 9px; font-weight: bold; "
            "letter-spacing: 1.5px; background: transparent;"
        )
        h_layout.addWidget(self._title)
        h_layout.addStretch()

        self._toggle_btn = QPushButton("‹")
        self._toggle_btn.setFixedSize(20, 20)
        self._toggle_btn.setStyleSheet(
            "QPushButton { background: transparent; border: none; color: #555555; font-size: 14px; }"
            "QPushButton:hover { color: #C41200; }"
        )
        self._toggle_btn.clicked.connect(self._toggle)
        h_layout.addWidget(self._toggle_btn)
        layout.addWidget(header)

        # Session list
        self._list = QListWidget()
        self._list.setStyleSheet("background: #161616; border: none;")
        self._list.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self._list)

    def refresh(self) -> None:
        """Reload session list from storage."""
        self._list.clear()
        rows = session_service.list_sessions()
        for row in rows:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, row["id"])
            files = json.loads(row.get("baseline_files") or "[]")
            primary = files[0] if files else "unknown"
            ts = row.get("timestamp", "")[:16].replace("T", " ")
            summary = row.get("summary", "")
            item.setText(f"{ts}\n{primary}\n{summary}")
            self._list.addItem(item)

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        session_id = item.data(Qt.ItemDataRole.UserRole)
        if session_id:
            self.session_selected.emit(session_id)

    def _toggle(self) -> None:
        self._collapsed = not self._collapsed
        if self._collapsed:
            self.setFixedWidth(self._COLLAPSED_WIDTH)
            self._title.setVisible(False)
            self._list.setVisible(False)
            self._toggle_btn.setText("›")
        else:
            self.setFixedWidth(self._EXPANDED_WIDTH)
            self._title.setVisible(True)
            self._list.setVisible(True)
            self._toggle_btn.setText("‹")
        self.collapsed_changed.emit(self._collapsed)
