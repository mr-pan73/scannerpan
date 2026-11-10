# 🖨️ ScannerPan

**ScannerPan** è un'applicazione moderna e completa per la gestione di scanner, scansioni avanzate e OCR, progettata per Linux con piena integrazione visiva e tematica per l'ambiente desktop **KDE Plasma (Breeze)**.

---

## 📥 Download Diretto Pacchetto Debian (.deb)

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

## 🛠️ Compilazione del Pacchetto .deb dai Sorgenti

Se desideri compilare il pacchetto `.deb` autonomamente:

```bash
git clone https://gitlab.com/mrpan-group/scannerpan.git
cd scannerpan
./build_deb.sh
```

Il pacchetto generato sarà disponibile in `uploads/scannerpan_1.0.0_amd64.deb` e nella directory principale.
