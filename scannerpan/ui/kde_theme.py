"""
KDE Plasma & Breeze Theme Integration for ScannerPan.
Provides automatic detection of KDE Dark/Light mode and applies
a polished Breeze-style design system with #3daee9 accent.
"""

import sys
import subprocess
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPalette, QColor, QFont, QIcon
from PyQt6.QtCore import Qt


def is_system_dark_mode() -> bool:
    """
    Detects if the desktop environment (KDE Plasma, GNOME, or FreeDesktop)
    is currently using a dark theme.
    """
    # 1. Try KDE kreadconfig6 / kreadconfig5
    for cmd in ["kreadconfig6", "kreadconfig5"]:
        try:
            res = subprocess.run(
                [cmd, "--group", "General", "--key", "ColorScheme"],
                capture_output=True, text=True, timeout=1
            )
            if res.returncode == 0:
                scheme = res.stdout.strip().lower()
                if "dark" in scheme or "black" in scheme:
                    return True
                if "light" in scheme or "breeze" in scheme:
                    return False
        except Exception:
            pass

    # 2. Try FreeDesktop portal via gsettings / dbus
    try:
        res = subprocess.run(
            ["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"],
            capture_output=True, text=True, timeout=1
        )
        if res.returncode == 0:
            val = res.stdout.strip().lower().strip("'\"")
            if "prefer-dark" in val or "dark" in val:
                return True
            if "default" in val or "light" in val:
                return False
    except Exception:
        pass

    # 3. Fallback: check QApplication palette window brightness if app exists
    app = QApplication.instance()
    if app:
        bg = app.palette().color(QPalette.ColorRole.Window)
        # Luminance test: 0.299*R + 0.587*G + 0.114*B
        lum = 0.299 * bg.red() + 0.587 * bg.green() + 0.114 * bg.blue()
        return lum < 128

    return True  # Default to modern dark if indeterminate


