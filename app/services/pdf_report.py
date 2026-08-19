"""
PRISM PDF summary export.

Builds a single-model "summary report" PDF: run metadata, headline metrics,
the dataset-level and prompt-condition tables, an optional comparison
model, an all-model leaderboard, and the on-screen dashboard charts
(passed in as already-rendered QPixmap grabs so the PDF matches what the
user was looking at).

Kept out of the GUI layer on purpose — this only knows about plain
dicts/lists/QPixmap, not about QChartView or the dashboard widget itself,
so it stays testable and reusable (e.g. from a future CLI "export" command).
"""

from __future__ import annotations

import io
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image,
    PageBreak, HRFlowable,
)

ACCENT = colors.HexColor("#6c5ce7")
GOOD = colors.HexColor("#2f9e5f")
DIM = colors.HexColor("#6b6b6b")
HEADER_BG = colors.HexColor("#f1effc")

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
    "prompt_invariant_incorrect_rate": "Invariant-incorrect", "prompt_condition": "Prompt",
    "accuracy": "Accuracy",
}


def _fmt(key: str, value: Any) -> str:
    if key in PCT_FIELDS:
        try:
            return f"{float(value) * 100:.1f}%"
        except (TypeError, ValueError):
            return str(value)
    return str(value)


def _avg(rows: list[dict], key: str) -> float:
    vals = [float(r.get(key, 0) or 0) for r in rows]
    return sum(vals) / len(vals) if vals else 0.0


def _styles():
    ss = getSampleStyleSheet()
    ss.add(ParagraphStyle("PrismTitle", parent=ss["Title"], textColor=ACCENT, fontSize=22, spaceAfter=2))
    ss.add(ParagraphStyle("PrismKicker", parent=ss["Normal"], textColor=DIM, fontSize=9, spaceAfter=10))
    ss.add(ParagraphStyle("PrismH2", parent=ss["Heading2"], textColor=colors.HexColor("#1a1a1a"),
                           spaceBefore=14, spaceAfter=6))
    ss.add(ParagraphStyle("PrismBody", parent=ss["BodyText"], textColor=colors.HexColor("#333333"),
                           fontSize=9.5, leading=13))
    return ss


def _metric_table(pairs: list[tuple[str, str]]) -> Table:
    data = [[k, v] for k, v in pairs]
    t = Table(data, colWidths=[70 * mm, 40 * mm])
    t.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("TEXTCOLOR", (0, 0), (0, -1), DIM),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica-Bold"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.HexColor("#e3e0f5")),
    ]))
    return t


