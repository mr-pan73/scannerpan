"""
ScannerPan - Main Window.
Polished PyQt6 user interface following KDE Plasma and Breeze design principles.
Seamlessly integrates SaneEngine hardware acquisition, OpenCV detection, and OCR export.
"""

from __future__ import annotations

import os
import sys
import logging
import cv2
from pathlib import Path
from typing import List, Dict, Optional, Any
from PIL import Image

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QToolBar, QStatusBar, QProgressBar, QLabel, QComboBox,
    QPushButton, QGroupBox, QListWidget, QListWidgetItem,
    QMessageBox, QFileDialog, QFrame, QToolButton, QAbstractItemView
)
from PyQt6.QtGui import QAction, QIcon, QPixmap, QImage, QColor, QFont, QKeySequence
from PyQt6.QtCore import Qt, QSize, QThread, pyqtSignal, QObject

from scannerpan.ui.kde_theme import get_kde_icon, apply_breeze_theme, is_system_dark_mode
from scannerpan.ui.canvas import InteractiveCanvas, pil_to_qpixmap
from scannerpan.ui.dialogs import (
    DuplexScanWizardDialog,
    MultiSubjectChoiceDialog,
    ExportOCRDialog
)
from scannerpan.hardware.sane_engine import SaneEngine, ScanOptions, ScannerDevice, ScanResult
from scannerpan.processing.cv_detector import CVDetector, cv_to_pil, pil_to_cv
from scannerpan.processing.ocr_exporter import export_scanned_document

logger = logging.getLogger("scannerpan.ui.main_window")


# ==============================================================================
# WORKER THREAD FOR NON-BLOCKING SCANS AND EXPORTS
# ==============================================================================

class ScanWorker(QObject):
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, sane_engine: SaneEngine, options: ScanOptions):
        super().__init__()
        self.sane_engine = sane_engine
        self.options = options

    def run(self):
        try:
            self.progress.emit(10, "Avvio scansione hardware...")
            result = self.sane_engine.scan(
                self.options,
                progress_callback=lambda p, m: self.progress.emit(p, m)
            )
            self.finished.emit(result)
        except Exception as exc:
            logger.error("Scan worker error: %s", exc, exc_info=True)
            self.error.emit(str(exc))


class ExportWorker(QObject):
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(bool)
    error = pyqtSignal(str)

    def __init__(self, images: List[Image.Image], destination: str, format_type: str, ocr_lang: str):
        super().__init__()
        self.images = images
        self.destination = destination
        self.format_type = format_type
        self.ocr_lang = ocr_lang

    def run(self):
        try:
            ok = export_scanned_document(
                self.images,
                self.destination,
                format_type=self.format_type,
                ocr_lang=self.ocr_lang,
                progress_callback=lambda p, m: self.progress.emit(p, m)
            )
            self.finished.emit(ok)
        except Exception as exc:
            logger.error("Export worker error: %s", exc, exc_info=True)
            self.error.emit(str(exc))


# ==============================================================================
# MAIN WINDOW CLASS
# ==============================================================================

