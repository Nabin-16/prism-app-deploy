from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QFrame, QScrollArea, QLineEdit, QProgressBar,
)

from app.gui.widgets import pill
from app.services import backend, app_state
from app.services.backend import PullWorker


class ModelRow(QFrame):
    pull_requested = Signal(str)

    def __init__(self, model_tag: str, label: str, parent=None):
        super().__init__(parent)
        self.model_tag = model_tag
        self.setObjectName("CardFlat")

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(8)

        top = QHBoxLayout()
        text_col = QVBoxLayout()
        text_col.setSpacing(1)
        name_lbl = QLabel(label)
        name_lbl.setObjectName("H2")
        tag_lbl = QLabel(model_tag)
        tag_lbl.setObjectName("Faint")
        text_col.addWidget(name_lbl)
        text_col.addWidget(tag_lbl)
        top.addLayout(text_col)
        top.addStretch(1)

        self.status_pill = pill("CHECKING\u2026", "#9c99a8", "transparent")
        top.addWidget(self.status_pill, 0, Qt.AlignmentFlag.AlignVCenter)

        self.action_btn = QPushButton("Pull model")
        self.action_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.action_btn.setFixedWidth(110)
        self.action_btn.clicked.connect(lambda: self.pull_requested.emit(self.model_tag))
        top.addWidget(self.action_btn)

        root.addLayout(top)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setVisible(False)
        root.addWidget(self.progress)

        self.progress_label = QLabel("")
        self.progress_label.setObjectName("Faint")
        self.progress_label.setVisible(False)
        root.addWidget(self.progress_label)

    def set_installed(self, installed: bool) -> None:
        if installed:
            self.status_pill.setText("INSTALLED")
            self.status_pill.setStyleSheet("background: rgba(95,209,142,0.15); color:#5fd18e;")
            self.action_btn.setText("Re-pull")
        else:
            self.status_pill.setText("NOT INSTALLED")
            self.status_pill.setStyleSheet("background: rgba(232,180,92,0.15); color:#e8b45c;")
            self.action_btn.setText("Pull model")
        self.action_btn.setEnabled(True)

    def set_pulling(self, active: bool) -> None:
        self.action_btn.setEnabled(not active)
        self.action_btn.setText("Pulling\u2026" if active else self.action_btn.text())
        self.progress.setVisible(active)
        self.progress_label.setVisible(active)
        if active:
            self.status_pill.setText("DOWNLOADING")
            self.status_pill.setStyleSheet("background: rgba(143,124,242,0.18); color:#8f7cf2;")

    def update_progress(self, status: str, completed: int, total: int) -> None:
        if total > 0:
            pct = int(completed / total * 100)
            self.progress.setRange(0, 100)
            self.progress.setValue(pct)
            mb_done = completed / (1024 * 1024)
            mb_total = total / (1024 * 1024)
            self.progress_label.setText(f"{status} \u2014 {mb_done:,.0f} / {mb_total:,.0f} MB")
        else:
            self.progress.setRange(0, 0)
            self.progress_label.setText(status)


