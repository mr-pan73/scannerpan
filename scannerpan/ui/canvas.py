"""
Interactive Canvas Widget for PyQt6 - ScannerPan.
Provides smooth high-performance image rendering, pan, zoom,
auto-crop indicators, and interactive multi-subject overlays with
selectable bounding boxes and numbered checkboxes.
"""

from typing import List, Dict, Optional, Tuple, Any
import numpy as np
from PIL import Image

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QToolButton, QFrame
)
from PyQt6.QtGui import (
    QPainter, QPixmap, QImage, QColor, QPen, QBrush,
    QFont, QMouseEvent, QWheelEvent, QPaintEvent, QResizeEvent,
    QPolygonF, QPainterPath
)
from PyQt6.QtCore import Qt, QRectF, QPointF, pyqtSignal

from scannerpan.ui.kde_theme import get_kde_icon


def pil_to_qpixmap(pil_img: Image.Image) -> QPixmap:
    """Converts a PIL Image to QPixmap safely."""
    if pil_img.mode != "RGBA":
        pil_img = pil_img.convert("RGBA")
    data = pil_img.tobytes("raw", "RGBA")
    qimg = QImage(data, pil_img.width, pil_img.height, QImage.Format.Format_RGBA8888)
    return QPixmap.fromImage(qimg)


def cv2_to_qpixmap(cv_img: np.ndarray) -> QPixmap:
    """Converts OpenCV numpy array (BGR or Gray) to QPixmap."""
    if len(cv_img.shape) == 2:
        h, w = cv_img.shape
        qimg = QImage(cv_img.data, w, h, w, QImage.Format.Format_Grayscale8)
    else:
        h, w, c = cv_img.shape
        # OpenCV is BGR, convert to RGB
        rgb = cv_img[:, :, ::-1].copy()
        qimg = QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888)
    return QPixmap.fromImage(qimg)


