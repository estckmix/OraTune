"""Upload panel widget — drag-and-drop file upload for one side of the comparison."""

from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFileDialog,
    QListWidget,
    QListWidgetItem,
)
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QDragEnterEvent, QDropEvent

# File extensions accepted by OraTune
_SQL_EXTS = {".sql", ".pls", ".pks", ".pkb", ".prc", ".fnc", ".trg"}
_PLAN_EXTS = {".xml"}
_AWR_EXTS = {".txt", ".lst", ".html", ".htm"}
_DMP_EXTS = {".dmp"}
_ALL_EXTS = _SQL_EXTS | _PLAN_EXTS | _AWR_EXTS | _DMP_EXTS


def _classify(filepath: str) -> str:
    ext = Path(filepath).suffix.lower()
    if ext in _SQL_EXTS:
        return "sql"
    if ext in _PLAN_EXTS:
        return "xplan"
    if ext in _AWR_EXTS:
        return "awr_tkprof"
    if ext in _DMP_EXTS:
        return "dmp"
    return "unknown"


class UploadPanel(QWidget):
    """A labelled drop zone showing accepted files with a Browse button."""

    files_changed = pyqtSignal(dict)  # emits {role: [filepath, ...]}

    def __init__(
        self,
        label: str,
        border_color: str,
        label_color: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._label = label
        self._border_color = border_color
        self._label_color = label_color
        self._files: dict[str, list[str]] = {}  # role -> [filepath]
        self.setAcceptDrops(True)
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._title = QLabel(self._label)
        self._title.setStyleSheet(
            f"color: {self._label_color}; font-size: 11px; font-weight: bold; "
            "letter-spacing: 2px; background: transparent;"
        )
        layout.addWidget(self._title)

        # One-line file field; scrolls internally when several files are loaded
        self._list = QListWidget()
        self._list.setFixedHeight(26)
        self._list.setStyleSheet(
            f"background-color: #161616; border: 1px dashed {self._border_color}; "
            "border-radius: 4px; font-size: 11px; color: #888888;"
        )
        layout.addWidget(self._list)

        # Controls under the field: hint on the left, buttons on the right
        controls = QHBoxLayout()
        self._hint = QLabel("Drop files here or click Browse")
        self._hint.setStyleSheet(
            "color: #555555; font-size: 10px; background: transparent;"
        )
        controls.addWidget(self._hint)
        controls.addStretch()
        browse_btn = QPushButton("Browse...")
        browse_btn.setFixedHeight(26)
        browse_btn.clicked.connect(self._browse)
        controls.addWidget(browse_btn)
        clear_btn = QPushButton("Clear")
        clear_btn.setFixedHeight(26)
        clear_btn.clicked.connect(self.clear)
        controls.addWidget(clear_btn)
        layout.addLayout(controls)

    def _browse(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            f"Select {self._label} files",
            "",
            "Oracle files (*.sql *.pls *.pks *.pkb *.prc *.fnc *.trg *.xml "
            "*.txt *.lst *.html *.htm *.dmp);;All Files (*)",
        )
        if paths:
            self._add_files(paths)

    def _add_files(self, paths: list[str]) -> None:
        for path in paths:
            role = _classify(path)
            if role == "unknown":
                continue
            if role not in self._files:
                self._files[role] = []
            if path not in self._files[role]:
                self._files[role].append(path)
                item = QListWidgetItem(f"[{role}] {Path(path).name}")
                self._list.addItem(item)
        self._hint.setVisible(self._list.count() == 0)
        self.files_changed.emit(self._files)

    def clear(self) -> None:
        self._files = {}
        self._list.clear()
        self._hint.setVisible(True)
        self.files_changed.emit(self._files)

    def dragEnterEvent(self, a0: QDragEnterEvent | None) -> None:
        if a0 is not None and (mime := a0.mimeData()) is not None and mime.hasUrls():
            a0.acceptProposedAction()

    def dropEvent(self, a0: QDropEvent | None) -> None:
        if a0 is None or (mime := a0.mimeData()) is None:
            return
        self._add_files([u.toLocalFile() for u in mime.urls()])