class MainWindow(QMainWindow):
    """
    KDE Plasma-compliant main application window for ScannerPan.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ScannerPan - Scanner e Acquisizione Documenti")
        self.resize(1180, 780)
        self.setMinimumSize(850, 600)

        # Set App Window Icon
        app_icon = get_kde_icon("scanner")
        if not app_icon.isNull():
            self.setWindowIcon(app_icon)

        # Core Engines
        self.sane_engine = SaneEngine(allow_mock_fallback=True)
        self.cv_detector = CVDetector()

        # State
        self.devices: List[ScannerDevice] = []
        self.current_pages: List[Image.Image] = []
        self.current_page_index: int = -1
        self.detected_subjects_cache: List[Dict[str, Any]] = []

        # Undo / Redo history per page
        self.undo_stacks: Dict[int, List[Image.Image]] = {}
        self.redo_stacks: Dict[int, List[Image.Image]] = {}
        self.is_preview_scan_running: bool = False
        self._has_preview_page: bool = False

        # Background worker management
        self.worker_thread: Optional[QThread] = None
        self.worker: Optional[QObject] = None

        self._build_ui()
        self._refresh_scanners()

    def _build_ui(self):
        # 1. Top Toolbar
        self._create_toolbar()

        # 2. Main Central Layout: Sidebar + Canvas + Thumbnails
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)

        self.splitter = QSplitter(Qt.Orientation.Horizontal, self)

        # Left: Settings Sidebar
        self.sidebar = self._create_settings_sidebar()
        self.splitter.addWidget(self.sidebar)

        # Center: Interactive Canvas
        self.canvas = InteractiveCanvas(self)
        self.canvas.selection_changed.connect(self._on_subject_selection_changed)
        self.splitter.addWidget(self.canvas)

        # Right: Page Thumbnails Panel
        self.thumbnail_panel = self._create_thumbnail_panel()
        self.splitter.addWidget(self.thumbnail_panel)

        # Set splitter proportions (e.g. 240px sidebar, remainder canvas, 160px thumbs)
        self.splitter.setSizes([260, 740, 180])
        main_layout.addWidget(self.splitter)

        # 3. Status Bar
        self.status_bar = QStatusBar(self)
        self.setStatusBar(self.status_bar)

        self.status_lbl = QLabel("Pronto.", self)
        self.status_bar.addWidget(self.status_lbl, 1)

        self.progress_bar = QProgressBar(self)
        self.progress_bar.setMaximumWidth(220)
        self.progress_bar.setFixedHeight(16)
        self.progress_bar.setVisible(False)
        self.status_bar.addPermanentWidget(self.progress_bar)

    # --------------------------------------------------------------------------
    # TOOLBAR CREATION
    # --------------------------------------------------------------------------
    def _create_toolbar(self):
        toolbar = QToolBar("Barra Strumenti Principale", self)
        toolbar.setIconSize(QSize(22, 22))
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar)

        # 1. Detect Scanner
        act_detect = QAction(get_kde_icon("view-refresh"), "Rileva Scanner", self)
        act_detect.setToolTip("Rileva gli scanner di rete e USB collegati")
        act_detect.triggered.connect(self._refresh_scanners)
        toolbar.addAction(act_detect)

        toolbar.addSeparator()

        # 2. Preview Scan (Scansione Anteprima)
        self.act_preview = QAction(get_kde_icon("view-preview"), "Anteprima", self)
        self.act_preview.setToolTip("Scansione rapida di anteprima a 100 DPI dal piano fisso")
        self.act_preview.triggered.connect(self._start_preview_scan)
        toolbar.addAction(self.act_preview)

        # 3. Scan Flatbed
        self.act_scan_flatbed = QAction(get_kde_icon("document-scan"), "Piano Fisso", self)
        self.act_scan_flatbed.setToolTip("Scansiona una pagina dal piano fisso dello scanner")
        self.act_scan_flatbed.triggered.connect(lambda: self._start_scan(source="Flatbed"))
        toolbar.addAction(self.act_scan_flatbed)

        # 4. Scan ADF
        self.act_scan_adf = QAction(get_kde_icon("edit-copy"), "ADF Fascicolo", self)
        self.act_scan_adf.setToolTip("Scansiona fascicolo continuo dall'alimentatore automatico (ADF)")
        self.act_scan_adf.triggered.connect(lambda: self._start_scan(source="ADF", batch=True))
        toolbar.addAction(self.act_scan_adf)

        # 5. Scan Duplex Wizard
        self.act_scan_duplex = QAction(get_kde_icon("media-playlist-repeat"), "Fronte / Retro", self)
        self.act_scan_duplex.setToolTip("Avvia la procedura guidata per scansionare fronte e retro")
        self.act_scan_duplex.triggered.connect(self._open_duplex_wizard)
        toolbar.addAction(self.act_scan_duplex)

        toolbar.addSeparator()

        # 6. Detect Multi-Subjects (Photo / Receipts)
        self.act_detect_subjects = QAction(get_kde_icon("edit-cut"), "Riconosci Soggetti", self)
        self.act_detect_subjects.setToolTip("Rileva automaticamente foto o scontrini multipli sul piano fisso")
        self.act_detect_subjects.triggered.connect(self._run_multi_subject_detection)
        toolbar.addAction(self.act_detect_subjects)

        toolbar.addSeparator()

        # 7. Undo / Redo for Image Enhancements
        self.act_undo = QAction(get_kde_icon("edit-undo"), "Annulla", self)
        self.act_undo.setShortcut(QKeySequence.StandardKey.Undo)
        self.act_undo.setToolTip("Annulla l'ultimo miglioramento applicato all'immagine (Ctrl+Z)")
        self.act_undo.triggered.connect(self._undo_current_page)
        self.act_undo.setEnabled(False)
        toolbar.addAction(self.act_undo)

        self.act_redo = QAction(get_kde_icon("edit-redo"), "Ripristina", self)
        self.act_redo.setShortcut(QKeySequence.StandardKey.Redo)
        self.act_redo.setToolTip("Ripristina il miglioramento annullato (Ctrl+Shift+Z / Ctrl+Y)")
        self.act_redo.triggered.connect(self._redo_current_page)
        self.act_redo.setEnabled(False)
        toolbar.addAction(self.act_redo)

        toolbar.addSeparator()

        # 8. Export / OCR
        self.act_export = QAction(get_kde_icon("document-save"), "Esporta / OCR...", self)
        self.act_export.setToolTip("Esporta in PDF ricercabile, DOCX, ODT, RTF, TXT o Immagini")
        self.act_export.triggered.connect(self._open_export_dialog)
        toolbar.addAction(self.act_export)

    # --------------------------------------------------------------------------
    # SIDEBAR SETTINGS
    # --------------------------------------------------------------------------
    def _create_settings_sidebar(self) -> QWidget:
        sidebar = QFrame(self)
        sidebar.setStyleSheet("""
            QFrame {
                background-color: #2b3035;
                border-radius: 6px;
            }
        """)
        s_layout = QVBoxLayout(sidebar)
        s_layout.setContentsMargins(12, 12, 12, 12)
        s_layout.setSpacing(14)

        # Device Selection
        dev_group = QGroupBox("Dispositivo Scanner", sidebar)
        dg_layout = QVBoxLayout(dev_group)
        self.combo_devices = QComboBox(dev_group)
        self.combo_devices.currentIndexChanged.connect(self._on_device_selection_changed)
        dg_layout.addWidget(self.combo_devices)

        self.lbl_device_status = QLabel("Nessun dispositivo rilevato", dev_group)
        self.lbl_device_status.setStyleSheet("color: #a0a6ac; font-size: 8.5pt;")
        self.lbl_device_status.setWordWrap(True)
        dg_layout.addWidget(self.lbl_device_status)
        s_layout.addWidget(dev_group)

        # Scan Properties
        prop_group = QGroupBox("Opzioni di Acquisizione", sidebar)
        pg_layout = QVBoxLayout(prop_group)

        # Resolution
        pg_layout.addWidget(QLabel("Risoluzione (DPI):", prop_group))
        self.combo_dpi = QComboBox(prop_group)
        self.combo_dpi.addItems(["100 DPI (Bozza)", "200 DPI (Veloce)", "300 DPI (Standard)", "600 DPI (Alta Qualità)"])
        self.combo_dpi.setCurrentIndex(2)  # 300 DPI
        pg_layout.addWidget(self.combo_dpi)

        # Color Mode
        pg_layout.addWidget(QLabel("Modalità Colore:", prop_group))
        self.combo_mode = QComboBox(prop_group)
        self.combo_mode.addItem("A Colori (24-bit)", "Color")
        self.combo_mode.addItem("Scala di Grigi (8-bit)", "Gray")
        self.combo_mode.addItem("Bianco e Nero / Testo (Lineart)", "Lineart")
        pg_layout.addWidget(self.combo_mode)

        # Source
        pg_layout.addWidget(QLabel("Sorgente:", prop_group))
        self.combo_source = QComboBox(prop_group)
        self.combo_source.addItem("Piano Fisso (Flatbed)", "Flatbed")
        self.combo_source.addItem("Alimentatore Automatico (ADF)", "ADF")
        pg_layout.addWidget(self.combo_source)
        s_layout.addWidget(prop_group)

        # Post-Processing options
        proc_group = QGroupBox("Miglioramenti Immagine", sidebar)
        prg_layout = QVBoxLayout(proc_group)

        self.btn_deskew = QPushButton("Raddrizza Inclinazione", proc_group)
        self.btn_deskew.setIcon(get_kde_icon("transform-rotate"))
        self.btn_deskew.setToolTip("Rileva l'orientamento del testo e raddrizza il documento")
        self.btn_deskew.clicked.connect(self._apply_deskew_current_page)
        prg_layout.addWidget(self.btn_deskew)

        self.btn_autocrop = QPushButton("Ritaglio Automatico Margini", proc_group)
        self.btn_autocrop.setIcon(get_kde_icon("edit-cut"))
        self.btn_autocrop.setToolTip("Rileva i bordi del foglio ed elimina i margini neri/vuoti")
        self.btn_autocrop.clicked.connect(self._apply_autocrop_current_page)
        prg_layout.addWidget(self.btn_autocrop)

        self.btn_enhance = QPushButton("Migliora Contrasto & Sfondo", proc_group)
        self.btn_enhance.setIcon(get_kde_icon("view-filter"))
        self.btn_enhance.setToolTip("Sbianca lo sfondo ed esalta i caratteri del testo")
        self.btn_enhance.clicked.connect(self._apply_enhance_current_page)
        prg_layout.addWidget(self.btn_enhance)

        # Undo / Redo Buttons for image improvements
        undo_redo_layout = QHBoxLayout()
        undo_redo_layout.setSpacing(6)

        self.btn_undo = QPushButton("Annulla", proc_group)
        self.btn_undo.setIcon(get_kde_icon("edit-undo"))
        self.btn_undo.setToolTip("Annulla l'ultimo miglioramento/modifica applicato (Ctrl+Z)")
        self.btn_undo.clicked.connect(self._undo_current_page)
        self.btn_undo.setEnabled(False)
        undo_redo_layout.addWidget(self.btn_undo)

        self.btn_redo = QPushButton("Ripristina", proc_group)
        self.btn_redo.setIcon(get_kde_icon("edit-redo"))
        self.btn_redo.setToolTip("Ripristina il miglioramento annullato (Ctrl+Y)")
        self.btn_redo.clicked.connect(self._redo_current_page)
        self.btn_redo.setEnabled(False)
        undo_redo_layout.addWidget(self.btn_redo)

        prg_layout.addLayout(undo_redo_layout)
        s_layout.addWidget(proc_group)

        s_layout.addStretch()

        # Fast Preview Scan Button
        self.btn_preview = QPushButton("Scansione Anteprima", sidebar)
        self.btn_preview.setIcon(get_kde_icon("view-preview"))
        self.btn_preview.setFixedHeight(34)
        self.btn_preview.setToolTip("Acquisisce rapidamente un'anteprima a 100 DPI dal piano fisso")
        self.btn_preview.clicked.connect(self._start_preview_scan)
        s_layout.addWidget(self.btn_preview)

        # Big Primary Scan Button
        self.btn_primary_scan = QPushButton("Scansiona Ora", sidebar)
        self.btn_primary_scan.setProperty("primary", True)
        self.btn_primary_scan.setIcon(get_kde_icon("document-scan"))
        self.btn_primary_scan.setFixedHeight(38)
        self.btn_primary_scan.setStyleSheet("font-size: 11pt;")
        self.btn_primary_scan.clicked.connect(self._start_scan_from_sidebar)
        s_layout.addWidget(self.btn_primary_scan)

        return sidebar

    # --------------------------------------------------------------------------
    # THUMBNAIL PANEL
    # --------------------------------------------------------------------------
    def _create_thumbnail_panel(self) -> QWidget:
        panel = QFrame(self)
        panel.setStyleSheet("""
            QFrame {
                background-color: #2b3035;
                border-radius: 6px;
            }
        """)
        p_layout = QVBoxLayout(panel)
        p_layout.setContentsMargins(8, 8, 8, 8)
        p_layout.setSpacing(6)

        header = QLabel("Pagine Scansionate", panel)
        header.setStyleSheet("font-weight: bold; color: #3daee9;")
        p_layout.addWidget(header)

        self.thumb_list = QListWidget(panel)
        self.thumb_list.setIconSize(QSize(100, 130))
        self.thumb_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.thumb_list.currentRowChanged.connect(self._on_thumbnail_selection_changed)
        p_layout.addWidget(self.thumb_list, stretch=1)

        # Quick action buttons for selected thumbnail
        t_actions = QHBoxLayout()
        t_actions.setSpacing(4)

        self.btn_rot_left = QToolButton(panel)
        self.btn_rot_left.setIcon(get_kde_icon("object-rotate-left"))
        self.btn_rot_left.setToolTip("Ruota 90° a sinistra")
        self.btn_rot_left.clicked.connect(lambda: self._rotate_current_page(-90))
        t_actions.addWidget(self.btn_rot_left)

        self.btn_rot_right = QToolButton(panel)
        self.btn_rot_right.setIcon(get_kde_icon("object-rotate-right"))
        self.btn_rot_right.setToolTip("Ruota 90° a destra")
        self.btn_rot_right.clicked.connect(lambda: self._rotate_current_page(90))
        t_actions.addWidget(self.btn_rot_right)

        self.btn_del_page = QToolButton(panel)
        self.btn_del_page.setIcon(get_kde_icon("edit-delete"))
        self.btn_del_page.setToolTip("Elimina la pagina corrente")
        self.btn_del_page.clicked.connect(self._delete_current_page)
        t_actions.addWidget(self.btn_del_page)

        p_layout.addLayout(t_actions)
        return panel

    # --------------------------------------------------------------------------
    # HARDWARE DETECTION & SIDEBAR UPDATES
    # --------------------------------------------------------------------------
    def _refresh_scanners(self):
        self.status_lbl.setText("Rilevamento scanner SANE e di rete in corso...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # indeterminate

        try:
            self.devices = self.sane_engine.list_devices()
            self.combo_devices.clear()
            for dev in self.devices:
                label = f"{dev.vendor} {dev.model}"
                if dev.is_brother:
                    label += " (Brother MFC)"
                if dev.is_mock:
                    label += " [Test Virtuale]"
                self.combo_devices.addItem(label, dev.name)

            if self.devices:
                self.status_lbl.setText(f"Rilevati {len(self.devices)} dispositivi scanner.")
            else:
                self.status_lbl.setText("Nessun scanner rilevato.")
        except Exception as exc:
            logger.error("Errore rilevamento: %s", exc)
            self.status_lbl.setText(f"Errore rilevamento: {exc}")
        finally:
            self.progress_bar.setVisible(False)

    def _on_device_selection_changed(self, index: int):
        if 0 <= index < len(self.devices):
            dev = self.devices[index]
            self.lbl_device_status.setText(f"URI: {dev.name}\nProtocollo: {'AirScan/WSD' if dev.is_airscan else 'SANE'}")
        else:
            self.lbl_device_status.setText("")

    # --------------------------------------------------------------------------
    # SCANNING OPERATIONS
    # --------------------------------------------------------------------------
    def _get_selected_options(self, override_source: Optional[str] = None, batch: bool = False) -> ScanOptions:
        dev_name = self.combo_devices.currentData()
        source = override_source or self.combo_source.currentData() or "Flatbed"
        mode = self.combo_mode.currentData() or "Color"

        dpi_text = self.combo_dpi.currentText()
        dpi = int(dpi_text.split()[0])

        return ScanOptions(
            device=dev_name,
            source=source,
            mode=mode,
            resolution=dpi,
            adf_batch=batch,
            format="png"
        )

    def _is_busy(self) -> bool:
        """Controlla in modo sicuro se c'è un'operazione di scansione o esportazione attiva."""
        if self.worker_thread is None:
            return False
        try:
            return bool(self.worker_thread.isRunning())
        except (RuntimeError, AttributeError):
            self.worker_thread = None
            return False

    def _cleanup_worker(self):
        """Ripulisce in modo sicuro il thread di background e il worker."""
        if self.worker_thread is not None:
            try:
                if self.worker_thread.isRunning():
                    self.worker_thread.quit()
                    self.worker_thread.wait(600)
            except (RuntimeError, AttributeError):
                pass
            self.worker_thread = None
        self.worker = None

    def _start_scan_from_sidebar(self):
        self._start_scan()

    def _start_scan(self, source: Optional[str] = None, batch: bool = False):
        if not self.combo_devices.count():
            QMessageBox.warning(self, "Attenzione", "Nessuno scanner selezionato o rilevato.")
            return

        if self._is_busy():
            self.status_lbl.setText("Un'acquisizione è già in corso. Attendi il completamento...")
            return

        options = self._get_selected_options(override_source=source, batch=batch)
        self._set_ui_busy(True, f"Scansione in corso ({options.source} @ {options.resolution} DPI)...")

        self.worker_thread = QThread()
        self.worker = ScanWorker(self.sane_engine, options)
        self.worker.moveToThread(self.worker_thread)

        self.worker_thread.started.connect(self.worker.run)
        self.worker.progress.connect(self._on_scan_progress)
        self.worker.finished.connect(self._on_scan_finished)
        self.worker.error.connect(self._on_scan_error)

        self.worker.finished.connect(self.worker_thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.error.connect(self.worker_thread.quit)
        self.worker_thread.finished.connect(self._cleanup_worker)

        self.worker_thread.start()

    def _on_scan_progress(self, percent: int, message: str):
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(percent)
        self.status_lbl.setText(message)

    def _on_scan_finished(self, result: ScanResult):
        self._set_ui_busy(False)
        self._cleanup_worker()

        if not result.success:
            QMessageBox.critical(self, "Errore Scansione", f"Scansione fallita: {result.error_message}")
            self.status_lbl.setText("Scansione fallita.")
            return

        pil_imgs = result.load_pil_images()
        if not pil_imgs:
            QMessageBox.warning(self, "Nessuna Immagine", "Nessun file immagine restituito dallo scanner.")
            return

        # Se avevamo una pagina di sola anteprima a 100 DPI, rimuovila prima di aggiungere la scansione reale
        if self._has_preview_page and len(self.current_pages) == 1:
            self.current_pages.clear()
            self.thumb_list.clear()
            self.undo_stacks.clear()
            self.redo_stacks.clear()
            self.current_page_index = -1
            self.canvas.set_crop_rect(None)
            self._has_preview_page = False

        for img in pil_imgs:
            self._add_scanned_page(img)

        self.status_lbl.setText(f"Acquisite {len(pil_imgs)} pagine con successo ({result.duration_sec:.1f}s).")

    def _on_scan_error(self, err_msg: str):
        self._set_ui_busy(False)
        self._cleanup_worker()
        QMessageBox.critical(self, "Errore", f"Si è verificato un errore: {err_msg}")
        self.status_lbl.setText("Errore durante l'acquisizione.")

    # --------------------------------------------------------------------------
    # PAGE MANAGEMENT & THUMBNAILS
    # --------------------------------------------------------------------------
    def _add_scanned_page(self, img: Image.Image):
        self.current_pages.append(img)
        idx = len(self.current_pages) - 1

        # Create thumbnail item
        thumb_pix = pil_to_qpixmap(img).scaled(
            90, 120, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
        )
        item = QListWidgetItem(QIcon(thumb_pix), f"Pagina {idx+1}")
        self.thumb_list.addItem(item)
        self.thumb_list.setCurrentRow(idx)

    def _on_thumbnail_selection_changed(self, row: int):
        if 0 <= row < len(self.current_pages):
            self.current_page_index = row
            img = self.current_pages[row]
            self.canvas.set_image(img)
        else:
            self.current_page_index = -1
            self.canvas.set_image(None)
        self._update_undo_redo_ui()

    # --------------------------------------------------------------------------
    # UNDO / REDO HISTORY MANAGEMENT
    # --------------------------------------------------------------------------
    def _push_undo_state(self, page_index: int):
        """Salva lo stato corrente dell'immagine nello stack di Undo della pagina."""
        if page_index < 0 or page_index >= len(self.current_pages):
            return
        if page_index not in self.undo_stacks:
            self.undo_stacks[page_index] = []
        # Salva una copia profonda dell'immagine prima della modifica
        self.undo_stacks[page_index].append(self.current_pages[page_index].copy())
        if len(self.undo_stacks[page_index]) > 25:
            self.undo_stacks[page_index].pop(0)

        # Ogni nuova modifica cancella la cronologia di Redo
        self.redo_stacks[page_index] = []
        self._update_undo_redo_ui()

    def _undo_current_page(self):
        """Annulla l'ultima modifica o miglioramento apportato alla pagina attiva (Ctrl+Z)."""
        idx = self.current_page_index
        if idx < 0 or idx not in self.undo_stacks or not self.undo_stacks[idx]:
            self.status_lbl.setText("Nessuna azione da annullare.")
            return

        prev_img = self.undo_stacks[idx].pop()
        if idx not in self.redo_stacks:
            self.redo_stacks[idx] = []
        self.redo_stacks[idx].append(self.current_pages[idx].copy())

        self.current_pages[idx] = prev_img
        self.canvas.set_image(prev_img)

        # Aggiorna miniatura
        thumb_pix = pil_to_qpixmap(prev_img).scaled(
            90, 120, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
        )
        if 0 <= idx < self.thumb_list.count():
            self.thumb_list.item(idx).setIcon(QIcon(thumb_pix))

        self.status_lbl.setText("Miglioramento annullato con successo (Undo).")
        self._update_undo_redo_ui()

    def _redo_current_page(self):
        """Ripristina l'ultimo miglioramento precedentemente annullato (Ctrl+Y / Ctrl+Shift+Z)."""
        idx = self.current_page_index
        if idx < 0 or idx not in self.redo_stacks or not self.redo_stacks[idx]:
            self.status_lbl.setText("Nessuna azione da ripristinare.")
            return

        next_img = self.redo_stacks[idx].pop()
        if idx not in self.undo_stacks:
            self.undo_stacks[idx] = []
        self.undo_stacks[idx].append(self.current_pages[idx].copy())

        self.current_pages[idx] = next_img
        self.canvas.set_image(next_img)

        # Aggiorna miniatura
        thumb_pix = pil_to_qpixmap(next_img).scaled(
            90, 120, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
        )
        if 0 <= idx < self.thumb_list.count():
            self.thumb_list.item(idx).setIcon(QIcon(thumb_pix))

        self.status_lbl.setText("Miglioramento ripristinato (Redo).")
        self._update_undo_redo_ui()

    def _update_undo_redo_ui(self):
        """Aggiorna lo stato di abilitazione dei pulsanti e azioni Undo/Redo."""
        idx = self.current_page_index
        can_undo = bool(idx >= 0 and self.undo_stacks.get(idx))
        can_redo = bool(idx >= 0 and self.redo_stacks.get(idx))

        if hasattr(self, "act_undo"):
            self.act_undo.setEnabled(can_undo)
        if hasattr(self, "act_redo"):
            self.act_redo.setEnabled(can_redo)
        if hasattr(self, "btn_undo"):
            self.btn_undo.setEnabled(can_undo)
        if hasattr(self, "btn_redo"):
            self.btn_redo.setEnabled(can_redo)

    def _rotate_current_page(self, angle: int):
        if 0 <= self.current_page_index < len(self.current_pages):
            self._push_undo_state(self.current_page_index)
            cur = self.current_pages[self.current_page_index]
            rotated = cur.rotate(-angle, expand=True)
            self.current_pages[self.current_page_index] = rotated

            thumb_pix = pil_to_qpixmap(rotated).scaled(
                90, 120, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
            item = self.thumb_list.item(self.current_page_index)
            item.setIcon(QIcon(thumb_pix))

            self.canvas.set_image(rotated)
            self.status_lbl.setText(f"Pagina ruotata di {angle}°.")

    def _delete_current_page(self):
        if 0 <= self.current_page_index < len(self.current_pages):
            row = self.current_page_index
            del self.current_pages[row]
            # Ripulisci cronologia undo per la pagina eliminata
            self.undo_stacks.pop(row, None)
            self.redo_stacks.pop(row, None)
            self.thumb_list.takeItem(row)

            for i in range(self.thumb_list.count()):
                self.thumb_list.item(i).setText(f"Pagina {i+1}")
            if self.current_pages:
                new_row = min(row, len(self.current_pages) - 1)
                self.thumb_list.setCurrentRow(new_row)
            else:
                self.current_page_index = -1
                self.canvas.set_image(None)
            self.status_lbl.setText("Pagina eliminata.")
            self._update_undo_redo_ui()

    # --------------------------------------------------------------------------
    # FAST PREVIEW SCAN (SCANSIONE ANTEPRIMA)
    # --------------------------------------------------------------------------
    def _start_preview_scan(self):
        """Esegue una scansione rapida di anteprima (100 DPI) dal piano fisso."""
        if not self.combo_devices.count():
            QMessageBox.warning(self, "Attenzione", "Nessuno scanner selezionato o rilevato.")
            return

        if self._is_busy():
            self.status_lbl.setText("Un'acquisizione è già in corso. Attendi il completamento...")
            return

        opts = self._get_selected_options(override_source="Flatbed")
        opts.resolution = 100
        opts.source = "Flatbed"
        opts.adf_batch = False

        self._set_ui_busy(True, "Scansione rapida anteprima in corso (100 DPI)...")

        self.worker_thread = QThread()
        self.worker = ScanWorker(self.sane_engine, opts)
        self.worker.moveToThread(self.worker_thread)

        self.worker_thread.started.connect(self.worker.run)
        self.worker.progress.connect(self._on_scan_progress)
        self.worker.finished.connect(self._on_preview_scan_finished)
        self.worker.error.connect(self._on_scan_error)

        self.worker.finished.connect(self.worker_thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.error.connect(self.worker_thread.quit)
        self.worker_thread.finished.connect(self._cleanup_worker)

        self.worker_thread.start()

    def _on_preview_scan_finished(self, scan_result: ScanResult):
        self._set_ui_busy(False)
        self._cleanup_worker()

        if not scan_result.success or not scan_result.images:
            QMessageBox.critical(
                self, "Errore Anteprima",
                f"Impossibile acquisire l'anteprima: {scan_result.error_message or 'Nessun dato immagine.'}"
            )
            return

        pil_imgs = scan_result.load_pil_images()
        if not pil_imgs:
            return

        preview_img = pil_imgs[0]
        # Se c'era già un'anteprima come unica pagina, sostituiscila con la nuova
        if self._has_preview_page and len(self.current_pages) == 1:
            self.current_pages[0] = preview_img
            thumb_pix = pil_to_qpixmap(preview_img).scaled(
                90, 120, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
            item = self.thumb_list.item(0)
            if item:
                item.setIcon(QIcon(thumb_pix))
                item.setText("Anteprima (100 DPI)")
            self.canvas.set_image(preview_img)
        else:
            self._add_scanned_page(preview_img)
            self._has_preview_page = True
            item = self.thumb_list.item(self.current_page_index)
            if item:
                item.setText("Anteprima (100 DPI)")

        # Rileva automaticamente i contorni del foglio e imposta il crop sull'anteprima
        try:
            cv_img = pil_to_cv(preview_img)
            boundary = self.cv_detector.detect_document_boundary(cv_img)
            if boundary is not None:
                bx, by, bw, bh = cv2.boundingRect(boundary)
                self.canvas.set_crop_rect(float(bx), float(by), float(bw), float(bh))
                self.status_lbl.setText("Anteprima acquisita (100 DPI). Bordi foglio rilevati: clicca 'Scansiona Ora' per la scansione finale.")
            else:
                self.canvas.set_crop_rect(None)
                self.status_lbl.setText("Anteprima acquisita (100 DPI). Posizione verificata: clicca 'Scansiona Ora' per la scansione finale.")
        except Exception as exc:
            logger.error("Errore elaborazione anteprima: %s", exc)
            self.canvas.set_crop_rect(None)
            self.status_lbl.setText("Anteprima acquisita (100 DPI). Clicca 'Scansiona Ora' per l'acquisizione definitiva.")

    # --------------------------------------------------------------------------
    # CV & IMAGE ENHANCEMENTS WITH UNDO SUPPORT
    # --------------------------------------------------------------------------
    def _apply_deskew_current_page(self):
        if self.current_page_index < 0 or not self.current_pages:
            self.status_lbl.setText("Nessuna scansione selezionata da raddrizzare.")
            return

        img = self.current_pages[self.current_page_index]
        self.status_lbl.setText("Analisi inclinazione e correzione ottica in corso...")
        cv_img = pil_to_cv(img)

        try:
            # Esegue il deskew basato sull'orientamento del testo o dei bordi
            deskew_res = self.cv_detector.deskew_document(cv_img)
            if isinstance(deskew_res, tuple) and len(deskew_res) >= 2:
                deskewed_cv, angle = deskew_res[0], float(deskew_res[1])
            elif isinstance(deskew_res, tuple):
                deskewed_cv, angle = deskew_res[0], 0.0
            else:
                deskewed_cv, angle = deskew_res, 0.0

            if abs(angle) < 0.15:
                self.status_lbl.setText("Il documento risulta già dritto (inclinazione < 0.2°).")
                return

            # Salva stato per Undo prima di aggiornare
            self._push_undo_state(self.current_page_index)

            new_img = cv_to_pil(deskewed_cv)
            self.current_pages[self.current_page_index] = new_img
            self.canvas.set_image(new_img)

            # Aggiorna miniatura
            thumb_pix = pil_to_qpixmap(new_img).scaled(
                90, 120, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
            self.thumb_list.item(self.current_page_index).setIcon(QIcon(thumb_pix))
            self.status_lbl.setText(f"Inclinazione raddrizzata con successo (corretti {angle:+.1f}°).")
        except Exception as exc:
            logger.error("Errore raddrizzamento inclinazione: %s", exc, exc_info=True)
            self.status_lbl.setText(f"Errore durante il raddrizzamento: {exc}")

    def _apply_autocrop_current_page(self):
        if self.current_page_index < 0 or not self.current_pages:
            return

        self._push_undo_state(self.current_page_index)
        img = self.current_pages[self.current_page_index]
        self.status_lbl.setText("Ritaglio automatico dei margini...")
        cv_img = pil_to_cv(img)
        cropped = self.cv_detector.auto_crop_margins(cv_img)
        new_img = cv_to_pil(cropped)

        self.current_pages[self.current_page_index] = new_img
        self.canvas.set_image(new_img)

        thumb_pix = pil_to_qpixmap(new_img).scaled(
            90, 120, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
        )
        self.thumb_list.item(self.current_page_index).setIcon(QIcon(thumb_pix))
        self.status_lbl.setText("Ritaglio margini completato.")

    def _apply_enhance_current_page(self):
        if self.current_page_index < 0 or not self.current_pages:
            return

        self._push_undo_state(self.current_page_index)
        img = self.current_pages[self.current_page_index]
        self.status_lbl.setText("Miglioramento contrasto e rimozione sfondo...")
        cv_img = pil_to_cv(img)
        enhanced = self.cv_detector.clean_background(cv_img)
        new_img = cv_to_pil(enhanced)

        self.current_pages[self.current_page_index] = new_img
        self.canvas.set_image(new_img)

        thumb_pix = pil_to_qpixmap(new_img).scaled(
            90, 120, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
        )
        self.thumb_list.item(self.current_page_index).setIcon(QIcon(thumb_pix))
        self.status_lbl.setText("Miglioramento contrasto e sfondo applicato.")

    # --------------------------------------------------------------------------
    # MULTI-SUBJECT DETECTION & WIZARDS
    # --------------------------------------------------------------------------
    def _run_multi_subject_detection(self):
        if self.current_page_index < 0 or not self.current_pages:
            QMessageBox.information(
                self, "Nessuna scansione", "Effettua prima una scansione del piano fisso."
            )
            return

        cur_img = self.current_pages[self.current_page_index]
        self.status_lbl.setText("Rilevamento ottico soggetti multipli in corso...")
        cv_img = pil_to_cv(cur_img)
        subjects = self.cv_detector.detect_multiple_subjects(cv_img)

        if not subjects:
            QMessageBox.information(
                self, "Rilevamento", "Nessun elemento separato distinto rilevato sul piano fisso."
            )
            self.status_lbl.setText("Nessun soggetto rilevato.")
            return

        # Prepare for canvas overlay
        canvas_subjects = []
        dialog_subjects = []
        for s in subjects:
            x, y, w, h = s.bbox
            canvas_subjects.append({
                "id": s.subject_id,
                "rect": (x, y, w, h),
                "label": f"Soggetto {s.subject_id}",
                "selected": True,
            })
            dialog_subjects.append({
                "id": s.subject_id,
                "name": f"Foto_Ritagliata_{s.subject_id:02d}",
                "image": s.pil_image,
                "width": s.cropped_image.shape[1],
                "height": s.cropped_image.shape[0],
                "selected": True,
            })

        self.canvas.set_detected_subjects(canvas_subjects)
        self.status_lbl.setText(f"Rilevati {len(subjects)} soggetti.")

        # Open Choice Dialog
        dlg = MultiSubjectChoiceDialog(dialog_subjects, self)
        if dlg.exec() == MultiSubjectChoiceDialog.DialogCode.Accepted:
            selected_items = dlg.selected_results
            saved_count = 0
            for item in selected_items:
                target_dir = Path(item["output_dir"])
                target_dir.mkdir(parents=True, exist_ok=True)
                fmt = item["format"]
                filename = f"{item['filename']}.{fmt}"
                save_path = target_dir / filename
                item_img: Image.Image = item["image"]
                rot = item.get("rotation", 0)
                if rot != 0:
                    item_img = item_img.rotate(-rot, expand=True)

                if fmt in ("jpg", "jpeg"):
                    item_img.convert("RGB").save(save_path, "JPEG", quality=95)
                elif fmt == "png":
                    item_img.save(save_path, "PNG")
                elif fmt == "webp":
                    item_img.save(save_path, "WEBP", quality=95)
                elif fmt == "pdf":
                    item_img.convert("RGB").save(save_path, "PDF")
                else:
                    item_img.save(save_path)
                saved_count += 1

            QMessageBox.information(
                self, "Salvataggio", f"Salvati {saved_count} soggetti con successo in {dlg.folder_edit.text()}."
            )

    def _on_subject_selection_changed(self, selected_list: list):
        self.status_lbl.setText(f"{len(selected_list)} soggetti selezionati.")

    def _open_duplex_wizard(self):
        """Opens Duplex Scan Wizard with live scanning callbacks."""
        def duplex_scan_callback(side: str) -> Optional[Image.Image]:
            opts = self._get_selected_options(override_source="Flatbed")
            res = self.sane_engine.scan(opts)
            if res.success:
                pil_imgs = res.load_pil_images()
                return pil_imgs[0] if pil_imgs else None
            else:
                QMessageBox.critical(self, "Errore", f"Scansione fallita: {res.error_message}")
                return None

        wizard = DuplexScanWizardDialog(self, scan_callback=duplex_scan_callback)
        if wizard.exec() == DuplexScanWizardDialog.DialogCode.Accepted:
            merge_mode = wizard.get_merge_mode()
            if wizard.front_image and wizard.back_image and merge_mode != "separate":
                try:
                    from scannerpan.processing.merger import DuplexMerger, LayoutMode
                    mode_map = {
                        "side_by_side": LayoutMode.SIDE_BY_SIDE,
                        "vertical": LayoutMode.VERTICAL,
                        "id_card": LayoutMode.ID_CARD,
                        "id_card_a4": LayoutMode.ID_CARD_A4,
                    }
                    lm = mode_map.get(merge_mode, LayoutMode.SIDE_BY_SIDE)
                    comp_img = DuplexMerger.create_composite_image(
                        wizard.front_image, wizard.back_image, layout=lm
                    )
                    self._add_scanned_page(comp_img)
                    self.status_lbl.setText(f"Immagine composita Fronte/Retro ({merge_mode}) creata.")
                except Exception as exc:
                    logger.error("Errore composizione duplex: %s", exc)
                    # Fallback to separate
                    self._add_scanned_page(wizard.front_image)
                    self._add_scanned_page(wizard.back_image)
                    self.status_lbl.setText("Aggiunte 2 pagine separate.")
            else:
                if wizard.front_image:
                    self._add_scanned_page(wizard.front_image)
                if wizard.back_image:
                    self._add_scanned_page(wizard.back_image)
                self.status_lbl.setText("Documento Fronte/Retro aggiunto alle pagine.")

    def _open_export_dialog(self):
        if not self.current_pages:
            QMessageBox.warning(self, "Attenzione", "Non ci sono pagine scansionate da esportare.")
            return

        if self._is_busy():
            self.status_lbl.setText("Un'operazione è già in corso. Attendi il completamento...")
            return

        dlg = ExportOCRDialog(self, default_filename=f"Scansione_Pagine_{len(self.current_pages)}")
        if dlg.exec() == ExportOCRDialog.DialogCode.Accepted:
            opts = dlg.export_options
            self._set_ui_busy(True, "Esportazione e riconoscimento OCR in corso...")

            self.worker_thread = QThread()
            self.worker = ExportWorker(
                images=list(self.current_pages),
                destination=opts["destination"],
                format_type=opts["format"],
                ocr_lang=opts["ocr_lang"]
            )
            self.worker.moveToThread(self.worker_thread)

            self.worker_thread.started.connect(self.worker.run)
            self.worker.progress.connect(self._on_scan_progress)
            self.worker.finished.connect(self._on_export_finished)
            self.worker.error.connect(self._on_scan_error)

            self.worker.finished.connect(self.worker_thread.quit)
            self.worker.finished.connect(self.worker.deleteLater)
            self.worker.error.connect(self.worker_thread.quit)
            self.worker_thread.finished.connect(self._cleanup_worker)

            self.worker_thread.start()

    def _on_export_finished(self, success: bool):
        self._set_ui_busy(False)
        self._cleanup_worker()

        if success:
            QMessageBox.information(self, "Esportazione", "File esportato con successo!")
            self.status_lbl.setText("Esportazione completata.")
        else:
            QMessageBox.critical(self, "Errore", "Si è verificato un errore durante l'esportazione.")
            self.status_lbl.setText("Errore esportazione.")

    def _set_ui_busy(self, busy: bool, message: str = ""):
        self.progress_bar.setVisible(busy)
        if busy:
            self.status_lbl.setText(message)
        if hasattr(self, "act_preview"):
            self.act_preview.setEnabled(not busy)
        if hasattr(self, "btn_preview"):
            self.btn_preview.setEnabled(not busy)
        if hasattr(self, "act_scan_flatbed"):
            self.act_scan_flatbed.setEnabled(not busy)
        if hasattr(self, "act_scan_adf"):
            self.act_scan_adf.setEnabled(not busy)
        if hasattr(self, "act_scan_duplex"):
            self.act_scan_duplex.setEnabled(not busy)
        if hasattr(self, "act_export"):
            self.act_export.setEnabled(not busy)
        if hasattr(self, "btn_primary_scan"):
            self.btn_primary_scan.setEnabled(not busy)
        if hasattr(self, "btn_deskew"):
            self.btn_deskew.setEnabled(not busy)
        if hasattr(self, "btn_autocrop"):
            self.btn_autocrop.setEnabled(not busy)
        if hasattr(self, "btn_enhance"):
            self.btn_enhance.setEnabled(not busy)
        if hasattr(self, "act_detect_subjects"):
            self.act_detect_subjects.setEnabled(not busy)
