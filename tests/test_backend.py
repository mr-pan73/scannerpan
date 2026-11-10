"""ScannerPan - Test Suite per i Moduli di Backend.

Verifica completa di:
- Hardware SaneEngine (rilevamento scanner, Brother MFC-1910W, mock mode, ADF batch)
- CVDetector (rilevamento contorni foglio, raddrizzamento prospettico, multi-soggetto, pulizia sfondo)
- OCREngine (Tesseract ita/deu/eng, esportazione PDF ricercabile, DOCX, ODT, RTF, TXT)
- DuplexMerger (composizione Fronte/Retro side-by-side, vertical, ID Card, foglio A4, export PNG/JPG/TIFF/WebP/PDF, interleaving)
"""

import os
import shutil
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw

from scannerpan import (
    CVDetector,
    DuplexMerger,
    ImageFormat,
    LayoutMode,
    OCREngine,
    SaneEngine,
    ScanOptions,
    ScanResult,
)


class TestSaneEngine(unittest.TestCase):
    """Test per sane_engine.py"""

    def setUp(self):
        self.engine = SaneEngine(allow_mock_fallback=True)

    def test_list_devices(self):
        devs = self.engine.list_devices(filter_webcams=True, timeout=10)
        self.assertGreaterEqual(len(devs), 1)
        # Verifica che gli oggetti siano di tipo ScannerDevice
        for d in devs:
            self.assertTrue(hasattr(d, "name"))
            self.assertTrue(hasattr(d, "vendor"))
            self.assertTrue(hasattr(d, "model"))
            self.assertFalse(d.is_webcam)

    def test_brother_options_query(self):
        opts = self.engine.get_device_options("airscan:w1:Brother MFC-1910W series")
        self.assertIn("Flatbed", opts.get("sources", []))
        self.assertIn(300, opts.get("resolutions", []))

    def test_mock_single_scan(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_dir = Path(tmp_dir)
            res = self.engine.scan(
                ScanOptions(
                    device="mock:Brother-MFC-1910W-Virtual",
                    source="Flatbed",
                    mode="Color",
                    resolution=200,
                    output_dir=out_dir,
                )
            )
            self.assertTrue(res.success)
            self.assertEqual(res.page_count, 1)
            self.assertTrue(res.primary_image.exists())
            self.assertGreater(res.primary_image.stat().st_size, 0)

    def test_mock_adf_batch_scan(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_dir = Path(tmp_dir)
            res = self.engine.scan(
                ScanOptions(
                    device="mock:Brother-MFC-1910W-Virtual",
                    source="ADF",
                    adf_batch=True,
                    resolution=150,
                    output_dir=out_dir,
                )
            )
            self.assertTrue(res.success)
            self.assertEqual(res.page_count, 2)
            for img_path in res.images:
                self.assertTrue(img_path.exists())


class TestCVDetector(unittest.TestCase):
    """Test per cv_detector.py"""

    def setUp(self):
        self.detector = CVDetector()

    def test_order_points_and_four_point_transform(self):
        # Immagine di prova quadrata
        img = np.zeros((300, 300, 3), dtype=np.uint8)
        cv2.rectangle(img, (20, 20), (280, 280), (200, 100, 50), -1)

        pts = np.array([[20, 20], [280, 20], [280, 280], [20, 280]], dtype="float32")
        ordered = self.detector.order_points(pts)
        self.assertEqual(ordered.shape, (4, 2))

        warped = self.detector.four_point_transform(img, pts)
        self.assertGreater(warped.shape[0], 0)
        self.assertGreater(warped.shape[1], 0)

    def test_multi_subject_detection(self):
        # Simulazione piano scanner con 3 fotografie/scontrini
        canvas = np.full((1200, 900, 3), 252, dtype=np.uint8)
        # Oggetto 1
        cv2.rectangle(canvas, (80, 80), (380, 480), (30, 40, 120), -1)
        # Oggetto 2
        cv2.rectangle(canvas, (480, 120), (820, 520), (120, 50, 30), -1)
        # Oggetto 3
        cv2.rectangle(canvas, (150, 650), (750, 1100), (40, 120, 50), -1)

        subjects = self.detector.detect_multiple_subjects(canvas, min_area_ratio=0.02)
        self.assertEqual(len(subjects), 3)
        for s in subjects:
            self.assertGreater(s.bbox[2], 50)
            self.assertGreater(s.bbox[3], 50)
            self.assertIsInstance(s.pil_image, Image.Image)

    def test_enhance_contrast_and_clean_background(self):
        img = np.full((200, 200, 3), 180, dtype=np.uint8)
        cv2.putText(img, "TEST", (30, 100), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (20, 20, 20), 3)

        clahe_res = self.detector.enhance_contrast(img, method="clahe")
        self.assertEqual(clahe_res.shape, img.shape)

        unsharp_res = self.detector.enhance_contrast(img, method="unsharp")
        self.assertEqual(unsharp_res.shape, img.shape)

        clean_doc = self.detector.clean_background(img, mode="document")
        self.assertEqual(clean_doc.shape, img.shape)

        clean_bw = self.detector.clean_background(img, mode="bw")
        self.assertEqual(len(clean_bw.shape), 2)  # Monocromatico


class TestOCREngine(unittest.TestCase):
    """Test per ocr_engine.py"""

    def setUp(self):
        self.engine = OCREngine()
        self.tmp_dir = tempfile.mkdtemp()

        # Genera immagine sintetica con testo chiaro
        self.img_path = Path(self.tmp_dir) / "test_ocr_input.png"
        img = Image.new("RGB", (900, 250), (255, 255, 255))
        d = ImageDraw.Draw(img)
        d.text((30, 40), "ScannerPan Collaudo OCR", fill=(0, 0, 0))
        d.text((30, 100), "Riconoscimento caratteri per italiano e inglese 2026", fill=(0, 0, 0))
        d.text((30, 160), "Qualità documenti e conformità aziendale garantita", fill=(0, 0, 0))
        img.save(str(self.img_path))

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_ocr_recognition(self):
        res = self.engine.recognize(self.img_path, language="ita+eng")
        self.assertTrue(res.text)
        self.assertIn("ScannerPan", res.text)
        self.assertGreater(res.confidence, 50.0)
        self.assertGreater(len(res.words), 0)

    def test_exports_all_formats(self):
        res = self.engine.recognize(self.img_path, language="ita")

        pdf_path = self.engine.export(res, "pdf", Path(self.tmp_dir) / "output.pdf")
        self.assertTrue(pdf_path.exists())
        self.assertGreater(pdf_path.stat().st_size, 0)

        docx_path = self.engine.export(res, "docx", Path(self.tmp_dir) / "output.docx")
        self.assertTrue(docx_path.exists())
        self.assertGreater(docx_path.stat().st_size, 0)

        odt_path = self.engine.export(res, "odt", Path(self.tmp_dir) / "output.odt")
        self.assertTrue(odt_path.exists())
        self.assertGreater(odt_path.stat().st_size, 0)

        rtf_path = self.engine.export(res, "rtf", Path(self.tmp_dir) / "output.rtf")
        self.assertTrue(rtf_path.exists())
        self.assertGreater(rtf_path.stat().st_size, 0)

        txt_path = self.engine.export(res, "txt", Path(self.tmp_dir) / "output.txt")
        self.assertTrue(txt_path.exists())
        self.assertGreater(txt_path.stat().st_size, 0)


class TestDuplexMerger(unittest.TestCase):
    """Test per merger.py"""

    def setUp(self):
        self.merger = DuplexMerger()
        self.tmp_dir = tempfile.mkdtemp()

        self.front = Image.new("RGB", (400, 250), (230, 240, 255))
        d1 = ImageDraw.Draw(self.front)
        d1.text((30, 30), "CARTA IDENTITA FRONTE", fill=(0, 0, 0))

        self.back = Image.new("RGB", (400, 250), (255, 240, 230))
        d2 = ImageDraw.Draw(self.back)
        d2.text((30, 30), "CARTA IDENTITA RETRO", fill=(0, 0, 0))

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_interleave_duplex(self):
        fronts = ["F1", "F2", "F3"]
        backs_inverted = ["R3", "R2", "R1"]
        res = self.merger.interleave_duplex(fronts, backs_inverted, reverse_back=True)
        self.assertEqual(res, ["F1", "R1", "F2", "R2", "F3", "R3"])

    def test_composite_layouts(self):
        comp_side = self.merger.create_composite_image(self.front, self.back, layout=LayoutMode.SIDE_BY_SIDE)
        self.assertGreater(comp_side.width, comp_side.height)

        comp_vert = self.merger.create_composite_image(self.front, self.back, layout=LayoutMode.VERTICAL)
        self.assertGreater(comp_vert.height, comp_vert.width)

        comp_id = self.merger.create_composite_image(self.front, self.back, layout=LayoutMode.ID_CARD)
        self.assertIsInstance(comp_id, Image.Image)

        comp_a4 = self.merger.create_composite_image(self.front, self.back, layout=LayoutMode.ID_CARD_A4)
        self.assertIsInstance(comp_a4, Image.Image)

    def test_image_formats_export(self):
        for fmt in [ImageFormat.PNG, ImageFormat.JPEG, ImageFormat.WEBP, ImageFormat.TIFF]:
            out_p = self.merger.export_image(self.front, Path(self.tmp_dir) / f"test.{fmt.value}", fmt)
            self.assertTrue(out_p.exists())
            self.assertGreater(out_p.stat().st_size, 0)

    def test_merge_duplex_to_pdf(self):
        pdf_out = self.merger.merge_duplex_to_pdf(
            [self.front],
            [self.back],
            Path(self.tmp_dir) / "duplex_merged.pdf",
            reverse_back=False,
        )
        self.assertTrue(pdf_out.exists())
        self.assertGreater(pdf_out.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
