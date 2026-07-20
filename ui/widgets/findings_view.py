"""Findings view — finding cards ordered by severity (sorting done by findings engine)."""

from core.models import AnalysisSession, Finding
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QScrollArea,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
)
import html as _html
import re as _re

from ui.app_theme import SEVERITY_COLORS as _SEV_COLORS

_ORA_RE = _re.compile(r"(ORA-\d{4,5})", _re.IGNORECASE)


class FindingsView(QWidget):
    annotation_requested = pyqtSignal(object)  # emits Finding
    # emits ORA- code, e.g. "ORA-04031"
    ora_code_clicked = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        self._container = QWidget()
        self._inner = QVBoxLayout(self._container)
        self._inner.setContentsMargins(12, 12, 12, 12)
        self._inner.setSpacing(8)
        self._inner.addStretch()

        scroll.setWidget(self._container)
        layout.addWidget(scroll)

    def load_results(self, session: AnalysisSession) -> None:
        self.clear()
        for finding in session.findings:
            self._inner.insertWidget(self._inner.count() - 1, self._make_card(finding))

    def clear(self) -> None:
        while self._inner.count() > 1:
            item = self._inner.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.deleteLater()

    def refresh_card_annotation(self, finding: Finding) -> None:
        """Call after an annotation is saved to update the displayed note."""
        for i in range(self._inner.count() - 1):
            item = self._inner.itemAt(i)
            card = item.widget() if item is not None else None
            if card is not None and card.property("finding_id") == finding.id:
                note_label = card.findChild(QLabel, "noteLabel")
                if note_label:
                    note_label.setText(finding.annotation)
                    note_label.setVisible(bool(finding.annotation))
                break

    def _linkify(self, text: str) -> str:
        escaped = _html.escape(text)
        return _ORA_RE.sub(
            r'<a href="ora://\1" style="color:#e3b341; text-decoration:underline;">\1</a>',
            escaped,
        )

    def _card_top_row(self, finding: Finding) -> QHBoxLayout:
        """Severity badge + linkified title + annotate button."""
        top = QHBoxLayout()
        top.setSpacing(10)

        color = _SEV_COLORS.get(finding.severity, "#888888")
        sev_label = QLabel(finding.severity)
        sev_label.setFixedWidth(72)
        sev_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sev_label.setStyleSheet(
            f"color: {color}; background: transparent; border: 1px solid {color}; "
            "border-radius: 3px; padding: 2px 6px; font-size: 10px; font-weight: bold; "
            "letter-spacing: 0.5px;"
        )
        top.addWidget(sev_label)

        title = QLabel(f"<b>{self._linkify(finding.title)}</b>")
        title.setTextFormat(Qt.TextFormat.RichText)
        title.setOpenExternalLinks(False)
        title.setStyleSheet("color: #F2F2F2; background: transparent;")
        title.setWordWrap(True)
        title.linkActivated.connect(
            lambda href: self.ora_code_clicked.emit(href.replace("ora://", "").upper())
        )
        top.addWidget(title, 1)

        note_btn = QPushButton("✎")
        note_btn.setFixedSize(26, 26)
        note_btn.setToolTip("Add/edit note")
        note_btn.setStyleSheet(
            "QPushButton { background: transparent; border: none; color: #555555; font-size: 14px; }"
            "QPushButton:hover { color: #C41200; }"
        )
        note_btn.clicked.connect(lambda _, f=finding: self.annotation_requested.emit(f))
        top.addWidget(note_btn)
        return top

    def _make_card(self, finding: Finding) -> QWidget:
        card = QFrame()
        card.setProperty("finding_id", finding.id)
        card.setStyleSheet(
            "QFrame { background-color: #1C1C1C; border: 1px solid #2A2A2A; "
            "border-radius: 6px; }"
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

        layout.addLayout(self._card_top_row(finding))

        # Description
        desc = QLabel(self._linkify(finding.description))
        desc.setTextFormat(Qt.TextFormat.RichText)
        desc.setOpenExternalLinks(False)
        desc.setStyleSheet("color: #888888; background: transparent; font-size: 12px;")
        desc.setWordWrap(True)
        desc.linkActivated.connect(
            lambda href: self.ora_code_clicked.emit(href.replace("ora://", "").upper())
        )
        layout.addWidget(desc)

        # Inline annotation (hidden when empty)
        note_label = QLabel(finding.annotation)
        note_label.setObjectName("noteLabel")
        note_label.setStyleSheet(
            "color: #555555; background: transparent; font-size: 11px; font-style: italic;"
        )
        note_label.setWordWrap(True)
        note_label.setVisible(bool(finding.annotation))
        layout.addWidget(note_label)

        return card