def get_breeze_stylesheet(dark: bool = True) -> str:
    """
    Returns a modern, polished stylesheet following KDE Plasma Breeze guidelines.
    Accent color: #3daee9 (KDE Breeze Highlight Blue).
    """
    if dark:
        bg_main = "#232629"
        bg_card = "#31363b"
        bg_input = "#1b1e20"
        bg_hover = "#3b4045"
        bg_selected = "#3daee9"
        text_main = "#eff0f1"
        text_muted = "#bdc3c7"
        border_col = "#444a50"
        border_focus = "#3daee9"
        scrollbar_bg = "#232629"
        scrollbar_handle = "#4d535a"
    else:
        bg_main = "#f7f7f7"
        bg_card = "#ffffff"
        bg_input = "#fcfcfc"
        bg_hover = "#e4e7ea"
        bg_selected = "#3daee9"
        text_main = "#232629"
        text_muted = "#656d76"
        border_col = "#d0d4d8"
        border_focus = "#3daee9"
        scrollbar_bg = "#f0f2f4"
        scrollbar_handle = "#c4c8cd"

    return f"""
    /* KDE Breeze Design System for ScannerPan */
    QWidget {{
        background-color: {bg_main};
        color: {text_main};
        font-family: "Noto Sans", "Cantarell", "Ubuntu", "Segoe UI", sans-serif;
        font-size: 10pt;
        selection-background-color: {bg_selected};
        selection-color: #ffffff;
    }}

    QMainWindow, QDialog {{
        background-color: {bg_main};
    }}

    /* GroupBox and Cards */
    QGroupBox {{
        background-color: {bg_card};
        border: 1px solid {border_col};
        border-radius: 6px;
        margin-top: 12px;
        padding-top: 16px;
        padding-left: 8px;
        padding-right: 8px;
        padding-bottom: 8px;
        font-weight: bold;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        left: 12px;
        padding: 0 4px;
        color: {bg_selected};
    }}

    /* Buttons */
    QPushButton {{
        background-color: {bg_card};
        color: {text_main};
        border: 1px solid {border_col};
        border-radius: 5px;
        padding: 6px 14px;
        font-weight: 500;
        min-height: 22px;
    }}
    QPushButton:hover {{
        background-color: {bg_hover};
        border-color: {border_focus};
    }}
    QPushButton:pressed {{
        background-color: {bg_input};
        border-color: {border_focus};
    }}
    QPushButton:disabled {{
        background-color: {bg_main};
        color: {text_muted};
        border-color: {border_col};
    }}

    /* Primary Accent Buttons */
    QPushButton#primaryButton, QPushButton[primary="true"] {{
        background-color: #3daee9;
        color: #ffffff;
        border: 1px solid #2980b9;
        font-weight: bold;
    }}
    QPushButton#primaryButton:hover, QPushButton[primary="true"]:hover {{
        background-color: #49bcf2;
        border-color: #3daee9;
    }}
    QPushButton#primaryButton:pressed, QPushButton[primary="true"]:pressed {{
        background-color: #2980b9;
    }}

    /* LineEdits, ComboBoxes, SpinBoxes */
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
        background-color: {bg_input};
        color: {text_main};
        border: 1px solid {border_col};
        border-radius: 5px;
        padding: 5px 8px;
        min-height: 20px;
    }}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
        border: 1px solid {border_focus};
    }}
    QComboBox::drop-down {{
        subcontrol-origin: padding;
        subcontrol-position: top right;
        width: 22px;
        border-left-width: 0px;
    }}
    QComboBox QAbstractItemView {{
        background-color: {bg_card};
        border: 1px solid {border_col};
        selection-background-color: {bg_selected};
        selection-color: #ffffff;
        border-radius: 4px;
        outline: none;
    }}

    /* Toolbars */
    QToolBar {{
        background-color: {bg_card};
        border-bottom: 1px solid {border_col};
        padding: 4px;
        spacing: 4px;
    }}
    QToolButton {{
        background-color: transparent;
        border: 1px solid transparent;
        border-radius: 4px;
        padding: 6px;
        font-weight: 500;
    }}
    QToolButton:hover {{
        background-color: {bg_hover};
        border: 1px solid {border_col};
    }}
    QToolButton:pressed {{
        background-color: {bg_input};
    }}

    /* Scrollbars */
    QScrollBar:vertical {{
        background-color: {scrollbar_bg};
        width: 12px;
        margin: 0px;
        border-radius: 6px;
    }}
    QScrollBar::handle:vertical {{
        background-color: {scrollbar_handle};
        min-height: 24px;
        border-radius: 5px;
        margin: 2px;
    }}
    QScrollBar::handle:vertical:hover {{
        background-color: {bg_selected};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}
    QScrollBar:horizontal {{
        background-color: {scrollbar_bg};
        height: 12px;
        margin: 0px;
        border-radius: 6px;
    }}
    QScrollBar::handle:horizontal {{
        background-color: {scrollbar_handle};
        min-width: 24px;
        border-radius: 5px;
        margin: 2px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background-color: {bg_selected};
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0px;
    }}

    /* Status Bar & Progress Bar */
    QStatusBar {{
        background-color: {bg_card};
        border-top: 1px solid {border_col};
        color: {text_muted};
    }}
    QProgressBar {{
        border: 1px solid {border_col};
        border-radius: 5px;
        background-color: {bg_input};
        text-align: center;
        color: {text_main};
        font-size: 9pt;
        font-weight: bold;
    }}
    QProgressBar::chunk {{
        background-color: #3daee9;
        border-radius: 4px;
    }}

    /* List and Tree Views */
    QListView, QTreeView, QListWidget {{
        background-color: {bg_card};
        border: 1px solid {border_col};
        border-radius: 5px;
        padding: 4px;
        outline: none;
    }}
    QListView::item {{
        padding: 6px;
        border-radius: 4px;
    }}
    QListView::item:hover {{
        background-color: {bg_hover};
    }}
    QListView::item:selected {{
        background-color: {bg_selected};
        color: #ffffff;
    }}

    /* TabWidget */
    QTabWidget::pane {{
        border: 1px solid {border_col};
        border-radius: 6px;
        background-color: {bg_card};
        top: -1px;
    }}
    QTabBar::tab {{
        background-color: {bg_main};
        border: 1px solid {border_col};
        border-bottom-color: {border_col};
        border-top-left-radius: 5px;
        border-top-right-radius: 5px;
        padding: 6px 14px;
        margin-right: 2px;
    }}
    QTabBar::tab:selected {{
        background-color: {bg_card};
        border-bottom-color: {bg_card};
        font-weight: bold;
        color: {bg_selected};
    }}
    QTabBar::tab:hover:!selected {{
        background-color: {bg_hover};
    }}

    /* CheckBoxes & RadioButtons */
    QCheckBox, QRadioButton {{
        spacing: 6px;
    }}
    QCheckBox::indicator, QRadioButton::indicator {{
        width: 16px;
        height: 16px;
        border: 1px solid {border_col};
        border-radius: 3px;
        background-color: {bg_input};
    }}
    QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
        background-color: {bg_selected};
        border-color: {bg_selected};
    }}

    /* ToolTips */
    QToolTip {{
        background-color: {bg_card};
        color: {text_main};
        border: 1px solid {border_col};
        border-radius: 4px;
        padding: 4px 8px;
        font-size: 9pt;
    }}
    """


