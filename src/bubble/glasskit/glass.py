"""Core frosted-glass painting primitives.

The module is deliberately free of application chrome and demo state.  It
provides the material model (:class:`FrostStyle`), a painter for laying the
material over an existing backdrop, and a pane that blurs the widget content
underneath it.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Protocol

import shiboken6

from PySide6.QtCore import *
from PySide6.QtGui import *
from PySide6.QtWidgets import *

from .imaging import (
    DesktopSource,
    WallpaperSource,
    exclude_window_from_capture,
    blur_qimage, 
    noise_texture
)

from .energy import EnergyModeController

from dataclasses import fields, replace
from .config import * # noqa: F401

from .settings import GlassRuntimeSettings, FrostStyle

_CONFIG_FIELDS = tuple(field.name for field in fields(GlassRuntimeSettings))


# ===========================================================================
# FrostStyle <-> QSS bridge
# ===========================================================================
# Every field of :class:`FrostStyle` is exposed as a Qt property on the glass
# painting widgets, so the built-in materials can be tuned from a style sheet::
#
#     GlassBackdrop {
#         qproperty-frostTint: #303030;
#         qproperty-frostOpacity: 80;
#         qproperty-frostBlur: 32;
#     }
#     GlassMenuBar[glassStyle="thin"] {
#         qproperty-frostOpacity: 30;
#     }
#
# The four presets from :mod:`.config` are written to the theme style sheets,
# which makes QSS the effective source at runtime while Python keeps working
# defaults (useful for the standalone library).
_FROST_QSS_FIELDS: tuple[tuple[str, type], ...] = (
    ("tint", QColor),
    ("opacity", int),
    ("blur", int),
    ("frost", int),
    ("noise", int),
    ("sheen", int),
    ("saturation", int),
    ("brightness", int),
    ("border", int),
    ("radius", int),
    ("vignette", int),
)

_FROST_INT_RANGES = {
    "opacity": (0, 100),
    "blur": (0, 200),
    "frost": (0, 100),
    "noise": (0, 100),
    "sheen": (0, 100),
    "saturation": (0, 300),
    "brightness": (0, 300),
    "border": (0, 100),
    "radius": (0, 100),
    "vignette": (0, 100),
}

_FROST_FIELD_NAMES = frozenset(name for name, _ in _FROST_QSS_FIELDS)


def _coerce_frost_value(field: str, value):
    if field == "tint":
        color = value if isinstance(value, QColor) else QColor(str(value))
        return color.name() if color.isValid() else "#000000"
    number = int(value)
    low, high = _FROST_INT_RANGES.get(field, (0, 300))
    return max(low, min(high, number))


def _frost_property(field: str, qtype: type):
    def getter(self):
        if qtype is QColor:
            return QColor(self.background_style.tint)
        return getattr(self.background_style, field)

    def setter(self, value):
        self.set_frost_style(**{field: value})

    return Property(qtype, getter, setter)


def _frost_properties():
    """Q_PROPERTY descriptors for the FrostStyle fields (assigned in class bodies)."""
    return tuple(_frost_property(field, qtype) for field, qtype in _FROST_QSS_FIELDS)


class _FrostStyleMixin:
    """Shared material state for widgets that paint a :class:`FrostStyle`."""

    background_style: FrostStyle = BUBBLE_BACKGROUND_NORMAL

    def set_frost_style(self, **fields) -> None:
        """Override individual material fields (used by ``qproperty-frost*``)."""
        unknown = set(fields) - _FROST_FIELD_NAMES
        if unknown:
            raise TypeError("未知的 FrostStyle 字段: " + ", ".join(sorted(unknown)))
        updates = {name: _coerce_frost_value(name, value) for name, value in fields.items()}
        self.background_style = replace(self.background_style, **updates)
        self.update()


def apply_glass_style(widget: QWidget, preset: str) -> None:
    """Switch a glass widget to a QSS preset variant such as ``"thin"``.

    The theme style sheets provide ``GlassBackdrop[glassStyle="thin"]`` /
    ``GlassMenuBar[glassStyle="thin"]`` blocks; this helper sets the dynamic
    property and re-polishes the widget so the block takes effect.
    """
    widget.setProperty("glassStyle", str(preset))
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()


def qcolor(value: str | QColor, alpha: int | None = None) -> QColor:
    """Return a QColor from a CSS string or another QColor."""
    color = QColor(value) if not isinstance(value, QColor) else QColor(value)
    if alpha is not None:
        color.setAlpha(max(0, min(255, int(alpha))))
    return color


def mix(a: str | QColor, b: str | QColor, t: float) -> QColor:
    """Linear colour interpolation; ``t`` is clamped to 0..1."""
    t = max(0.0, min(1.0, float(t)))
    ca, cb = qcolor(a), qcolor(b)
    return QColor(
        int(round(ca.red() * (1 - t) + cb.red() * t)),
        int(round(ca.green() * (1 - t) + cb.green() * t)),
        int(round(ca.blue() * (1 - t) + cb.blue() * t)),
        int(round(ca.alpha() * (1 - t) + cb.alpha() * t)),
    )

def rounded_path(rect: QRectF, radius: float) -> QPainterPath:
    path = QPainterPath()
    radius = max(0.0, min(float(radius), min(rect.width(), rect.height()) / 2.0))
    path.addRoundedRect(rect, radius, radius)
    return path


def paint_frost_overlay(
    painter: QPainter,
    rect: QRectF,
    style: FrostStyle,
    *,
    radius: float | None = None,
    border: bool = True,
    vignette: int | None = None,
    sheen: bool = True,
    clip: bool = True,
    texture_offset: QPoint = QPoint(0, 0),
) -> None:
    """Paint tint, haze, grain, sheen and an optional border over a backdrop.

    The caller is responsible for drawing the blurred backdrop first.  This
    function only beautifies the *background*; widgets drawn later remain
    perfectly sharp.
    """
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    radius = style.radius if radius is None else radius
    vignette = style.vignette if vignette is None else int(vignette)
    path = rounded_path(rect, radius)
    if clip:
        painter.setClipPath(path)

    # Tint.  Saturation and brightness belong to the source image; opacity is
    # the strength of the coloured glass layer.
    tint = qcolor(style.tint)
    tint_alpha = int(round(255 * (style.opacity / 100.0)))
    tint.setAlpha(tint_alpha)
    painter.fillRect(rect, tint)

    # Frost is a soft, slightly milky veil which lowers backdrop contrast.
    if style.frost > 0:
        haze_color = mix(style.tint, "#F7F4EC", 0.24)
        haze = QLinearGradient(rect.topLeft(), rect.bottomRight())
        haze.setColorAt(0.0, qcolor(haze_color, int(style.frost * 0.90)))
        haze.setColorAt(0.55, qcolor(haze_color, int(style.frost * 0.48)))
        haze.setColorAt(1.0, qcolor(haze_color, int(style.frost * 0.22)))
        painter.fillRect(rect, haze)

    # Tileable procedural textures add the "frosted" tactile quality.
    if style.frost > 0:
        painter.save()
        painter.translate(texture_offset)
        painter.setOpacity(min(0.7, style.frost / 100.0 * 0.38))
        painter.fillRect(rect.translated(-texture_offset), QBrush(noise_texture("cloud")))
        painter.restore()
    if style.noise > 0:
        painter.save()
        painter.translate(texture_offset + QPoint(73, 41))
        painter.setOpacity(min(0.8, style.noise / 100.0 * 0.55))
        painter.fillRect(rect.translated(-texture_offset - QPoint(73, 41)),
                         QBrush(noise_texture("grain")))
        painter.restore()

    if sheen and style.sheen > 0:
        top = QLinearGradient(rect.topLeft(), QPointF(rect.left(), rect.top() + rect.height() * 0.48))
        top.setColorAt(0.0, QColor(255, 255, 255, int(style.sheen * 0.34)))
        top.setColorAt(0.5, QColor(255, 255, 255, int(style.sheen * 0.10)))
        top.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.fillRect(rect, top)
        # A brighter line on the top lip catches the eye like real glass.
        lip = QLinearGradient(rect.left(), 0, rect.right(), 0)
        lip.setColorAt(0.0, QColor(255, 255, 255, 0))
        lip.setColorAt(0.22, QColor(255, 255, 255, int(style.sheen * 0.7)))
        lip.setColorAt(0.78, QColor(255, 255, 255, int(style.sheen * 0.45)))
        lip.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.setPen(QPen(QBrush(lip), 1.0))
        painter.drawLine(QPointF(rect.left() + radius * 0.4, rect.top() + 0.5),
                         QPointF(rect.right() - radius * 0.4, rect.top() + 0.5))

    if vignette:
        painter.setClipPath(path)
        radial = QRadialGradient(rect.center(), max(rect.width(), rect.height()) * 0.72)
        radial.setColorAt(0.35, QColor(0, 0, 0, 0))
        radial.setColorAt(0.78, QColor(0, 0, 0, int(vignette * 0.55)))
        radial.setColorAt(1.0, QColor(0, 0, 0, int(vignette * 1.25)))
        painter.fillRect(rect, radial)

    if border and style.border > 0:
        painter.setClipping(False)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        edge = QLinearGradient(rect.topLeft(), rect.bottomRight())
        edge.setColorAt(0.0, QColor(255, 255, 255, int(style.border * 1.55)))
        edge.setColorAt(0.45, QColor(255, 255, 255, int(style.border * 0.55)))
        edge.setColorAt(1.0, QColor(255, 255, 255, int(style.border * 0.95)))
        painter.setPen(QPen(QBrush(edge), 1.0))
        painter.drawPath(rounded_path(rect.adjusted(0.5, 0.5, -0.5, -0.5), radius))
        # Inner shadow at the bottom gives the pane a little physical weight.
        inner = QLinearGradient(rect.left(), rect.bottom() - 28, rect.left(), rect.bottom())
        inner.setColorAt(0.0, QColor(0, 0, 0, 0))
        inner.setColorAt(1.0, QColor(0, 0, 0, 38))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setClipPath(rounded_path(rect.adjusted(0.5, 0.5, -0.5, -0.5), max(0.0, radius - 0.5)))
        painter.fillRect(QRectF(rect.left(), rect.bottom() - 28, rect.width(), 28), inner)

    painter.restore()


class BlurSource(Protocol):
    def render_source_image(self) -> QImage: ...
    def source_revision(self) -> int: ...


class BlurredGlassPanel(QWidget):
    """A glass pane that blurs the content of a sibling/parent source widget.

    The source widget implements ``render_source_image()`` and
    ``source_revision()``.  Everything painted on the pane (labels, buttons,
    etc.) stays crisp; only the captured scene underneath is blurred.
    """

    def __init__(self, source_widget: BlurSource, style: FrostStyle,
                 parent: QWidget | None = None):
        super().__init__(parent or source_widget)  # type: ignore[arg-type]
        self.source_widget = source_widget
        self.style = style
        self._revision = -1
        self._blurred: QImage | None = None
        self._blurred_pos = QPointF(0, 0)
        self._build_key: tuple | None = None
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)
        self.setMouseTracking(False)

    # -- public ------------------------------------------------------------
    def set_style(self, style: FrostStyle) -> None:
        self.style = style
        self.update()

    def refresh_style(self) -> None:
        self.update()

    def invalidate(self) -> None:
        self._build_key = None
        self.update()

    # -- backdrop ----------------------------------------------------------
    def _source_dpr(self) -> float:
        try:
            return max(1.0, float(self.source_widget.devicePixelRatioF()))
        except Exception:
            return 1.0

    def _build_backdrop(self) -> None:
        source_image = self.source_widget.render_source_image()
        revision = self.source_widget.source_revision()
        dpr = max(1.0, float(source_image.devicePixelRatio() or self._source_dpr()))
        style = self.style

        # Include the pane's position: moving it over a different part of the
        # source must sample different pixels.
        offset = self.mapTo(self.source_widget, QPoint(0, 0))
        key = (revision, offset.x(), offset.y(), self.width(), self.height(), dpr,
               style.blur, style.saturation, style.brightness)
        if key == self._build_key and self._blurred is not None:
            return
        self._build_key = key

        if source_image.isNull():
            self._blurred = None
            return

        # Include padding so the blur kernel sees real neighbouring pixels.
        pad = int(max(10, style.blur * 2 + 10))
        logical = QRect(offset.x() - pad, offset.y() - pad,
                        self.width() + pad * 2, self.height() + pad * 2)
        source_logical = self.source_widget.rect()
        clipped = logical.intersected(source_logical)
        if clipped.isEmpty():
            self._blurred = None
            return

        pixel_rect = QRect(
            int(round(clipped.x() * dpr)),
            int(round(clipped.y() * dpr)),
            max(1, int(round(clipped.width() * dpr))),
            max(1, int(round(clipped.height() * dpr))),
        )
        pixel_rect = pixel_rect.intersected(source_image.rect())
        if pixel_rect.isEmpty():
            self._blurred = None
            return

        cropped = source_image.copy(pixel_rect)
        physical_radius = style.blur * dpr
        blurred = blur_qimage(cropped, physical_radius, style.brightness, style.saturation)
        blurred.setDevicePixelRatio(dpr)
        self._blurred = blurred
        self._blurred_pos = QPointF(
            pixel_rect.x() / dpr - offset.x(),
            pixel_rect.y() / dpr - offset.y(),
        )

    # -- painting ----------------------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        painter = QPainter(self)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing |
                               QPainter.RenderHint.SmoothPixmapTransform)
        self._build_backdrop()
        radius = self.style.radius
        rect = QRectF(self.rect())
        path = rounded_path(rect, radius)

        # A soft dark edge inside the pane gives it weight without requiring a
        # QGraphicsEffect (which would blur the glass content too).
        painter.save()
        painter.setClipPath(path)
        painter.fillRect(rect, QColor(10, 10, 10, 160))
        if self._blurred is not None:
            painter.drawImage(self._blurred_pos, self._blurred)
        painter.restore()

        paint_frost_overlay(painter, rect, self.style, radius=radius, vignette=6)
        painter.end()

class GlassBackdrop(_FrostStyleMixin, QWidget):
    """Frosted glass layer that can sit inside any host window.

    The backdrop is a plain child widget: it paints the blurred wallpaper /
    live desktop and hosts the energy-saving cross-fade.  Put it at the bottom
    of a window (QMainWindow's central widget, a dialog's only child, ...) and
    add the real content to :attr:`content_layout`, which is painted on top of
    the glass.

    ``host`` is the top-level window that owns everything window-level: drag
    and double-click gestures are forwarded to it, capture exclusion applies to
    its native handle, and its activation events drive
    ``auto_energy_on_focus_loss``.  Keep the backdrop at the same client-area
    geometry as the host (as all hosts below do) so the transition snapshots
    stay aligned.
    """

    #: Frost material painted as the whole-window backdrop.
    background_style: FrostStyle = BUBBLE_BACKGROUND_NORMAL

    #: QSS-accessible material fields (``qproperty-frost*``).
    (
        frostTint, frostOpacity, frostBlur, frostFrost, frostNoise, frostSheen,
        frostSaturation, frostBrightness, frostBorder, frostRadius, frostVignette,
    ) = _frost_properties()

    def __init__(self, host: QWidget, parent: QWidget | None = None) -> None:
        super().__init__(parent if parent is not None else host)
        self._host = host
        self.config = RUNTIME.copy()
        self._drag_offset = None
        self._capture_excluded = False
        self._live_capture_active = False
        self._shutdown_done = False
        self._watched_window: QWidget | None = None

        # The real UI of the host window is mounted here, on top of the glass.
        self.content_layout = QVBoxLayout(self)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(0)

        # The backdrop paints the glass itself; the host window stays empty.
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAutoFillBackground(False)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)

        self.desktop = DesktopSource.capture(dynamic=self.config.screen_tracking, fps=self.config.fps)
        self.desktop.set_capture_region(self._global_rect(), CAPTURE_SCALE)
        self.wallpaper = WallpaperSource()
        self.source = self.wallpaper if self.config.wallpaper else self.desktop
        self.desktop.updated.connect(self.update)
        self.wallpaper.updated.connect(self.update)

        # The controller watches the *host* window: activation events used by
        # auto_energy_on_focus_loss are delivered to the top-level window, never
        # to a child widget.  Painting still happens in backdrop coordinates.
        self.energy = EnergyModeController(
            self._host,
            self._render_background,
            duration_ms=self.config.transition_ms,
            auto_on_focus_loss=self.config.auto_energy_on_focus_loss,
        )
        self.energy.energyChanged.connect(self._on_energy_changed)
        self.energy.transitionFinished.connect(self._on_energy_finished)
        self.energy.set_explicit(self.config.energy_saving)

        # A child never receives its host's move/hide events, so watch them.
        self._host.installEventFilter(self)
        self._sync_window_watch()
        self._sync_background_source()

    # -- public API -------------------------------------------------------
    def setBrush(self, style: FrostStyle) -> None:
        """Set the frosted material used by this backdrop.

        The style's ``tint`` doubles as the opaque colour of energy-saving
        mode, so both backgrounds follow the brush.
        """
        if not isinstance(style, FrostStyle):
            raise TypeError("setBrush 需要 FrostStyle 实例")
        self.background_style = style
        self.update()

    def setConfig(self, *args, **kwargs) -> None:
        """Update this backdrop's runtime settings.

        Keyword names match :class:`GlassRuntimeSettings`; omitted fields keep
        their current values.  Positional arguments may be either one
        ``GlassRuntimeSettings`` instance or values in field order::

            backdrop.setConfig(fps=30, background_mode="screen")
            backdrop.setConfig(GlassRuntimeSettings(energy_saving=True))
            backdrop.setConfig("screen", 30)     # background_mode, fps
        """
        unknown = set(kwargs) - set(_CONFIG_FIELDS)
        if unknown:
            raise TypeError("未知配置项: " + ", ".join(sorted(unknown)))

        if len(args) == 1 and isinstance(args[0], GlassRuntimeSettings):
            config = args[0].copy()
        else:
            if len(args) > len(_CONFIG_FIELDS):
                raise TypeError(f"setConfig 最多接受 {len(_CONFIG_FIELDS)} 个位置参数")
            config = replace(self.config, **dict(zip(_CONFIG_FIELDS, args)))
        config = replace(config, **kwargs)
        self._apply_config(config)

    def shutdown(self) -> None:
        """Stop background work and release the capture exclusion.

        Idempotent, and safe to call on a wrapper whose C++ object has already
        been destroyed (for example when the host window was torn down by Qt
        before the Python attribute was released).
        """
        if self._shutdown_done or not shiboken6.isValid(self):
            return
        self._shutdown_done = True
        try:
            self._set_capture_excluded(False)
            self._live_capture_active = False
            self.desktop.set_dynamic(False)
            self.desktop.set_paused(True)
            self.wallpaper.stop()
        except RuntimeError:
            # Some child object was already deleted; nothing left to release.
            pass
        try:
            if shiboken6.isValid(self._host):
                self._host.removeEventFilter(self)
        except RuntimeError:
            pass
        watched = self._watched_window
        self._watched_window = None
        try:
            if (watched is not None and watched is not self._host
                    and shiboken6.isValid(watched)):
                watched.removeEventFilter(self)
        except RuntimeError:
            pass

    # -- host plumbing -----------------------------------------------------
    def _global_rect(self) -> QRect:
        """Backdrop rect in global (screen) coordinates."""
        return QRect(self.mapToGlobal(QPoint(0, 0)), self.size())

    def _sync_window_watch(self) -> None:
        """也监听真正的顶层窗口（宿主被嵌入到别的窗口时）。

        玻璃采样依赖窗口的全局位置：顶层窗口移动/缩放后必须重绘，否则玻璃
        会停留在旧位置，直到其它事件碰巧触发重绘。宿主是子控件时收不到顶层
        窗口的 Move 事件，所以这里把事件过滤器挂到 ``host.window()`` 上。
        """
        try:
            window = self._host.window()
        except RuntimeError:
            return
        if window is self._watched_window:
            return
        if self._watched_window is not None:
            try:
                self._watched_window.removeEventFilter(self)
            except RuntimeError:
                pass
        self._watched_window = window
        if window is not None and window is not self._host:
            window.installEventFilter(self)

    def _apply_config(self, config: GlassRuntimeSettings) -> None:
        previous = self.config
        self.config = config

        if config.background_mode != previous.background_mode:
            # Re-select wallpaper/desktop and redo capture region + policy.
            self._sync_background_source()
        else:
            if config.fps != previous.fps:
                self.desktop.set_fps(config.fps)
            if config.allow_capture != previous.allow_capture:
                self._update_capture_policy()

        if config.energy_saving != previous.energy_saving:
            self.energy.set_explicit(config.energy_saving)
        if config.auto_energy_on_focus_loss != previous.auto_energy_on_focus_loss:
            self.energy.set_auto_on_focus_loss(config.auto_energy_on_focus_loss)
        if config.transition_ms != previous.transition_ms:
            self.energy.set_duration(config.transition_ms)

        self._update_capture_policy()
        self.update()

    # -- background source -----------------------------------------------
    def _sync_background_source(self) -> None:
        selected = self.wallpaper if self.config.wallpaper else self.desktop
        if selected is not self.source:
            self.source = selected
        if self.config.wallpaper:
            self.wallpaper.reload()
        else:
            self.desktop.set_dynamic(True)
            self.desktop.set_fps(self.config.fps)
        self._sync_capture_region()
        self._update_capture_policy()
        self.update()

    def _sync_capture_region(self) -> None:
        if self.config.screen_tracking:
            self.desktop.set_capture_region(self._capture_global_rect(), CAPTURE_SCALE)

    def _capture_global_rect(self) -> QRect:
        """玻璃采样需要截取的屏幕区域：backdrop 矩形，必要时扩展到顶层窗口。

        宿主是子控件时（例如 NavigationView 被嵌进自定义标题栏窗口），标题栏
        这类“抬头”会用同一套玻璃材质采样，而它位于 backdrop 上方。只截
        backdrop 自己的矩形会采不到那些像素，抬头只能退化成平均色。
        """
        rect = self._global_rect()
        try:
            window = self._host.window()
        except RuntimeError:
            return rect
        if window is None or window is self._host:
            return rect
        try:
            window_rect = QRect(window.mapToGlobal(QPoint(0, 0)), window.size())
        except RuntimeError:
            return rect
        return rect.united(window_rect)

    # -- energy mode -----------------------------------------------------
    def _on_energy_changed(self, _active: bool) -> None:
        self._update_capture_policy()
        self.update()

    def _on_energy_finished(self, _active: bool) -> None:
        self._update_capture_policy()
        self.update()

    def _update_capture_policy(self) -> None:
        if not self._host.isVisible():
            return
        live = bool(self.config.screen_tracking and not self.config.allow_capture
                    and not self.energy.active)
        was_live = self._live_capture_active
        if live and not self._set_capture_excluded(True):
            live = False
        if (was_live and not live and not self.energy.active
                and not self.config.wallpaper):
            self.desktop.refresh_full()
        if not live:
            self._set_capture_excluded(False)
        self._live_capture_active = live
        self.desktop.set_paused(not live)

    def _set_capture_excluded(self, enabled: bool) -> bool:
        enabled = bool(enabled)
        if enabled == self._capture_excluded:
            return True
        # Capture exclusion applies to the native top-level window only.
        hwnd = int(self._host.winId())
        if enabled:
            self._capture_excluded = exclude_window_from_capture(hwnd, True)
        else:
            if self._capture_excluded:
                exclude_window_from_capture(hwnd, False)
            self._capture_excluded = False
        return True if not enabled else self._capture_excluded

    def _release_capture(self) -> None:
        self._set_capture_excluded(False)
        self._live_capture_active = False
        self.desktop.set_paused(True)

    # -- host events -------------------------------------------------------
    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        event_type = event.type()
        if obj is self._host:
            if event_type in (QEvent.Type.Move, QEvent.Type.Resize):
                self._sync_capture_region()
                self.update()
            elif event_type == QEvent.Type.ParentChange:
                self._sync_window_watch()
            elif event_type == QEvent.Type.Hide:
                self._release_capture()
            elif event_type == QEvent.Type.Close:
                # Pause immediately, but defer the full teardown: it removes
                # this very event filter, which is not safe to do while Qt is
                # iterating its filter list for the event being dispatched.
                # Host closeEvent() normally performs the shutdown first, in
                # which case the deferred call is a no-op.
                self._release_capture()
                QTimer.singleShot(0, self._deferred_shutdown)
        elif obj is self._watched_window:
            # 宿主是子控件：顶层窗口移动/缩放同样会让玻璃采样失效。
            if event_type in (QEvent.Type.Move, QEvent.Type.Resize):
                self._sync_capture_region()
                self.update()
        return super().eventFilter(obj, event)

    def _deferred_shutdown(self) -> None:
        if not shiboken6.isValid(self):
            return
        # close() followed by show() before the timer fires: keep the glass
        # alive for the re-shown window.
        if shiboken6.isValid(self._host) and self._host.isVisible():
            return
        self.shutdown()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        # close() only hides a window; re-arm so the next close tears down
        # again and restart the wallpaper watcher stopped by shutdown().
        self._shutdown_done = False
        self._sync_window_watch()
        self._sync_background_source()
        if self.config.wallpaper:
            self.wallpaper.start_watch()
        self._update_capture_policy()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._sync_capture_region()
        self.update()

    # -- painting --------------------------------------------------------
    def _render_background(self, energy: bool) -> QPixmap:
        pixmap = QPixmap(self.size())
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        if energy:
            self._paint_energy(painter)
        else:
            self._paint_normal(painter)
        painter.end()
        return pixmap

    def _paint_energy(self, painter: QPainter) -> None:
        # Energy-saving mode is a flat fill; the colour is the brush's tint.
        painter.fillRect(self.rect(), QColor(self.background_style.tint))
        painter.setPen(QPen(QColor(255, 255, 255, 26), 1))
        painter.drawRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5))

    def paint_material(self, painter: QPainter, target_rect: QRectF,
                       global_rect: QRect, style: FrostStyle | None = None) -> None:
        """Paint the frosted material for ``global_rect`` into ``target_rect``.

        ``target_rect`` is in the painter's coordinate system while
        ``global_rect`` is the matching screen rectangle used to sample the
        source image.  Sibling widgets that need their own brush (for example
        :class:`GlassMenuBar`) call this to stay pixel-continuous with the
        backdrop behind them.
        """
        style = self.background_style if style is None else style
        image, target = self.source.processed_region(
            global_rect,
            style.blur,
            style.brightness,
            style.saturation,
        )
        if image is None or image.isNull():
            # 采样区域落在捕获图之外（窗口被拖出屏幕）：用源图平均色兜底，
            # 保持与壁纸一致的玻璃色调，而不是一块与源图无关的不透明纯色。
            painter.fillRect(target_rect, self.source.average_color())
        else:
            offset = target.topLeft() - QPointF(global_rect.topLeft())
            painter.drawImage(
                QRectF(target_rect.x() + offset.x(), target_rect.y() + offset.y(),
                       target.width(), target.height()),
                image,
            )

        paint_frost_overlay(
            painter,
            target_rect,
            style,
            radius=0,
            border=False,
        )

    def _paint_normal(self, painter: QPainter) -> None:
        self.paint_material(painter, QRectF(self.rect()), self._global_rect(),
                            self.background_style)
        painter.setPen(QPen(QColor(255, 255, 255, 26), 1))
        painter.drawRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5))

    def _paint_glass(self, painter: QPainter) -> None:
        if self.energy.active:
            self._paint_energy(painter)
        else:
            self._paint_normal(painter)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        # Start from a clean translucent canvas so semi-transparent overlay
        # frames do not accumulate.
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.fillRect(self.rect(), Qt.GlobalColor.transparent)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        if self.energy.paint(painter):
            painter.end()
            return
        self._paint_glass(painter)
        painter.end()

    # -- window gestures (forwarded to the host) ---------------------------
    def _host_is_window(self) -> bool:
        """只有顶层宿主窗口才响应窗口级手势。

        当 backdrop 被嵌入到另一个窗口（宿主是被 reparent 的子控件）时，
        拖动会把宿主控件从布局里挪走（外层窗口并不会移动），双击还会关闭
        这个子控件，所以这类窗口级手势必须关掉。
        """
        host = self._host
        return host is not None and host.isWindow()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self._host_is_window():
            self._drag_offset = (
                event.globalPosition().toPoint() - self._host.frameGeometry().topLeft()
            )
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if (self._drag_offset is not None and self._host_is_window()
                and event.buttons() & Qt.MouseButton.LeftButton):
            self._host.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._drag_offset = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self._host_is_window():
            self._host.close()
            return
        super().mouseDoubleClickEvent(event)


# ===========================================================================
# Glass panel (frost card inside a glass window)
# ===========================================================================


class GlassPanel(_FrostStyleMixin, QWidget):
    """Rounded frost card painted on top of a glass window.

    Unlike :class:`GlassBackdrop` it captures nothing: it simply layers a
    :class:`FrostStyle` material over whatever is already behind it (normally a
    backdrop), so it can be used as a header bar, sidebar card or floating
    badge.  Put the panel's widgets into :attr:`content_layout`; they stay
    sharp on top of the frost.
    """

    #: Frost material painted by the panel.
    background_style: FrostStyle = BUBBLE_BACKGROUND_NORMAL

    #: QSS-accessible material fields (``qproperty-frost*``).
    (
        frostTint, frostOpacity, frostBlur, frostFrost, frostNoise, frostSheen,
        frostSaturation, frostBrightness, frostBorder, frostRadius, frostVignette,
    ) = _frost_properties()

    def __init__(self, layout, parent: QWidget | None = None, *,
                 style: FrostStyle | None = None) -> None:
        super().__init__(parent)
        self.setAutoFillBackground(False)
        # Keep the panel compact in a vertical layout: height follows content.
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.content_layout = layout
        if style is not None:
            self.setBrush(style)

    def setBrush(self, style: FrostStyle) -> None:
        """Set the material painted by this panel."""
        if not isinstance(style, FrostStyle):
            raise TypeError("setBrush 需要 FrostStyle 实例")
        self.background_style = style
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        style = self.background_style
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        paint_frost_overlay(
            painter,
            rect,
            style,
            radius=style.radius,
            border=True,
        )
        painter.end()


# ===========================================================================
# Host windows
# ===========================================================================


class _GlassHostMixin:
    """Window-level plumbing shared by all glass host classes."""

    backdrop: GlassBackdrop

    def _attach_backdrop(self) -> GlassBackdrop:
        # The window itself must be translucent; otherwise the glass would be
        # composited over an opaque client area instead of over the desktop.
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.backdrop = GlassBackdrop(self)
        return self.backdrop

    # -- public API -------------------------------------------------------
    @property
    def content_layout(self) -> QVBoxLayout:
        """Layout of the backdrop; add application widgets here."""
        return self.backdrop.content_layout

    def setBrush(self, style: FrostStyle) -> None:
        """Forward to :meth:`GlassBackdrop.setBrush`."""
        self.backdrop.setBrush(style)

    def setConfig(self, *args, **kwargs) -> None:
        """Forward to :meth:`GlassBackdrop.setConfig`."""
        self.backdrop.setConfig(*args, **kwargs)

    # -- events -----------------------------------------------------------
    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event) -> None:  # noqa: N802
        backdrop = getattr(self, 'backdrop', None)
        if backdrop is not None and shiboken6.isValid(backdrop):
            backdrop.shutdown()
        super().closeEvent(event)


class GlassWindowBase(_GlassHostMixin, QWidget):
    """Plain top-level QWidget whose client area is the glass backdrop."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._attach_backdrop())

    def setLayout(self, layout) -> None:  # noqa: N802
        """Mount an application layout on the glass content area.

        The host window already owns the backdrop layout, so Qt would reject a
        second ``setLayout()``.  Forward the layout to the backdrop instead.
        """
        if layout is None or layout is QWidget.layout(self):
            return
        self.content_layout.addLayout(layout)


