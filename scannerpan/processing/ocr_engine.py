"""ScannerPan - OCR Engine & Multi-format Document Exporter.

Motore avanzato di riconoscimento ottico dei caratteri (OCR) basato su Tesseract:
- Supporto multilingua: Italiano (ita), Tedesco (deu), Inglese (eng).
- Esportazione in Searchable PDF (PDF vettoriale ricercabile multi-pagina).
- Esportazione in formato Microsoft Word DOCX (tramite python-docx).
- Esportazione in formato OpenDocument Text ODT (tramite odfpy).
- Esportazione in formato Rich Text Format RTF (con codifica Unicode nativa e stili).
- Esportazione in formato testo puro TXT (UTF-8).
- Calcolo indice di confidenza medio e tracciamento parole e coordinate.
"""

from __future__ import annotations

import csv
import io
import logging
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

from PIL import Image

try:
    import docx
    from docx.shared import Inches, Pt, RGBColor
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False

try:
    from odf.opendocument import OpenDocumentText
    from odf.style import Style, TextProperties
    from odf.text import H, P
    ODF_AVAILABLE = True
except ImportError:
    ODF_AVAILABLE = False

from enum import Enum

logger = logging.getLogger("scannerpan.processing.ocr_engine")


class DocumentFormat(str, Enum):
    """Formati documento supportati per l'esportazione OCR."""
    PDF = "pdf"
    DOCX = "docx"
    ODT = "odt"
    RTF = "rtf"
    TXT = "txt"


@dataclass
class OCRWord:
    """Informazioni su una singola parola identificata tramite OCR."""
    text: str
    confidence: float
    bbox: Tuple[int, int, int, int]  # (x, y, w, h)
    line_num: int
    page_num: int


@dataclass
class OCRResult:
    """Risultato completo dell'elaborazione OCR su uno o più fogli."""
    text: str
    confidence: float  # Percentuale media (0.0 - 100.0)
    language: str
    words: List[OCRWord] = field(default_factory=list)
    page_count: int = 1
    execution_time_sec: float = 0.0
    source_images: List[Path] = field(default_factory=list)

    def is_reliable(self, threshold: float = 60.0) -> bool:
        """Determina se il testo estratto ha una confidenza sufficientemente affidabile."""
        return self.confidence >= threshold


