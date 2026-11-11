# 🤖 Artificial Intelligence Credits (AI Credits)

This project, **ScannerPan**, was designed, architected, developed, and optimized with the advanced assistance of Artificial Intelligence.

---

## 🧠 AI Agent Platform & Models

* **AI Agent Platform:** **Antigravity** (Google DeepMind - Advanced Agentic Coding)
* **Core Foundation Model:** **Google Gemini 2.5 Pro**
* **Operating Environment:** Linux Ubuntu x86_64 / KDE Plasma / Wine Environment
* **Human Creator & System Architect:** **Marco Panista** (`mr-pan73` / `mrpan-group`)
* **GitLab Repository:** [https://gitlab.com/mrpan-group/scannerpan](https://gitlab.com/mrpan-group/scannerpan)

---

## 🛠️ Key Architectural & Technical AI Contributions

The AI actively authored the system architecture, algorithms, user interface, hardware abstraction, and deployment packaging:

1. **Computer Vision & Image Processing (`cv_detector.py`, `merger.py`):**
   * Automatic document border detection and smart cropping to eliminate black/empty scanner margins.
   * Multi-subject segmentation to independently crop and extract multiple receipts, photos, or business cards placed simultaneously on the flatbed glass.
   * Deskew angle estimation and rotation correction based on probabilistic Hough line transformation.
   * Front & back duplex merge wizard (side-by-side or stacked top-to-bottom) with DPI normalization.

2. **Native Graphical User Interface (`ui/`):**
   * Built from scratch in **PyQt6** following **KDE Plasma (Breeze Light & Dark)** human interface design guidelines.
   * System theme detection for both Linux (`kreadconfig6`, `freedesktop portal`) and Windows 11 (`winreg` - `AppsUseLightTheme`).
   * Responsive interactive canvas with smooth pan/zoom, non-destructive cropping, and complete history undo/redo (`Ctrl+Z` / `Ctrl+Y`).
   * Multi-subject visual picker with thumbnail cards and selective saving.

3. **Hardware Engine & Network Scanning (`hardware/sane_engine.py`):**
   * SANE CLI wrapper (`scanimage`) and network **eSCL / AirScan** protocol support (tested with Brother MFC-1910W).
   * Fully functional mock virtual scanner engine for offline and CI/CD testing.

4. **High-Performance OCR Pipeline (`ocr_engine.py`, `ocr_exporter.py`):**
   * Unified single-pass extraction for words, bounding boxes, and text, reducing per-page OCR latency by ~10x (~0.19s/page).
   * Smart downscaled grayscale preprocessing (1800px) and performance flag injection (`--dpi 300`, `-c tessedit_do_invert=0`).
   * Multi-format document export: Searchable PDF, Microsoft Word (`.docx`), OpenDocument (`.odt`), Rich Text (`.rtf`), Plain Text (`.txt`), and high-res image sets.

5. **Cross-Platform Release Engineering & CI/CD:**
   * Automated Debian/Ubuntu `.deb` package build (`build_deb.sh`).
   * Single-file standalone Windows 11 executable build (`ScannerPan.exe`) via PyInstaller and Wine with bundled ICU libraries.
   * Automated local installation script (`install_local.sh`) and continuous GitLab monorepo synchronization.

---

## 📅 Development History with AI

| Date | Release | Key AI Milestones |
| :--- | :---: | :--- |
| **Nov 2026** | **v1.0.0** | Initial architecture, KDE Breeze UI, SANE/AirScan hardware driver, OpenCV CV pipeline, Debian `.deb` packaging. |
| **Nov 2026** | **v1.0.1** | Native Windows 11 standalone executable (`.exe`), Windows registry dark mode detection, ICU DLL bundle, PyInstaller spec. |
| **Nov 2026** | **v1.0.2** | 10x faster single-pass OCR pipeline, graceful Tesseract absence handling, automated local install script (`install_local.sh`). |