class GlassMainWindow(_GlassHostMixin, QMainWindow):
    """QMainWindow whose whole client area is covered by the glass backdrop.

    The backdrop is a plain child widget that fills the client area and is
    stacked below the menu bar, status bar and central widget, so all of them
    can be transparent and share the same glass material.  (QMainWindow's own
    central widget cannot be used for the backdrop: it would exclude the menu
    bar and status bar from the glass area.)  Application content stays a
    normal central widget; ``setCentralWidget()`` keeps standard behaviour.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        backdrop = self._attach_backdrop()
        backdrop.setGeometry(self.rect())
        backdrop.lower()

    # -- layout -----------------------------------------------------------
    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        backdrop = getattr(self, 'backdrop', None)
        if backdrop is not None and shiboken6.isValid(backdrop):
            backdrop.setGeometry(self.rect())


class GlassMenuBar(_FrostStyleMixin, QMenuBar):
    """QMenuBar that paints the sidebar material over a :class:`GlassMainWindow`.

    A QMainWindow's menu bar is laid out outside the central widget, so the
    bar cannot be a child of the backdrop.  Instead the bar paints the
    backdrop's blurred source itself with :attr:`background_style`
    (``BUBBLE_SIDEBAR_NORMAL`` by default), keeping the pixels continuous with
    the window glass while giving the bar its own brush::

        window = GlassMainWindow()
        window.setMenuBar(GlassMenuBar(window))

    The material fields are QSS-able (``qproperty-frost*``) and a ``"thin"``
    preset is available through ``GlassMenuBar[glassStyle="thin"]`` in the
    theme style sheets (see :func:`apply_glass_style`).  Popup menus (``QMenu``)
    keep their normal opaque style.
    """

    #: Frost material painted by the bar (sidebar variant by default).
    background_style: FrostStyle = BUBBLE_SIDEBAR_NORMAL

    #: QSS-accessible material fields (``qproperty-frost*``).
    (
        frostTint, frostOpacity, frostBlur, frostFrost, frostNoise, frostSheen,
        frostSaturation, frostBrightness, frostBorder, frostRadius, frostVignette,
    ) = _frost_properties()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.background_style = self.background_style.copy()
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)
        # A widget-local rule outranks the application style sheet, so an
        # opaque ``QMenuBar { background-color: ... }`` there is neutralised
        # while the ::item rules keep working.
        self.setStyleSheet('QMenuBar { background: transparent; }')
        self._watched_host: QWidget | None = None
        self._watch_host(self.parentWidget())

    # -- host tracking ----------------------------------------------------
    def _watch_host(self, host: QWidget | None) -> None:
        """Re-sample the wallpaper when the host window moves/resizes."""
        if host is self._watched_host:
            return
        old = self._watched_host
        if old is not None and shiboken6.isValid(old):
            try:
                old.removeEventFilter(self)
            except RuntimeError:
                pass
        self._watched_host = host
        if host is not None:
            host.installEventFilter(self)

    def event(self, event) -> bool:  # noqa: N802
        if event.type() == QEvent.Type.ParentChange:
            self._watch_host(self.parentWidget())
        return super().event(event)

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if obj is self._watched_host and event.type() in (
            QEvent.Type.Move, QEvent.Type.Resize
        ):
            self.update()
        return super().eventFilter(obj, event)

    # -- painting ---------------------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        style = self.background_style
        backdrop = self._backdrop()
        if backdrop is None:
            # No glass window behind us: paint the brush over whatever is
            # already there (best effort, e.g. inside a plain QMainWindow).
            paint_frost_overlay(painter, QRectF(self.rect()), style,
                                radius=0, border=False)
        elif backdrop.energy.active:
            painter.fillRect(self.rect(), QColor(style.tint))
        else:
            global_rect = QRect(self.mapToGlobal(QPoint(0, 0)), self.size())
            backdrop.paint_material(painter, QRectF(self.rect()), global_rect, style)
        painter.end()
        super().paintEvent(event)

    def _backdrop(self) -> "GlassBackdrop | None":
        parent = self.parentWidget()
        backdrop = getattr(parent, 'backdrop', None) if parent is not None else None
        if backdrop is not None and shiboken6.isValid(backdrop):
            return backdrop
        return None


class GlassDialog(_GlassHostMixin, QDialog):
    """QDialog whose whole client area is glass.

    The backdrop fills the dialog edge to edge; application content is inset
    by :attr:`CONTENT_MARGIN` and separated by :attr:`CONTENT_SPACING`.
    """

    #: Padding between the dialog edge and its content.
    CONTENT_MARGIN = 12
    #: Spacing between content widgets.
    CONTENT_SPACING = 8

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._attach_backdrop())
        margin = self.CONTENT_MARGIN
        self.content_layout.setContentsMargins(margin, margin, margin, margin)
        self.content_layout.setSpacing(self.CONTENT_SPACING)

    def setLayout(self, layout) -> None:  # noqa: N802
        """Mount an application layout on the glass content area.

        The dialog owns the outer padding, so the mounted layout loses its own
        margins (they would otherwise add up to more than ``CONTENT_MARGIN``)
        and uses ``CONTENT_SPACING`` between its widgets.
        """
        if layout is None or layout is QWidget.layout(self):
            return
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(self.CONTENT_SPACING)
        self.content_layout.addLayout(layout)
