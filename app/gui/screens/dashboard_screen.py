from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QPushButton,
    QComboBox, QTableWidget, QTableWidgetItem, QTabWidget, QScrollArea,
    QHeaderView, QStackedWidget, QFileDialog, QMessageBox,
)
from PySide6.QtCharts import (
    QChart, QChartView, QBarSeries, QBarSet, QBarCategoryAxis, QValueAxis,
    QLineSeries, QPieSeries, QScatterSeries,
)

from app.gui.widgets import (
    card, h1, h2, body, faint, divider, SectionHeader, MetricTile, kicker,
    EmptyStateCTA,
)
from app.services import backend, app_state
from app.services import pdf_report

PRIMARY_COLOR = QColor("#8f7cf2")
COMPARE_COLOR = QColor("#5fd18e")

# Chart text (titles/legends/axis labels) must contrast against whichever
# palette is active — the dashboard used to hardcode light-on-dark colors,
# which read as nearly invisible on the paper (light) theme. These pick the
# right pair at draw time instead.
_DARK_THEME_TEXT = {"title": QColor("#eceaf5"), "axis": QColor("#a6a4b8")}
_LIGHT_THEME_TEXT = {"title": QColor("#2a2733"), "axis": QColor("#6b6879")}


def _chart_text_colors() -> dict:
    return _DARK_THEME_TEXT if app_state.get_theme() == "dusk" else _LIGHT_THEME_TEXT


AXIS_LABEL_COLOR = QColor("#a6a4b8")  # kept as fallback default; call sites use _chart_text_colors()

# Distinct palette used when plotting *all* locally-benchmarked models at
# once (comparison tab / scatter / radar) — cycles if there are more models
# than colors.
MULTI_COLORS = [
    QColor("#8f7cf2"), QColor("#5fd18e"), QColor("#e8b45c"),
    QColor("#ea6b6b"), QColor("#5cc7e8"), QColor("#f28fd0"),
    QColor("#c9d15f"), QColor("#9d7cf2"),
]


def _color_for(index: int) -> QColor:
    return MULTI_COLORS[index % len(MULTI_COLORS)]

PCT_FIELDS = {
    "prompt_response_accuracy", "conditional_accuracy", "answer_recovery_rate",
    "instruction_compliance_rate", "question_majority_accuracy", "mean_agreement",
    "mean_prompt_sensitivity", "answer_unanimous_rate",
    "prompt_invariant_incorrect_rate", "accuracy", "instruction_compliant_rate",
}

PRETTY = {
    "dataset": "Dataset", "n_questions": "Questions",
    "prompt_response_accuracy": "Accuracy", "conditional_accuracy": "Cond. accuracy",
    "answer_recovery_rate": "Recovery rate", "instruction_compliance_rate": "Instr. compliance",
    "question_majority_accuracy": "Majority accuracy", "mean_agreement": "Agreement",
    "mean_prompt_sensitivity": "Prompt sensitivity", "answer_unanimous_rate": "Unanimous rate",
    "prompt_invariant_incorrect_rate": "Invariant-incorrect",
}
TABLE_COLUMNS = [
    "dataset", "n_questions", "prompt_response_accuracy", "conditional_accuracy",
    "mean_agreement", "mean_prompt_sensitivity", "instruction_compliance_rate",
    "answer_recovery_rate", "answer_unanimous_rate", "prompt_invariant_incorrect_rate",
]


def _fmt(key: str, value) -> str:
    if key in PCT_FIELDS:
        try:
            return f"{float(value) * 100:.1f}%"
        except (TypeError, ValueError):
            return str(value)
    return str(value)


def _avg(rows: list[dict], key: str) -> float:
    vals = [float(r.get(key, 0) or 0) for r in rows]
    return sum(vals) / len(vals) if vals else 0.0