def _rows_table(rows: list[dict], columns: list[str]) -> Table:
    header = [PRETTY.get(c, c.replace("_", " ").title()) for c in columns]
    data = [header]
    for r in rows:
        data.append([_fmt(c, r.get(c, "")) for c in columns])
    t = Table(data, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), HEADER_BG),
        ("TEXTCOLOR", (0, 0), (-1, 0), ACCENT),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.2),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#faf9fd")]),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#e3e0f5")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


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
    chart_images: Optional[list[tuple[str, Any]]] = None,
) -> None:
    """Renders a PRISM benchmark summary report to `out_path`.

    `chart_images` is a list of (title, QPixmap) grabs taken straight off
    the dashboard's chart views, so the PDF reflects the exact charts the
    user was looking at when they exported.
    """
    compare_rows = compare_rows or []
    leaderboard = leaderboard or {}
    chart_images = chart_images or []
    ss = _styles()

    doc = SimpleDocTemplate(
        str(out_path), pagesize=A4,
        topMargin=18 * mm, bottomMargin=16 * mm, leftMargin=16 * mm, rightMargin=16 * mm,
        title=f"PRISM summary \u2014 {model_label}",
    )

    story: list[Any] = []
    story.append(Paragraph("PRISM Benchmark Summary", ss["PrismTitle"]))
    story.append(Paragraph(
        f"Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} "
        "\u00b7 Prompt Reliability through Intelligent Semantic Multiplexing",
        ss["PrismKicker"],
    ))
    story.append(HRFlowable(width="100%", color=colors.HexColor("#e3e0f5"), thickness=1))
    story.append(Spacer(1, 10))

    story.append(Paragraph(model_label, ss["PrismH2"]))
    when = (run_info.get("finished_utc") or run_info.get("created_utc") or "")[:19].replace("T", " ")
    meta_bits = [f"Model tag: {model_tag}"]
    if when:
        meta_bits.append(f"Last run: {when} UTC")
    if run_info.get("benchmark_run_id"):
        meta_bits.append(f"Run ID: {run_info['benchmark_run_id']}")
    story.append(Paragraph(" &nbsp;\u00b7&nbsp; ".join(meta_bits), ss["PrismBody"]))
    story.append(Spacer(1, 8))

    # ---- headline metrics ----
    total_q = sum(int(float(r.get("n_questions", 0) or 0)) for r in dataset_rows)
    headline = [
        ("Questions run", str(total_q)),
        ("Accuracy", f"{_avg(dataset_rows, 'prompt_response_accuracy') * 100:.1f}%"),
        ("Agreement (P0\u2013P4)", f"{_avg(dataset_rows, 'mean_agreement') * 100:.1f}%"),
        ("Instruction compliance", f"{_avg(dataset_rows, 'instruction_compliance_rate') * 100:.1f}%"),
        ("Invariant-incorrect", f"{_avg(dataset_rows, 'prompt_invariant_incorrect_rate') * 100:.1f}%"),
    ]
    story.append(_metric_table(headline))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        "PRISM measures answer stability across five semantically equivalent prompts "
        "in addition to accuracy \u2014 a model can be highly consistent while being "
        "consistently wrong, so these numbers should be read together, not collapsed "
        "into a single score.",
        ss["PrismBody"],
    ))

    # ---- dataset-level table ----
    if dataset_rows:
        story.append(Paragraph("Results by dataset", ss["PrismH2"]))
        cols = [
            "dataset", "n_questions", "prompt_response_accuracy", "conditional_accuracy",
            "mean_agreement", "mean_prompt_sensitivity", "instruction_compliance_rate",
            "answer_recovery_rate", "answer_unanimous_rate", "prompt_invariant_incorrect_rate",
        ]
        story.append(_rows_table(dataset_rows, cols))

    # ---- prompt-condition table ----
    if prompt_rows:
        story.append(Paragraph("Results by prompt condition (P0\u2013P4)", ss["PrismH2"]))
        cols = [c for c in ("dataset", "prompt_condition", "accuracy",
                             "instruction_compliant_rate") if c in prompt_rows[0]]
        if cols:
            story.append(_rows_table(prompt_rows, cols))

    # ---- comparison model ----
    if compare_label and compare_rows:
        story.append(Paragraph(f"Comparison \u2014 {compare_label}", ss["PrismH2"]))
        cmp_headline = [
            ("Questions run", str(sum(int(float(r.get("n_questions", 0) or 0)) for r in compare_rows))),
            ("Accuracy", f"{_avg(compare_rows, 'prompt_response_accuracy') * 100:.1f}%"),
            ("Agreement (P0\u2013P4)", f"{_avg(compare_rows, 'mean_agreement') * 100:.1f}%"),
            ("Instruction compliance", f"{_avg(compare_rows, 'instruction_compliance_rate') * 100:.1f}%"),
        ]
        story.append(_metric_table(cmp_headline))

    # ---- charts ----
    if chart_images:
        story.append(PageBreak())
        story.append(Paragraph("Dashboard charts", ss["PrismH2"]))
        max_w = doc.width
        for title, pixmap in chart_images:
            try:
                buf = io.BytesIO()
                # QPixmap.save writes directly into a QBuffer normally, but a
                # plain BytesIO works too via the PNG bytes round-trip below.
                from PySide6.QtCore import QBuffer, QIODevice
                qbuf = QBuffer()
                qbuf.open(QIODevice.OpenModeFlag.WriteOnly)
                pixmap.save(qbuf, "PNG")
                buf.write(bytes(qbuf.data()))
                qbuf.close()
                buf.seek(0)
                w, h = pixmap.width(), pixmap.height()
                scale = min(max_w / w, 1.0)
                img = Image(buf, width=w * scale, height=h * scale)
                story.append(Paragraph(title, ss["PrismBody"]))
                story.append(img)
                story.append(Spacer(1, 10))
            except Exception:
                continue

    # ---- all-model leaderboard ----
    if leaderboard:
        story.append(PageBreak())
        story.append(Paragraph("Leaderboard \u2014 all locally benchmarked models", ss["PrismH2"]))
        ordered = sorted(leaderboard.items(), key=lambda kv: kv[1]["prompt_response_accuracy"], reverse=True)
        header = ["Model", "Questions", "Accuracy", "Agreement", "Instr. compliance", "Invariant-incorrect"]
        data = [header]
        for tag, m in ordered:
            data.append([
                tag, str(m["n_questions"]),
                f"{m['prompt_response_accuracy'] * 100:.1f}%",
                f"{m['mean_agreement'] * 100:.1f}%",
                f"{m['instruction_compliance_rate'] * 100:.1f}%",
                f"{m['prompt_invariant_incorrect_rate'] * 100:.1f}%",
            ])
        t = Table(data, repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), HEADER_BG),
            ("TEXTCOLOR", (0, 0), (-1, 0), ACCENT),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#faf9fd")]),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#e3e0f5")),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(t)

    doc.build(story)