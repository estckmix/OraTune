"""Diff View - Side-by-side SQL/PLSQL code comparison (rebuilt for AnalysisSession)"""

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QSplitter,
    QTextEdit,
    QFrame,
    QComboBox,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import (
    QColor,
    QFont,
    QSyntaxHighlighter,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
)

from core.models import AnalysisSession, DiffResult


class SQLHighlighter(QSyntaxHighlighter):
    """Basic SQL syntax highlighter"""

    KEYWORDS = [
        "SELECT",
        "FROM",
        "WHERE",
        "AND",
        "OR",
        "NOT",
        "IN",
        "EXISTS",
        "JOIN",
        "LEFT",
        "RIGHT",
        "INNER",
        "OUTER",
        "FULL",
        "CROSS",
        "ON",
        "GROUP",
        "BY",
        "ORDER",
        "HAVING",
        "UNION",
        "ALL",
        "INSERT",
        "INTO",
        "VALUES",
        "UPDATE",
        "SET",
        "DELETE",
        "CREATE",
        "ALTER",
        "DROP",
        "INDEX",
        "TABLE",
        "VIEW",
        "WITH",
        "AS",
        "CASE",
        "WHEN",
        "THEN",
        "ELSE",
        "END",
        "DECLARE",
        "BEGIN",
        "EXCEPTION",
        "RAISE",
        "RETURN",
        "PROCEDURE",
        "FUNCTION",
        "PACKAGE",
        "BODY",
        "IS",
        "CURSOR",
        "FETCH",
        "OPEN",
        "CLOSE",
        "LOOP",
        "FOR",
        "WHILE",
        "IF",
        "THEN",
        "ELSIF",
        "END",
        "NULL",
        "COMMIT",
        "ROLLBACK",
        "DISTINCT",
        "BETWEEN",
        "LIKE",
        "IS",
        "NULL",
        "ROWNUM",
        "ROWID",
        "SYSDATE",
        "DUAL",
        "NUMBER",
        "VARCHAR2",
        "DATE",
        "TIMESTAMP",
        "CHAR",
        "CLOB",
        "BLOB",
        "INDEX",
        "HINT",
        "PARALLEL",
        "FULL",
        "USE_NL",
        "USE_HASH",
        "LEADING",
        "NO_MERGE",
        "PUSH_PRED",
    ]

    def __init__(self, document: QTextDocument | None) -> None:
        super().__init__(document)
        import re

        self.re = re

        self.keyword_format = QTextCharFormat()
        self.keyword_format.setForeground(QColor("#ff7b72"))
        self.keyword_format.setFontWeight(QFont.Weight.Bold)

        self.string_format = QTextCharFormat()
        self.string_format.setForeground(QColor("#a5d6ff"))

        self.comment_format = QTextCharFormat()
        self.comment_format.setForeground(QColor("#8b949e"))
        self.comment_format.setFontItalic(True)

        self.number_format = QTextCharFormat()
        self.number_format.setForeground(QColor("#79c0ff"))

        self.hint_format = QTextCharFormat()
        self.hint_format.setForeground(QColor("#e3b341"))

        pattern = r"\b(" + "|".join(self.KEYWORDS) + r")\b"
        self.keyword_re = re.compile(pattern, re.IGNORECASE)

    def highlightBlock(self, text: str | None) -> None:
        if text is None:
            return
        # Comments
        for m in self.re.finditer(r"--[^\n]*", text):
            self.setFormat(m.start(), m.end() - m.start(), self.comment_format)

        # Strings
        for m in self.re.finditer(r"'[^']*'", text):
            self.setFormat(m.start(), m.end() - m.start(), self.string_format)

        # Hints
        for m in self.re.finditer(r"/\*\+.*?\*/", text):
            self.setFormat(m.start(), m.end() - m.start(), self.hint_format)

        # Keywords
        for m in self.keyword_re.finditer(text):
            self.setFormat(m.start(), m.end() - m.start(), self.keyword_format)

        # Numbers
        for m in self.re.finditer(r"\b\d+(\.\d+)?\b", text):
            self.setFormat(m.start(), m.end() - m.start(), self.number_format)


