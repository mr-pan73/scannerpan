"""ScannerPan - Sistema Professionale di Scansione, Elaborazione e OCR per Scanner Brother e SANE."""

__version__ = "1.0.0"
__author__ = "ScannerPan Team (mrpan-group)"

from .hardware.sane_engine import (
    SaneEngine,
    ScannerDevice,
    ScanOptions,
    ScanResult,
    ScanSource,
    ScanMode,
)
from .processing.cv_detector import (
    CVDetector,
    DetectedSubject,
)
from .processing.ocr_engine import (
    OCREngine,
    OCRResult,
    OCRWord,
)
from .processing.merger import (
    DuplexMerger,
    LayoutMode,
    ImageFormat,
)

__all__ = [
    "SaneEngine",
    "ScannerDevice",
    "ScanOptions",
    "ScanResult",
    "ScanSource",
    "ScanMode",
    "CVDetector",
    "DetectedSubject",
    "OCREngine",
    "OCRResult",
    "OCRWord",
    "DuplexMerger",
    "LayoutMode",
    "ImageFormat",
]
