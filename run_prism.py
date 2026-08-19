

"""
PRISM desktop app entry point.

    python run_prism.py

Launches the PySide6 GUI. The GUI (app/) is a thin presentation layer over
prism_core — a Qt-free benchmark engine (inference, parsing, consistency
scoring, reporting, local run index) that talks to Ollama directly and holds
no GUI code. app/ depends on prism_core; prism_core never imports app/.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtWidgets import QApplication

from app.gui.main_window import MainWindow


def main() -> None:
    app = QApplication(sys.argv)
    # Fusion is Qt's own native-feeling cross-platform style (proper focus
    # rects, real system-ish widgets) — a much better base for the QSS in
    # theme.py to sit on top of than whatever the platform default is.
    app.setStyle("Fusion")
    app.setApplicationName("PRISM")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
