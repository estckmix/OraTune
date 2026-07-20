"""Main window — OraTune v2.2 layout with session sidebar and Live DB mode."""

from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QTabWidget,
    QStatusBar,
    QFileDialog,
    QProgressBar,
    QFrame,
    QMessageBox,
    QStackedWidget,
    QButtonGroup,
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QAction, QCloseEvent, QPixmap, QResizeEvent

import sys
from pathlib import Path

from core.models import AnalysisSession, Finding
from services.analysis_service import AnalysisWorker
from services import session_service, report_service
from services.ai_service import get_api_key, get_active_provider_label
from services.db_service import OracleConnection
from ui.widgets.upload_panel import UploadPanel
from ui.widgets.diff_view import DiffView
from ui.widgets.plan_view import PlanView
from ui.widgets.findings_view import FindingsView
from ui.widgets.recommendations_view import RecommendationsView
from ui.widgets.session_panel import SessionPanel
from ui.dialogs.settings_dialog import SettingsDialog
from ui.dialogs.annotation_dialog import AnnotationDialog
from ui.dialogs.connection_dialog import ConnectionDialog
from ui.dialogs.ora_error_dialog import OraErrorDialog
from ui.widgets.live.connection_tab import ConnectionTab
from ui.widgets.live.explain_plan_tab import ExplainPlanTab
from ui.widgets.live.top_sql_tab import TopSqlTab
from ui.widgets.live.stats_health_tab import StatsHealthTab
from ui.widgets.live.baselines_tab import BaselinesTab
from ui.widgets.live.scheduler_tab import SchedulerTab
from ui.widgets.live.awr_trend_tab import AwrTrendTab
from ui.widgets.live.index_advisor_tab import IndexAdvisorTab
from ui.widgets.batch_panel import BatchPanel


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("OraTune  ·  SQL Performance Analyzer")
        self.setMinimumSize(1280, 800)
        self.resize(1440, 900)

        self._baseline_files: dict[str, list[str]] = {}
        self._current_files: dict[str, list[str]] = {}
        self._current_session: AnalysisSession | None = None
        self._live_tab_gap: int | None = None
        self._justify_pending = False
        self._worker: AnalysisWorker | None = None
        self._oracle_conn = OracleConnection()

        self._build_menu()
        self._build_ui()
        self._build_status_bar()
        self._session_panel.refresh()

    # ── Menu ──────────────────────────────────────────────────────────────────

    def _build_menu(self) -> None:
        mb = self.menuBar()
        assert mb is not None

        file_menu = mb.addMenu("File")
        assert file_menu is not None
        new_act = QAction("New Analysis", self)
        new_act.setShortcut("Ctrl+N")
        new_act.triggered.connect(self._reset)
        file_menu.addAction(new_act)
        file_menu.addSeparator()
        export_act = QAction("Export Report...", self)
        export_act.setShortcut("Ctrl+E")
        export_act.triggered.connect(self._export_report)
        file_menu.addAction(export_act)
        file_menu.addSeparator()
        quit_act = QAction("Quit", self)
        quit_act.setShortcut("Ctrl+Q")
        quit_act.triggered.connect(self.close)
        file_menu.addAction(quit_act)

        tools_menu = mb.addMenu("Tools")
        assert tools_menu is not None
        settings_act = QAction("Settings / API Key...", self)
        settings_act.triggered.connect(self._open_settings)
        tools_menu.addAction(settings_act)
        tools_menu.addSeparator()
        ora_ref_act = QAction("ORA- Error Reference…", self)
        ora_ref_act.setShortcut("Ctrl+Shift+O")
        ora_ref_act.triggered.connect(lambda: self._open_ora_reference())
        tools_menu.addAction(ora_ref_act)

        help_menu = mb.addMenu("Help")
        assert help_menu is not None
        about_act = QAction("About OraTune", self)
        about_act.triggered.connect(self._show_about)
        help_menu.addAction(about_act)

    # ── UI construction ────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_header())

        # Body: sidebar + main
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        self._session_panel = SessionPanel()
        self._session_panel.session_selected.connect(self._load_session)
        # collapsing the sidebar widens the live tab bar without a window resize
        self._session_panel.collapsed_changed.connect(
            lambda _collapsed: self._request_justify()
        )
        body.addWidget(self._session_panel)

        # Separator line
        sep = QFrame()
        sep.setFixedWidth(1)
        sep.setStyleSheet("background: #2A2A2A;")
        body.addWidget(sep)

        body.addWidget(self._build_main_area(), 1)
        root.addLayout(body, 1)

    def _build_header(self) -> QFrame:
        header = QFrame()
        header.setFixedHeight(54)
        header.setStyleSheet(
            "QFrame { background-color: #1C1C1C; border-bottom: 1px solid #2A2A2A; }"
        )
        layout = QHBoxLayout(header)
        layout.setContentsMargins(16, 0, 16, 0)

        layout.addWidget(self._build_logo())
        layout.addStretch()

        # Mode switcher
        self._file_mode_btn = QPushButton("FILE ANALYSIS")
        self._file_mode_btn.setCheckable(True)
        self._file_mode_btn.setChecked(True)
        self._file_mode_btn.setFixedHeight(30)

        self._batch_mode_btn = QPushButton("BATCH")
        self._batch_mode_btn.setCheckable(True)
        self._batch_mode_btn.setFixedHeight(30)

        self._live_mode_btn = QPushButton("LIVE DB")
        self._live_mode_btn.setCheckable(True)
        self._live_mode_btn.setFixedHeight(30)

        self._mode_group = QButtonGroup(self)
        self._mode_group.addButton(self._file_mode_btn)
        self._mode_group.addButton(self._batch_mode_btn)
        self._mode_group.addButton(self._live_mode_btn)
        self._mode_group.setExclusive(True)

        layout.addWidget(self._file_mode_btn)
        layout.addSpacing(4)
        layout.addWidget(self._batch_mode_btn)
        layout.addSpacing(4)
        layout.addWidget(self._live_mode_btn)
        layout.addSpacing(16)

        self._db_status_label = QLabel("● OFFLINE")
        self._db_status_label.setStyleSheet(
            "color: #555555; font-size: 10px; letter-spacing: 1.5px; background: transparent;"
        )
        self._db_status_label.hide()

        self._api_status_label = QLabel()
        self._api_status_label.setStyleSheet("background: transparent;")
        layout.addWidget(self._api_status_label)
        self._refresh_api_status()

        self._file_mode_btn.clicked.connect(self._switch_to_file_mode)
        self._batch_mode_btn.clicked.connect(self._switch_to_batch_mode)
        self._live_mode_btn.clicked.connect(self._switch_to_live_mode)
        layout.addWidget(self._db_status_label)

        return header

    def _build_logo(self) -> QWidget:
        """Logo image (assets/Logo.png), frozen-path aware."""
        logo_widget = QWidget()
        logo_widget.setStyleSheet("background: transparent;")
        logo_layout = QVBoxLayout(logo_widget)
        logo_layout.setContentsMargins(0, 0, 0, 0)
        logo_layout.setSpacing(0)
        name_label = QLabel()
        if getattr(sys, "frozen", False):
            # sys._MEIPASS only exists in PyInstaller binaries, hence getattr
            base = Path(getattr(sys, "_MEIPASS"))
        else:
            base = Path(__file__).parent.parent
        name_label.setPixmap(
            QPixmap(str(base / "assets" / "Logo.png")).scaledToHeight(
                38, Qt.TransformationMode.SmoothTransformation
            )
        )
        name_label.setStyleSheet("background: transparent;")
        logo_layout.addWidget(name_label)
        return logo_widget

    def _build_main_area(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._mode_stack = QStackedWidget()

        self._mode_stack.addWidget(self._build_file_page())

        # ── Page 1: Batch Analysis ────────────────────────────────────────────
        self._batch_panel = BatchPanel()
        self._mode_stack.addWidget(self._batch_panel)

        self._mode_stack.addWidget(self._build_live_page())
        # the live page's geometry is stale until it is shown, so re-justify
        # its tab bar whenever the visible mode changes
        self._mode_stack.currentChanged.connect(lambda _index: self._request_justify())

        layout.addWidget(self._mode_stack, 1)
        return widget

    def _build_file_page(self) -> QWidget:
        """Page 0: upload panels, progress bar, and result tabs."""
        file_page = QWidget()
        fp_layout = QVBoxLayout(file_page)
        fp_layout.setContentsMargins(0, 0, 0, 0)
        fp_layout.setSpacing(0)

        upload_row = QWidget()
        upload_row.setObjectName("uploadRow")
        # scope to this widget only: bare declarations act as a universal
        # selector and override child styling (e.g. the ANALYZE red gradient)
        upload_row.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        upload_row.setStyleSheet(
            "#uploadRow { background: #111111; border-bottom: 1px solid #1E1E1E; }"
        )
        ur_layout = QHBoxLayout(upload_row)
        ur_layout.setContentsMargins(12, 10, 12, 10)
        ur_layout.setSpacing(10)
        ur_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._baseline_panel = UploadPanel("BASELINE", "#1a3a1a", "#2ea043")
        self._baseline_panel.files_changed.connect(self._on_baseline_changed)
        ur_layout.addWidget(self._baseline_panel)

        self._analyze_btn = QPushButton("ANALYZE")
        self._analyze_btn.setObjectName("primaryBtn")
        self._analyze_btn.setFixedSize(110, 42)
        self._analyze_btn.setEnabled(False)
        self._analyze_btn.clicked.connect(self._run_analysis)
        self._analyze_btn.setToolTip(
            "Upload at least one file to each panel, then click to analyze"
        )
        # top offset = panel title height + spacing, so the button's top edge
        # lines up with the top of the one-line file fields beside it
        analyze_box = QWidget()
        ab_layout = QVBoxLayout(analyze_box)
        ab_layout.setContentsMargins(0, 21, 0, 0)
        ab_layout.setSpacing(0)
        ab_layout.addWidget(self._analyze_btn)
        ab_layout.addStretch()
        ur_layout.addWidget(analyze_box)

        self._current_panel = UploadPanel("CURRENT / DEGRADED", "#3a1515", "#C41200")
        self._current_panel.files_changed.connect(self._on_current_changed)
        ur_layout.addWidget(self._current_panel)

        fp_layout.addWidget(upload_row)

        self._progress = QProgressBar()
        self._progress.setFixedHeight(3)
        self._progress.setTextVisible(False)
        self._progress.setRange(0, 0)
        self._progress.hide()
        fp_layout.addWidget(self._progress)

        self._tabs = QTabWidget()
        self._tabs.setEnabled(False)
        self._diff_view = DiffView()
        self._plan_view = PlanView()
        self._findings_view = FindingsView()
        self._findings_view.annotation_requested.connect(self._open_annotation)
        self._findings_view.ora_code_clicked.connect(self._open_ora_reference)
        self._rec_view = RecommendationsView()
        self._tabs.addTab(self._diff_view, "Code Diff")
        self._tabs.addTab(self._plan_view, "Execution Plans")
        self._tabs.addTab(self._findings_view, "Findings")
        self._tabs.addTab(self._rec_view, "Recommendations")
        fp_layout.addWidget(self._tabs, 1)

        return file_page

    def _build_live_page(self) -> QWidget:
        """Page 2: live-DB tab set."""
        live_page = QWidget()
        lp_layout = QVBoxLayout(live_page)
        lp_layout.setContentsMargins(0, 0, 0, 0)
        lp_layout.setSpacing(0)

        self._live_tabs = QTabWidget()
        self._live_tabs.setEnabled(False)

        self._conn_tab = ConnectionTab()
        self._conn_tab.disconnect_requested.connect(self._on_disconnect_clicked)
        self._explain_tab = ExplainPlanTab()
        self._top_sql_tab = TopSqlTab()
        self._top_sql_tab.set_explain_tab(
            self._explain_tab,
            lambda: self._live_tabs.setCurrentWidget(self._explain_tab),
        )
        self._awr_trend_tab = AwrTrendTab()
        self._top_sql_tab.set_trend_tab(
            self._awr_trend_tab,
            lambda: self._live_tabs.setCurrentWidget(self._awr_trend_tab),
        )
        self._index_advisor_tab = IndexAdvisorTab()
        self._stats_tab = StatsHealthTab()
        self._baselines_tab = BaselinesTab()
        self._scheduler_tab = SchedulerTab()

        self._live_tabs.addTab(self._conn_tab, "Connection")
        self._live_tabs.addTab(self._explain_tab, "Explain Plan")
        self._live_tabs.addTab(self._top_sql_tab, "Top SQL")
        self._live_tabs.addTab(self._awr_trend_tab, "AWR Trends")
        self._live_tabs.addTab(self._index_advisor_tab, "Index Advisor")
        self._live_tabs.addTab(self._stats_tab, "Stats Health")
        self._live_tabs.addTab(self._baselines_tab, "Plan Baselines")
        self._live_tabs.addTab(self._scheduler_tab, "Scheduler")

        lp_layout.addWidget(self._live_tabs, 1)
        return live_page

    def _request_justify(self) -> None:
        """Defer justification one event-loop cycle so layout geometry is valid.

        Widget widths are stale inside resize/switch handlers; the stacked
        layout applies real geometry only after the pending layout events run.
        Requests within the same cycle are coalesced into one run.
        """
        if self._justify_pending:
            return
        self._justify_pending = True
        QTimer.singleShot(0, self._run_justify)

    def _run_justify(self) -> None:
        self._justify_pending = False
        self._justify_live_tabs()

    def _justify_live_tabs(self) -> None:
        """Spread the Live DB tab buttons evenly across the full bar width.

        The buttons keep their natural size; leftover bar width becomes equal
        gaps, flush to both edges. Only the margins are set here — dynamic
        geometry cannot live in the static QSS file; all visual styling stays
        in app_theme. tabRect() includes the QSS margin, and repolish of a
        visible bar is deferred, so subtract the margins known to be applied
        rather than re-measuring at zero margin.
        """
        if not self._live_tabs.isVisible():
            return
        bar = self._live_tabs.tabBar()
        if bar is None:
            return
        count = bar.count()
        if count < 2:
            return
        # app_theme applies 8px margin-right to every tab; our own sheet
        # applies the computed gap to all but the last
        prior = (
            8 * count
            if self._live_tab_gap is None
            else self._live_tab_gap * (count - 1)
        )
        content = sum(bar.tabRect(i).width() for i in range(count)) - prior
        avail = self._live_tabs.width() - 10  # QSS tab-bar left offset
        gap = max(8, (avail - content) // (count - 1))
        if gap == self._live_tab_gap:
            return
        self._live_tab_gap = gap
        bar.setStyleSheet(
            f"QTabBar::tab {{ margin-right: {gap}px; }} "
            "QTabBar::tab:last { margin-right: 0px; }"
        )

    def resizeEvent(self, a0: QResizeEvent | None) -> None:
        super().resizeEvent(a0)
        self._request_justify()

    def _build_status_bar(self) -> None:
        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self._status.showMessage("Ready  ·  Upload baseline and current files to begin")

    # ── Slots ──────────────────────────────────────────────────────────────────

    def _refresh_api_status(self) -> None:
        key = get_api_key()
        if key:
            label = get_active_provider_label()
            self._api_status_label.setText(f"● AI-POWERED · {label}")
            self._api_status_label.setStyleSheet(
                "color: #C41200; font-size: 10px; font-weight: bold; "
                "letter-spacing: 1.5px; background: transparent;"
            )
        else:
            self._api_status_label.setText("● OFFLINE MODE")
            self._api_status_label.setStyleSheet(
                "color: #555555; font-size: 10px; letter-spacing: 1.5px; background: transparent;"
            )

    def _on_baseline_changed(self, files: dict[str, list[str]]) -> None:
        self._baseline_files = files
        self._check_ready()

    def _on_current_changed(self, files: dict[str, list[str]]) -> None:
        self._current_files = files
        self._check_ready()

    def _check_ready(self) -> None:
        ready = bool(self._baseline_files) and bool(self._current_files)
        self._analyze_btn.setEnabled(ready)

    def _run_analysis(self) -> None:
        self._analyze_btn.setEnabled(False)
        self._tabs.setEnabled(False)
        self._progress.show()
        self._status.showMessage("Analyzing...")

        self._worker = AnalysisWorker(self._baseline_files, self._current_files)
        self._worker.progress.connect(self._status.showMessage)
        self._worker.finished.connect(self._on_analysis_done)
        self._worker.error.connect(self._on_analysis_error)
        self._worker.start()

    def _on_analysis_done(self, session: AnalysisSession) -> None:
        self._current_session = session
        self._progress.hide()
        self._tabs.setEnabled(True)

        self._diff_view.load_results(session)
        self._plan_view.load_results(session)
        self._findings_view.load_results(session)
        self._rec_view.load_results(session)

        self._tabs.setCurrentIndex(2)
        self._analyze_btn.setEnabled(True)
        self._session_panel.refresh()

        n = len(session.findings)
        self._status.showMessage(
            f"Analysis complete  ·  {n} finding{'s' if n != 1 else ''} identified  ·  Session saved"
        )

    def _on_analysis_error(self, message: str) -> None:
        self._progress.hide()
        self._check_ready()
        self._status.showMessage(f"Error: {message[:80]}")
        QMessageBox.critical(self, "Analysis Error", message)

    def _load_session(self, session_id: str) -> None:
        session = session_service.load(session_id)
        if session is None:
            self._status.showMessage("Could not load session")
            return
        self._current_session = session
        self._tabs.setEnabled(True)
        self._diff_view.load_results(session)
        self._plan_view.load_results(session)
        self._findings_view.load_results(session)
        self._rec_view.load_results(session)
        self._tabs.setCurrentIndex(2)
        self._check_ready()
        self._status.showMessage(
            f"Session loaded  ·  {len(session.findings)} finding(s)"
        )

    def _open_annotation(self, finding: Finding) -> None:
        if self._current_session is None:
            return
        dlg = AnnotationDialog(finding, self)
        if dlg.exec():
            finding.annotation = dlg.annotation_text()
            session_service.save(self._current_session)
            self._findings_view.refresh_card_annotation(finding)
            self._status.showMessage("Note saved")

    def _reset(self) -> None:
        self._baseline_panel.clear()
        self._current_panel.clear()
        self._baseline_files = {}
        self._current_files = {}
        self._current_session = None
        self._tabs.setEnabled(False)
        self._analyze_btn.setEnabled(False)
        self._diff_view.clear()
        self._plan_view.clear()
        self._findings_view.clear()
        self._rec_view.clear()
        self._status.showMessage("Ready  ·  Upload baseline and current files to begin")

    def _open_settings(self) -> None:
        dlg = SettingsDialog(self)
        if dlg.exec():
            self._refresh_api_status()

    def _open_ora_reference(self, code: str = "") -> None:
        dlg = OraErrorDialog(self, initial_code=code)
        dlg.exec()

    def _export_report(self) -> None:
        if not self._current_session:
            QMessageBox.information(
                self, "No Results", "Run an analysis first before exporting."
            )
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Report", "oratune_report.html", "HTML Files (*.html)"
        )
        if path:
            ok = report_service.export_html(self._current_session, path)
            if ok:
                self._status.showMessage(f"Report exported to {path}")
                QMessageBox.information(self, "Exported", f"Report saved to:\n{path}")
            else:
                QMessageBox.warning(
                    self,
                    "Export Failed",
                    "Could not generate report. Check the console for details.",
                )

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            "About OraTune",
            "<h3>OraTune v2.2</h3>"
            "<p>Oracle SQL/PLSQL Performance Regression Analysis Tool</p>"
            "<p>File analysis, Batch Analysis, Live DB monitoring, "
            "and ORA- Error Reference.</p>"
            "<p><b>Modes:</b> Offline (rules-based) · AI-Powered (multi-provider)</p>",
        )

    def _switch_to_file_mode(self) -> None:
        self._mode_stack.setCurrentIndex(0)
        self._api_status_label.show()
        self._db_status_label.hide()
        self._status.showMessage("File Analysis mode")

    def _switch_to_batch_mode(self) -> None:
        self._mode_stack.setCurrentWidget(self._batch_panel)
        self._api_status_label.show()
        self._db_status_label.hide()
        self._status.showMessage("Batch Analysis mode")

    def _switch_to_live_mode(self) -> None:
        if not self._oracle_conn.is_connected:
            self._open_connection_dialog()
        else:
            self._mode_stack.setCurrentIndex(2)
            self._api_status_label.hide()
            self._db_status_label.show()

    def _open_connection_dialog(self) -> None:
        dlg = ConnectionDialog(self)
        if dlg.exec():
            profile = dlg.profile()
            if profile:
                try:
                    self._oracle_conn.connect(profile)
                    self._on_db_connected()
                except Exception as e:
                    self._status.showMessage(f"Connection failed: {str(e)[:80]}")
                    self._file_mode_btn.setChecked(True)
                    self._mode_stack.setCurrentIndex(0)
        else:
            self._file_mode_btn.setChecked(True)
            self._mode_stack.setCurrentIndex(0)

    def _on_db_connected(self) -> None:
        p = self._oracle_conn.profile
        assert p is not None  # only called right after a successful connect
        svc = p.alias if p.connection_type == "tns" else f"{p.host}/{p.service}"
        self._db_status_label.setText(f"● CONNECTED · {svc}")
        self._db_status_label.setStyleSheet(
            "color: #2ea043; font-size: 10px; font-weight: bold; "
            "letter-spacing: 1.5px; background: transparent;"
        )
        self._live_tabs.setEnabled(True)
        self._mode_stack.setCurrentIndex(2)
        self._api_status_label.hide()
        self._db_status_label.show()
        self._explain_tab.set_conn(self._oracle_conn)
        self._top_sql_tab.set_conn(self._oracle_conn)
        self._awr_trend_tab.set_conn(self._oracle_conn)
        self._index_advisor_tab.set_conn(self._oracle_conn)
        self._stats_tab.set_conn(self._oracle_conn)
        self._baselines_tab.set_conn(self._oracle_conn)
        self._scheduler_tab.set_conn(self._oracle_conn)
        self._conn_tab.refresh(self._oracle_conn)
        self._status.showMessage(f"Connected to {svc}")

    def _on_disconnect_clicked(self) -> None:
        """Disconnect and return to the initial Live DB connect screen."""
        self._on_db_disconnected()
        self._open_connection_dialog()

    def _on_db_disconnected(self) -> None:
        self._oracle_conn.disconnect()
        self._db_status_label.setText("● DISCONNECTED")
        self._db_status_label.setStyleSheet(
            "color: #f85149; font-size: 10px; letter-spacing: 1.5px; background: transparent;"
        )
        self._live_tabs.setEnabled(False)
        self._status.showMessage("Disconnected from Oracle DB")

    def closeEvent(self, a0: QCloseEvent | None) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._worker.quit()
            self._worker.wait(3000)
        if self._oracle_conn.is_connected:
            self._oracle_conn.disconnect()
        super().closeEvent(a0)