class StartupScreen(QWidget):
    """
    First thing the user sees: a centered card that (1) checks the local
    Ollama daemon, then (2) lets the user pick — or pull — the single model
    that becomes the app's *active model* for both the benchmark run and the
    dashboard. A "Manage models" panel exposes pulling any other model.
    """

    model_chosen = Signal(str)
    skip_to_dashboard = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pull_workers: dict[str, PullWorker] = {}
        self.model_rows: dict[str, ModelRow] = {}
        self.setObjectName("StartupRoot")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 24, 28, 24)

        brand_row = QHBoxLayout()
        brand = QLabel("PRISM")
        brand.setObjectName("BrandMark")
        brand_row.addWidget(brand)
        brand_row.addStretch(1)
        outer.addLayout(brand_row)

        outer.addStretch(1)

        center_row = QHBoxLayout()
        center_row.setSpacing(28)
        center_row.addStretch(1)

        self.card = QFrame()
        self.card.setObjectName("StartupCard")
        self.card.setFixedWidth(420)
        card_lay = QVBoxLayout(self.card)
        card_lay.setContentsMargins(0, 0, 0, 0)
        card_lay.setSpacing(18)

        self.title = QLabel("Connecting to Ollama")
        self.title.setObjectName("StartupTitle")
        card_lay.addWidget(self.title)

        self.subtitle = QLabel("Checking localhost:11434 for a running Ollama instance\u2026")
        self.subtitle.setObjectName("StartupSubtitle")
        self.subtitle.setWordWrap(True)
        card_lay.addWidget(self.subtitle)

        self.status_row = QHBoxLayout()
        self.status_dot = QLabel("\u25cf")
        self.status_dot.setObjectName("StatusDotPending")
        self.status_text = QLabel("Searching\u2026")
        self.status_text.setObjectName("StartupStatusText")
        self.status_row.addWidget(self.status_dot)
        self.status_row.addWidget(self.status_text)
        self.status_row.addStretch(1)
        card_lay.addLayout(self.status_row)

        self.model_label = QLabel("Model")
        self.model_label.setObjectName("FieldLabel")
        self.model_label.setVisible(False)
        card_lay.addWidget(self.model_label)

        self.model_combo = QComboBox()
        self.model_combo.setObjectName("StartupCombo")
        self.model_combo.setVisible(False)
        self.model_combo.setFixedHeight(42)
        card_lay.addWidget(self.model_combo)

        self.model_hint = QLabel("")
        self.model_hint.setObjectName("StartupSubtitle")
        self.model_hint.setWordWrap(True)
        self.model_hint.setVisible(False)
        card_lay.addWidget(self.model_hint)

        self.primary_btn = QPushButton("Retry connection")
        self.primary_btn.setObjectName("StartupPrimaryBtn")
        self.primary_btn.setFixedHeight(42)
        self.primary_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.primary_btn.clicked.connect(self._on_primary_clicked)
        card_lay.addWidget(self.primary_btn)

        self.manage_link = QPushButton("Manage models  \u21b4")
        self.manage_link.setObjectName("StartupSkipLink")
        self.manage_link.setCursor(Qt.CursorShape.PointingHandCursor)
        self.manage_link.setFlat(True)
        self.manage_link.setVisible(False)
        self.manage_link.clicked.connect(self._toggle_models_panel)
        card_lay.addWidget(self.manage_link)

        self.install_hint = QLabel(
            "Don't have Ollama? Install it from ollama.com, run "
            "`ollama serve`, then retry."
        )
        self.install_hint.setObjectName("StartupFootnote")
        self.install_hint.setWordWrap(True)
        card_lay.addWidget(self.install_hint)

        self.skip_link = QPushButton("Existing results found \u2014 skip to dashboard  \u2192")
        self.skip_link.setObjectName("StartupSkipLink")
        self.skip_link.setCursor(Qt.CursorShape.PointingHandCursor)
        self.skip_link.setFlat(True)
        self.skip_link.setVisible(False)
        self.skip_link.clicked.connect(self.skip_to_dashboard.emit)
        card_lay.addWidget(self.skip_link)

        self._existing_results = False
        center_row.addWidget(self.card)

        # ---- models management panel ----
        self.models_panel = QFrame()
        self.models_panel.setObjectName("StartupModelsPanel")
        self.models_panel.setFixedWidth(380)
        self.models_panel.setVisible(False)
        panel_lay = QVBoxLayout(self.models_panel)
        panel_lay.setContentsMargins(20, 20, 20, 20)
        panel_lay.setSpacing(10)

        panel_title = QLabel("Manage models")
        panel_title.setObjectName("H2")
        panel_lay.addWidget(panel_title)
        panel_sub = QLabel(
            "Pull any model straight into your local Ollama install. Installed "
            "models are detected automatically and appear in the picker on the left."
        )
        panel_sub.setObjectName("StartupSubtitle")
        panel_sub.setWordWrap(True)
        panel_lay.addWidget(panel_sub)

        custom_row = QHBoxLayout()
        self.custom_model_input = QLineEdit()
        self.custom_model_input.setObjectName("StartupCombo")
        self.custom_model_input.setPlaceholderText("e.g. qwen2.5:7b")
        self.custom_model_input.setFixedHeight(38)
        custom_row.addWidget(self.custom_model_input, 1)
        self.custom_pull_btn = QPushButton("Pull")
        self.custom_pull_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.custom_pull_btn.setFixedHeight(38)
        self.custom_pull_btn.clicked.connect(self._pull_custom_model)
        custom_row.addWidget(self.custom_pull_btn)
        panel_lay.addLayout(custom_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setMaximumHeight(360)
        rows_host = QWidget()
        self.rows_lay = QVBoxLayout(rows_host)
        self.rows_lay.setContentsMargins(0, 4, 0, 4)
        self.rows_lay.setSpacing(8)

        for tag, meta in backend.models_catalog().items():
            row = ModelRow(tag, meta["label"])
            row.pull_requested.connect(self._start_pull)
            self.model_rows[tag] = row
            self.rows_lay.addWidget(row)
        self.rows_lay.addStretch(1)

        scroll.setWidget(rows_host)
        panel_lay.addWidget(scroll)

        self.device_label = QLabel("")
        self.device_label.setObjectName("StartupFootnote")
        self.device_label.setWordWrap(True)
        panel_lay.addWidget(self.device_label)

        center_row.addWidget(self.models_panel)
        center_row.addStretch(1)
        outer.addLayout(center_row)
        outer.addStretch(2)

        self._connected = False
        self._models_panel_open = False
        QTimer.singleShot(250, self._check_ollama)

    # ---------------- logic ----------------

    def set_existing_results_available(self, available: bool) -> None:
        self._existing_results = available
        self.skip_link.setVisible(available)

    def _check_ollama(self) -> None:
        self.title.setText("Connecting to Ollama")
        self.subtitle.setText("Checking localhost:11434 for a running Ollama instance\u2026")
        self.status_dot.setObjectName("StatusDotPending")
        self.status_text.setText("Searching\u2026")
        self._refresh_dot_style()

        reachable = backend.ollama_available()
        if reachable:
            self._connected = True
            self.status_dot.setObjectName("StatusDotGood")
            self.status_text.setText("Connected")
            self._refresh_dot_style()
            self._show_model_picker()
            self.manage_link.setVisible(True)
            self._refresh_model_rows()
        else:
            self._connected = False
            self.status_dot.setObjectName("StatusDotBad")
            self.status_text.setText("Not found")
            self._refresh_dot_style()
            self.title.setText("Ollama not detected")
            self.subtitle.setText(
                "PRISM benchmarks run locally against Ollama. Start it, then retry."
            )
            self.primary_btn.setText("Retry connection")
            self.install_hint.setVisible(True)
            self.manage_link.setVisible(False)
            self.models_panel.setVisible(False)

    def _refresh_dot_style(self) -> None:
        colors = {
            "StatusDotPending": "#e8b45c",
            "StatusDotGood": "#5fd18e",
            "StatusDotBad": "#ea6b6b",
        }
        name = self.status_dot.objectName()
        self.status_dot.setStyleSheet(f"color:{colors.get(name, '#9c99a8')}; font-size:11px;")

    def _show_model_picker(self) -> None:
        self.title.setText("Select a model")
        self.subtitle.setText(
            "Pick the model PRISM will benchmark and show on the dashboard. "
            "Models already pulled are marked ready; others download through "
            "Ollama when you continue."
        )
        self.install_hint.setVisible(False)

        installed = backend.installed_model_tags()
        self.model_combo.clear()
        for tag, meta in backend.models_catalog().items():
            ready = tag in installed or tag.split(":")[0] in installed
            label = f"{meta['label']}  \u2014  {'ready' if ready else 'will download'}"
            self.model_combo.addItem(label, userData=tag)

        remembered = app_state.get_selected_model()
        if remembered:
            idx = self.model_combo.findData(remembered)
            if idx >= 0:
                self.model_combo.setCurrentIndex(idx)

        self.model_label.setVisible(True)
        self.model_combo.setVisible(True)
        self.model_hint.setVisible(True)
        self._update_model_hint()
        self.model_combo.currentIndexChanged.connect(lambda _i: self._update_model_hint())

        self.primary_btn.setText("Continue  \u2192")
        self.primary_btn.setObjectName("StartupPrimaryBtnReady")
        self.primary_btn.setStyleSheet("")

    def _update_model_hint(self) -> None:
        tag = self.model_combo.currentData()
        if not tag:
            return
        installed = backend.installed_model_tags()
        ready = tag in installed or tag.split(":")[0] in installed
        if ready:
            self.model_hint.setText(f"\u201c{tag}\u201d is already pulled \u2014 inference can start immediately.")
        else:
            self.model_hint.setText(f"\u201c{tag}\u201d isn't pulled yet \u2014 PRISM will download it first (progress shown on the next screen).")

    def _on_primary_clicked(self) -> None:
        if not self._connected:
            self._check_ollama()
            return
        tag = self.model_combo.currentData()
        if tag:
            app_state.set_selected_model(tag)
            self.model_chosen.emit(tag)

    # ---------------- manage-models panel ----------------

    def _toggle_models_panel(self) -> None:
        self._models_panel_open = not self._models_panel_open
        self.models_panel.setVisible(self._models_panel_open)
        self.manage_link.setText(
            "Manage models  \u2191" if self._models_panel_open else "Manage models  \u21b4"
        )
        if self._models_panel_open:
            self._refresh_model_rows()

    def _refresh_model_rows(self) -> None:
        installed = backend.installed_model_tags()
        for tag, row in self.model_rows.items():
            row.set_installed(tag in installed or tag.split(":")[0] in installed)
        self._refresh_device_label()

    def _refresh_device_label(self) -> None:
        installed = sorted(backend.installed_model_tags())
        if not installed:
            self.device_label.setText("No models installed on this device yet.")
            return
        self.device_label.setText(f"On this device ({len(installed)}): " + ", ".join(installed))

    def _pull_custom_model(self) -> None:
        tag = self.custom_model_input.text().strip()
        if not tag:
            return
        if tag not in self.model_rows:
            row = ModelRow(tag, tag)
            row.pull_requested.connect(self._start_pull)
            self.model_rows[tag] = row
            self.rows_lay.insertWidget(self.rows_lay.count() - 1, row)
            row.set_installed(backend.is_installed(tag))
        self.custom_model_input.clear()
        self._start_pull(tag)

    def _start_pull(self, model_tag: str) -> None:
        if model_tag in self.pull_workers:
            return
        row = self.model_rows.get(model_tag)
        if row is None:
            return
        row.set_pulling(True)

        worker = PullWorker(model_tag)
        worker.progress.connect(row.update_progress)
        worker.finished_ok.connect(lambda ok, msg, t=model_tag: self._pull_finished(t, ok, msg))
        self.pull_workers[model_tag] = worker
        worker.start()

    def _pull_finished(self, model_tag: str, ok: bool, msg: str) -> None:
        row = self.model_rows.get(model_tag)
        self.pull_workers.pop(model_tag, None)
        if row is not None:
            row.set_pulling(False)
            if not ok and msg:
                row.progress_label.setVisible(True)
                row.progress_label.setText(f"Failed: {msg}")
        self._refresh_model_rows()
        if ok and self._connected:
            self._show_model_picker()
