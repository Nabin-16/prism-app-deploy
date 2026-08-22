from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QPushButton

from app.gui.widgets import card, h2, body, faint, divider, SectionHeader

# TODO: replace with the real PRISM project website once it's live.
PRISM_WEBSITE_URL = "https://prism-project.example.com"
PRISM_DOCS_URL = "https://prism-project.example.com/docs"


class SettingsScreen(QWidget):
    theme_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(36, 32, 36, 32)
        root.setSpacing(22)

        root.addWidget(SectionHeader("Settings", "Appearance and app information."))

        appearance = card("Card")
        al = QVBoxLayout(appearance)
        al.setContentsMargins(24, 22, 24, 22)
        al.setSpacing(12)
        al.addWidget(h2("Appearance"))

        row = QHBoxLayout()
        row.addWidget(body("Choose the theme PRISM runs in."))
        row.addStretch(1)

        self.dark_btn = QPushButton("Dusk (dark)")
        self.light_btn = QPushButton("Paper (light)")
        for b in (self.dark_btn, self.light_btn):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setCheckable(True)
        self.dark_btn.clicked.connect(lambda: self._pick("dusk"))
        self.light_btn.clicked.connect(lambda: self._pick("paper"))
        row.addWidget(self.dark_btn)
        row.addWidget(self.light_btn)
        al.addLayout(row)
        root.addWidget(appearance)

        about = card("Card")
        bl = QVBoxLayout(about)
        bl.setContentsMargins(24, 22, 24, 22)
        bl.setSpacing(10)
        bl.addWidget(h2("About PRISM"))

        bl.addWidget(body(
            "<b>PRISM (Prompt Reliability Through Intelligent Semantic "
            "Multiplexing)</b> is a benchmark and local desktop application "
            "for evaluating how small, locally runnable language models "
            "behave when the same question is presented through different, "
            "semantically equivalent prompt formulations."
        ))
        bl.addWidget(body(
            "It was created to make prompt-dependent model behavior "
            "directly observable and measurable rather than leaving it as "
            "an assumption."
        ))
        bl.addWidget(body(
            "PRISM sends the same question through several prompt "
            "formulations, evaluates each response independently, and "
            "reports where a model's behavior stayed stable and where it "
            "did not."
        ))
        bl.addWidget(body(
            "The desktop application performs benchmark execution locally, "
            "while the public website provides documentation and access to "
            "published benchmark results."
        ))

        links_row = QHBoxLayout()
        self.website_btn = QPushButton("Download the app")
        self.docs_btn = QPushButton("Documentation")
        for b in (self.website_btn, self.docs_btn):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
        self.website_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(PRISM_WEBSITE_URL))
        )
        self.docs_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(PRISM_DOCS_URL))
        )
        links_row.addWidget(self.website_btn)
        links_row.addWidget(self.docs_btn)
        links_row.addStretch(1)
        bl.addLayout(links_row)

        what_card = card("CardRaised")
        wl = QVBoxLayout(what_card)
        wl.setContentsMargins(16, 14, 16, 14)
        wl.setSpacing(6)
        wl.addWidget(h2("What PRISM does"))
        wl.addWidget(body(
            "1. Presents the same underlying question through <b>five "
            "distinct prompt formulations</b>."
        ))
        wl.addWidget(body(
            "2. Evaluates each response independently for <b>correctness, "
            "instruction compliance, and answer recoverability</b>."
        ))
        wl.addWidget(body(
            "3. Reports where a model's behavior <b>stayed stable</b> and "
            "where it <b>did not</b> across those formulations."
        ))
        bl.addWidget(what_card)

        bl.addWidget(faint("Protocol 1.0 · Templates 1.0 · Local-only inference · Temperature 0"))
        bl.addWidget(faint(
            "This project is developed as part of a 6th semester computer "
            "engineering curriculum."
        ))

        data_row = QHBoxLayout()
        data_row.addWidget(faint("Local data lives at:"))
        data_row.addStretch(1)
        bl.addLayout(data_row)
        path_lbl = QLabel(str(Path.home() / ".prism"))
        path_lbl.setObjectName("Faint")
        path_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        bl.addWidget(path_lbl)
        root.addWidget(about)

        root.addStretch(1)

    def set_active(self, theme: str) -> None:
        self.dark_btn.setChecked(theme == "dusk")
        self.light_btn.setChecked(theme == "paper")

    def _pick(self, theme: str) -> None:
        self.set_active(theme)
        self.theme_changed.emit(theme)