class CanvasViewport(QWidget):
    """
    Internal painting widget that handles transforms, image rendering,
    pan/zoom mathematics and subject hit testing.
    """
    subject_toggled = pyqtSignal(int, bool)
    selection_changed = pyqtSignal(list)
    zoom_changed = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._pixmap: Optional[QPixmap] = None
        self._zoom: float = 1.0
        self._pan_offset = QPointF(0, 0)

        # Mouse interaction state
        self._is_panning = False
        self._last_mouse_pos = QPointF(0, 0)
        self._drag_start_pos = QPointF(0, 0)
        self._dragged_significantly = False

        # Subject overlays: list of dicts:
        # { 'id': int, 'rect': (x, y, w, h), 'label': str, 'selected': bool, 'color': QColor }
        self._subjects: List[Dict[str, Any]] = []
        self._hovered_subject_id: Optional[int] = None

        # Auto-crop box: (x, y, w, h)
        self._crop_rect: Optional[Tuple[float, float, float, float]] = None

        # Distinct colors for detected subjects
        self._palette_colors = [
            QColor("#3daee9"),  # Breeze Blue
            QColor("#27ae60"),  # Green
            QColor("#e67e22"),  # Orange
            QColor("#9b59b6"),  # Purple
            QColor("#e74c3c"),  # Red
            QColor("#1abc9c"),  # Teal
            QColor("#f39c12"),  # Amber
        ]

    def set_pixmap(self, pixmap: Optional[QPixmap]):
        self._pixmap = pixmap
        self._subjects.clear()
        self._crop_rect = None
        if self._pixmap and not self._pixmap.isNull():
            self.fit_to_page()
        else:
            self._zoom = 1.0
            self._pan_offset = QPointF(0, 0)
            self.update()

    def set_subjects(self, subjects: List[Dict[str, Any]]):
        """
        Receives subjects list. Each item should have 'rect': (x,y,w,h) or 'box'.
        Options: 'id', 'selected', 'label', 'color'.
        """
        self._subjects = []
        for idx, s in enumerate(subjects):
            s_copy = dict(s)
            s_copy.setdefault("id", idx + 1)
            s_copy.setdefault("selected", True)
            s_copy.setdefault("label", f"Soggetto {s_copy['id']}")
            color_idx = idx % len(self._palette_colors)
            s_copy.setdefault("color", self._palette_colors[color_idx])
            self._subjects.append(s_copy)
        self.update()
        self.selection_changed.emit(self.get_selected_subjects())

    def set_crop_rect(self, *args):
        if len(args) == 1:
            val = args[0]
            if val is None or isinstance(val, (tuple, list)):
                self._crop_rect = val
            else:
                self._crop_rect = None
        elif len(args) == 4:
            self._crop_rect = (float(args[0]), float(args[1]), float(args[2]), float(args[3]))
        else:
            self._crop_rect = None
        self.update()

    def get_selected_subjects(self) -> List[Dict[str, Any]]:
        return [s for s in self._subjects if s.get("selected", False)]

    def get_all_subjects(self) -> List[Dict[str, Any]]:
        return list(self._subjects)

    def select_all_subjects(self, select: bool = True):
        for s in self._subjects:
            s["selected"] = select
        self.update()
        self.selection_changed.emit(self.get_selected_subjects())

    # --- Coordinate Transforms ---
    def image_to_viewport(self, pt: QPointF) -> QPointF:
        return QPointF(
            pt.x() * self._zoom + self._pan_offset.x(),
            pt.y() * self._zoom + self._pan_offset.y()
        )

    def viewport_to_image(self, pt: QPointF) -> QPointF:
        if self._zoom <= 0:
            return QPointF(0, 0)
        return QPointF(
            (pt.x() - self._pan_offset.x()) / self._zoom,
            (pt.y() - self._pan_offset.y()) / self._zoom
        )

    # --- Zoom / Pan Operations ---
    def fit_to_page(self):
        if not self._pixmap or self._pixmap.isNull():
            return
        vw, vh = self.width(), self.height()
        pw, ph = self._pixmap.width(), self._pixmap.height()
        if pw <= 0 or ph <= 0 or vw <= 0 or vh <= 0:
            return

        margin = 24
        scale_x = (vw - margin * 2) / pw
        scale_y = (vh - margin * 2) / ph
        self._zoom = max(0.05, min(scale_x, scale_y, 3.0))

        # Center image
        new_x = (vw - pw * self._zoom) / 2.0
        new_y = (vh - ph * self._zoom) / 2.0
        self._pan_offset = QPointF(new_x, new_y)
        self.zoom_changed.emit(self._zoom)
        self.update()

    def fit_to_width(self):
        if not self._pixmap or self._pixmap.isNull():
            return
        vw = self.width()
        pw = self._pixmap.width()
        if pw <= 0 or vw <= 0:
            return
        margin = 24
        self._zoom = max(0.05, (vw - margin * 2) / pw)
        self._pan_offset = QPointF(margin, 24)
        self.zoom_changed.emit(self._zoom)
        self.update()

    def set_zoom(self, zoom: float, center_on_mouse: Optional[QPointF] = None):
        new_zoom = max(0.05, min(zoom, 10.0))
        if abs(new_zoom - self._zoom) < 1e-4:
            return

        if center_on_mouse is not None:
            # Keep point under cursor stable
            img_pt = self.viewport_to_image(center_on_mouse)
            self._zoom = new_zoom
            self._pan_offset = QPointF(
                center_on_mouse.x() - img_pt.x() * self._zoom,
                center_on_mouse.y() - img_pt.y() * self._zoom
            )
        else:
            # Zoom centered on viewport center
            center_v = QPointF(self.width() / 2, self.height() / 2)
            img_pt = self.viewport_to_image(center_v)
            self._zoom = new_zoom
            self._pan_offset = QPointF(
                center_v.x() - img_pt.x() * self._zoom,
                center_v.y() - img_pt.y() * self._zoom
            )

        self.zoom_changed.emit(self._zoom)
        self.update()

    def zoom_in(self):
        self.set_zoom(self._zoom * 1.25)

    def zoom_out(self):
        self.set_zoom(self._zoom / 1.25)

    def reset_zoom(self):
        self.set_zoom(1.0)

    # --- Subject Hit Testing ---
    def _hit_test_subject(self, img_pt: QPointF) -> Optional[int]:
        """Returns subject ID under the image coordinate point, checking in reverse order."""
        for s in reversed(self._subjects):
            rx, ry, rw, rh = s["rect"]
            if rx <= img_pt.x() <= rx + rw and ry <= img_pt.y() <= ry + rh:
                return s["id"]
        return None

    # --- Mouse Events ---
    def mousePressEvent(self, event: QMouseEvent):
        if event.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.MiddleButton):
            self._is_panning = True
            self._last_mouse_pos = event.position()
            self._drag_start_pos = event.position()
            self._dragged_significantly = False
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event: QMouseEvent):
        curr_pos = event.position()
        if self._is_panning:
            diff = curr_pos - self._last_mouse_pos
            if (curr_pos - self._drag_start_pos).manhattanLength() > 4:
                self._dragged_significantly = True
            self._pan_offset += diff
            self._last_mouse_pos = curr_pos
            self.update()
        else:
            # Hover detection
            img_pt = self.viewport_to_image(curr_pos)
            hovered = self._hit_test_subject(img_pt)
            if hovered != self._hovered_subject_id:
                self._hovered_subject_id = hovered
                self.update()
                if hovered is not None:
                    self.setCursor(Qt.CursorShape.PointingHandCursor)
                else:
                    self.setCursor(Qt.CursorShape.ArrowCursor)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.MiddleButton):
            self._is_panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)

            # If it was a quick click without dragging, toggle subject under cursor
            if event.button() == Qt.MouseButton.LeftButton and not self._dragged_significantly:
                img_pt = self.viewport_to_image(event.position())
                clicked_id = self._hit_test_subject(img_pt)
                if clicked_id is not None:
                    for s in self._subjects:
                        if s["id"] == clicked_id:
                            s["selected"] = not s.get("selected", True)
                            self.subject_toggled.emit(s["id"], s["selected"])
                            break
                    self.selection_changed.emit(self.get_selected_subjects())
                    self.update()

    def wheelEvent(self, event: QWheelEvent):
        degrees = event.angleDelta().y() / 8.0
        steps = degrees / 15.0
        factor = 1.15 ** steps
        self.set_zoom(self._zoom * factor, center_on_mouse=event.position())
        event.accept()

    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)
        # Re-center if newly created
        if self._pixmap and not self._pixmap.isNull() and self._pan_offset == QPointF(0, 0):
            self.fit_to_page()

    # --- Painting ---
    def paintEvent(self, event: QPaintEvent):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        # 1. Dark checkboard or background
        vw, vh = self.width(), self.height()
        painter.fillRect(0, 0, vw, vh, QColor("#1e2124"))

        # 2. Draw Image if present
        if not self._pixmap or self._pixmap.isNull():
            painter.setPen(QColor("#808890"))
            font = QFont("Noto Sans", 11)
            painter.setFont(font)
            painter.drawText(
                0, 0, vw, vh,
                Qt.AlignmentFlag.AlignCenter,
                "Nessuna immagine scansionata.\nFai clic su 'Scansiona' per iniziare."
            )
            return

        pw = self._pixmap.width() * self._zoom
        ph = self._pixmap.height() * self._zoom
        img_rect = QRectF(self._pan_offset.x(), self._pan_offset.y(), pw, ph)

        # Drop shadow behind scanned paper
        shadow_rect = img_rect.adjusted(4, 4, 4, 4)
        painter.fillRect(shadow_rect, QColor(0, 0, 0, 75))

        # Scanned page
        painter.drawPixmap(img_rect.toRect(), self._pixmap)

        # Border around scanned paper
        painter.setPen(QPen(QColor("#50565e"), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(img_rect)

        # 3. Draw Single-Document Auto-Crop Indicator if set
        if self._crop_rect:
            cx, cy, cw, ch = self._crop_rect
            top_left = self.image_to_viewport(QPointF(cx, cy))
            view_w = cw * self._zoom
            view_h = ch * self._zoom
            crop_vrect = QRectF(top_left.x(), top_left.y(), view_w, view_h)

            crop_pen = QPen(QColor("#3daee9"), 2, Qt.PenStyle.DashLine)
            painter.setPen(crop_pen)
            painter.setBrush(QColor(61, 174, 233, 20))  # translucent highlight
            painter.drawRect(crop_vrect)

            # Draw L-shaped corner guides
            bracket_len = min(16.0, view_w / 4, view_h / 4)
            bpen = QPen(QColor("#3daee9"), 3)
            painter.setPen(bpen)
            # Top-left
            painter.drawLine(int(top_left.x()), int(top_left.y()), int(top_left.x() + bracket_len), int(top_left.y()))
            painter.drawLine(int(top_left.x()), int(top_left.y()), int(top_left.x()), int(top_left.y() + bracket_len))
            # Bottom-right
            br_x = top_left.x() + view_w
            br_y = top_left.y() + view_h
            painter.drawLine(int(br_x), int(br_y), int(br_x - bracket_len), int(br_y))
            painter.drawLine(int(br_x), int(br_y), int(br_x), int(br_y - bracket_len))

        # 4. Draw Multiple Detected Subjects (Photos, Receipts, Cards)
        for s in self._subjects:
            sid = s["id"]
            rx, ry, rw, rh = s["rect"]
            selected = s.get("selected", True)
            is_hovered = (sid == self._hovered_subject_id)
            base_col: QColor = s.get("color", QColor("#3daee9"))

            top_left = self.image_to_viewport(QPointF(rx, ry))
            sw = rw * self._zoom
            sh = rh * self._zoom
            subj_vrect = QRectF(top_left.x(), top_left.y(), sw, sh)

            # Fill translucent
            if selected:
                alpha = 60 if not is_hovered else 85
                fill_color = QColor(base_col.red(), base_col.green(), base_col.blue(), alpha)
                border_color = base_col
                border_width = 3 if is_hovered else 2
            else:
                alpha = 25
                fill_color = QColor(100, 100, 100, alpha)
                border_color = QColor(130, 135, 140, 160)
                border_width = 1

            painter.setPen(QPen(border_color, border_width))
            painter.setBrush(fill_color)
            painter.drawRoundedRect(subj_vrect, 4, 4)

            # Badge / Checkbox pill on top-left of the subject
            badge_h = 24.0
            badge_w = 90.0
            badge_rect = QRectF(top_left.x() + 4, top_left.y() + 4, badge_w, badge_h)

            painter.setPen(Qt.PenStyle.NoPen)
            badge_bg = QColor(25, 28, 31, 220) if selected else QColor(45, 48, 51, 180)
            painter.setBrush(badge_bg)
            painter.drawRoundedRect(badge_rect, 12, 12)

            # Checkmark indicator circle
            chk_circle = QRectF(badge_rect.x() + 4, badge_rect.y() + 4, 16, 16)
            chk_col = base_col if selected else QColor(120, 120, 120)
            painter.setBrush(chk_col)
            painter.drawEllipse(chk_circle)

            if selected:
                painter.setPen(QPen(QColor("#ffffff"), 2))
                # draw tiny checkmark
                painter.drawLine(
                    int(chk_circle.x() + 4), int(chk_circle.y() + 8),
                    int(chk_circle.x() + 7), int(chk_circle.y() + 11)
                )
                painter.drawLine(
                    int(chk_circle.x() + 7), int(chk_circle.y() + 11),
                    int(chk_circle.x() + 12), int(chk_circle.y() + 5)
                )

            # Label text
            painter.setPen(QColor("#ffffff") if selected else QColor("#aaaaaa"))
            font = QFont("Noto Sans", 8, QFont.Weight.Bold)
            painter.setFont(font)
            text_rect = QRectF(badge_rect.x() + 24, badge_rect.y(), badge_w - 26, badge_h)
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, f"#{sid}")


class InteractiveCanvas(QWidget):
    """
    Complete Canvas widget offering the interactive viewport plus a
    stylish floating/docked Breeze control bar for zoom, multi-subject
    toggles and selection tools.
    """
    subject_toggled = pyqtSignal(int, bool)
    selection_changed = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Top Control Bar (floating aesthetic with Breeze styling)
        self.control_bar = QFrame(self)
        self.control_bar.setStyleSheet("""
            QFrame {
                background-color: rgba(35, 38, 41, 0.92);
                border-bottom: 1px solid #444a50;
                padding: 2px 8px;
            }
        """)
        c_layout = QHBoxLayout(self.control_bar)
        c_layout.setContentsMargins(8, 4, 8, 4)
        c_layout.setSpacing(6)

        # Subject selection actions
        self.btn_select_all = QPushButton("Seleziona tutti", self.control_bar)
        self.btn_select_all.setIcon(get_kde_icon("edit-select-all"))
        self.btn_select_all.setToolTip("Seleziona tutti i soggetti rilevati")
        self.btn_select_all.clicked.connect(lambda: self.viewport.select_all_subjects(True))
        c_layout.addWidget(self.btn_select_all)

        self.btn_deselect_all = QPushButton("Deseleziona", self.control_bar)
        self.btn_deselect_all.setIcon(get_kde_icon("edit-clear"))
        self.btn_deselect_all.setToolTip("Deseleziona tutti i soggetti rilevati")
        self.btn_deselect_all.clicked.connect(lambda: self.viewport.select_all_subjects(False))
        c_layout.addWidget(self.btn_deselect_all)

        self.lbl_subject_count = QLabel("Nessun soggetto rilevato", self.control_bar)
        self.lbl_subject_count.setStyleSheet("color: #bdc3c7; font-size: 9pt; margin-left: 8px;")
        c_layout.addWidget(self.lbl_subject_count)

        c_layout.addStretch()

        # Zoom Controls
        self.btn_zoom_out = QToolButton(self.control_bar)
        self.btn_zoom_out.setIcon(get_kde_icon("zoom-out"))
        self.btn_zoom_out.setToolTip("Riduci zoom (o rotella mouse indietro)")
        self.btn_zoom_out.clicked.connect(self.zoom_out)
        c_layout.addWidget(self.btn_zoom_out)

        self.lbl_zoom = QLabel("100%", self.control_bar)
        self.lbl_zoom.setStyleSheet("font-weight: bold; min-width: 44px; text-align: center;")
        c_layout.addWidget(self.lbl_zoom)

        self.btn_zoom_in = QToolButton(self.control_bar)
        self.btn_zoom_in.setIcon(get_kde_icon("zoom-in"))
        self.btn_zoom_in.setToolTip("Aumenta zoom (o rotella mouse avanti)")
        self.btn_zoom_in.clicked.connect(self.zoom_in)
        c_layout.addWidget(self.btn_zoom_in)

        self.btn_fit_page = QToolButton(self.control_bar)
        self.btn_fit_page.setIcon(get_kde_icon("zoom-fit-best"))
        self.btn_fit_page.setToolTip("Adatta alla pagina")
        self.btn_fit_page.clicked.connect(self.fit_to_page)
        c_layout.addWidget(self.btn_fit_page)

        self.btn_fit_width = QToolButton(self.control_bar)
        self.btn_fit_width.setIcon(get_kde_icon("zoom-fit-width"))
        self.btn_fit_width.setToolTip("Adatta alla larghezza")
        self.btn_fit_width.clicked.connect(self.fit_to_width)
        c_layout.addWidget(self.btn_fit_width)

        layout.addWidget(self.control_bar)

        # Viewport
        self.viewport = CanvasViewport(self)
        self.viewport.zoom_changed.connect(self._on_zoom_changed)
        self.viewport.subject_toggled.connect(self.subject_toggled)
        self.viewport.selection_changed.connect(self._on_selection_changed)
        layout.addWidget(self.viewport, stretch=1)

    def set_image(self, image: Any):
        """Accepts QPixmap, QImage, PIL.Image, or cv2 np.ndarray."""
        if image is None:
            self.viewport.set_pixmap(None)
        elif isinstance(image, QPixmap):
            self.viewport.set_pixmap(image)
        elif isinstance(image, QImage):
            self.viewport.set_pixmap(QPixmap.fromImage(image))
        elif isinstance(image, Image.Image):
            self.viewport.set_pixmap(pil_to_qpixmap(image))
        elif isinstance(image, np.ndarray):
            self.viewport.set_pixmap(cv2_to_qpixmap(image))
        else:
            raise TypeError(f"Unsupported image type: {type(image)}")
        self._update_subject_label()

    def set_detected_subjects(self, subjects: List[Dict[str, Any]]):
        self.viewport.set_subjects(subjects)
        self._update_subject_label()

    def set_crop_rect(self, *args):
        self.viewport.set_crop_rect(*args)

    def get_selected_subjects(self) -> List[Dict[str, Any]]:
        return self.viewport.get_selected_subjects()

    def get_all_subjects(self) -> List[Dict[str, Any]]:
        return self.viewport.get_all_subjects()

    def fit_to_page(self):
        self.viewport.fit_to_page()

    def fit_to_width(self):
        self.viewport.fit_to_width()

    def zoom_in(self):
        self.viewport.zoom_in()

    def zoom_out(self):
        self.viewport.zoom_out()

    def reset_zoom(self):
        self.viewport.reset_zoom()

    def _on_zoom_changed(self, zoom: float):
        percent = int(round(zoom * 100))
        self.lbl_zoom.setText(f"{percent}%")

    def _on_selection_changed(self, selected_list: list):
        self._update_subject_label()
        self.selection_changed.emit(selected_list)

    def _update_subject_label(self):
        all_subs = self.viewport.get_all_subjects()
        sel_subs = self.viewport.get_selected_subjects()
        if not all_subs:
            self.lbl_subject_count.setText("Nessun soggetto rilevato")
            self.btn_select_all.setEnabled(False)
            self.btn_deselect_all.setEnabled(False)
        else:
            self.lbl_subject_count.setText(
                f"{len(sel_subs)} di {len(all_subs)} soggetti selezionati"
            )
            self.btn_select_all.setEnabled(True)
            self.btn_deselect_all.setEnabled(True)
