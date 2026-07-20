"""Global QSS stylesheet — OraTune logo color palette.

Import THEME and apply once in main.py:
    app.setStyleSheet(THEME)

No inline styles in widget files. All styling comes from here.

Color palette (from OraTune Logo.jpg):
  #111111  Background
  #1C1C1C  Surface (panels, cards, tab backgrounds)
  #2A2A2A  Border
  #C41200  Brand Red (primary accent)
  #E01500  Red Hover
  #F2F2F2  White (primary text)
  #888888  Muted (secondary text, labels)
"""

# Canonical severity colors — single source for every view that renders severity.
SEVERITY_COLORS = {
    "CRITICAL": "#C41200",  # Signal Red
    "HIGH": "#e3b341",  # Delta Amber
    "MEDIUM": "#C8A000",  # Caution Gold
    "LOW": "#79c0ff",  # Info Blue
    "INFO": "#888888",  # Muted Steel
}

THEME = """
QMainWindow, QDialog {
    background-color: #111111;
}

QWidget {
    background-color: #111111;
    color: #F2F2F2;
    font-family: 'Segoe UI', 'Consolas', 'Courier New', sans-serif;
    font-size: 13px;
}

/* ── Tab bar ── */
QTabWidget::pane {
    border: 1px solid #2A2A2A;
    background-color: #1C1C1C;
    border-radius: 0px;
}

QTabWidget::tab-bar {
    left: 10px;
}

/* Subtle Depth tabs: squared gradient buttons with a 1px lit top edge;
   selected = red gradient. border-radius must stay <= half the tab height
   or Qt drops the rounding. Vertical margins 5/4 render optically centered
   (Qt reserves an extra pixel row under the tab bar). */
QTabBar::tab {
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #2A2A2A, stop:1 #1C1C1C);
    color: #888888;
    padding: 8px 18px;
    border: 1px solid #111111;
    border-top: 1px solid rgba(255, 255, 255, 18%);
    border-radius: 8px;
    margin-right: 8px;
    margin-top: 5px;
    margin-bottom: 4px;
    min-width: 97px;
    font-family: 'Calibri';
    font-size: 12px;
    font-weight: bold;
    letter-spacing: 0.5px;
}

QTabBar::tab:selected {
    color: #FFFFFF;
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(224, 21, 0, 90%), stop:1 rgba(150, 12, 0, 85%));
    border: 1px solid rgb(150, 12, 0);
    border-top: 1px solid rgba(255, 255, 255, 35%);
}

QTabBar::tab:hover:!selected {
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #333333, stop:1 #222222);
    color: #F2F2F2;
}

/* ── Buttons ── */
/* Subtle Depth: squared gradient buttons with a 1px lit top edge; pressing
   inverts the gradient and kills the edge light. Radius 8px <= half height
   of the shortest buttons (26px Browse/Clear). */
QPushButton {
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #2A2A2A, stop:1 #1C1C1C);
    color: #F2F2F2;
    border: 1px solid #111111;
    border-top: 1px solid rgba(255, 255, 255, 18%);
    border-radius: 8px;
    padding: 8px 18px;
    font-family: 'Calibri';
    font-size: 12px;
    font-weight: bold;
}

QPushButton:hover {
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #333333, stop:1 #222222);
}

QPushButton:pressed {
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #161616, stop:1 #1C1C1C);
    border-top: 1px solid #111111;
}

QPushButton:disabled {
    background-color: #1A1A1A;
    border: 1px solid #1E1E1E;
    color: #4D4D4D;
}

QPushButton#primaryBtn {
    color: #FFFFFF;
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(224, 21, 0, 90%), stop:1 rgba(150, 12, 0, 85%));
    border: 1px solid rgb(150, 12, 0);
    border-top: 1px solid rgba(255, 255, 255, 35%);
    border-radius: 8px;
    padding: 8px 18px;
    font-size: 12px;
    letter-spacing: 1px;
}

QPushButton#primaryBtn:hover {
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #E01500, stop:1 rgba(170, 14, 0, 90%));
}

QPushButton#primaryBtn:pressed {
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(150, 12, 0, 90%), stop:1 rgba(120, 10, 0, 85%));
    border-top: 1px solid rgb(120, 10, 0);
}

QPushButton#primaryBtn:disabled {
    background-color: #1A1A1A;
    border: 1px solid #1E1E1E;
    color: #4D4D4D;
}

QPushButton#primaryBtn:disabled {
    background-color: rgba(255, 255, 255, 2%);
    border: 1px solid rgba(255, 255, 255, 4%);
    color: #4D4D4D;
}

/* ── Text areas ── */
QTextEdit, QPlainTextEdit {
    background-color: #1C1C1C;
    color: #F2F2F2;
    border: 1px solid #2A2A2A;
    border-radius: 4px;
    padding: 6px;
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 12px;
    selection-background-color: #C41200;
}

/* ── Labels ── */
QLabel {
    color: #F2F2F2;
    background-color: transparent;
}

QLabel#sectionHeader {
    color: #C41200;
    font-size: 13px;
    font-weight: bold;
    letter-spacing: 1px;
}

QLabel#dimLabel {
    color: #888888;
    font-size: 11px;
}

/* ── Group boxes ── */
QGroupBox {
    border: 1px solid #2A2A2A;
    border-radius: 6px;
    margin-top: 12px;
    padding-top: 8px;
    font-weight: bold;
    color: #888888;
    font-size: 11px;
    letter-spacing: 1px;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 6px;
    color: #888888;
}

/* ── Scroll bars ── */
QScrollBar:vertical {
    background-color: #1C1C1C;
    width: 8px;
    border-radius: 4px;
}

QScrollBar::handle:vertical {
    background-color: #333333;
    border-radius: 4px;
    min-height: 20px;
}

QScrollBar::handle:vertical:hover {
    background-color: #555555;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }

QScrollBar:horizontal {
    background-color: #1C1C1C;
    height: 8px;
    border-radius: 4px;
}

QScrollBar::handle:horizontal {
    background-color: #333333;
    border-radius: 4px;
    min-width: 20px;
}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

/* ── Splitter ── */
QSplitter::handle {
    background-color: #2A2A2A;
}

/* ── Line edit ── */
QLineEdit {
    background-color: #1C1C1C;
    color: #F2F2F2;
    border: 1px solid #2A2A2A;
    border-radius: 4px;
    padding: 5px 8px;
}

QLineEdit:focus {
    border-color: #C41200;
}

/* ── Combo box ── */
QComboBox {
    background-color: #222222;
    color: #F2F2F2;
    border: 1px solid #2A2A2A;
    border-radius: 4px;
    padding: 5px 8px;
}

QComboBox::drop-down {
    border: none;
}

QComboBox QAbstractItemView {
    background-color: #1C1C1C;
    border: 1px solid #2A2A2A;
    color: #F2F2F2;
    selection-background-color: #C41200;
}

/* ── Progress bar ── */
QProgressBar {
    background-color: #222222;
    border: 1px solid #2A2A2A;
    border-radius: 3px;
    text-align: center;
    color: transparent;
}

QProgressBar::chunk {
    background-color: #C41200;
    border-radius: 3px;
}

/* ── Status bar ── */
QStatusBar {
    background-color: #1C1C1C;
    color: #888888;
    border-top: 1px solid #2A2A2A;
    font-size: 11px;
}

/* ── Menu bar ── */
QMenuBar {
    background-color: #1C1C1C;
    color: #F2F2F2;
    border-bottom: 1px solid #2A2A2A;
}

QMenuBar::item:selected {
    background-color: #2A2A2A;
}

QMenu {
    background-color: #1C1C1C;
    border: 1px solid #2A2A2A;
    border-radius: 4px;
}

QMenu::item:selected {
    background-color: #C41200;
}

/* ── Tooltips ── */
QToolTip {
    background-color: #222222;
    color: #F2F2F2;
    border: 1px solid #2A2A2A;
    border-radius: 4px;
    padding: 4px 8px;
    font-size: 11px;
}

/* ── List widget (used in session panel) ── */
QListWidget {
    background-color: #161616;
    border: none;
    outline: none;
}

QListWidget::item {
    padding: 8px 10px;
    border-bottom: 1px solid #1E1E1E;
    color: #F2F2F2;
}

QListWidget::item:selected {
    background-color: #1C1C1C;
    border-left: 3px solid #C41200;
    color: #F2F2F2;
}

QListWidget::item:hover:!selected {
    background-color: #1A1A1A;
}

/* ── Mode switcher buttons ── */
/* Same Subtle Depth language, tighter padding. Radius 8px stays under half
   height of the ~24px checkable Show/Hide toggle in settings. */
QPushButton[checkable="true"] {
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #2A2A2A, stop:1 #1C1C1C);
    color: #888888;
    border: 1px solid #111111;
    border-top: 1px solid rgba(255, 255, 255, 18%);
    border-radius: 8px;
    padding: 4px 14px;
    font-family: 'Calibri';
    font-size: 11px;
    font-weight: bold;
    letter-spacing: 1px;
}

QPushButton[checkable="true"]:checked {
    color: #FFFFFF;
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(224, 21, 0, 90%), stop:1 rgba(150, 12, 0, 85%));
    border: 1px solid rgb(150, 12, 0);
    border-top: 1px solid rgba(255, 255, 255, 35%);
}

QPushButton[checkable="true"]:hover:!checked {
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #333333, stop:1 #222222);
    color: #F2F2F2;
}

/* ── Live DB tables (QTableWidget) ── */
QTableWidget {
    background-color: #161616;
    alternate-background-color: #1A1A1A;
    border: 1px solid #2A2A2A;
    gridline-color: #222222;
    font-family: 'Consolas', monospace;
    font-size: 11px;
}

QTableWidget::item { padding: 3px 6px; }

QTableWidget::item:selected {
    background-color: #C41200;
    color: #FFFFFF;
}

QHeaderView::section {
    background-color: #1C1C1C;
    color: #888888;
    border: none;
    border-right: 1px solid #2A2A2A;
    border-bottom: 1px solid #2A2A2A;
    padding: 4px 8px;
    font-size: 10px;
    font-weight: bold;
    letter-spacing: 1px;
}

/* ── Live DB tree (QTreeWidget) ── */
QTreeWidget {
    background-color: #161616;
    alternate-background-color: #1A1A1A;
    border: 1px solid #2A2A2A;
    font-family: 'Consolas', monospace;
    font-size: 11px;
}

QTreeWidget::item { padding: 3px 4px; }
QTreeWidget::item:selected { background-color: #C41200; color: #FFFFFF; }
"""
