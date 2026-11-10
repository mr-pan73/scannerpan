"""
ScannerPan - OCR & Document Exporter Engine.
Exports scanned pages to Searchable PDF, DOCX, ODT, RTF, TXT, and images (PNG, JPG, TIFF, WebP).
Uses system tesseract CLI for rock-solid OCR and native Python libraries.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional, Union
from PIL import Image

logger = logging.getLogger("scannerpan.processing.ocr_exporter")


def run_tesseract_ocr(
    image: Image.Image,
    lang: str = "ita",
    output_type: str = "txt"
) -> Union[str, bytes]:
    """
    Executes tesseract CLI directly on a PIL image.
    output_type: 'txt' or 'pdf'
    """
    tesseract_bin = shutil.which("tesseract") or "/usr/bin/tesseract"
    if not os.path.exists(tesseract_bin):
        logger.warning("Tesseract binary not found at %s", tesseract_bin)
        return "" if output_type == "txt" else b""

    with tempfile.TemporaryDirectory(prefix="scannerpan_ocr_") as tmp_dir:
        in_img_path = Path(tmp_dir) / "input.png"
        image.save(in_img_path, format="PNG")
        out_base = Path(tmp_dir) / "output"

        cmd = [tesseract_bin, str(in_img_path), str(out_base), "-l", lang]
        if output_type == "pdf":
            cmd.append("pdf")

        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if res.returncode != 0:
            logger.error("Tesseract error: %s", res.stderr)

        if output_type == "pdf":
            pdf_path = Path(tmp_dir) / "output.pdf"
            if pdf_path.exists():
                return pdf_path.read_bytes()
            return b""
        else:
            txt_path = Path(tmp_dir) / "output.txt"
            if txt_path.exists():
                return txt_path.read_text(encoding="utf-8", errors="replace")
            return ""


def export_scanned_document(
    images: List[Image.Image],
    output_path: Union[str, Path],
    format_type: str = "pdf",
    ocr_lang: str = "ita",
    progress_callback: Optional[callable] = None
) -> bool:
    """
    Exports a list of scanned PIL images into the requested document format.
    format_type: 'pdf', 'docx', 'odt', 'rtf', 'txt', 'png', 'jpg', 'tiff', 'webp'
    """
    if not images:
        logger.warning("No images provided for export")
        return False

    out_p = Path(output_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    fmt = format_type.lower().strip(".")

    total = len(images)
    try:
        # 1. SEARCHABLE PDF
        if fmt == "pdf":
            # If tesseract is available, generate searchable PDF per page and merge with pdfunite/img2pdf
            tesseract_bin = shutil.which("tesseract")
            pdfunite_bin = shutil.which("pdfunite")

            if tesseract_bin and pdfunite_bin and len(images) > 1:
                with tempfile.TemporaryDirectory(prefix="scannerpan_pdf_") as tmp_dir:
                    page_pdfs = []
                    for idx, img in enumerate(images):
                        if progress_callback:
                            progress_callback(int((idx / total) * 90), f"OCR Pagina {idx+1}/{total}...")
                        pdf_bytes = run_tesseract_ocr(img, lang=ocr_lang, output_type="pdf")
                        if pdf_bytes:
                            p_path = Path(tmp_dir) / f"page_{idx:03d}.pdf"
                            p_path.write_bytes(pdf_bytes)
                            page_pdfs.append(str(p_path))
                        else:
                            # Fallback direct image save to pdf
                            p_path = Path(tmp_dir) / f"page_{idx:03d}.pdf"
                            img.convert("RGB").save(p_path, "PDF")
                            page_pdfs.append(str(p_path))

                    if progress_callback:
                        progress_callback(95, "Unione pagine PDF in corso...")
                    merge_cmd = [pdfunite_bin] + page_pdfs + [str(out_p)]
                    subprocess.run(merge_cmd, check=True)
            elif tesseract_bin and len(images) == 1:
                if progress_callback:
                    progress_callback(50, "OCR del documento in corso...")
                pdf_bytes = run_tesseract_ocr(images[0], lang=ocr_lang, output_type="pdf")
                if pdf_bytes:
                    out_p.write_bytes(pdf_bytes)
                else:
                    images[0].convert("RGB").save(out_p, "PDF")
            else:
                # Direct PIL PDF save
                first = images[0].convert("RGB")
                rest = [im.convert("RGB") for im in images[1:]]
                first.save(out_p, "PDF", save_all=True, append_images=rest)

        # 2. DOCX (Microsoft Word)
        elif fmt == "docx":
            import docx
            from docx.shared import Inches

            doc = docx.Document()
            for idx, img in enumerate(images):
                if progress_callback:
                    progress_callback(int((idx / total) * 90), f"OCR Pagina {idx+1}/{total} per Word...")
                text = run_tesseract_ocr(img, lang=ocr_lang, output_type="txt")
                if idx > 0:
                    doc.add_page_break()
                doc.add_heading(f"Pagina {idx+1}", level=2)
                for paragraph in text.split("\n\n"):
                    p_clean = paragraph.strip()
                    if p_clean:
                        doc.add_paragraph(p_clean)
            doc.save(str(out_p))

        # 3. ODT (OpenDocument Text)
        elif fmt == "odt":
            from odf.opendocument import OpenDocumentText
            from odf.text import P, H

            doc = OpenDocumentText()
            for idx, img in enumerate(images):
                if progress_callback:
                    progress_callback(int((idx / total) * 90), f"OCR Pagina {idx+1}/{total} per ODT...")
                text = run_tesseract_ocr(img, lang=ocr_lang, output_type="txt")
                h = H(outlinelevel=2, text=f"Pagina {idx+1}")
                doc.text.addElement(h)
                for paragraph in text.split("\n\n"):
                    p_clean = paragraph.strip()
                    if p_clean:
                        doc.text.addElement(P(text=p_clean))
            doc.save(str(out_p))

        # 4. RTF (Rich Text Format)
        elif fmt == "rtf":
            rtf_content = ["{\\rtf1\\ansi\\deff0"]
            for idx, img in enumerate(images):
                if progress_callback:
                    progress_callback(int((idx / total) * 90), f"OCR Pagina {idx+1}/{total} per RTF...")
                text = run_tesseract_ocr(img, lang=ocr_lang, output_type="txt")
                rtf_content.append(f"\\b Pagina {idx+1}\\b0\\par")
                for line in text.splitlines():
                    rtf_content.append(f"{line}\\par")
                rtf_content.append("\\page")
            rtf_content.append("}")
            out_p.write_text("\n".join(rtf_content), encoding="utf-8")

        # 5. TXT (Plain text)
        elif fmt == "txt":
            all_text = []
            for idx, img in enumerate(images):
                if progress_callback:
                    progress_callback(int((idx / total) * 90), f"OCR Pagina {idx+1}/{total}...")
                text = run_tesseract_ocr(img, lang=ocr_lang, output_type="txt")
                all_text.append(f"--- PAGINA {idx+1} ---\n\n{text}\n")
            out_p.write_text("\n".join(all_text), encoding="utf-8")

        # 6. IMAGES (TIFF, PNG, JPG, WEBP)
        elif fmt in ("tiff", "tif"):
            first = images[0]
            rest = images[1:]
            first.save(out_p, format="TIFF", save_all=True, append_images=rest)
        elif fmt in ("jpg", "jpeg", "png", "webp"):
            if len(images) == 1:
                images[0].convert("RGB" if fmt in ("jpg", "jpeg") else "RGBA").save(out_p)
            else:
                stem = out_p.stem
                parent = out_p.parent
                suffix = out_p.suffix
                for idx, img in enumerate(images):
                    page_path = parent / f"{stem}_{idx+1:02d}{suffix}"
                    img.convert("RGB" if fmt in ("jpg", "jpeg") else "RGBA").save(page_path)

        if progress_callback:
            progress_callback(100, "Esportazione completata con successo!")
        return True

    except Exception as exc:
        logger.error("Errore durante l'esportazione: %s", exc, exc_info=True)
        return False