class DashboardScreen(QWidget):
    benchmark_requested = Signal(str)   # model_tag the user wants to download+run to compare

    def __init__(self, parent=None):
        super().__init__(parent)
        self.conn = backend.get_conn()
        self.model_tag: str | None = None
        self.compare_tag: str | None = None
        # when a comparison model is chosen, this can be flipped off to
        # temporarily show only the primary model again without losing the
        # chosen comparison (compare_tag stays set the whole time)
        self.show_compare = True

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

        # ---------------- header ----------------
        header_row = QHBoxLayout()
        header_col = QVBoxLayout()
        header_col.setSpacing(2)
        header_col.addWidget(kicker("Dashboard"))
        self.model_title = h1("No model selected")
        header_col.addWidget(self.model_title)
        self.model_sub = body("Pick a model on the startup screen, then run a benchmark.")
        header_col.addWidget(self.model_sub)
        header_row.addLayout(header_col)
        header_row.addStretch(1)

        self.rerun_btn = QPushButton("Re-run benchmark")
        self.rerun_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.rerun_btn.clicked.connect(lambda: self.benchmark_requested.emit(self.model_tag or ""))
        header_row.addWidget(self.rerun_btn, 0, Qt.AlignmentFlag.AlignTop)

        self.compare_toggle = QPushButton("+ Compare with another model")
        self.compare_toggle.setObjectName("CompareBtn")
        self.compare_toggle.setCheckable(True)
        self.compare_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.compare_toggle.clicked.connect(self._toggle_compare_drawer)
        header_row.addWidget(self.compare_toggle, 0, Qt.AlignmentFlag.AlignTop)

        self.export_btn = QPushButton("Download PDF summary")
        self.export_btn.setObjectName("Primary")
        self.export_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.export_btn.clicked.connect(self._export_pdf)
        header_row.addWidget(self.export_btn, 0, Qt.AlignmentFlag.AlignTop)
        root.addLayout(header_row)

        # ---------------- compare drawer ----------------
        self.compare_drawer = QFrame()
        self.compare_drawer.setObjectName("CompareDrawer")
        self.compare_drawer.setVisible(False)
        drawer_lay = QVBoxLayout(self.compare_drawer)
        drawer_lay.setContentsMargins(20, 16, 20, 16)
        drawer_lay.setSpacing(10)

        drawer_top = QHBoxLayout()
        drawer_top.addWidget(h2("Compare against"))
        drawer_top.addStretch(1)
        self.compare_combo = QComboBox()
        self.compare_combo.setMinimumWidth(240)
        drawer_top.addWidget(self.compare_combo)
        self.compare_go_btn = QPushButton("Compare")
        self.compare_go_btn.setObjectName("Primary")
        self.compare_go_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.compare_go_btn.clicked.connect(self._on_compare_selected)
        drawer_top.addWidget(self.compare_go_btn)
        self.compare_clear_btn = QPushButton("Clear")
        self.compare_clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.compare_clear_btn.setVisible(False)
        self.compare_clear_btn.clicked.connect(self._clear_compare)
        drawer_top.addWidget(self.compare_clear_btn)
        # lets the user flip back to a single-model view without losing the
        # chosen comparison model \u2014 re-checking it brings the overlay right back
        self.compare_show_toggle = QPushButton("Show only this model")
        self.compare_show_toggle.setObjectName("CompareBtn")
        self.compare_show_toggle.setCheckable(True)
        self.compare_show_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.compare_show_toggle.setVisible(False)
        self.compare_show_toggle.toggled.connect(self._on_show_compare_toggled)
        drawer_top.addWidget(self.compare_show_toggle)
        drawer_lay.addLayout(drawer_top)

        self.compare_stack = QStackedWidget()
        self._compare_info = body(
            "Choose a model above. If it already has local benchmark data, its "
            "results are overlaid on every chart below. Otherwise you'll be asked "
            "to download the model and run inference first."
        )
        self._compare_empty = EmptyStateCTA(
            "No local data for this model",
            "PRISM hasn't benchmarked this model on this device yet.",
            "Download & run benchmark",
        )
        self._compare_empty.button.clicked.connect(
            lambda: self.benchmark_requested.emit(self.compare_combo.currentData() or "")
        )
        self.compare_stack.addWidget(self._compare_info)
        self.compare_stack.addWidget(self._compare_empty)
        drawer_lay.addWidget(self.compare_stack)

        root.addWidget(self.compare_drawer)

        # ---------------- metric tiles ----------------
        self.tiles_row = QHBoxLayout()
        self.tile_questions = MetricTile("Questions run", "—")
        self.tile_accuracy = MetricTile("Accuracy", "—")
        self.tile_agreement = MetricTile("Agreement", "—")
        self.tile_compliance = MetricTile("Instr. compliance", "—")
        self.tile_invariant = MetricTile("Invariant-incorrect", "—")
        for t in (self.tile_questions, self.tile_accuracy, self.tile_agreement,
                  self.tile_compliance, self.tile_invariant):
            self.tiles_row.addWidget(t)
        root.addLayout(self.tiles_row)

        note = QFrame()
        note.setObjectName("CardFlat")
        note_lay = QHBoxLayout(note)
        note_lay.setContentsMargins(16, 10, 16, 10)
        note_lay.addWidget(body(
            "PRISM measures answer stability across five equivalent prompts as well "
            "as accuracy — a model can be highly consistent yet consistently wrong."
        ))
        root.addWidget(note)

        # ---------------- charts + table ----------------
        tabs_card = card("Card")
        tl = QVBoxLayout(tabs_card)
        tl.setContentsMargins(16, 14, 16, 16)
        self.tabs = QTabWidget()
        tl.addWidget(self.tabs)

        self.bar_chart_view = self._new_chart_view()
        self.line_chart_view = self._new_chart_view()
        self.pie_chart_view = self._new_chart_view()
        self.scatter_chart_view = self._new_chart_view()
        self.allmodel_bar_view = self._new_chart_view()
        self.detail_chart_view = self._new_chart_view(height=280)
        self.leaderboard_chart_view = self._new_chart_view(height=280)
        self.detailed_table = QTableWidget()
        self.leaderboard_table = QTableWidget()

        self._wrap_chart_tab("Metrics by dataset", self.bar_chart_view)
        self._wrap_chart_tab("Accuracy by prompt condition", self.line_chart_view)
        self._wrap_chart_tab("Answer consistency", self.pie_chart_view)
        self._wrap_chart_tab("Accuracy vs. agreement", self.scatter_chart_view)
        self._wrap_chart_tab("All models \u2014 accuracy", self.allmodel_bar_view)
        self._wrap_chart_and_table_tab("Detailed table", self.detail_chart_view, self.detailed_table)
        self._wrap_chart_and_table_tab("Leaderboard (all models)", self.leaderboard_chart_view, self.leaderboard_table)

        root.addWidget(tabs_card)
        root.addStretch(1)

    # ---------------- construction helpers ----------------

    def _new_chart_view(self, height: int = 360) -> QChartView:
        v = QChartView()
        v.setMinimumHeight(height)
        v.setRenderHint(QPainter.RenderHint.Antialiasing)
        return v

    def _wrap_chart_tab(self, title: str, chart_view: QChartView) -> None:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(4, 8, 4, 4)
        lay.addWidget(chart_view)
        self.tabs.addTab(w, title)

    def _wrap_tab(self, title: str, table: QTableWidget) -> None:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(4, 8, 4, 4)
        lay.addWidget(table)
        self.tabs.addTab(w, title)

    def _wrap_chart_and_table_tab(self, title: str, chart_view: QChartView, table: QTableWidget) -> None:
        """A chart on top, its backing table below it — used for the two
        table-only tabs so every tab on the dashboard shows a graph, not
        just numbers."""
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(4, 8, 4, 4)
        lay.setSpacing(10)
        lay.addWidget(chart_view)
        lay.addWidget(table)
        self.tabs.addTab(w, title)

    # ---------------- public API ----------------

    def set_model(self, model_tag: str | None) -> None:
        self.model_tag = model_tag
        self.compare_tag = None
        self.show_compare = True
        self.compare_clear_btn.setVisible(False)
        self.compare_show_toggle.setVisible(False)
        self.compare_show_toggle.setChecked(False)
        self.refresh()

    def refresh(self) -> None:
        if not self.model_tag:
            self.model_title.setText("No model selected")
            self.model_sub.setText("Pick a model on the startup screen, then run a benchmark.")
            self.rerun_btn.setEnabled(False)
            self.compare_toggle.setEnabled(False)
            return

        self.rerun_btn.setEnabled(True)
        self.compare_toggle.setEnabled(True)
        label = backend.model_label(self.model_tag)
        self.model_title.setText(label)

        rows = backend.model_dataset_rows(self.conn, self.model_tag)
        info = backend.run_info(self.conn, self.model_tag)
        if not rows:
            self.model_sub.setText(f"\u201c{self.model_tag}\u201d \u2014 no local benchmark yet.")
        else:
            when = (info or {}).get("finished_utc") or (info or {}).get("created_utc") or ""
            self.model_sub.setText(f"\u201c{self.model_tag}\u201d \u00b7 last run {when[:19].replace('T', ' ')} UTC")

        # the toggle lets the user park the comparison without losing it \u2014
        # when it's off, every chart/table below just gets an empty
        # compare_rows and renders exactly like single-model mode
        compare_rows = (
            backend.model_dataset_rows(self.conn, self.compare_tag)
            if (self.compare_tag and self.show_compare) else []
        )

        self._populate_compare_combo()
        self._update_tiles(rows, compare_rows)
        self._update_bar_chart(rows, compare_rows)
        self._update_line_chart(
            backend.model_prompt_rows(self.conn, self.model_tag) if rows else [],
            backend.model_prompt_rows(self.conn, self.compare_tag) if compare_rows else [],
        )
        self._update_pie_chart(rows, compare_rows)
        self._update_table(rows, compare_rows)
        self._update_scatter_chart()
        self._update_allmodel_bar_chart()
        self._update_leaderboard_table()
        self._update_detail_chart(rows, compare_rows)
        self._update_leaderboard_chart()

    # ---------------- compare drawer ----------------

    def _toggle_compare_drawer(self) -> None:
        self.compare_drawer.setVisible(self.compare_toggle.isChecked())
        if self.compare_toggle.isChecked():
            self._populate_compare_combo()

    def _populate_compare_combo(self) -> None:
        self.compare_combo.blockSignals(True)
        self.compare_combo.clear()
        have_data = backend.models_with_data(self.conn)
        for tag, meta in backend.models_catalog().items():
            if tag == self.model_tag:
                continue
            suffix = " \u00b7 data available" if tag in have_data else " \u00b7 not benchmarked yet"
            self.compare_combo.addItem(f"{meta['label']}{suffix}", userData=tag)
        self.compare_combo.blockSignals(False)

    def _on_compare_selected(self) -> None:
        tag = self.compare_combo.currentData()
        if not tag:
            return
        if backend.has_data(self.conn, tag):
            self.compare_tag = tag
            self.show_compare = True
            self.compare_clear_btn.setVisible(True)
            self.compare_show_toggle.setVisible(True)
            self.compare_show_toggle.blockSignals(True)
            self.compare_show_toggle.setChecked(False)
            self.compare_show_toggle.blockSignals(False)
            self.compare_show_toggle.setText("Show only this model")
            self.compare_stack.setCurrentWidget(self._compare_info)
            self.refresh()
        else:
            self.compare_tag = None
            self.compare_clear_btn.setVisible(False)
            self.compare_show_toggle.setVisible(False)
            self._compare_empty.button.setText(
                f"Download & run benchmark for {backend.model_label(tag)}"
            )
            self.compare_stack.setCurrentWidget(self._compare_empty)
            self.refresh()

    def _on_show_compare_toggled(self, checked: bool) -> None:
        # checked == "show only the primary model" (comparison hidden)
        self.show_compare = not checked
        self.compare_show_toggle.setText(
            "Show comparison again" if checked else "Show only this model"
        )
        self.refresh()

    def _clear_compare(self) -> None:
        self.compare_tag = None
        self.show_compare = True
        self.compare_clear_btn.setVisible(False)
        self.compare_show_toggle.setVisible(False)
        self.compare_show_toggle.blockSignals(True)
        self.compare_show_toggle.setChecked(False)
        self.compare_show_toggle.blockSignals(False)
        self.refresh()

    # ---------------- data -> widgets ----------------

    def _update_tiles(self, rows: list[dict], compare_rows: list[dict] | None = None) -> None:
        tiles = (self.tile_questions, self.tile_accuracy, self.tile_agreement,
                 self.tile_compliance, self.tile_invariant)
        if not rows:
            for t in tiles:
                t.set_value("—")
                t.set_compare(None)
            return

        total_q = sum(int(float(r.get("n_questions", 0) or 0)) for r in rows)
        self.tile_questions.set_value(str(total_q))
        self.tile_accuracy.set_value(f"{_avg(rows, 'prompt_response_accuracy') * 100:.1f}%")
        self.tile_agreement.set_value(f"{_avg(rows, 'mean_agreement') * 100:.1f}%")
        self.tile_compliance.set_value(f"{_avg(rows, 'instruction_compliance_rate') * 100:.1f}%")
        self.tile_invariant.set_value(f"{_avg(rows, 'prompt_invariant_incorrect_rate') * 100:.1f}%")

        # Show the comparison model's numbers as a second line on each tile,
        # so "Compare" visibly changes the dashboard even before you look at
        # the charts/table below.
        if self.compare_tag and compare_rows:
            cmp_label = backend.model_label(self.compare_tag)
            cmp_total_q = sum(int(float(r.get("n_questions", 0) or 0)) for r in compare_rows)
            self.tile_questions.set_compare(f"vs {cmp_label}: {cmp_total_q}")
            self.tile_accuracy.set_compare(
                f"vs {cmp_label}: {_avg(compare_rows, 'prompt_response_accuracy') * 100:.1f}%")
            self.tile_agreement.set_compare(
                f"vs {cmp_label}: {_avg(compare_rows, 'mean_agreement') * 100:.1f}%")
            self.tile_compliance.set_compare(
                f"vs {cmp_label}: {_avg(compare_rows, 'instruction_compliance_rate') * 100:.1f}%")
            self.tile_invariant.set_compare(
                f"vs {cmp_label}: {_avg(compare_rows, 'prompt_invariant_incorrect_rate') * 100:.1f}%")
        else:
            for t in tiles:
                t.set_compare(None)

    def _update_bar_chart(self, rows: list[dict], compare_rows: list[dict]) -> None:
        chart = QChart()
        chart.setBackgroundVisible(False)
        tc = _chart_text_colors()
        chart.legend().setLabelColor(tc["axis"])
        chart.setTitleBrush(tc["title"])
        chart.setTitle("Accuracy & agreement by dataset")

        if not rows:
            self.bar_chart_view.setChart(chart)
            return

        datasets = sorted({r["dataset"] for r in rows} | {r["dataset"] for r in compare_rows})
        by_ds = {r["dataset"]: r for r in rows}
        cmp_by_ds = {r["dataset"]: r for r in compare_rows}

        series = QBarSeries()
        acc_set = QBarSet(f"{backend.model_label(self.model_tag)} \u00b7 accuracy")
        acc_set.setColor(PRIMARY_COLOR)
        agree_set = QBarSet(f"{backend.model_label(self.model_tag)} \u00b7 agreement")
        agree_set.setColor(PRIMARY_COLOR.lighter(140))
        for d in datasets:
            r = by_ds.get(d, {})
            acc_set.append(float(r.get("prompt_response_accuracy", 0) or 0) * 100)
            agree_set.append(float(r.get("mean_agreement", 0) or 0) * 100)
        series.append(acc_set)
        series.append(agree_set)

        if self.compare_tag and compare_rows:
            cmp_acc = QBarSet(f"{backend.model_label(self.compare_tag)} \u00b7 accuracy")
            cmp_acc.setColor(COMPARE_COLOR)
            cmp_agree = QBarSet(f"{backend.model_label(self.compare_tag)} \u00b7 agreement")
            cmp_agree.setColor(COMPARE_COLOR.lighter(140))
            for d in datasets:
                r = cmp_by_ds.get(d, {})
                cmp_acc.append(float(r.get("prompt_response_accuracy", 0) or 0) * 100)
                cmp_agree.append(float(r.get("mean_agreement", 0) or 0) * 100)
            series.append(cmp_acc)
            series.append(cmp_agree)

        chart.addSeries(series)
        axis_x = QBarCategoryAxis()
        axis_x.append([d.replace("_", " ").title() for d in datasets])
        axis_x.setLabelsColor(tc["axis"])
        chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
        series.attachAxis(axis_x)
        axis_y = QValueAxis()
        axis_y.setRange(0, 100)
        axis_y.setLabelFormat("%d%%")
        axis_y.setLabelsColor(tc["axis"])
        chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
        series.attachAxis(axis_y)
        self.bar_chart_view.setChart(chart)

    def _update_line_chart(self, prompt_rows: list[dict], cmp_prompt_rows: list[dict]) -> None:
        chart = QChart()
        chart.setBackgroundVisible(False)
        tc = _chart_text_colors()
        chart.legend().setLabelColor(tc["axis"])
        chart.setTitleBrush(tc["title"])
        chart.setTitle("Accuracy by prompt condition (P0\u2013P4), averaged over datasets")

        if not prompt_rows:
            self.line_chart_view.setChart(chart)
            return

        conditions = sorted({r["prompt_condition"] for r in prompt_rows if r.get("prompt_condition")})

        def _series_for(rows: list[dict], name: str, color: QColor) -> QLineSeries:
            s = QLineSeries()
            s.setName(name)
            pen = s.pen()
            pen.setWidth(3)
            pen.setColor(color)
            s.setPen(pen)
            by_cond: dict[str, list[float]] = {}
            for r in rows:
                by_cond.setdefault(r["prompt_condition"], []).append(float(r.get("accuracy", 0) or 0))
            for i, cond in enumerate(conditions):
                vals = by_cond.get(cond, [])
                avg = (sum(vals) / len(vals)) if vals else 0.0
                s.append(i, avg * 100)
            return s

        primary_series = _series_for(prompt_rows, backend.model_label(self.model_tag), PRIMARY_COLOR)
        chart.addSeries(primary_series)

        if self.compare_tag and cmp_prompt_rows:
            cmp_series = _series_for(cmp_prompt_rows, backend.model_label(self.compare_tag), COMPARE_COLOR)
            chart.addSeries(cmp_series)

        axis_x = QBarCategoryAxis()
        axis_x.append(conditions)
        axis_x.setLabelsColor(tc["axis"])
        chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
        axis_y = QValueAxis()
        axis_y.setRange(0, 100)
        axis_y.setLabelFormat("%d%%")
        axis_y.setLabelsColor(tc["axis"])
        chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
        for s in chart.series():
            s.attachAxis(axis_x)
            s.attachAxis(axis_y)
        self.line_chart_view.setChart(chart)

    def _update_pie_chart(self, rows: list[dict], compare_rows: list[dict]) -> None:
        chart = QChart()
        chart.setBackgroundVisible(False)
        tc = _chart_text_colors()
        chart.legend().setLabelColor(tc["axis"])
        chart.setTitleBrush(tc["title"])
        label = backend.model_label(self.model_tag) if self.model_tag else ""
        chart.setTitle(f"{label} \u2014 unanimous vs. varying answers across prompts")

        if not rows:
            self.pie_chart_view.setChart(chart)
            return

        unanimous = _avg(rows, "answer_unanimous_rate")
        series = QPieSeries()
        s1 = series.append("Unanimous across P0\u2013P4", unanimous)
        s2 = series.append("Varies by prompt", max(0.0, 1 - unanimous))
        s1.setBrush(PRIMARY_COLOR)
        s2.setBrush(QColor("#2a2833"))
        s1.setLabelVisible(True)
        s2.setLabelVisible(True)
        series.setHoleSize(0.45)
        chart.addSeries(series)
        self.pie_chart_view.setChart(chart)

    def _update_table(self, rows: list[dict], compare_rows: list[dict]) -> None:
        table = self.detailed_table
        table.clear()
        columns = ["model"] + TABLE_COLUMNS
        all_rows = list(rows) + list(compare_rows)
        table.setColumnCount(len(columns))
        table.setRowCount(len(all_rows))
        table.setHorizontalHeaderLabels([PRETTY.get(c, c.replace("_", " ").title()) for c in columns])
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)

        for r_idx, row in enumerate(all_rows):
            for c_idx, col in enumerate(columns):
                if col == "model":
                    value = backend.model_label(row.get("model", self.model_tag or ""))
                else:
                    value = _fmt(col, row.get(col, ""))
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
                table.setItem(r_idx, c_idx, item)

        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setStretchLastSection(True)

    # ---------------- all-model comparison ----------------

    def _all_models_avg(self) -> dict[str, dict[str, float]]:
        """{model_tag: {metric: dataset-averaged value}} for every locally
        benchmarked model — used by the scatter chart, all-model bar chart,
        the leaderboard table, and the PDF export."""
        data = backend.all_models_dataset_rows(self.conn)
        out: dict[str, dict[str, float]] = {}
        for tag, rows in data.items():
            if not rows:
                continue
            out[tag] = {
                "prompt_response_accuracy": _avg(rows, "prompt_response_accuracy"),
                "mean_agreement": _avg(rows, "mean_agreement"),
                "conditional_accuracy": _avg(rows, "conditional_accuracy"),
                "instruction_compliance_rate": _avg(rows, "instruction_compliance_rate"),
                "answer_recovery_rate": _avg(rows, "answer_recovery_rate"),
                "answer_unanimous_rate": _avg(rows, "answer_unanimous_rate"),
                "prompt_invariant_incorrect_rate": _avg(rows, "prompt_invariant_incorrect_rate"),
                "n_questions": sum(int(float(r.get("n_questions", 0) or 0)) for r in rows),
            }
        return out

    def _update_scatter_chart(self) -> None:
        chart = QChart()
        chart.setBackgroundVisible(False)
        tc = _chart_text_colors()
        chart.legend().setLabelColor(tc["axis"])
        chart.setTitleBrush(tc["title"])
        chart.setTitle("Accuracy vs. agreement \u2014 every locally benchmarked model")

        summary = self._all_models_avg()
        if not summary:
            self.scatter_chart_view.setChart(chart)
            return

        axis_x = QValueAxis()
        axis_x.setRange(0, 100)
        axis_x.setTitleText("Agreement across P0\u2013P4 (%)")
        axis_x.setLabelsColor(tc["axis"])
        axis_y = QValueAxis()
        axis_y.setRange(0, 100)
        axis_y.setTitleText("Accuracy (%)")
        axis_y.setLabelsColor(tc["axis"])
        chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
        chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)

        for i, (tag, m) in enumerate(summary.items()):
            s = QScatterSeries()
            s.setName(backend.model_label(tag))
            s.setMarkerSize(18.0)
            s.setColor(_color_for(i))
            s.append(m["mean_agreement"] * 100, m["prompt_response_accuracy"] * 100)
            chart.addSeries(s)
            s.attachAxis(axis_x)
            s.attachAxis(axis_y)

        self.scatter_chart_view.setChart(chart)

    def _update_allmodel_bar_chart(self) -> None:
        chart = QChart()
        chart.setBackgroundVisible(False)
        tc = _chart_text_colors()
        chart.legend().setLabelColor(tc["axis"])
        chart.setTitleBrush(tc["title"])
        chart.setTitle("Accuracy, agreement & compliance \u2014 all locally benchmarked models")

        summary = self._all_models_avg()
        if not summary:
            self.allmodel_bar_view.setChart(chart)
            return

        tags = list(summary.keys())
        labels = [backend.model_label(t) for t in tags]

        series = QBarSeries()
        acc_set = QBarSet("Accuracy")
        acc_set.setColor(PRIMARY_COLOR)
        agree_set = QBarSet("Agreement")
        agree_set.setColor(QColor("#5fd18e"))
        compliance_set = QBarSet("Instr. compliance")
        compliance_set.setColor(QColor("#e8b45c"))
        for t in tags:
            m = summary[t]
            acc_set.append(m["prompt_response_accuracy"] * 100)
            agree_set.append(m["mean_agreement"] * 100)
            compliance_set.append(m["instruction_compliance_rate"] * 100)
        series.append(acc_set)
        series.append(agree_set)
        series.append(compliance_set)
        chart.addSeries(series)

        axis_x = QBarCategoryAxis()
        axis_x.append(labels)
        axis_x.setLabelsColor(tc["axis"])
        chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
        series.attachAxis(axis_x)
        axis_y = QValueAxis()
        axis_y.setRange(0, 100)
        axis_y.setLabelFormat("%d%%")
        axis_y.setLabelsColor(tc["axis"])
        chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
        series.attachAxis(axis_y)
        self.allmodel_bar_view.setChart(chart)

    def _update_leaderboard_table(self) -> None:
        table = self.leaderboard_table
        table.clear()
        summary = self._all_models_avg()
        columns = [
            "model", "n_questions", "prompt_response_accuracy", "mean_agreement",
            "conditional_accuracy", "instruction_compliance_rate",
            "answer_recovery_rate", "answer_unanimous_rate",
            "prompt_invariant_incorrect_rate",
        ]
        headers = [
            "Model", "Questions", "Accuracy", "Agreement", "Cond. accuracy",
            "Instr. compliance", "Recovery rate", "Unanimous rate", "Invariant-incorrect",
        ]
        # rank models best-accuracy-first so the leaderboard reads top to bottom
        ordered = sorted(summary.items(), key=lambda kv: kv[1]["prompt_response_accuracy"], reverse=True)

        table.setColumnCount(len(columns))
        table.setRowCount(len(ordered))
        table.setHorizontalHeaderLabels(headers)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)

        # best value per metric gets highlighted so the table doubles as a
        # quick "who wins on what" view, not just raw numbers.
        best_col: dict[str, float] = {}
        worse_is_better = {"prompt_invariant_incorrect_rate"}
        for col in columns[2:]:
            vals = [m[col] for _, m in ordered]
            if not vals:
                continue
            best_col[col] = min(vals) if col in worse_is_better else max(vals)

        for r_idx, (tag, m) in enumerate(ordered):
            rank_prefix = f"#{r_idx + 1} \u00b7 " if r_idx < 3 else ""
            values = [rank_prefix + backend.model_label(tag), str(m["n_questions"])]
            values += [f"{m[c] * 100:.1f}%" for c in columns[2:]]
            for c_idx, val in enumerate(values):
                item = QTableWidgetItem(val)
                item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
                col_key = columns[c_idx]
                if col_key in best_col and abs(m.get(col_key, -1) - best_col[col_key]) < 1e-9:
                    item.setForeground(QColor("#5fd18e"))
                table.setItem(r_idx, c_idx, item)

        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setStretchLastSection(True)

    def _update_detail_chart(self, rows: list[dict], compare_rows: list[dict]) -> None:
        """Grouped bar sitting above the Detailed table \u2014 accuracy, agreement
        and recovery rate per dataset for the active model (+ compare model
        if one is selected), so the raw numbers below always have a picture
        to go with them."""
        chart = QChart()
        chart.setBackgroundVisible(False)
        tc = _chart_text_colors()
        chart.legend().setLabelColor(tc["axis"])
        chart.setTitleBrush(tc["title"])
        chart.setTitle("Dataset breakdown \u2014 accuracy, agreement, recovery")

        if not rows:
            self.detail_chart_view.setChart(chart)
            return

        datasets = sorted({r["dataset"] for r in rows} | {r["dataset"] for r in compare_rows})
        by_ds = {r["dataset"]: r for r in rows}
        cmp_by_ds = {r["dataset"]: r for r in compare_rows}
        label = backend.model_label(self.model_tag) if self.model_tag else ""

        series = QBarSeries()
        metrics = [
            ("prompt_response_accuracy", "Accuracy"),
            ("mean_agreement", "Agreement"),
            ("answer_recovery_rate", "Recovery"),
        ]
        colors = [PRIMARY_COLOR, QColor("#5fd18e"), QColor("#e8b45c")]
        for (key, name), color in zip(metrics, colors):
            bset = QBarSet(f"{label} \u00b7 {name}")
            bset.setColor(color)
            for d in datasets:
                bset.append(float(by_ds.get(d, {}).get(key, 0) or 0) * 100)
            series.append(bset)

        if self.compare_tag and compare_rows:
            cmp_label = backend.model_label(self.compare_tag)
            cmp_acc = QBarSet(f"{cmp_label} \u00b7 Accuracy")
            cmp_acc.setColor(COMPARE_COLOR.darker(120))
            for d in datasets:
                cmp_acc.append(float(cmp_by_ds.get(d, {}).get("prompt_response_accuracy", 0) or 0) * 100)
            series.append(cmp_acc)

        chart.addSeries(series)
        axis_x = QBarCategoryAxis()
        axis_x.append([d.replace("_", " ").title() for d in datasets])
        axis_x.setLabelsColor(tc["axis"])
        chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
        series.attachAxis(axis_x)
        axis_y = QValueAxis()
        axis_y.setRange(0, 100)
        axis_y.setLabelFormat("%d%%")
        axis_y.setLabelsColor(tc["axis"])
        chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
        series.attachAxis(axis_y)
        self.detail_chart_view.setChart(chart)

    def _update_leaderboard_chart(self) -> None:
        """Horizontal-reading ranked bar above the Leaderboard table \u2014
        every locally benchmarked model's accuracy, sorted best to worst."""
        chart = QChart()
        chart.setBackgroundVisible(False)
        tc = _chart_text_colors()
        chart.legend().setLabelColor(tc["axis"])
        chart.setTitleBrush(tc["title"])
        chart.setTitle("Leaderboard \u2014 accuracy, ranked")

        summary = self._all_models_avg()
        if not summary:
            self.leaderboard_chart_view.setChart(chart)
            return

        ordered = sorted(summary.items(), key=lambda kv: kv[1]["prompt_response_accuracy"], reverse=True)
        labels = [backend.model_label(tag) for tag, _ in ordered]

        series = QBarSeries()
        acc_set = QBarSet("Accuracy")
        acc_set.setColor(PRIMARY_COLOR)
        agree_set = QBarSet("Agreement")
        agree_set.setColor(QColor("#5fd18e"))
        for _, m in ordered:
            acc_set.append(m["prompt_response_accuracy"] * 100)
            agree_set.append(m["mean_agreement"] * 100)
        series.append(acc_set)
        series.append(agree_set)
        chart.addSeries(series)

        axis_x = QBarCategoryAxis()
        axis_x.append(labels)
        axis_x.setLabelsColor(tc["axis"])
        chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
        series.attachAxis(axis_x)
        axis_y = QValueAxis()
        axis_y.setRange(0, 100)
        axis_y.setLabelFormat("%d%%")
        axis_y.setLabelsColor(tc["axis"])
        chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
        series.attachAxis(axis_y)
        self.leaderboard_chart_view.setChart(chart)

    # ---------------- PDF export ----------------

    def _export_pdf(self) -> None:
        if not self.model_tag:
            QMessageBox.information(self, "No model selected",
                                     "Pick a model and run a benchmark before exporting a summary.")
            return

        default_name = f"prism_summary_{self.model_tag.replace(':', '_').replace('/', '_')}.pdf"
        path, _ = QFileDialog.getSaveFileName(self, "Save PDF summary", default_name, "PDF files (*.pdf)")
        if not path:
            return

        rows = backend.model_dataset_rows(self.conn, self.model_tag)
        prompt_rows = backend.model_prompt_rows(self.conn, self.model_tag)
        info = backend.run_info(self.conn, self.model_tag)
        compare_rows = (
            backend.model_dataset_rows(self.conn, self.compare_tag)
            if (self.compare_tag and self.show_compare) else []
        )

        # grab the currently-rendered charts as images so the PDF mirrors
        # what's actually on screen, not a re-derived version of it
        chart_images = []
        for title, view in (
            ("Metrics by dataset", self.bar_chart_view),
            ("Accuracy by prompt condition", self.line_chart_view),
            ("Answer consistency", self.pie_chart_view),
            ("Accuracy vs. agreement (all models)", self.scatter_chart_view),
            ("All models \u2014 accuracy", self.allmodel_bar_view),
            ("Dataset breakdown", self.detail_chart_view),
            ("Leaderboard \u2014 accuracy, ranked", self.leaderboard_chart_view),
        ):
            pixmap = view.grab()
            if not pixmap.isNull():
                chart_images.append((title, pixmap))

        try:
            pdf_report.build_model_summary_pdf(
                path,
                model_label=backend.model_label(self.model_tag),
                model_tag=self.model_tag,
                run_info=info or {},
                dataset_rows=rows,
                prompt_rows=prompt_rows,
                compare_label=backend.model_label(self.compare_tag) if (self.compare_tag and self.show_compare) else None,
                compare_rows=compare_rows,
                leaderboard=self._all_models_avg(),
                chart_images=chart_images,
            )
        except Exception as exc:  # noqa: BLE001 - surface any export error to the user
            QMessageBox.warning(self, "Export failed", f"Could not write PDF:\n{exc}")
            return

        QMessageBox.information(self, "Summary exported", f"PDF summary saved to:\n{path}")