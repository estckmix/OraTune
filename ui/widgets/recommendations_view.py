"""Recommendations View widget — AI or rules-based tuning suggestions."""

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QTextEdit,
)
from PyQt6.QtGui import QFont

from core.models import AnalysisSession


class RecommendationsView(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Header
        header = QHBoxLayout()
        self._mode_label = QLabel("● OFFLINE MODE  —  Rules-based recommendations")
        self._mode_label.setStyleSheet(
            "color: #888888; font-size: 11px; letter-spacing: 1px; background: transparent;"
        )
        header.addWidget(self._mode_label)
        header.addStretch()
        layout.addLayout(header)

        # Error banner (hidden by default)
        self._error_banner = QLabel()
        self._error_banner.setStyleSheet(
            "background: #2a2a15; color: #e3b341; border: 1px solid #e3b341; "
            "border-radius: 4px; padding: 6px 10px; font-size: 11px;"
        )
        self._error_banner.setVisible(False)
        self._error_banner.setWordWrap(True)
        layout.addWidget(self._error_banner)

        # Recommendations text area
        self._text = QTextEdit()
        self._text.setReadOnly(True)
        self._text.setFont(QFont("Consolas", 12))
        self._text.setStyleSheet("""
            QTextEdit {
                background-color: #161616;
                color: #F2F2F2;
                border: 1px solid #2A2A2A;
                border-radius: 4px;
                padding: 16px;
                font-family: 'Consolas', monospace;
                font-size: 12px;
                line-height: 1.6;
            }
        """)
        self._set_placeholder()
        layout.addWidget(self._text)

    def _set_placeholder(self) -> None:
        self._text.setHtml("""
            <p style='color: #555555; font-family: Consolas; font-size: 13px;'>
            Run an analysis to generate tuning recommendations.
            </p>
        """)

    def load_results(self, session: AnalysisSession) -> None:
        rec = session.recommendations
        mode = rec.get("mode", "offline")
        provider = rec.get("provider", "Offline")
        content = rec.get("content", "")
        error = rec.get("error")

        self._mode_label.setText(f"Mode: {mode.upper()}  ·  Provider: {provider}")

        if error:
            self._error_banner.setText(
                f"⚠  AI unavailable — showing offline analysis.  ({error})"
            )
            self._error_banner.setVisible(True)
        else:
            self._error_banner.setVisible(False)

        self._text.setMarkdown(content) if content else self._text.clear()

    def clear(self) -> None:
        self._set_placeholder()
        self._mode_label.setText("● OFFLINE MODE  —  Rules-based recommendations")
        self._mode_label.setStyleSheet(
            "color: #888888; font-size: 11px; letter-spacing: 1px; background: transparent;"
        )
        self._error_banner.setVisible(False)
