"""Annotation dialog — add or edit a note on a Finding."""

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QWidget,
)
from PyQt6.QtCore import Qt

from core.models import Finding


class AnnotationDialog(QDialog):
    def __init__(self, finding: Finding, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._finding = finding
        self.setWindowTitle("Add Note")
        self.setFixedSize(400, 220)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        label = QLabel(f"Note for: {self._finding.title}")
        label.setStyleSheet("color: #888888; font-size: 11px;")
        label.setWordWrap(True)
        layout.addWidget(label)

        self._editor = QPlainTextEdit()
        self._editor.setPlainText(self._finding.annotation or "")
        self._editor.setPlaceholderText("Add your note here...")
        layout.addWidget(self._editor)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        ok = QPushButton("Save Note")
        ok.setObjectName("primaryBtn")
        ok.clicked.connect(self.accept)
        btn_row.addWidget(cancel)
        btn_row.addWidget(ok)
        layout.addLayout(btn_row)

    def annotation_text(self) -> str:
        return self._editor.toPlainText().strip()
