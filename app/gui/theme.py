"""
PRISM theme system.

Two palettes (dusk / paper), one QSS template. Native-desktop finish: sharp
(0-4px) corners, real 1px hairline borders instead of shadows/rounded cards,
flat surfaces, and the OS's own UI font. Nothing here should read as a
"card on a webpage" — it should read as Qt/Windows/macOS chrome.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Palette:
    name: str
    # base surfaces, darkest -> lightest elevation
    bg: str
    surface: str
    surface_raised: str
    surface_hover: str
    # text
    text: str
    text_dim: str
    text_faint: str
    # accents
    accent: str
    accent_soft: str
    accent_text: str
    # status
    good: str
    warn: str
    bad: str
    # structure
    hairline: str
    shadow: str


DUSK = Palette(
    name="dusk",
    bg="#000000",
    surface="#0a0a0a",
    surface_raised="#121212",
    surface_hover="#1a1a1a",
    text="#f2f2f2",
    text_dim="#a3a3a3",
    text_faint="#707070",
    accent="#8f7cf2",
    accent_soft="#211f2b",
    accent_text="#c9befa",
    good="#5fd18e",
    warn="#e8b45c",
    bad="#ea6b6b",
    hairline="#2c2c2c",
    shadow="#000000",
)

PAPER = Palette(
    name="paper",
    bg="#f3f1eb",
    surface="#fbfaf6",
    surface_raised="#ffffff",
    surface_hover="#eeece3",
    text="#2a2733",
    text_dim="#6b6879",
    text_faint="#9c99a8",
    accent="#6a52d6",
    accent_soft="#eae5fb",
    accent_text="#5a41c4",
    good="#28925f",
    warn="#b4791a",
    bad="#c94f4f",
    hairline="#d8d2c4",
    shadow="#c9c4b6",
)

# Sharp, native-chrome corner radii. Kept as named constants (rather than
# 0 everywhere) so small controls like checkboxes/pills still read as
# intentional rather than accidentally square.
R_NONE = "0px"
R_SM = "2px"
R_MD = "3px"


def build_qss(p: Palette) -> str:
    return f"""
    * {{
        font-family: "Segoe UI", "SF Pro Text", "Helvetica Neue", "Noto Sans", sans-serif;
        outline: none;
    }}

    QWidget {{
        background: transparent;
        color: {p.text};
        font-size: 13px;
    }}

    QMainWindow, #AppRoot {{
        background: {p.bg};
    }}

    /* ---------- Sidebar ---------- */
    #Sidebar {{
        background: {p.surface};
        border-right: 1px solid {p.hairline};
    }}
    #SidebarBrand {{
        color: {p.text};
        font-size: 16px;
        font-weight: 700;
        letter-spacing: 1.5px;
    }}
    #SidebarTagline {{
        color: {p.text_faint};
        font-size: 10.5px;
        letter-spacing: 0.5px;
    }}
    QPushButton#NavButton {{
        text-align: left;
        padding: 8px 12px;
        border-radius: {R_SM};
        border: 1px solid transparent;
        color: {p.text_dim};
        background: transparent;
        font-size: 13px;
        font-weight: 500;
    }}
    QPushButton#NavButton:hover {{
        background: {p.surface_hover};
        color: {p.text};
    }}
    QPushButton#NavButton:checked {{
        background: {p.accent_soft};
        color: {p.accent_text};
        border: 1px solid {p.hairline};
        font-weight: 600;
    }}

    /* ---------- Cards / surfaces ---------- */
    QFrame#Card {{
        background: {p.surface};
        border: 1px solid {p.hairline};
        border-radius: {R_SM};
    }}
    QFrame#CardFlat {{
        background: {p.surface_raised};
        border: 1px solid {p.hairline};
        border-radius: {R_SM};
    }}
    QFrame#CardRaised {{
        background: {p.surface_raised};
        border: 1px solid {p.hairline};
        border-radius: {R_SM};
    }}
    QFrame#Divider {{
        background: {p.hairline};
        max-height: 1px;
        min-height: 1px;
        border: none;
    }}

    /* ---------- Typography helpers ---------- */
    QLabel#H1 {{ font-size: 20px; font-weight: 600; color: {p.text}; }}
    QLabel#H2 {{ font-size: 14px; font-weight: 600; color: {p.text}; }}
    QLabel#Body {{ font-size: 13px; color: {p.text_dim}; }}
    QLabel#Faint {{ font-size: 11.5px; color: {p.text_faint}; }}
    QLabel#Stat {{ font-size: 22px; font-weight: 600; color: {p.text}; }}
    QLabel#StatLabel {{ font-size: 10.5px; color: {p.text_faint}; letter-spacing: 0.8px; }}
    QLabel#Pill {{
        padding: 2px 9px;
        border: 1px solid {p.hairline};
        border-radius: {R_SM};
        font-size: 10.5px;
        font-weight: 700;
        letter-spacing: 0.4px;
    }}

    /* ---------- Buttons ---------- */
    QPushButton {{
        background: {p.surface_raised};
        color: {p.text};
        border: 1px solid {p.hairline};
        border-radius: {R_SM};
        padding: 6px 14px;
        font-size: 12.5px;
        font-weight: 500;
    }}
    QPushButton:hover {{ background: {p.surface_hover}; border-color: {p.text_faint}; }}
    QPushButton:pressed {{ background: {p.accent_soft}; }}
    QPushButton:disabled {{ color: {p.text_faint}; border-color: {p.hairline}; }}

    QPushButton#Primary {{
        background: {p.accent};
        color: #ffffff;
        border: 1px solid {p.accent};
        font-weight: 600;
    }}
    QPushButton#Primary:hover {{ background: {p.accent_text}; border-color: {p.accent_text}; }}
    QPushButton#Primary:pressed {{ background: {p.accent}; }}
    QPushButton#Primary:disabled {{
        background: {p.surface_hover}; color: {p.text_faint}; border-color: {p.hairline};
    }}

    QPushButton#Danger {{
        background: transparent;
        color: {p.bad};
        border: 1px solid {p.bad};
    }}
    QPushButton#Danger:hover {{ background: rgba(234,107,107,0.12); }}

    QPushButton#Ghost {{
        background: transparent;
        border: 1px solid transparent;
        color: {p.text_dim};
        padding: 5px 8px;
    }}
    QPushButton#Ghost:hover {{ color: {p.text}; border-color: {p.hairline}; }}

    /* ---------- Inputs ---------- */
    QLineEdit, QComboBox, QSpinBox {{
        background: {p.surface_raised};
        border: 1px solid {p.hairline};
        border-radius: {R_SM};
        padding: 6px 9px;
        color: {p.text};
        selection-background-color: {p.accent_soft};
    }}
    QLineEdit:focus, QComboBox:focus {{ border: 1px solid {p.accent}; }}
    QComboBox::drop-down {{ border: none; width: 22px; }}
    QComboBox QAbstractItemView {{
        background: {p.surface_raised};
        border: 1px solid {p.hairline};
        border-radius: {R_SM};
        selection-background-color: {p.accent_soft};
        selection-color: {p.accent_text};
        outline: none;
        padding: 2px;
    }}

    QCheckBox {{ color: {p.text_dim}; spacing: 8px; }}
    QCheckBox::indicator {{
        width: 15px; height: 15px; border-radius: {R_SM};
        border: 1px solid {p.hairline}; background: {p.surface_raised};
    }}
    QCheckBox::indicator:checked {{ background: {p.accent}; border-color: {p.accent}; }}
    QCheckBox::indicator:hover {{ border-color: {p.text_faint}; }}

    /* ---------- Progress ---------- */
    QProgressBar {{
        background: {p.surface_raised};
        border: 1px solid {p.hairline};
        border-radius: {R_SM};
        height: 14px;
        text-align: center;
        color: {p.text_dim};
        font-size: 10.5px;
        font-weight: 600;
    }}
    QProgressBar::chunk {{
        background: {p.accent};
    }}
    QProgressBar#OverallBar {{
        height: 14px;
        border-radius: 7px;
    }}
    QProgressBar#OverallBar::chunk {{
        background: {p.accent};
        border-radius: 7px;
    }}
    QProgressBar#DatasetBar {{
        height: 10px;
        border-radius: 5px;
        background: {p.surface};
    }}
    QProgressBar#DatasetBar::chunk {{
        background: {p.good};
        border-radius: 5px;
    }}

    /* ---------- Tables ---------- */
    QTableWidget, QTableView {{
        background: {p.surface};
        alternate-background-color: {p.surface_raised};
        border: 1px solid {p.hairline};
        border-radius: {R_NONE};
        gridline-color: {p.hairline};
        selection-background-color: {p.accent_soft};
        selection-color: {p.text};
    }}
    QHeaderView::section {{
        background: {p.surface_raised};
        color: {p.text_faint};
        padding: 8px 10px;
        border: none;
        border-bottom: 1px solid {p.hairline};
        border-right: 1px solid {p.hairline};
        font-size: 10.5px;
        font-weight: 700;
        letter-spacing: 0.5px;
    }}
    QTableWidget::item {{ padding: 6px 10px; border: none; }}
    QTableCornerButton::section {{ background: {p.surface_raised}; border: none; border-bottom: 1px solid {p.hairline}; }}

    /* ---------- Tabs ---------- */
    QTabWidget::pane {{ border-top: 1px solid {p.hairline}; margin-top: 6px; }}
    QTabBar::tab {{
        background: transparent;
        color: {p.text_faint};
        padding: 7px 4px;
        margin-right: 20px;
        font-size: 12.5px;
        font-weight: 600;
        border-bottom: 2px solid transparent;
    }}
    QTabBar::tab:selected {{ color: {p.text}; border-bottom: 2px solid {p.accent}; }}
    QTabBar::tab:hover {{ color: {p.text}; }}

    /* ---------- Scrollbars ---------- */
    QScrollBar:vertical {{
        background: transparent; width: 12px; margin: 0px;
    }}
    QScrollBar::handle:vertical {{
        background: {p.hairline}; border-radius: {R_SM}; min-height: 30px;
    }}
    QScrollBar::handle:vertical:hover {{ background: {p.text_faint}; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
    QScrollBar:horizontal {{ background: transparent; height: 12px; margin: 0px; }}
    QScrollBar::handle:horizontal {{ background: {p.hairline}; border-radius: {R_SM}; min-width: 30px; }}

    QListWidget {{
        background: {p.surface};
        border: 1px solid {p.hairline};
        border-radius: {R_SM};
        padding: 2px;
    }}
    QListWidget::item {{
        padding: 7px 8px;
        border-radius: {R_SM};
        color: {p.text_dim};
    }}
    QListWidget::item:selected {{
        background: {p.accent_soft};
        color: {p.accent_text};
    }}
    QListWidget::item:hover {{ background: {p.surface_hover}; }}

    QTextEdit, QPlainTextEdit {{
        background: {p.surface_raised};
        border: 1px solid {p.hairline};
        border-radius: {R_SM};
        color: {p.text_dim};
        font-family: "Cascadia Mono", "SFMono-Regular", "Consolas", "Menlo", monospace;
        font-size: 11.5px;
        padding: 8px;
    }}

    QToolTip {{
        background: {p.surface_raised};
        color: {p.text};
        border: 1px solid {p.hairline};
        border-radius: {R_SM};
        padding: 4px 7px;
    }}

    QSplitter::handle {{ background: {p.hairline}; }}

    /* ---------- Startup / splash screen ---------- */
    #StartupRoot {{
        background: {p.bg};
    }}
    QLabel#BrandMark {{
        color: {p.text};
        font-size: 13px;
        font-weight: 700;
        letter-spacing: 1.5px;
    }}
    QFrame#StartupCard {{
        background: transparent;
        border: none;
    }}
    QLabel#StartupTitle {{
        font-size: 20px;
        font-weight: 600;
        color: {p.text};
    }}
    QLabel#StartupSubtitle {{
        font-size: 12.5px;
        color: {p.text_dim};
    }}
    QLabel#StartupFootnote {{
        font-size: 11px;
        color: {p.text_faint};
    }}
    QLabel#StartupStatusText {{
        font-size: 12px;
        color: {p.text_dim};
        font-weight: 600;
    }}
    QLabel#FieldLabel {{
        font-size: 11.5px;
        font-weight: 700;
        color: {p.text_dim};
        letter-spacing: 0.3px;
        margin-top: 6px;
    }}
    QComboBox#StartupCombo {{
        background: {p.surface_raised};
        border: 1px solid {p.hairline};
        border-radius: {R_SM};
        padding: 7px 10px;
        font-size: 13px;
        color: {p.text};
    }}
    QComboBox#StartupCombo:focus {{ border: 1px solid {p.accent}; }}
    QPushButton#StartupPrimaryBtn, QPushButton#StartupPrimaryBtnReady {{
        background: {p.accent};
        color: #ffffff;
        border: 1px solid {p.accent};
        border-radius: {R_SM};
        font-size: 13px;
        font-weight: 600;
    }}
    QPushButton#StartupPrimaryBtn:hover, QPushButton#StartupPrimaryBtnReady:hover {{
        background: {p.accent_text};
        border-color: {p.accent_text};
    }}
    QPushButton#StartupSkipLink {{
        background: transparent;
        border: none;
        color: {p.accent_text};
        font-size: 11.5px;
        font-weight: 600;
        text-align: left;
        padding: 2px 0px;
    }}
    QPushButton#StartupSkipLink:hover {{
        color: {p.accent};
        text-decoration: underline;
    }}
    QFrame#StartupModelsPanel {{
        background: {p.surface};
        border: 1px solid {p.hairline};
        border-radius: {R_SM};
    }}

    /* ---------- Native desktop chrome: menu bar / toolbar / status bar ---------- */
    QMenuBar {{
        background: {p.surface};
        color: {p.text_dim};
        border-bottom: 1px solid {p.hairline};
        padding: 1px 3px;
        font-size: 12.5px;
    }}
    QMenuBar::item {{ background: transparent; padding: 4px 9px; border-radius: {R_SM}; }}
    QMenuBar::item:selected {{ background: {p.surface_hover}; color: {p.text}; }}
    QMenu {{
        background: {p.surface_raised};
        color: {p.text};
        border: 1px solid {p.hairline};
        border-radius: {R_SM};
        padding: 3px;
    }}
    QMenu::item {{ padding: 6px 14px; border-radius: {R_SM}; }}
    QMenu::item:selected {{ background: {p.accent_soft}; color: {p.accent_text}; }}
    QMenu::separator {{ height: 1px; background: {p.hairline}; margin: 5px 4px; }}

    QToolBar#AppToolBar {{
        background: {p.surface};
        border-bottom: 1px solid {p.hairline};
        padding: 5px 8px;
        spacing: 3px;
    }}
    QToolBar#AppToolBar QToolButton {{
        background: transparent;
        color: {p.text_dim};
        border: 1px solid transparent;
        border-radius: {R_SM};
        padding: 6px 12px;
        font-size: 12.5px;
        font-weight: 500;
    }}
    QToolBar#AppToolBar QToolButton:hover {{ background: {p.surface_hover}; color: {p.text}; }}
    QToolBar#AppToolBar QToolButton:checked {{
        background: {p.accent_soft}; color: {p.accent_text}; border-color: {p.hairline};
    }}
    QToolBar::separator {{ background: {p.hairline}; width: 1px; margin: 4px 8px; }}

    QStatusBar#AppStatusBar {{
        background: {p.surface};
        border-top: 1px solid {p.hairline};
        color: {p.text_faint};
        font-size: 11px;
    }}
    QStatusBar#AppStatusBar QLabel {{ color: {p.text_faint}; font-size: 11px; padding: 0 6px; }}

    /* ---------- Model badge / compare chip ---------- */
    QFrame#ModelBadge {{
        background: {p.accent_soft};
        border: 1px solid {p.hairline};
        border-radius: {R_SM};
    }}
    QLabel#ModelBadgeText {{
        color: {p.accent_text};
        font-size: 11.5px;
        font-weight: 700;
    }}
    QLabel#ModelBadgeCaption {{
        color: {p.text_faint};
        font-size: 9.5px;
        letter-spacing: 0.5px;
    }}
    QPushButton#CompareBtn {{
        background: {p.surface_raised};
        color: {p.text};
        border: 1px solid {p.hairline};
        border-radius: {R_SM};
        padding: 6px 13px;
        font-size: 12px;
        font-weight: 500;
    }}
    QPushButton#CompareBtn:hover {{ background: {p.accent_soft}; color: {p.accent_text}; }}
    QPushButton#CompareBtn:checked {{ background: {p.accent}; color: #ffffff; border-color: {p.accent}; }}

    /* ---------- Compare drawer / empty-state CTA ---------- */
    QFrame#CompareDrawer {{
        background: {p.surface_raised};
        border: 1px solid {p.hairline};
        border-radius: {R_SM};
    }}
    QFrame#EmptyStateCard {{
        background: {p.surface_raised};
        border: 1px dashed {p.hairline};
        border-radius: {R_SM};
    }}
    QLabel#MetricValue {{
        font-size: 24px; font-weight: 700; color: {p.text};
    }}
    QLabel#MetricLabel {{
        font-size: 10px; font-weight: 700; color: {p.text_faint}; letter-spacing: 0.6px;
    }}
    QLabel#MetricCompare {{
        font-size: 11px; font-weight: 600; color: {p.good}; margin-top: 1px;
    }}
    QLabel#Kicker {{
        font-size: 10.5px; font-weight: 700; color: {p.accent_text};
        letter-spacing: 1.2px;
    }}
    """