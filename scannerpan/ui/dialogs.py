"""
Dialogs for ScannerPan:
1. DuplexScanWizardDialog (Wizard Fronte / Retro)
2. MultiSubjectChoiceDialog (Scelta Soggetti Multipli / Foto / Scontrini)
3. ExportOCRDialog (Esportazione & OCR in vari formati)
"""

import os
from typing import List, Dict, Optional, Any, Callable
from PIL import Image

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QWizard, QWizardPage, QComboBox, QLineEdit, QCheckBox,
    QSpinBox, QFileDialog, QGroupBox, QGridLayout, QTableWidget,
    QTableWidgetItem, QHeaderView, QRadioButton, QButtonGroup,
    QMessageBox, QProgressBar, QScrollArea, QWidget, QFrame
)
from PyQt6.QtGui import QPixmap, QIcon, QImage, QFont
from PyQt6.QtCore import Qt, pyqtSignal

from scannerpan.ui.kde_theme import get_kde_icon
from scannerpan.ui.canvas import pil_to_qpixmap


# ==============================================================================
# 1. WIZARD FRONTE / RETRO (Duplex Scan Wizard)
# ==============================================================================

class DuplexScanWizardDialog(QDialog):
    """
    Step-by-step wizard for scanning double-sided documents or photos.
    Supports both Flatbed manual flipping and automatic ADF Duplex scanning.
    """
    scan_requested = pyqtSignal(str)  # 'front' or 'back'

    def __init__(self, parent=None, scan_callback: Optional[Callable[[str], Any]] = None):
        super().__init__(parent)
        self.setWindowTitle("Wizard Scansione Fronte / Retro - ScannerPan")
        self.resize(750, 520)
        self.scan_callback = scan_callback

        self.front_image: Optional[Image.Image] = None
        self.back_image: Optional[Image.Image] = None

        self._current_step = 1

        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(16)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # Header with KDE Breeze icon
        header_layout = QHBoxLayout()
        icon_lbl = QLabel(self)
        icon_lbl.setPixmap(get_kde_icon("document-scan").pixmap(40, 40))
        header_layout.addWidget(icon_lbl)

        header_text_layout = QVBoxLayout()
        self.title_lbl = QLabel("Passo 1: Scansione del Fronte", self)
        self.title_lbl.setStyleSheet("font-size: 13pt; font-weight: bold; color: #3daee9;")
        self.desc_lbl = QLabel(
            "Posiziona il documento sul piano fisso (o ADF) con il fronte rivolto verso il vetro.",
            self
        )
        self.desc_lbl.setStyleSheet("color: #bdc3c7;")
        header_text_layout.addWidget(self.title_lbl)
        header_text_layout.addWidget(self.desc_lbl)
        header_layout.addLayout(header_text_layout)
        header_layout.addStretch()

        main_layout.addLayout(header_layout)

        # Central View Area
        self.preview_frame = QFrame(self)
        self.preview_frame.setStyleSheet("""
            QFrame {
                background-color: #1b1e20;
                border: 1px solid #444a50;
                border-radius: 8px;
            }
        """)
        pf_layout = QHBoxLayout(self.preview_frame)
        pf_layout.setContentsMargins(16, 16, 16, 16)
        pf_layout.setSpacing(16)

        # Front preview box
        self.front_box = QGroupBox("Anteprima Fronte", self.preview_frame)
        fb_layout = QVBoxLayout(self.front_box)
        self.front_img_lbl = QLabel("In attesa della scansione...", self.front_box)
        self.front_img_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.front_img_lbl.setStyleSheet("color: #808890;")
        fb_layout.addWidget(self.front_img_lbl, stretch=1)

        f_bar = QHBoxLayout()
        btn_rot_front = QPushButton("Ruota Fronte 90°", self.front_box)
        btn_rot_front.setIcon(get_kde_icon("object-rotate-right"))
        btn_rot_front.clicked.connect(self._rotate_front)
        f_bar.addWidget(btn_rot_front)
        fb_layout.addLayout(f_bar)

        pf_layout.addWidget(self.front_box)

        # Back preview box
        self.back_box = QGroupBox("Anteprima Retro", self.preview_frame)
        bb_layout = QVBoxLayout(self.back_box)
        self.back_img_lbl = QLabel("In attesa...", self.back_box)
        self.back_img_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.back_img_lbl.setStyleSheet("color: #808890;")
        bb_layout.addWidget(self.back_img_lbl, stretch=1)

        b_bar = QHBoxLayout()
        btn_rot_back = QPushButton("Ruota Retro 90°", self.back_box)
        btn_rot_back.setIcon(get_kde_icon("object-rotate-right"))
        btn_rot_back.clicked.connect(self._rotate_back)
        b_bar.addWidget(btn_rot_back)
        bb_layout.addLayout(b_bar)

        pf_layout.addWidget(self.back_box)

        main_layout.addWidget(self.preview_frame, stretch=1)

        # Composition layout option
        self.merge_options_box = QGroupBox("Modalità di Unione Fronte / Retro", self)
        mob_layout = QHBoxLayout(self.merge_options_box)
        self.combo_merge_mode = QComboBox(self.merge_options_box)
        self.combo_merge_mode.addItem("Pagine Separate (2 pagine PDF/fascicolo)", "separate")
        self.combo_merge_mode.addItem("Unica Immagine Affiancata (Side-by-Side)", "side_by_side")
        self.combo_merge_mode.addItem("Unica Immagine Impilata (Verticale)", "vertical")
        self.combo_merge_mode.addItem("Carta d'Identità / Patente (ID Card)", "id_card")
        self.combo_merge_mode.addItem("Carta d'Identità su Foglio A4 (Pronto Stampa)", "id_card_a4")
        mob_layout.addWidget(QLabel("Disposizione:", self.merge_options_box))
        mob_layout.addWidget(self.combo_merge_mode, stretch=1)
        main_layout.addWidget(self.merge_options_box)

        # Action / Guidance prompt
        self.guidance_box = QFrame(self)
        self.guidance_box.setStyleSheet("""
            QFrame {
                background-color: #2b3035;
                border-left: 4px solid #3daee9;
                border-radius: 4px;
                padding: 10px;
            }
        """)
        g_layout = QHBoxLayout(self.guidance_box)
        self.guidance_lbl = QLabel(
            "💡 Clicca 'Scansiona Fronte' per acquisire la prima pagina.", self.guidance_box
        )
        self.guidance_lbl.setStyleSheet("font-weight: 500;")
        g_layout.addWidget(self.guidance_lbl)
        main_layout.addWidget(self.guidance_box)

        # Buttons Bottom Bar
        btn_bar = QHBoxLayout()
        btn_bar.setSpacing(10)

        self.btn_cancel = QPushButton("Annulla", self)
        self.btn_cancel.clicked.connect(self.reject)
        btn_bar.addWidget(self.btn_cancel)

        btn_bar.addStretch()

        self.btn_action = QPushButton("Scansiona Fronte", self)
        self.btn_action.setProperty("primary", True)
        self.btn_action.setIcon(get_kde_icon("document-scan"))
        self.btn_action.clicked.connect(self._handle_action_button)
        btn_bar.addWidget(self.btn_action)

        self.btn_finish = QPushButton("Completa e Unisci", self)
        self.btn_finish.setProperty("primary", True)
        self.btn_finish.setIcon(get_kde_icon("dialog-ok-apply"))
        self.btn_finish.setEnabled(False)
        self.btn_finish.clicked.connect(self.accept)
        btn_bar.addWidget(self.btn_finish)

        main_layout.addLayout(btn_bar)

    def _rotate_front(self):
        if self.front_image:
            self.front_image = self.front_image.rotate(-90, expand=True)
            pix = pil_to_qpixmap(self.front_image).scaled(
                280, 360, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
            self.front_img_lbl.setPixmap(pix)

    def _rotate_back(self):
        if self.back_image:
            self.back_image = self.back_image.rotate(-90, expand=True)
            pix = pil_to_qpixmap(self.back_image).scaled(
                280, 360, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
            self.back_img_lbl.setPixmap(pix)

    def get_merge_mode(self) -> str:
        return self.combo_merge_mode.currentData()

    def set_front_image(self, img: Image.Image):
        self.front_image = img
        pix = pil_to_qpixmap(img).scaled(
            280, 360,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        self.front_img_lbl.setPixmap(pix)
        self._current_step = 2
        self._update_step_ui()

    def set_back_image(self, img: Image.Image):
        self.back_image = img
        pix = pil_to_qpixmap(img).scaled(
            280, 360,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        self.back_img_lbl.setPixmap(pix)
        self._current_step = 3
        self._update_step_ui()

    def _update_step_ui(self):
        if self._current_step == 1:
            self.title_lbl.setText("Passo 1: Scansione del Fronte")
            self.desc_lbl.setText("Posiziona il fronte del documento sul piano fisso dello scanner.")
            self.guidance_lbl.setText("💡 Clicca 'Scansiona Fronte' per avviare.")
            self.btn_action.setText("Scansiona Fronte")
            self.btn_action.setEnabled(True)
            self.btn_finish.setEnabled(False)
        elif self._current_step == 2:
            self.title_lbl.setText("Passo 2: Gira il Documento per il Retro")
            self.desc_lbl.setText("Gira il foglio/foto sul piano fisso dello scanner con il retro rivolto verso il vetro.")
            self.guidance_lbl.setText("🔄 Foglio girato? Clicca 'Scansiona Retro' per continuare.")
            self.btn_action.setText("Scansiona Retro")
            self.btn_action.setIcon(get_kde_icon("view-refresh"))
            self.btn_action.setEnabled(True)
            self.btn_finish.setEnabled(False)
        elif self._current_step == 3:
            self.title_lbl.setText("Passo 3: Revisione Fronte / Retro")
            self.desc_lbl.setText("Entrambe le facciate sono state acquisite con successo.")
            self.guidance_lbl.setText("✅ Verifica l'anteprima. Fai clic su 'Completa e Unisci' per procedere.")
            self.btn_action.setText("Riscansiona Retro")
            self.btn_action.setEnabled(True)
            self.btn_finish.setEnabled(True)

    def _handle_action_button(self):
        if self._current_step == 1:
            if self.scan_callback:
                res = self.scan_callback("front")
                if res:
                    self.set_front_image(res)
            else:
                self.scan_requested.emit("front")
        elif self._current_step in (2, 3):
            if self.scan_callback:
                res = self.scan_callback("back")
                if res:
                    self.set_back_image(res)
            else:
                self.scan_requested.emit("back")


# ==============================================================================
# 2. SCELTA SOGGETTI MULTIPLI (Multi-Subject Choice Dialog)
# ==============================================================================

class MultiSubjectChoiceDialog(QDialog):
    """
    Dialog to review, name, select and export multiple photos or receipts
    detected on the flatbed in a single scan.
    """
    def __init__(self, subjects_info: List[Dict[str, Any]], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Salvataggio Soggetti Riconosciuti - ScannerPan")
        self.resize(760, 500)
        self.subjects_info = subjects_info
        self.selected_results: List[Dict[str, Any]] = []

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        # Header
        h_layout = QHBoxLayout()
        ic = QLabel(self)
        ic.setPixmap(get_kde_icon("edit-cut").pixmap(36, 36))
        h_layout.addWidget(ic)

        txt_l = QVBoxLayout()
        title = QLabel(f"Riconosciuti {len(self.subjects_info)} elementi sul piano fisso", self)
        title.setStyleSheet("font-size: 12pt; font-weight: bold; color: #3daee9;")
        desc = QLabel(
            "Seleziona quali elementi esportare, personalizza il nome file e la cartella di destinazione.",
            self
        )
        desc.setStyleSheet("color: #bdc3c7;")
        txt_l.addWidget(title)
        txt_l.addWidget(desc)
        h_layout.addLayout(txt_l)
        h_layout.addStretch()
        layout.addLayout(h_layout)

        # Table of subjects
        self.table = QTableWidget(len(self.subjects_info), 5, self)
        self.table.setHorizontalHeaderLabels(["Includi", "Anteprima", "Nome File", "Dimensioni", "Ruota"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalHeader().setDefaultSectionSize(70)

        for row, subj in enumerate(self.subjects_info):
            # Checkbox
            chk = QCheckBox(self)
            chk.setChecked(subj.get("selected", True))
            cell_chk_widget = QWidget()
            c_lay = QHBoxLayout(cell_chk_widget)
            c_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
            c_lay.setContentsMargins(0, 0, 0, 0)
            c_lay.addWidget(chk)
            self.table.setCellWidget(row, 0, cell_chk_widget)

            # Thumbnail
            thumb_lbl = QLabel(self)
            thumb_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            img = subj.get("image")
            if isinstance(img, Image.Image):
                qpix = pil_to_qpixmap(img).scaled(
                    60, 60, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
                )
                thumb_lbl.setPixmap(qpix)
            elif isinstance(img, QPixmap):
                thumb_lbl.setPixmap(img.scaled(60, 60, Qt.AspectRatioMode.KeepAspectRatio))
            else:
                thumb_lbl.setText("Foto")
            self.table.setCellWidget(row, 1, thumb_lbl)

            # Name Edit
            default_name = subj.get("name", f"Scansione_Soggetto_{row+1:02d}")
            name_edit = QLineEdit(default_name, self)
            self.table.setCellWidget(row, 2, name_edit)

            # Dimensions
            w, h = subj.get("width", 0), subj.get("height", 0)
            dim_lbl = QLabel(f"{w}x{h} px" if w > 0 else "-", self)
            dim_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setCellWidget(row, 3, dim_lbl)

            # Rotation combo
            rot_combo = QComboBox(self)
            rot_combo.addItems(["0°", "90°", "180°", "270°"])
            self.table.setCellWidget(row, 4, rot_combo)

        layout.addWidget(self.table, stretch=1)

        # Output folder & format options
        opt_box = QGroupBox("Impostazioni di Esportazione", self)
        opt_grid = QGridLayout(opt_box)

        opt_grid.addWidget(QLabel("Cartella di salvataggio:"), 0, 0)
        self.folder_edit = QLineEdit(os.path.expanduser("~/Immagini"), opt_box)
        opt_grid.addWidget(self.folder_edit, 0, 1)

        self.btn_browse = QPushButton("Sfoglia...", opt_box)
        self.btn_browse.setIcon(get_kde_icon("document-open"))
        self.btn_browse.clicked.connect(self._browse_folder)
        opt_grid.addWidget(self.btn_browse, 0, 2)

        opt_grid.addWidget(QLabel("Formato immagini:"), 1, 0)
        self.format_combo = QComboBox(opt_box)
        self.format_combo.addItems(["JPEG (*.jpg)", "PNG (*.png)", "WebP (*.webp)", "TIFF (*.tiff)", "PDF Singoli (*.pdf)"])
        opt_grid.addWidget(self.format_combo, 1, 1)

        layout.addWidget(opt_box)

        # Buttons
        b_bar = QHBoxLayout()
        btn_sel_all = QPushButton("Seleziona tutti", self)
        btn_sel_all.clicked.connect(lambda: self._set_all_checks(True))
        b_bar.addWidget(btn_sel_all)

        btn_desel_all = QPushButton("Deseleziona tutti", self)
        btn_desel_all.clicked.connect(lambda: self._set_all_checks(False))
        b_bar.addWidget(btn_desel_all)

        b_bar.addStretch()

        btn_cancel = QPushButton("Annulla", self)
        btn_cancel.clicked.connect(self.reject)
        b_bar.addWidget(btn_cancel)

        btn_save = QPushButton("Salva Selezionati", self)
        btn_save.setProperty("primary", True)
        btn_save.setIcon(get_kde_icon("document-save"))
        btn_save.clicked.connect(self._collect_and_accept)
        b_bar.addWidget(btn_save)

        layout.addLayout(b_bar)

    def _browse_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Seleziona Cartella di Destinazione", self.folder_edit.text())
        if d:
            self.folder_edit.setText(d)

    def _set_all_checks(self, checked: bool):
        for row in range(self.table.rowCount()):
            chk_cell = self.table.cellWidget(row, 0)
            chk = chk_cell.findChild(QCheckBox)
            if chk:
                chk.setChecked(checked)

    def _collect_and_accept(self):
        out_dir = self.folder_edit.text().strip()
        fmt = self.format_combo.currentText().split()[0].lower()

        results = []
        for row in range(self.table.rowCount()):
            chk_cell = self.table.cellWidget(row, 0)
            chk = chk_cell.findChild(QCheckBox)
            if chk and chk.isChecked():
                name_edit: QLineEdit = self.table.cellWidget(row, 2)
                rot_combo: QComboBox = self.table.cellWidget(row, 4)

                subj = dict(self.subjects_info[row])
                subj["filename"] = name_edit.text().strip()
                subj["rotation"] = int(rot_combo.currentText().replace("°", ""))
                subj["output_dir"] = out_dir
                subj["format"] = fmt
                results.append(subj)

        if not results:
            QMessageBox.warning(self, "Nessun elemento", "Seleziona almeno un soggetto da salvare.")
            return

        self.selected_results = results
        self.accept()


# ==============================================================================
# 3. ESPORTAZIONE & OCR (Export & OCR Dialog)
# ==============================================================================

class ExportOCRDialog(QDialog):
    """
    Dialog for exporting scanned document(s) to searchable PDF, DOCX, ODT,
    RTF, TXT or high-res images, with full OCR language and resolution choices.
    """
    def __init__(self, parent=None, default_filename: str = "Documento_Scansionato"):
        super().__init__(parent)
        self.setWindowTitle("Esportazione Documento & OCR - ScannerPan")
        self.resize(600, 520)

        self.default_filename = default_filename
        self.export_options: Dict[str, Any] = {}

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(18, 18, 18, 18)

        # Header
        h_layout = QHBoxLayout()
        ic = QLabel(self)
        ic.setPixmap(get_kde_icon("document-save").pixmap(36, 36))
        h_layout.addWidget(ic)

        txt_l = QVBoxLayout()
        t = QLabel("Esportazione e Riconoscimento Testo (OCR)", self)
        t.setStyleSheet("font-size: 12pt; font-weight: bold; color: #3daee9;")
        d = QLabel("Scegli il formato del file di output e i parametri di riconoscimento.", self)
        d.setStyleSheet("color: #bdc3c7;")
        txt_l.addWidget(t)
        txt_l.addWidget(d)
        h_layout.addLayout(txt_l)
        h_layout.addStretch()
        layout.addLayout(h_layout)

        # Group 1: Format
        fmt_group = QGroupBox("Formato di Destinazione", self)
        fg_layout = QGridLayout(fmt_group)

        self.rb_pdf = QRadioButton("PDF Ricercabile (Searchable PDF con OCR)", fmt_group)
        self.rb_pdf.setChecked(True)
        self.rb_pdf.toggled.connect(self._on_format_changed)
        fg_layout.addWidget(self.rb_pdf, 0, 0)

        self.rb_docx = QRadioButton("Microsoft Word (.docx)", fmt_group)
        self.rb_docx.toggled.connect(self._on_format_changed)
        fg_layout.addWidget(self.rb_docx, 0, 1)

        self.rb_odt = QRadioButton("OpenDocument Text (.odt)", fmt_group)
        self.rb_odt.toggled.connect(self._on_format_changed)
        fg_layout.addWidget(self.rb_odt, 1, 0)

        self.rb_rtf = QRadioButton("Rich Text Format (.rtf)", fmt_group)
        self.rb_rtf.toggled.connect(self._on_format_changed)
        fg_layout.addWidget(self.rb_rtf, 1, 1)

        self.rb_txt = QRadioButton("Solo Testo Estratto (.txt)", fmt_group)
        self.rb_txt.toggled.connect(self._on_format_changed)
        fg_layout.addWidget(self.rb_txt, 2, 0)

        self.rb_img = QRadioButton("Immagine Singola / Multipagina (PNG, JPG, TIFF, WebP)", fmt_group)
        self.rb_img.toggled.connect(self._on_format_changed)
        fg_layout.addWidget(self.rb_img, 2, 1)

        layout.addWidget(fmt_group)

        # Image Subformat (visible only if rb_img selected)
        self.img_format_combo = QComboBox(self)
        self.img_format_combo.addItems(["PNG (*.png)", "JPEG (*.jpg)", "TIFF Multipagina (*.tiff)", "WebP (*.webp)"])
        self.img_format_combo.setVisible(False)
        layout.addWidget(self.img_format_combo)

        # Group 2: OCR Settings
        self.ocr_group = QGroupBox("Parametri di Riconoscimento Testo (Tesseract OCR)", self)
        og_layout = QGridLayout(self.ocr_group)

        og_layout.addWidget(QLabel("Lingua OCR:"), 0, 0)
        self.lang_combo = QComboBox(self.ocr_group)
        self.lang_combo.addItem("Italiano (ita)", "ita")
        self.lang_combo.addItem("Inglese (eng)", "eng")
        self.lang_combo.addItem("Italiano + Inglese (ita+eng)", "ita+eng")
        self.lang_combo.addItem("Francese (fra)", "fra")
        self.lang_combo.addItem("Tedesco (deu)", "deu")
        self.lang_combo.addItem("Spagnolo (spa)", "spa")
        og_layout.addWidget(self.lang_combo, 0, 1)

        self.chk_enhance = QCheckBox("Migliora nitidezza e raddrizza testo (Deskew automatico)", self.ocr_group)
        self.chk_enhance.setChecked(True)
        og_layout.addWidget(self.chk_enhance, 1, 0, 1, 2)

        self.chk_remove_shadows = QCheckBox("Rimuovi ombre e macchie di scansione", self.ocr_group)
        self.chk_remove_shadows.setChecked(True)
        og_layout.addWidget(self.chk_remove_shadows, 2, 0, 1, 2)

        layout.addWidget(self.ocr_group)

        # Group 3: File Destination
        dest_group = QGroupBox("Destinazione File", self)
        dg_layout = QGridLayout(dest_group)

        dg_layout.addWidget(QLabel("Salva in:"), 0, 0)
        default_path = os.path.expanduser(f"~/Documenti/{self.default_filename}.pdf")
        self.dest_edit = QLineEdit(default_path, dest_group)
        dg_layout.addWidget(self.dest_edit, 0, 1)

        btn_browse = QPushButton("Sfoglia...", dest_group)
        btn_browse.setIcon(get_kde_icon("document-open"))
        btn_browse.clicked.connect(self._browse_save_path)
        dg_layout.addWidget(btn_browse, 0, 2)

        layout.addWidget(dest_group)

        # Bottom buttons
        b_bar = QHBoxLayout()
        b_bar.addStretch()

        btn_cancel = QPushButton("Annulla", self)
        btn_cancel.clicked.connect(self.reject)
        b_bar.addWidget(btn_cancel)

        btn_export = QPushButton("Avvia Esportazione", self)
        btn_export.setProperty("primary", True)
        btn_export.setIcon(get_kde_icon("document-save"))
        btn_export.clicked.connect(self._confirm_export)
        b_bar.addWidget(btn_export)

        layout.addLayout(b_bar)

    def _on_format_changed(self):
        is_img = self.rb_img.isChecked()
        self.img_format_combo.setVisible(is_img)
        self.ocr_group.setEnabled(not is_img)

        ext = ".pdf"
        if self.rb_docx.isChecked():
            ext = ".docx"
        elif self.rb_odt.isChecked():
            ext = ".odt"
        elif self.rb_rtf.isChecked():
            ext = ".rtf"
        elif self.rb_txt.isChecked():
            ext = ".txt"
        elif is_img:
            sub = self.img_format_combo.currentText().split()[0].lower()
            ext = f".{sub}"

        cur = self.dest_edit.text()
        base, _ = os.path.splitext(cur)
        self.dest_edit.setText(f"{base}{ext}")

    def _browse_save_path(self):
        filter_str = "PDF Document (*.pdf);;Tutti i file (*.*)"
        if self.rb_docx.isChecked():
            filter_str = "Word Document (*.docx);;Tutti i file (*.*)"
        elif self.rb_odt.isChecked():
            filter_str = "OpenDocument (*.odt);;Tutti i file (*.*)"
        elif self.rb_rtf.isChecked():
            filter_str = "Rich Text (*.rtf);;Tutti i file (*.*)"
        elif self.rb_txt.isChecked():
            filter_str = "Text File (*.txt);;Tutti i file (*.*)"
        elif self.rb_img.isChecked():
            filter_str = "Images (*.png *.jpg *.tiff *.webp);;Tutti i file (*.*)"

        path, _ = QFileDialog.getSaveFileName(
            self, "Salva file esportato", self.dest_edit.text(), filter_str
        )
        if path:
            self.dest_edit.setText(path)

    def _confirm_export(self):
        dest = self.dest_edit.text().strip()
        if not dest:
            QMessageBox.warning(self, "Attenzione", "Specifica un percorso di destinazione valido.")
            return

        fmt = "pdf"
        if self.rb_docx.isChecked():
            fmt = "docx"
        elif self.rb_odt.isChecked():
            fmt = "odt"
        elif self.rb_rtf.isChecked():
            fmt = "rtf"
        elif self.rb_txt.isChecked():
            fmt = "txt"
        elif self.rb_img.isChecked():
            fmt = self.img_format_combo.currentText().split()[0].lower()

        self.export_options = {
            "format": fmt,
            "destination": dest,
            "ocr_lang": self.lang_combo.currentData(),
            "enhance": self.chk_enhance.isChecked(),
            "remove_shadows": self.chk_remove_shadows.isChecked()
        }
        self.accept()