def get_kde_icon(name: str, fallback_standard=None) -> QIcon:
    """
    Retrieves a standard FreeDesktop/KDE theme icon by name,
    falling back to standard PyQt QStyle pixmap if not available.
    """
    icon = QIcon.fromTheme(name)
    if not icon.isNull():
        return icon
    
    # Try alternative theme names common on Linux/KDE
    aliases = {
        "scanner": ["scanner-symbolic", "yast-scanner", "hwinfo"],
        "document-scan": ["scanner", "document-import", "camera-photo"],
        "document-save": ["document-save-as", "filesave"],
        "edit-cut": ["transform-crop-and-resize", "crop"],
        "zoom-in": ["zoom-in-symbolic", "list-add"],
        "zoom-out": ["zoom-out-symbolic", "list-remove"],
        "zoom-fit-best": ["zoom-fit-width", "zoom-original"],
        "view-refresh": ["reload", "browser-reload"],
        "preferences-system": ["configure", "settings-configure"],
        "system-run": ["media-playback-start", "arrow-right"]
    }
    
    if name in aliases:
        for alt in aliases[name]:
            ic = QIcon.fromTheme(alt)
            if not ic.isNull():
                return ic

    if fallback_standard is not None:
        app = QApplication.instance()
        if app:
            return app.style().standardIcon(fallback_standard)

    return QIcon()


def apply_breeze_theme(app: QApplication, force_dark: bool = None):
    """
    Applies the KDE Plasma Breeze theme and styling to the given QApplication.
    """
    # 1. Prefer Breeze Qt style if installed
    available_styles = [s.lower() for s in app.style().metaObject().className()] # check available
    try:
        from PyQt6.QtWidgets import QStyleFactory
        styles = [s.lower() for s in QStyleFactory.keys()]
        if "breeze" in styles:
            app.setStyle("Breeze")
        elif "fusion" in styles:
            app.setStyle("Fusion")
    except Exception:
        pass

    # 2. Determine Dark vs Light
    if force_dark is None:
        dark = is_system_dark_mode()
    else:
        dark = force_dark

    # 3. Configure palette
    palette = QPalette()
    if dark:
        palette.setColor(QPalette.ColorRole.Window, QColor("#232629"))
        palette.setColor(QPalette.ColorRole.WindowText, QColor("#eff0f1"))
        palette.setColor(QPalette.ColorRole.Base, QColor("#1b1e20"))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#2c3034"))
        palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#31363b"))
        palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#eff0f1"))
        palette.setColor(QPalette.ColorRole.Text, QColor("#eff0f1"))
        palette.setColor(QPalette.ColorRole.Button, QColor("#31363b"))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor("#eff0f1"))
        palette.setColor(QPalette.ColorRole.BrightText, QColor("#ffffff"))
        palette.setColor(QPalette.ColorRole.Link, QColor("#3daee9"))
        palette.setColor(QPalette.ColorRole.Highlight, QColor("#3daee9"))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    else:
        palette.setColor(QPalette.ColorRole.Window, QColor("#f7f7f7"))
        palette.setColor(QPalette.ColorRole.WindowText, QColor("#232629"))
        palette.setColor(QPalette.ColorRole.Base, QColor("#ffffff"))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#edf0f2"))
        palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#ffffff"))
        palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#232629"))
        palette.setColor(QPalette.ColorRole.Text, QColor("#232629"))
        palette.setColor(QPalette.ColorRole.Button, QColor("#ffffff"))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor("#232629"))
        palette.setColor(QPalette.ColorRole.BrightText, QColor("#ffffff"))
        palette.setColor(QPalette.ColorRole.Link, QColor("#3daee9"))
        palette.setColor(QPalette.ColorRole.Highlight, QColor("#3daee9"))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))

    app.setPalette(palette)
    app.setStyleSheet(get_breeze_stylesheet(dark))
