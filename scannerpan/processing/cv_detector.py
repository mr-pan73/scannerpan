"""ScannerPan - Computer Vision Detector & Document Processing Engine.

Fornisce algoritmi avanzati basati su OpenCV e NumPy per:
- Document boundary detection automatico con correzione prospettica a 4 punti (unwarp/deskew).
- Correzione rotazione ed inclinazione automatica (skew correction).
- Rilevamento multi-soggetto (Multi-subject / Photo detection) per scannerizzare contemporaneamente
  più foto, scontrini, biglietti da visita o scontrini posizionati sul piano.
- Ritaglio automatico dei margini (auto-crop) e filtri di miglioramento (CLAHE, unsharp mask,
  pulizia avanzata dello sfondo e rimozione ombre).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple, Union

import cv2
import numpy as np
from PIL import Image

logger = logging.getLogger("scannerpan.processing.cv_detector")


@dataclass
class DetectedSubject:
    """Rappresentazione di un singolo elemento (foto, scontrino, documento) rilevato sul piano."""
    subject_id: int
    bbox: Tuple[int, int, int, int]  # (x, y, w, h)
    angle: float  # Inclinazione in gradi rilevata
    cropped_image: np.ndarray  # Immagine ritagliata e raddrizzata (RGB o Gray)
    area: float
    confidence: float = 1.0

    @property
    def pil_image(self) -> Image.Image:
        """Converte il crop ritagliato in oggetto PIL.Image."""
        return cv_to_pil(self.cropped_image)


def pil_to_cv(image: Image.Image) -> np.ndarray:
    """Converte un'immagine PIL in array NumPy OpenCV (RGB/BGR corretto)."""
    if image.mode == "L":
        return np.array(image)
    if image.mode != "RGB":
        image = image.convert("RGB")
    arr = np.array(image)
    return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)


def cv_to_pil(image: np.ndarray) -> Image.Image:
    """Converte un array NumPy OpenCV in immagine PIL (RGB)."""
    if len(image.shape) == 2:
        return Image.fromarray(image)
    # Se ha 3 canali, assume BGR da OpenCV e converte in RGB
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    return Image.fromarray(rgb)


def load_image(image_input: Union[str, Path, Image.Image, np.ndarray]) -> np.ndarray:
    """Carica in modo sicuro un'immagine da percorso file, oggetto PIL o ndarray."""
    if isinstance(image_input, np.ndarray):
        return image_input.copy()
    if isinstance(image_input, Image.Image):
        return pil_to_cv(image_input)
    path_str = str(image_input)
    img = cv2.imread(path_str)
    if img is None:
        raise ValueError(f"Impossibile leggere l'immagine dal percorso: {path_str}")
    return img


