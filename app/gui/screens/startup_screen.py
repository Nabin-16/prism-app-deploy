from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QLineEdit, QProgressBar, QMessageBox,
)

from app.gui.widgets import pill, card, h2, body, faint, SectionHeader, centered_column
from app.services import backend, app_state, supabase_sync
from app.services.backend import PullWorker


class ModelRow(QFrame):
    """One row in the model list. The row itself *is* the selector - click
    anywhere on it (outside the pull button) to make it the active model.
    A selected row gets an accent-colored fill; the pull button still does
    its own separate job of downloading the model."""

    pull_requested = Signal(str)
    stop_requested = Signal(str)
    selected = Signal(str)

    def __init__(self, model_tag: str, label: str, parent=None):
        super().__init__(parent)
        self.model_tag = model_tag
        self.setObjectName("ModelListRow")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._selected = False

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(8)

        top = QHBoxLayout()
        top.setSpacing(10)

        self.star_lbl = QLabel("\u2606")
        self.star_lbl.setObjectName("ModelRowStar")
        top.addWidget(self.star_lbl, 0, Qt.AlignmentFlag.AlignVCenter)

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
        self.action_btn.clicked.connect(self._on_pull_clicked)
        top.addWidget(self.action_btn)

        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setObjectName("Danger")
        self.stop_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.stop_btn.setFixedWidth(70)
        self.stop_btn.setVisible(False)
        self.stop_btn.clicked.connect(lambda: self.stop_requested.emit(self.model_tag))
        top.addWidget(self.stop_btn)

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

    def _on_pull_clicked(self) -> None:
        # Pulling a model doesn't itself change the selection, so this is
        # kept separate from mousePressEvent's row-click selection.
        self.pull_requested.emit(self.model_tag)

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt override)
        if self.action_btn.geometry().contains(event.pos()) or self.stop_btn.geometry().contains(event.pos()):
            super().mousePressEvent(event)
            return
        self.selected.emit(self.model_tag)
        super().mousePressEvent(event)

    def set_selected(self, is_selected: bool) -> None:
        self._selected = is_selected
        self.setProperty("selected", "true" if is_selected else "false")
        self.style().unpolish(self)
        self.style().polish(self)

    def set_installed(self, installed: bool) -> None:
        self.star_lbl.setText("\u2605" if installed else "\u2606")
        if installed:
            self.status_pill.setText("INSTALLED")
            self.status_pill.setStyleSheet("background: rgba(95,209,142,0.15); color:#5fd18e;")
            self.action_btn.setText("Re-pull")
        else:
            self.status_pill.setText("NOT INSTALLED")
            self.status_pill.setStyleSheet("background: rgba(232,180,92,0.15); color:#e8b45c;")
            self.action_btn.setText("Pull model")
        self.action_btn.setEnabled(True)
        self.action_btn.setVisible(True)
        self.stop_btn.setVisible(False)

    def set_pulling(self, active: bool) -> None:
        self.action_btn.setVisible(not active)
        self.stop_btn.setVisible(active)
        self.stop_btn.setEnabled(active)
        self.progress.setVisible(active)
        self.progress_label.setVisible(active)
        if active:
            self.status_pill.setText("DOWNLOADING")
            self.status_pill.setStyleSheet("background: rgba(143,124,242,0.18); color:#8f7cf2;")

    def update_progress(self, status: str, completed: float, total: float) -> None:
        if total > 0:
            pct = int(completed / total * 100)
            self.progress.setRange(0, 100)
            self.progress.setValue(pct)
            mb_done = completed / (1024 * 1024)
            mb_total = total / (1024 * 1024)
            self.progress_label.setText(f"{status} - {mb_done:,.0f} / {mb_total:,.0f} MB")
        else:
            self.progress.setRange(0, 0)
            self.progress_label.setText(status)