class DiffTextEdit(QTextEdit):
    def __init__(self, title: str, title_color: str) -> None:
        super().__init__()
        self.setReadOnly(True)
        self.setFont(QFont("Consolas", 11))
        self.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)

        self._highlighter = SQLHighlighter(self.document())

        self._title = title
        self._title_color = title_color

    def set_content(
        self, content: str, diff_lines: dict[int, str] | None = None
    ) -> None:
        """
        diff_lines: dict mapping line_number -> 'add' | 'remove' | 'change'
        Background colors per tag:
          remove -> #3a1515 (dark red)
          add    -> #152a15 (dark green)
          change -> #2a2a15 (dark amber)
        """
        self.clear()
        cursor = self.textCursor()

        lines = content.split("\n")
        for i, line in enumerate(lines):
            fmt = QTextCharFormat()

            if diff_lines:
                tag = diff_lines.get(i + 1)
                if tag == "remove":
                    fmt.setBackground(QColor("#3a1515"))
                elif tag == "add":
                    fmt.setBackground(QColor("#152a15"))
                elif tag == "change":
                    fmt.setBackground(QColor("#2a2a15"))

            cursor.movePosition(QTextCursor.MoveOperation.End)
            cursor.insertText(line + ("\n" if i < len(lines) - 1 else ""), fmt)

        self.moveCursor(QTextCursor.MoveOperation.Start)


def _editor_pane(title: str, color: str) -> tuple[QFrame, DiffTextEdit]:
    """Titled diff editor pane — identical styling for both sides."""
    frame = QFrame()
    pane_layout = QVBoxLayout(frame)
    pane_layout.setContentsMargins(0, 0, 0, 0)
    pane_layout.setSpacing(4)
    title_lbl = QLabel(title)
    title_lbl.setStyleSheet(
        f"color: {color}; font-size: 11px; font-weight: bold; letter-spacing: 2px; background: transparent;"
    )
    pane_layout.addWidget(title_lbl)
    edit = DiffTextEdit(title, color)
    pane_layout.addWidget(edit)
    return frame, edit


class DiffView(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # File selector if multiple SQL files
        top_bar = QHBoxLayout()
        top_bar.addWidget(QLabel("Comparing:"))
        self.file_selector = QComboBox()
        self.file_selector.setMinimumWidth(300)
        self.file_selector.currentIndexChanged.connect(self._on_file_selected)
        top_bar.addWidget(self.file_selector)
        top_bar.addStretch()

        # Legend
        for color, label in [
            ("#2ea043", "Added"),
            ("#f85149", "Removed"),
            ("#e3b341", "Changed"),
        ]:
            dot = QLabel(f"■ {label}")
            dot.setStyleSheet(
                f"color: {color}; font-size: 11px; background: transparent;"
            )
            top_bar.addWidget(dot)

        layout.addLayout(top_bar)

        # Side-by-side diff
        splitter = QSplitter(Qt.Orientation.Horizontal)

        left_frame, self.left_edit = _editor_pane("BASELINE", "#2ea043")
        right_frame, self.right_edit = _editor_pane("CURRENT", "#f85149")

        splitter.addWidget(left_frame)
        splitter.addWidget(right_frame)
        splitter.setSizes([600, 600])
        layout.addWidget(splitter)

        # Sync scrollbars
        left_bar = self.left_edit.verticalScrollBar()
        right_bar = self.right_edit.verticalScrollBar()
        assert left_bar is not None and right_bar is not None
        left_bar.valueChanged.connect(right_bar.setValue)
        right_bar.valueChanged.connect(left_bar.setValue)

        self._diff_data: list[DiffResult] = []
        self._placeholder()

    def _placeholder(self) -> None:
        placeholder = "-- No SQL/PLSQL files loaded yet\n-- Upload .sql, .pls, .pkb files to see diff"
        self.left_edit.setPlainText(placeholder)
        self.right_edit.setPlainText(placeholder)

    def load_results(self, session: AnalysisSession) -> None:
        """Load diff results from an AnalysisSession."""
        self.clear()
        for diff in session.diff_results:
            self._load_diff(diff)

    def _load_diff(self, diff: DiffResult) -> None:
        """Register a single DiffResult and populate the selector."""
        self._diff_data.append(diff)
        self.file_selector.addItem(diff.label)
        # Show first item automatically when it is added
        if len(self._diff_data) == 1:
            self._show_diff(0)

    def _on_file_selected(self, idx: int) -> None:
        if idx >= 0:
            self._show_diff(idx)

    def _show_diff(self, idx: int) -> None:
        if idx < 0 or idx >= len(self._diff_data):
            return
        diff = self._diff_data[idx]
        self.left_edit.set_content(diff.baseline_text, diff.baseline_diff_lines)
        self.right_edit.set_content(diff.current_text, diff.current_diff_lines)

    def clear(self) -> None:
        self.file_selector.clear()
        self._diff_data = []
        self._placeholder()
