"""PDF summary export for the Dashboard screen's "Download PDF" button.

Builds a single-model (optionally vs. a comparison model) benchmark summary
as a PDF, using reportlab. This is intentionally the *only* place PDF layout
lives - the Dashboard screen just gathers the rows/images and hands them to
:func:`build_model_summary_pdf`.

Sections, in order:

1. Title block - model name/tag, run metadata (dataset version, run id, when
   it completed).
2. Key metrics table - one row per dataset for the primary model, and (if a
   comparison model is selected) its rows too, so the two are easy to scan
   side by side.
3. Prompt-condition (P0-P4) breakdown, if available.
4. Chart images grabbed live from the Dashboard's on-screen charts, so the
   PDF matches what the user was looking at when they clicked "Download PDF".
5. A cross-model leaderboard, for context beyond the one/two models in focus.

Every row value is defensively coerced with ``_f``/``_pct`` since the input
dicts come straight from CSV/SQLite reads and may have missing or blank
fields (e.g. a dataset with zero completed requests).
"""
from __future__ import annotations

import io
from pathlib import Path
from typing import Any, Iterable, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# Column labels shared between the dataset-level and leaderboard tables.
_ACCENT = colors.HexColor("#5b4bd6")
_HAIRLINE = colors.HexColor("#dcd8ea")
_TEXT_FAINT = colors.HexColor("#6b6878")


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _pct(value: Any) -> str:
    return f"{_f(value) * 100.0:.1f}%"


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "PrismTitle", parent=base["Title"], fontSize=22, leading=26,
            textColor=colors.HexColor("#221f2b"),
        ),
        "subtitle": ParagraphStyle(
            "PrismSubtitle", parent=base["Normal"], fontSize=10.5, leading=14,
            textColor=_TEXT_FAINT, spaceAfter=4,
        ),
        "h2": ParagraphStyle(
            "PrismH2", parent=base["Heading2"], fontSize=14, leading=18,
            textColor=colors.HexColor("#221f2b"), spaceBefore=18, spaceAfter=8,
        ),
        "body": ParagraphStyle(
            "PrismBody", parent=base["Normal"], fontSize=9.5, leading=13,
            textColor=colors.HexColor("#3a3745"),
        ),
        "caption": ParagraphStyle(
            "PrismCaption", parent=base["Normal"], fontSize=8.5, leading=11,
            textColor=_TEXT_FAINT, spaceBefore=4, spaceAfter=10,
        ),
    }


def _metrics_table(
    rows: list[dict[str, Any]],
    *,
    row_label_key: str = "dataset",
    row_label_title: str = "Dataset",
) -> Table:
    """One row per dataset (or per model, for the leaderboard) with the core
    accuracy/consistency metrics side by side."""
    headers = [
        row_label_title, "Questions", "Accuracy", "Agreement",
        "Compliance", "Recovery", "Unknown", "Invariant Wrong",
    ]
    data = [headers]
    for row in rows:
        data.append([
            str(row.get(row_label_key, "")),
            str(int(_f(row.get("n_questions")))),
            _pct(row.get("prompt_response_accuracy")),
            _pct(row.get("mean_agreement")),
            _pct(row.get("instruction_compliance_rate")),
            _pct(row.get("answer_recovery_rate")),
            _pct(row.get("unknown_rate")),
            _pct(row.get("prompt_invariant_incorrect_rate")),
        ])

    table = Table(data, hAlign="LEFT", repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), _ACCENT),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f3fb")]),
        ("GRID", (0, 0), (-1, -1), 0.5, _HAIRLINE),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return table


