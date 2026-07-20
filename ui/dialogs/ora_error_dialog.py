"""ORA- Error Reference dialog — searchable lookup for Oracle error codes."""

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QLineEdit,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QFrame,
    QWidget,
)
from PyQt6.QtGui import QColor

from services.ora_error_service import search
from ui.app_theme import SEVERITY_COLORS as _SEV_COLORS

_PLACEHOLDER = "No error selected."


class OraErrorDialog(QDialog):
    def __init__(self, parent: QWidget | None = None, initial_code: str = "") -> None:
        super().__init__(parent)
        self.setWindowTitle("ORA- Error Reference")
        self.resize(860, 560)
        self._build_ui()
        self._populate(search(""))
        self._search_bar.textChanged.connect(self._on_search)
        if initial_code:
            self._search_bar.setText(initial_code.upper())

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self._search_bar = QLineEdit()
        self._search_bar.setPlaceholderText("Search by code, message, or cause…")
        self._search_bar.setClearButtonEnabled(True)
        layout.addWidget(self._search_bar)

        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["Code", "Message", "Severity"])
        hdr = self._table.horizontalHeader()
        assert hdr is not None
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        v_header = self._table.verticalHeader()
        assert v_header is not None
        v_header.setVisible(False)
        self._table.currentCellChanged.connect(
            lambda row, *_: self._on_row_changed(row)
        )
        layout.addWidget(self._table, 1)

        layout.addWidget(self._build_detail_frame())

    def _build_detail_frame(self) -> QFrame:
        """Cause/action detail panel below the results table."""
        detail_frame = QFrame()
        detail_frame.setStyleSheet(
            "QFrame { background: #1C1C1C; border: 1px solid #2A2A2A; border-radius: 4px; }"
        )
        detail_frame.setFixedHeight(150)
        detail_layout = QVBoxLayout(detail_frame)
        detail_layout.setContentsMargins(10, 8, 10, 8)
        detail_layout.setSpacing(4)

        self._detail_title = QLabel(_PLACEHOLDER)
        self._detail_title.setStyleSheet(
            "color: #F2F2F2; font-weight: bold; font-size: 12px; background: transparent;"
        )
        detail_layout.addWidget(self._detail_title)

        self._cause_hdr = QLabel("Cause")
        self._cause_hdr.setStyleSheet(
            "color: #e3b341; font-size: 10px; font-weight: bold; "
            "letter-spacing: 1px; background: transparent;"
        )
        self._cause_hdr.hide()
        detail_layout.addWidget(self._cause_hdr)

        self._cause_lbl = QLabel()
        self._cause_lbl.setWordWrap(True)
        self._cause_lbl.setStyleSheet(
            "color: #888888; font-size: 11px; background: transparent;"
        )
        self._cause_lbl.hide()
        detail_layout.addWidget(self._cause_lbl)

        self._action_hdr = QLabel("Action")
        self._action_hdr.setStyleSheet(
            "color: #2ea043; font-size: 10px; font-weight: bold; "
            "letter-spacing: 1px; background: transparent;"
        )
        self._action_hdr.hide()
        detail_layout.addWidget(self._action_hdr)

        self._action_lbl = QLabel()
        self._action_lbl.setWordWrap(True)
        self._action_lbl.setStyleSheet(
            "color: #888888; font-size: 11px; background: transparent;"
        )
        self._action_lbl.hide()
        detail_layout.addWidget(self._action_lbl)

        detail_layout.addStretch()
        return detail_frame

    def _on_search(self, text: str) -> None:
        self._populate(search(text))

    def _populate(self, results: list[dict[str, str]]) -> None:
        self._table.setRowCount(0)
        white = QColor("#F2F2F2")
        for row_idx, entry in enumerate(results):
            self._table.insertRow(row_idx)
            code_item = QTableWidgetItem(entry["code"])
            code_item.setForeground(white)
            self._table.setItem(row_idx, 0, code_item)
            msg_item = QTableWidgetItem(entry.get("message", ""))
            msg_item.setForeground(white)
            self._table.setItem(row_idx, 1, msg_item)
            sev = entry.get("severity", "")
            sev_item = QTableWidgetItem(sev)
            sev_item.setForeground(QColor(_SEV_COLORS.get(sev, "#888888")))
            self._table.setItem(row_idx, 2, sev_item)
        if results:
            self._table.selectRow(0)
        else:
            self._clear_detail()

    def _on_row_changed(self, row: int) -> None:
        if row < 0 or row >= self._table.rowCount():
            self._clear_detail()
            return
        code_item = self._table.item(row, 0)
        if code_item is None:
            self._clear_detail()
            return
        from services.ora_error_service import lookup

        entry = lookup(code_item.text())
        if entry:
            self._detail_title.setText(
                f"{code_item.text()} · {entry.get('message', '')}"
            )
            self._cause_lbl.setText(entry.get("cause", ""))
            self._action_lbl.setText(entry.get("action", ""))
            for w in (
                self._cause_hdr,
                self._cause_lbl,
                self._action_hdr,
                self._action_lbl,
            ):
                w.show()
        else:
            self._clear_detail()

    def _clear_detail(self) -> None:
        self._detail_title.setText(_PLACEHOLDER)
        for w in (self._cause_hdr, self._cause_lbl, self._action_hdr, self._action_lbl):
            w.hide()
