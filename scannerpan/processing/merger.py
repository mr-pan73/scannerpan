"""ScannerPan - Duplex Scanner Merger & Multi-format Image Exporter.

Modulo per l'accorpamento e la composizione di scansioni Fronte e Retro (Duplex):
- Generazione PDF multi-pagina (Fronte, Retro, o interleaving di lotti ADF).
- Composizione grafica Fronte/Retro in unica immagine:
  - Affiancata orizzontalmente (Side-by-side).
  - Impilata verticalmente (Stacked/Vertical).
  - ID Card (Carta d'Identità / Patente): scheda compatta o foglio A4 centrato con margini
    standard ed etichette 'FRONTE' e 'RETRO' opzionali.
- Interleaving intelligente per scanner simplex senza alimentatore duplex automatico
  (es. Brother MFC-1910W): accoppia F1, R1, F2, R2... anche con retro invertito dal vassoio ADF.
- Esportazione grafica in alta risoluzione: PNG, JPEG, TIFF, WebP, PDF con controllo DPI e compressione.
"""

from __future__ import annotations

import logging
from enum import Enum
from pathlib import Path
from typing import Any, List, Optional, Sequence, Tuple, Union

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

logger = logging.getLogger("scannerpan.processing.merger")


class LayoutMode(str, Enum):
    """Modalità di disposizione per l'immagine composita Fronte / Retro."""
    SIDE_BY_SIDE = "side_by_side"    # Affiancate orizzontalmente (Fronte sx, Retro dx)
    VERTICAL = "vertical"            # Impilate verticalmente (Fronte sopra, Retro sotto)
    ID_CARD = "id_card"              # Scheda sagomata compatta (stile tessera ID/patente)
    ID_CARD_A4 = "id_card_a4"        # Foglio A4 completo con tessere centrate per stampa


class ImageFormat(str, Enum):
    """Formati grafici e documentali supportati per l'esportazione."""
    PNG = "png"
    JPEG = "jpeg"
    TIFF = "tiff"
    WEBP = "webp"
    PDF = "pdf"


def _to_pil(img_input: Union[str, Path, Image.Image, np.ndarray]) -> Image.Image:
    """Converte un input in un oggetto PIL.Image RGB."""
    if isinstance(img_input, Image.Image):
        return img_input.convert("RGB") if img_input.mode != "RGB" else img_input.copy()
    if isinstance(img_input, np.ndarray):
        if len(img_input.shape) == 2:
            return Image.fromarray(img_input).convert("RGB")
        import cv2
        rgb = cv2.cvtColor(img_input, cv2.COLOR_BGR2RGB)
        return Image.fromarray(rgb)
    p = Path(img_input)
    if not p.exists():
        raise FileNotFoundError(f"File immagine non trovato: {p}")
    with Image.open(p) as loaded:
        return loaded.convert("RGB")


