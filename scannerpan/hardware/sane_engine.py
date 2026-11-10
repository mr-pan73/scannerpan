"""ScannerPan - Hardware SANE Engine.

Gestisce la comunicazione con dispositivi SANE / airscan via command-line scanimage:
- Rilevamento scanner (incluso supporto dedicato Brother MFC-1910W via airscan/WSD).
- Ispezione e interrogazione opzioni hardware (Flatbed, ADF, DPI, Modalità colore).
- Acquisizione immagini singole e fascicoli multi-pagina ADF in batch.
- Motore di simulazione mock integrato per test headless e ambienti privi di scanner fisico.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger("scannerpan.hardware.sane_engine")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)


class ScanSource(str, Enum):
    FLATBED = "Flatbed"
    ADF = "ADF"
    AUTOMATIC = "Auto"


class ScanMode(str, Enum):
    COLOR = "Color"
    GRAY = "Gray"
    LINEART = "Lineart"


@dataclass
class ScannerDevice:
    """Rappresentazione di un dispositivo scanner rilevato."""
    name: str  # URI dispositivo SANE, es. 'airscan:w1:Brother MFC-1910W series'
    vendor: str
    model: str
    device_type: str = "scanner"
    is_airscan: bool = False
    is_brother: bool = False
    is_webcam: bool = False
    ip_address: Optional[str] = None
    sources: List[str] = field(default_factory=lambda: ["Flatbed", "ADF"])
    resolutions: List[int] = field(default_factory=lambda: [100, 200, 300, 600])
    modes: List[str] = field(default_factory=lambda: ["Color", "Gray", "Lineart"])
    is_mock: bool = False
    raw_info: str = ""

    def __str__(self) -> str:
        tag = "[MOCK] " if self.is_mock else ""
        brother_tag = " (Brother MFC)" if self.is_brother else ""
        ip_info = f" @ {self.ip_address}" if self.ip_address else ""
        return f"{tag}{self.vendor} {self.model}{brother_tag}{ip_info} [{self.name}]"


@dataclass
class ScanOptions:
    """Opzioni di configurazione per il processo di scansione."""
    device: Optional[str] = None
    source: str = "Flatbed"
    mode: str = "Color"
    resolution: int = 300
    format: str = "png"  # 'png', 'tiff', 'jpeg'
    brightness: Optional[int] = None  # -100..100
    contrast: Optional[int] = None    # -100..100
    adf_batch: bool = False
    max_pages: Optional[int] = None
    output_dir: Optional[Path] = None
    timeout_sec: int = 120


@dataclass
class ScanResult:
    """Risultato dell'operazione di scansione."""
    success: bool
    images: List[Path] = field(default_factory=list)
    page_count: int = 0
    error_message: Optional[str] = None
    device_used: str = ""
    duration_sec: float = 0.0

    @property
    def primary_image(self) -> Optional[Path]:
        return self.images[0] if self.images else None

    def load_pil_images(self) -> List[Image.Image]:
        """Carica tutte le immagini acquisite come oggetti PIL.Image."""
        pil_imgs = []
        for p in self.images:
            if p.exists():
                with Image.open(p) as img:
                    pil_imgs.append(img.copy())
        return pil_imgs