class StartupScreen(QWidget):
    """
    Setup screen: a full-width page (matching the rest of the app's
    Settings-style screens) with an Ollama connection status card up top
    and a "Model Selection" card below it containing the model list, the
    "add another model" field, and the continue action.
    """

    model_chosen = Signal(str)
    skip_to_dashboard = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pull_workers: dict[str, PullWorker] = {}
        self.model_rows: dict[str, ModelRow] = {}
        self.selected_model_tag: str | None = None
        # Set while a pull was kicked off from the "Continue" button, so
        # that a *successful* pull automatically advances into the app
        # instead of leaving the user stranded on this screen.
        self._auto_continue_tag: str | None = None
        self.setObjectName("StartupRoot")
        self._existing_results = False
        self._connected = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Centered, width-capped content column (same pattern as the
        # Benchmark screen) so the page reads as a focused setup panel
        # instead of stretching full-bleed across a wide window.
        content = QWidget()
        root.addWidget(content)
        inner = centered_column(content, max_width=760, margins=(28, 36, 28, 36), spacing=22)

        inner.addWidget(SectionHeader(
            "Setup Benchmark",
        ))

        # ---- Ollama connection status card ----
        conn_card = card("CardFlat")
        conn_lay = QVBoxLayout(conn_card)
        conn_lay.setContentsMargins(20, 16, 20, 16)
        conn_lay.setSpacing(6)

        conn_top = QHBoxLayout()
        conn_top.setSpacing(10)
        self.status_dot = QLabel("\u25cf")
        self.status_dot.setObjectName("StatusDotPending")
        conn_top.addWidget(self.status_dot, 0, Qt.AlignmentFlag.AlignVCenter)
        ollama_lbl = QLabel("Ollama")
        ollama_lbl.setObjectName("H2")
        conn_top.addWidget(ollama_lbl, 0, Qt.AlignmentFlag.AlignVCenter)
        self.status_pill = pill("CHECKING\u2026", "#9c99a8", "transparent")
        conn_top.addWidget(self.status_pill, 0, Qt.AlignmentFlag.AlignVCenter)
        conn_top.addStretch(1)
        self.refresh_btn = QPushButton("Refresh Status")
        self.refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_btn.clicked.connect(self._check_ollama)
        conn_top.addWidget(self.refresh_btn)
        conn_lay.addLayout(conn_top)

        self.status_detail = faint("Checking localhost:11434 for a running Ollama instance\u2026")
        conn_lay.addWidget(self.status_detail)

        inner.addWidget(conn_card)

        # ---- Model Selection card ----
        sel_label = QLabel("Model Selection")
        sel_label.setObjectName("SectionLabel")
        inner.addWidget(sel_label)

        sel_card = card("CardFlat")
        sel_lay = QVBoxLayout(sel_card)
        sel_lay.setContentsMargins(20, 18, 20, 18)
        sel_lay.setSpacing(14)

        sel_lay.addWidget(body(
            "Select an installed model to benchmark, or add another model from Ollama."
        ))

        # ---- model rows - laid out directly (no scroll) so all four
        # validated models are visible at once without scrolling; any
        # custom/cloud-saved tags added later simply grow the card. ----
        self.rows_host = QWidget()
        self.rows_lay = QVBoxLayout(self.rows_host)
        self.rows_lay.setContentsMargins(0, 0, 0, 0)
        self.rows_lay.setSpacing(8)

        for tag, meta in backend.models_catalog().items():
            row = ModelRow(tag, meta["label"])
            row.pull_requested.connect(self._start_pull)
            row.stop_requested.connect(self._stop_pull)
            row.selected.connect(self._select_model)
            self.model_rows[tag] = row
            self.rows_lay.addWidget(row)

        sel_lay.addWidget(self.rows_host)

        # ---- "Add other models" - a labeled input row so pulling
        # something outside the four validated models reads as one simple
        # action (type a tag, hit the button). Anything pulled here is
        # also saved to Supabase (see supabase_sync.save_custom_model) so
        # it's remembered on the next launch and on any other device
        # synced to the same project.
        custom_row = QHBoxLayout()
        custom_row.setSpacing(8)
        self.custom_model_input = QLineEdit()
        self.custom_model_input.setObjectName("StartupCombo")
        self.custom_model_input.setPlaceholderText("Enter Ollama model tag, e.g. qwen2.5:3b")
        self.custom_model_input.setFixedHeight(40)
        self.custom_model_input.returnPressed.connect(self._pull_custom_model)
        custom_row.addWidget(self.custom_model_input, 1)
        self.custom_pull_btn = QPushButton("Add Model")
        self.custom_pull_btn.setObjectName("Primary")
        self.custom_pull_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.custom_pull_btn.setFixedHeight(40)
        self.custom_pull_btn.clicked.connect(self._pull_custom_model)
        custom_row.addWidget(self.custom_pull_btn)
        sel_lay.addLayout(custom_row)

        add_sub = faint(
            "Note: Enter the exact model tag from the Ollama library. If not "
            "installed, it will be prepared automatically."
        )
        sel_lay.addWidget(add_sub)

        self.device_label = faint("")
        sel_lay.addWidget(self.device_label)

        # Shown as soon as a too-big-for-this-device model is selected,
        # *before* the user tries to pull or continue - an up-front heads
        # up rather than a surprise at click time.
        self.ram_warning_label = QLabel("")
        self.ram_warning_label.setObjectName("Faint")
        self.ram_warning_label.setStyleSheet("color:#ea6b6b;")
        self.ram_warning_label.setWordWrap(True)
        self.ram_warning_label.setVisible(False)
        sel_lay.addWidget(self.ram_warning_label)

        self.continue_btn = QPushButton("Select a model")
        self.continue_btn.setObjectName("StartupPrimaryBtnReady")
        self.continue_btn.setFixedHeight(48)
        self.continue_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.continue_btn.setEnabled(False)
        self.continue_btn.clicked.connect(self._on_continue_clicked)
        sel_lay.addWidget(self.continue_btn)

        inner.addWidget(sel_card)

        # ---- "existing results" skip link - the very last thing on the
        # screen, below the model selection card. ----
        self.skip_link = QPushButton(" Skip to dashboard  \u2192")
        self.skip_link.setObjectName("StartupSkipLink")
        self.skip_link.setCursor(Qt.CursorShape.PointingHandCursor)
        self.skip_link.setFlat(True)
        self.skip_link.setVisible(False)
        inner.addWidget(self.skip_link, 0, Qt.AlignmentFlag.AlignHCenter)
        self.skip_link.clicked.connect(self.skip_to_dashboard.emit)

        inner.addStretch(1)

        QTimer.singleShot(250, self._check_ollama)

    # ---------------- logic ----------------

    def set_existing_results_available(self, available: bool) -> None:
        self._existing_results = available
        self.skip_link.setVisible(available)

    def _check_ollama(self) -> None:
        self.status_dot.setObjectName("StatusDotPending")
        self._refresh_dot_style()
        self.status_pill.setText("CHECKING\u2026")
        self.status_pill.setStyleSheet("background: rgba(156,153,168,0.15); color:#9c99a8;")
        self.status_detail.setText("Checking localhost:11434 for a running Ollama instance\u2026")

        reachable = backend.ollama_available()
        if reachable:
            self._connected = True
            self.status_dot.setObjectName("StatusDotGood")
            self._refresh_dot_style()
            self.status_pill.setText("CONNECTED")
            self.status_pill.setStyleSheet("background: rgba(95,209,142,0.15); color:#5fd18e;")
            self._show_model_picker()
        else:
            self._connected = False
            self.status_dot.setObjectName("StatusDotBad")
            self._refresh_dot_style()
            self.status_pill.setText("NOT FOUND")
            self.status_pill.setStyleSheet("background: rgba(234,107,107,0.15); color:#ea6b6b;")
            self.status_detail.setText(
                "Ollama isn't reachable at localhost:11434. Install it from "
                "ollama.com, run `ollama serve`, then refresh status."
            )
            self._update_continue_btn()

    def _refresh_dot_style(self) -> None:
        colors = {
            "StatusDotPending": "#e8b45c",
            "StatusDotGood": "#5fd18e",
            "StatusDotBad": "#ea6b6b",
        }
        name = self.status_dot.objectName()
        self.status_dot.setStyleSheet(f"color:{colors.get(name, '#9c99a8')}; font-size:11px;")

    def _show_model_picker(self) -> None:
        self._load_cloud_models()
        self._refresh_model_rows()

        remembered = app_state.get_selected_model()
        if remembered and remembered in self.model_rows:
            self._select_model(remembered)
        elif self.model_rows and self.selected_model_tag is None:
            self._select_model(next(iter(self.model_rows)))
        else:
            self._update_continue_btn()

    def _select_model(self, tag: str) -> None:
        if tag not in self.model_rows:
            return
        self.selected_model_tag = tag
        for row_tag, row in self.model_rows.items():
            row.set_selected(row_tag == tag)
        self._update_ram_warning(tag)
        self._update_continue_btn()

    def _update_ram_warning(self, tag: str) -> None:
        """Surface an insufficient-RAM warning inline, right away, as soon
        as a model is picked - before the user ever clicks Pull/Continue."""
        installed = backend.is_installed(tag)
        shortfall = None if installed else backend.check_ram_for_model(tag)
        if shortfall is None:
            self.ram_warning_label.setVisible(False)
            self.ram_warning_label.setText("")
            return
        required_gb, available_gb = shortfall
        self.ram_warning_label.setText(
            f"\u26a0 \u201c{tag}\u201d recommends about {required_gb:.0f} GB of RAM, "
            f"but this device has only {available_gb:.1f} GB. It may run very "
            "slowly, swap heavily, or fail to load."
        )
        self.ram_warning_label.setVisible(True)

    def _update_continue_btn(self) -> None:
        tag = self.selected_model_tag
        if not tag:
            self.continue_btn.setText("Select a model")
            self.continue_btn.setEnabled(False)
            return
        if not self._connected:
            self.continue_btn.setText("Waiting for Ollama\u2026")
            self.continue_btn.setEnabled(False)
            return
        if tag in self.pull_workers:
            self.continue_btn.setEnabled(False)
            self.continue_btn.setText(f"Downloading {tag}\u2026")
            return
        self.continue_btn.setEnabled(True)
        if backend.is_installed(tag):
            self.continue_btn.setText(f"Continue with {tag}  \u2192")
        else:
            self.continue_btn.setText(f"Download {tag} to continue  \u2192")

    def _on_continue_clicked(self) -> None:
        tag = self.selected_model_tag
        if not tag or not self._connected:
            return

        if not backend.is_installed(tag):
            # Hard gate: never let the user reach Benchmark/Dashboard with
            # a model that isn't actually pulled onto this device. Instead
            # of proceeding, kick off the pull here (after the RAM check)
            # and auto-continue once it finishes successfully.
            if not self._confirm_ram_ok(tag):
                return
            self._auto_continue_tag = tag
            self._start_pull(tag)
            return

        app_state.set_selected_model(tag)
        self.model_chosen.emit(tag)

    def _confirm_ram_ok(self, model_tag: str) -> bool:
        """Show a blocking error dialog (and let the user back out) if
        this device's RAM looks too small for ``model_tag``. Returns True
        to proceed anyway, False to cancel. A model already installed
        skips the check entirely -- if it runs today, it'll keep running."""
        shortfall = backend.check_ram_for_model(model_tag)
        if shortfall is None:
            return True
        required_gb, available_gb = shortfall
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Critical)
        box.setWindowTitle("Insufficient RAM for this model")
        box.setText(f"\u201c{model_tag}\u201d likely will not run well on this device.")
        box.setInformativeText(
            f"This model recommends at least {required_gb:.0f} GB of RAM, "
            f"but this device has about {available_gb:.1f} GB available.\n\n"
            "Downloading and running it anyway may cause Ollama to run very "
            "slowly, swap heavily, or fail to load the model entirely.\n\n"
            "Continue anyway?"
        )
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        box.setDefaultButton(QMessageBox.StandardButton.No)
        choice = box.exec()
        return choice == QMessageBox.StandardButton.Yes


    # ---------------- model list ----------------

    def _refresh_model_rows(self) -> None:
        installed = backend.installed_model_tags()
        for tag, row in self.model_rows.items():
            row.set_installed(tag in installed or tag.split(":")[0] in installed)
        if self.selected_model_tag:
            self._update_ram_warning(self.selected_model_tag)
        self._update_continue_btn()


    def _load_cloud_models(self) -> None:
        """Pull in any "other model" tags previously saved to Supabase
        (from this device or another one) and add a row for each that isn't
        already part of the built-in catalog, so they show up on every
        launch instead of only for the session that added them."""
        if not supabase_sync.is_configured():
            return
        for entry in supabase_sync.fetch_custom_models():
            tag = (entry.get("model_tag") or "").strip()
            if not tag or tag in self.model_rows:
                continue
            label = entry.get("label") or tag
            row = ModelRow(tag, label)
            row.pull_requested.connect(self._start_pull)
            row.stop_requested.connect(self._stop_pull)
            row.selected.connect(self._select_model)
            self.model_rows[tag] = row
            self.rows_lay.addWidget(row)
            row.set_installed(backend.is_installed(tag))

    def _pull_custom_model(self) -> None:
        tag = self.custom_model_input.text().strip()
        if not tag:
            return
        is_new = tag not in self.model_rows
        if is_new:
            row = ModelRow(tag, tag)
            row.pull_requested.connect(self._start_pull)
            row.stop_requested.connect(self._stop_pull)
            row.selected.connect(self._select_model)
            self.model_rows[tag] = row
            self.rows_lay.addWidget(row)
            row.set_installed(backend.is_installed(tag))
        self.custom_model_input.clear()
        # Remember it in Supabase right away (not gated on the pull actually
        # succeeding) so it reappears in "Add other models" on next launch
        # even if this pull is retried later.
        if is_new:
            supabase_sync.save_custom_model(tag)
        self._select_model(tag)
        self._start_pull(tag)

    def _start_pull(self, model_tag: str) -> None:
        if model_tag in self.pull_workers:
            return
        row = self.model_rows.get(model_tag)
        if row is None:
            return
        if not backend.is_installed(model_tag) and not self._confirm_ram_ok(model_tag):
            return
        row.set_pulling(True)

        worker = PullWorker(model_tag)
        worker.progress.connect(row.update_progress)
        worker.finished_ok.connect(lambda ok, msg, t=model_tag: self._pull_finished(t, ok, msg))
        self.pull_workers[model_tag] = worker
        worker.start()

    def _stop_pull(self, model_tag: str) -> None:
        worker = self.pull_workers.get(model_tag)
        if worker is None:
            return
        row = self.model_rows.get(model_tag)
        if row is not None:
            row.stop_btn.setEnabled(False)
            row.progress_label.setVisible(True)
            row.progress_label.setText("Stopping\u2026")
        worker.cancel()
        if self._auto_continue_tag == model_tag:
            self._auto_continue_tag = None

    def _pull_finished(self, model_tag: str, ok: bool, msg: str) -> None:
        row = self.model_rows.get(model_tag)
        self.pull_workers.pop(model_tag, None)
        cancelled = msg == "Cancelled"
        if row is not None:
            row.set_pulling(False)
            if not ok and msg:
                row.progress_label.setVisible(True)
                row.progress_label.setText("Stopped" if cancelled else f"Couldn't finish: {msg}")
        self._refresh_model_rows()

        if self._auto_continue_tag == model_tag:
            self._auto_continue_tag = None
            if ok and backend.is_installed(model_tag):
                app_state.set_selected_model(model_tag)
                self.model_chosen.emit(model_tag)
            elif not cancelled:
                QMessageBox.critical(
                    self,
                    "Download didn't finish",
                    (
                        f"\u201c{model_tag}\u201d didn't finish downloading"
                        + (f" ({msg})." if msg else ".")
                        + "\n\nIt needs to be on this device before you can benchmark or "
                        "view results for it - give it another try when you're ready."
                    ),
                )