import os
import sys
import json
import urllib.request
import math
import uuid
import random
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLineEdit, QLabel, QSlider, QFrame, QScrollArea,
    QGridLayout, QButtonGroup, QGraphicsDropShadowEffect, QComboBox,
    QFileDialog, QMessageBox
)
from PyQt6.QtCore import (
    Qt, QThread, pyqtSignal, QUrl, QTimer, QDateTime, pyqtProperty,
    QPropertyAnimation, QEasingCurve, QPoint, QMimeData, QPointF, QRect
)
from PyQt6.QtGui import (
    QPixmap, QColor, QDrag, QPainter, QPen, QPainterPath, QBrush, QLinearGradient, QImage
)
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
import yt_dlp
import imageio_ffmpeg

# Safe non-blocking FFmpeg setup
try:
    ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
    if getattr(sys, 'frozen', False):
        try: os.chmod(ffmpeg_path, 0o755)
        except Exception: pass
    os.environ["PATH"] += os.pathsep + os.path.dirname(ffmpeg_path)
except Exception:
    pass

CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".soundcloud_turntable")
os.makedirs(CONFIG_DIR, exist_ok=True)
SAVE_FILE = os.path.join(CONFIG_DIR, "saved_playlists_steam_v2.json")
CACHE_DIR = os.path.join(CONFIG_DIR, "audio_cache")
os.makedirs(CACHE_DIR, exist_ok=True)

THEMES = {
    "Steam Classic": {
        "bg_main": "#171d25",
        "bg_sub": "#1b2838",
        "bg_card": "#16202d",
        "bg_card_selected": "#1b2838",
        "bg_element": "#10161d",
        "border": "#2a475e",
        "accent": "#1a9fff",
        "accent_hover": "#66c0f4",
        "text": "#c7d5e0",
        "text_dim": "#8f98a0"
    },
    "Cyberpunk Neon": {
        "bg_main": "#0b0b10",
        "bg_sub": "#13131c",
        "bg_card": "#181824",
        "bg_card_selected": "#222238",
        "bg_element": "#0f0f14",
        "border": "#ff007f",
        "accent": "#00f0ff",
        "accent_hover": "#70ffff",
        "text": "#ffffff",
        "text_dim": "#a0a0c0"
    },
    "Retro Vinyl": {
        "bg_main": "#1e1b18",
        "bg_sub": "#2c2621",
        "bg_card": "#352e28",
        "bg_card_selected": "#443a32",
        "bg_element": "#241f1c",
        "border": "#5c4e43",
        "accent": "#f39c12",
        "accent_hover": "#f1c40f",
        "text": "#f5e6d3",
        "text_dim": "#b8a491"
    },
    "OLED Midnight": {
        "bg_main": "#000000",
        "bg_sub": "#080808",
        "bg_card": "#121212",
        "bg_card_selected": "#1a1a1a",
        "bg_element": "#050505",
        "border": "#222222",
        "accent": "#2ecc71",
        "accent_hover": "#27ae60",
        "text": "#ffffff",
        "text_dim": "#777777"
    }
}

def format_time(ms):
    if ms <= 0: return "00:00"
    s = int(ms / 1000)
    return f"{s // 60:02d}:{s % 60:02d}"

class MyLogger:
    def debug(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg): print(msg)

class LoadingOverlay(QFrame):
    def __init__(self, theme, parent=None):
        super().__init__(parent)
        self.theme = theme
        self.setStyleSheet("background-color: rgba(10, 14, 20, 220);")

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.card = QFrame()
        self.card.setFixedSize(420, 180)

        card_layout = QVBoxLayout(self.card)
        card_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.setSpacing(12)

        self.op_label = QLabel("⏳ Processing Operation...")
        self.op_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(self.op_label)

        self.time_label = QLabel("Estimated time remaining: Calculating...")
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(self.time_label)

        layout.addWidget(self.card)

        self.update_card_style()
        self.hide()

    def update_theme(self, theme):
        self.theme = theme
        self.update_card_style()
        self.setStyleSheet("background-color: rgba(10, 14, 20, 220);")

    def update_card_style(self):
        self.card.setStyleSheet(f"""
            QFrame {{
                background-color: {self.theme['bg_card']};
                border: 2px solid {self.theme['accent']};
                border-radius: 12px;
            }}
            QLabel {{
                color: {self.theme['text']};
                font-size: 14px;
                font-weight: bold;
                border: none;
                background: transparent;
            }}
        """)
        self.time_label.setStyleSheet(f"color: {self.theme['accent']}; font-size: 12px; font-weight: bold; border: none; background: transparent;")

    def show_loading(self, operation_text, estimated_seconds=2):
        self.op_label.setText(f"⏳ {operation_text}")
        self.time_label.setText(f"Estimated time remaining: ~{estimated_seconds}s")
        if self.parent():
            self.resize(self.parent().size())
        self.show()
        self.raise_()

    def mousePressEvent(self, event): event.accept()
    def mouseReleaseEvent(self, event): event.accept()
    def mouseMoveEvent(self, event): event.accept()

    def resizeEvent(self, event):
        if self.parent():
            self.resize(self.parent().size())
        super().resizeEvent(event)

