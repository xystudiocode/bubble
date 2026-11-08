"""Image plumbing for the frosted-glass surfaces.

The toolkit composites frost itself instead of relying on an OS backdrop
material.  That gives independent, smoothly adjustable blur radii for each
glass region as well as colour/saturation controls.

Two backdrop sources are provided: :class:`DesktopSource` for live screen
tracking and :class:`WallpaperSource` for a Mica-like static system wallpaper
that only reloads when Windows reports a wallpaper change.

Pillow is used only for Gaussian blur and noise generation; all UI drawing
stays in Qt.  When Pillow or screen capture is unavailable the library falls
back gracefully to a generated background.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import os
import random
import sys
from collections import OrderedDict
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import (
    QFileSystemWatcher,
    QObject,
    QPoint,
    QRect,
    QRectF,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QGuiApplication,
    QImage,
    QLinearGradient,
    QPainter,
    QPixmap,
    QRadialGradient,
)

try:  # Pillow is optional at import time; the UI degrades to no blur.
    from PIL import Image, ImageEnhance, ImageFilter, ImageGrab
    _PIL_AVAILABLE = True
except Exception:  # pragma: no cover - only on minimal machines
    _PIL_AVAILABLE = False


# ---------------------------------------------------------------------------
# Qt <-> Pillow bridges
# ---------------------------------------------------------------------------

def qimage_to_pil(image: QImage) -> "Image.Image":
    converted = image.convertToFormat(QImage.Format.Format_RGBA8888)
    width, height = converted.width(), converted.height()
    stride = converted.bytesPerLine()
    data = bytes(converted.constBits())
    return Image.frombuffer("RGBA", (width, height), data, "raw", "RGBA", stride, 1).copy()


def pil_to_qimage(image: "Image.Image") -> QImage:
    image = image.convert("RGBA")
    data = image.tobytes("raw", "RGBA")
    qimage = QImage(data, image.width, image.height, image.width * 4,
                    QImage.Format.Format_RGBA8888)
    return qimage.copy()


def blur_qimage(image: QImage, radius: float, brightness: int = 100,
                saturation: int = 100) -> QImage:
    """Colour grade then Gaussian-blur a QImage.

    ``radius`` is in image pixels.  All adjustments are optional and returning
    a copy keeps Qt's implicit sharing detached from Pillow's buffers.
    """
    if image.isNull():
        return image
    if not _PIL_AVAILABLE:
        return image.copy()
    if radius <= 0.35 and brightness == 100 and saturation == 100:
        return image.copy()

    pil = qimage_to_pil(image)
    if brightness != 100:
        pil = ImageEnhance.Brightness(pil).enhance(brightness / 100.0)
    if saturation != 100:
        pil = ImageEnhance.Color(pil).enhance(saturation / 100.0)
    if radius > 0.35:
        pil = pil.filter(ImageFilter.GaussianBlur(float(radius)))
    return pil_to_qimage(pil)


# ---------------------------------------------------------------------------
# Procedural textures
# ---------------------------------------------------------------------------

_TEXTURE_CACHE: dict[tuple, QPixmap] = {}


def _noise_alpha_layer(size: int, sigma: float, gain: float, seed: int) -> QImage:
    random.seed(seed)
    noise = Image.effect_noise((size, size), sigma).convert("L")
    # Gaussian noise centres around 128.  Turn it into sparse high/lowlights.
    lut = []
    for value in range(256):
        delta = abs(value - 128) / 128.0
        lut.append(int(max(0, min(255, (delta ** 1.7) * 255 * gain))))
    alpha = noise.point(lut)
    layer = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    layer.putalpha(alpha)
    return pil_to_qimage(layer)


def noise_texture(kind: str = "grain", size: int = 768) -> QPixmap:
    """Return a tileable white-alpha product used for frost / grain overlays.

    ``grain`` is high-frequency film grain, ``cloud`` is a soft frosted haze.
    Textures are cached for the lifetime of the process.
    """
    key = (kind, size)
    cached = _TEXTURE_CACHE.get(key)
    if cached is not None:
        return cached
    if not _PIL_AVAILABLE:
        pix = QPixmap(size, size)
        pix.fill(Qt.GlobalColor.transparent)
        _TEXTURE_CACHE[key] = pix
        return pix

    if kind == "cloud":
        random.seed(41)
        tiny = Image.effect_noise((96, 96), 72).convert("L").filter(ImageFilter.GaussianBlur(2.2))
        cloud = tiny.resize((size, size), Image.Resampling.BICUBIC)
        cloud = cloud.filter(ImageFilter.GaussianBlur(10))
        lut = [int(max(0, min(255, (abs(v - 128) / 128.0) ** 1.4 * 135))) for v in range(256)]
        alpha = cloud.point(lut)
        layer = Image.new("RGBA", (size, size), (255, 255, 255, 0))
        layer.putalpha(alpha)
        image = pil_to_qimage(layer)
    else:
        image = _noise_alpha_layer(size, 82, 0.85, 9)
    pix = QPixmap.fromImage(image)
    _TEXTURE_CACHE[key] = pix
    return pix


def clear_texture_cache() -> None:
    _TEXTURE_CACHE.clear()


# ---------------------------------------------------------------------------
# Desktop capture
# ---------------------------------------------------------------------------

def _fallback_background(size: QSize) -> QImage:
    size = size if size.isValid() and size.width() > 10 else QSize(1920, 1080)
    image = QImage(size, QImage.Format.Format_RGBA8888)
    image.fill(QColor("#202329"))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    gradient = QLinearGradient(0, 0, size.width(), size.height())
    gradient.setColorAt(0.0, QColor("#32363E"))
    gradient.setColorAt(0.45, QColor("#1D2026"))
    gradient.setColorAt(1.0, QColor("#0E1014"))
    painter.fillRect(image.rect(), gradient)
    for cx, cy, radius, color in (
        (0.18, 0.22, 0.34, QColor(127, 149, 190, 92)),
        (0.82, 0.30, 0.30, QColor(219, 189, 132, 66)),
        (0.60, 0.86, 0.40, QColor(84, 157, 165, 44)),
    ):
        rad = QRadialGradient(QPoint(int(size.width() * cx), int(size.height() * cy)),
                              int(size.width() * radius))
        rad.setColorAt(0.0, color)
        rad.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setBrush(rad)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPoint(int(size.width() * cx), int(size.height() * cy)),
                            int(size.width() * radius), int(size.width() * radius))
    painter.end()
    return image


def _grab_screen() -> QImage | None:
    """Capture the primary screen as a QImage.

    Qt's screen grab is used first because it is noticeably faster than
    Pillow's ImageGrab on Windows.  Pillow remains a fallback.
    """
    screen = QGuiApplication.primaryScreen()
    if screen is not None:
        try:
            pixmap = screen.grabWindow(0)
            if not pixmap.isNull():
                image = pixmap.toImage()
                if not image.isNull():
                    return image
        except Exception:
            pass

    if _PIL_AVAILABLE:
        try:
            shot = ImageGrab.grab(all_screens=False)
            if shot is not None and shot.width > 0:
                return pil_to_qimage(shot.convert("RGBA"))
        except Exception:
            pass
    return None


WDA_EXCLUDEFROMCAPTURE = 0x00000011

_GDI_AVAILABLE = sys.platform == "win32"
if _GDI_AVAILABLE:
    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _gdi32 = ctypes.WinDLL("gdi32")
    _user32.GetDC.restype = wt.HDC
    _user32.GetDC.argtypes = [wt.HWND]
    _user32.ReleaseDC.argtypes = [wt.HWND, wt.HDC]
    _gdi32.CreateCompatibleDC.restype = wt.HDC
    _gdi32.CreateCompatibleDC.argtypes = [wt.HDC]
    _gdi32.CreateCompatibleBitmap.restype = wt.HBITMAP
    _gdi32.CreateCompatibleBitmap.argtypes = [wt.HDC, ctypes.c_int, ctypes.c_int]
    _gdi32.SelectObject.restype = wt.HGDIOBJ
    _gdi32.SelectObject.argtypes = [wt.HDC, wt.HGDIOBJ]
    _gdi32.DeleteObject.argtypes = [wt.HGDIOBJ]
    _gdi32.DeleteDC.argtypes = [wt.HDC]
    _gdi32.StretchBlt.argtypes = [
        wt.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        wt.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        wt.DWORD,
    ]


class _BitmapInfoHeader(ctypes.Structure):
    _fields_ = [
        ("biSize", wt.DWORD),
        ("biWidth", wt.LONG),
        ("biHeight", wt.LONG),
        ("biPlanes", wt.WORD),
        ("biBitCount", wt.WORD),
        ("biCompression", wt.DWORD),
        ("biSizeImage", wt.DWORD),
        ("biXPelsPerMeter", wt.LONG),
        ("biYPelsPerMeter", wt.LONG),
        ("biClrUsed", wt.DWORD),
        ("biClrImportant", wt.DWORD),
    ]


class _BitmapInfo(ctypes.Structure):
    _fields_ = [("bmiHeader", _BitmapInfoHeader), ("bmiColors", wt.DWORD * 3)]


if _GDI_AVAILABLE:
    _gdi32.SetStretchBltMode.argtypes = [wt.HDC, ctypes.c_int]
    _gdi32.GetDIBits.argtypes = [
        wt.HDC, wt.HBITMAP, wt.UINT, wt.UINT, ctypes.c_void_p,
        ctypes.POINTER(_BitmapInfo), wt.UINT,
    ]
    _gdi32.GetDIBits.restype = ctypes.c_int


def _grab_region_gdi(global_rect: QRect, out_width: int, out_height: int) -> QImage | None:
    """Capture one logical screen region through GDI at a reduced size.

    Only the window area is captured, which is both faster and cheaper than
    grabbing the full 2560x1440 desktop every frame.  Windows excluded with
    :func:`exclude_window_from_capture` are omitted by the compositor just as
    they are for a full-screen grab.
    """
    if not _GDI_AVAILABLE:
        return None
    screen = QGuiApplication.primaryScreen()
    if screen is None:
        return None
    dpr = max(1.0, float(screen.devicePixelRatio()))
    geo = screen.geometry()
    src_x = int(round((global_rect.x() - geo.x()) * dpr))
    src_y = int(round((global_rect.y() - geo.y()) * dpr))
    src_w = max(1, int(round(global_rect.width() * dpr)))
    src_h = max(1, int(round(global_rect.height() * dpr)))
    out_width = max(2, min(4096, int(out_width)))
    out_height = max(2, min(4096, int(out_height)))

    hdc_screen = _user32.GetDC(None)
    if not hdc_screen:
        return None
    hdc_mem = _gdi32.CreateCompatibleDC(hdc_screen)
    bitmap = _gdi32.CreateCompatibleBitmap(hdc_screen, out_width, out_height)
    if not hdc_mem or not bitmap:
        if bitmap:
            _gdi32.DeleteObject(bitmap)
        if hdc_mem:
            _gdi32.DeleteDC(hdc_mem)
        _user32.ReleaseDC(None, hdc_screen)
        return None

    old = _gdi32.SelectObject(hdc_mem, bitmap)
    _gdi32.SetStretchBltMode(hdc_mem, 4)  # HALFTONE
    ok = _gdi32.StretchBlt(
        hdc_mem, 0, 0, out_width, out_height,
        hdc_screen, src_x, src_y, src_w, src_h,
        0x00CC0020,  # SRCCOPY
    )

    info = _BitmapInfo()
    info.bmiHeader.biSize = ctypes.sizeof(_BitmapInfoHeader)
    info.bmiHeader.biWidth = out_width
    info.bmiHeader.biHeight = -out_height
    info.bmiHeader.biPlanes = 1
    info.bmiHeader.biBitCount = 32

    image = QImage(out_width, out_height, QImage.Format.Format_RGB32)
    bits = image.bits()
    bits_ptr = ctypes.addressof(ctypes.c_char.from_buffer(bits))
    got = _gdi32.GetDIBits(hdc_mem, bitmap, 0, out_height,
                           ctypes.c_void_p(bits_ptr),
                           ctypes.byref(info), 0)

    _gdi32.SelectObject(hdc_mem, old)
    _gdi32.DeleteObject(bitmap)
    _gdi32.DeleteDC(hdc_mem)
    _user32.ReleaseDC(None, hdc_screen)

    if not ok or got != out_height:
        return None
    return image


def exclude_window_from_capture(hwnd: int, enabled: bool = True) -> bool:
    """Exclude a native window from screen captures (Windows 10 2004+).

    Dynamic desktop capture must not see the application's own glass windows,
    otherwise the blur would feed on itself.  The helper is a no-op on other
    platforms and returns whether the system accepted the request.
    """
    if sys.platform != "win32":
        return False
    try:
        affinity = WDA_EXCLUDEFROMCAPTURE if enabled else 0
        return bool(ctypes.windll.user32.SetWindowDisplayAffinity(int(hwnd), affinity))
    except Exception:
        return False


_SPI_GETDESKWALLPAPER = 0x0073


def system_wallpaper_path() -> str:
    """Return the best available path to the current Windows wallpaper.

    ``SPI_GETDESKWALLPAPER`` points at the source image selected by the user.
    Some themes and slideshow configurations leave it empty; in that case the
    active ``TranscodedWallpaper`` file is used instead.
    """
    if sys.platform != "win32":
        return ""
    path = ""
    try:
        buffer = ctypes.create_unicode_buffer(1024)
        if ctypes.windll.user32.SystemParametersInfoW(
            _SPI_GETDESKWALLPAPER, len(buffer), buffer, 0
        ):
            path = buffer.value.strip()
    except Exception:
        path = ""
    if path and Path(path).exists():
        return path

    appdata = os.environ.get("APPDATA")
    if appdata:
        transcoded = Path(appdata) / "Microsoft" / "Windows" / "Themes" / "TranscodedWallpaper"
        if transcoded.exists():
            return str(transcoded)
    return ""


def _wallpaper_state(geometry: QRect | None = None, dpr: float = 1.0) -> tuple:
    """Cheap signature used to detect wallpaper file or screen changes."""
    appdata = os.environ.get("APPDATA", "")
    transcoded = (Path(appdata) / "Microsoft" / "Windows" / "Themes" / "TranscodedWallpaper"
                  if appdata else None)
    files = []
    for kind, path in (("source", system_wallpaper_path()), ("transcoded", str(transcoded) if transcoded else "")):
        if not path:
            files.append((kind, ""))
            continue
        try:
            stat = Path(path).stat()
            files.append((kind, path, stat.st_mtime_ns, stat.st_size))
        except OSError:
            files.append((kind, path, None, None))
    geo = geometry or QRect()
    return (geo.x(), geo.y(), geo.width(), geo.height(), round(float(dpr), 3), tuple(files))


def _load_wallpaper_image(path: str, geometry: QRect, dpr: float) -> QImage | None:
    """Load and cover-fit the wallpaper for the primary screen."""
    if not path:
        return None
    try:
        image = QImage(path)
    except Exception:
        image = QImage()
    if image.isNull() and _PIL_AVAILABLE:
        try:
            pil = Image.open(path).convert("RGBA")
            image = pil_to_qimage(pil)
        except Exception:
            image = QImage()
    if image.isNull():
        return None

    target = QSize(max(2, int(round(geometry.width() * dpr))),
                   max(2, int(round(geometry.height() * dpr))))
    if image.size() != target:
        image = image.scaled(
            target,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
    if image.width() > target.width() or image.height() > target.height():
        x = max(0, (image.width() - target.width()) // 2)
        y = max(0, (image.height() - target.height()) // 2)
        image = image.copy(x, y, target.width(), target.height())
    return image


class DesktopSource(QObject):
    """A desktop capture with cached blur variants and optional live refresh.

    ``dynamic`` is enabled by default: a precise timer re-captures the primary
    screen at ``fps`` frames per second (15 by default) and emits ``updated``.
    Windows belonging to the application should be passed through
    :func:`exclude_window_from_capture` so they are not captured into the
    backdrop.

    Static use remains identical: construct once, call :meth:`processed` (or
    :meth:`processed_region`) and paint the result.
    """

    updated = Signal()

    def __init__(self, image: QImage | None = None, screen_geometry: QRect | None = None,
                 dpr: float = 1.0, captured_at: datetime | None = None,
                 dynamic: bool = True, fps: int = 15,
                 parent: QObject | None = None):
        super().__init__(parent)
        screen = QGuiApplication.primaryScreen()
        geometry = QRect(screen_geometry or (screen.geometry() if screen else QRect(0, 0, 1920, 1080)))
        self._dynamic = False
        self._fps = self._clamp_fps(fps)
        self._revision = 0
        self._cache: "OrderedDict[tuple, QImage]" = OrderedDict()
        self._region_cache: "OrderedDict[tuple, tuple[QImage, QRectF]]" = OrderedDict()
        self._capture_region: QRect | None = None
        self._capture_scale = 0.5
        self._paused = False

        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.timeout.connect(self._capture_tick)

        self._apply(image, geometry, dpr, captured_at)
        if dynamic:
            self.set_dynamic(True)

    # -- construction ------------------------------------------------------
    @classmethod
    def capture(cls, *, dynamic: bool = True, fps: int = 15) -> "DesktopSource":
        screen = QGuiApplication.primaryScreen()
        geometry = QRect(screen.geometry()) if screen else QRect(0, 0, 1920, 1080)
        dpr = float(screen.devicePixelRatio()) if screen else 1.0
        image = _grab_screen()
        return cls(image, geometry, dpr, dynamic=dynamic, fps=fps)

    # -- dynamic capture ---------------------------------------------------
    @property
    def dynamic(self) -> bool:
        return self._dynamic

    @property
    def fps(self) -> int:
        return self._fps

    @property
    def revision(self) -> int:
        """Increases whenever the captured image changes."""
        return self._revision

    def average_color(self) -> QColor:
        """捕获图的平均颜色。

        采样区域落在屏幕/图像之外时（窗口被拖出屏幕），用它给玻璃兜底，
        保持与源图一致的色调，而不是刷一块与壁纸无关的纯色。
        """
        revision = getattr(self, "_average_revision", -1)
        if revision != self._revision:
            scaled = self.image.scaled(
                1, 1, Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._average_color = scaled.pixelColor(0, 0)
            self._average_revision = self._revision
        return self._average_color

    @staticmethod
    def _clamp_fps(fps: int) -> int:
        try:
            value = int(fps)
        except (TypeError, ValueError):
            value = 15
        return max(1, min(30, value))

    def _interval_ms(self) -> int:
        return max(1, int(round(1000.0 / self._fps)))

    def set_dynamic(self, enabled: bool) -> None:
        enabled = bool(enabled)
        if enabled == self._dynamic:
            return
        self._dynamic = enabled
        if enabled:
            # An explicit user enable overrides a stale interaction pause.
            self._paused = False
            self._timer.start(self._interval_ms())
            self._capture_tick()
        else:
            self._timer.stop()
            self._paused = False

    def set_paused(self, paused: bool) -> None:
        """Temporarily pause live capture without changing the user switch.

        Window moves/resizes use this so the native move loop stays responsive.
        """
        paused = bool(paused)
        if paused == self._paused:
            return
        self._paused = paused
        if not self._dynamic:
            return
        if paused:
            self._timer.stop()
        else:
            self._timer.start(self._interval_ms())
            self._capture_tick()

    def set_capture_region(self, region: QRect | None, scale: float = 0.5) -> None:
        """Limit live capture to one window region at a reduced size."""
        self._capture_region = QRect(region) if region is not None and not region.isNull() else None
        self._capture_scale = max(0.25, min(1.0, float(scale)))

    def set_fps(self, fps: int) -> None:
        value = self._clamp_fps(fps)
        if value == self._fps:
            return
        self._fps = value
        if self._dynamic:
            self._timer.setInterval(self._interval_ms())

    def refresh_full(self) -> None:
        """Capture one full-screen frame, regardless of the region setting.

        Used when live sampling is turned off for capture compatibility, so the
        static glass still has a complete desktop image while the window moves.
        """
        screen = QGuiApplication.primaryScreen()
        geometry = QRect(screen.geometry()) if screen else self.screen_geometry
        dpr = float(screen.devicePixelRatio()) if screen else self.dpr
        image = _grab_screen()
        if image is None or image.isNull():
            return
        self._apply(image, geometry, dpr, datetime.now())
        self.updated.emit()

    def _capture_tick(self) -> None:
        if not self._dynamic or self._paused:
            return
        screen = QGuiApplication.primaryScreen()
        geometry = QRect(screen.geometry()) if screen else self.screen_geometry
        dpr = float(screen.devicePixelRatio()) if screen else self.dpr

        if self._capture_region is not None and _GDI_AVAILABLE:
            region = self._capture_region.intersected(geometry)
            if not region.isEmpty():
                scale = min(self._capture_scale, 1280.0 / max(1, max(region.width(), region.height())))
                scale = max(0.2, scale)
                out_w = max(2, int(round(region.width() * scale)))
                out_h = max(2, int(round(region.height() * scale)))
                image = _grab_region_gdi(region, out_w, out_h)
                if image is not None and not image.isNull():
                    self._apply(image, region, dpr, datetime.now())
                    self.updated.emit()
                    return

        image = _grab_screen()
        if image is None or image.isNull():
            return
        self._apply(image, geometry, dpr, datetime.now())
        self.updated.emit()

    # -- image state -------------------------------------------------------
    def _apply(self, image: QImage | None, screen_geometry: QRect, dpr: float,
               captured_at: datetime | None) -> None:
        self.screen_geometry = QRect(screen_geometry)
        self.dpr = float(dpr or 1.0)
        if image is None or image.isNull():
            width = max(16, int(round(self.screen_geometry.width() * self.dpr)))
            height = max(16, int(round(self.screen_geometry.height() * self.dpr)))
            image = _fallback_background(QSize(width, height))
            self.captured_at = captured_at
            self.is_fallback = True
        else:
            self.captured_at = captured_at or datetime.now()
            self.is_fallback = False

        self.image = image
        self.scale_x = image.width() / max(1, self.screen_geometry.width())
        self.scale_y = image.height() / max(1, self.screen_geometry.height())
        self._cache.clear()
        self._region_cache.clear()
        self._revision += 1

    # -- geometry ----------------------------------------------------------
    def source_rect(self, global_rect: QRect) -> QRectF:
        """Map a logical global rectangle to pixels in the stored capture."""
        x = (global_rect.x() - self.screen_geometry.x()) * self.scale_x
        y = (global_rect.y() - self.screen_geometry.y()) * self.scale_y
        return QRectF(x, y, max(1.0, global_rect.width() * self.scale_x),
                      max(1.0, global_rect.height() * self.scale_y))

    # -- processing --------------------------------------------------------
    def processed(self, radius: int, brightness: int = 100, saturation: int = 100,
                  max_dimension: int = 1280) -> QImage:
        """Return a blurred variant, cached by its settings.

        Large desktop blurs are computed on a reduced copy.  A frosted pane has
        no high-frequency detail to preserve, so the saving is essentially free
        visually and makes live slider feedback feel responsive.
        """
        key = (int(radius), int(brightness), int(saturation), int(max_dimension))
        found = self._cache.get(key)
        if found is not None:
            self._cache.move_to_end(key)
            return found
        source = self.image
        largest = max(source.width(), source.height())
        factor = min(1.0, max_dimension / max(1, largest))
        if factor < 0.999:
            working = source.scaled(
                max(8, int(round(source.width() * factor))),
                max(8, int(round(source.height() * factor))),
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        else:
            working = source
        physical_radius = max(0.0, float(radius) * factor * ((self.scale_x + self.scale_y) / 2.0))
        result = blur_qimage(working, physical_radius, brightness, saturation)
        self._cache[key] = result
        while len(self._cache) > 6:
            self._cache.popitem(last=False)
        return result

    def processed_region(self, global_rect: QRect, radius: int, brightness: int = 100,
                         saturation: int = 100,
                         max_dimension: int = 1280) -> tuple[QImage | None, QRectF]:
        """Blur only one screen region.

        Returns ``(image, target_rect)`` where ``target_rect`` is in logical
        screen coordinates.  This keeps live capture cheap: the full desktop is
        never re-blurred for a single window.
        """
        key = (global_rect.x(), global_rect.y(), global_rect.width(), global_rect.height(),
               int(radius), int(brightness), int(saturation), int(max_dimension))
        found = self._region_cache.get(key)
        if found is not None:
            self._region_cache.move_to_end(key)
            return found

        source = self.image
        if source.isNull():
            return None, QRectF()

        mapped = self.source_rect(global_rect)
        pixel_rect = QRect(
            int(round(mapped.x())),
            int(round(mapped.y())),
            max(1, int(round(mapped.width()))),
            max(1, int(round(mapped.height()))),
        )
        pixel_rect = pixel_rect.intersected(source.rect())
        if pixel_rect.isEmpty():
            return None, QRectF()

        crop = source.copy(pixel_rect)
        factor = min(1.0, max_dimension / max(1, max(crop.width(), crop.height())))
        if factor < 0.999:
            crop = crop.scaled(
                max(1, int(round(crop.width() * factor))),
                max(1, int(round(crop.height() * factor))),
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )

        physical_radius = max(0.0, float(radius) * factor * ((self.scale_x + self.scale_y) / 2.0))
        result = blur_qimage(crop, physical_radius, brightness, saturation)
        result.setDevicePixelRatio(1.0)
        target = QRectF(
            self.screen_geometry.x() + pixel_rect.x() / self.scale_x,
            self.screen_geometry.y() + pixel_rect.y() / self.scale_y,
            pixel_rect.width() / self.scale_x,
            pixel_rect.height() / self.scale_y,
        )
        self._region_cache[key] = (result, target)
        while len(self._region_cache) > 12:
            self._region_cache.popitem(last=False)
        return result, target


class WallpaperSource(DesktopSource):
    """Static glass backdrop built from the current system wallpaper.

    The source behaves like :class:`DesktopSource` for painting and caching, but
    it never samples the screen.  A filesystem watcher (with a slow polling
    fallback) reloads the image only when the wallpaper file or the primary
    screen geometry changes.  That keeps idle CPU cost near zero while still
    following Windows theme/slideshow changes.
    """

    def __init__(self, parent: QObject | None = None, *, watch: bool = True):
        screen = QGuiApplication.primaryScreen()
        geometry = QRect(screen.geometry()) if screen else QRect(0, 0, 1920, 1080)
        dpr = float(screen.devicePixelRatio()) if screen else 1.0
        path = system_wallpaper_path()
        image = _load_wallpaper_image(path, geometry, dpr)
        super().__init__(image, geometry, dpr, datetime.now(), dynamic=False, fps=1,
                         parent=parent)
        self._wallpaper_path = path
        self._wallpaper_state = _wallpaper_state(geometry, dpr)
        self._watcher: QFileSystemWatcher | None = None
        self._watch_timer = QTimer(self)
        self._watch_timer.setInterval(1500)
        self._watch_timer.timeout.connect(self.reload)
        if watch:
            self.start_watch()

    @property
    def wallpaper_path(self) -> str:
        return self._wallpaper_path

    # Wallpaper mode is deliberately static: never start screen sampling even
    # if a host still calls the DesktopSource compatibility API.
    def set_dynamic(self, enabled: bool) -> None:
        return

    def set_fps(self, fps: int) -> None:
        return

    def refresh_full(self) -> None:
        self.reload(force=True)

    def reload(self, force: bool = False) -> bool:
        """Reload the wallpaper when it (or the screen geometry) changed."""
        screen = QGuiApplication.primaryScreen()
        geometry = QRect(screen.geometry()) if screen else self.screen_geometry
        dpr = float(screen.devicePixelRatio()) if screen else self.dpr
        state = _wallpaper_state(geometry, dpr)
        if not force and state == self._wallpaper_state:
            return False

        path = system_wallpaper_path()
        image = _load_wallpaper_image(path, geometry, dpr)
        if image is None or image.isNull():
            # Keep the previous frame during transient transcoding failures.
            return False

        self._apply(image, geometry, dpr, datetime.now())
        self._wallpaper_path = path
        self._wallpaper_state = state
        self._refresh_watcher_paths()
        self.updated.emit()
        return True

    def stop(self) -> None:
        """Stop watching for wallpaper changes."""
        self._watch_timer.stop()
        if self._watcher is not None:
            self._watcher.deleteLater()
            self._watcher = None

    def start_watch(self) -> None:
        """Start (or restart) watching for wallpaper changes.

        ``stop()`` is called when a glass host is closed; the same host may be
        shown again later, so the watcher has to be restartable.
        """
        if self._watcher is None:
            self._watcher = QFileSystemWatcher(self)
            self._watcher.fileChanged.connect(self._on_watch_changed)
            self._watcher.directoryChanged.connect(self._on_watch_changed)
        self._refresh_watcher_paths()
        self._watch_timer.start()

    def _on_watch_changed(self, _path: str) -> None:
        self.reload()

    def _refresh_watcher_paths(self) -> None:
        if self._watcher is None:
            return
        wanted: set[str] = set()
        for path in (self._wallpaper_path, self._transcoded_path()):
            if not path:
                continue
            candidate = Path(path)
            wanted.add(str(candidate))
            wanted.add(str(candidate.parent))
        current = set(self._watcher.files()) | set(self._watcher.directories())
        stale = current - wanted
        if stale:
            self._watcher.removePaths(sorted(stale))
        missing = wanted - current
        if missing:
            self._watcher.addPaths(sorted(missing))

    @staticmethod
    def _transcoded_path() -> str:
        appdata = os.environ.get("APPDATA")
        if not appdata:
            return ""
        path = Path(appdata) / "Microsoft" / "Windows" / "Themes" / "TranscodedWallpaper"
        return str(path) if path.exists() else ""
