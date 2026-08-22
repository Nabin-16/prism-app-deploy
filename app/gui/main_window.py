from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QActionGroup, QAction, QIcon, QPixmap
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QStackedWidget, QToolBar, QStatusBar,
    QLabel, QPushButton,
)

from app.gui.theme import DUSK, PAPER, build_qss
from app.gui.widgets import ModelBadge
from app.gui.screens.startup_screen import StartupScreen
from app.gui.screens.run_screen import RunScreen
from app.gui.screens.dashboard_screen import DashboardScreen
from app.gui.screens.settings_screen import SettingsScreen
from app.services import backend, app_state, supabase_sync

RESOURCES_DIR = Path(__file__).resolve().parents[1] / "resources"
LOGO_ICON_PATH = RESOURCES_DIR / "prism_logo.png"      # mark only, used as window/app icon
LOGO_WORDMARK_PATH = RESOURCES_DIR / "prism_text.png"  # mark + "PRISM" wordmark, used in the toolbar


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
        self.setWindowTitle("PRISM - Prompt-Reliability Benchmark")
        if LOGO_ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(LOGO_ICON_PATH)))
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

        # ---------- native chrome: toolbar / status bar (menu bar removed) ----------
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

        backend.ensure_bundled_seed()
        has_existing = bool(backend.models_with_data(backend.get_conn()))
        self.startup_screen.set_existing_results_available(has_existing)
        self._show_startup_chrome()
        self.outer_stack.setCurrentWidget(self.startup_screen)

        self._ollama_timer = QTimer(self)
        self._ollama_timer.timeout.connect(self._refresh_ollama_status)
        self._ollama_timer.start(8000)
        self._refresh_ollama_status()

    # ---------------- chrome construction ----------------

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Main")
        toolbar.setObjectName("AppToolBar")
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        self.addToolBar(toolbar)

        # Brand mark (leading, like a native app's toolbar icon) - the
        # icon-only mark, with the "PRISM" name set as real text beside it
        # rather than baked into a wordmark image.
        brand_icon = QLabel()
        brand_icon.setObjectName("BrandIcon")
        if LOGO_ICON_PATH.exists():
            pix = QPixmap(str(LOGO_ICON_PATH))
            if not pix.isNull():
                brand_icon.setPixmap(pix.scaledToHeight(32, Qt.TransformationMode.SmoothTransformation))
        toolbar.addWidget(brand_icon)

        brand_text = QLabel("PRISM")
        brand_text.setObjectName("BrandMark")
        toolbar.addWidget(brand_text)
        self.toolbar_separator = toolbar.addSeparator()

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
        self.toolbar_spacer = QWidget()
        self.toolbar_spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.toolbar_spacer_action = toolbar.addWidget(self.toolbar_spacer)

        self.model_badge = ModelBadge()
        self.model_badge_action = toolbar.addWidget(self.model_badge)

        self.change_model_btn = QPushButton("Change")
        self.change_model_btn.setObjectName("ChangeModelBtn")
        self.change_model_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.change_model_btn.clicked.connect(self._on_change_model_requested)
        self.change_model_btn_action = toolbar.addWidget(self.change_model_btn)

        # Widgets added to a QToolBar are wrapped in a QAction under the
        # hood; the toolbar's own layout re-shows the wrapped widget based
        # on THAT action's visibility whenever the toolbar is (re)shown or
        # polished, regardless of what setVisible() was called directly on
        # the widget. So hide/show must go through these actions, not the
        # widgets themselves, or the widgets flash back to visible the
        # moment the window is first shown.
        self.model_badge_action.setVisible(False)
        self.change_model_btn_action.setVisible(False)

        self.nav_dashboard.setChecked(True)

    def _build_status_bar(self) -> None:
        bar = QStatusBar()
        bar.setObjectName("AppStatusBar")
        self.setStatusBar(bar)
        self.ollama_status_lbl = QLabel("Ollama: checking\u2026")
        bar.addPermanentWidget(self.ollama_status_lbl)
        self.data_path_lbl = QLabel(f"Local data: {backend.APP_DIR}")
        bar.addWidget(self.data_path_lbl)

    # ------------------------------------------------------------ Qt events

    def showEvent(self, event) -> None:
        """Qt re-reveals explicitly-hidden child widgets the first time a
        top-level window is shown, which would otherwise undo the
        model-badge/Change-button hide() applied in __init__ (before
        main.py's window.show() ever runs). Re-apply whichever chrome
        state is correct for the screen currently on top once the window
        is actually on screen, so the startup screen never flashes them.
        """
        super().showEvent(event)
        if self.outer_stack.currentWidget() is self.startup_screen:
            self._show_startup_chrome()
        else:
            self._show_app_chrome()

    # ---------------- navigation ----------------

    def _show_startup_chrome(self) -> None:
        """On the startup screen, the toolbar shows only the brand mark - no Dashboard/Benchmark/Settings nav, no model badge, no status bar - since there's no active model or app state yet to navigate
        around."""
        for action in (self.nav_dashboard, self.nav_benchmark, self.nav_settings):
            action.setVisible(False)
        self.toolbar_separator.setVisible(False)
        self.toolbar_spacer_action.setVisible(False)
        self.model_badge_action.setVisible(False)
        self.change_model_btn_action.setVisible(False)
        self.statusBar().setVisible(False)

    def _show_app_chrome(self) -> None:
        for action in (self.nav_dashboard, self.nav_benchmark, self.nav_settings):
            action.setVisible(True)
        self.toolbar_separator.setVisible(True)
        self.toolbar_spacer_action.setVisible(True)
        self.model_badge_action.setVisible(True)
        self.change_model_btn_action.setVisible(True)
        self.statusBar().setVisible(True)

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

    def _on_model_chosen(self, model_tag: str) -> None:
        self._show_app_chrome()
        self.active_model = model_tag
        self.model_badge.set_model(backend.model_label(model_tag))
        self.dashboard_screen.set_model(model_tag)
        self.run_screen.preselect_model(model_tag)
        self.outer_stack.setCurrentWidget(self.app_shell)

        # Always land on the Benchmark screen after startup - if this model
        # already has local results, preselect_model() above has already
        # surfaced its own "Existing results found - View dashboard" prompt
        # there, so the user decides rather than being auto-redirected.
        self._show_tab("benchmark")

    def _on_skip_to_dashboard(self) -> None:
        self._show_app_chrome()
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

    def _on_change_model_requested(self) -> None:
        """'Change' button on the toolbar model badge - drops the user back
        onto the startup screen's model picker so they can switch the
        active model. The badge (and this button) are hidden on the
        startup screen itself, so this is only reachable from the other
        screens."""
        has_existing = bool(backend.models_with_data(backend.get_conn()))
        self.startup_screen.set_existing_results_available(has_existing)
        self._show_startup_chrome()
        self.outer_stack.setCurrentWidget(self.startup_screen)

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
        # chart title/legend/axis colors are picked per-theme at draw time,
        # so a live theme switch needs a repaint to actually show the fix
        if hasattr(self, "dashboard_screen"
                   ):
            self.dashboard_screen.refresh()