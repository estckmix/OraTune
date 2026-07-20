"""Live DB widgets package. Provides LiveWorker for all live tabs."""

from typing import Callable

from PyQt6.QtCore import QThread, pyqtSignal


class LiveWorker(QThread):
    """Generic worker — run any blocking DB call off the main thread."""

    finished = pyqtSignal(object)  # emits result of fn(*args, **kwargs)
    error = pyqtSignal(str)  # emits str(exception)

    def __init__(
        self, fn: Callable[..., object], *args: object, **kwargs: object
    ) -> None:
        super().__init__()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs

    def run(self) -> None:
        try:
            self.finished.emit(self._fn(*self._args, **self._kwargs))
        except Exception as e:
            self.error.emit(str(e))
