from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QLabel, QVBoxLayout, QHBoxLayout, QWidget, QGraphicsDropShadowEffect,
    QPushButton, QSizePolicy,
)
from PySide6.QtGui import QColor


# Ported from prompt-reliability's prism_app/widgets/layout.py: a
# horizontally-centred, max-width content column. Used to blend that
# project's calmer single-column composition into screens (like the
# Benchmark screen) that would otherwise stretch to the full window width.
CONTENT_MAX_WIDTH = 900


def centered_column(
    host: QWidget,
    *,
    max_width: int = CONTENT_MAX_WIDTH,
    margins: tuple[int, int, int, int] = (24, 24, 24, 24),
    spacing: int = 16,
) -> QVBoxLayout:
    """Install a horizontally-centred, max-width content column on *host*.

    Returns the inner QVBoxLayout for the screen's content - a view's own
    build method keeps adding widgets to the returned layout exactly as
    before. On windows narrower than *max_width* the column simply uses
    whatever width is available.
    """
    outer = QHBoxLayout(host)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)
    outer.addStretch(1)

    column = QWidget()
    column.setObjectName("ContentColumn")
    column.setMaximumWidth(max_width)
    column.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    outer.addWidget(column, 20)

    outer.addStretch(1)

    inner = QVBoxLayout(column)
    inner.setContentsMargins(*margins)
    inner.setSpacing(spacing)
    return inner


def status_badge(text: str, object_name: str = "StateBadge") -> QLabel:
    """Small pill-style status label, ported in spirit from
    prompt-reliability's progress_view state badge (READY/RUNNING/etc.)."""
    lbl = QLabel(text)
    lbl.setObjectName(object_name)
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return lbl


def card(object_name: str = "Card") -> QFrame:
    f = QFrame()
    f.setObjectName(object_name)
    shadow = QGraphicsDropShadowEffect(f)
    shadow.setBlurRadius(28)
    shadow.setOffset(0, 6)
    shadow.setColor(QColor(0, 0, 0, 60))
    f.setGraphicsEffect(shadow)
    return f


def h1(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("H1")
    lbl.setWordWrap(True)
    return lbl


def h2(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("H2")
    lbl.setWordWrap(True)
    return lbl


def body(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("Body")
    lbl.setWordWrap(True)
    return lbl


def faint(text: str, wrap: bool = True) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("Faint")
    # Word-wrap by default so short captions used inside fixed/half-width
    # cards (e.g. side-by-side section cards) never force the layout wider
    # than its container - that forced-width was clipping cards at narrow
    # window sizes instead of reflowing. Callers that truly want a single-
    # line caption (pills, inline stat labels) can pass wrap=False.
    lbl.setWordWrap(wrap)
    return lbl


def divider() -> QFrame:
    f = QFrame()
    f.setObjectName("Divider")
    f.setFrameShape(QFrame.Shape.NoFrame)
    return f


def pill(text: str, color: str, soft_bg: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("Pill")
    lbl.setStyleSheet(f"background:{soft_bg}; color:{color};")
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return lbl


class StatTile(QFrame):
    def __init__(self, label: str, value: str = " - ", parent=None):
        super().__init__(parent)
        self.setObjectName("CardRaised")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(4)
        self.value_lbl = QLabel(value)
        self.value_lbl.setObjectName("Stat")
        self.value_lbl.setWordWrap(True)
        self.label_lbl = QLabel(label.upper())
        self.label_lbl.setObjectName("StatLabel")
        self.label_lbl.setWordWrap(True)
        lay.addWidget(self.value_lbl)
        lay.addWidget(self.label_lbl)

    def set_value(self, value: str) -> None:
        self.value_lbl.setText(value)


class SectionHeader(QWidget):
    def __init__(self, title: str, subtitle: str = "", parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        lay.addWidget(h1(title))
        if subtitle:
            lay.addWidget(body(subtitle))


def kicker(text: str) -> QLabel:
    lbl = QLabel(text.upper())
    lbl.setObjectName("Kicker")
    return lbl


class MetricTile(QFrame):
    """A dense stat tile: big value, small caption. Used on the model-scoped
    dashboard header (accuracy, agreement, questions run, etc.)."""

    def __init__(self, label: str, value: str = " - ", parent=None):
        super().__init__(parent)
        self.setObjectName("CardRaised")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(4)
        self.value_lbl = QLabel(value)
        self.value_lbl.setObjectName("MetricValue")
        self.value_lbl.setWordWrap(True)
        self.compare_lbl = QLabel("")
        self.compare_lbl.setObjectName("MetricCompare")
        self.compare_lbl.setWordWrap(True)
        self.compare_lbl.setVisible(False)
        self.label_lbl = QLabel(label.upper())
        self.label_lbl.setObjectName("MetricLabel")
        self.label_lbl.setWordWrap(True)
        lay.addWidget(self.value_lbl)
        lay.addWidget(self.compare_lbl)
        lay.addWidget(self.label_lbl)

    def set_value(self, value: str) -> None:
        self.value_lbl.setText(value)

    def set_compare(self, text: str | None) -> None:
        """Show a second, smaller line ('vs. <other model> 42.3%') below the
        primary value when a comparison model is active. Pass None to hide it."""
        if text:
            self.compare_lbl.setText(text)
            self.compare_lbl.setVisible(True)
        else:
            self.compare_lbl.setText("")
            self.compare_lbl.setVisible(False)


class ModelBadge(QFrame):
    """Compact 'active model' chip shown in the toolbar."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ModelBadge")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 4, 12, 5)
        lay.setSpacing(0)
        self.caption = QLabel("ACTIVE MODEL")
        self.caption.setObjectName("ModelBadgeCaption")
        self.text = QLabel("None selected")
        self.text.setObjectName("ModelBadgeText")
        # Elide (never wrap - it must stay one line in the toolbar) so a
        # long custom model tag on a narrow window shrinks its label
        # instead of pushing the toolbar's other buttons off-screen.
        self.text.setMaximumWidth(180)
        self.text.setToolTip("None selected")
        lay.addWidget(self.caption)
        lay.addWidget(self.text)

    def set_model(self, label: str) -> None:
        from PySide6.QtGui import QFontMetrics
        metrics = QFontMetrics(self.text.font())
        elided = metrics.elidedText(label, Qt.TextElideMode.ElideRight, self.text.maximumWidth())
        self.text.setText(elided)
        self.text.setToolTip(label)


class EmptyStateCTA(QFrame):
    """'No data yet' card with a single call-to-action button - used for the
    compare panel when the chosen model hasn't been benchmarked locally."""

    def __init__(self, title: str, body_text: str, button_text: str, parent=None):
        super().__init__(parent)
        self.setObjectName("EmptyStateCard")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 20, 22, 20)
        lay.setSpacing(8)
        t = QLabel(title)
        t.setObjectName("H2")
        lay.addWidget(t)
        b = body(body_text)
        lay.addWidget(b)
        row = QHBoxLayout()
        self.button = QPushButton(button_text)
        self.button.setObjectName("Primary")
        self.button.setCursor(Qt.CursorShape.PointingHandCursor)
        row.addWidget(self.button)
        row.addStretch(1)
        lay.addLayout(row)