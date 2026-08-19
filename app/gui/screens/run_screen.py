from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QPushButton, QCheckBox,
    QSpinBox, QProgressBar, QPlainTextEdit, QScrollArea, QGridLayout,
)

from app.gui.widgets import card, h2, body, faint, divider, SectionHeader, MetricTile, kicker
from app.services import backend
from app.services.backend import BenchmarkWorker


def _format_eta(seconds: float) -> str:
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s"
    minutes, secs = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {secs}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m"


class RunScreen(QWidget):
    run_completed = Signal(str)          # model_tag that just finished
    continue_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker: BenchmarkWorker | None = None
        self.model_tag: str | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll)

        content = QWidget()
        scroll.setWidget(content)
        root = QVBoxLayout(content)
        root.setContentsMargins(28, 24, 28, 28)
        root.setSpacing(18)

        header_col = QVBoxLayout()
        header_col.setSpacing(2)
        header_col.addWidget(kicker("Benchmark"))
        self.title_lbl = QLabel("Run benchmark")
        self.title_lbl.setObjectName("H1")
        header_col.addWidget(self.title_lbl)
        self.sub_lbl = body(
            "Runs the full PRISM pipeline for this model: inference \u2192 parsing \u2192 "
            "consistency scoring \u2192 summary — against your local Ollama installation."
        )
        header_col.addWidget(self.sub_lbl)
        root.addLayout(header_col)

        config_card = card("Card")
        cl = QVBoxLayout(config_card)
        cl.setContentsMargins(24, 22, 24, 22)
        cl.setSpacing(14)

        grid = QGridLayout()
        grid.setHorizontalSpacing(40)

        ds_col = QVBoxLayout()
        ds_col.addWidget(h2("Datasets"))
        self.dataset_checks: dict[str, QCheckBox] = {}
        for name in backend.datasets_catalog():
            cb = QCheckBox(name.replace("_", " ").title())
            cb.setChecked(True)
            self.dataset_checks[name] = cb
            ds_col.addWidget(cb)
        grid.addLayout(ds_col, 0, 0)

        opts_col = QVBoxLayout()
        opts_col.addWidget(h2("Options"))
        limit_row = QHBoxLayout()
        limit_row.addWidget(faint("Max questions"))
        self.max_q_spin = QSpinBox()
        self.max_q_spin.setRange(0, 1000)
        self.max_q_spin.setValue(0)
        self.max_q_spin.setSpecialValueText("All")
        limit_row.addWidget(self.max_q_spin)
        opts_col.addLayout(limit_row)
        self.overwrite_cb = QCheckBox("Overwrite completed requests")
        opts_col.addWidget(self.overwrite_cb)
        opts_col.addStretch(1)
        grid.addLayout(opts_col, 0, 1)

        cl.addLayout(grid)
        cl.addWidget(divider())

        action_row = QHBoxLayout()
        self.start_btn = QPushButton("Start benchmark")
        self.start_btn.setObjectName("Primary")
        self.start_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.start_btn.setFixedHeight(38)
        self.start_btn.clicked.connect(self.start_run)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("Danger")
        self.cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self.cancel_run)

        action_row.addWidget(self.start_btn)
        action_row.addWidget(self.cancel_btn)
        action_row.addStretch(1)
        cl.addLayout(action_row)

        root.addWidget(config_card)

        # ---- Live progress ----
        progress_card = card("CardRaised")
        pl = QVBoxLayout(progress_card)
        pl.setContentsMargins(24, 22, 24, 22)
        pl.setSpacing(12)

        self.status_title = QLabel("Idle")
        self.status_title.setObjectName("H2")
        self.status_sub = QLabel("Configure a run above and press Start.")
        self.status_sub.setObjectName("Body")
        pl.addWidget(self.status_title)
        pl.addWidget(self.status_sub)

        overall_lbl_row = QHBoxLayout()
        overall_lbl_row.addWidget(faint("Overall progress"))
        overall_lbl_row.addStretch(1)
        self.overall_pct_lbl = QLabel("0%")
        self.overall_pct_lbl.setObjectName("Faint")
        overall_lbl_row.addWidget(self.overall_pct_lbl)
        pl.addLayout(overall_lbl_row)

        self.overall_bar = QProgressBar()
        self.overall_bar.setObjectName("OverallBar")
        self.overall_bar.setRange(0, 100)
        self.overall_bar.setValue(0)
        self.overall_bar.setTextVisible(False)
        self.overall_bar.setFixedHeight(14)
        pl.addWidget(self.overall_bar)

        dataset_lbl_row = QHBoxLayout()
        dataset_lbl_row.addWidget(faint("Current dataset"))
        dataset_lbl_row.addStretch(1)
        self.dataset_pct_lbl = QLabel("0%")
        self.dataset_pct_lbl.setObjectName("Faint")
        dataset_lbl_row.addWidget(self.dataset_pct_lbl)
        pl.addLayout(dataset_lbl_row)

        self.dataset_bar = QProgressBar()
        self.dataset_bar.setObjectName("DatasetBar")
        self.dataset_bar.setRange(0, 100)
        self.dataset_bar.setValue(0)
        self.dataset_bar.setTextVisible(False)
        self.dataset_bar.setFixedHeight(10)
        pl.addWidget(self.dataset_bar)

        stats_row = QHBoxLayout()
        self.stat_dataset = MetricTile("Dataset", "\u2014")
        self.stat_requests = MetricTile("Requests", "0 / 0")
        self.stat_latency = MetricTile("Avg latency", "\u2014")
        self.stat_eta = MetricTile("Est. time left", "\u2014")
        for s in (self.stat_dataset, self.stat_requests, self.stat_latency, self.stat_eta):
            stats_row.addWidget(s)
        pl.addLayout(stats_row)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setFixedHeight(150)
        pl.addWidget(self.log)

        root.addWidget(progress_card)
        root.addStretch(1)

        continue_row = QHBoxLayout()
        continue_row.addStretch(1)
        self.continue_btn = QPushButton("View dashboard  \u2192")
        self.continue_btn.setObjectName("Primary")
        self.continue_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.continue_btn.setFixedHeight(40)
        self.continue_btn.setVisible(False)
        self.continue_btn.clicked.connect(self.continue_requested.emit)
        continue_row.addWidget(self.continue_btn)
        root.addLayout(continue_row)

    def preselect_model(self, model_tag: str) -> None:
        self.model_tag = model_tag
        self.title_lbl.setText(f"Run benchmark \u2014 {backend.model_label(model_tag)}")
        self.continue_btn.setVisible(False)
        if backend.has_data(backend.get_conn(), model_tag):
            self.status_title.setText("Existing results found")
            self.status_sub.setText(
                "This model already has local benchmark data \u2014 continue to the "
                "dashboard, or start a fresh run above."
            )
            self.continue_btn.setVisible(True)
        else:
            self.status_title.setText("Idle")
            self.status_sub.setText("Configure a run above and press Start.")

    # ---------------- run control ----------------

    def start_run(self) -> None:
        if not self.model_tag:
            self.status_title.setText("No model selected")
            self.status_sub.setText("Pick a model on the startup screen first.")
            return

        datasets = [n for n, cb in self.dataset_checks.items() if cb.isChecked()]
        if not datasets:
            self.status_title.setText("Select at least one dataset")
            return

        max_q = None if self.max_q_spin.value() == 0 else self.max_q_spin.value()

        self.log.clear()
        self.overall_bar.setValue(0)
        self.overall_pct_lbl.setText("0%")
        self.dataset_bar.setValue(0)
        self.dataset_pct_lbl.setText("0%")
        self.start_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.continue_btn.setVisible(False)
        self.status_title.setText("Starting\u2026")
        self.status_sub.setText(f"Warming up inference for {backend.model_label(self.model_tag)}")
        self.stat_dataset.set_value("\u2014")
        self.stat_requests.set_value("0 / 0")
        self.stat_latency.set_value("\u2014")
        self.stat_eta.set_value("\u2014")

        self.worker = BenchmarkWorker(
            self.model_tag, datasets,
            max_questions=max_q, overwrite=self.overwrite_cb.isChecked(),
        )
        self.worker.stage.connect(self._on_stage)
        self.worker.request_progress.connect(self._on_progress)
        self.worker.finished_ok.connect(self._on_finished)
        self.worker.start()

    def cancel_run(self) -> None:
        if self.worker:
            self.worker.cancel()
            self.status_sub.setText("Cancelling after the current request\u2026")
            self.cancel_btn.setEnabled(False)

    def _on_stage(self, stage: str, message: str, dataset, index: int, count: int) -> None:
        self.status_title.setText(message)
        if dataset:
            self.stat_dataset.set_value(str(dataset).replace("_", " ").title())
        self.log.appendPlainText(f"\u25b6 [{stage}] {message}")
        if count:
            pct = int(index / count * 100)
            self.overall_bar.setValue(pct)
            self.overall_pct_lbl.setText(f"{pct}%  \u00b7  dataset {min(index + 1, count)} of {count}")
        # a new dataset stage starting means its own sub-progress resets
        self.dataset_bar.setValue(0)
        self.dataset_pct_lbl.setText("0%")

    def _on_progress(self, dataset: str, status: str, request_number: int, total: int,
                      percent: float, avg_latency: float, eta_seconds: float | None = None) -> None:
        self.stat_requests.set_value(f"{request_number} / {total}")
        if avg_latency:
            self.stat_latency.set_value(f"{avg_latency:.2f}s")
        if eta_seconds is not None:
            self.stat_eta.set_value(_format_eta(eta_seconds))

        pct = int(percent) if percent else (int(request_number / total * 100) if total else 0)
        pct = max(0, min(100, pct))
        self.dataset_bar.setValue(pct)
        self.dataset_pct_lbl.setText(f"{pct}%")

        if status == "error":
            self.log.appendPlainText(f"  \u2715 error on {dataset} request {request_number}")

    def _on_finished(self, success: bool, message: str, result) -> None:
        self.cancel_btn.setEnabled(False)
        self.start_btn.setEnabled(True)

        if not success:
            self.status_title.setText("Run stopped")
            self.status_sub.setText(message or "Benchmark did not complete.")
            self.log.appendPlainText(f"\u26a0 {message}")
            return

        self.status_title.setText("Benchmark complete")
        self.status_sub.setText("Results are ready on the Dashboard.")
        self.log.appendPlainText("\u2713 Benchmark finished, summary written.")
        self.continue_btn.setVisible(True)
        self.overall_bar.setValue(100)
        self.overall_pct_lbl.setText("100%")
        self.dataset_bar.setValue(100)
        self.dataset_pct_lbl.setText("100%")
        self.stat_eta.set_value("Done")
        if self.model_tag:
            self.run_completed.emit(self.model_tag)