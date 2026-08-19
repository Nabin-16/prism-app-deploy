from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QPushButton

from app.gui.widgets import card, h2, body, faint, divider, SectionHeader


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
        bl.setSpacing(6)
        bl.addWidget(h2("About PRISM"))
        bl.addWidget(body(
            "PRISM benchmarks how reliably small language models answer the same "
            "question when it's phrased in five different but equivalent ways, "
            "running entirely against your local Ollama installation. The engine "
            "(prism_core) is Qt-free and reusable outside this app; every run is "
            "indexed locally at ~/.prism, and completed runs are mirrored to the "
            "project's shared results automatically."
        ))
        bl.addWidget(faint("Protocol 1.0 · Templates 1.0 · Local-only inference · Temperature 0"))

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