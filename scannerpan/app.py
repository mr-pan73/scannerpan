"""
ScannerPan - Application Entry Point.
Configures Qt application environment for KDE Plasma / Linux Desktop,
applies Breeze theme and starts MainWindow.
"""

from __future__ import annotations

import os
import sys
import signal
import argparse
import logging

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QCoreApplication
from PyQt6.QtGui import QIcon

from scannerpan.ui.kde_theme import apply_breeze_theme, get_kde_icon
from scannerpan.ui.main_window import MainWindow

logger = logging.getLogger("scannerpan.app")


def setup_environment():
    """Configures high-DPI and platform attributes for Linux / KDE Plasma / Windows."""
    if sys.platform != "win32":
        # Ensure correct desktop file name for Wayland / X11 taskbars
        os.environ.setdefault("QT_QPA_PLATFORMTHEME", "kde")
        os.environ.setdefault("PULSE_PROP_application.name", "ScannerPan")


def parse_args():
    parser = argparse.ArgumentParser(
        description="ScannerPan - Modern Linux / KDE Scanning Application"
    )
    parser.add_argument("--dark", action="store_true", help="Force Breeze Dark theme")
    parser.add_argument("--light", action="store_true", help="Force Breeze Light theme")
    parser.add_argument("--debug", action="store_true", help="Enable verbose debug logging")
    return parser.parse_args()


def main():
    setup_environment()
    args = parse_args()

    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    # Enable Ctrl+C in terminal
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    app = QApplication(sys.argv)
    app.setApplicationName("ScannerPan")
    app.setApplicationDisplayName("ScannerPan")
    app.setOrganizationName("MrPan")
    app.setOrganizationDomain("mrpan.org")
    app.setDesktopFileName("scannerpan.desktop")

    # App Icon
    icon = get_kde_icon("scanner")
    if icon.isNull():
        base_dir = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        ico_path = os.path.join(base_dir, "resources", "scannerpan.ico")
        if os.path.isfile(ico_path):
            icon = QIcon(ico_path)
    if not icon.isNull():
        app.setWindowIcon(icon)

    # Apply Breeze Theme
    force_dark = True if args.dark else (False if args.light else None)
    apply_breeze_theme(app, force_dark=force_dark)

    # Create & show main window
    window = MainWindow()
    window.show()

    logger.info("ScannerPan GUI avviata con successo.")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
