# 🤖 Riferimenti Intelligenza Artificiale (AI Credits)

Questo progetto, **ScannerPan**, è stato progettato, sviluppato e ottimizzato con il supporto avanzato dell'Intelligenza Artificiale.

---

## 🧠 Modello e Strumenti IA Utilizzati

* **Assistente Agente IA:** **Antigravity** (Google DeepMind - Advanced Agentic Coding)
* **Modello Linguistico di Riferimento:** **Google Gemini 2.5 Pro**
* **Ambiente Operativo:** Linux Ubuntu x86_64 / KDE Plasma / Wine Environment
* **Sviluppatore Umano & System Architect:** **Marco Panista** (`mr-pan73` / `mrpan-group`)
* **Repository GitLab:** [https://gitlab.com/mrpan-group/scannerpan](https://gitlab.com/mrpan-group/scannerpan)

---

## 🛠️ Contributi Specifici dell'Intelligenza Artificiale

L'Intelligenza Artificiale ha partecipato attivamente alla concezione dell'architettura software, alla scrittura del codice sorgente, al refactoring, al debug e al packaging multipiattaforma:

1. **Computer Vision & Elaborazione Immagini (`cv_detector.py`, `merger.py`):**
   * Rilevamento automatico dei bordi dei documenti e rimozione intelligente dei margini vuoti o neri del piano dello scanner.
   * Segmentazione automatica multi-soggetto per il ritaglio di scontrini multipli, biglietti da visita o fotografie disposti simultaneamente sul vetro dello scanner.
   * Algoritmo di raddrizzamento dell'inclinazione (*Deskew*) basato sulla trasformata di Hough probabilistica con stima accurata dell'angolo di rotazione.
   * Composizione e accorpamento fronte/retro (affiancato o sovrapposto) con bilanciamento DPI.

2. **Interfaccia Grafica e Integrazione Desktop (`ui/`):**
   * Sviluppo completo dell'interfaccia grafica in **PyQt6** con aderenza rigorosa alle linee guida visive **KDE Plasma (Breeze Light e Breeze Dark)**.
   * Sistema di rilevamento automatico del tema di sistema su Linux (`kreadconfig6`, `portal`) e su Windows 11 (`winreg` - `AppsUseLightTheme`).
   * Canvas di visualizzazione reattivo con supporto a zoom fluido, rotazione, ritaglio interattivo e cronologia completa delle modifiche (*Undo/Redo* con `Ctrl+Z` / `Ctrl+Y`).
   * Procedura guidata interattiva Fronte/Retro (*Duplex Wizard*) e dialogo di scelta dei soggetti multipli con anteprime in miniatura.

3. **Integrazione Hardware Scanner (`hardware/sane_engine.py`):**
   * Driver e parser per l'interazione con **SANE** (`scanimage`), protocolli di rete **eSCL / AirScan** e scanner USB (con supporto specifico e testato per stampanti multifunzione Brother serie MFC-1910W).
   * Motore di simulazione (*Mock Scanner*) per test e sviluppo anche in assenza di periferiche fisiche collegate.

4. **Ottimizzazione delle Prestazioni OCR (`ocr_engine.py`, `ocr_exporter.py`):**
   * Riconfigurazione della pipeline Tesseract per ridurre i tempi di elaborazione da oltre 2 secondi a meno di 0.2 secondi per pagina (~10x più veloce) tramite:
     * Singola passata unificata per testo e coordinate TSV.
     * Preprocessing e ridimensionamento a scala di grigi ottimizzata (1800px).
     * Iniezione dei parametri di accelerazione `--dpi 300` e `-c tessedit_do_invert=0`.
   * Esportazione multi-formato: Searchable PDF, Microsoft Word (`.docx`), OpenDocument (`.odt`), Rich Text (`.rtf`), Plain Text (`.txt`) e immagini ad alta definizione.

5. **Ingegneria di Packaging & CI/CD:**
   * Script e specifica per la creazione del pacchetto nativo Debian/Ubuntu [`.deb`](uploads/scannerpan_1.0.0_amd64.deb).
   * Script e ambiente PyInstaller/Wine per la generazione del binario standalone a 64-bit per Windows 11 [`ScannerPan.exe`](https://gitlab.com/api/v4/projects/88754086/packages/generic/scannerpan/1.0.0/ScannerPan.exe).
   * Script di automazione per il deploy continuo e la sincronizzazione con il monorepo GitLab `mrpan-group/MrPan-project`.

---

## 📅 Cronologia di Sviluppo IA

| Data | Versione | Interventi IA Principali |
| :--- | :---: | :--- |
| **Novembre 2026** | **v1.0.0** | Architettura iniziale, interfaccia KDE Breeze, integrazione SANE/AirScan, Computer Vision con OpenCV, packaging Debian `.deb`. |
| **Novembre 2026** | **v1.0.1** | Supporto nativo Windows 11 (.exe standalone), integrazione Registro Windows per Dark Mode, bundle DLL ICU, spec PyInstaller. |
| **Novembre 2026** | **v1.0.2** | Ottimizzazione pipeline OCR (10x più veloce a singola passata), gestione trasparente in assenza di Tesseract, script di installazione locale automatica `install_local.sh`. |