class ToastNotification(QFrame):
    import_requested = pyqtSignal(str)

    def __init__(self, theme, parent=None):
        super().__init__(parent)
        self.theme = theme
        self.detected_url = ""
        self.setFixedHeight(50)
        self.setFixedWidth(380)
        self.update_style()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)

        self.lbl = QLabel("📋 Clipboard link detected!")
        layout.addWidget(self.lbl)
        layout.addStretch()

        self.import_btn = QPushButton("Import")
        self.import_btn.clicked.connect(self.on_import)
        layout.addWidget(self.import_btn)

        close_btn = QPushButton("✕")
        close_btn.setFixedWidth(24)
        close_btn.setStyleSheet("background-color: transparent; color: #8f98a0; border: none;")
        close_btn.clicked.connect(self.hide)
        layout.addWidget(close_btn)

        self.hide()

    def update_theme(self, theme):
        self.theme = theme
        self.update_style()

    def update_style(self):
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {self.theme['bg_element']};
                border: 2px solid {self.theme['accent']};
                border-radius: 8px;
            }}
            QLabel {{ color: {self.theme['text']}; font-weight: bold; font-size: 12px; border: none; background: transparent; }}
            QPushButton {{ background-color: {self.theme['accent']}; color: white; border-radius: 4px; padding: 4px 10px; font-weight: bold; border: none; }}
            QPushButton:hover {{ background-color: {self.theme['accent_hover']}; }}
        """)

    def show_toast(self, url):
        self.detected_url = url
        self.show()
        self.raise_()

    def on_import(self):
        if self.detected_url:
            self.import_requested.emit(self.detected_url)
        self.hide()

class FavoriteButton(QPushButton):
    def __init__(self, is_fav=False, theme=None, parent=None):
        super().__init__(parent)
        self.is_fav = is_fav
        self.theme = theme or THEMES["Steam Classic"]
        self._scale_factor = 1.0
        self.setFixedSize(32, 32)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self.pop_anim = QPropertyAnimation(self, b"scale_factor")
        self.pop_anim.setDuration(350)
        self.pop_anim.setEasingCurve(QEasingCurve.Type.OutBack)

    def get_scale(self): return self._scale_factor
    def set_scale(self, s):
        self._scale_factor = s
        self.update()
    scale_factor = pyqtProperty(float, get_scale, set_scale)

    def trigger_pop(self):
        self.pop_anim.stop()
        self.pop_anim.setStartValue(1.4)
        self.pop_anim.setEndValue(1.0)
        self.pop_anim.start()

    def set_favorite(self, is_fav):
        self.is_fav = is_fav
        self.trigger_pop()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect()
        cx, cy = rect.width() / 2, rect.height() / 2

        painter.translate(cx, cy)
        painter.scale(self._scale_factor, self._scale_factor)
        painter.translate(-cx, -cy)

        bg_color = QColor(self.theme['accent']) if self.underMouse() else QColor(16, 22, 29, 230)
        border_color = QColor(self.theme['accent_hover']) if self.underMouse() else QColor(self.theme['accent'])

        painter.setBrush(QBrush(bg_color))
        painter.setPen(QPen(border_color, 1.5))
        painter.drawEllipse(rect.adjusted(1, 1, -1, -1))

        path = QPainterPath()
        path.moveTo(cx, cy + 6)
        path.cubicTo(cx - 9, cy - 1, cx - 9, cy - 8, cx - 3.5, cy - 8)
        path.cubicTo(cx, cy - 8, cx, cy - 4, cx, cy - 4)
        path.cubicTo(cx, cy - 4, cx, cy - 8, cx + 3.5, cy - 8)
        path.cubicTo(cx + 9, cy - 8, cx + 9, cy - 1, cx, cy + 6)

        if self.is_fav:
            heart_color = QColor("#ff4757") if not self.underMouse() else QColor("#ffffff")
            painter.setBrush(QBrush(heart_color))
            painter.setPen(Qt.PenStyle.NoPen)
        else:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(self.theme['text']), 2))

        painter.drawPath(path)

class TurntableWidget(QWidget):
    track_dropped = pyqtSignal(int, int)
    tonearm_toggled = pyqtSignal(bool)

    def __init__(self, theme, parent=None):
        super().__init__(parent)
        self.theme = theme
        self.setAcceptDrops(True)
        self.setMinimumWidth(360)
        self.angle = 0
        self._arm_angle = 0.0
        self.is_playing = False
        self.current_art = None
        self.ambient_color = QColor("#1a9fff")
        self.playback_rate = 1.0
        self.is_dragging_arm = False

        self.arm_anim = QPropertyAnimation(self, b"arm_angle")
        self.arm_anim.setDuration(600)
        self.arm_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.rotate_vinyl)
        self.timer.start(30)

    def update_theme(self, theme):
        self.theme = theme
        if not self.current_art:
            self.ambient_color = QColor(theme['accent'])
        self.update()

    def get_arm_angle(self): return self._arm_angle
    def set_arm_angle(self, a):
        self._arm_angle = a
        self.update()
    arm_angle = pyqtProperty(float, get_arm_angle, set_arm_angle)

    def set_playback_rate(self, rate):
        self.playback_rate = rate

    def rotate_vinyl(self):
        if self.is_playing:
            self.angle = (self.angle + (2.5 * self.playback_rate)) % 360
            self.update()

    def set_playing(self, playing):
        self.is_playing = playing
        self.arm_anim.stop()
        self.arm_anim.setEndValue(28.0 if playing else 0.0)
        self.arm_anim.start()

    def set_art(self, pixmap):
        self.current_art = pixmap
        self.angle = 0
        if pixmap and not pixmap.isNull():
            img = pixmap.toImage().scaled(10, 10)
            c = img.pixelColor(5, 5)
            self.ambient_color = QColor(c.red(), c.green(), c.blue())
        else:
            self.ambient_color = QColor(self.theme['accent'])
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            rect = self.rect()
            pivot_x = rect.width() - 40
            pivot_y = 50
            if math.hypot(event.pos().x() - pivot_x, event.pos().y() - pivot_y) < 220:
                self.is_dragging_arm = True
                self.arm_anim.stop()
                self.update_arm_drag(event.pos())

    def mouseMoveEvent(self, event):
        if self.is_dragging_arm:
            self.update_arm_drag(event.pos())

    def mouseReleaseEvent(self, event):
        if self.is_dragging_arm:
            self.is_dragging_arm = False
            should_play = self._arm_angle > 14.0
            self.arm_anim.stop()
            self.arm_anim.setEndValue(28.0 if should_play else 0.0)
            self.arm_anim.start()
            self.tonearm_toggled.emit(should_play)

    def update_arm_drag(self, pos):
        rect = self.rect()
        pivot_x = rect.width() - 40
        pivot_y = 50
        radius = min(rect.width() / 2, rect.height() / 2) - 30
        dx = pos.x() - pivot_x
        dy = pos.y() - pivot_y
        base_angle = math.degrees(math.atan2(radius - 10, -40))
        delta = math.degrees(math.atan2(dy, dx)) - base_angle
        self._arm_angle = max(0.0, min(32.0, delta))
        self.update()

    def dragEnterEvent(self, event):
        if event.mimeData().hasText() and event.mimeData().text().startswith("record:"):
            event.acceptProposedAction()

    def dropEvent(self, event):
        data = event.mimeData().text().split(":")[1]
        g_idx, t_idx = map(int, data.split(","))
        self.track_dropped.emit(g_idx, t_idx)
        event.acceptProposedAction()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect()
        cx, cy = rect.width() / 2, rect.height() / 2
        radius = min(cx, cy) - 30

        painter.fillRect(rect, QColor(self.theme['bg_main']))

        if self.is_playing:
            glow_grad = QLinearGradient(cx, cy - radius, cx, cy + radius)
            glow_grad.setColorAt(0.0, QColor(self.ambient_color.red(), self.ambient_color.green(), self.ambient_color.blue(), 40))
            glow_grad.setColorAt(1.0, QColor(0, 0, 0, 0))
            painter.setBrush(QBrush(glow_grad))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QPointF(cx, cy), radius + 20, radius + 20)

        painter.setPen(QPen(QColor(self.theme['border']), 4))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(rect)

        if not self.is_playing and not self.current_art:
            painter.setPen(QPen(QColor(self.theme['border']), 2, Qt.PenStyle.DashLine))
            painter.drawEllipse(QPointF(cx, cy), radius, radius)
            painter.setPen(QColor(self.theme['text_dim']))
            font = painter.font()
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "DRAG RECORD HERE\nOR PULL TONEARM TO PLAY")
        else:
            painter.setBrush(QColor("#0d0d0d"))
            painter.setPen(QColor("#222222"))
            painter.drawEllipse(QPointF(cx, cy), radius, radius)

            painter.setPen(QPen(QColor("#1a1a1a"), 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            for i in range(1, 6):
                painter.drawEllipse(QPointF(cx, cy), radius - (i * 12), radius - (i * 12))

            shine_grad = QLinearGradient(cx - radius, cy - radius, cx + radius, cy + radius)
            shine_grad.setColorAt(0.0, QColor(255, 255, 255, 0))
            shine_grad.setColorAt(0.48, QColor(255, 255, 255, 12))
            shine_grad.setColorAt(0.50, QColor(255, 255, 255, 30))
            shine_grad.setColorAt(0.52, QColor(255, 255, 255, 12))
            shine_grad.setColorAt(1.0, QColor(255, 255, 255, 0))
            painter.setBrush(QBrush(shine_grad))
            painter.drawEllipse(QPointF(cx, cy), radius, radius)

            painter.translate(cx, cy)
            painter.rotate(self.angle)

            label_radius = radius * 0.35
            if self.current_art and not self.current_art.isNull():
                path = QPainterPath()
                path.addEllipse(QPointF(0, 0), label_radius, label_radius)
                painter.setClipPath(path)
                scaled_art = self.current_art.scaled(
                    int(label_radius * 2), int(label_radius * 2),
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation
                )
                painter.drawPixmap(int(-label_radius), int(-label_radius), scaled_art)
            else:
                painter.setBrush(QColor(self.theme['accent']))
                painter.drawEllipse(QPointF(0, 0), label_radius, label_radius)

            painter.setClipRect(QRect(-999, -999, 1998, 1998))
            painter.setBrush(QColor(self.theme['bg_main']))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QPointF(0, 0), 4, 4)

            painter.resetTransform()

        pivot_x = rect.width() - 40
        pivot_y = 50

        painter.translate(pivot_x, pivot_y)
        painter.rotate(self._arm_angle)

        arm_color = QColor(self.theme['accent_hover']) if self.is_dragging_arm else QColor(self.theme['text'])
        painter.setPen(QPen(arm_color, 5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(0, 0, -40, int(radius - 10))

        painter.translate(-40, int(radius - 10))
        painter.rotate(15)
        painter.setBrush(QColor("#111111"))
        painter.setPen(QColor(self.theme['accent']) if self.is_dragging_arm else QColor("#333333"))
        painter.drawRect(-8, 0, 16, 25)

        painter.resetTransform()
        painter.setBrush(QColor("#333333"))
        painter.setPen(QColor("#111111"))
        painter.drawEllipse(QPointF(pivot_x, pivot_y), 15, 15)
        painter.setBrush(QColor(self.theme['accent']))
        painter.drawEllipse(QPointF(pivot_x, pivot_y), 4, 4)

class MediaCardWidget(QFrame):
    clicked = pyqtSignal(int, int, object)
    favorite_toggled = pyqtSignal(dict, bool)

    def __init__(self, track_data, group_title, g_idx, t_idx, theme, parent_player=None):
        super().__init__()
        self.track_data = track_data
        self.group_title = group_title
        self.g_idx = g_idx
        self.t_idx = t_idx
        self.theme = theme
        self.parent_player = parent_player
        self.is_selected = False
        self.drag_start_pos = None
        self.current_pixmap = None

        self.setFixedSize(160, 240)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.update_style()

        self.shadow = QGraphicsDropShadowEffect(self)
        self.shadow.setBlurRadius(0)
        self.shadow.setColor(QColor(self.theme['accent']))
        self.shadow.setOffset(0, 0)
        self.setGraphicsEffect(self.shadow)

        self.glow_anim = QPropertyAnimation(self.shadow, b"blurRadius")
        self.glow_anim.setDuration(200)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.art_container = QWidget(self)
        self.art_container.setFixedSize(160, 170)
        art_layout = QVBoxLayout(self.art_container)
        art_layout.setContentsMargins(0, 0, 0, 0)

        self.art_label = QLabel(self.art_container)
        self.art_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.art_label.setFixedSize(160, 170)
        art_layout.addWidget(self.art_label)
        layout.addWidget(self.art_container)

        info_widget = QWidget()
        info_layout = QVBoxLayout(info_widget)
        info_layout.setContentsMargins(8, 8, 8, 8)
        self.title_label = QLabel(track_data.get('title', 'Unknown Track'))
        self.title_label.setWordWrap(True)
        self.title_label.setStyleSheet(f"color: {self.theme['text']}; font-size: 11px; font-weight: bold; border: none; background: transparent;")
        info_layout.addWidget(self.title_label)
        layout.addWidget(info_widget)

        is_fav = self.track_data.get('favorite', False)
        self.fav_btn = FavoriteButton(is_fav, self.theme, self.art_container)
        self.fav_btn.move(120, 8)
        self.fav_btn.clicked.connect(self.on_fav_clicked)
        self.fav_btn.show()
        self.fav_btn.raise_()

        thumb_path = track_data.get('thumbnail_path')
        if thumb_path and os.path.exists(thumb_path):
            self.update_art(thumb_path)
        else:
            self.art_label.setText("🎵")
            self.art_label.setStyleSheet(f"color: {self.theme['accent']}; font-size: 32px; background-color: {self.theme['bg_element']}; border-top-left-radius: 6px; border-top-right-radius: 6px;")

    def update_theme(self, theme):
        self.theme = theme
        self.shadow.setColor(QColor(theme['accent']))
        self.title_label.setStyleSheet(f"color: {theme['text']}; font-size: 11px; font-weight: bold; border: none; background: transparent;")
        self.fav_btn.theme = theme
        self.fav_btn.update()
        self.set_selected(self.is_selected)

    def update_style(self):
        bg = self.theme['bg_card_selected'] if self.is_selected else self.theme['bg_card']
        border = self.theme['accent'] if self.is_selected else self.theme['border']
        self.setStyleSheet(f"MediaCardWidget {{ background-color: {bg}; border: 2px solid {border}; border-radius: 8px; }}")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_start_pos = event.pos()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if self.drag_start_pos and (event.pos() - self.drag_start_pos).manhattanLength() < 5:
            self.clicked.emit(self.g_idx, self.t_idx, self)
        super().mouseReleaseEvent(event)

    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.MouseButton.LeftButton) or not self.drag_start_pos: return
        if (event.pos() - self.drag_start_pos).manhattanLength() < QApplication.startDragDistance(): return

        drag = QDrag(self)
        mime_data = QMimeData()
        mime_data.setText(f"record:{self.g_idx},{self.t_idx}")
        drag.setMimeData(mime_data)

        drag_pixmap = QPixmap(100, 100)
        drag_pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(drag_pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor("#0a0a0a"))
        painter.setPen(QColor("#333"))
        painter.drawEllipse(0, 0, 100, 100)

        if self.current_pixmap:
            path = QPainterPath()
            path.addEllipse(QPointF(50, 50), 30, 30)
            painter.setClipPath(path)
            scaled = self.current_pixmap.scaled(60, 60, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
            painter.drawPixmap(20, 20, scaled)
        else:
            painter.setBrush(QColor(self.theme['accent']))
            painter.drawEllipse(20, 20, 60, 60)
        painter.end()

        drag.setPixmap(drag_pixmap)
        drag.setHotSpot(QPoint(50, 50))
        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        drag.exec(Qt.DropAction.CopyAction)
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def on_fav_clicked(self):
        new_fav_state = not self.track_data.get('favorite', False)
        self.track_data['favorite'] = new_fav_state
        self.fav_btn.set_favorite(new_fav_state)
        self.favorite_toggled.emit(self.track_data, new_fav_state)

    def enterEvent(self, event):
        if not self.is_selected: self.animate_glow(14)
        super().enterEvent(event)

    def leaveEvent(self, event):
        if not self.is_selected: self.animate_glow(0)
        super().leaveEvent(event)

    def animate_glow(self, radius):
        self.glow_anim.stop()
        self.glow_anim.setEndValue(radius)
        self.glow_anim.start()

    def update_art(self, image_path):
        if image_path and os.path.exists(image_path):
            pixmap = QPixmap(image_path)
            if not pixmap.isNull():
                self.current_pixmap = pixmap
                scaled = pixmap.scaled(160, 170, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
                self.art_label.setPixmap(scaled)
                self.art_label.setText("")
                self.art_label.setStyleSheet(f"background-color: {self.theme['bg_element']}; border-top-left-radius: 6px; border-top-right-radius: 6px;")
                self.fav_btn.raise_()

    def set_selected(self, selected):
        self.is_selected = selected
        if selected:
            self.animate_glow(22)
            self.setStyleSheet(f"MediaCardWidget {{ background-color: {self.theme['bg_card_selected']}; border: 2px solid {self.theme['accent']}; border-radius: 8px; }}")
        else:
            self.animate_glow(0)
            self.setStyleSheet(f"MediaCardWidget {{ background-color: {self.theme['bg_card']}; border: 2px solid {self.theme['border']}; border-radius: 8px; }}")

class BatchThumbnailWorker(QThread):
    thumbnail_loaded = pyqtSignal(str, str)
    def __init__(self, tracks): super().__init__(); self.tracks = tracks
    def run(self):
        ydl_opts = {'quiet': True, 'skip_download': True, 'logger': MyLogger()}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            for item in self.tracks:
                url = item.get('url')
                if not url: continue
                try:
                    thumb_url = item.get('thumbnail_url')
                    if not thumb_url:
                        info = ydl.extract_info(url, download=False)
                        if info: thumb_url = info.get('thumbnail')
                    if thumb_url:
                        local_path = os.path.join(CACHE_DIR, f"thumb_{uuid.uuid4()}.jpg")
                        req = urllib.request.Request(thumb_url, headers={'User-Agent': 'Mozilla/5.0'})
                        with urllib.request.urlopen(req, timeout=8) as res:
                            with open(local_path, 'wb') as f: f.write(res.read())
                        self.thumbnail_loaded.emit(url, local_path)
                except Exception: pass

class SoundCloudWorker(QThread):
    data_ready = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)
    def __init__(self, url, format_str): super().__init__(); self.url = url; self.format_str = format_str
    def run(self):
        try:
            with yt_dlp.YoutubeDL({'format': self.format_str, 'quiet': True, 'ignoreerrors': True, 'logger': MyLogger()}) as ydl:
                info = ydl.extract_info(self.url, download=False)
                if info: self.data_ready.emit(info)
                else: self.error_occurred.emit("Could not parse URL")
        except Exception as e: self.error_occurred.emit(str(e))

class AudioDownloadWorker(QThread):
    audio_ready = pyqtSignal(str, str, str, bytes, int)
    error_occurred = pyqtSignal(str)
    def __init__(self, track_url, track_title, format_str): super().__init__(); self.track_url = track_url; self.track_title = track_title; self.format_str = format_str
    def run(self):
        try:
            outtmpl = os.path.join(CACHE_DIR, f"{uuid.uuid4()}.%(ext)s")
            with yt_dlp.YoutubeDL({'format': self.format_str, 'outtmpl': outtmpl, 'quiet': True, 'logger': MyLogger()}) as ydl:
                info = ydl.extract_info(self.track_url, download=True)
                path = info['requested_downloads'][0]['filepath'] if 'requested_downloads' in info else ydl.prepare_filename(info)
                duration_ms = int(info.get('duration', 0) * 1000)
            self.audio_ready.emit(path, self.track_title, self.track_url, b"", duration_ms)
        except Exception as e: self.error_occurred.emit(str(e))

class AnimatedPlaylistSection(QWidget):
    def __init__(self, title, track_count, g_idx, parent_player):
        super().__init__()
        self.g_idx = g_idx
        self.parent_player = parent_player
        self.is_expanded = g_idx not in parent_player.collapsed_playlists
        self.theme = parent_player.current_theme

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 10)

        self.header_frame = QFrame()
        self.header_frame.setCursor(Qt.CursorShape.PointingHandCursor)
        self.update_header_style()

        header_layout = QHBoxLayout(self.header_frame)
        icon_str = "▼" if self.is_expanded else "►"
        self.toggle_lbl = QLabel(f"{icon_str}  <b>📁 {title}</b>  ({track_count} tracks)")
        self.toggle_lbl.setStyleSheet(f"color: {self.theme['text']}; font-size: 13px; border: none; background: transparent;")
        header_layout.addWidget(self.toggle_lbl)
        header_layout.addStretch()
        self.header_frame.mousePressEvent = self.toggle_collapse
        self.main_layout.addWidget(self.header_frame)

        self.body_widget = QWidget()
        self.body_layout = QGridLayout(self.body_widget)
        self.body_layout.setContentsMargins(10, 8, 10, 8)
        self.body_layout.setHorizontalSpacing(20)
        self.body_layout.setVerticalSpacing(20)
        self.main_layout.addWidget(self.body_widget)

        if not self.is_expanded:
            self.body_widget.hide()

    def update_theme(self, theme):
        self.theme = theme
        self.update_header_style()
        self.toggle_lbl.setStyleSheet(f"color: {theme['text']}; font-size: 13px; border: none; background: transparent;")

    def update_header_style(self):
        self.header_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {self.theme['bg_element']};
                border: 1px solid {self.theme['border']};
                border-radius: 6px;
            }}
            QFrame:hover {{
                background-color: {self.theme['bg_card']};
                border: 1px solid {self.theme['accent']};
            }}
        """)

    def toggle_collapse(self, event=None):
        self.is_expanded = not self.is_expanded
        if self.is_expanded:
            if self.g_idx in self.parent_player.collapsed_playlists: self.parent_player.collapsed_playlists.remove(self.g_idx)
            self.toggle_lbl.setText(self.toggle_lbl.text().replace("►", "▼"))
            self.body_widget.show()
        else:
            self.parent_player.collapsed_playlists.add(self.g_idx)
            self.toggle_lbl.setText(self.toggle_lbl.text().replace("▼", "►"))
            self.body_widget.hide()
        self.parent_player.refresh_grid()