def _prompt_table(rows: list[dict[str, Any]]) -> Table:
    headers = ["Dataset", "Condition", "Observed", "Accuracy", "Compliance", "Recovery"]
    data = [headers]
    for row in sorted(rows, key=lambda r: (str(r.get("dataset", "")), str(r.get("prompt_condition", "")))):
        data.append([
            str(row.get("dataset", "")),
            str(row.get("prompt_condition", "")),
            str(row.get("n_observed", row.get("n_recovered", ""))),
            _pct(row.get("accuracy")),
            _pct(row.get("instruction_compliant_rate")),
            _pct(row.get("answer_recovery_rate")),
        ])

    table = Table(data, hAlign="LEFT", repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#3a3745")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f3fb")]),
        ("GRID", (0, 0), (-1, -1), 0.5, _HAIRLINE),
        ("ALIGN", (2, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return table


def _leaderboard_table(leaderboard: dict[str, dict[str, float]]) -> Table:
    headers = ["Model", "Questions", "Accuracy", "Agreement", "Compliance", "Invariant Wrong"]
    data = [headers]
    for tag, m in sorted(leaderboard.items(), key=lambda kv: kv[1].get("prompt_response_accuracy", 0.0), reverse=True):
        data.append([
            tag,
            str(int(_f(m.get("n_questions")))),
            _pct(m.get("prompt_response_accuracy")),
            _pct(m.get("mean_agreement")),
            _pct(m.get("instruction_compliance_rate")),
            _pct(m.get("prompt_invariant_incorrect_rate")),
        ])

    table = Table(data, hAlign="LEFT", repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), _ACCENT),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f3fb")]),
        ("GRID", (0, 0), (-1, -1), 0.5, _HAIRLINE),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return table


def _pixmap_to_image_flowable(pixmap: Any, *, max_width: float) -> Optional[Image]:
    """Convert a QPixmap grabbed from the live dashboard charts into a
    reportlab Image flowable, scaled to fit the page width. Returns None if
    the pixmap can't be encoded (e.g. it's empty)."""
    if pixmap is None or pixmap.isNull():
        return None
    try:
        from PySide6.QtCore import QBuffer, QIODevice
    except ImportError:
        return None

    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    pixmap.save(buffer, "PNG")
    png_bytes = bytes(buffer.data())
    buffer.close()
    if not png_bytes:
        return None

    stream = io.BytesIO(png_bytes)
    img = Image(stream)
    scale = min(1.0, max_width / img.imageWidth)
    img.drawWidth = img.imageWidth * scale
    img.drawHeight = img.imageHeight * scale
    return img


def build_model_summary_pdf(
    out_path: str | Path,
    *,
    model_label: str,
    model_tag: str,
    run_info: dict[str, Any],
    dataset_rows: list[dict[str, Any]],
    prompt_rows: list[dict[str, Any]],
    compare_label: Optional[str] = None,
    compare_rows: Optional[list[dict[str, Any]]] = None,
    leaderboard: Optional[dict[str, dict[str, float]]] = None,
    chart_images: Optional[Iterable[tuple[str, Any]]] = None,
) -> None:
    """Render a PDF benchmark summary for one model to ``out_path``.

    Raises on any I/O or rendering failure - the caller (Dashboard screen)
    catches this and shows the error to the user rather than silently
    producing a corrupt or empty file.
    """
    out_path = Path(out_path)
    styles = _styles()

    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=letter,
        leftMargin=0.7 * inch, rightMargin=0.7 * inch,
        topMargin=0.7 * inch, bottomMargin=0.7 * inch,
        title=f"PRISM summary - {model_label}",
    )

    story: list[Any] = []

    # ---- Title block --------------------------------------------------
    story.append(Paragraph("PRISM Benchmark Summary", styles["title"]))
    story.append(Paragraph(f"{model_label}  ({model_tag})", styles["subtitle"]))

    meta_bits = []
    if run_info.get("benchmark_run_id"):
        meta_bits.append(f"Run ID: {run_info['benchmark_run_id']}")
    if run_info.get("completed_at"):
        meta_bits.append(f"Completed: {run_info['completed_at']}")
    if compare_label:
        meta_bits.append(f"Compared with: {compare_label}")
    if meta_bits:
        story.append(Paragraph("  \u00b7  ".join(meta_bits), styles["caption"]))

    story.append(Spacer(1, 6))

    # ---- Key metrics ----------------------------------------------------
    story.append(Paragraph(f"Results - {model_label}", styles["h2"]))
    if dataset_rows:
        story.append(_metrics_table(dataset_rows))
    else:
        story.append(Paragraph("No dataset-level results available for this model.", styles["body"]))

    if compare_label and compare_rows:
        story.append(Paragraph(f"Results - {compare_label}", styles["h2"]))
        story.append(_metrics_table(compare_rows))

    # ---- Prompt-condition breakdown --------------------------------------
    if prompt_rows:
        story.append(Paragraph("Accuracy by Prompt Condition (P0-P4)", styles["h2"]))
        story.append(_prompt_table(prompt_rows))

    # ---- Charts -----------------------------------------------------------
    images = list(chart_images or [])
    if images:
        story.append(PageBreak())
        story.append(Paragraph("Charts", styles["h2"]))
        usable_width = doc.width
        for title, pixmap in images:
            story.append(Paragraph(str(title), styles["body"]))
            flowable = _pixmap_to_image_flowable(pixmap, max_width=usable_width)
            if flowable is not None:
                story.append(Spacer(1, 4))
                story.append(flowable)
                story.append(Spacer(1, 14))

    # ---- Leaderboard --------------------------------------------------
    if leaderboard:
        story.append(PageBreak())
        story.append(Paragraph("All Models - Leaderboard", styles["h2"]))
        story.append(Paragraph(
            "Average dataset-level metrics across all locally available "
            "benchmark data for every model, for context beyond the "
            "model(s) above.",
            styles["caption"],
        ))
        story.append(_leaderboard_table(leaderboard))

    doc.build(story)