class CVDetector:
    """Engine di rilevamento ottico geometrico e pulizia immagini per ScannerPan."""

    def __init__(self, debug: bool = False):
        self.debug = debug

    # =========================================================================
    # 1. RILEVAMENTO BORDI FOGLIO & TRASFORMAZIONE PROSPETTICA (DESKEW)
    # =========================================================================

    @staticmethod
    def order_points(pts: np.ndarray) -> np.ndarray:
        """Ordina le 4 coordinate di un poligono in: top-left, top-right, bottom-right, bottom-left."""
        rect = np.zeros((4, 2), dtype="float32")
        # Somma (x + y): il minimo è top-left, il massimo è bottom-right
        s = pts.sum(axis=1)
        rect[0] = pts[np.argmin(s)]
        rect[2] = pts[np.argmax(s)]

        # Differenza (y - x): il minimo è top-right, il massimo è bottom-left
        diff = np.diff(pts, axis=1)
        rect[1] = pts[np.argmin(diff)]
        rect[3] = pts[np.argmax(diff)]
        return rect

    def four_point_transform(self, image: np.ndarray, pts: np.ndarray) -> np.ndarray:
        """Esegue la trasformazione prospettica proiettando il quadrilatero in un rettangolo ortogonale."""
        rect = self.order_points(pts)
        (tl, tr, br, bl) = rect

        # Calcola la larghezza massima del nuovo rettangolo
        width_a = np.sqrt(((br[0] - bl[0]) ** 2) + ((br[1] - bl[1]) ** 2))
        width_b = np.sqrt(((tr[0] - tl[0]) ** 2) + ((tr[1] - tl[1]) ** 2))
        max_width = max(int(width_a), int(width_b))

        # Calcola l'altezza massima del nuovo rettangolo
        height_a = np.sqrt(((tr[0] - br[0]) ** 2) + ((tr[1] - br[1]) ** 2))
        height_b = np.sqrt(((tl[0] - bl[0]) ** 2) + ((tl[1] - bl[1]) ** 2))
        max_height = max(int(height_a), int(height_b))

        if max_width <= 0 or max_height <= 0:
            return image

        dst = np.array([
            [0, 0],
            [max_width - 1, 0],
            [max_width - 1, max_height - 1],
            [0, max_height - 1]
        ], dtype="float32")

        matrix = cv2.getPerspectiveTransform(rect, dst)
        warped = cv2.warpPerspective(image, matrix, (max_width, max_height), flags=cv2.INTER_CUBIC)
        return warped

    def detect_document_boundary(
        self,
        image_input: Union[str, Path, Image.Image, np.ndarray],
        min_area_ratio: float = 0.20,
    ) -> Optional[np.ndarray]:
        """Rileva i 4 vertici del foglio posizionato sul piano dello scanner.

        Restituisce un array NumPy con 4 punti (shape: 4, 2) oppure None se
        il documento occupa l'intero piano o non ha contorni evidenti.
        """
        img = load_image(image_input)
        h, w = img.shape[:2]
        total_area = float(h * w)

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img.copy()
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)

        # Canny edge detection con soglie bilanciate
        edged = cv2.Canny(blurred, 50, 200)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        edged = cv2.morphologyEx(edged, cv2.MORPH_CLOSE, kernel, iterations=2)

        contours, _ = cv2.findContours(edged, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        contours = sorted(contours, key=cv2.contourArea, reverse=True)[:5]

        for c in contours:
            area = cv2.contourArea(c)
            if area < (min_area_ratio * total_area):
                continue
            peri = cv2.arcLength(c, True)
            approx = cv2.approxPolyDP(c, 0.02 * peri, True)
            if len(approx) == 4:
                return approx.reshape(4, 2)

        return None

    def deskew_and_crop_document(
        self,
        image_input: Union[str, Path, Image.Image, np.ndarray],
    ) -> Tuple[np.ndarray, bool]:
        """Raddrizza ed estrae automaticamente il documento dal piano di scansione.

        Se viene rilevato un contorno a 4 punti, applica four_point_transform.
        Altrimenti, esegue il deskew basato sull'orientamento del testo/bordi (minAreaRect).
        Restituisce (immagine_elaborata, is_perspective_transformed).
        """
        img = load_image(image_input)
        boundary = self.detect_document_boundary(img)
        if boundary is not None:
            warped = self.four_point_transform(img, boundary)
            return warped, True

        # Fallback su deskew orientamento testo
        deskewed, _ = self.deskew_by_angle(img)
        return deskewed, False

    def deskew_by_angle(
        self,
        image_input: Union[str, Path, Image.Image, np.ndarray],
        max_angle: float = 45.0,
    ) -> Tuple[np.ndarray, float]:
        """Corregge le leggere rotazioni di scansione (inclinazione testo) calcolando l'angolo."""
        img = load_image(image_input)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img.copy()

        # Inverti e binarizza per evidenziare il testo
        thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]

        # Trova tutti i punti dove ci sono pixel di testo/disegno
        coords = np.column_stack(np.where(thresh > 0))
        if len(coords) < 100:
            return img, 0.0

        angle = cv2.minAreaRect(coords)[-1]
        # minAreaRect restituisce angoli in [-90, 0] o simili
        if angle < -45:
            angle = -(90 + angle)
        else:
            angle = -angle

        if abs(angle) > max_angle or abs(angle) < 0.2:
            return img, 0.0

        (h, w) = img.shape[:2]
        center = (w // 2, h // 2)
        rot_mat = cv2.getRotationMatrix2D(center, angle, 1.0)
        rotated = cv2.warpAffine(
            img,
            rot_mat,
            (w, h),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=(255, 255, 255) if len(img.shape) == 3 else 255,
        )
        return rotated, float(angle)

    # =========================================================================
    # 2. MULTI-SUBJECT / PHOTO DETECTION
    # =========================================================================

    def detect_multiple_subjects(
        self,
        image_input: Union[str, Path, Image.Image, np.ndarray],
        min_area_ratio: float = 0.015,
        max_area_ratio: float = 0.85,
        padding_px: int = 15,
        deskew_crops: bool = True,
    ) -> List[DetectedSubject]:
        """Rileva automaticamente molteplici foto, ricevute o tessere scansionate insieme sul piano.

        Separa ciascun elemento, calcola il bounding box rettangolare con margine (padding),
        raddrizza i singoli soggetti e li restituisce ordinati dall'alto in basso, da sinistra a destra.
        """
        img = load_image(image_input)
        h, w = img.shape[:2]
        total_area = float(h * w)
        min_area = total_area * min_area_ratio
        max_area = total_area * max_area_ratio

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img.copy()

        # Sfocatura per eliminare rumore del vetro
        blurred = cv2.GaussianBlur(gray, (7, 7), 0)

        # Rileva se lo sfondo del piano è prevalentemente chiaro (bianco) o scuro
        # Mediana sui bordi dell'immagine (10 pixel esterni)
        border_pixels = np.concatenate([
            gray[:10, :].flatten(),
            gray[-10:, :].flatten(),
            gray[:, :10].flatten(),
            gray[:, -10:].flatten(),
        ])
        is_light_background = np.median(border_pixels) > 127

        if is_light_background:
            # Piano chiaro (bianco): oggetti più scuri rispetto al fondo
            thresh = cv2.threshold(blurred, 235, 255, cv2.THRESH_BINARY_INV)[1]
        else:
            # Piano scuro: oggetti più chiari
            thresh = cv2.threshold(blurred, 30, 255, cv2.THRESH_BINARY)[1]

        # Operazione morfologica per unire contorni frammentati dello stesso oggetto
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 15))
        closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=2)
        closed = cv2.morphologyEx(closed, cv2.MORPH_OPEN, kernel, iterations=1)

        contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        candidate_subjects: List[Tuple[int, int, int, int, float, np.ndarray]] = []
        for c in contours:
            area = cv2.contourArea(c)
            if area < min_area or area > max_area:
                continue

            # Bounding box dritto
            bx, by, bw, bh = cv2.boundingRect(c)

            # Aggiungi padding con clamp ai limiti immagine
            px1 = max(0, bx - padding_px)
            py1 = max(0, by - padding_px)
            px2 = min(w, bx + bw + padding_px)
            py2 = min(h, by + bh + padding_px)

            cropped = img[py1:py2, px1:px2].copy()

            # Calcolo inclinazione specifica del soggetto tramite minAreaRect
            rect = cv2.minAreaRect(c)
            sub_angle = rect[-1]
            if sub_angle < -45:
                sub_angle = -(90 + sub_angle)
            else:
                sub_angle = -sub_angle

            if deskew_crops and abs(sub_angle) > 0.5 and abs(sub_angle) < 45:
                # Ruota il singolo crop per raddrizzarlo
                ch, cw = cropped.shape[:2]
                center = (cw // 2, ch // 2)
                m = cv2.getRotationMatrix2D(center, sub_angle, 1.0)
                cropped = cv2.warpAffine(
                    cropped,
                    m,
                    (cw, ch),
                    flags=cv2.INTER_CUBIC,
                    borderMode=cv2.BORDER_CONSTANT,
                    borderValue=(255, 255, 255) if len(cropped.shape) == 3 else 255,
                )

            candidate_subjects.append((px1, py1, px2 - px1, py2 - py1, float(sub_angle), cropped, area))

        # Ordina dall'alto in basso, poi da sinistra a destra
        candidate_subjects.sort(key=lambda item: (item[1] // 100, item[0]))

        detected: List[DetectedSubject] = []
        for idx, (x, y, sw, sh, ang, crop_mat, c_area) in enumerate(candidate_subjects, start=1):
            detected.append(
                DetectedSubject(
                    subject_id=idx,
                    bbox=(x, y, sw, sh),
                    angle=ang,
                    cropped_image=crop_mat,
                    area=c_area,
                    confidence=1.0,
                )
            )

        return detected

    # =========================================================================
    # 3. FILTRI DI MIGLIORAMENTO, CONTRASTO E PULIZIA SFONDO
    # =========================================================================

    def enhance_contrast(
        self,
        image_input: Union[str, Path, Image.Image, np.ndarray],
        method: str = "clahe",
    ) -> np.ndarray:
        """Migliora il contrasto e la leggibilità di testo e dettagli grafici.

        Metodi supportati:
        - 'clahe': Contrast Limited Adaptive Histogram Equalization su canale Luminanza.
        - 'unsharp': Maschera di contrasto (Unsharp Mask) per rendere nitidi i contorni del testo.
        - 'normalize': Normalizzazione dell'istogramma dinamico min-max.
        """
        img = load_image(image_input)

        if method.lower() == "clahe":
            if len(img.shape) == 3:
                lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
                l, a, b = cv2.split(lab)
                clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
                cl = clahe.apply(l)
                merged = cv2.merge((cl, a, b))
                return cv2.cvtColor(merged, cv2.COLOR_LAB2BGR)
            else:
                clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
                return clahe.apply(img)

        elif method.lower() == "unsharp":
            gaussian = cv2.GaussianBlur(img, (0, 0), 2.0)
            unsharp = cv2.addWeighted(img, 1.5, gaussian, -0.5, 0)
            return unsharp

        elif method.lower() == "normalize":
            norm = np.zeros_like(img)
            return cv2.normalize(img, norm, alpha=0, beta=255, norm_type=cv2.NORM_MINMAX)

        return img

    def clean_background(
        self,
        image_input: Union[str, Path, Image.Image, np.ndarray],
        mode: str = "document",
    ) -> np.ndarray:
        """Pulisce lo sfondo cartaceo da ingiallimento, ombre dello scanner e trasparenze.

        Modalità:
        - 'document': Sbianca uniformemente lo sfondo cartaceo preservando inalterati
                      i colori di timbri, firme e grafici.
        - 'bw': Binarizzazione ad alto contrasto bianco/nero ottimale per documenti
                di testo puliti e documenti legali.
        - 'photo': Correzione gamma bilanciata per fotografie senza perdita di sfumature.
        """
        img = load_image(image_input)

        if mode == "bw":
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img.copy()
            # Binarizzazione adattiva con filtro gaussiano
            bw = cv2.adaptiveThreshold(
                gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 21, 10
            )
            return bw

        elif mode == "document":
            # Algoritmo di rimozione ombra per divisione su sfondo stimato
            if len(img.shape) == 3:
                planes = cv2.split(img)
                result_planes = []
                for plane in planes:
                    dilated = cv2.dilate(plane, np.ones((7, 7), np.uint8))
                    bg_img = cv2.medianBlur(dilated, 21)
                    diff_img = 255 - cv2.absdiff(plane, bg_img)
                    norm_img = cv2.normalize(
                        diff_img, None, alpha=0, beta=255, norm_type=cv2.NORM_MINMAX, dtype=cv2.CV_8UC1
                    )
                    result_planes.append(norm_img)
                return cv2.merge(result_planes)
            else:
                dilated = cv2.dilate(img, np.ones((7, 7), np.uint8))
                bg_img = cv2.medianBlur(dilated, 21)
                diff_img = 255 - cv2.absdiff(img, bg_img)
                return cv2.normalize(
                    diff_img, None, alpha=0, beta=255, norm_type=cv2.NORM_MINMAX, dtype=cv2.CV_8UC1
                )

        elif mode == "photo":
            # Correzione gamma leggera (gamma = 1.1) per ravvivare le zone d'ombra
            inv_gamma = 1.0 / 1.15
            table = np.array([((i / 255.0) ** inv_gamma) * 255 for i in np.arange(0, 256)]).astype("uint8")
            return cv2.LUT(img, table)

        return img

    def auto_crop_margins(
        self,
        image_input: Union[str, Path, Image.Image, np.ndarray],
        margin_px: int = 10,
        threshold_diff: int = 20,
    ) -> np.ndarray:
        """Rileva e rimuove automaticamente i bordi neri o non desiderati dello scanner."""
        img = load_image(image_input)
        h, w = img.shape[:2]

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img.copy()

        # Cerca pixel che differiscono significativamente dal bordo esterno nero/bianco
        corner_val = int(gray[0, 0])
        diff = np.abs(gray.astype(np.int32) - corner_val)
        active_mask = (diff > threshold_diff).astype(np.uint8)

        coords = cv2.findNonZero(active_mask)
        if coords is None:
            return img

        x, y, bw, bh = cv2.boundingRect(coords)
        x1 = max(0, x - margin_px)
        y1 = max(0, y - margin_px)
        x2 = min(w, x + bw + margin_px)
        y2 = min(h, y + bh + margin_px)

        return img[y1:y2, x1:x2].copy()
