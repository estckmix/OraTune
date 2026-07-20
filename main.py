#!/usr/bin/env python3
"""OraTune v2.2 — Entry point."""

from ui.main_window import MainWindow
from ui.app_theme import THEME
from services.ai_service import migrate_plaintext_keys
from PyQt6.QtWidgets import QApplication, QMessageBox
import os
import site
import sys
import traceback
from pathlib import Path

import structlog

from types import TracebackType

log = structlog.get_logger()


def _configure_logging() -> None:
    """Configure structlog once at startup — human-readable events to stderr."""
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.format_exc_info,
            structlog.dev.ConsoleRenderer(colors=False),
        ],
        logger_factory=structlog.PrintLoggerFactory(sys.stderr),
    )


# PyQt6-Charts installs its Qt6Charts.dll in the user site-packages Qt6\bin
# directory. On Windows, add it to the DLL search path so the import succeeds
# regardless of where PyQt6-Qt6 core DLLs live.
for _sp in site.getusersitepackages(), *site.getsitepackages():
    _dll_dir = Path(_sp) / "PyQt6" / "Qt6" / "bin"
    if _dll_dir.is_dir():
        os.add_dll_directory(str(_dll_dir))


def _excepthook(
    exc_type: type[BaseException],
    exc_value: BaseException,
    exc_tb: TracebackType | None,
) -> None:
    """Global handler — keeps the app alive and shows an error dialog."""
    msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    log.error("unhandled_exception", exc_info=(exc_type, exc_value, exc_tb))
    try:
        dlg = QMessageBox()
        dlg.setIcon(QMessageBox.Icon.Critical)
        dlg.setWindowTitle("Unexpected Error")
        dlg.setText(
            "An unexpected error occurred. The application will try to continue."
        )
        dlg.setDetailedText(msg)
        dlg.exec()
    except Exception:
        # Last-resort guard inside the excepthook itself: if even the error
        # dialog fails, there is nothing left to do but stay alive.
        pass


def main() -> None:
    _configure_logging()
    sys.excepthook = _excepthook
    migrate_plaintext_keys()

    app = QApplication(sys.argv)
    app.setApplicationName("OraTune")
    app.setOrganizationName("OraTune")
    app.setStyleSheet(THEME)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