class DuplexMerger:
    """Engine per la fusione, composizione ed esportazione di documenti fronte-retro."""

    # Dimensioni A4 a 300 DPI in pixel (210 x 297 mm)
    A4_WIDTH_300DPI = 2480
    A4_HEIGHT_300DPI = 3508

    # Dimensioni standard carta d'identità / patente (ISO 7810 ID-1: 85.6 x 53.98 mm)
    # A 300 DPI: ~1011 x 638 pixel (rapporto 1.586)
    ID_CARD_WIDTH_300DPI = 1011
    ID_CARD_HEIGHT_300DPI = 638

    @staticmethod
    def interleave_duplex(
        front_pages: Sequence[Union[str, Path, Image.Image]],
        back_pages: Sequence[Union[str, Path, Image.Image]],
        reverse_back: bool = True,
    ) -> List[Any]:
        """Interfogliatura intelligente per scansioni duplex simplex.

        Negli scanner simplex con ADF (come Brother MFC-1910W), l'utente scansiona
        prima tutti i fronti [F1, F2, F3]. Poi prende il mazzo uscito e lo reinserisce
        nel vassoio per scansionare i retro: le pagine retro escono spesso in ordine
        invertito [R3, R2, R1].
        Se `reverse_back` è True, la lista dei retro viene automaticamente capovolta
        per produrre l'ordine corretto: [F1, R1, F2, R2, F3, R3].
        """
        fronts = list(front_pages)
        backs = list(back_pages)

        if reverse_back:
            backs = list(reversed(backs))

        interleaved: List[Any] = []
        max_len = max(len(fronts), len(backs))
        for i in range(max_len):
            if i < len(fronts):
                interleaved.append(fronts[i])
            if i < len(backs):
                interleaved.append(backs[i])

        return interleaved

    def create_composite_image(
        self,
        front_image: Union[str, Path, Image.Image, np.ndarray],
        back_image: Union[str, Path, Image.Image, np.ndarray],
        layout: Union[LayoutMode, str] = LayoutMode.ID_CARD,
        bg_color: Tuple[int, int, int] = (255, 255, 255),
        padding: int = 40,
        add_labels: bool = True,
        target_dpi: int = 300,
    ) -> Image.Image:
        """Crea un'unica immagine composita con Fronte e Retro disposti secondo il layout scelto.

        Layout supportati:
        - 'side_by_side': fronte e retro affiancati orizzontalmente.
        - 'vertical': fronte e retro incolonnati verticalmente.
        - 'id_card': scheda compatta con proporzioni uniformi e spaziatura elegante.
        - 'id_card_a4': posizionamento centrato su un foglio standard A4 pronto per la stampa/archiviazione.
        """
        mode = LayoutMode(layout) if isinstance(layout, str) else layout
        img_front = _to_pil(front_image)
        img_back = _to_pil(back_image)

        if mode == LayoutMode.SIDE_BY_SIDE:
            return self._build_side_by_side(img_front, img_back, bg_color, padding, add_labels)
        elif mode == LayoutMode.VERTICAL:
            return self._build_vertical(img_front, img_back, bg_color, padding, add_labels)
        elif mode == LayoutMode.ID_CARD:
            return self._build_id_card(img_front, img_back, bg_color, padding, add_labels)
        elif mode == LayoutMode.ID_CARD_A4:
            return self._build_id_card_a4(img_front, img_back, add_labels, target_dpi)
        else:
            raise ValueError(f"Layout mode non supportato: {layout}")

    def _build_side_by_side(
        self,
        front: Image.Image,
        back: Image.Image,
        bg_color: Tuple[int, int, int],
        padding: int,
        add_labels: bool,
    ) -> Image.Image:
        """Fronte e retro affiancati orizzontalmente con altezza unificata."""
        label_height = 40 if add_labels else 0
        target_h = max(front.height, back.height)

        # Riscala mantenendo aspect ratio se le altezze differiscono
        f_w = int(front.width * (target_h / front.height))
        f_scaled = front.resize((f_w, target_h), Image.Resampling.LANCZOS)

        b_w = int(back.width * (target_h / back.height))
        b_scaled = back.resize((b_w, target_h), Image.Resampling.LANCZOS)

        total_w = padding + f_w + padding + b_w + padding
        total_h = padding + label_height + target_h + padding

        canvas = Image.new("RGB", (total_w, total_h), color=bg_color)
        draw = ImageDraw.Draw(canvas)

        # Incolla fronte
        f_x = padding
        f_y = padding + label_height
        canvas.paste(f_scaled, (f_x, f_y))

        # Incolla retro
        b_x = padding + f_w + padding
        b_y = padding + label_height
        canvas.paste(b_scaled, (b_x, b_y))

        if add_labels:
            draw.text((f_x + 10, padding + 10), "FRONTE", fill=(50, 50, 50))
            draw.text((b_x + 10, padding + 10), "RETRO", fill=(50, 50, 50))

        return canvas

    def _build_vertical(
        self,
        front: Image.Image,
        back: Image.Image,
        bg_color: Tuple[int, int, int],
        padding: int,
        add_labels: bool,
    ) -> Image.Image:
        """Fronte e retro impilati verticalmente con larghezza unificata."""
        label_height = 40 if add_labels else 0
        target_w = max(front.width, back.width)

        f_h = int(front.height * (target_w / front.width))
        f_scaled = front.resize((target_w, f_h), Image.Resampling.LANCZOS)

        b_h = int(back.height * (target_w / back.width))
        b_scaled = back.resize((target_w, b_h), Image.Resampling.LANCZOS)

        total_w = padding + target_w + padding
        total_h = padding + label_height + f_h + padding + label_height + b_h + padding

        canvas = Image.new("RGB", (total_w, total_h), color=bg_color)
        draw = ImageDraw.Draw(canvas)

        curr_y = padding
        if add_labels:
            draw.text((padding + 10, curr_y + 10), "FRONTE", fill=(50, 50, 50))
            curr_y += label_height

        canvas.paste(f_scaled, (padding, curr_y))
        curr_y += f_h + padding

        if add_labels:
            draw.text((padding + 10, curr_y + 10), "RETRO", fill=(50, 50, 50))
            curr_y += label_height

        canvas.paste(b_scaled, (padding, curr_y))
        return canvas

    def _build_id_card(
        self,
        front: Image.Image,
        back: Image.Image,
        bg_color: Tuple[int, int, int],
        padding: int,
        add_labels: bool,
    ) -> Image.Image:
        """Scheda tessere d'identità / patenti standard con proporzioni armonizzate."""
        label_height = 40 if add_labels else 0

        # Uniforma le dimensioni di fronte e retro per simmetria perfetta
        card_w = max(front.width, back.width, self.ID_CARD_WIDTH_300DPI)
        card_h = int(card_w / 1.586)  # Rapporto standard ID-1

        f_fitted = ImageOps.fit(front, (card_w, card_h), method=Image.Resampling.LANCZOS)
        b_fitted = ImageOps.fit(back, (card_w, card_h), method=Image.Resampling.LANCZOS)

        total_w = padding + card_w + padding
        total_h = padding + label_height + card_h + padding + label_height + card_h + padding

        canvas = Image.new("RGB", (total_w, total_h), color=bg_color)
        draw = ImageDraw.Draw(canvas)

        # Bordo leggero attorno alle tessere
        border_color = (210, 210, 210)

        # Fronte
        y_f = padding + label_height
        canvas.paste(f_fitted, (padding, y_f))
        draw.rectangle([(padding - 1, y_f - 1), (padding + card_w, y_f + card_h)], outline=border_color, width=2)
        if add_labels:
            draw.text((padding + 5, padding + 10), "DOCUMENTO D'IDENTITÀ - FRONTE", fill=(30, 80, 180))

        # Retro
        y_b = y_f + card_h + padding + label_height
        canvas.paste(b_fitted, (padding, y_b))
        draw.rectangle([(padding - 1, y_b - 1), (padding + card_w, y_b + card_h)], outline=border_color, width=2)
        if add_labels:
            draw.text((padding + 5, y_f + card_h + padding + 10), "DOCUMENTO D'IDENTITÀ - RETRO", fill=(30, 80, 180))

        return canvas

    def _build_id_card_a4(
        self,
        front: Image.Image,
        back: Image.Image,
        add_labels: bool,
        dpi: int = 300,
    ) -> Image.Image:
        """Genera un foglio A4 completo con Carta d'Identità Fronte e Retro centrate per stampa formale."""
        # Dimensioni proporzionali ai DPI
        a4_w = int(8.27 * dpi)
        a4_h = int(11.69 * dpi)

        canvas = Image.new("RGB", (a4_w, a4_h), color=(255, 255, 255))
        draw = ImageDraw.Draw(canvas)

        # Dimensioni standard carta (85.6 x 54 mm) in pixel alla risoluzione data
        card_w = int(3.37 * dpi)
        card_h = int(2.125 * dpi)

        f_fitted = ImageOps.fit(front, (card_w, card_h), method=Image.Resampling.LANCZOS)
        b_fitted = ImageOps.fit(back, (card_w, card_h), method=Image.Resampling.LANCZOS)

        center_x = (a4_w - card_w) // 2
        y1 = int(a4_h * 0.20)
        y2 = int(a4_h * 0.55)

        border_col = (200, 200, 200)

        # Intestazione pagina A4
        draw.rectangle([(center_x, y1 - 40), (center_x + card_w, y1 - 10)], fill=(240, 240, 245))
        draw.text((center_x + 10, y1 - 32), "DOCUMENTO - FRONTE", fill=(40, 40, 40))

        canvas.paste(f_fitted, (center_x, y1))
        draw.rectangle([(center_x - 1, y1 - 1), (center_x + card_w, y1 + card_h)], outline=border_col, width=2)

        # Retro
        draw.rectangle([(center_x, y2 - 40), (center_x + card_w, y2 - 10)], fill=(240, 240, 245))
        draw.text((center_x + 10, y2 - 32), "DOCUMENTO - RETRO", fill=(40, 40, 40))

        canvas.paste(b_fitted, (center_x, y2))
        draw.rectangle([(center_x - 1, y2 - 1), (center_x + card_w, y2 + card_h)], outline=border_col, width=2)

        return canvas

    # =========================================================================
    # ESPORTAZIONE FILE
    # =========================================================================

    def export_image(
        self,
        image: Union[Image.Image, np.ndarray],
        output_path: Union[str, Path],
        image_format: Optional[Union[ImageFormat, str]] = None,
        dpi: int = 300,
        quality: int = 92,
    ) -> Path:
        """Salva un'immagine nel formato grafico specificato (PNG, JPEG, TIFF, WebP)."""
        pil_img = _to_pil(image)
        out_p = Path(output_path).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)

        fmt_str = image_format.value if isinstance(image_format, ImageFormat) else image_format
        if not fmt_str:
            fmt_str = out_p.suffix.lower().lstrip(".") or "png"

        fmt_str = fmt_str.lower()
        target_file = out_p.with_suffix(f".{fmt_str}")

        save_kwargs: dict[str, Any] = {"dpi": (dpi, dpi)}

        if fmt_str in ("jpg", "jpeg"):
            save_kwargs["quality"] = quality
            save_kwargs["optimize"] = True
            pil_img.save(str(target_file), "JPEG", **save_kwargs)
        elif fmt_str == "png":
            save_kwargs["compress_level"] = 6
            save_kwargs["optimize"] = True
            pil_img.save(str(target_file), "PNG", **save_kwargs)
        elif fmt_str == "webp":
            save_kwargs["quality"] = quality
            save_kwargs["method"] = 6
            pil_img.save(str(target_file), "WEBP", **save_kwargs)
        elif fmt_str in ("tif", "tiff"):
            save_kwargs["compression"] = "tiff_deflate"
            pil_img.save(str(target_file), "TIFF", **save_kwargs)
        elif fmt_str == "pdf":
            pil_img.save(str(target_file), "PDF", resolution=dpi)
        else:
            raise ValueError(f"Formato grafico non supportato: {fmt_str}")

        return target_file

    def merge_to_pdf(
        self,
        images: Sequence[Union[str, Path, Image.Image, np.ndarray]],
        output_pdf_path: Union[str, Path],
        dpi: int = 300,
        fit_a4: bool = False,
    ) -> Path:
        """Unisce una sequenza ordinata di immagini in un unico documento PDF multi-pagina."""
        out_p = Path(output_pdf_path).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)
        target_pdf = out_p.with_suffix(".pdf")

        if not images:
            raise ValueError("Nessuna immagine fornita per la creazione del PDF.")

        pil_list: List[Image.Image] = []
        a4_w = int(8.27 * dpi)
        a4_h = int(11.69 * dpi)

        for item in images:
            img = _to_pil(item)
            if fit_a4:
                # Inserisci l'immagine centrata su un foglio A4 bianco
                page = Image.new("RGB", (a4_w, a4_h), color=(255, 255, 255))
                # Calcola scala per adattare all'A4 con margine
                margin = int(0.5 * dpi)
                max_w = a4_w - (margin * 2)
                max_h = a4_h - (margin * 2)
                scale = min(max_w / img.width, max_h / img.height, 1.0)
                new_w = int(img.width * scale)
                new_h = int(img.height * scale)
                img_resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
                paste_x = (a4_w - new_w) // 2
                paste_y = (a4_h - new_h) // 2
                page.paste(img_resized, (paste_x, paste_y))
                pil_list.append(page)
            else:
                pil_list.append(img)

        first_page = pil_list[0]
        remaining = pil_list[1:] if len(pil_list) > 1 else []

        first_page.save(
            str(target_pdf),
            "PDF",
            resolution=dpi,
            save_all=True,
            append_images=remaining,
        )

        return target_pdf

    def merge_duplex_to_pdf(
        self,
        front_pages: Sequence[Union[str, Path, Image.Image, np.ndarray]],
        back_pages: Sequence[Union[str, Path, Image.Image, np.ndarray]],
        output_pdf_path: Union[str, Path],
        reverse_back: bool = True,
        dpi: int = 300,
        fit_a4: bool = False,
    ) -> Path:
        """Accorpa i lotti fronte e retro in un PDF multi-pagina con interfogliatura corretta."""
        ordered = self.interleave_duplex(front_pages, back_pages, reverse_back=reverse_back)
        return self.merge_to_pdf(ordered, output_pdf_path, dpi=dpi, fit_a4=fit_a4)
