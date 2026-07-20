"""AWR Trend Analysis tab — time-series line chart drawn with QPainter."""

from datetime import datetime, timedelta
from typing import Callable

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QComboBox,
    QDateEdit,
)
from PyQt6.QtCore import Qt, QDate, QPointF
from PyQt6.QtGui import QColor, QFont, QPainter, QPaintEvent, QPen

from services.db_service import OracleConnection, OracleRow
from services.awr_trend_service import fetch_awr_trend
from ui.widgets.live import LiveWorker

_METRICS = {
    "Elapsed ms / Exec": "elapsed_ms_per_exec",
    "CPU ms / Exec": "cpu_ms_per_exec",
    "Buffer Gets / Exec": "buffer_gets_per_exec",
    "Disk Reads / Exec": "disk_reads_per_exec",
    "Executions": "executions",
}

_RANGES = ["Last 24 hours", "Last 7 days", "Last 30 days", "Custom…"]


class _LineChart(QWidget):
    """QPainter-based line chart — no QtCharts dependency."""

    def __init__(self) -> None:
        super().__init__()
        self._points: list[tuple[datetime, float]] = []
        self._y_label = ""
        self.setMinimumHeight(200)

    def set_data(self, points: list[tuple[datetime, float]], y_label: str = "") -> None:
        self._points = points
        self._y_label = y_label
        self.update()

    def paintEvent(self, a0: QPaintEvent | None) -> None:
        if not self._points:
            return

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        L, R, T, B = 75, 20, 20, 50  # margins
        pw, ph = w - L - R, h - T - B  # plot area size

        p.fillRect(0, 0, w, h, QColor("#1C1C1C"))

        times = [pt[0] for pt in self._points]
        values = [pt[1] for pt in self._points]

        t_min = min(times).timestamp()
        t_max = max(times).timestamp()
        v_min = min(values)
        v_max = max(values)

        t_range = t_max - t_min or 1.0
        v_pad = (v_max - v_min) * 0.1 or 1.0
        v_min -= v_pad
        v_max += v_pad
        v_range = v_max - v_min

        def sx(t: datetime) -> float:
            return L + (t.timestamp() - t_min) / t_range * pw

        def sy(v: float) -> float:
            return T + ph - (v - v_min) / v_range * ph

        # Grid lines
        grid_pen = QPen(QColor("#2A2A2A"))
        grid_pen.setWidth(1)
        p.setPen(grid_pen)
        for i in range(5):
            y = int(T + i * ph / 4)
            p.drawLine(L, y, L + pw, y)

        # Labels
        lbl_font = QFont("Segoe UI", 8)
        p.setFont(lbl_font)
        p.setPen(QColor("#888888"))

        self._draw_axis_labels(p, times, v_min, v_max, v_range, L, T, ph, sx)
        self._draw_series(p, sx, sy)

        p.end()

    def _draw_axis_labels(
        self,
        p: QPainter,
        times: list[datetime],
        v_min: float,
        v_max: float,
        v_range: float,
        L: int,
        T: int,
        ph: int,
        sx: "Callable[[datetime], float]",
    ) -> None:
        """Y-axis values, X-axis timestamps, and the rotated Y-axis title."""
        for i in range(5):
            v = v_max - i * v_range / 4
            y = int(T + i * ph / 4)
            txt = f"{v:.1f}" if v < 10_000 else f"{v:,.0f}"
            p.drawText(
                0,
                y - 8,
                L - 4,
                16,
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                txt,
            )

        n = min(5, len(self._points))
        step = max(1, (len(self._points) - 1) // max(n - 1, 1))
        for i in range(0, len(self._points), step):
            t = times[i]
            x = int(sx(t))
            txt = t.strftime("%m/%d\n%H:%M")
            p.drawText(
                x - 30,
                T + ph + 4,
                60,
                42,
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                txt,
            )

        p.save()
        p.translate(10, T + ph // 2)
        p.rotate(-90)
        p.drawText(-60, -8, 120, 16, Qt.AlignmentFlag.AlignCenter, self._y_label)
        p.restore()

    def _draw_series(
        self,
        p: QPainter,
        sx: "Callable[[datetime], float]",
        sy: "Callable[[float], float]",
    ) -> None:
        """The data line and its point dots."""
        line_pen = QPen(QColor("#C41200"))
        line_pen.setWidth(2)
        p.setPen(line_pen)
        pts = [QPointF(sx(t), sy(v)) for t, v in self._points]
        for i in range(len(pts) - 1):
            p.drawLine(pts[i], pts[i + 1])

        dot_pen = QPen(QColor("#C41200"))
        dot_pen.setWidth(5)
        p.setPen(dot_pen)
        for pt in pts:
            p.drawPoint(pt)


class AwrTrendTab(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._conn: OracleConnection | None = None
        self._worker: LiveWorker | None = None
        self._rows: list[OracleRow] = []
        self._build_ui()

    def set_conn(self, conn: OracleConnection) -> None:
        self._conn = conn

    def set_sql_id(self, sql_id: str) -> None:
        """Pre-populate SQL ID field and trigger a fetch (called by Top SQL tab)."""
        self._sql_id_edit.setText(sql_id)
        self._on_show_trend()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        layout.addLayout(self._build_controls_row())

        # ── No-data / error label ─────────────────────────────────────────────
        self._no_data_lbl = QLabel("Enter a SQL ID and click Show Trend")
        self._no_data_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._no_data_lbl.setObjectName("dimLabel")
        layout.addWidget(self._no_data_lbl)

        # ── Chart ─────────────────────────────────────────────────────────────
        self._chart = _LineChart()
        self._chart.hide()
        layout.addWidget(self._chart, 1)

        # ── Signal connections ────────────────────────────────────────────────
        self._show_btn.clicked.connect(self._on_show_trend)
        self._metric_combo.currentIndexChanged.connect(self._redraw_chart)
        self._range_combo.currentIndexChanged.connect(self._on_range_changed)
        self._sql_id_edit.textChanged.connect(
            lambda t: self._show_btn.setEnabled(bool(t.strip()))
        )

    def _build_controls_row(self) -> QHBoxLayout:
        """SQL ID input, metric/range selectors, and custom date pickers."""
        ctrl = QHBoxLayout()

        ctrl.addWidget(QLabel("SQL ID:"))
        self._sql_id_edit = QLineEdit()
        self._sql_id_edit.setPlaceholderText("e.g. 1a2b3c4d5e6f7")
        self._sql_id_edit.setFixedWidth(200)
        ctrl.addWidget(self._sql_id_edit)

        self._show_btn = QPushButton("Show Trend")
        self._show_btn.setObjectName("primaryBtn")
        self._show_btn.setEnabled(False)
        ctrl.addWidget(self._show_btn)

        ctrl.addWidget(QLabel("Metric:"))
        self._metric_combo = QComboBox()
        self._metric_combo.addItems(list(_METRICS.keys()))
        ctrl.addWidget(self._metric_combo)

        ctrl.addWidget(QLabel("Range:"))
        self._range_combo = QComboBox()
        self._range_combo.addItems(_RANGES)
        self._range_combo.setCurrentIndex(1)  # "Last 7 days" default
        ctrl.addWidget(self._range_combo)

        self._start_date = QDateEdit()
        self._start_date.setCalendarPopup(True)
        self._start_date.setDate(QDate.currentDate().addDays(-7))
        self._start_date.hide()
        ctrl.addWidget(self._start_date)

        self._end_date = QDateEdit()
        self._end_date.setCalendarPopup(True)
        self._end_date.setDate(QDate.currentDate())
        self._end_date.hide()
        ctrl.addWidget(self._end_date)

        ctrl.addStretch()
        return ctrl

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _on_range_changed(self) -> None:
        is_custom = self._range_combo.currentText() == "Custom…"
        self._start_date.setVisible(is_custom)
        self._end_date.setVisible(is_custom)

    def _time_range(self) -> tuple[datetime, datetime]:
        end = datetime.now()
        text = self._range_combo.currentText()
        if text == "Last 24 hours":
            return end - timedelta(hours=24), end
        if text == "Last 7 days":
            return end - timedelta(days=7), end
        if text == "Last 30 days":
            return end - timedelta(days=30), end
        sd = self._start_date.date()
        ed = self._end_date.date()
        return (
            datetime(sd.year(), sd.month(), sd.day()),
            datetime(ed.year(), ed.month(), ed.day(), 23, 59, 59),
        )

    def _on_show_trend(self) -> None:
        sql_id = self._sql_id_edit.text().strip()
        if not sql_id or self._conn is None:
            return
        self._show_btn.setEnabled(False)
        start, end = self._time_range()
        self._worker = LiveWorker(fetch_awr_trend, self._conn, sql_id, start, end)
        self._worker.finished.connect(self._on_data)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_data(self, rows: list[OracleRow]) -> None:
        self._rows = rows
        self._show_btn.setEnabled(True)
        if not rows:
            self._chart.hide()
            self._no_data_lbl.setText(
                "No AWR data found for this SQL ID and time range"
            )
            self._no_data_lbl.show()
            return
        self._no_data_lbl.hide()
        self._chart.show()
        self._redraw_chart()

    def _on_error(self, msg: str) -> None:
        self._show_btn.setEnabled(True)
        self._chart.hide()
        self._no_data_lbl.setText(f"Error: {msg[:120]}")
        self._no_data_lbl.show()

    def _redraw_chart(self) -> None:
        if not self._rows:
            return
        metric_key = _METRICS[self._metric_combo.currentText()]
        y_label = self._metric_combo.currentText()
        points = [(r["snap_time"], float(r[metric_key])) for r in self._rows]
        self._chart.set_data(points, y_label)