class SteamOSMediaPlayer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SteamOS Gamepad Media Deck")
        self.resize(1360, 850)

        self.playlist_groups = []
        self.collapsed_playlists = set()
        self.current_group_idx = 0
        self.current_track_idx = 0
        self.current_volume = 0.8
        self.is_slider_down = False
        self.track_duration = 0
        self.current_filter = "ALL"
        self.last_clipboard = ""
        self.is_loop_enabled = False
        self.current_theme = THEMES["Steam Classic"]

        self.sleep_timer = QTimer(self)
        self.sleep_timer.setSingleShot(True)
        self.sleep_timer.timeout.connect(self.trigger_sleep_fade)

        self.audio_output = QAudioOutput()
        self.audio_output.setVolume(self.current_volume)
        self.media_player = QMediaPlayer()
        self.media_player.setAudioOutput(self.audio_output)
        self.media_player.mediaStatusChanged.connect(self.handle_media_status)

        self.progress_timer = QTimer(self)
        self.progress_timer.setInterval(200)
        self.progress_timer.timeout.connect(self.update_timeline)
        self.progress_timer.start()

        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self.update_header_clock)
        self.clock_timer.start(1000)

        self.clipboard_timer = QTimer(self)
        self.clipboard_timer.timeout.connect(self.check_clipboard)
        self.clipboard_timer.start(1500)

        self.init_ui()

        QTimer.singleShot(50, self.trigger_startup_loading)

    def trigger_startup_loading(self):
        self.loading_overlay.show_loading("Loading Saved Playlists", estimated_seconds=1)
        QTimer.singleShot(100, self.delayed_startup_load)

    def delayed_startup_load(self):
        try:
            self.load_playlist_from_disk()
            self.update_header_clock()
            self.refresh_grid()
        except Exception as e:
            print(f"Startup load error: {e}")
        finally:
            self.loading_overlay.hide()
            QTimer.singleShot(100, self.fetch_missing_thumbnails)

    def change_theme(self, theme_name):
        if theme_name in THEMES:
            self.current_theme = THEMES[theme_name]
            self.apply_theme_to_ui()

    def apply_theme_to_ui(self):
        t = self.current_theme

        self.header_frame.setStyleSheet(f"background-color: {t['bg_main']}; border-bottom: 1px solid {t['border']};")
        self.search_box.setStyleSheet(f"QLineEdit {{ background-color: {t['bg_element']}; color: {t['text']}; border: 1px solid {t['border']}; border-radius: 6px; padding: 4px; }}")
        self.url_input.setStyleSheet(f"QLineEdit {{ background-color: {t['bg_element']}; color: {t['text']}; border: 1px solid {t['border']}; border-radius: 6px; padding: 4px; }}")
        self.clock_label.setStyleSheet(f"font-weight: bold; color: {t['text']}; font-size: 13px; margin-left: 15px;")

        self.shuffle_btn.setStyleSheet(f"QPushButton {{ background-color: {t['bg_card']}; color: {t['text']}; border: 1px solid {t['border']}; border-radius: 14px; padding: 6px 12px; font-weight: bold; }} QPushButton:hover {{ background-color: {t['accent']}; color: white; }}")
        self.import_json_btn.setStyleSheet(f"QPushButton {{ background-color: {t['bg_card']}; color: {t['text']}; border: 1px solid {t['border']}; border-radius: 14px; padding: 6px 12px; font-weight: bold; }} QPushButton:hover {{ background-color: {t['accent']}; color: white; }}")
        self.clear_all_btn.setStyleSheet(f"QPushButton {{ background-color: {t['bg_card']}; color: #ff4757; border: 1px solid {t['border']}; border-radius: 14px; padding: 6px 12px; font-weight: bold; }} QPushButton:hover {{ background-color: #ff4757; color: white; }}")
        self.import_btn.setStyleSheet(f"QPushButton {{ background-color: {t['accent']}; color: white; border-radius: 14px; padding: 8px 18px; font-weight: bold; border: none; }} QPushButton:hover {{ background-color: {t['accent_hover']}; }}")

        self.tabs_frame.setStyleSheet(f"background-color: {t['bg_sub']}; border-bottom: 1px solid {t['border']};")
        for btn in self.filter_btn_group.buttons():
            btn.setStyleSheet(f"QPushButton {{ background-color: transparent; color: {t['text_dim']}; border: none; font-weight: bold; font-size: 13px; padding: 6px 12px; border-radius: 4px; }} QPushButton:checked {{ background-color: {t['accent']}; color: white; }}")

        self.sleep_btn.setStyleSheet(f"QPushButton {{ background-color: transparent; color: {t['text_dim']}; border: none; font-weight: bold; font-size: 12px; }} QPushButton:hover {{ color: {t['accent']}; }}")
        self.theme_combo.setStyleSheet(f"QComboBox {{ background-color: {t['bg_element']}; color: {t['text']}; border: 1px solid {t['border']}; border-radius: 4px; padding: 2px 6px; font-weight: bold; }} QComboBox::drop-down {{ border: none; }}")

        self.scroll_area.setStyleSheet(f"QScrollArea {{ background-color: transparent; border: none; border-right: 1px solid {t['border']}; }}")
        self.grid_container.setStyleSheet(f"background-color: {t['bg_sub']};")

        self.footer_frame.setStyleSheet(f"background-color: {t['bg_main']}; border-top: 1px solid {t['border']};")
        self.timeline_slider.setStyleSheet(f"QSlider::groove:horizontal {{ background: {t['bg_element']}; height: 6px; border-radius: 3px; }} QSlider::sub-page:horizontal {{ background: {t['accent']}; border-radius: 3px; }} QSlider::handle:horizontal {{ background: white; width: 14px; margin: -4px 0; border-radius: 7px; }}")
        self.time_current_label.setStyleSheet(f"color: {t['text']};")
        self.time_total_label.setStyleSheet(f"color: {t['text']};")
        self.now_playing_label.setStyleSheet(f"font-weight: bold; color: {t['accent']}; font-size: 12px;")

        side_btn_style = f"""
            QPushButton {{
                background-color: {t['bg_element']};
                color: {t['text']};
                border: 1px solid {t['border']};
                border-radius: 8px;
                padding: 8px 18px;
                font-weight: bold;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background-color: {t['bg_card']};
                border: 1px solid {t['accent']};
            }}
        """
        primary_btn_style = f"""
            QPushButton {{
                background-color: {t['accent']};
                color: #ffffff;
                border: none;
                border-radius: 8px;
                padding: 8px 24px;
                font-weight: bold;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background-color: {t['accent_hover']};
            }}
        """
        self.prev_btn.setStyleSheet(side_btn_style)
        self.play_pause_btn.setStyleSheet(primary_btn_style)
        self.next_btn.setStyleSheet(side_btn_style)

        if self.is_loop_enabled:
            self.loop_btn.setStyleSheet(f"QPushButton {{ background-color: {t['accent']}; color: #ffffff; border: none; border-radius: 8px; padding: 8px 14px; font-weight: bold; font-size: 13px; }}")
        else:
            self.loop_btn.setStyleSheet(side_btn_style)

        self.turntable.update_theme(t)
        self.toast.update_theme(t)
        self.loading_overlay.update_theme(t)
        self.refresh_grid()

    def check_clipboard(self):
        cb = QApplication.clipboard().text().strip()
        if cb and cb != self.last_clipboard and ("youtube.com" in cb or "youtu.be" in cb or "soundcloud.com" in cb):
            self.last_clipboard = cb
            self.toast.show_toast(cb)

    def trigger_sleep_fade(self):
        self.media_player.pause()
        self.turntable.set_playing(False)
        self.play_pause_btn.setText("▶ Play")
        self.now_playing_label.setText("SLEEP TIMER EXPIRED")

    def set_sleep_timer(self, mins):
        if mins == 0:
            self.sleep_timer.stop()
            self.sleep_btn.setText("🌙 Sleep")
        else:
            self.sleep_timer.start(mins * 60 * 1000)
            self.sleep_btn.setText(f"🌙 {mins}m")

    def update_header_clock(self):
        if hasattr(self, 'clock_label'): self.clock_label.setText(QDateTime.currentDateTime().toString("h:mm AP"))

    def update_timeline(self):
        if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            pos = self.media_player.position()
            dur = self.media_player.duration() or self.track_duration

            if dur > 0:
                self.timeline_slider.setMaximum(dur)
                self.time_total_label.setText(format_time(dur))
            if not self.is_slider_down: self.timeline_slider.setValue(pos)
            self.time_current_label.setText(format_time(pos))

    def handle_media_status(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            if self.is_loop_enabled:
                self.media_player.setPosition(0)
                self.media_player.play()
            else:
                self.play_next_track()

    def toggle_loop_mode(self):
        self.is_loop_enabled = not self.is_loop_enabled
        t = self.current_theme
        if self.is_loop_enabled:
            self.loop_btn.setStyleSheet(f"QPushButton {{ background-color: {t['accent']}; color: #ffffff; border: none; border-radius: 8px; padding: 8px 14px; font-weight: bold; font-size: 13px; }}")
        else:
            self.loop_btn.setStyleSheet(f"QPushButton {{ background-color: {t['bg_element']}; color: {t['text']}; border: 1px solid {t['border']}; border-radius: 8px; padding: 8px 14px; font-weight: bold; font-size: 13px; }}")

    def save_playlist_to_disk(self):
        try:
            with open(SAVE_FILE, 'w') as f: json.dump(self.playlist_groups, f, indent=2)
        except Exception: pass

    def load_playlist_from_disk(self):
        if os.path.exists(SAVE_FILE):
            try:
                with open(SAVE_FILE, 'r') as f:
                    data = json.load(f)
                    if isinstance(data, list) and len(data) > 0: self.playlist_groups = data
            except Exception: pass

    def clear_all_data(self):
        confirm = QMessageBox.question(
            self,
            "Clear All Data",
            "Are you sure you want to delete all saved playlists, cached audio, and thumbnails?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if confirm != QMessageBox.StandardButton.Yes:
            return

        # 1. Stop playback & turntable
        self.media_player.stop()
        self.turntable.set_playing(False)
        self.turntable.set_art(QPixmap())

        # 2. Delete saved JSON playlist file
        if os.path.exists(SAVE_FILE):
            try:
                os.remove(SAVE_FILE)
            except Exception as e:
                print(f"Error removing save file: {e}")

        # 3. Clear audio cache & thumbnail cache
        if os.path.exists(CACHE_DIR):
            for filename in os.listdir(CACHE_DIR):
                file_path = os.path.join(CACHE_DIR, filename)
                try:
                    if os.path.isfile(file_path):
                        os.remove(file_path)
                except Exception as e:
                    print(f"Error removing cache file: {e}")

        # 4. Reset internal state
        self.playlist_groups = []
        self.collapsed_playlists.clear()
        self.current_group_idx = 0
        self.current_track_idx = 0
        self.track_duration = 0

        # 5. Reset UI components
        self.search_box.clear()
        self.url_input.clear()
        self.timeline_slider.setValue(0)
        self.time_current_label.setText("00:00")
        self.time_total_label.setText("00:00")
        self.now_playing_label.setText("ALL DATA CLEARED")

        # 6. Redraw empty grid
        self.refresh_grid()

    def import_json_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Import Playlist JSON", CONFIG_DIR, "JSON Files (*.json)")
        if file_path:
            self.loading_overlay.show_loading(f"Importing {os.path.basename(file_path)}", estimated_seconds=1)
            QTimer.singleShot(50, lambda: self.process_json_import(file_path))

    def process_json_import(self, file_path):
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
                if isinstance(data, list):
                    self.playlist_groups.extend(data)
                    self.save_playlist_to_disk()
                    self.refresh_grid()
                    self.fetch_missing_thumbnails()
                    self.now_playing_label.setText(f"IMPORTED JSON: {os.path.basename(file_path)}")
        except Exception:
            self.now_playing_label.setText("ERROR IMPORTING JSON FILE")
        finally:
            self.loading_overlay.hide()

    def on_favorite_toggled(self, track_data, is_fav):
        self.save_playlist_to_disk()
        if self.current_filter == "FAVORITES": self.refresh_grid()

    def fetch_missing_thumbnails(self):
        missing = [t for g in self.playlist_groups for t in g.get('tracks', []) if not t.get('thumbnail_path') or not os.path.exists(t.get('thumbnail_path'))]
        if missing:
            self.thumb_worker = BatchThumbnailWorker(missing)
            self.thumb_worker.thumbnail_loaded.connect(self.on_thumbnail_cached)
            self.thumb_worker.start()

    def on_thumbnail_cached(self, track_url, local_path):
        for g in self.playlist_groups:
            for t in g.get('tracks', []):
                if t.get('url') == track_url: t['thumbnail_path'] = local_path
        self.save_playlist_to_disk()
        self.refresh_grid()

    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Header Frame
        self.header_frame = QFrame()
        h_layout = QHBoxLayout(self.header_frame)

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("🔍 Search tracks...")
        self.search_box.setFixedWidth(200)
        self.search_box.textChanged.connect(lambda t: self.refresh_grid(t.lower().strip()))
        h_layout.addWidget(self.search_box)

        self.shuffle_btn = QPushButton("🎰 Shuffle")
        self.shuffle_btn.clicked.connect(self.slot_machine_shuffle)
        h_layout.addWidget(self.shuffle_btn)

        self.import_json_btn = QPushButton("📁 JSON")
        self.import_json_btn.clicked.connect(self.import_json_file)
        h_layout.addWidget(self.import_json_btn)

        self.clear_all_btn = QPushButton("🗑️ Clear All")
        self.clear_all_btn.clicked.connect(self.clear_all_data)
        h_layout.addWidget(self.clear_all_btn)

        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("📥 Paste SoundCloud / YouTube URL...")
        h_layout.addWidget(self.url_input, stretch=1)

        self.import_btn = QPushButton("Import")
        self.import_btn.clicked.connect(lambda: self.start_import(self.url_input.text().strip()))
        h_layout.addWidget(self.import_btn)

        self.clock_label = QLabel("12:00 PM")
        h_layout.addWidget(self.clock_label)
        main_layout.addWidget(self.header_frame)

        # Tabs Frame
        self.tabs_frame = QFrame()
        t_layout = QHBoxLayout(self.tabs_frame)

        self.filter_btn_group = QButtonGroup(self)
        for label_text, f_key in [("ALL MUSIC", "ALL"), ("PLAYLISTS", "PLAYLISTS"), ("FAVORITES", "FAVORITES")]:
            btn = QPushButton(label_text)
            btn.setCheckable(True)
            if f_key == "ALL": btn.setChecked(True)
            btn.clicked.connect(lambda c, k=f_key: self.set_filter(k))
            self.filter_btn_group.addButton(btn)
            t_layout.addWidget(btn)

        t_layout.addStretch()

        self.theme_combo = QComboBox()
        self.theme_combo.addItems(list(THEMES.keys()))
        self.theme_combo.currentTextChanged.connect(self.change_theme)
        t_layout.addWidget(QLabel("🎨"))
        t_layout.addWidget(self.theme_combo)
        t_layout.addSpacing(15)

        self.sleep_btn = QPushButton("🌙 Sleep")
        self.sleep_btn.clicked.connect(self.cycle_sleep_timer)
        t_layout.addWidget(self.sleep_btn)

        main_layout.addWidget(self.tabs_frame)

        # Middle Section
        middle = QHBoxLayout()
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)

        self.grid_container = QWidget()
        self.grid_layout = QVBoxLayout(self.grid_container)
        self.scroll_area.setWidget(self.grid_container)
        middle.addWidget(self.scroll_area, stretch=7)

        self.turntable = TurntableWidget(self.current_theme, self)
        self.turntable.track_dropped.connect(self.launch_track_by_index)
        self.turntable.tonearm_toggled.connect(self.on_tonearm_toggled)
        middle.addWidget(self.turntable, stretch=4)
        main_layout.addLayout(middle, stretch=1)

        # Footer Frame
        self.footer_frame = QFrame()
        f_layout = QVBoxLayout(self.footer_frame)

        time_layout = QHBoxLayout()
        self.time_current_label = QLabel("00:00")
        self.timeline_slider = QSlider(Qt.Orientation.Horizontal)
        self.timeline_slider.sliderPressed.connect(lambda: setattr(self, 'is_slider_down', True))
        self.timeline_slider.sliderReleased.connect(self.slider_released)
        self.time_total_label = QLabel("00:00")

        time_layout.addWidget(self.time_current_label)
        time_layout.addWidget(self.timeline_slider)
        time_layout.addWidget(self.time_total_label)

        f_layout.addLayout(time_layout)

        ctrl_row = QHBoxLayout()
        self.now_playing_label = QLabel("DRAG A RECORD OR PULL TONEARM TO PLAY")
        ctrl_row.addWidget(self.now_playing_label, stretch=1)

        self.prev_btn = QPushButton("⏮ Prev")
        self.prev_btn.clicked.connect(self.play_previous_track)

        self.play_pause_btn = QPushButton("⏸ Pause")
        self.play_pause_btn.clicked.connect(self.toggle_play_pause)

        self.next_btn = QPushButton("Next ⏭")
        self.next_btn.clicked.connect(self.play_next_track)

        self.loop_btn = QPushButton("🔁 Loop")
        self.loop_btn.clicked.connect(self.toggle_loop_mode)

        ctrl_row.addWidget(self.prev_btn)
        ctrl_row.addWidget(self.play_pause_btn)
        ctrl_row.addWidget(self.next_btn)
        ctrl_row.addWidget(self.loop_btn)

        ctrl_row.addSpacing(15)
        ctrl_row.addWidget(QLabel("🎛️ Pitch"))
        self.pitch_slider = QSlider(Qt.Orientation.Horizontal)
        self.pitch_slider.setRange(50, 150)
        self.pitch_slider.setValue(100)
        self.pitch_slider.setFixedWidth(70)
        self.pitch_slider.valueChanged.connect(self.on_pitch_changed)
        ctrl_row.addWidget(self.pitch_slider)

        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(int(self.current_volume * 100))
        self.volume_slider.setFixedWidth(80)
        self.volume_slider.valueChanged.connect(lambda v: self.audio_output.setVolume(v/100.0))
        ctrl_row.addSpacing(15)
        ctrl_row.addWidget(QLabel("🔊"))
        ctrl_row.addWidget(self.volume_slider)

        f_layout.addLayout(ctrl_row)
        main_layout.addWidget(self.footer_frame)

        self.toast = ToastNotification(self.current_theme, self)
        self.toast.move(24, 70)
        self.toast.import_requested.connect(self.start_import)

        self.loading_overlay = LoadingOverlay(self.current_theme, self)

        self.apply_theme_to_ui()

    def on_pitch_changed(self, val):
        rate = val / 100.0
        self.media_player.setPlaybackRate(rate)
        self.turntable.set_playback_rate(rate)

    def cycle_sleep_timer(self):
        if not self.sleep_timer.isActive(): self.set_sleep_timer(15)
        elif self.sleep_timer.interval() == 15 * 60 * 1000: self.set_sleep_timer(30)
        elif self.sleep_timer.interval() == 30 * 60 * 1000: self.set_sleep_timer(60)
        else: self.set_sleep_timer(0)

    def slot_machine_shuffle(self):
        all_tracks = [(g_idx, t_idx) for g_idx, g in enumerate(self.playlist_groups) for t_idx, _ in enumerate(g.get('tracks', []))]
        if not all_tracks: return
        target = random.choice(all_tracks)
        self.launch_track_by_index(target[0], target[1])

    def on_tonearm_toggled(self, should_play):
        if should_play:
            if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PausedState:
                self.media_player.play()
                self.play_pause_btn.setText("⏸ Pause")
                self.turntable.set_playing(True)
            elif self.playlist_groups: self.play_current_track()
        else:
            if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                self.media_player.pause()
                self.play_pause_btn.setText("▶ Play")
                self.turntable.set_playing(False)

    def set_filter(self, key):
        self.current_filter = key
        self.refresh_grid()

    def refresh_grid(self, search_query=""):
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()

        max_cols = 5
        if self.current_filter == "PLAYLISTS":
            for g_idx, group in enumerate(self.playlist_groups):
                title = group.get('playlist_title', 'Untitled')
                tracks = group.get('tracks', [])
                matching = [(t_idx, t) for t_idx, t in enumerate(tracks) if not search_query or search_query in t.get('title', '').lower()]
                if search_query and not matching: continue

                section = AnimatedPlaylistSection(title, len(tracks), g_idx, self)
                row, col = 0, 0
                items_to_add = matching if search_query else list(enumerate(tracks))
                for t_idx, track in items_to_add:
                    card = MediaCardWidget(track, title, g_idx, t_idx, self.current_theme, self)
                    card.clicked.connect(self.launch_track_by_index)
                    card.favorite_toggled.connect(self.on_favorite_toggled)
                    if g_idx == self.current_group_idx and t_idx == self.current_track_idx: card.set_selected(True)
                    section.body_layout.addWidget(card, row, col)
                    col += 1
                    if col >= max_cols: col, row = 0, row + 1

                if section.is_expanded and items_to_add:
                    num_rows = row + (1 if col > 0 else 0)
                    section.body_widget.setMinimumHeight(num_rows * 260)

                self.grid_layout.addWidget(section)
        else:
            flat_container = QWidget()
            flat_layout = QGridLayout(flat_container)
            flat_layout.setSpacing(20)
            flat_layout.setContentsMargins(10, 10, 10, 10)
            row, col = 0, 0
            total_items = 0
            for g_idx, group in enumerate(self.playlist_groups):
                for t_idx, track in enumerate(group.get('tracks', [])):
                    if self.current_filter == "FAVORITES" and not track.get('favorite', False): continue
                    if search_query and search_query not in track.get('title', '').lower(): continue
                    card = MediaCardWidget(track, group.get('playlist_title', ''), g_idx, t_idx, self.current_theme, self)
                    card.clicked.connect(self.launch_track_by_index)
                    card.favorite_toggled.connect(self.on_favorite_toggled)
                    if g_idx == self.current_group_idx and t_idx == self.current_track_idx: card.set_selected(True)
                    flat_layout.addWidget(card, row, col)
                    col += 1
                    total_items += 1
                    if col >= max_cols: col, row = 0, row + 1

            if total_items > 0:
                num_rows = row + (1 if col > 0 else 0)
                flat_container.setMinimumHeight(num_rows * 260)

            self.grid_layout.addWidget(flat_container)

        self.grid_layout.addStretch()

    def launch_track_by_index(self, group_idx, track_idx, card_widget=None):
        self.current_group_idx = group_idx
        self.current_track_idx = track_idx
        self.refresh_grid()
        self.play_current_track()

    def start_import(self, url):
        if not url: return
        self.url_input.setEnabled(False)
        self.loading_overlay.show_loading("Fetching Playlist from Web", estimated_seconds=4)
        self.worker = SoundCloudWorker(url, 'bestaudio/best')
        self.worker.data_ready.connect(self.handle_import_success)
        self.worker.start()

    def handle_import_success(self, info):
        self.url_input.setEnabled(True)
        self.url_input.clear()
        tracks = []
        if 'entries' in info:
            for e in info['entries']:
                if e: tracks.append({'title': e.get('title'), 'url': e.get('webpage_url') or e.get('url'), 'thumbnail_url': e.get('thumbnail'), 'favorite': False})
        else:
            tracks.append({'title': info.get('title'), 'url': info.get('webpage_url') or info.get('url'), 'thumbnail_url': info.get('thumbnail'), 'favorite': False})
        if tracks:
            self.playlist_groups.append({'playlist_title': info.get('title', 'Import'), 'tracks': tracks})
            self.save_playlist_to_disk()
            self.refresh_grid()
            self.fetch_missing_thumbnails()
        self.loading_overlay.hide()

    def play_current_track(self):
        if not self.playlist_groups: return
        track = self.playlist_groups[self.current_group_idx]['tracks'][self.current_track_idx]
        self.now_playing_label.setText(f"SPINNING UP: {track['title']}")
        self.media_player.stop()
        self.turntable.set_playing(False)

        thumb_path = track.get('thumbnail_path')
        if thumb_path and os.path.exists(thumb_path): self.turntable.set_art(QPixmap(thumb_path))

        self.audio_worker = AudioDownloadWorker(track['url'], track['title'], 'bestaudio/best')
        self.audio_worker.audio_ready.connect(self.start_audio_playback)
        self.audio_worker.start()

    def start_audio_playback(self, file_path, title, url, image_bytes, duration_ms):
        self.track_duration = duration_ms
        if duration_ms > 0: self.timeline_slider.setMaximum(duration_ms)
        self.media_player.setSource(QUrl.fromLocalFile(file_path))
        self.media_player.setPlaybackRate(self.pitch_slider.value() / 100.0)
        self.media_player.play()

        self.play_pause_btn.setText("⏸ Pause")
        self.now_playing_label.setText(f"NOW PLAYING: {title}")
        self.turntable.set_playing(True)

    def toggle_play_pause(self):
        if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.media_player.pause()
            self.play_pause_btn.setText("▶ Play")
            self.turntable.set_playing(False)
        elif self.media_player.playbackState() == QMediaPlayer.PlaybackState.PausedState:
            self.media_player.play()
            self.play_pause_btn.setText("⏸ Pause")
            self.turntable.set_playing(True)
        elif self.playlist_groups: self.play_current_track()

    def play_next_track(self):
        self.current_track_idx += 1
        if self.current_track_idx >= len(self.playlist_groups[self.current_group_idx]['tracks']):
            self.current_track_idx = 0
            self.current_group_idx = (self.current_group_idx + 1) % len(self.playlist_groups)
        self.launch_track_by_index(self.current_group_idx, self.current_track_idx)

    def play_previous_track(self):
        self.current_track_idx -= 1
        if self.current_track_idx < 0:
            self.current_group_idx = (self.current_group_idx - 1) % len(self.playlist_groups)
            self.current_track_idx = len(self.playlist_groups[self.current_group_idx]['tracks']) - 1
        self.launch_track_by_index(self.current_group_idx, self.current_track_idx)

    def slider_released(self):
        self.is_slider_down = False
        self.media_player.setPosition(self.timeline_slider.value())

if __name__ == "__main__":
    app = QApplication(sys.argv)
    player = SteamOSMediaPlayer()
    player.show()
    sys.exit(app.exec())
