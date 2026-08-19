from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QActionGroup, QAction
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QStackedWidget, QToolBar, QStatusBar,
    QLabel, QPushButton, QMessageBox,
)

from app.gui.theme import DUSK, PAPER, build_qss
from app.gui.widgets import ModelBadge
from app.gui.screens.startup_screen import StartupScreen
from app.gui.screens.run_screen import RunScreen
from app.gui.screens.dashboard_screen import DashboardScreen
from app.gui.screens.settings_screen import SettingsScreen
from app.services import backend, app_state, supabase_sync


class MainWindow(QMainWindow):
    """
    PRISM opens on a full-window startup screen (connect to Ollama, choose
    the active model). Once a model is chosen the real app shell takes over:
    a native menu bar + toolbar + status bar (genuine OS-style desktop chrome,
    not a sidebar-in-a-webpage), with Dashboard / Benchmark / Settings as
    toolbar destinations. The Dashboard and Benchmark screens are always
    scoped to whichever single model is currently active.
    """

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("PRISM \u2014 Prompt-Reliability Benchmark")
        self.resize(1220, 780)
        self.setMinimumSize(1000, 660)

        self.active_model: str | None = None
        self._theme = app_state.get_theme()

        root = QWidget()
        root.setObjectName("AppRoot")
        self.setCentralWidget(root)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # ---------- outer switcher: startup <-> app shell ----------
        self.outer_stack = QStackedWidget()
        root_layout.addWidget(self.outer_stack)

        self.startup_screen = StartupScreen()
        self.outer_stack.addWidget(self.startup_screen)

        self.app_shell = QWidget()
        shell_lay = QVBoxLayout(self.app_shell)
        shell_lay.setContentsMargins(0, 0, 0, 0)
        shell_lay.setSpacing(0)

        self.content_stack = QStackedWidget()
        self.dashboard_screen = DashboardScreen()
        self.run_screen = RunScreen()
        self.settings_screen = SettingsScreen()
        self.content_stack.addWidget(self.dashboard_screen)
        self.content_stack.addWidget(self.run_screen)
        self.content_stack.addWidget(self.settings_screen)
        shell_lay.addWidget(self.content_stack)

        self.outer_stack.addWidget(self.app_shell)

        # ---------- native chrome: menu bar / toolbar / status bar ----------
        self._build_menu_bar()
        self._build_toolbar()
        self._build_status_bar()

        # ---------- wiring ----------
        self.startup_screen.model_chosen.connect(self._on_model_chosen)
        self.startup_screen.skip_to_dashboard.connect(self._on_skip_to_dashboard)
        self.run_screen.run_completed.connect(self._on_run_completed)
        self.run_screen.continue_requested.connect(lambda: self._show_tab("dashboard"))
        self.dashboard_screen.benchmark_requested.connect(self._on_benchmark_requested)
        self.settings_screen.theme_changed.connect(self.apply_theme)

        self.settings_screen.set_active(self._theme)
        self.apply_theme(self._theme)

        has_existing = bool(backend.models_with_data(backend.get_conn()))
        self.startup_screen.set_existing_results_available(has_existing)
        self.outer_stack.setCurrentWidget(self.startup_screen)

        self._ollama_timer = QTimer(self)
        self._ollama_timer.timeout.connect(self._refresh_ollama_status)
        self._ollama_timer.start(8000)
        self._refresh_ollama_status()

    # ---------------- chrome construction ----------------

    def _build_menu_bar(self) -> None:
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("&File")
        change_model_action = QAction("Change active model\u2026", self)
        change_model_action.triggered.connect(self._go_to_startup)
        file_menu.addAction(change_model_action)
        file_menu.addSeparator()
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        view_menu = menu_bar.addMenu("&View")
        theme_group = QActionGroup(self)
        theme_group.setExclusive(True)
        self.dusk_action = QAction("Dusk (dark)", self, checkable=True)
        self.paper_action = QAction("Paper (light)", self, checkable=True)
        for a in (self.dusk_action, self.paper_action):
            theme_group.addAction(a)
            view_menu.addAction(a)
        self.dusk_action.triggered.connect(lambda: self.apply_theme("dusk"))
        self.paper_action.triggered.connect(lambda: self.apply_theme("paper"))

        help_menu = menu_bar.addMenu("&Help")
        about_action = QAction("About PRISM", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Main")
        toolbar.setObjectName("AppToolBar")
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        self.addToolBar(toolbar)

        nav_group = QActionGroup(self)
        nav_group.setExclusive(True)

        self.nav_dashboard = QAction("Dashboard", self, checkable=True)
        self.nav_dashboard.triggered.connect(lambda: self._show_tab("dashboard"))
        self.nav_benchmark = QAction("Benchmark", self, checkable=True)
        self.nav_benchmark.triggered.connect(lambda: self._show_tab("benchmark"))
        self.nav_settings = QAction("Settings", self, checkable=True)
        self.nav_settings.triggered.connect(lambda: self._show_tab("settings"))

        for a in (self.nav_dashboard, self.nav_benchmark, self.nav_settings):
            nav_group.addAction(a)
            toolbar.addAction(a)

        # expanding spacer pushes the model badge / change button to the
        # right edge of the toolbar, like a native app's trailing toolbar items
        from PySide6.QtWidgets import QSizePolicy
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)

        self.model_badge = ModelBadge()
        toolbar.addWidget(self.model_badge)

        self.change_model_btn = QPushButton("Change")
        self.change_model_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.change_model_btn.clicked.connect(self._go_to_startup)
        toolbar.addWidget(self.change_model_btn)

        self.nav_dashboard.setChecked(True)

    def _build_status_bar(self) -> None:
        bar = QStatusBar()
        bar.setObjectName("AppStatusBar")
        self.setStatusBar(bar)
        self.ollama_status_lbl = QLabel("Ollama: checking\u2026")
        bar.addPermanentWidget(self.ollama_status_lbl)
        self.data_path_lbl = QLabel(f"Local data: {backend.APP_DIR}")
        bar.addWidget(self.data_path_lbl)

    # ---------------- navigation ----------------

    def _show_tab(self, key: str) -> None:
        mapping = {
            "dashboard": (self.dashboard_screen, self.nav_dashboard),
            "benchmark": (self.run_screen, self.nav_benchmark),
            "settings": (self.settings_screen, self.nav_settings),
        }
        widget, action = mapping[key]
        if key == "dashboard":
            self.dashboard_screen.refresh()
        action.setChecked(True)
        self.content_stack.setCurrentWidget(widget)

    def _go_to_startup(self) -> None:
        self.outer_stack.setCurrentWidget(self.startup_screen)

    def _on_model_chosen(self, model_tag: str) -> None:
        self.active_model = model_tag
        self.model_badge.set_model(backend.model_label(model_tag))
        self.dashboard_screen.set_model(model_tag)
        self.run_screen.preselect_model(model_tag)
        self.outer_stack.setCurrentWidget(self.app_shell)

        if backend.has_data(backend.get_conn(), model_tag):
            self._show_tab("dashboard")
        else:
            self._show_tab("benchmark")

    def _on_skip_to_dashboard(self) -> None:
        conn = backend.get_conn()
        model_tag = app_state.get_selected_model()
        if not model_tag or not backend.has_data(conn, model_tag):
            data = backend.models_with_data(conn)
            model_tag = next(iter(data), None)
        if model_tag:
            self.active_model = model_tag
            app_state.set_selected_model(model_tag)
            self.model_badge.set_model(backend.model_label(model_tag))
            self.dashboard_screen.set_model(model_tag)
            self.run_screen.preselect_model(model_tag)
        self.outer_stack.setCurrentWidget(self.app_shell)
        self._show_tab("dashboard")

    def _on_run_completed(self, model_tag: str) -> None:
        # Refresh regardless of whether this was the active model (a re-run)
        # or a "compare" target model run from the dashboard's compare drawer.
        self.dashboard_screen.refresh()
        self._maybe_auto_sync(model_tag)

    def _on_benchmark_requested(self, model_tag: str) -> None:
        if not model_tag:
            return
        self.run_screen.preselect_model(model_tag)
        self._show_tab("benchmark")

    def _show_about(self) -> None:
        QMessageBox.information(
            self, "About PRISM",
            "PRISM \u2014 Prompt-Reliability Benchmark\n\n"
            "Measures how reliably small language models answer the same "
            "question phrased five semantically-equivalent ways, running "
            "entirely against a local Ollama installation.\n\n"
            "Engine: prism_core (Qt-free) \u00b7 GUI: PySide6",
        )

    def _refresh_ollama_status(self) -> None:
        if backend.ollama_available():
            self.ollama_status_lbl.setText("\u25cf Ollama online")
        else:
            self.ollama_status_lbl.setText("\u25cb Ollama offline")

    # ---------------- cloud sync ----------------

    def _maybe_auto_sync(self, model_tag: str) -> None:
        """Silently mirrors the run that just finished to the project's
        shared Supabase store (hardcoded in prism_core/config.py). No-op if
        that project isn't configured; failures show briefly in the status
        bar but never interrupt the app."""
        if not supabase_sync.is_configured():
            return
        conn = backend.get_conn()
        info = backend.run_info(conn, model_tag)
        if not info:
            return
        worker = backend.SyncWorker(mode="single", benchmark_run_id=info["benchmark_run_id"], parent=self)
        worker.finished_ok.connect(self._on_sync_finished)
        self._sync_worker = worker  # keep a reference so it isn't GC'd mid-run
        worker.start()

    def _on_sync_finished(self, ok: bool, message: str) -> None:
        if ok:
            self.statusBar().showMessage("Synced to Supabase.", 4000)
        else:
            self.statusBar().showMessage(f"Supabase sync failed: {message}", 6000)

    # ---------------- theme ----------------

    def apply_theme(self, name: str) -> None:
        self._theme = name
        app_state.set_theme(name)
        palette = DUSK if name == "dusk" else PAPER
        self.setStyleSheet(build_qss(palette))
        self.settings_screen.set_active(name)
        self.dusk_action.setChecked(name == "dusk")
        self.paper_action.setChecked(name == "paper")
        # chart title/legend/axis colors are picked per-theme at draw time,
        # so a live theme switch needs a repaint to actually show the fix
        if hasattr(self, "dashboard_screen"):
            self.dashboard_screen.refresh()