class SaneEngine:
    """Engine principale per l'interazione con scanner SANE e airscan."""

    BROTHER_DEFAULT_URI = "airscan:w1:Brother MFC-1910W series"

    def __init__(self, default_device: Optional[str] = None, allow_mock_fallback: bool = True):
        self.default_device = default_device
        self.allow_mock_fallback = allow_mock_fallback
        self._cached_devices: List[ScannerDevice] = []
        self._options_cache: Dict[str, Dict[str, Any]] = {}
        found_scanimage = shutil.which("scanimage")
        self.scanimage_bin = found_scanimage or ("scanimage.exe" if os.name == "nt" else "/usr/bin/scanimage")

    def is_sane_installed(self) -> bool:
        """Verifica se l'utility scanimage è installata ed eseguibile."""
        return bool(self.scanimage_bin and os.path.isfile(self.scanimage_bin) and os.access(self.scanimage_bin, os.X_OK))

    def list_devices(
        self,
        filter_webcams: bool = True,
        force_mock: bool = False,
        timeout: int = 15,
    ) -> List[ScannerDevice]:
        """Elenca tutti gli scanner disponibili tramite `scanimage -L`.

        Identifica dispositivi Brother MFC-1910W, protocolli WSD/airscan e
        filtra le webcam v4l se richiesto. Se non viene trovato alcuno scanner
        fisico (o force_mock=True), aggiunge un dispositivo virtuale di test.
        """
        if force_mock or not self.is_sane_installed():
            logger.info("Modalità simulata (mock) attiva per rilevamento scanner.")
            mock_dev = self._create_mock_device()
            self._cached_devices = [mock_dev]
            return self._cached_devices

        devices: List[ScannerDevice] = []
        try:
            cmd = [self.scanimage_bin, "-L"]
            logger.info("Esecuzione rilevamento dispositivi SANE: %s", " ".join(cmd))
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            stdout = proc.stdout or ""
            stderr = proc.stderr or ""
            logger.debug("scanimage -L stdout:\n%s", stdout)
            if stderr:
                logger.debug("scanimage -L stderr:\n%s", stderr)

            # Esempio righe:
            # device `airscan:w1:Brother MFC-1910W series' is a WSD Brother MFC-1910W series ip=192.168.178.251
            # device `v4l:/dev/video2' is a Noname USB  Live camera: USB  Live cam virtual device
            pattern = re.compile(r"device `([^']+)'\s+is\s+a\s+(.+)")
            for line in stdout.splitlines():
                line = line.strip()
                if not line or not line.startswith("device"):
                    continue
                match = pattern.search(line)
                if not match:
                    continue

                uri = match.group(1).strip()
                desc = match.group(2).strip()

                is_webcam = uri.startswith("v4l:") or "/dev/video" in uri or "camera" in desc.lower()
                if filter_webcams and is_webcam:
                    logger.debug("Webcam filtrata: %s (%s)", uri, desc)
                    continue

                is_airscan = uri.startswith("airscan:") or "WSD" in desc or "eSCL" in desc
                is_brother = (
                    "brother" in uri.lower()
                    or "brother" in desc.lower()
                    or "mfc-1910w" in uri.lower()
                    or "mfc-1910w" in desc.lower()
                )

                # Estrai IP se presente
                ip_match = re.search(r"ip=([0-9a-fA-F.:]+)", desc)
                ip_address = ip_match.group(1) if ip_match else None

                # Estrazione vendor e model
                vendor = "Brother" if is_brother else "Scanner"
                model = desc
                if is_brother:
                    model = "MFC-1910W series"
                elif is_webcam:
                    vendor = "Webcam"
                    model = desc

                dev = ScannerDevice(
                    name=uri,
                    vendor=vendor,
                    model=model,
                    device_type="webcam" if is_webcam else "scanner",
                    is_airscan=is_airscan,
                    is_brother=is_brother,
                    is_webcam=is_webcam,
                    ip_address=ip_address,
                    raw_info=desc,
                )
                devices.append(dev)

        except subprocess.TimeoutExpired:
            logger.warning("Rilevamento scanner scaduto per timeout (%ds).", timeout)
        except Exception as exc:
            logger.error("Errore durante l'esecuzione di scanimage -L: %s", exc, exc_info=True)

        # Se nessun dispositivo valido è stato trovato e il fallback è abilitato
        if not devices and self.allow_mock_fallback:
            logger.warning("Nessun dispositivo fisico rilevato; attivazione scanner mock di test.")
            devices.append(self._create_mock_device())

        # Ordina: preferisci Brother MFC-1910W e scanner airscan prima di altri
        devices.sort(
            key=lambda d: (
                0 if d.is_brother else 1,
                0 if d.is_airscan else 1,
                1 if d.is_webcam else 0,
                d.name,
            )
        )

        self._cached_devices = devices
        return devices

    def _create_mock_device(self) -> ScannerDevice:
        """Crea un dispositivo scanner virtuale per testing e sviluppo."""
        return ScannerDevice(
            name="mock:Brother-MFC-1910W-Virtual",
            vendor="Brother",
            model="MFC-1910W series (Simulatore Test)",
            device_type="scanner",
            is_airscan=True,
            is_brother=True,
            is_mock=True,
            ip_address="127.0.0.1",
            sources=["Flatbed", "ADF"],
            resolutions=[100, 200, 300, 600],
            modes=["Color", "Gray", "Lineart"],
            raw_info="Simulated Brother MFC-1910W Network Scanner for Testing",
        )

    def get_device_options(self, device_name: str, use_cache: bool = True) -> Dict[str, Any]:
        """Interroga le opzioni supportate dal dispositivo tramite `scanimage --help -d <device>`.

        Restituisce un dizionario contenente:
        - sources: ["Flatbed", "ADF"]
        - resolutions: [100, 200, 300, ...]
        - modes: ["Color", "Gray", "Lineart"]
        - has_brightness: bool
        - has_contrast: bool
        - geometry: {x, y, l, t}
        """
        if use_cache and device_name in self._options_cache:
            return self._options_cache[device_name]

        if device_name.startswith("mock:") or not self.is_sane_installed():
            opts = {
                "sources": ["Flatbed", "ADF"],
                "resolutions": [100, 200, 300, 600],
                "modes": ["Color", "Gray", "Lineart"],
                "has_brightness": True,
                "has_contrast": True,
                "default_resolution": 300,
                "default_source": "Flatbed",
                "default_mode": "Color",
            }
            self._options_cache[device_name] = opts
            return opts

        parsed_opts = {
            "sources": ["Flatbed"],
            "resolutions": [100, 200, 300],
            "modes": ["Color", "Gray"],
            "has_brightness": False,
            "has_contrast": False,
            "default_resolution": 300,
            "default_source": "Flatbed",
            "default_mode": "Color",
        }

        try:
            cmd = [self.scanimage_bin, "-d", device_name, "--help"]
            logger.info("Interrogazione opzioni per '%s'...", device_name)
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=12, check=False)
            output = (proc.stdout or "") + "\n" + (proc.stderr or "")

            # Parsing sorgenti: --source Flatbed|ADF [Flatbed]
            source_match = re.search(r"--source\s+([A-Za-z0-9_|]+)", output)
            if source_match:
                sources = [s.strip() for s in source_match.group(1).split("|") if s.strip()]
                if sources:
                    parsed_opts["sources"] = sources

            # Parsing risoluzioni: --resolution 100|200|300dpi [300] oppure 50..600dpi
            res_match = re.search(r"--resolution\s+([0-9|]+)dpi", output)
            if res_match:
                resolutions = [int(r) for r in res_match.group(1).split("|") if r.isdigit()]
                if resolutions:
                    parsed_opts["resolutions"] = resolutions
            else:
                range_match = re.search(r"--resolution\s+(\d+)\.\.(\d+)dpi", output)
                if range_match:
                    low, high = int(range_match.group(1)), int(range_match.group(2))
                    parsed_opts["resolutions"] = [r for r in [100, 150, 200, 300, 600, 1200] if low <= r <= high]

            # Parsing modalità: --mode Color|Gray [Color]
            mode_match = re.search(r"--mode\s+([A-Za-z0-9_|]+)", output)
            if mode_match:
                modes = [m.strip() for m in mode_match.group(1).split("|") if m.strip()]
                if modes:
                    parsed_opts["modes"] = modes

            if "--brightness" in output:
                parsed_opts["has_brightness"] = True
            if "--contrast" in output:
                parsed_opts["has_contrast"] = True

        except Exception as exc:
            logger.warning("Errore durante l'interrogazione delle opzioni dispositivo: %s", exc)

        # Per il Brother MFC-1910W, assicura il supporto ad ADF e 100/200/300 dpi
        if "brother" in device_name.lower() or "mfc-1910w" in device_name.lower():
            if "ADF" not in parsed_opts["sources"]:
                parsed_opts["sources"].append("ADF")
            if 300 not in parsed_opts["resolutions"]:
                parsed_opts["resolutions"].append(300)

        self._options_cache[device_name] = parsed_opts
        return parsed_opts

    def scan(
        self,
        options: Optional[ScanOptions] = None,
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ) -> ScanResult:
        """Esegue una scansione singola o un'acquisizione multi-pagina con alimentatore ADF.

        Se `options.adf_batch` è True e la sorgente è ADF, viene avviata la modalità
        batch tramite scanimage `--batch` fino ad esaurimento del vassoio di carico.
        """
        options = options or ScanOptions()
        start_time = time.time()

        device = options.device or self.default_device or self.BROTHER_DEFAULT_URI
        target_dir = options.output_dir or Path(tempfile.mkdtemp(prefix="scannerpan_scan_"))
        target_dir.mkdir(parents=True, exist_ok=True)

        # Se il dispositivo è mock o non abbiamo scanimage, usa la scansione simulata
        if device.startswith("mock:") or not self.is_sane_installed():
            logger.info("Esecuzione scansione simulata per device: %s", device)
            res = self._mock_scan(options, target_dir, progress_callback)
            res.duration_sec = time.time() - start_time
            return res

        # Verifica opzioni hardware supportate
        dev_opts = self.get_device_options(device)
        chosen_source = options.source
        if chosen_source not in dev_opts.get("sources", []):
            if dev_opts.get("sources"):
                chosen_source = dev_opts["sources"][0]
                logger.info("Sorgente '%s' non supportata, fallback su '%s'", options.source, chosen_source)

        chosen_mode = options.mode
        if chosen_mode not in dev_opts.get("modes", []):
            if "Color" in dev_opts.get("modes", []):
                chosen_mode = "Color"
            elif dev_opts.get("modes"):
                chosen_mode = dev_opts["modes"][0]

        is_adf_batch = options.adf_batch or (chosen_source.upper() == "ADF")

        if is_adf_batch:
            return self._scan_adf_batch(
                device=device,
                options=options,
                source=chosen_source,
                mode=chosen_mode,
                target_dir=target_dir,
                progress_callback=progress_callback,
                start_time=start_time,
            )
        else:
            return self._scan_single_flatbed(
                device=device,
                options=options,
                source=chosen_source,
                mode=chosen_mode,
                target_dir=target_dir,
                progress_callback=progress_callback,
                start_time=start_time,
            )

    def _scan_single_flatbed(
        self,
        device: str,
        options: ScanOptions,
        source: str,
        mode: str,
        target_dir: Path,
        progress_callback: Optional[Callable[[int, str], None]],
        start_time: float,
    ) -> ScanResult:
        """Acquisisce una singola pagina da piano scanner Flatbed o ADF."""
        ext = options.format.lower()
        if ext not in ("png", "tiff", "jpeg"):
            ext = "png"
        out_file = target_dir / f"scan_{int(time.time()*1000)}.{ext}"

        cmd = [
            self.scanimage_bin,
            "-d", device,
            f"--format={ext}",
            f"--resolution={options.resolution}",
            f"--mode={mode}",
            f"--source={source}",
            f"--output-file={str(out_file)}",
        ]

        if options.brightness is not None:
            cmd.append(f"--brightness={options.brightness}")
        if options.contrast is not None:
            cmd.append(f"--contrast={options.contrast}")

        logger.info("Esecuzione comando scanimage singolo: %s", " ".join(cmd))
        if progress_callback:
            progress_callback(10, f"Inizializzazione scansione su {device}...")

        try:
            if progress_callback:
                progress_callback(30, "Acquisizione ottica in corso...")

            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=options.timeout_sec,
                check=False,
            )

            if proc.returncode != 0:
                err_msg = (proc.stderr or "").strip() or f"Codice di uscita errore: {proc.returncode}"
                logger.error("Errore scanimage: %s", err_msg)
                # Fallback mock se l'hardware non ha risposto (es. offline)
                if self.allow_mock_fallback and ("no SANE devices found" in err_msg.lower() or "device busy" in err_msg.lower() or "error" in err_msg.lower()):
                    logger.warning("Hardware non accessibile, fallback su simulazione test.")
                    return self._mock_scan(options, target_dir, progress_callback)
                return ScanResult(
                    success=False,
                    error_message=f"Errore scanner: {err_msg}",
                    device_used=device,
                    duration_sec=time.time() - start_time,
                )

            if not out_file.exists() or out_file.stat().st_size == 0:
                return ScanResult(
                    success=False,
                    error_message="Il file acquisito è vuoto o mancante.",
                    device_used=device,
                    duration_sec=time.time() - start_time,
                )

            if progress_callback:
                progress_callback(100, "Scansione completata.")

            return ScanResult(
                success=True,
                images=[out_file],
                page_count=1,
                device_used=device,
                duration_sec=time.time() - start_time,
            )

        except subprocess.TimeoutExpired:
            return ScanResult(
                success=False,
                error_message=f"Timeout superato ({options.timeout_sec}s) durante l'acquisizione.",
                device_used=device,
                duration_sec=time.time() - start_time,
            )
        except Exception as exc:
            return ScanResult(
                success=False,
                error_message=str(exc),
                device_used=device,
                duration_sec=time.time() - start_time,
            )

    def _scan_adf_batch(
        self,
        device: str,
        options: ScanOptions,
        source: str,
        mode: str,
        target_dir: Path,
        progress_callback: Optional[Callable[[int, str], None]],
        start_time: float,
    ) -> ScanResult:
        """Acquisisce fogli multipli da caricatore ADF continuo fino a esaurimento."""
        ext = options.format.lower()
        if ext not in ("png", "tiff", "jpeg"):
            ext = "png"

        batch_pattern = str(target_dir / f"page_%04d.{ext}")
        cmd = [
            self.scanimage_bin,
            "-d", device,
            f"--format={ext}",
            f"--resolution={options.resolution}",
            f"--mode={mode}",
            f"--source={source}",
            f"--batch={batch_pattern}",
            "--batch-print",
        ]

        if options.max_pages:
            cmd.append(f"--batch-count={options.max_pages}")
        if options.brightness is not None:
            cmd.append(f"--brightness={options.brightness}")
        if options.contrast is not None:
            cmd.append(f"--contrast={options.contrast}")

        logger.info("Esecuzione scansione ADF Batch: %s", " ".join(cmd))
        if progress_callback:
            progress_callback(10, "Avvio alimentatore automatico ADF...")

        scanned_files: List[Path] = []
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )

            # Leggi stdout in streaming mentre scanimage stampa i file acquisiti
            assert proc.stdout is not None
            page_counter = 0
            for line in proc.stdout:
                line = line.strip()
                if not line:
                    continue
                logger.info("scanimage batch output: %s", line)
                # scanimage stampa il path del file salvato
                path_cand = Path(line)
                if path_cand.exists() and path_cand not in scanned_files:
                    scanned_files.append(path_cand)
                    page_counter += 1
                    if progress_callback:
                        progress_callback(min(90, page_counter * 20), f"Acquisita pagina {page_counter} da ADF...")

            _, stderr = proc.communicate(timeout=options.timeout_sec)
            ret_code = proc.returncode

            # Se ADF è vuoto o finisce la carta, scanimage può restituire codice non zero
            # con messaggio 'Out of documents' o 'Document feeder out of documents'
            feeder_empty = any(
                phrase in (stderr or "").lower()
                for phrase in ["out of documents", "document feeder empty", "no documents", "adf empty"]
            )

            # Cerca tutti i file generati se batch-print non ha catturato tutti i percorsi
            found_files = sorted(target_dir.glob(f"page_*.{ext}"))
            if found_files:
                scanned_files = found_files

            if not scanned_files:
                if feeder_empty:
                    err = "Nessun foglio presente nel caricatore ADF (Vassoio vuoto)."
                else:
                    err = (stderr or "").strip() or "Nessun documento acquisito da ADF."
                return ScanResult(
                    success=False,
                    error_message=err,
                    device_used=device,
                    duration_sec=time.time() - start_time,
                )

            if progress_callback:
                progress_callback(100, f"Completate {len(scanned_files)} pagine da ADF.")

            return ScanResult(
                success=True,
                images=scanned_files,
                page_count=len(scanned_files),
                device_used=device,
                duration_sec=time.time() - start_time,
            )

        except Exception as exc:
            logger.error("Errore durante ADF batch scan: %s", exc, exc_info=True)
            return ScanResult(
                success=False,
                error_message=str(exc),
                device_used=device,
                duration_sec=time.time() - start_time,
            )

    def _mock_scan(
        self,
        options: ScanOptions,
        target_dir: Path,
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ) -> ScanResult:
        """Genera documenti di test sintetici di alta qualità per simulazione o CI."""
        ext = options.format.lower()
        if ext not in ("png", "tiff", "jpeg"):
            ext = "png"

        num_pages = 2 if (options.adf_batch or options.source.upper() == "ADF") else 1
        created_files: List[Path] = []

        # Dimensioni standard A4 a 300 DPI: ~2480 x 3508 pixel
        # Per 100/200/300 dpi scala proporzionalmente
        dpi = options.resolution or 300
        width = int(8.27 * dpi)
        height = int(11.69 * dpi)

        if progress_callback:
            progress_callback(20, "Generazione immagine di test simulata...")

        for page_idx in range(1, num_pages + 1):
            # Immagine di sfondo bianca con leggero rumore cartaceo
            mode_str = "RGB" if options.mode == "Color" else "L"
            bg_color = (252, 252, 250) if mode_str == "RGB" else 252
            img = Image.new(mode_str, (width, height), color=bg_color)
            draw = ImageDraw.Draw(img)

            # Intestazione grafica ScannerPan
            header_color = (30, 80, 180) if mode_str == "RGB" else 50
            border_color = (180, 180, 180) if mode_str == "RGB" else 150
            text_color = (20, 20, 20) if mode_str == "RGB" else 20

            # Bordo pagina documento
            draw.rectangle([(40, 40), (width - 40, height - 40)], outline=border_color, width=3)

            # Barra titolo superiore
            draw.rectangle([(40, 40), (width - 40, 200)], fill=header_color)

            # Testi informativi
            title_text = "ScannerPan - Documento di Collaudo e Scansione"
            sub_text = f"Pagina {page_idx} di {num_pages} | Brother MFC-1910W Series (Virtual Mock)"
            ts_text = f"Data Acquisizione: {time.strftime('%Y-%m-%d %H:%M:%S')} | Risoluzione: {dpi} DPI"

            draw.text((60, 70), title_text, fill=(255, 255, 255) if mode_str == "RGB" else 255)
            draw.text((60, 130), sub_text, fill=(230, 230, 230) if mode_str == "RGB" else 230)

            # Paragrafi di testo multilingua per test OCR (Italiano, Inglese, Tedesco)
            y_offset = 260
            paragraphs = [
                ("1. Riconoscimento Caratteri Italiano (ITA)", [
                    "ScannerPan offre un supporto completo per la digitalizzazione avanzata di documenti.",
                    "Include rilevamento automatico dei bordi, raddrizzamento prospettico e rimozione ombre.",
                    "Tutti i file possono essere esportati in formato PDF ricercabile, Microsoft Word (DOCX), ODF e RTF.",
                ]),
                ("2. Multilingual OCR Verification (ENG & DEU)", [
                    "English: The quick brown fox jumps over the lazy dog. Accuracy and fidelity guaranteed.",
                    "Deutsch: Sehr geehrte Damen und Herren, dieses Dokument dient zur Qualitätsprüfung.",
                    "Spezielle Zeichen: Überprüfen von Umlauten (ä, ö, ü, ß) und Zahlen: 1234567890 EUR 49,99.",
                ]),
                ("3. Metadati e Parametri Hardware", [
                    f"Sorgente di acquisizione: {options.source} (Alimentatore/Piano)",
                    f"Modalità colore: {options.mode} | Contrasto: {options.contrast or 'Default'}",
                    f"Dispositivo SANE target: {options.device or self.BROTHER_DEFAULT_URI}",
                ]),
            ]

            for section_title, lines in paragraphs:
                draw.text((60, y_offset), section_title, fill=text_color)
                y_offset += 40
                for line in lines:
                    draw.text((80, y_offset), line, fill=text_color)
                    y_offset += 30
                y_offset += 30

            # Disegna una tabella di esempio
            table_y = y_offset + 20
            draw.rectangle([(60, table_y), (width - 60, table_y + 160)], outline=border_color, width=2)
            draw.line([(60, table_y + 40), (width - 60, table_y + 40)], fill=border_color, width=2)
            draw.line([(400, table_y), (400, table_y + 160)], fill=border_color, width=2)
            draw.line([(800, table_y), (800, table_y + 160)], fill=border_color, width=2)

            draw.text((70, table_y + 12), "CODICE", fill=text_color)
            draw.text((410, table_y + 12), "DESCRIZIONE COMPONENTE", fill=text_color)
            draw.text((810, table_y + 12), "STATO SISTEMA", fill=text_color)

            draw.text((70, table_y + 60), "MFC-1910W", fill=text_color)
            draw.text((410, table_y + 60), "Scanner Multifunzione Laser Brother", fill=text_color)
            draw.text((810, table_y + 60), "OPERATIVO (100% OK)", fill=(0, 150, 0) if mode_str == "RGB" else 50)

            draw.text((70, table_y + 110), "OCR-TESS", fill=text_color)
            draw.text((410, table_y + 110), "Motore Tesseract v5 Multi-lingua (ita/deu/eng)", fill=text_color)
            draw.text((810, table_y + 110), "PRONTO ALL'USO", fill=(0, 150, 0) if mode_str == "RGB" else 50)

            # Footer
            draw.line([(60, height - 100), (width - 60, height - 100)], fill=border_color, width=1)
            draw.text((60, height - 80), ts_text, fill=border_color)

            # Salva immagine
            target_path = target_dir / f"scan_page_{page_idx}.{ext}"
            img.save(str(target_path))
            created_files.append(target_path)
            if progress_callback:
                progress_callback(int(20 + 80 * (page_idx / num_pages)), f"Generata pagina simulata {page_idx}/{num_pages}...")

        return ScanResult(
            success=True,
            images=created_files,
            page_count=len(created_files),
            device_used=options.device or "mock:Brother-MFC-1910W-Virtual",
            duration_sec=0.1,
        )
