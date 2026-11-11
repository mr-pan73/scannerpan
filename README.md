# 🖨️ ScannerPan

**ScannerPan** è un'applicazione moderna e completa per la gestione di scanner, scansioni avanzate e OCR, progettata per Linux (ambiente desktop **KDE Plasma**) e nativamente compatibile con **Windows 11 / Windows 10 (64-bit)**.

---

## 🪟 Download per Windows 11 / Windows 10 (64-bit)

È disponibile l'eseguibile standalone nativo precompilato (senza necessità di installare Python o dipendenze esterne):

* 🚀 **Download Diretto Eseguibile (.exe):**
  [ScannerPan.exe](https://gitlab.com/api/v4/projects/88754086/packages/generic/scannerpan/1.0.0/ScannerPan.exe) *(124 MB)*
* 📦 **Download Archivio (.zip):**
  [ScannerPan_v1.0.0_Windows_x64.zip](https://gitlab.com/api/v4/projects/88754086/packages/generic/scannerpan/1.0.0/ScannerPan_v1.0.0_Windows_x64.zip)

### Caratteristiche su Windows 11:
- **Eseguibile Standalone unico:** basta scaricarlo e fare doppio clic.
- **Rilevamento automatico Tema di Windows 11:** si adatta istantaneamente a Modalità Scura o Chiara di sistema.
- **Supporto OCR Tesseract:** rileva automaticamente `tesseract.exe` nelle cartelle standard (es. `C:\Program Files\Tesseract-OCR`).
- **Icona applicazione ad alta risoluzione:** integrata nel file `.exe` (fino a 256x256 con supporto HiDPI).

---

## 📥 Download Pacchetto Debian / Ubuntu (.deb)

Puoi scaricare il pacchetto precompilato direttamente con `wget` o `curl` tramite il Package Registry ufficiale di GitLab (privo di rate limit):

```bash
# Download con wget
wget "https://gitlab.com/api/v4/projects/88754086/packages/generic/scannerpan/1.0.0/scannerpan_1.0.0_amd64.deb" -O scannerpan_1.0.0_amd64.deb

# Oppure con curl
curl -L "https://gitlab.com/api/v4/projects/88754086/packages/generic/scannerpan/1.0.0/scannerpan_1.0.0_amd64.deb" -o scannerpan_1.0.0_amd64.deb
```

* 📦 **Release Ufficiale GitLab:** [https://gitlab.com/mrpan-group/scannerpan/-/releases/v1.0.0](https://gitlab.com/mrpan-group/scannerpan/-/releases/v1.0.0)
* 📂 **File nel repository:** [uploads/scannerpan_1.0.0_amd64.deb](uploads/scannerpan_1.0.0_amd64.deb)

---

## 🚀 Installazione su Ubuntu / Debian

Dopo aver scaricato il file `.deb`, installalo con:

```bash
sudo dpkg -i scannerpan_1.0.0_amd64.deb
sudo apt-get update && sudo apt-get install -f -y
```

Una volta installato, puoi avviare ScannerPan dal menu applicazioni di KDE (sezione *Grafica* / *Utility*) oppure digitando da terminale:
```bash
scannerpan
```

---

## ✨ Funzionalità Principali

* **Compatibilità Hardware Nativa:**
  * Rilevamento automatico di scanner USB e di rete SANE e eSCL/AirScan (es. Brother MFC-1910W e compatibili).
* **Supporto Sorgenti di Scansione:**
  * **Piano Fisso (Flatbed):** per documenti singoli, foto o libri.
  * **Alimentatore Automatico (ADF):** scansione continua multi-pagina a fascicolo.
  * **Procedura Guidata Fronte / Retro (Duplex Wizard):** accorpamento automatico in un unico documento o composizione affiancata (Side-by-Side / Top-Bottom).
* **Scansione Rapida di Anteprima:**
  * Anteprima veloce a 100 DPI per posizionamento e verifica inquadratura.
  * Selezionando successivamente *Scansiona Ora*, la scansione ad alta risoluzione rimpiazza automaticamente l'anteprima.
* **Computer Vision & Riconoscimento Automatico (OpenCV):**
  * **Rilevamento Automatico Bordi e Contorni:** rileva i confini del foglio ed elimina i bordi neri o vuoti del piano dello scanner.
  * **Riconoscimento Multi-Soggetto:** individua automaticamente scontrini, fotografie multiple o biglietti da visita disposti sul vetro, consentendo di selezionare cosa salvare.
  * **Raddrizza Inclinazione (Deskew):** algoritmo basato sulla trasformata di Hough per allineare documenti storti.
  * **Miglioramento Contrasto & Sbiancamento Sfondo:** ottimizza la leggibilità dei testi.
  * **Funzione Annulla / Ripristina (Undo/Redo):** cronologia completa delle modifiche per ogni pagina (Ctrl+Z / Ctrl+Y).
* **Esportazione Multi-Formato & OCR:**
  * **PDF Ricercabile:** con layer testuale incorporato tramite Tesseract OCR multilingua (Italiano, Inglese, Tedesco, Francese, Spagnolo).
  * **Documenti Editabili:** LibreOffice Writer (`.odt`), Microsoft Word (`.docx`), Rich Text (`.rtf`), Testo semplice (`.txt`).
  * **Formati Grafici:** PNG, JPEG, TIFF multi-pagina, WebP.

---

## 🛠️ Compilazione dai Sorgenti

### Su Linux (Pacchetto .deb)
```bash
git clone https://gitlab.com/mrpan-group/scannerpan.git
cd scannerpan
./build_deb.sh
```

### Su Windows (Eseguibile .exe)
Esegui lo script batch incluso con un doppio clic o da terminale Windows:
```cmd
build_exe.bat
```
oppure manualmente tramite PyInstaller:
```cmd
python -m PyInstaller --clean scannerpan.spec
```
L'eseguibile `.exe` verrà generato nella cartella `dist\ScannerPan.exe`.

---

## 🤖 Development & Artificial Intelligence (AI Credits)

This project is designed, architected, and continuously developed with the assistance of Artificial Intelligence:

* **AI Agent Platform:** **Antigravity** (Google DeepMind - Advanced Agentic Coding)
* **Core Foundation Model:** **Google Gemini 2.5 Pro**
* **Human Creator & System Architect:** **Marco Panista** (`mr-pan73` / `mrpan-group`)
* **Detailed Documentation:** see [AI_CREDITS.md](AI_CREDITS.md) for full architectural breakdown and AI-authored subsystems.

### Key AI Contributions:
1. **Computer Vision (OpenCV):** Automatic border detection, black edge suppression, Hough-based deskewing, and intelligent multi-subject segmentation (receipts and photos).
2. **User Interface (PyQt6):** Full compliance with KDE Breeze design system (Light/Dark), Windows 11 registry theme detection (`AppsUseLightTheme`), and responsive non-destructive undo/redo canvas.
3. **Hardware & OCR Engines:** SANE / eSCL AirScan protocol integration and high-speed single-pass OCR pipeline (~0.19s/page).
4. **Cross-Platform Packaging:** Standalone packages for Debian/Ubuntu (`.deb`) and 64-bit Windows 11 (`ScannerPan.exe`).