class OCREngine:
    """Motore OCR e convertitore multiformato per ScannerPan."""

    SUPPORTED_LANGUAGES = ["ita", "deu", "eng"]
    DEFAULT_LANGUAGES = "ita+eng"

    def __init__(self, tesseract_path: Optional[str] = None):
        if tesseract_path:
            self.tesseract_bin = tesseract_path
        else:
            found = shutil.which("tesseract")
            if not found and os.name == "nt":
                candidates = [
                    os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "Tesseract-OCR", "tesseract.exe"),
                    os.path.join(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), "Tesseract-OCR", "tesseract.exe"),
                    os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Tesseract-OCR", "tesseract.exe"),
                ]
                for c in candidates:
                    if os.path.isfile(c):
                        found = c
                        break
            self.tesseract_bin = found or (r"C:\Program Files\Tesseract-OCR\tesseract.exe" if os.name == "nt" else "/usr/bin/tesseract")
        self._available_langs = self._query_available_languages()

    def is_available(self) -> bool:
        """Verifica se l'eseguibile tesseract è presente sul sistema."""
        return os.path.isfile(self.tesseract_bin) and os.access(self.tesseract_bin, os.X_OK)

    def _query_available_languages(self) -> List[str]:
        """Elenca le lingue correntemente installate nel dizionario Tesseract."""
        if not self.is_available():
            return []
        try:
            res = subprocess.run([self.tesseract_bin, "--list-langs"], capture_output=True, text=True, check=False)
            lines = [line.strip() for line in res.stdout.splitlines() if line.strip()]
            langs = [l for l in lines if not l.startswith("List of")]
            return langs
        except Exception as exc:
            logger.warning("Impossibile determinare le lingue Tesseract: %s", exc)
            return ["ita", "eng", "deu"]

    def validate_languages(self, lang_spec: str) -> str:
        """Valida e normalizza la stringa della lingua (es. 'ita', 'deu+eng')."""
        parts = [p.strip() for p in lang_spec.split("+") if p.strip()]
        valid_parts = []
        for p in parts:
            if p in self._available_langs:
                valid_parts.append(p)
            else:
                logger.warning("Lingua OCR '%s' non trovata tra i dizionari installati.", p)
        if not valid_parts:
            # Fallback
            for fb in ["ita", "eng", "deu"]:
                if fb in self._available_langs:
                    valid_parts.append(fb)
                    break
        return "+".join(valid_parts) if valid_parts else "eng"

    def recognize(
        self,
        images: Union[str, Path, Image.Image, List[Union[str, Path, Image.Image]]],
        language: str = DEFAULT_LANGUAGES,
        psm: int = 3,  # Page segmentation mode (3 = Fully automatic page segmentation)
    ) -> OCRResult:
        """Esegue il riconoscimento OCR su una o più immagini di input.

        Restituisce un oggetto OCRResult con il testo estratto e la percentuale di confidenza media.
        """
        start_time = time.time()
        img_list = images if isinstance(images, list) else [images]
        valid_lang = self.validate_languages(language)

        temp_dir = Path(tempfile.mkdtemp(prefix="scannerpan_ocr_"))
        temp_paths: List[Path] = []

        try:
            for idx, img_input in enumerate(img_list):
                if isinstance(img_input, (str, Path)) and Path(img_input).exists():
                    temp_paths.append(Path(img_input))
                elif isinstance(img_input, Image.Image):
                    p = temp_dir / f"page_{idx:04d}.png"
                    img_input.save(str(p), "PNG")
                    temp_paths.append(p)
                else:
                    raise ValueError(f"Input immagine non valido: {img_input}")

            if not temp_paths:
                return OCRResult(text="", confidence=0.0, language=valid_lang)

            full_texts: List[str] = []
            all_words: List[OCRWord] = []
            confidences: List[float] = []

            for page_num, p in enumerate(temp_paths, start=1):
                # Esegui tesseract estraendo sia TSV (dati analitici parole/confidenza) che testo puro
                cmd_tsv = [
                    self.tesseract_bin,
                    str(p),
                    "stdout",
                    "-l", valid_lang,
                    f"--psm", str(psm),
                    "tsv"
                ]
                proc_tsv = subprocess.run(cmd_tsv, capture_output=True, text=True, check=False)
                if proc_tsv.returncode == 0:
                    page_words, page_conf = self._parse_tsv(proc_tsv.stdout, page_num)
                    all_words.extend(page_words)
                    if page_conf > 0:
                        confidences.append(page_conf)

                # Testo pulito
                cmd_txt = [
                    self.tesseract_bin,
                    str(p),
                    "stdout",
                    "-l", valid_lang,
                    f"--psm", str(psm),
                ]
                proc_txt = subprocess.run(cmd_txt, capture_output=True, text=True, check=False)
                if proc_txt.returncode == 0:
                    full_texts.append(proc_txt.stdout.strip())

            final_text = "\n\n--- Nuova Pagina ---\n\n".join(full_texts) if len(full_texts) > 1 else (full_texts[0] if full_texts else "")
            avg_confidence = float(sum(confidences) / len(confidences)) if confidences else 0.0

            return OCRResult(
                text=final_text,
                confidence=round(avg_confidence, 1),
                language=valid_lang,
                words=all_words,
                page_count=len(temp_paths),
                execution_time_sec=round(time.time() - start_time, 2),
                source_images=temp_paths,
            )

        finally:
            # Pulisci file temporanei generati internamente (se presenti in temp_dir)
            try:
                for f in temp_dir.glob("page_*.png"):
                    f.unlink(missing_ok=True)
                temp_dir.rmdir()
            except Exception:
                pass

    def _parse_tsv(self, tsv_output: str, page_num: int) -> Tuple[List[OCRWord], float]:
        """Effettua il parsing dell'output TSV di tesseract per estrarre parole, bounding box e confidenze."""
        words: List[OCRWord] = []
        confs: List[float] = []

        reader = csv.DictReader(io.StringIO(tsv_output), delimiter="\t")
        for row in reader:
            txt = row.get("text", "").strip()
            conf_str = row.get("conf", "-1")
            try:
                conf = float(conf_str)
            except ValueError:
                conf = -1.0

            if txt and conf >= 0:
                x = int(row.get("left", 0))
                y = int(row.get("top", 0))
                w = int(row.get("width", 0))
                h = int(row.get("height", 0))
                line_num = int(row.get("line_num", 1))

                words.append(
                    OCRWord(
                        text=txt,
                        confidence=conf,
                        bbox=(x, y, w, h),
                        line_num=line_num,
                        page_num=page_num,
                    )
                )
                confs.append(conf)

        avg_conf = float(sum(confs) / len(confs)) if confs else 0.0
        return words, avg_conf

    # =========================================================================
    # ESPORTAZIONE DOCUMENTI
    # =========================================================================

    def export_searchable_pdf(
        self,
        images: Union[str, Path, List[Union[str, Path]]],
        output_pdf_path: Union[str, Path],
        language: str = DEFAULT_LANGUAGES,
    ) -> Path:
        """Crea un documento PDF ricercabile (Searchable PDF) con testo vettoriale indicizzabile.

        Se viene fornita una lista di immagini, crea un PDF multi-pagina.
        """
        out_path = Path(output_pdf_path).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        valid_lang = self.validate_languages(language)

        img_list = images if isinstance(images, list) else [images]
        img_paths = [Path(img).resolve() for img in img_list]

        # Tesseract rimuove automaticamente il suffisso .pdf dall'outputbase
        out_base = str(out_path.with_suffix(""))

        if len(img_paths) == 1:
            cmd = [
                self.tesseract_bin,
                str(img_paths[0]),
                out_base,
                "-l", valid_lang,
                "pdf"
            ]
            proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if proc.returncode != 0:
                raise RuntimeError(f"Errore generazione PDF ricercabile da Tesseract: {proc.stderr}")
        else:
            # Per immagini multiple, tesseract accetta un file di testo con la lista dei path
            with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as list_file:
                for p in img_paths:
                    list_file.write(f"{str(p)}\n")
                list_file_path = list_file.name

            try:
                cmd = [
                    self.tesseract_bin,
                    list_file_path,
                    out_base,
                    "-l", valid_lang,
                    "pdf"
                ]
                proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
                if proc.returncode != 0:
                    raise RuntimeError(f"Errore generazione PDF multi-pagina da Tesseract: {proc.stderr}")
            finally:
                Path(list_file_path).unlink(missing_ok=True)

        target_file = Path(f"{out_base}.pdf")
        if not target_file.exists():
            raise FileNotFoundError(f"File PDF atteso non generato: {target_file}")

        return target_file

    def export_docx(
        self,
        text: str,
        output_path: Union[str, Path],
        title: str = "Documento Digitalizzato - ScannerPan",
        source_image: Optional[Path] = None,
    ) -> Path:
        """Esporta il testo estratto in un file Microsoft Word DOCX formattato."""
        if not DOCX_AVAILABLE:
            raise ImportError("Modulo python-docx non disponibile. Installa con: pip install python-docx")

        out_path = Path(output_path).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)

        doc = docx.Document()

        # Intestazione con titolo formattato
        heading = doc.add_heading(title, level=0)
        heading.paragraph_format.space_after = Pt(12)

        # Metadati generati
        meta_para = doc.add_paragraph()
        run_meta = meta_para.add_run(f"Data digitalizzazione: {time.strftime('%d/%m/%Y %H:%M')} | Generato con ScannerPan")
        run_meta.font.size = Pt(9)
        run_meta.font.italic = True
        run_meta.font.color.rgb = RGBColor(120, 120, 120)

        # Se richiesta, inserisci l'immagine di scansione in miniatura
        if source_image and Path(source_image).exists():
            try:
                doc.add_paragraph("Scansione Originale:")
                doc.add_picture(str(source_image), width=Inches(5.0))
                doc.add_paragraph()
            except Exception as exc:
                logger.warning("Impossibile incorporare l'immagine nel DOCX: %s", exc)

        # Corpo del testo
        doc.add_heading("Testo Riconosciuto (OCR)", level=1)
        paragraphs = text.split("\n")
        for p in paragraphs:
            line = p.strip()
            if line:
                doc.add_paragraph(line)

        doc.save(str(out_path))
        return out_path

    def export_odt(
        self,
        text: str,
        output_path: Union[str, Path],
        title: str = "Documento Digitalizzato - ScannerPan",
    ) -> Path:
        """Esporta il testo estratto in formato OpenDocument Text ODT (compatibile LibreOffice)."""
        if not ODF_AVAILABLE:
            raise ImportError("Modulo odfpy non disponibile. Installa con: pip install odfpy")

        out_path = Path(output_path).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)

        doc = OpenDocumentText()

        # Titolo principale H1
        doc.text.addElement(H(outlinelevel=1, text=title))

        # Metadati
        ts_str = f"Data: {time.strftime('%d/%m/%Y %H:%M')} | Riconoscimento ottico OCR ScannerPan"
        doc.text.addElement(P(text=ts_str))

        # Paragrafi di testo
        for line in text.split("\n"):
            line = line.strip()
            if line:
                doc.text.addElement(P(text=line))
            else:
                doc.text.addElement(P(text=""))

        doc.save(str(out_path))
        return out_path

    def export_rtf(
        self,
        text: str,
        output_path: Union[str, Path],
        title: str = "Documento Digitalizzato - ScannerPan",
    ) -> Path:
        """Esporta il testo in formato Rich Text Format (RTF) nativo con corretta codifica caratteri UTF-8."""
        out_path = Path(output_path).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)

        def _escape_rtf(input_str: str) -> str:
            escaped = []
            for ch in input_str:
                code = ord(ch)
                if ch == "\n":
                    escaped.append(r"\par ")
                elif ch in ("{", "}", "\\"):
                    escaped.append(f"\\{ch}")
                elif 32 <= code <= 126:
                    escaped.append(ch)
                else:
                    if code > 32767:
                        code -= 65536
                    escaped.append(f"\\u{code}?")
            return "".join(escaped)

        rtf_title = _escape_rtf(title)
        rtf_date = _escape_rtf(f"Data scansione: {time.strftime('%d/%m/%Y %H:%M')} - ScannerPan")
        rtf_body = _escape_rtf(text)

        rtf_content = (
            r"{\rtf1\ansi\ansicpg1252\deff0\nouicompat"
            r"{\fonttbl{\f0\fnil\fcharset0 Arial;}{\f1\fnil\fcharset0 Calibri;}}"
            r"{\colortbl ;\red30\green80\blue180;\red120\green120\blue120;\red0\green0\blue0;}"
            r"\viewkind4\uc1"
            rf"\pard\sa200\sl276\slmult1\cf1\b\fs32 {rtf_title}\cf3\b0\fs20\par" + "\n"
            rf"\pard\sa100\cf2\i {rtf_date}\i0\par\par" + "\n"
            r"\pard\sa160\sl260\slmult1\cf3\f1\fs22 "
            f"{rtf_body}\\par\n"
            r"}"
        )

        with open(out_path, "w", encoding="ascii", errors="replace") as f:
            f.write(rtf_content)

        return out_path

    def export_txt(
        self,
        text: str,
        output_path: Union[str, Path],
    ) -> Path:
        """Esporta il testo estratto in formato UTF-8 puro."""
        out_path = Path(output_path).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)

        with open(out_path, "w", encoding="utf-8") as f:
            f.write(text)

        return out_path

    def export(
        self,
        ocr_result: OCRResult,
        format_type: str,
        output_path: Union[str, Path],
        title: Optional[str] = None,
    ) -> Path:
        """Metodo unificato per esportare il risultato OCR nel formato desiderato.

        Formati supportati: 'pdf', 'docx', 'odt', 'rtf', 'txt'.
        """
        fmt = format_type.lower().strip().lstrip(".")
        title_str = title or "Documento Riconosciuto - ScannerPan"

        if fmt == "pdf":
            if not ocr_result.source_images:
                raise ValueError("Nessuna immagine sorgente registrata nel risultato OCR per generare il PDF ricercabile.")
            return self.export_searchable_pdf(
                images=ocr_result.source_images,
                output_pdf_path=output_path,
                language=ocr_result.language,
            )
        elif fmt == "docx":
            src = ocr_result.source_images[0] if ocr_result.source_images else None
            return self.export_docx(text=ocr_result.text, output_path=output_path, title=title_str, source_image=src)
        elif fmt == "odt":
            return self.export_odt(text=ocr_result.text, output_path=output_path, title=title_str)
        elif fmt == "rtf":
            return self.export_rtf(text=ocr_result.text, output_path=output_path, title=title_str)
        elif fmt == "txt":
            return self.export_txt(text=ocr_result.text, output_path=output_path)
        else:
            raise ValueError(f"Formato di esportazione '{format_type}' non supportato. Formati validi: pdf, docx, odt, rtf, txt.")
