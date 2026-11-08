#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PySide6 NavigationView：统一托管窗口加载的侧边栏导航组件。

依赖：PySide6、expander.py（图标控件）、glasskit/（玻璃材质）。

Windows 11 风格自定义标题栏（保留 Windows 原生视觉效果）。

用法
----
继承 ``TitleBarMainWindow``（QMainWindow，标题栏固定在顶部，
菜单栏会显示在标题栏下方）::

    class MyWindow(TitleBarMainWindow):
        def __init__(self):
            super().__init__(title="我的应用")
            self.setCentralWidget(QTextEdit())

注意
----
* 标题栏高度在构造时用 ``height=...`` 指定（逻辑像素，默认取
  ``TitleBar.HEIGHT``），运行时用 ``set_title_bar_height()`` 修改；按钮尺寸、非客户区命中测试
  区域、``TitleBarMainWindow`` 为标题栏预留的边距都由同一个高度推导。
  直接改 ``TitleBar.HEIGHT`` 只对之后新建的实例生效。
* 仅在 Windows 上启用原生效果；其他平台退化为普通窗口。
* 如果不需要“原生按钮”（例如想自己拦截最小化/关闭），可以传
  ``native_caption=False``，此时按钮由 Qt 处理、没有贴靠布局面板。
* 窗口被系统最大化时，Qt 可能因为“无边框 + 铺满屏幕”而同时报告
  ``WindowFullScreen``，判断状态请用 ``isMaximized()``。
"""

from __future__ import annotations

import math
import sys
import time
import warnings
from enum import Enum, auto
from typing import Callable

from .icon import FontIcon, _FONT_FAMILIES

from PySide6.QtCore import (
    QAbstractAnimation,
    QEasingCurve,
    QEvent,
    QObject,
    QPoint,
    QPointF,
    QPropertyAnimation,
    QParallelAnimationGroup,
    QRect,
    QRectF,
    QSize,
    Qt,
    QTimer,
    QVariantAnimation,
    Property,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QFrame,
    QLabel,
    QLayout,
    QScrollArea,
    QScrollBar,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from typing import Optional
from .glasskit import (
    BUBBLE_BACKGROUND_NORMAL,
    BUBBLE_SIDEBAR_NORMAL,
    FrostStyle,
    blur_qimage,
    paint_frost_overlay,
    rounded_path,
)
from .glasskit.glass import GlassWindowBase

from PySide6.QtWidgets import *
from PySide6.QtCore import *
from PySide6.QtGui import *

import ctypes
import ctypes.wintypes as wt

import traceback


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

APP_FONT = "Microsoft YaHei UI"

COMPACT_WIDTH = 48
EXPANDED_WIDTH = 312
ROW_HEIGHT = 36
ROW_MARGIN_X = 4
ROW_MARGIN_TOP = 4
TOP_INDENT = 16
CHILD_INDENT = 36

ICON_SIZE = 16
ICON_GAP = 18
TEXT_SIZE = 14
ARROW_SIZE = 12
ARROW_GLYPH = "\uE70D"

SEPARATOR_COLOR = "#cccccc"
SEPARATOR_SIZE = 12
SEPARATOR_TOP = 14
SEPARATOR_BOTTOM = 12

INDICATOR_COLOR = "#99ebff"
INDICATOR_W = 2
INDICATOR_H = 16
INDICATOR_GAP = 10
#: 指示器左边界贴着菜单行（按钮）左边界；菜单行左边距即 ROW_MARGIN_X。
INDICATOR_INSET = ROW_MARGIN_X
#: 图标相对按钮左边界的位置 = 指示器宽度 + 与 fonticon 的 10px 间距。
ROW_ICON_INDENT = INDICATOR_W + INDICATOR_GAP

ANIM_MS = 250
INDICATOR_STEP_MS = 125
SCROLLBAR_MS = 250
SCROLLBAR_MIN = 2
SCROLLBAR_MAX = 5
SCROLLBAR_HIT = 6
SCROLLBAR_COLOR = "#9f9f9f"

#: 自定义悬浮提示（HoverToolTip）默认值；均可用 QSS ``qproperty-*`` 覆盖。
TOOLTIP_BG = "#2d2d2d"
TOOLTIP_TEXT = "#ffffff"
TOOLTIP_RADIUS = 8
TOOLTIP_PADDING = 12
TOOLTIP_FONT_SIZE = 14
TOOLTIP_DELAY_MS = 1000
TOOLTIP_FADE_MS = 250
TOOLTIP_OFFSET_X = 0
TOOLTIP_OFFSET_Y = -20
TOOLTIP_SHADOW = 16


SELECTED_BG = "#2d2d2d"
SELECTED_HOVER_BG = "#292929"
SELECTED_PRESSED_BG = "#2d2d2d"
HOVER_BG = "#2d2d2d"
PRESSED_BG = "#292929"
TEXT_COLOR = "#ffffff"
PRESSED_TEXT = "#cfcfcf"

CORNER_RADIUS = 4
HEADER_BUTTON_SIZE = (36, 32)
HEADER_MARGIN = 4
SHADOW_MARGIN = 24
FLYOUT_OFFSET_X = 50
#: 折叠项子菜单 Flyout 的尺寸：整宽 220，左右各 4px Padding，内容宽 212。
FLYOUT_WIDTH = 220
FLYOUT_RADIUS = 8
FLYOUT_ITEM_RADIUS = 4
FLYOUT_ROW_HEIGHT = 40
FLYOUT_ITEM_GAP = 4
FLYOUT_PADDING_X = 4
FLYOUT_PADDING_Y = 6
FLYOUT_CONTENT_MARGIN = 12
HISTORY_LIMIT = 16
SETTINGS_GLYPH = "\uE713"
SETTINGS_DIVIDER_COLOR = "#313131"
SETTINGS_DIVIDER_HEIGHT = 1
SETTINGS_BOTTOM_MARGIN = 6
SETTINGS_TOP_MARGIN = 12
GEAR_PRESS_MS = 150
GEAR_SPIN_MS = 650

#: 侧边栏常态玻璃。
SIDEBAR_GLASS = BUBBLE_SIDEBAR_NORMAL.copy()

#: Flyout 玻璃：取自 glassdemo.py 的参数，圆角改为 4px。
FLYOUT_GLASS = FrostStyle(
    tint="#2e2e2e",
    opacity=58,
    blur=40,
    frost=18,
    noise=6,
    sheen=14,
    saturation=95,
    brightness=105,
    border=24,
    radius=4,
    vignette=6,
)

#: 折叠项子菜单 Flyout 专用玻璃。
FLYOUT_FOLD_GLASS = FrostStyle(
    tint="#202020",
    opacity=65,
    blur=30,
    frost=4,
    noise=2,
    sheen=3,
    saturation=95,
    brightness=105,
    border=24,
    radius=4,
    vignette=6,
)

#: 主题默认值：QSS 可通过 ``qproperty-*`` 覆盖，未覆盖时使用这里的配置。
THEME_DEFAULTS = {
    "selectedBg": QColor(SELECTED_BG),
    "selectedHoverBg": QColor(SELECTED_HOVER_BG),
    "selectedPressedBg": QColor(SELECTED_PRESSED_BG),
    "hoverBg": QColor(HOVER_BG),
    "pressedBg": QColor(PRESSED_BG),
    "textColor": QColor(TEXT_COLOR),
    "pressedText": QColor(PRESSED_TEXT),
    "separatorColor": QColor(SEPARATOR_COLOR),
    "dividerColor": QColor(SETTINGS_DIVIDER_COLOR),
    "indicatorColor": QColor(INDICATOR_COLOR),
    "indicatorWidth": INDICATOR_W,
    "indicatorHeight": INDICATOR_H,
    "navItemRadius": CORNER_RADIUS,
    "flyoutRadius": FLYOUT_RADIUS,
    "flyoutItemRadius": FLYOUT_ITEM_RADIUS,
}

_UNSET = object()
_QWIDGETSIZE_MAX = 16777215

# ---------------------------------------------------------------------------
# 自定义悬浮提示
# ---------------------------------------------------------------------------


class HoverToolTip(QWidget):
    """深色悬浮提示气泡：12px Padding、8px 圆角、窗口同款软阴影。

    默认值见 ``TOOLTIP_*`` 常量；可通过 QSS ``qproperty-tip*`` 覆盖。
    顶层窗口不抢焦点、不接收鼠标事件，因此可以超出主窗口边界。
    """

    _instance: "HoverToolTip | None" = None

    def __init__(self, parent=None):
        super().__init__(parent)
        self._text = ""
        self._owner = None
        self._anchor = QPoint()
        self._bg_color = QColor(TOOLTIP_BG)
        self._text_color = QColor(TOOLTIP_TEXT)
        self._radius = TOOLTIP_RADIUS
        self._padding = TOOLTIP_PADDING
        self._font_size = TOOLTIP_FONT_SIZE
        self._offset_x = TOOLTIP_OFFSET_X
        self._offset_y = TOOLTIP_OFFSET_Y
        self._delay_ms = TOOLTIP_DELAY_MS
        self._fade_ms = TOOLTIP_FADE_MS
        self._font = QFont(APP_FONT)
        self._font.setPixelSize(self._font_size)
        self._fade: QPropertyAnimation | None = None

        self.setWindowFlags(
            Qt.ToolTip | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint
            | Qt.WindowDoesNotAcceptFocus | Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.NoFocus)
        self.setObjectName("HoverToolTip")

    # -- QSS 可覆盖参数 ---------------------------------------------------
    def get_tip_bg_color(self) -> QColor:
        return self._bg_color

    def set_tip_bg_color(self, color):
        color = QColor(color)
        if color != self._bg_color:
            self._bg_color = color
            self.update()

    def get_tip_text_color(self) -> QColor:
        return self._text_color

    def set_tip_text_color(self, color):
        color = QColor(color)
        if color != self._text_color:
            self._text_color = color
            self.update()

    def get_tip_radius(self) -> int:
        return self._radius

    def set_tip_radius(self, value):
        value = max(0, int(value))
        if value != self._radius:
            self._radius = value
            self._relayout()

    def get_tip_padding(self) -> int:
        return self._padding

    def set_tip_padding(self, value):
        value = max(0, int(value))
        if value != self._padding:
            self._padding = value
            self._relayout()

    def get_tip_font_size(self) -> int:
        return self._font_size

    def set_tip_font_size(self, value):
        value = max(1, int(value))
        if value != self._font_size:
            self._font_size = value
            self._font.setPixelSize(value)
            self._relayout()

    def get_tip_offset_x(self) -> int:
        return self._offset_x

    def set_tip_offset_x(self, value):
        self._offset_x = int(value)
        self._relayout()

    def get_tip_offset_y(self) -> int:
        return self._offset_y

    def set_tip_offset_y(self, value):
        self._offset_y = int(value)
        self._relayout()

    def get_tip_delay_ms(self) -> int:
        return self._delay_ms

    def set_tip_delay_ms(self, value):
        self._delay_ms = max(0, int(value))

    def get_tip_fade_ms(self) -> int:
        return self._fade_ms

    def set_tip_fade_ms(self, value):
        self._fade_ms = max(0, int(value))

    tipBgColor = Property(QColor, get_tip_bg_color, set_tip_bg_color)
    tipTextColor = Property(QColor, get_tip_text_color, set_tip_text_color)
    tipRadius = Property(int, get_tip_radius, set_tip_radius)
    tipPadding = Property(int, get_tip_padding, set_tip_padding)
    tipFontSize = Property(int, get_tip_font_size, set_tip_font_size)
    tipOffsetX = Property(int, get_tip_offset_x, set_tip_offset_x)
    tipOffsetY = Property(int, get_tip_offset_y, set_tip_offset_y)
    tipDelayMs = Property(int, get_tip_delay_ms, set_tip_delay_ms)
    tipFadeMs = Property(int, get_tip_fade_ms, set_tip_fade_ms)

    # -- 尺寸 / 位置 -------------------------------------------------------
    def _panel_size(self) -> QSize:
        metrics = QFontMetrics(self._font)
        width = max(1, metrics.horizontalAdvance(self._text))
        height = max(1, metrics.height())
        return QSize(width + self._padding * 2 + TOOLTIP_SHADOW * 2,
                     height + self._padding * 2 + TOOLTIP_SHADOW * 2)

    def _relayout(self) -> None:
        if not self.isVisible():
            return
        size = self._panel_size()
        self.resize(size)
        self.move(self._anchor + QPoint(self._offset_x - TOOLTIP_SHADOW,
                                        self._offset_y - TOOLTIP_SHADOW))
        self.update()

    def show_for(self, text: str, global_pos: QPoint, owner=None) -> None:
        """在鼠标位置显示提示；visible panel 左上角 = 鼠标 + offset。"""
        self._text = text or ""
        self._owner = owner
        self._anchor = QPoint(global_pos)
        self.ensurePolished()
        self._font.setPixelSize(self._font_size)
        if self._fade is not None:
            self._fade.stop()
            self._fade = None
        size = self._panel_size()
        self.resize(size)
        self.move(self._anchor + QPoint(self._offset_x - TOOLTIP_SHADOW,
                                        self._offset_y - TOOLTIP_SHADOW))
        if not self.isVisible():
            self.setWindowOpacity(0.0)
            self.show()
            self.raise_()
            self._animate_opacity(1.0)
        else:
            self.setWindowOpacity(1.0)
            self.update()

    def hide_for(self, owner=None) -> None:
        if not self.isVisible():
            return
        if owner is not None and self._owner is not owner:
            return
        self._owner = None
        self._animate_opacity(0.0, hide=True)

    def _animate_opacity(self, target: float, *, hide: bool = False) -> None:
        if self._fade is not None:
            self._fade.stop()
        if self._fade_ms <= 0:
            self.setWindowOpacity(target)
            if hide:
                self.hide()
            self._fade = None
            return
        anim = QPropertyAnimation(self, b"windowOpacity", self)
        anim.setDuration(self._fade_ms)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.setStartValue(float(self.windowOpacity()))
        anim.setEndValue(float(target))
        if hide:
            anim.finished.connect(self.hide)
        self._fade = anim
        anim.start()

    # -- 绘制 -------------------------------------------------------------
    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)

        margin = TOOLTIP_SHADOW
        panel = QRectF(self.rect()).adjusted(margin, margin, -margin, -margin)
        radius = min(float(self._radius), panel.width() / 2.0,
                     panel.height() / 2.0)

        # 分层圆角矩形模拟窗口软阴影（与系统菜单的做法一致）。
        painter.setPen(Qt.NoPen)
        steps = 12
        for step in range(steps, 0, -1):
            grow = margin * step / float(steps)
            alpha = int(6 + (steps - step) * 1.4)
            painter.setBrush(QColor(0, 0, 0, alpha))
            painter.drawRoundedRect(
                panel.adjusted(-grow, -grow, grow, grow),
                radius + grow, radius + grow)

        painter.setBrush(self._bg_color)
        painter.drawRoundedRect(panel, radius, radius)

        painter.setPen(self._text_color)
        painter.setFont(self._font)
        painter.drawText(
            panel.adjusted(self._padding, self._padding,
                           -self._padding, -self._padding),
            Qt.AlignLeft | Qt.AlignVCenter, self._text)
        painter.end()

    # -- 单例 -------------------------------------------------------------
    @classmethod
    def shared(cls) -> "HoverToolTip":
        if cls._instance is not None:
            try:
                cls._instance.isVisible()
            except RuntimeError:
                # C++ 对象已在应用退出阶段销毁，重新创建一个即可。
                cls._instance = None
        if cls._instance is None:
            cls._instance = HoverToolTip()
        return cls._instance


class HoverTip(QObject):
    """给控件挂一个“静止 1 秒才出现”的自定义悬浮提示。"""

    def __init__(self, widget: QWidget, text: str = "", parent=None):
        super().__init__(parent or widget)
        self._widget = widget
        self._text = text or ""
        self._anchor = QPoint()
        self._armed = False
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._show)
        widget.setMouseTracking(True)
        widget.installEventFilter(self)

    def text(self) -> str:
        return self._text

    def setText(self, text: str) -> None:
        text = text or ""
        if text == self._text:
            return
        self._text = text
        if not text:
            self._cancel()
            self._hide()

    def _cancel(self) -> None:
        self._timer.stop()
        self._armed = False

    def _hide(self) -> None:
        bubble = HoverToolTip._instance
        if bubble is None:
            return
        try:
            bubble.hide_for(self)
        except RuntimeError:
            HoverToolTip._instance = None

    def _show(self) -> None:
        if not self._armed or not self._text:
            return
        try:
            if not self._widget.isVisible():
                self._cancel()
                return
            HoverToolTip.shared().show_for(self._text, QCursor.pos(),
                                           owner=self)
        except RuntimeError:
            self._cancel()
            HoverToolTip._instance = None

    def eventFilter(self, obj, event) -> bool:
        if obj is not self._widget:
            return super().eventFilter(obj, event)
        event_type = event.type()
        if event_type in (QEvent.Type.Enter, QEvent.Type.HoverEnter):
            if self._text:
                try:
                    self._anchor = event.globalPosition().toPoint()
                except AttributeError:
                    self._anchor = QCursor.pos()
                self._armed = True
                bubble = HoverToolTip.shared()
                bubble.ensurePolished()
                self._timer.start(bubble.get_tip_delay_ms())
        elif event_type in (QEvent.Type.MouseMove, QEvent.Type.HoverMove):
            if self._armed or HoverToolTip._instance is not None:
                try:
                    position = event.globalPosition().toPoint()
                except AttributeError:
                    position = QCursor.pos()
                if position != self._anchor:
                    self._cancel()
                    self._hide()
        elif event_type in (QEvent.Type.Leave, QEvent.Type.HoverLeave,
                            QEvent.Type.MouseButtonPress,
                            QEvent.Type.Wheel,
                            QEvent.Type.Hide,
                            QEvent.Type.Destroy):
            self._cancel()
            self._hide()
        return super().eventFilter(obj, event)


def attach_hover_tip(widget: QWidget, text: str = "") -> HoverTip:
    """给控件挂自定义悬浮提示；重复调用时复用已有对象。"""
    tip = getattr(widget, "_hover_tip", None)
    if isinstance(tip, HoverTip):
        tip.setText(text)
        return tip
    tip = HoverTip(widget, text)
    widget._hover_tip = tip
    return tip


def _theme_qcolor(name: str):
    def getter(self):
        return self._theme[name]

    def setter(self, value):
        color = QColor(value)
        if color != self._theme[name]:
            self._theme[name] = color
            self._refresh_theme()

    return Property(QColor, getter, setter)


def _theme_int(name: str):
    def getter(self):
        return self._theme[name]

    def setter(self, value):
        number = int(value)
        if number != self._theme[name]:
            self._theme[name] = number
            self._refresh_theme()

    return Property(int, getter, setter)


# ---------------------------------------------------------------------------
# 枚举
# ---------------------------------------------------------------------------


class PaneStateEnum(Enum):
    """侧边栏形态。"""

    Auto = auto()          # 使用窗口宽度阈值
    Expanded = auto()      # 强制展开
    Compact = auto()       # 仅图标
    ForceCompact = auto()  # 强制仅图标
    Hide = auto()          # 强制隐藏


class PaneShowInlineEnum(Enum):
    """展开呈现方式。"""

    Auto = auto()
    Inline = auto()
    Flyout = auto()


def _coerce_pane_state(value) -> PaneStateEnum:
    if isinstance(value, PaneStateEnum):
        return value
    if isinstance(value, str):
        key = value.strip().lower().replace("_", "").replace("-", "")
        for member in PaneStateEnum:
            if member.name.lower() == key:
                return member
    raise TypeError(f"Invalid PaneStateEnum: {value!r}")


def _coerce_show_inline(value) -> PaneShowInlineEnum:
    if isinstance(value, PaneShowInlineEnum):
        return value
    if isinstance(value, str):
        key = value.strip().lower().replace("_", "").replace("-", "")
        for member in PaneShowInlineEnum:
            if member.name.lower() == key:
                return member
    raise TypeError(f"Invalid PaneShowInlineEnum: {value!r}")


def _disconnect_signals(*signals) -> None:
    """静默断开（可能没有任何连接的）信号。"""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        for signal in signals:
            try:
                signal.disconnect()
            except (RuntimeError, TypeError):
                pass


# ---------------------------------------------------------------------------
# 缓动与按钮动画（汉堡 / 返回）
# ---------------------------------------------------------------------------


def cubic_bezier(x1: float, y1: float, x2: float, y2: float):
    """返回 CSS cubic-bezier 缓动函数 f(t), t∈[0,1]。"""

    def f(t: float) -> float:
        if t <= 0.0:
            return 0.0
        if t >= 1.0:
            return 1.0
        lo, hi = 0.0, 1.0
        for _ in range(22):
            u = (lo + hi) * 0.5
            x = 3.0 * (1.0 - u) ** 2 * u * x1 + 3.0 * (1.0 - u) * u * u * x2 + u ** 3
            if x < t:
                lo = u
            else:
                hi = u
        u = (lo + hi) * 0.5
        return 3.0 * (1.0 - u) ** 2 * u * y1 + 3.0 * (1.0 - u) * u * u * y2 + u ** 3

    return f


LINEAR = cubic_bezier(0.0, 0.0, 1.0, 1.0)
EASE_PRESS = cubic_bezier(0.167, 0.167, 0.0, 1.0)
EASE_HAMMER_OUT = cubic_bezier(0.85, 0.0, 0.75, 1.0)
EASE_HAMMER_SETTLE = cubic_bezier(0.35, 0.0, 0.0, 1.0)
EASE_BACK_TIP = cubic_bezier(0.85, 0.0, 0.75, 1.0)
EASE_BACK_STEM = cubic_bezier(0.55, 0.0, 0.75, 1.0)
EASE_BACK_SETTLE = cubic_bezier(0.35, 0.0, 0.0, 1.0)

HAMBURGER_W = 44.75
HAMBURGER_T = 2.75
HAMBURGER_YS = (-13.75, 0.41, 13.75)

BACK_TIP_X = -18.0
BACK_NOTCH_X = -12.0
BACK_STEM_RIGHT = 40.875
BACK_STEM_T = 2.25

ICON_COLOR = QColor("#ffffff")
ICON_COLOR_PRESSED = QColor(PRESSED_TEXT)
ICON_COLOR_DISABLED = QColor(255, 255, 255, 90)


class AnimatedIconButton(QAbstractButton):
    """汉堡 / 返回按钮：Fluent 风格按下、松开时间线动画。"""

    def __init__(self, kind: str, icon_size: int = 18,
                 button_size=HEADER_BUTTON_SIZE, parent=None):
        super().__init__(parent)
        assert kind in ("hamburger", "back")
        self._kind = kind
        self._icon_size = icon_size
        self.setFixedSize(*button_size)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover, True)
        self.setAccessibleName({"hamburger": "菜单", "back": "返回"}[kind])
        self._hover_tip = attach_hover_tip(
            self, "展开菜单" if kind == "hamburger" else "返回")

        self._hover = False
        self._pressed = False
        self._state = "normal"
        self._vals = self._default_vals()
        self._anim: dict | None = None

        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.PreciseTimer)
        self._timer.setInterval(15)
        self._timer.timeout.connect(self._tick)

    def set_button_size(self, width: int, height: int) -> None:
        """切换按钮尺寸（NavigationView 内为 36×32，移入 TitleBar 后为 40×48）。"""
        width = max(1, int(width))
        height = max(1, int(height))
        if self.width() != width or self.height() != height:
            self.setFixedSize(width, height)
            self.update()

    def set_hover_text(self, text: str) -> None:
        self._hover_tip.setText(text)

    # -- 状态参数 ---------------------------------------------------------
    def _default_vals(self) -> dict:
        if self._kind == "hamburger":
            return {"wf": 1.0, "ty": 1.0}
        return {"tip_dx": 0.0, "stem_right": BACK_STEM_RIGHT}

    # -- 状态机 -----------------------------------------------------------
    def _refresh_state(self) -> None:
        if not self.isEnabled():
            new_state = "normal"
        else:
            new_state = "pressed" if self._pressed else ("pointerover" if self._hover else "normal")
        if new_state == self._state:
            return
        old_state, self._state = self._state, new_state
        if new_state == "pressed":
            self._play_press()
        elif old_state == "pressed":
            self._play_release()
        self.update()

    def _play_press(self) -> None:
        if self._kind == "hamburger":
            self._start([(150.0, {"wf": EASE_PRESS, "ty": EASE_PRESS},
                          {"wf": 0.521, "ty": 1.0})])
        else:
            self._start([(150.0, {"tip_dx": EASE_PRESS, "stem_right": EASE_PRESS},
                          {"tip_dx": 9.0, "stem_right": 41.813})])

    def _play_release(self) -> None:
        if self._kind == "hamburger":
            self._start([
                (133.0, {"wf": EASE_HAMMER_OUT, "ty": EASE_HAMMER_OUT},
                 {"wf": 1.048, "ty": 0.9937}),
                (184.0, {"wf": EASE_HAMMER_SETTLE, "ty": EASE_HAMMER_SETTLE},
                 {"wf": 1.0, "ty": 1.0}),
            ])
        else:
            self._start([
                (167.0, {"tip_dx": EASE_BACK_TIP, "stem_right": EASE_BACK_STEM},
                 {"tip_dx": -4.016, "stem_right": 37.125}),
                (150.0, {"tip_dx": EASE_BACK_SETTLE, "stem_right": EASE_BACK_SETTLE},
                 {"tip_dx": 0.0, "stem_right": BACK_STEM_RIGHT}),
            ])

    # -- 时间线 -----------------------------------------------------------
    def _start(self, phases) -> None:
        self._anim = {
            "phases": phases,
            "i": 0,
            "t0": time.perf_counter(),
            "phase_from": dict(self._vals),
        }
        self._timer.start()

    def _finish(self) -> None:
        self._anim = None
        self._timer.stop()
        self.update()

    def _tick(self) -> None:
        anim = self._anim
        if anim is None:
            return
        now = time.perf_counter()
        elapsed = (now - anim["t0"]) * 1000.0
        while anim["i"] < len(anim["phases"]):
            duration, eases, targets = anim["phases"][anim["i"]]
            if elapsed < duration:
                p = elapsed / duration
                for key, target in targets.items():
                    start = anim["phase_from"][key]
                    self._vals[key] = start + (target - start) * eases[key](p)
                self.update()
                return
            self._vals.update(targets)
            elapsed -= duration
            anim["t0"] += duration / 1000.0
            anim["i"] += 1
            if anim["i"] < len(anim["phases"]):
                anim["phase_from"] = dict(self._vals)
        self._finish()

    # -- 鼠标 / 键盘 ------------------------------------------------------
    def mousePressEvent(self, event) -> None:
        if not self.isEnabled():
            return
        if event.button() == Qt.LeftButton:
            self._pressed = True
            self._refresh_state()
            event.accept()

    def mouseReleaseEvent(self, event) -> None:
        if not self.isEnabled() or event.button() != Qt.LeftButton or not self._pressed:
            return
        self._pressed = False
        self._hover = self.rect().contains(event.position().toPoint())
        self._refresh_state()
        if self._hover:
            self.click()
        event.accept()

    def enterEvent(self, event) -> None:
        self._hover = True
        if not self._pressed:
            self._refresh_state()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover = False
        if not self._pressed:
            self._refresh_state()
        super().leaveEvent(event)

    def keyPressEvent(self, event) -> None:
        if not self.isEnabled():
            return
        if event.key() == Qt.Key_Space and not event.isAutoRepeat():
            self._pressed = True
            self._refresh_state()
            event.accept()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event) -> None:
        if not self.isEnabled():
            return
        if event.key() == Qt.Key_Space and not event.isAutoRepeat() and self._pressed:
            self._pressed = False
            self._refresh_state()
            self.click()
            event.accept()
            return
        super().keyReleaseEvent(event)

    def changeEvent(self, event) -> None:
        if event.type() == QEvent.EnabledChange:
            self._pressed = False
            self._hover = self.rect().contains(self.mapFromGlobal(self.cursor().pos()))
            self._refresh_state()
            self.update()
        super().changeEvent(event)

    # -- 绘制 -------------------------------------------------------------
    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)

        enabled = self.isEnabled()
        if enabled and self._pressed:
            painter.fillPath(self._background_path(), QColor(PRESSED_BG))
        elif enabled and self._hover:
            painter.fillPath(self._background_path(), QColor(HOVER_BG))

        painter.translate(self.width() / 2.0, self.height() / 2.0)
        scale = self._icon_size / 48.0
        painter.scale(scale, scale)

        if not enabled:
            color = ICON_COLOR_DISABLED
        else:
            color = ICON_COLOR_PRESSED if self._pressed else ICON_COLOR
        if self._kind == "hamburger":
            self._paint_hamburger(painter, color)
        else:
            self._paint_back(painter, color)
        painter.end()

    def _background_path(self) -> QPainterPath:
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), CORNER_RADIUS, CORNER_RADIUS)
        return path

    def _paint_hamburger(self, painter: QPainter, color: QColor) -> None:
        width = HAMBURGER_W * self._vals["wf"]
        thickness = HAMBURGER_T * self._vals["ty"]
        painter.setPen(Qt.NoPen)
        painter.setBrush(color)
        radius = thickness / 2.0
        for y in HAMBURGER_YS:
            rect = QRectF(-width / 2.0, y - thickness / 2.0, width, thickness)
            painter.drawRoundedRect(rect, radius, radius)

    def _paint_back(self, painter: QPainter, color: QColor) -> None:
        dx = self._vals["tip_dx"]
        stem_right = self._vals["stem_right"] - 24.0
        stem_left = BACK_NOTCH_X + dx

        head_points = [
            (-1.88, 15.45),
            (-0.37, 13.79),
            (-14.24, 1.12),
            (-11.99, 1.10),
            (-11.99, -1.15),
            (-14.24, -1.13),
            (-0.37, -13.79),
            (-1.88, -15.45),
            (-17.44, -1.25),
            (BACK_TIP_X, 0.0),
            (-17.44, 1.25),
        ]
        head = QPainterPath(QPointF(head_points[0][0] + dx, head_points[0][1]))
        for x, y in head_points[1:]:
            head.lineTo(QPointF(x + dx, y))
        head.closeSubpath()

        painter.setPen(Qt.NoPen)
        painter.setBrush(color)
        painter.drawPath(head)

        pen = QPen(color, BACK_STEM_T)
        pen.setCapStyle(Qt.FlatCap)
        painter.setPen(pen)
        painter.drawLine(QPointF(stem_left, 0.0), QPointF(stem_right, 0.0))

        painter.setPen(Qt.NoPen)
        radius = BACK_STEM_T / 2.0
        painter.drawEllipse(QPointF(stem_right, 0.0), radius, radius)


# ---------------------------------------------------------------------------
# 胶囊滚动条
# ---------------------------------------------------------------------------


class _CapsuleScrollBar(QScrollBar):
    """2px 胶囊滚动条；鼠标悬浮时 250ms 动画到 5px。"""

    def __init__(self, parent=None):
        super().__init__(Qt.Vertical, parent)
        self.setFixedWidth(SCROLLBAR_HIT)
        self.setAutoFillBackground(False)
        self.setFocusPolicy(Qt.NoFocus)
        self.setCursor(Qt.ArrowCursor)
        self._bar_width = float(SCROLLBAR_MIN)
        self._bar_color = QColor(SCROLLBAR_COLOR)
        self._anim = QPropertyAnimation(self, b"barWidth", self)
        self._anim.setDuration(SCROLLBAR_MS)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

    def get_bar_color(self) -> QColor:
        return self._bar_color

    def set_bar_color(self, color):
        color = QColor(color)
        if color != self._bar_color:
            self._bar_color = color
            self.update()

    barColor = Property(QColor, get_bar_color, set_bar_color)

    def get_bar_width(self) -> float:
        return self._bar_width

    def set_bar_width(self, value):
        value = float(value)
        if value != self._bar_width:
            self._bar_width = value
            self.update()

    barWidth = Property(float, get_bar_width, set_bar_width)

    def _animate_to(self, target: float) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._bar_width)
        self._anim.setEndValue(float(target))
        self._anim.start()

    def enterEvent(self, event) -> None:
        self._animate_to(SCROLLBAR_MAX)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._animate_to(SCROLLBAR_MIN)
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(Qt.NoPen)

        span = self.maximum() - self.minimum()
        if span <= 0:
            return
        bar_width = max(1.0, self._bar_width)
        track = float(self.height())
        page = max(1, self.pageStep())
        handle = max(24.0, track * page / float(page + span))
        travel = max(0.0, track - handle)
        ratio = (self.value() - self.minimum()) / float(span)
        top = travel * ratio
        x = self.width() - bar_width
        painter.setBrush(self._bar_color)
        painter.drawRoundedRect(
            QRectF(x, top, bar_width, handle), bar_width / 2.0, bar_width / 2.0
        )
        painter.end()


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


class NavItem(QObject):
    """普通菜单项（也用于折叠菜单的子项与内置设置项）。

    顶层项的 ``globalIndex`` 是导航选择索引；子项的 ``index`` 是兄弟局部索引，
    ``globalIndex`` 返回父折叠项的全局索引（选择 API 只按顶层/折叠项编号）。
    """

    clicked = Signal()
    pressed = Signal()
    released = Signal()
    stateChanged = Signal(bool)

    def __init__(self, navigation, fonticon: str, name: str, layout=None,
                 fold=None, settings: bool = False):
        super().__init__(navigation)
        self._nav = navigation
        self._fonticon = fonticon or ""
        self._name = name or ""
        self._layout = layout
        self._fold = fold
        self._settings = bool(settings)
        self._selected = False
        self._alive = True
        self._index = -1
        self._row: "_NavRow | None" = None
        self._wrapper: "QWidget | None" = None
        self._page: "_ContentPage | None" = None

    # -- 有效性 -----------------------------------------------------------
    def isValid(self) -> bool:
        return self._alive

    @property
    def deleted(self) -> bool:
        return not self._alive

    def _require_alive(self) -> None:
        if not self._alive:
            raise RuntimeError("Thid NavItem is already removed.")

    # -- 属性 -------------------------------------------------------------
    @property
    def fonticon(self) -> str:
        return self._fonticon if self._alive else ""

    @fonticon.setter
    def fonticon(self, value: str):
        self._require_alive()
        self._fonticon = value or ""
        self._nav._refresh_item(self)

    @property
    def name(self) -> str:
        return self._name if self._alive else ""

    @name.setter
    def name(self, value: str):
        self._require_alive()
        self._name = value or ""
        self._nav._refresh_item(self)

    @property
    def layout(self):
        return self._layout if self._alive else None

    @layout.setter
    def layout(self, value):
        self._require_alive()
        self._nav._set_item_layout(self, value)

    @property
    def index(self) -> int:
        return self._index if self._alive else -1

    @property
    def globalIndex(self) -> int:
        if not self._alive:
            return -1
        if self._fold is not None:
            return self._fold.globalIndex
        return self._nav._global_index_of(self)

    @property
    def selected(self) -> bool:
        return self._selected if self._alive else False

    @property
    def isSettings(self) -> bool:
        return self._settings

    def select(self, animate: bool = False) -> None:
        """程序化选中本项（子项也可直接调用）。"""
        self._require_alive()
        if self._settings:
            self._nav._select_target(top=None, child=None, settings=True,
                                     animate=animate, record=False)
            return
        if self._fold is not None:
            self._nav._select_target(top=self._fold, child=self, settings=False,
                                     animate=animate, record=False)
        else:
            self._nav._select_target(top=self, child=None, settings=False,
                                     animate=animate, record=False)

    def _set_selected(self, value: bool) -> None:
        if not self._alive:
            return
        value = bool(value)
        if value == self._selected:
            return
        self._selected = value
        if self._row is not None:
            self._row.set_selected(value)
        self.stateChanged.emit(value)

    def _invalidate(self) -> None:
        if not self._alive:
            return
        self._alive = False
        self._selected = False
        self._layout = None
        self._index = -1
        if self._row is not None:
            self._row.deleteLater()
            self._row = None
        if self._wrapper is not None:
            self._wrapper.deleteLater()
            self._wrapper = None
        _disconnect_signals(self.clicked, self.pressed, self.released,
                            self.stateChanged)
        self.setParent(None)

    def __repr__(self) -> str:
        state = "deleted" if not self._alive else f"index={self._index}"
        return f"NavItem({self._name!r}, {state})"


class NavFoldItem(QObject):
    """可展开菜单项。内部只能添加普通子项，不能再嵌套折叠项。

    ``index`` 是折叠项内部的局部索引，``globalIndex`` 是顶层选择索引。
    ``selected`` 表示标题或任一子项被选中（分支选中）。
    """

    clicked = Signal()
    pressed = Signal()
    released = Signal()
    selectedChanged = Signal(int)
    foldStateChanged = Signal(bool)
    stateChanged = Signal(bool)

    def __init__(self, navigation, fonticon: str, name: str, layout=None):
        super().__init__(navigation)
        self._nav = navigation
        self._fonticon = fonticon or ""
        self._name = name or ""
        self._layout = layout
        self._selected = False
        self._expanded = False
        self._alive = True
        self._index = -1
        self._children: list[NavItem] = []
        self._last_child_selected: int | None = None
        self._row: "_FoldRow | None" = None
        self._group: "_FoldGroup | None" = None
        self._page: "_ContentPage | None" = None

    # -- 有效性 -----------------------------------------------------------
    def isValid(self) -> bool:
        return self._alive

    @property
    def deleted(self) -> bool:
        return not self._alive

    def _require_alive(self) -> None:
        if not self._alive:
            raise RuntimeError("This NavFoldItem is already removed.")

    # -- 属性 -------------------------------------------------------------
    @property
    def fonticon(self) -> str:
        return self._fonticon if self._alive else ""

    @fonticon.setter
    def fonticon(self, value: str):
        self._require_alive()
        self._fonticon = value or ""
        self._nav._refresh_item(self)

    @property
    def name(self) -> str:
        return self._name if self._alive else ""

    @name.setter
    def name(self, value: str):
        self._require_alive()
        self._name = value or ""
        self._nav._refresh_item(self)

    @property
    def layout(self):
        return self._layout if self._alive else None

    @layout.setter
    def layout(self, value):
        self._require_alive()
        self._nav._set_item_layout(self, value)

    @property
    def index(self) -> int:
        return self._index if self._alive else -1

    @property
    def globalIndex(self) -> int:
        if not self._alive:
            return -1
        return self._nav._global_index_of(self)

    @property
    def selected(self) -> bool:
        return self._selected if self._alive else False

    @property
    def expanded(self) -> bool:
        return self._expanded if self._alive else False

    @expanded.setter
    def expanded(self, value: bool):
        self._require_alive()
        self._nav._set_fold_expanded(self, bool(value), animate=True)

    def children(self) -> list[NavItem]:
        return [child for child in self._children if child.isValid()]

    def select(self, animate: bool = False) -> None:
        self._require_alive()
        self._nav._select_target(top=self, child=None, settings=False,
                                 animate=animate, record=False)

    # -- 子项 -------------------------------------------------------------
    def addNavItem(self, fonticon: str, name: str, layout=None) -> NavItem:
        self._require_alive()
        return self._nav._add_child(self, fonticon, name, layout)

    def _set_selected(self, value: bool) -> None:
        if not self._alive:
            return
        value = bool(value)
        if value == self._selected:
            return
        self._selected = value
        self.stateChanged.emit(value)

    def _set_expanded(self, value: bool) -> None:
        if not self._alive:
            return
        value = bool(value)
        if value == self._expanded:
            return
        self._expanded = value
        self.foldStateChanged.emit(value)

    def _emit_child_selected(self, index: int) -> None:
        if not self._alive:
            return
        if index == self._last_child_selected:
            return
        self._last_child_selected = index
        self.selectedChanged.emit(index)

    def _invalidate(self) -> None:
        if not self._alive:
            return
        self._alive = False
        self._selected = False
        self._expanded = False
        self._nav._remembered_folds.discard(self)
        # 子项的控件由 _FoldGroup 统一销毁，这里只让模型失效。
        for child in self._children:
            child._alive = False
            child._selected = False
            child._layout = None
            child._index = -1
            child._row = None
            child._wrapper = None
            _disconnect_signals(child.clicked, child.pressed, child.released,
                                child.stateChanged)
            child.setParent(None)
        self._children = []
        self._layout = None
        self._index = -1
        if self._group is not None:
            self._group.deleteLater()
            self._group = None
        self._row = None
        _disconnect_signals(self.clicked, self.pressed, self.released,
                            self.selectedChanged, self.foldStateChanged,
                            self.stateChanged)
        self.setParent(None)

    def __repr__(self) -> str:
        state = "deleted" if not self._alive else f"index={self._index}"
        return f"NavFoldItem({self._name!r}, {state})"


class _SeparatorEntry:
    """内部：分隔描述符模型。"""

    def __init__(self, text: str):
        self.text = text or ""
        self.widget: "_SeparatorWidget | None" = None


class _LineEntry:
    """内部：``addSeparateLine()`` 添加的 1px 横线模型。"""

    def __init__(self):
        self.widget: "QWidget | None" = None


# ---------------------------------------------------------------------------
# 菜单行
# ---------------------------------------------------------------------------


def _wrap_row(row: QWidget, top_margin: int = ROW_MARGIN_TOP) -> QWidget:
    """给一行加上顶部边距（左右/下边距由菜单布局提供）。"""
    top_margin = max(0, int(top_margin))
    wrapper = QWidget()
    wrapper.setFixedHeight(ROW_HEIGHT + top_margin)
    layout = QVBoxLayout(wrapper)
    layout.setContentsMargins(0, top_margin, 0, 0)
    layout.setSpacing(0)
    layout.addWidget(row)
    return wrapper


class _NavRow(QWidget):
    """自绘菜单行：背景、图标、文字、折叠箭头。"""

    clicked = Signal()
    pressed = Signal()
    released = Signal()

    def __init__(self, item, compact: bool = False, child: bool = False,
                 parent=None, content_margin: int | None = None):
        super().__init__(parent)
        self._item = item
        self._compact = bool(compact)
        self._child = bool(child)
        self._content_margin = content_margin
        self._selected = False
        self._hover = False
        self._pressed = False
        self._expanded = False
        self._fold = isinstance(item, NavFoldItem)

        self.setFixedHeight(ROW_HEIGHT)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover, True)
        self.setAccessibleName(item.name)
        self._hover_tip = attach_hover_tip(
            self, item.name if self._compact else "")

        self._font = QFont(APP_FONT)
        self._font.setPixelSize(TEXT_SIZE)

        self._icon = FontIcon(item.fonticon, size=ICON_SIZE, parent=self)
        self._icon.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._arrow: FontIcon | None = None
        if self._fold:
            self._arrow = FontIcon(ARROW_GLYPH, size=ARROW_SIZE)
            self._arrow.setParent(self)
            self._arrow.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            self._arrow.set_angle(0.0)

        self._arrow_anim = QPropertyAnimation(self._arrow, b"angle", self) if self._arrow else None
        if self._arrow_anim is not None:
            self._arrow_anim.setDuration(ANIM_MS)
            self._arrow_anim.setEasingCurve(QEasingCurve.InOutCubic)

        # 内置“设置”项的齿轮：按下 -20°，松开转完整一圈（与旧版按钮动画一致）。
        self._gear_anim: QPropertyAnimation | None = None
        if getattr(item, "isSettings", False):
            self.pressed.connect(self._on_gear_press)
            self.released.connect(self._on_gear_release)

        self._apply_visual_state()
        self._layout_children()

    # -- 外部状态 ---------------------------------------------------------
    def set_selected(self, value: bool) -> None:
        value = bool(value)
        if value == self._selected:
            return
        self._selected = value
        self._apply_visual_state()
        self.update()

    def set_compact(self, compact: bool) -> None:
        compact = bool(compact)
        if compact == self._compact:
            return
        self._compact = compact
        self._hover_tip.setText(self._item.name if compact else "")
        self._layout_children()
        self.update()

    def set_expanded(self, expanded: bool, animate: bool = True) -> None:
        if self._arrow is None:
            return
        expanded = bool(expanded)
        if expanded == self._expanded:
            return
        self._expanded = expanded
        target = 180.0 if expanded else 0.0
        if self._arrow_anim is not None and animate:
            self._arrow_anim.stop()
            self._arrow_anim.setStartValue(float(self._arrow.get_angle()))
            self._arrow_anim.setEndValue(target)
            self._arrow_anim.start()
        else:
            if self._arrow_anim is not None:
                self._arrow_anim.stop()
            self._arrow.set_angle(target)

    def refresh_content(self) -> None:
        self._icon.setText(self._item.fonticon)
        self.setAccessibleName(self._item.name)
        self._hover_tip.setText(self._item.name if self._compact else "")
        self._layout_children()
        self.update()

    # -- 设置齿轮转圈 -----------------------------------------------------
    def _stop_gear_anim(self) -> None:
        if self._gear_anim is not None:
            self._gear_anim.stop()
            self._gear_anim = None

    def _on_gear_press(self) -> None:
        if not self._item.isSettings:
            return
        self._stop_gear_anim()
        start = float(self._icon.get_angle())
        anim = QPropertyAnimation(self._icon, b"angle", self)
        anim.setDuration(GEAR_PRESS_MS)
        anim.setEasingCurve(QEasingCurve.Linear)
        anim.setStartValue(start)
        anim.setEndValue(start - 20.0)
        self._gear_anim = anim
        anim.start()

    def _on_gear_release(self) -> None:
        if not self._item.isSettings:
            return
        self._stop_gear_anim()
        start = float(self._icon.get_angle())
        target = 360.0 if start <= 0.0 else 360.0 * math.ceil(start / 360.0)
        anim = QPropertyAnimation(self._icon, b"angle", self)
        anim.setDuration(GEAR_SPIN_MS)
        # 对应 cubic-bezier(0, 0, 0, 1) 的强 ease-out。
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.setStartValue(start)
        anim.setEndValue(target)
        anim.finished.connect(self._normalize_gear_angle)
        self._gear_anim = anim
        anim.start()

    def _normalize_gear_angle(self) -> None:
        self._gear_anim = None
        self._icon.set_angle(self._icon.get_angle() % 360.0)

    # -- 主题 -------------------------------------------------------------
    def _theme(self) -> dict:
        nav = getattr(self._item, "_nav", None)
        return getattr(nav, "_theme", THEME_DEFAULTS)

    def _item_radius(self) -> int:
        key = ("flyoutItemRadius" if self._content_margin is not None
               else "navItemRadius")
        return int(self._theme()[key])

    # -- 状态 -------------------------------------------------------------
    def _background_color(self) -> QColor | None:
        theme = self._theme()
        if self._pressed:
            key = "selectedPressedBg" if self._selected else "pressedBg"
            return QColor(theme[key])
        if self._hover:
            key = "selectedHoverBg" if self._selected else "hoverBg"
            return QColor(theme[key])
        if self._selected:
            return QColor(theme["selectedBg"])
        return None

    def _text_color(self) -> QColor:
        theme = self._theme()
        return QColor(theme["pressedText"] if self._pressed else theme["textColor"])

    def _apply_visual_state(self) -> None:
        color = self._text_color()
        self._icon.set_icon_color(color)
        if self._arrow is not None:
            self._arrow.set_icon_color(color)

    # -- 尺寸 -------------------------------------------------------------
    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._layout_children()

    def _layout_children(self) -> None:
        width = self.width()
        center_y = self.height() // 2
        has_icon = bool(self._item.fonticon)
        margin = (ROW_ICON_INDENT if self._content_margin is None
                  else self._content_margin)
        indent = margin + (CHILD_INDENT if self._child else 0)
        if self._compact:
            if has_icon:
                icon_x = max(0, (width - ICON_SIZE) // 2)
                self._icon.setGeometry(icon_x, center_y - ICON_SIZE // 2,
                                       ICON_SIZE, ICON_SIZE)
                self._icon.show()
            else:
                self._icon.hide()
            self._arrow and self._arrow.hide()
        else:
            if width <= 0:
                return
            if has_icon:
                self._icon.setGeometry(indent, center_y - ICON_SIZE // 2,
                                       ICON_SIZE, ICON_SIZE)
                self._icon.show()
            else:
                self._icon.hide()
            if self._arrow is not None:
                arrow_x = max(0, width - 16 - ARROW_SIZE)
                self._arrow.setGeometry(arrow_x, center_y - ARROW_SIZE // 2,
                                        ARROW_SIZE, ARROW_SIZE)
                self._arrow.show()
        self._apply_visual_state()
        self.update()

    def _text_rect(self) -> QRectF:
        margin = (ROW_ICON_INDENT if self._content_margin is None
                  else self._content_margin)
        left = margin + (CHILD_INDENT if self._child else 0)
        if self._item.fonticon:
            left += ICON_SIZE + ICON_GAP
        right = self.width() - (16 if self._content_margin is None else margin)
        if self._fold:
            right -= ARROW_SIZE + 8
        return QRectF(left, 0, max(0, right - left), self.height())

    # -- 绘制 -------------------------------------------------------------
    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)

        bg = self._background_color()
        if bg is not None:
            radius = self._item_radius()
            painter.setPen(Qt.NoPen)
            painter.setBrush(bg)
            painter.drawRoundedRect(QRectF(self.rect()), radius, radius)

        if not self._compact:
            painter.setPen(self._text_color())
            painter.setFont(self._font)
            text_rect = self._text_rect()
            metrics = QFontMetrics(self._font)
            text = metrics.elidedText(self._item.name, Qt.ElideRight,
                                      max(1, int(text_rect.width())))
            painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, text)
        elif not self._item.fonticon and self._item.name:
            # 窄模式无 fonticon：显示名称首字（如“文档”→“文”）。
            painter.setPen(self._text_color())
            painter.setFont(self._font)
            painter.drawText(self.rect(), Qt.AlignCenter,
                             self._item.name.strip()[:1])
        painter.end()

    # -- 交互 -------------------------------------------------------------
    def enterEvent(self, event) -> None:
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover = False
        if not self._pressed:
            self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._pressed = True
            self._apply_visual_state()
            self.update()
            self.pressed.emit()
            event.accept()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() != Qt.LeftButton or not self._pressed:
            return
        inside = self.rect().contains(event.position().toPoint())
        self._pressed = False
        self._apply_visual_state()
        self.update()
        self.released.emit()
        if inside:
            self.clicked.emit()
        event.accept()


class _FoldRow(_NavRow):
    """折叠菜单标题行（与普通行同尺寸，额外显示箭头）。"""


class _FoldBody(QWidget):
    """折叠项的子项容器：maximumHeight 动画。"""

    heightChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        self._expanded = False
        self.setMaximumHeight(0)
        self.setVisible(False)
        self._anim = QPropertyAnimation(self, b"maximumHeight", self)
        self._anim.setDuration(ANIM_MS)
        self._anim.setEasingCurve(QEasingCurve.InOutCubic)
        self._anim.valueChanged.connect(lambda _value: self.heightChanged.emit())
        self._anim.finished.connect(self._on_anim_finished)

    def add_wrapper(self, wrapper: QWidget) -> None:
        self._layout.addWidget(wrapper)
        if self._expanded:
            self.setMaximumHeight(self._natural_height())
            self.heightChanged.emit()

    def remove_wrapper(self, wrapper: QWidget) -> None:
        self._layout.removeWidget(wrapper)

    def _natural_height(self) -> int:
        return max(0, self._layout.sizeHint().height())

    def set_expanded(self, expanded: bool, animate: bool = True) -> None:
        expanded = bool(expanded)
        if expanded == self._expanded:
            if expanded:
                self.setMaximumHeight(self._natural_height())
            return
        self._expanded = expanded
        self._anim.stop()
        if expanded:
            self.setVisible(True)
            natural = self._natural_height()
            if animate:
                self.setMaximumHeight(0)
                self._anim.setStartValue(0)
                self._anim.setEndValue(natural)
                self._anim.start()
            else:
                self.setMaximumHeight(_QWIDGETSIZE_MAX if natural >= 0 else 0)
        else:
            if animate and self.height() > 0:
                self._anim.setStartValue(self.height())
                self._anim.setEndValue(0)
                self._anim.start()
            else:
                self.setMaximumHeight(0)
                self.setVisible(False)

    def _on_anim_finished(self) -> None:
        if self._expanded:
            self.setMaximumHeight(_QWIDGETSIZE_MAX)
        else:
            self.setVisible(False)
            self.setMaximumHeight(0)
        self.heightChanged.emit()


class _FoldGroup(QWidget):
    """折叠标题 + 子项容器的组合控件。"""

    def __init__(self, fold: NavFoldItem, header: _FoldRow, parent=None):
        super().__init__(parent)
        self._fold = fold
        self._header = header
        self._body = _FoldBody(self)
        self._header_wrapper = _wrap_row(header)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        self._layout.addWidget(self._header_wrapper)
        self._layout.addWidget(self._body)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

    def header_wrapper(self) -> QWidget:
        return self._header_wrapper

    def body(self) -> _FoldBody:
        return self._body

    def add_child(self, row: _NavRow) -> None:
        self._body.add_wrapper(_wrap_row(row))

    def set_expanded(self, expanded: bool, animate: bool = True) -> None:
        self._header.set_expanded(expanded, animate=animate)
        self._body.set_expanded(expanded, animate=animate)


class _SeparatorWidget(QWidget):
    """加粗 #cccccc 的分隔描述符。"""

    heightChanged = Signal()

    def __init__(self, text: str, parent=None, navigation=None):
        super().__init__(parent)
        self._nav = navigation
        self._text = text or ""
        self._compact = False
        self._font = QFont(APP_FONT)
        self._font.setPixelSize(SEPARATOR_SIZE)
        self._font.setBold(True)
        metrics = QFontMetrics(self._font)
        self._natural = SEPARATOR_TOP + metrics.height() + SEPARATOR_BOTTOM
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMaximumHeight(self._natural)
        self._anim = QPropertyAnimation(self, b"maximumHeight", self)
        self._anim.setDuration(ANIM_MS)
        self._anim.setEasingCurve(QEasingCurve.InOutCubic)
        self._anim.valueChanged.connect(lambda _value: self.heightChanged.emit())
        self._anim.finished.connect(self._on_anim_finished)

    def set_text(self, text: str) -> None:
        self._text = text or ""
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(0, self._natural)

    def minimumSizeHint(self) -> QSize:
        return QSize(0, 0)

    def set_compact(self, compact: bool, animate: bool = True) -> None:
        compact = bool(compact)
        if compact == self._compact and self.isVisible() == (not compact):
            return
        self._compact = compact
        self._anim.stop()
        if compact:
            if animate and self.isVisible():
                self._anim.setStartValue(self.height())
                self._anim.setEndValue(0)
                self._anim.start()
            else:
                self.setMaximumHeight(0)
                self.setVisible(False)
        else:
            self.setVisible(True)
            if animate:
                self.setMaximumHeight(0)
                self._anim.setStartValue(0)
                self._anim.setEndValue(self._natural)
                self._anim.start()
            else:
                self.setMaximumHeight(self._natural)

    def _on_anim_finished(self) -> None:
        if self._compact:
            self.setVisible(False)
            self.setMaximumHeight(0)
        else:
            self.setMaximumHeight(self._natural)
        self.heightChanged.emit()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.TextAntialiasing, True)
        theme = getattr(self._nav, "_theme", THEME_DEFAULTS)
        painter.setPen(QColor(theme["separatorColor"]))
        painter.setFont(self._font)
        metrics = QFontMetrics(self._font)
        rect = QRectF(TOP_INDENT, SEPARATOR_TOP, self.width() - TOP_INDENT * 2,
                      metrics.height())
        painter.drawText(rect, Qt.AlignLeft | Qt.AlignVCenter,
                         metrics.elidedText(self._text, Qt.ElideRight,
                                            max(1, int(rect.width()))))
        painter.end()


class _SettingsDivider(QWidget):
    """1px 分割线：设置底栏上方与 ``addSeparateLine()`` 共用。"""

    def __init__(self, navigation=None, parent=None):
        super().__init__(parent)
        self._nav = navigation
        self.setFixedHeight(SETTINGS_DIVIDER_HEIGHT)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setAutoFillBackground(False)

    def paintEvent(self, event) -> None:
        theme = getattr(self._nav, "_theme", THEME_DEFAULTS)
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(theme["dividerColor"]))
        painter.end()


# ---------------------------------------------------------------------------
# 指示器
# ---------------------------------------------------------------------------


class _IndicatorOverlay(QWidget):
    """2×16 胶囊选中指示器，贴菜单行左边界，带两段 125ms 位移/拉伸动画。"""

    def __init__(self, pane, parent=None):
        super().__init__(parent or pane)
        self._pane = pane
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAutoFillBackground(False)
        self._row: QWidget | None = None
        self._anchor_row: QWidget | None = None
        self._top = 0.0
        self._bottom = 0.0
        self._edge = ""
        self._frozen_top = 0.0
        self._frozen_bottom = 0.0
        self._phase = 0
        self._new_row: QWidget | None = None
        self._above = True
        self._default_top = 0.0
        self._default_bottom = 0.0

        self._anim = QVariantAnimation(self)
        self._anim.setDuration(INDICATOR_STEP_MS)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(self._on_anim_value)
        self._anim.finished.connect(self._on_anim_finished)

        self._slide_anim = QVariantAnimation(self)
        self._slide_anim.setDuration(INDICATOR_STEP_MS)
        self._slide_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._slide_anim.valueChanged.connect(self._on_slide_value)
        self._slide_from_top = 0.0
        self._slide_from_bottom = 0.0
        self._slide_to_top = 0.0
        self._slide_to_bottom = 0.0
        self.hide()

    # -- 主题 -------------------------------------------------------------
    def _theme(self) -> dict:
        nav = getattr(self._pane, "_nav", None)
        return getattr(nav, "_theme", THEME_DEFAULTS)

    # -- 几何 -------------------------------------------------------------
    def _row_rect(self, row: QWidget) -> QRect:
        row_global = row.mapToGlobal(QPoint(0, 0))
        overlay_global = self.mapToGlobal(QPoint(0, 0))
        return QRect(row_global.x() - overlay_global.x(),
                     row_global.y() - overlay_global.y(),
                     row.width(), row.height())

    def _default_span(self, row: QWidget) -> tuple[float, float]:
        rect = self._row_rect(row)
        center = rect.center().y()
        height = float(self._theme()["indicatorHeight"])
        return center - height / 2.0, center + height / 2.0

    def _is_row_visible(self, row: QWidget) -> bool:
        if row is None or not row.isVisible():
            return False
        return self._pane.row_visible_for_indicator(row)

    # -- 对外接口 ---------------------------------------------------------
    def set_row(self, row: QWidget | None, animate: bool = True) -> None:
        self._anim.stop()
        self._anchor_row = row
        if row is None or not self._is_row_visible(row):
            self._row = None
            self.hide()
            return

        old_row = self._row
        if old_row is row:
            self._row = row
            self._top, self._bottom = self._default_span(row)
            self.show()
            self.raise_()
            self.update()
            return

        self.show()
        self.raise_()
        if old_row is None or not self._is_row_visible(old_row) or not animate:
            self._row = row
            self._top, self._bottom = self._default_span(row)
            self.update()
            return

        old_rect = self._row_rect(old_row)
        self._row = row
        self._new_row = row
        new_rect = self._row_rect(row)
        self._above = new_rect.center().y() < old_rect.center().y()
        self._default_top, self._default_bottom = self._default_span(row)
        self._frozen_top = self._top
        self._frozen_bottom = self._bottom
        self._phase = 0

        if self._above:
            self._edge = "top"
            self._start_edge(self._top, old_rect.top())
        else:
            self._edge = "bottom"
            self._start_edge(self._bottom, old_rect.bottom())

    def hide_indicator(self) -> None:
        self._anim.stop()
        self._slide_anim.stop()
        self._row = None
        self._anchor_row = None
        self.hide()

    def is_animating(self) -> bool:
        return (self._anim.state() == QAbstractAnimation.Running or
                self._slide_anim.state() == QAbstractAnimation.Running)

    def set_row_animated_from(self, row: QWidget | None, start_y: float) -> None:
        """把指示器从 start_y（本控件坐标）滑动到 row 的默认位置。"""
        self._anim.stop()
        self._slide_anim.stop()
        self._anchor_row = row
        if row is None or not self._is_row_visible(row):
            self._row = None
            self.hide()
            return
        self._row = row
        self._slide_to_top, self._slide_to_bottom = self._default_span(row)
        offset = float(start_y) - (self._slide_to_top + self._slide_to_bottom) / 2.0
        self._slide_from_top = self._slide_to_top + offset
        self._slide_from_bottom = self._slide_to_bottom + offset
        self._top = self._slide_from_top
        self._bottom = self._slide_from_bottom
        self.show()
        self.raise_()
        self.update()
        self._slide_anim.setStartValue(0.0)
        self._slide_anim.setEndValue(1.0)
        self._slide_anim.start()

    def _on_slide_value(self, value) -> None:
        value = float(value)
        self._top = self._slide_from_top + (self._slide_to_top - self._slide_from_top) * value
        self._bottom = self._slide_from_bottom + (
            self._slide_to_bottom - self._slide_from_bottom
        ) * value
        self.update()

    def refresh(self) -> None:
        anchor = self._anchor_row
        if anchor is None:
            self._row = None
            self.hide()
            return
        if self._anim.state() == QAbstractAnimation.Running:
            return
        if not self._is_row_visible(anchor):
            self._row = None
            self.hide()
            return
        self._row = anchor
        self._top, self._bottom = self._default_span(anchor)
        self.show()
        self.raise_()
        self.update()

    # -- 动画 -------------------------------------------------------------
    def _start_edge(self, start: float, end: float) -> None:
        self._anim.stop()
        self._anim.setStartValue(float(start))
        self._anim.setEndValue(float(end))
        self._anim.start()

    def _on_anim_value(self, value) -> None:
        value = float(value)
        if self._edge == "top":
            self._top = value
        else:
            self._bottom = value
        self.update()

    def _on_anim_finished(self) -> None:
        if self._phase == 0:
            self._phase = 1
            if self._above:
                self._top = self._default_top
                self._bottom = self._row_rect(self._new_row).bottom()
                self._edge = "bottom"
                self._start_edge(self._bottom, self._default_bottom)
            else:
                self._top = self._row_rect(self._new_row).top()
                self._bottom = self._default_bottom
                self._edge = "top"
                self._start_edge(self._top, self._default_top)
        else:
            self._phase = 2
            if self._row is not None:
                self._top, self._bottom = self._default_span(self._row)
            else:
                self._top = self._default_top
                self._bottom = self._default_bottom
            self.update()

    # -- 绘制 -------------------------------------------------------------
    def paintEvent(self, event) -> None:
        if self._row is None or self._bottom - self._top <= 0:
            return
        theme = self._theme()
        width = float(theme["indicatorWidth"])
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(theme["indicatorColor"]))
        painter.drawRoundedRect(
            QRectF(INDICATOR_INSET, self._top, width,
                   self._bottom - self._top),
            width / 2.0, width / 2.0,
        )
        painter.end()


# ---------------------------------------------------------------------------
# 内容区
# ---------------------------------------------------------------------------


class _LayoutHost(QWidget):
    """承载用户 QLayout 的容器，向滚动区透传 heightForWidth。"""

    def heightForWidth(self, width: int) -> int:
        layout = self.layout()
        if layout is not None and layout.hasHeightForWidth():
            return layout.heightForWidth(width)
        return super().heightForWidth(width)

    def sizeHint(self) -> QSize:
        layout = self.layout()
        if layout is not None and layout.hasHeightForWidth() and self.width() > 0:
            return QSize(max(1, layout.sizeHint().width()),
                         max(1, layout.heightForWidth(self.width())))
        return super().sizeHint()


class _ContentPage(QScrollArea):
    """一个菜单项对应的内容页（自带胶囊滚动条）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.NoFrame)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBar(_CapsuleScrollBar(self))
        self.setAutoFillBackground(False)
        self.viewport().setAutoFillBackground(False)
        self.viewport().setStyleSheet("background: transparent;")
        self._body = QWidget()
        self._body.setAutoFillBackground(False)
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(0, 0, 0, 0)
        self._body_layout.setSpacing(0)
        self.setWidget(self._body)
        self.setStyleSheet("QScrollArea { background: transparent; border: none; }")

    def body_layout(self) -> QVBoxLayout:
        return self._body_layout

    def add_host(self, host: QWidget) -> None:
        if host.parent() is not self._body:
            host.setParent(self._body)
        if self._body_layout.indexOf(host) < 0:
            self._body_layout.addWidget(host)

    def remove_host(self, host: QWidget) -> None:
        if self._body_layout.indexOf(host) >= 0:
            self._body_layout.removeWidget(host)


class _ContentHost(QWidget):
    """内容页容器：负责页面定位与 64px 上滑动画。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAutoFillBackground(False)
        self._pages: list[_ContentPage] = []
        self._current: _ContentPage | None = None
        self._anim = QPropertyAnimation(self, b"pos", self)

    def register_page(self, page: _ContentPage) -> None:
        if page not in self._pages:
            self._pages.append(page)
            page.setParent(self)
            page.hide()

    def pages(self) -> list[_ContentPage]:
        return list(self._pages)

    def remove_page(self, page: _ContentPage) -> None:
        if page in self._pages:
            self._pages.remove(page)
        if self._current is page:
            self._anim.stop()
            self._current = None
        page.hide()
        page.deleteLater()

    def current_page(self) -> _ContentPage | None:
        return self._current

    def show_page(self, page: _ContentPage | None, animate: bool = True) -> None:
        old = self._current
        if page is None:
            self._anim.stop()
            for candidate in self._pages:
                candidate.hide()
            self._current = None
            return
        if page is old:
            page.move(0, 0)
            page.show()
            page.raise_()
            return

        self.register_page(page)
        self._current = page
        for candidate in self._pages:
            if candidate is not page:
                candidate.hide()
        page.setGeometry(0, 0, self.width(), self.height())
        page.show()
        page.raise_()
        if animate:
            page.move(0, 64)
            self._anim.stop()
            self._anim.setTargetObject(page)
            self._anim.setPropertyName(b"pos")
            self._anim.setDuration(ANIM_MS)
            self._anim.setEasingCurve(QEasingCurve.OutCubic)
            self._anim.setStartValue(QPoint(0, 64))
            self._anim.setEndValue(QPoint(0, 0))
            self._anim.start()
        else:
            self._anim.stop()
            page.move(0, 0)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        for page in self._pages:
            page.setGeometry(0, 0, self.width(), self.height())
        if self._current is not None:
            self._current.move(0, 0)


class HighLightPanel(QWidget):
    """内容卡片：默认透明，让窗口背板的玻璃透出。

    经过 ``TitleBar.initNavigationView()`` 集成后，卡片会开启玻璃叠层和左上
    圆角：先在卡片区域绘制 ``BUBBLE_BACKGROUND_NORMAL`` 玻璃，再用圆角路径
    裁剪，因此左上圆角外侧透出的是窗口背景玻璃，层级更明显。``bg_color``
    仍可作为额外纯色叠层（QSS: ``qproperty-bg_color``）。
    """

    BG = QColor("#272727")
    RADIUS = 16
    PADDING = 36

    def __init__(self, parent=None, navigation=None):
        super().__init__(parent)
        self._nav = navigation
        self._bg_color = QColor(0, 0, 0, 0)
        self._radius = self.RADIUS
        self._corner_enabled = False
        self._glass_enabled = False
        self._glass_style = BUBBLE_BACKGROUND_NORMAL
        self.setAutoFillBackground(False)
        self._layout = QVBoxLayout(self)
        self._base_top = self.PADDING - 6
        self._layout.setContentsMargins(
            self.PADDING, self._base_top, self.PADDING, self.PADDING - 3
        )
        self._layout.setSpacing(0)
        self._content_host = _ContentHost(self)
        self._layout.addWidget(self._content_host, 1)

    def enable_titlebar_corner(self, color=None) -> None:
        """由 TitleBar 集成调用：启用玻璃叠层与左上圆角。"""
        changed = False
        if not self._glass_enabled:
            self._glass_enabled = True
            changed = True
        if not self._corner_enabled:
            self._corner_enabled = True
            changed = True
        if color is not None:
            color = color if isinstance(color, QColor) else QColor(color)
            if color != self._bg_color:
                self._bg_color = color
                changed = True
        if changed:
            self.update()

    def corner_enabled(self) -> bool:
        return self._corner_enabled

    def glass_enabled(self) -> bool:
        return self._glass_enabled

    def set_glass_style(self, style) -> None:
        if style is None or style is self._glass_style:
            return
        self._glass_style = style
        self.update()

    def set_top_clearance(self, clearance: int) -> None:
        """为 Hide 模式下浮在内容上的顶栏预留空间。"""
        top = self._base_top + max(0, int(clearance))
        margins = self._layout.contentsMargins()
        if margins.top() != top:
            self._layout.setContentsMargins(
                margins.left(), top, margins.right(), margins.bottom()
            )
            self._layout.activate()

    def content_host(self) -> _ContentHost:
        return self._content_host

    def get_bg_color(self) -> QColor:
        return self._bg_color

    def set_bg_color(self, color):
        color = QColor(color)
        if color != self._bg_color:
            self._bg_color = color
            self.update()

    bg_color = Property(QColor, get_bg_color, set_bg_color)

    def get_corner_radius(self) -> int:
        return self._radius

    def set_corner_radius(self, value):
        value = max(0, int(value))
        if value != self._radius:
            self._radius = value
            self.update()

    cornerRadius = Property(int, get_corner_radius, set_corner_radius)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        # 内缩 0.5 像素，让 1px 描边落在像素中心，避免发虚
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        radius = self._radius if self._corner_enabled else 0
        r = min(radius, rect.width() / 2, rect.height() / 2)

        path = QPainterPath()
        # 从左上圆角的“下端”开始，顺时针走一圈
        path.moveTo(rect.left(), rect.top() + r)
        path.lineTo(rect.left(), rect.bottom())    # 左下角：直角
        path.lineTo(rect.right(), rect.bottom())   # 右下角：直角
        path.lineTo(rect.right(), rect.top())      # 右上角：直角
        path.lineTo(rect.left() + r, rect.top())   # 走到左上圆角的起点

        # 左上角圆弧：外接矩形 (left, top, 2r, 2r)
        # Qt 角度以 3 点钟方向为 0°，逆时针为正
        # 90° = 顶部，扫 90° 到 180° = 左侧
        path.arcTo(rect.left(), rect.top(), 2 * r, 2 * r, 90, 90)
        path.closeSubpath()

        if self._glass_enabled:
            self._paint_glass(painter, rect, path)
        if self._bg_color.alpha() > 0:
            painter.fillPath(path, self._bg_color)

        painter.end()

    def _paint_glass(self, painter: QPainter, rect: QRectF,
                     path: QPainterPath) -> None:
        """在卡片区域叠加一层玻璃，并用左上圆角路径裁剪。"""
        style = self._glass_style
        backdrop = getattr(self._nav, "backdrop", None)
        painter.save()
        try:
            painter.setClipPath(path)
            if backdrop is not None and self.isVisible():
                if backdrop.energy.active:
                    painter.fillRect(rect, QColor(style.tint))
                else:
                    global_rect = QRect(self.mapToGlobal(QPoint(0, 0)),
                                        self.size())
                    backdrop.paint_material(painter, rect, global_rect, style)
            else:
                paint_frost_overlay(painter, rect, style, radius=0,
                                    border=False)
        finally:
            painter.restore()


# ---------------------------------------------------------------------------
# 侧边栏 / 根画布 / 顶栏
# ---------------------------------------------------------------------------


class _Pane(QWidget):
    """侧边栏玻璃面板：正常玻璃或 Flyout 玻璃。"""

    def __init__(self, navigation, parent=None):
        super().__init__(parent)
        self._nav = navigation
        self._flyout = False
        self._snapshot: QImage | None = None
        self._snapshot_origin = QPoint(0, 0)
        self._settings_wrapper: QWidget | None = None
        self._settings_row: _NavRow | None = None
        self._settings_divider: QWidget | None = None

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(ROW_MARGIN_X, 48 + ROW_MARGIN_TOP,
                                        ROW_MARGIN_X, 0)
        self._layout.setSpacing(0)

        self._scroll = QScrollArea(self)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        # 滚动条不占布局宽度：菜单行始终占满，滚动条作为覆盖层画在行上面。
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setAutoFillBackground(False)
        self._scroll.viewport().setAutoFillBackground(False)
        self._scroll.viewport().setStyleSheet("background: transparent;")
        self._scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        self._menu = QWidget()
        self._menu.setAutoFillBackground(False)
        self._menu_layout = QVBoxLayout(self._menu)
        self._menu_layout.setContentsMargins(0, 0, 0, 0)
        self._menu_layout.setSpacing(0)
        self._menu_layout.addStretch(1)
        self._scroll.setWidget(self._menu)
        self._layout.addWidget(self._scroll, 1)

        self._scrollbar_model = self._scroll.verticalScrollBar()
        self._scroll_overlay = _CapsuleScrollBar(self)
        self._scroll_overlay.setFocusPolicy(Qt.NoFocus)
        self._scroll_overlay.hide()
        self._scroll_syncing = False
        self._scrollbar_model.rangeChanged.connect(self._on_scroll_range_changed)
        self._scrollbar_model.valueChanged.connect(self._on_scroll_model_value)
        self._scroll_overlay.valueChanged.connect(self._on_scroll_overlay_value)

        self._indicator = _IndicatorOverlay(self, self)
        self._indicator.raise_()
        self._scrollbar_model.valueChanged.connect(self._indicator.refresh)

    # -- 菜单内容 ---------------------------------------------------------
    def add_menu_widget(self, widget: QWidget) -> None:
        index = max(0, self._menu_layout.count() - 1)
        self._menu_layout.insertWidget(index, widget)

    def remove_menu_widget(self, widget: QWidget) -> None:
        self._menu_layout.removeWidget(widget)

    def set_settings_widget(self, wrapper: QWidget, row: _NavRow) -> None:
        self._settings_wrapper = wrapper
        self._settings_row = row
        # 设置项固定在滚动区外：上方 1px 分割线，下方 6px 外边距。
        self._settings_divider = _SettingsDivider(self._nav, self)
        self._layout.addWidget(self._settings_divider)
        self._layout.addWidget(wrapper)
        margins = self._layout.contentsMargins()
        self._layout.setContentsMargins(
            margins.left(), margins.top(), margins.right(),
            SETTINGS_BOTTOM_MARGIN,
        )
        self._layout.activate()
        self._position_scroll_overlay()

    def settings_widget(self) -> QWidget | None:
        return self._settings_wrapper

    def set_header_height(self, height: int) -> None:
        margins = self._layout.contentsMargins()
        self._layout.setContentsMargins(margins.left(), height + ROW_MARGIN_TOP,
                                        margins.right(), margins.bottom())
        self._layout.activate()
        self._menu_layout.activate()
        self.updateGeometry()
        QTimer.singleShot(0, self._sync_scroll_overlay)

    # -- 覆盖式滚动条 -----------------------------------------------------
    def _sync_scroll_overlay(self) -> None:
        if not hasattr(self, "_scroll_overlay"):
            return
        model = self._scrollbar_model
        overlay = self._scroll_overlay
        self._scroll_syncing = True
        try:
            overlay.setRange(model.minimum(), model.maximum())
            overlay.setPageStep(model.pageStep())
            overlay.setSingleStep(model.singleStep())
            overlay.setValue(model.value())
        finally:
            self._scroll_syncing = False
        self._position_scroll_overlay()

    def _position_scroll_overlay(self) -> None:
        if not hasattr(self, "_scroll_overlay"):
            return
        top_left = self._scroll.mapTo(self, QPoint(0, 0))
        x = max(0, self.width() - ROW_MARGIN_X - SCROLLBAR_HIT)
        height = max(0, self._scroll.height())
        self._scroll_overlay.setGeometry(x, top_left.y(), SCROLLBAR_HIT, height)
        needed = self._scrollbar_model.maximum() > self._scrollbar_model.minimum()
        self._scroll_overlay.setVisible(bool(needed and self.isVisible()))
        if needed:
            self._scroll_overlay.raise_()

    def _on_scroll_range_changed(self, _minimum: int, _maximum: int) -> None:
        if self._scroll_syncing:
            return
        self._sync_scroll_overlay()

    def _on_scroll_model_value(self, value: int) -> None:
        if self._scroll_syncing:
            return
        self._scroll_syncing = True
        try:
            self._scroll_overlay.setValue(int(value))
        finally:
            self._scroll_syncing = False

    def _on_scroll_overlay_value(self, value: int) -> None:
        if self._scroll_syncing:
            return
        self._scrollbar_model.setValue(int(value))

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._sync_scroll_overlay()

    # -- 状态 -------------------------------------------------------------
    def set_flyout(self, flyout: bool) -> None:
        flyout = bool(flyout)
        if flyout == self._flyout:
            return
        self._flyout = flyout
        self.update()

    def set_snapshot(self, image: QImage | None, origin: QPoint) -> None:
        self._snapshot = image
        self._snapshot_origin = QPoint(origin)
        self.update()

    def shift_snapshot(self, dx: int, dy: int) -> None:
        if self._snapshot is not None:
            self._snapshot_origin += QPoint(int(dx), int(dy))
            self.update()

    def set_compact(self, compact: bool) -> None:
        if self._settings_row is not None:
            self._settings_row.set_compact(compact)

    def refresh_theme(self) -> None:
        self._indicator.refresh()
        self._indicator.update()
        if self._settings_divider is not None:
            self._settings_divider.update()
        if hasattr(self, "_scroll_overlay"):
            self._scroll_overlay.update()
        for widget in self._menu.findChildren(QWidget):
            if isinstance(widget, (_SeparatorWidget, _SettingsDivider)):
                widget.update()
        self.update()

    def menu_visible_rect(self) -> QRect:
        viewport = self._scroll.viewport()
        top_left = viewport.mapTo(self, QPoint(0, 0))
        return QRect(top_left, viewport.size())

    def row_visible_for_indicator(self, row: QWidget | None) -> bool:
        if row is None or not row.isVisible():
            return False
        if self._settings_wrapper is not None and (
                row is self._settings_wrapper or
                self._settings_wrapper.isAncestorOf(row)):
            return True
        visible_rect = self.menu_visible_rect()
        center_global = row.mapToGlobal(
            QPoint(row.width() // 2, row.height() // 2)
        )
        center = self.mapFromGlobal(center_global)
        return visible_rect.contains(center)

    def indicator(self) -> _IndicatorOverlay:
        return self._indicator

    # -- 绘制 -------------------------------------------------------------
    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        rect = QRectF(self.rect())

        if self._flyout:
            style = FLYOUT_GLASS
            path = rounded_path(rect, style.radius)
            painter.save()
            painter.setClipPath(path)
            base = QColor(style.tint)
            base.setAlpha(int(round(255 * style.opacity / 100.0)))
            painter.fillRect(rect, base)
            if self._snapshot is not None and not self._snapshot.isNull():
                dpr = float(self._snapshot.devicePixelRatio() or 1.0)
                our_global = self.mapToGlobal(QPoint(0, 0))
                offset = self._snapshot_origin - our_global
                target = QRectF(offset.x(), offset.y(),
                                self._snapshot.width() / dpr,
                                self._snapshot.height() / dpr)
                painter.drawImage(target, self._snapshot)
            painter.restore()
            paint_frost_overlay(painter, rect, style, radius=style.radius,
                                border=False, vignette=style.vignette)
        else:
            style = SIDEBAR_GLASS
            backdrop = self._nav.backdrop
            if backdrop is not None and self.isVisible():
                if backdrop.energy.active:
                    painter.fillRect(rect, QColor(style.tint))
                else:
                    global_rect = QRect(self.mapToGlobal(QPoint(0, 0)), self.size())
                    backdrop.paint_material(painter, rect, global_rect, style)
            else:
                paint_frost_overlay(painter, rect, style, radius=0, border=False)
        painter.end()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._indicator.setGeometry(self.rect())
        self._indicator.refresh()
        self._sync_scroll_overlay()


class _PaneShadow(QWidget):
    """侧边栏 Flyout 的柔和阴影层（预模糊，不压暗玻璃内部）。"""

    def __init__(self, parent=None, radius: int = CORNER_RADIUS):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAutoFillBackground(False)
        self._radius = int(radius)
        self._cache_key: tuple | None = None
        self._image: QImage | None = None

    def set_radius(self, radius: int) -> None:
        radius = max(0, int(radius))
        if radius != self._radius:
            self._radius = radius
            self._cache_key = None
            self.update()

    def _build_image(self) -> QImage | None:
        width, height = self.width(), self.height()
        if width <= 0 or height <= 0:
            return None
        dpr = float(self.devicePixelRatioF() or 1.0)
        key = (width, height, dpr, self._radius)
        if self._cache_key == key and self._image is not None:
            return self._image

        image = QImage(int(width * dpr), int(height * dpr),
                       QImage.Format.Format_RGBA8888)
        image.setDevicePixelRatio(dpr)
        image.fill(Qt.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(0, 0, 0, 165))
        inner = QRectF(self.rect()).adjusted(
            SHADOW_MARGIN, SHADOW_MARGIN, -SHADOW_MARGIN, -SHADOW_MARGIN
        )
        painter.drawRoundedRect(inner, self._radius, self._radius)
        painter.end()

        blurred = blur_qimage(image, 12.0 * dpr)
        blurred.setDevicePixelRatio(dpr)
        # 挖掉面板内部，玻璃只叠在外侧柔和阴影上。
        erase = QPainter(blurred)
        erase.setRenderHint(QPainter.Antialiasing, True)
        erase.setCompositionMode(QPainter.CompositionMode_Clear)
        erase.setPen(Qt.NoPen)
        erase.setBrush(Qt.black)
        erase.drawRoundedRect(inner, self._radius, self._radius)
        erase.end()

        self._cache_key = key
        self._image = blurred
        return blurred

    def paintEvent(self, event) -> None:
        image = self._build_image()
        if image is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.drawImage(0, 0, image)
        painter.end()


class _HeaderBar(QWidget):
    """汉堡 / 返回按钮容器：始终竖排，返回在上、汉堡在下。"""

    def __init__(self, buttons: list[AnimatedIconButton], parent=None):
        super().__init__(parent)
        self._buttons: list[AnimatedIconButton] = []
        self._vertical = True
        self._initialized = True
        self.setAutoFillBackground(False)
        self.attach_buttons(buttons)

    def buttons(self) -> list[AnimatedIconButton]:
        return list(self._buttons)

    def is_empty(self) -> bool:
        return not self.visible_buttons()

    def visible_buttons(self) -> list[AnimatedIconButton]:
        return [button for button in self._buttons if not button.isHidden()]

    def set_vertical(self, vertical: bool = True) -> None:
        self._vertical = True
        self.refresh_layout()

    def attach_buttons(self, buttons: list[AnimatedIconButton]) -> None:
        self._buttons = list(buttons)
        for button in self._buttons:
            button.setParent(self)
            button.set_button_size(*HEADER_BUTTON_SIZE)
            button.show()
        self.refresh_layout()

    def detach_buttons(self) -> list[AnimatedIconButton]:
        buttons = list(self._buttons)
        self._buttons = []
        self.setFixedSize(0, 0)
        self.hide()
        return buttons

    def refresh_layout(self) -> None:
        visible = self.visible_buttons()
        if not visible:
            self.setFixedSize(0, 0)
            self.hide()
            return
        width, height = HEADER_BUTTON_SIZE
        for index, button in enumerate(visible):
            button.set_button_size(width, height)
            button.move(HEADER_MARGIN,
                        HEADER_MARGIN + index * (height + HEADER_MARGIN))
        self.setFixedSize(HEADER_MARGIN * 2 + width,
                          HEADER_MARGIN * 2 + len(visible) * height +
                          (len(visible) - 1) * HEADER_MARGIN)
        self.show()

    def recommended_size(self) -> QSize:
        return self.size()


class _RootCanvas(QWidget):
    """窗口根画布：内容卡片、侧边栏、阴影、顶栏全部手动定位。"""

    def __init__(self, navigation, parent=None):
        super().__init__(parent)
        self._nav = navigation
        self.setAutoFillBackground(False)
        self._content_card = HighLightPanel(self, navigation)
        self._shadow = _PaneShadow(self)
        self._pane = _Pane(navigation, self)
        self._header: _HeaderBar | None = None

        self._pane_w = float(EXPANDED_WIDTH)
        self._pane_x = 0.0
        self._pane_y = 0.0
        self._pane_h = 0.0
        self._content_x = float(EXPANDED_WIDTH)
        self._flyout_mode = False
        self._base_width = COMPACT_WIDTH

        self._anim_group: QParallelAnimationGroup | None = None
        self._finish_callback: Callable[[], None] | None = None

        self._shadow.hide()
        self._layout_children()

    # -- 属性动画 ---------------------------------------------------------
    def get_pane_width(self) -> float:
        return self._pane_w

    def set_pane_width(self, value):
        self._pane_w = float(value)
        self._layout_children()

    paneWidth = Property(float, get_pane_width, set_pane_width)

    def get_pane_x(self) -> float:
        return self._pane_x

    def set_pane_x(self, value):
        self._pane_x = float(value)
        self._layout_children()

    paneX = Property(float, get_pane_x, set_pane_x)

    def get_pane_y(self) -> float:
        return self._pane_y

    def set_pane_y(self, value):
        self._pane_y = float(value)
        self._layout_children()

    paneY = Property(float, get_pane_y, set_pane_y)

    def get_pane_height(self) -> float:
        return self._pane_h

    def set_pane_height(self, value):
        self._pane_h = float(value)
        self._layout_children()

    paneHeight = Property(float, get_pane_height, set_pane_height)

    def get_content_x(self) -> float:
        return self._content_x

    def set_content_x(self, value):
        self._content_x = float(value)
        self._layout_children()

    contentX = Property(float, get_content_x, set_content_x)

    # -- 对外 -------------------------------------------------------------
    def content_card(self) -> HighLightPanel:
        return self._content_card

    def pane(self) -> _Pane:
        return self._pane

    def shadow(self) -> _PaneShadow:
        return self._shadow

    def attach_header(self, header: _HeaderBar) -> None:
        self._header = header
        header.setParent(self)
        self._layout_children()

    def set_base_width(self, width: int) -> None:
        self._base_width = int(width)

    def base_width(self) -> int:
        return self._base_width

    def set_flyout_mode(self, flyout: bool) -> None:
        self._flyout_mode = bool(flyout)
        if self._flyout_mode:
            self._shadow.show()
            self._shadow.raise_()
            self._pane.raise_()
        else:
            self._shadow.hide()

    def animate_to(self, *, pane_width: float, pane_x: float, pane_y: float,
                   pane_height: float, content_x: float, duration: int,
                   flyout: bool, on_finished: Callable[[], None] | None = None) -> None:
        self.stop_animation()
        self.set_flyout_mode(flyout)
        targets = [
            ("paneWidth", self._pane_w, float(pane_width)),
            ("paneX", self._pane_x, float(pane_x)),
            ("paneY", self._pane_y, float(pane_y)),
            ("paneHeight", self._pane_h, float(pane_height)),
            ("contentX", self._content_x, float(content_x)),
        ]
        animations = []
        for name, start, end in targets:
            if abs(start - end) < 0.5:
                continue
            anim = QPropertyAnimation(self, name.encode("ascii"), self)
            anim.setDuration(max(0, int(duration)))
            anim.setEasingCurve(QEasingCurve.OutCubic)
            anim.setStartValue(start)
            anim.setEndValue(end)
            animations.append(anim)

        self._finish_callback = on_finished
        if not animations or duration <= 0:
            self._pane_w = float(pane_width)
            self._pane_x = float(pane_x)
            self._pane_y = float(pane_y)
            self._pane_h = float(pane_height)
            self._content_x = float(content_x)
            self._layout_children()
            self._run_finish_callback()
            return

        group = QParallelAnimationGroup(self)
        for anim in animations:
            group.addAnimation(anim)
        group.finished.connect(self._on_animation_finished)
        self._anim_group = group
        group.start()

    def stop_animation(self) -> None:
        if self._anim_group is not None:
            self._anim_group.stop()
            self._anim_group.deleteLater()
            self._anim_group = None
        self._finish_callback = None

    def _on_animation_finished(self) -> None:
        self._anim_group = None
        self._layout_children()
        self._run_finish_callback()

    def _run_finish_callback(self) -> None:
        callback, self._finish_callback = self._finish_callback, None
        if callback is not None:
            callback()

    # -- 布局 -------------------------------------------------------------
    def refresh_geometry(self) -> None:
        if self._pane_h <= 0:
            self._pane_h = float(self.height())
        self._layout_children()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._anim_group is None:
            self._pane_h = float(self.height())
            if self._flyout_mode:
                self._pane_y = 4.0
                self._pane_h = float(self.height() - 8)
            self._layout_children()

    def _layout_children(self) -> None:
        width = self.width()
        height = self.height()
        if height <= 0:
            return

        pane_w = max(0.0, min(self._pane_w, float(width)))
        pane_h = self._pane_h if self._pane_h > 0 else float(height)
        pane_h = max(0.0, min(pane_h, float(height)))
        self._pane.setGeometry(round(self._pane_x), round(self._pane_y),
                               round(pane_w), round(pane_h))
        if pane_w < 1:
            self._pane.hide()
        else:
            self._pane.show()

        content_x = max(0.0, min(self._content_x, float(width)))
        self._content_card.setGeometry(round(content_x), 0,
                                       max(0, width - round(content_x)), height)

        if self._flyout_mode:
            self._shadow.setGeometry(
                round(self._pane_x) - SHADOW_MARGIN,
                round(self._pane_y) - SHADOW_MARGIN,
                round(pane_w) + SHADOW_MARGIN * 2,
                round(pane_h) + SHADOW_MARGIN * 2,
            )
            self._shadow.show()
            self._shadow.raise_()
        else:
            self._shadow.hide()

        if self._header is not None:
            self._header.move(HEADER_MARGIN, HEADER_MARGIN)
            self._header.raise_()

        self._content_card.lower()
        if self._flyout_mode:
            self._shadow.raise_()
        self._pane.raise_()
        if self._header is not None:
            self._header.raise_()


# ---------------------------------------------------------------------------
# 窄模式子菜单 Flyout
# ---------------------------------------------------------------------------


class _FlyoutSurface(QWidget):
    """Flyout 玻璃表面 + 子菜单行 + 指示器。"""

    def __init__(self, navigation, parent=None):
        super().__init__(parent)
        self._nav = navigation
        self._snapshot: QImage | None = None
        self._snapshot_origin = QPoint(0, 0)
        self.setAutoFillBackground(False)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(
            FLYOUT_PADDING_X, FLYOUT_PADDING_Y,
            FLYOUT_PADDING_X, FLYOUT_PADDING_Y,
        )
        self._layout.setSpacing(FLYOUT_ITEM_GAP)
        self._layout.addStretch(1)
        self._rows: list[_NavRow] = []
        self._indicator = _IndicatorOverlay(self, self)
        self._indicator.raise_()

    def add_row(self, row: _NavRow) -> None:
        self._rows.append(row)
        row.setParent(self)
        row.setFixedHeight(FLYOUT_ROW_HEIGHT)
        self._layout.insertWidget(max(0, self._layout.count() - 1), row)

    def refresh_theme(self) -> None:
        self._indicator.refresh()
        self._indicator.update()
        for row in self._rows:
            row.refresh_content()
        self.update()

    def set_snapshot(self, image: QImage | None, origin: QPoint) -> None:
        self._snapshot = image
        self._snapshot_origin = QPoint(origin)
        self.update()

    def shift_snapshot(self, dx: int, dy: int) -> None:
        """主窗口移动时同步玻璃快照的全局原点。"""
        if self._snapshot is not None:
            self._snapshot_origin += QPoint(int(dx), int(dy))
            self.update()

    def menu_visible_rect(self) -> QRect:
        return self.rect()

    def row_visible_for_indicator(self, row: QWidget | None) -> bool:
        if row is None or not row.isVisible():
            return False
        center_global = row.mapToGlobal(
            QPoint(row.width() // 2, row.height() // 2)
        )
        return self.rect().contains(self.mapFromGlobal(center_global))

    def indicator(self) -> _IndicatorOverlay:
        return self._indicator

    def sizeHint(self) -> QSize:
        hint = self._layout.sizeHint()
        return QSize(FLYOUT_WIDTH, max(1, hint.height()))

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        rect = QRectF(self.rect())
        style = FLYOUT_FOLD_GLASS
        radius = float(self._nav._theme["flyoutRadius"])
        path = rounded_path(rect, radius)
        painter.save()
        painter.setClipPath(path)
        base = QColor(style.tint)
        base.setAlpha(int(round(255 * style.opacity / 100.0)))
        painter.fillRect(rect, base)

        # Flyout 可能伸出主窗口：先用桌面/壁纸玻璃铺底，
        # 窗口内的部分再由主窗口快照覆盖，避免左侧出现纯色条。
        backdrop = SIDEBAR_GLASS
        our_global = self.mapToGlobal(QPoint(0, 0))
        if backdrop is not None:
            global_rect = QRect(our_global, self.size())
            try:
                image, target = backdrop.source.processed_region(
                    global_rect, style.blur, style.brightness, style.saturation
                )
            except Exception:
                image, target = None, QRectF()
            if image is not None and not image.isNull():
                target = target.translated(-our_global.x(), -our_global.y())
                painter.drawImage(target, image)

        if self._snapshot is not None and not self._snapshot.isNull():
            dpr = float(self._snapshot.devicePixelRatio() or 1.0)
            offset = self._snapshot_origin - our_global
            target = QRectF(offset.x(), offset.y(),
                            self._snapshot.width() / dpr,
                            self._snapshot.height() / dpr)
            painter.drawImage(target, self._snapshot)
        painter.restore()
        paint_frost_overlay(painter, rect, style, radius=radius,
                            border=True, vignette=style.vignette)
        painter.end()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._indicator.setGeometry(self.rect())
        self._indicator.refresh()


class _SubmenuFlyout(QWidget):
    """窄模式下的子菜单浮窗：渐显 + 右移；失焦/点击外部关闭。"""

    def __init__(self, navigation, fold: NavFoldItem):
        super().__init__(None)
        self._nav = navigation
        self._fold = fold
        self.setWindowFlags(
            Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint |
            Qt.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)

        self._shadow = _PaneShadow(
            self, radius=int(navigation._theme["flyoutRadius"])
        )
        self._surface = _FlyoutSurface(navigation, self)
        self._surface.raise_()
        self._row_by_child: dict[NavItem, _NavRow] = {}
        for child in fold.children():
            # 子菜单不叠加 CHILD_INDENT，按顶层菜单的 12px 内容边距排版。
            row = _NavRow(child, compact=False, child=False,
                          content_margin=FLYOUT_CONTENT_MARGIN,
                          parent=self._surface)
            row.pressed.connect(child.pressed.emit)
            row.released.connect(child.released.emit)
            row.clicked.connect(
                lambda child=child: self._on_child_clicked(child)
            )
            self._surface.add_row(row)
            self._row_by_child[child] = row

        self._anim_pos: QPropertyAnimation | None = None
        self._anim_opacity: QPropertyAnimation | None = None
        self._closing = False

    def surface(self) -> _FlyoutSurface:
        return self._surface

    def refresh_theme(self) -> None:
        self._shadow.set_radius(int(self._nav._theme["flyoutRadius"]))
        self._surface.refresh_theme()

    def fold(self) -> NavFoldItem:
        return self._fold

    def row_for(self, child: NavItem) -> _NavRow | None:
        return self._row_by_child.get(child)

    def _on_child_clicked(self, child: NavItem) -> None:
        child.clicked.emit()
        self._nav._activate_child(child, from_submenu=True)

    # -- 展示 -------------------------------------------------------------
    def _final_geometry(self) -> QRect:
        surface_hint = self._surface.sizeHint()
        panel_w = FLYOUT_WIDTH
        panel_h = max(FLYOUT_ROW_HEIGHT + FLYOUT_PADDING_Y * 2,
                      surface_hint.height())
        window_w = panel_w + SHADOW_MARGIN * 2
        window_h = panel_h + SHADOW_MARGIN * 2

        main_global = self._nav.mapToGlobal(QPoint(0, 0))
        # 玻璃面板左边界 = 主窗口左边界 + 50px（外层窗口还要再让出阴影边距）。
        target_x = main_global.x() + FLYOUT_OFFSET_X - SHADOW_MARGIN

        # 第一个列表项的中线与展开项的中线对齐；空间不足时也不自动挪位置。
        first_center = FLYOUT_PADDING_Y + FLYOUT_ROW_HEIGHT / 2.0
        row = self._fold._row
        if row is not None:
            row_center = row.mapToGlobal(QPoint(0, row.height() // 2)).y()
            surface_top = row_center - first_center
            target_y = round(surface_top) - SHADOW_MARGIN
        else:
            target_y = main_global.y() + 8 - SHADOW_MARGIN

        return QRect(target_x, target_y, window_w, window_h)

    def _layout_children(self) -> None:
        self._shadow.setGeometry(self.rect())
        self._surface.setGeometry(SHADOW_MARGIN, SHADOW_MARGIN,
                                  self.width() - SHADOW_MARGIN * 2,
                                  self.height() - SHADOW_MARGIN * 2)
        self._shadow.lower()
        self._surface.raise_()

    def show_flyout(self) -> None:
        for anim in (self._anim_pos, self._anim_opacity):
            if anim is not None:
                anim.stop()
        snapshot = self._nav._grab_window_snapshot(FLYOUT_FOLD_GLASS)
        if snapshot is not None:
            self._surface.set_snapshot(snapshot[0], snapshot[1])
        final = self._final_geometry()
        self.setGeometry(final)
        self._layout_children()
        self.setWindowOpacity(0.0)
        self.move(final.x() - FLYOUT_OFFSET_X, final.y())
        self.show()
        self.raise_()

        self._closing = False
        self._anim_pos = QPropertyAnimation(self, b"pos", self)
        self._anim_pos.setDuration(ANIM_MS)
        self._anim_pos.setEasingCurve(QEasingCurve.OutCubic)
        self._anim_pos.setStartValue(QPoint(final.x() - FLYOUT_OFFSET_X, final.y()))
        self._anim_pos.setEndValue(final.topLeft())
        self._anim_pos.start()

        self._anim_opacity = QPropertyAnimation(self, b"windowOpacity", self)
        self._anim_opacity.setDuration(ANIM_MS)
        self._anim_opacity.setStartValue(0.0)
        self._anim_opacity.setEndValue(1.0)
        self._anim_opacity.start()

        self._setup_indicator()

    def _setup_indicator(self) -> None:
        self._surface.indicator().hide_indicator()
        if self._fold.layout is not None:
            return
        child = self._nav._selected_child
        if child is None or child._fold is not self._fold:
            return
        row = self._row_by_child.get(child)
        if row is None:
            return
        self._surface.indicator().set_row_animated_from(row, self._fold_row_y())

    def _fold_row_y(self) -> float:
        row = self._fold._row
        if row is None:
            return 0.0
        top_left = row.mapToGlobal(QPoint(0, 0))
        surface_top = self._surface.mapToGlobal(QPoint(0, 0))
        return float(top_left.y() - surface_top.y() + row.height() // 2)

    def close_flyout(self, animate: bool = True) -> None:
        if not self.isVisible() or self._closing:
            return
        self._closing = True
        for anim in (self._anim_pos, self._anim_opacity):
            if anim is not None:
                anim.stop()
        if not animate:
            self.hide()
            self._nav._on_submenu_closed(self)
            return
        start = self.geometry()
        self._anim_pos = QPropertyAnimation(self, b"pos", self)
        self._anim_pos.setDuration(INDICATOR_STEP_MS)
        self._anim_pos.setEasingCurve(QEasingCurve.InCubic)
        self._anim_pos.setStartValue(start.topLeft())
        self._anim_pos.setEndValue(QPoint(start.x() - FLYOUT_OFFSET_X, start.y()))
        self._anim_pos.start()

        self._anim_opacity = QPropertyAnimation(self, b"windowOpacity", self)
        self._anim_opacity.setDuration(INDICATOR_STEP_MS)
        self._anim_opacity.setStartValue(self.windowOpacity())
        self._anim_opacity.setEndValue(0.0)
        self._anim_opacity.finished.connect(self._finish_close)
        self._anim_opacity.start()

    def _finish_close(self) -> None:
        self.hide()
        self._nav._on_submenu_closed(self)

    def contains_widget(self, widget: QWidget | None) -> bool:
        if widget is None:
            return False
        return widget is self or self.isAncestorOf(widget)

    def move_with_window(self, dx: int, dy: int) -> None:
        """主窗口拖动时，Flyout 保持相对位置一起移动。"""
        if not self.isVisible() or self._closing or (not dx and not dy):
            return
        if (self._anim_pos is not None and
                self._anim_pos.state() == QAbstractAnimation.Running):
            self._anim_pos.stop()
            self._anim_pos = None
        self.move(self.pos() + QPoint(int(dx), int(dy)))
        self._surface.shift_snapshot(dx, dy)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._layout_children()


# ---------------------------------------------------------------------------
# NavigationView
# ---------------------------------------------------------------------------


class NavigationView(GlassWindowBase):
    """统一托管整个窗口的导航视图。

    ``show_pane`` 控制汉堡按钮（需求中 pane 指代汉堡按钮，而不是侧栏显隐）；
    ``show_back`` 控制返回按钮；``show_settings`` 控制内置设置项。

    示例::

        class DemoWindow(NavigationView):
            def __init__(self):
                super().__init__()
                self.addNavItem("\\uE80F", "主页", layout)
                self.setSelectedNavItem(0)
    """

    selectedChanged = Signal(int)
    paneStateChanged = Signal(bool, object, object, bool)
    backVisibilityChanged = Signal(bool)

    # -- QSS 可覆盖的主题（默认值见 THEME_DEFAULTS） ---------------------
    selectedBg = _theme_qcolor("selectedBg")
    selectedHoverBg = _theme_qcolor("selectedHoverBg")
    selectedPressedBg = _theme_qcolor("selectedPressedBg")
    hoverBg = _theme_qcolor("hoverBg")
    pressedBg = _theme_qcolor("pressedBg")
    textColor = _theme_qcolor("textColor")
    pressedText = _theme_qcolor("pressedText")
    separatorColor = _theme_qcolor("separatorColor")
    dividerColor = _theme_qcolor("dividerColor")
    indicatorColor = _theme_qcolor("indicatorColor")
    indicatorWidth = _theme_int("indicatorWidth")
    indicatorHeight = _theme_int("indicatorHeight")
    navItemRadius = _theme_int("navItemRadius")
    flyoutRadius = _theme_int("flyoutRadius")
    flyoutItemRadius = _theme_int("flyoutItemRadius")

    def __init__(self, show_pane: bool = True, show_back: bool = True,
                 show_settings: bool = True, hide_threshold: int = 700,
                 compact_threshold: int = 1000, MinWidth: int = 0,
                 MaxWidth: int = 0, MinHeight: int = 0, MaxHeight: int = 0):
        super().__init__()
        # 内容区使用 glasskit 自带的全窗口玻璃；侧边栏/飞窗各自覆盖。
        self.setBrush(BUBBLE_BACKGROUND_NORMAL)
        self.setWindowTitle("NavigationView")
        self._theme = dict(THEME_DEFAULTS)
        self._ready = False

        self._show_pane = bool(show_pane)
        self._show_back = bool(show_back)
        self._show_settings = bool(show_settings)
        self._hide_threshold = max(0, int(hide_threshold))
        self._compact_threshold = max(0, int(compact_threshold))
        if self._compact_threshold < self._hide_threshold:
            warnings.warn("compact_threshold < hide_threshold, will deal with hide_threshold.",
                          RuntimeWarning, stacklevel=2)
            self._compact_threshold = self._hide_threshold

        # -- 模型与状态 ---------------------------------------------------
        self._menu_entries: list = []
        self._nav_items: list[NavItem] = []
        self._fold_items: list[NavFoldItem] = []
        self._selected_top = None
        self._selected_child = None
        self._settings_selected = False
        self._last_selected_index = -1
        self._last_selected_key = None
        self._history: list[dict] = []
        self._history_limit = HISTORY_LIMIT
        self._remembered_folds: set[NavFoldItem] = set()

        self._pane_state = PaneStateEnum.Auto
        self._show_inline = PaneShowInlineEnum.Auto
        self._effective_state: PaneStateEnum | None = None
        self._presentation_flyout = False
        self._last_base: PaneStateEnum | None = None
        self._last_state_tuple: tuple | None = None
        self._was_visually_expanded: bool | None = None
        self._pane_open_inline = True
        self._pane_flyout_open = False
        self._auto_hide_back = False
        self._titlebar = None
        self._buttons_external = False

        self._submenu: _SubmenuFlyout | None = None
        self._app_filter_installed = False
        self._content_revision = 0
        self._last_clearance = 0
        self._pane_snapshot_cache: tuple | None = None
        self._window_snapshot_cache: tuple | None = None
        self._last_window_pos = QPoint(0, 0)
        self._glass_watch_window: QWidget | None = None
        self._glass_last_window_pos = QPoint(0, 0)
        self._pane_snapshot_timer = QTimer(self)
        self._pane_snapshot_timer.setSingleShot(True)
        self._pane_snapshot_timer.setInterval(ANIM_MS + 30)
        self._pane_snapshot_timer.timeout.connect(
            self._capture_pane_snapshot_if_needed
        )

        self._layout_owner: dict[int, object] = {}
        self._layout_registry: dict[int, tuple[object, QWidget]] = {}
        self._layout_pool = QWidget(self)
        self._layout_pool.hide()

        # -- 界面 ---------------------------------------------------------
        self._root = _RootCanvas(self)
        self.content_layout.addWidget(self._root)
        self._content_card = self._root.content_card()
        self._content_host = self._content_card.content_host()
        self._pane = self._root.pane()

        buttons: list[AnimatedIconButton] = []
        self._hamburger: AnimatedIconButton | None = None
        self._back: AnimatedIconButton | None = None
        if self._show_back:
            self._back = AnimatedIconButton("back", parent=self._root)
            self._back.clicked.connect(self._go_back)
            self._back.setEnabled(False)
            self._back.set_hover_text("返回")
            buttons.append(self._back)
        if self._show_pane:
            self._hamburger = AnimatedIconButton("hamburger", parent=self._root)
            self._hamburger.clicked.connect(self._toggle_pane)
            self._hamburger.set_hover_text("展开菜单")
            buttons.append(self._hamburger)
        self._header = _HeaderBar(buttons, self._root)
        self._root.attach_header(self._header)
        if not buttons:
            self._header.hide()

        self._settings_item: NavItem | None = None
        self._settings_row: _NavRow | None = None
        if self._show_settings:
            self._settings_item = NavItem(self, SETTINGS_GLYPH, "设置",
                                          layout=None, settings=True)
            self._settings_item.clicked.connect(self._activate_settings)
            self._settings_row = self._create_row(self._settings_item, child=False)
            wrapper = _wrap_row(self._settings_row, SETTINGS_TOP_MARGIN)
            self._pane.set_settings_widget(wrapper, self._settings_row)

        self._apply_size_limits(MinWidth, MaxWidth, MinHeight, MaxHeight)
        self._sync_app_filter()

        self.resize(1180, 760)
        self._ready = True
        self._reset_open_flags()
        self._apply_pane_state(manual=False, animate=False, force=True)
        self._update_back_enabled()

    # ------------------------------------------------------------------
    # 构造辅助
    # ------------------------------------------------------------------
    def _apply_size_limits(self, min_w: int, max_w: int,
                           min_h: int, max_h: int) -> None:
        min_w = max(0, int(min_w))
        max_w = max(0, int(max_w))
        min_h = max(0, int(min_h))
        max_h = max(0, int(max_h))
        if max_w > 0 and min_w > max_w:
            warnings.warn("MinWidth > MaxWidth, already clamped.", RuntimeWarning, stacklevel=2)
            min_w = max_w
        if max_h > 0 and min_h > max_h:
            warnings.warn("MinHeight > MaxHeight, already clamped.", RuntimeWarning, stacklevel=2)
            min_h = max_h
        self.setMinimumWidth(min_w)
        self.setMaximumWidth(max_w if max_w > 0 else _QWIDGETSIZE_MAX)
        self.setMinimumHeight(min_h)
        self.setMaximumHeight(max_h if max_h > 0 else _QWIDGETSIZE_MAX)

    def _refresh_theme(self) -> None:
        """QSS 主题变化后刷新所有自绘控件。"""
        if not hasattr(self, "_theme"):
            return
        for item in getattr(self, "_nav_items", ()):
            if getattr(item, "isValid", lambda: False)() and item._row is not None:
                item._row.refresh_content()
        for fold in getattr(self, "_fold_items", ()):
            if not getattr(fold, "isValid", lambda: False)():
                continue
            if fold._row is not None:
                fold._row.refresh_content()
            for child in fold._children:
                if child.isValid() and child._row is not None:
                    child._row.refresh_content()
        if getattr(self, "_settings_row", None) is not None:
            self._settings_row.refresh_content()
        pane = getattr(self, "_pane", None)
        if pane is not None:
            pane.refresh_theme()
        card = getattr(self, "_content_card", None)
        if card is not None:
            card.update()
        submenu = getattr(self, "_submenu", None)
        if submenu is not None:
            submenu.refresh_theme()

    def _create_row(self, item, child: bool = False) -> _NavRow:
        row: _NavRow
        if isinstance(item, NavFoldItem):
            row = _FoldRow(item, compact=not self._visually_expanded(), child=child)
        else:
            row = _NavRow(item, compact=not self._visually_expanded(), child=child)
        row.pressed.connect(item.pressed.emit)
        row.released.connect(item.released.emit)
        row.clicked.connect(item.clicked.emit)
        item._row = row
        return row

    def _build_top_item(self, item) -> None:
        if isinstance(item, NavFoldItem):
            row = self._create_row(item)
            group = _FoldGroup(item, row)
            item._group = group
            group.body().heightChanged.connect(self._on_layout_shifted)
            item.clicked.connect(lambda item=item: self._activate_fold(item))
            self._pane.add_menu_widget(group)
        else:
            row = self._create_row(item)
            wrapper = _wrap_row(row)
            item._wrapper = wrapper
            item.clicked.connect(lambda item=item: self._activate_nav_item(item))
            self._pane.add_menu_widget(wrapper)
        item._row.set_compact(not self._visually_expanded())

    # ------------------------------------------------------------------
    # 公共 API：添加 / 修改 / 删除
    # ------------------------------------------------------------------
    def addNavItem(self, fonticon: str, name: str, layout=None) -> NavItem:
        """添加普通菜单项；返回 NavItem。"""
        item = NavItem(self, fonticon, name, layout=None)
        self._nav_items.append(item)
        self._menu_entries.append(item)
        self._build_top_item(item)
        self._set_item_layout(item, layout)
        self._refresh_indices()
        return item

    def addNavFoldItem(self, fonticon: str, name: str, layout=None) -> NavFoldItem:
        """添加折叠菜单项；layout 可选，有 layout 时点击标题会同时展开并切换内容。"""
        fold = NavFoldItem(self, fonticon, name, layout=None)
        self._fold_items.append(fold)
        self._menu_entries.append(fold)
        self._build_top_item(fold)
        self._set_item_layout(fold, layout)
        self._refresh_indices()
        return fold

    def _add_child(self, fold: NavFoldItem, fonticon: str, name: str,
                   layout) -> NavItem:
        if not fold.isValid():
            raise RuntimeError("This NavFoldItem is already removed.")
        if fold._group is None:
            raise RuntimeError("NavFoldItem has not finished building.")
        child = NavItem(self, fonticon, name, layout=None, fold=fold)
        fold._children.append(child)
        row = self._create_row(child, child=True)
        child.clicked.connect(lambda child=child: self._activate_child(child))
        fold._group.add_child(row)
        self._set_item_layout(child, layout)
        self._refresh_indices()
        return child

    def addSeparator(self, text: str):
        entry = _SeparatorEntry(text)
        widget = _SeparatorWidget(text, navigation=self)
        entry.widget = widget
        widget.heightChanged.connect(self._on_layout_shifted)
        self._menu_entries.append(entry)
        self._pane.add_menu_widget(widget)
        widget.set_compact(not self._visually_expanded(), animate=False)
        return widget

    def addSeparateLine(self):
        """添加一条与设置项上方同款的 1px 分割线。"""
        entry = _LineEntry()
        line = _SettingsDivider(self)
        wrapper = QWidget()
        wrapper.setFixedHeight(SETTINGS_DIVIDER_HEIGHT + ROW_MARGIN_TOP * 2)
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, ROW_MARGIN_TOP, 0, ROW_MARGIN_TOP)
        layout.setSpacing(0)
        layout.addWidget(line)
        entry.widget = wrapper
        wrapper.setVisible(self._visually_expanded())
        self._menu_entries.append(entry)
        self._pane.add_menu_widget(wrapper)
        return line

    def setSelectedNavItem(self, index: int) -> None:
        """按全局选择索引选中（含折叠项）；-1 清空；程序化选中不播放点击动画。"""
        index = int(index)
        if index == -1:
            self._close_submenu(animate=False)
            self._clear_selection()
            return
        entries = self._selectable_entries()
        if index < 0 or index >= len(entries):
            raise IndexError(f"NavigationView Index Out of Range: {index} (Total {len(entries)}).")
        entry = entries[index]
        self._close_submenu(animate=False)
        self._select_target(top=entry, child=None, settings=False,
                            animate=False, record=False)

    def setNavItem(self, index: int, fonticon=_UNSET, name=_UNSET,
                   layout=_UNSET) -> None:
        """按普通项内部索引修改；只更新传入的参数，layout=None 表示清空。"""
        index = int(index)
        if index < 0 or index >= len(self._nav_items):
            raise IndexError(f"NavItem Index Out of Range: {index}.")
        item = self._nav_items[index]
        if not item.isValid():
            raise RuntimeError("This NavItem is already removed.")
        if fonticon is not _UNSET:
            item.fonticon = fonticon
        if name is not _UNSET:
            item.name = name
        if layout is not _UNSET:
            self._set_item_layout(item, layout)
        self._refresh_item(item)

    def setSettingLayout(self, layout) -> None:
        if self._settings_item is None:
            raise RuntimeError("show_settings is False. There is no settings item.")
        self._set_item_layout(self._settings_item, layout)

    def removeNavItem(self, index: int) -> None:
        """按普通项内部索引删除，并使对应 NavItem 逻辑失效。"""
        index = int(index)
        if index < 0 or index >= len(self._nav_items):
            raise IndexError(f"NavItem Index Out of Range: {index}.")
        self._close_submenu(animate=False)
        item = self._nav_items[index]
        if self._selected_top is item:
            self._clear_selection(notify=False)
        self._unmount_layout(item)
        self._drop_page(item)
        if item._wrapper is not None:
            self._pane.remove_menu_widget(item._wrapper)
        item._invalidate()
        self._nav_items.pop(index)
        if item in self._menu_entries:
            self._menu_entries.remove(item)
        self._sanitize_history()
        self._refresh_indices()
        self._update_back_enabled()
        self._update_indicator(animate=False)
        self._notify_selected_changed()

    def removeNavFoldItem(self, index: int) -> None:
        """按折叠项内部索引删除（连同子项），相关模型全部逻辑失效。"""
        index = int(index)
        if index < 0 or index >= len(self._fold_items):
            raise IndexError(f"NavFoldItem Index Out of Range: {index}.")
        self._close_submenu(animate=False)
        fold = self._fold_items[index]
        involved = (self._selected_top is fold or
                    (self._selected_child is not None and
                     self._selected_child._fold is fold))
        if involved:
            self._clear_selection(notify=False)
        for child in list(fold._children):
            self._unmount_layout(child)
            self._drop_page(child)
        self._unmount_layout(fold)
        self._drop_page(fold)
        if fold._group is not None:
            self._pane.remove_menu_widget(fold._group)
        fold._invalidate()
        self._fold_items.pop(index)
        if fold in self._menu_entries:
            self._menu_entries.remove(fold)
        self._sanitize_history()
        self._refresh_indices()
        self._update_back_enabled()
        self._update_indicator(animate=False)
        self._notify_selected_changed()

    def CleatNavItems(self) -> None:
        """清空普通项、折叠项与分隔符（保留设置项）。"""
        self._close_submenu(animate=False)
        self._clear_selection(notify=False)
        for item in list(self._nav_items):
            self._unmount_layout(item)
            self._drop_page(item)
            if item._wrapper is not None:
                self._pane.remove_menu_widget(item._wrapper)
            item._invalidate()
        for fold in list(self._fold_items):
            for child in list(fold._children):
                self._unmount_layout(child)
                self._drop_page(child)
            self._unmount_layout(fold)
            self._drop_page(fold)
            if fold._group is not None:
                self._pane.remove_menu_widget(fold._group)
            fold._invalidate()
        for entry in list(self._menu_entries):
            if isinstance(entry, (_SeparatorEntry, _LineEntry)) and entry.widget is not None:
                self._pane.remove_menu_widget(entry.widget)
                entry.widget.deleteLater()
        self._nav_items.clear()
        self._fold_items.clear()
        self._menu_entries.clear()
        self._remembered_folds.clear()
        self._history.clear()
        self._update_back_enabled()
        self._update_indicator(animate=False)
        self._notify_selected_changed()

    def clearNavItems(self) -> None:
        self.CleatNavItems()

    # ------------------------------------------------------------------
    # 公共 API：形态 / 查询
    # ------------------------------------------------------------------
    def setPaneState(self, state) -> None:
        state = _coerce_pane_state(state)
        if state is self._pane_state:
            return
        self._pane_state = state
        self._reset_open_flags()
        self._apply_pane_state(manual=False, animate=True, force=True)

    def setExpandedShowInline(self, mode) -> None:
        mode = _coerce_show_inline(mode)
        if mode is self._show_inline:
            return
        self._show_inline = mode
        self._reset_open_flags()
        self._apply_pane_state(manual=False, animate=True, force=True)

    def paneState(self) -> PaneStateEnum:
        return self._pane_state

    def expandedShowInline(self) -> PaneShowInlineEnum:
        return self._show_inline

    def effectivePaneState(self) -> PaneStateEnum | None:
        return self._effective_state

    def usesFlyout(self) -> bool:
        return self._presentation_flyout

    def indexOf(self, item) -> int:
        if item is None:
            return -1
        fold = getattr(item, "_fold", None)
        if fold is not None:
            return fold.globalIndex
        return self._global_index_of(item)

    def currentSelection(self):
        """当前选中的 NavItem / NavFoldItem；设置项返回内置设置 NavItem。"""
        return self._current_target()

    def setHistoryLimit(self, limit: int) -> None:
        self._history_limit = max(0, int(limit))
        while len(self._history) > self._history_limit:
            self._history.pop(0)
        self._update_back_enabled()

    def historyLimit(self) -> int:
        return self._history_limit

    # ------------------------------------------------------------------
    # 选择模型
    # ------------------------------------------------------------------
    def _selectable_entries(self) -> list:
        return [entry for entry in self._menu_entries
                if isinstance(entry, (NavItem, NavFoldItem))]

    def _global_index_of(self, item) -> int:
        index = 0
        for entry in self._menu_entries:
            if isinstance(entry, (NavItem, NavFoldItem)):
                if entry is item:
                    return index
                index += 1
        return -1

    def _selection_index(self) -> int:
        if self._settings_selected:
            return -1
        if self._selected_child is not None:
            return self._selected_child._fold.globalIndex
        if self._selected_top is not None:
            return self._selected_top.globalIndex
        return -1

    def _selection_key(self):
        if self._settings_selected:
            return ("settings", None)
        if self._selected_child is not None:
            return ("child", self._selected_child)
        if self._selected_top is not None:
            return ("top", self._selected_top)
        return None

    def _current_target(self):
        if self._settings_selected:
            return self._settings_item
        if self._selected_child is not None:
            return self._selected_child
        return self._selected_top

    def _visually_expanded(self) -> bool:
        return self._effective_state is PaneStateEnum.Expanded

    def _refresh_indices(self) -> None:
        for index, item in enumerate(self._nav_items):
            item._index = index if item.isValid() else -1
        for index, fold in enumerate(self._fold_items):
            fold._index = index if fold.isValid() else -1
            for child_index, child in enumerate(fold._children):
                child._index = child_index if child.isValid() else -1

    def _sync_selection_models(self) -> None:
        for item in self._nav_items:
            if item.isValid():
                item._set_selected(
                    self._selected_top is item and self._selected_child is None
                )
        for fold in self._fold_items:
            if not fold.isValid():
                continue
            branch = (self._selected_top is fold or
                      (self._selected_child is not None and
                       self._selected_child._fold is fold))
            fold._set_selected(branch)
            for child in fold._children:
                if child.isValid():
                    child._set_selected(self._selected_child is child)
            if (self._selected_child is not None and
                    self._selected_child._fold is fold and
                    self._selected_child in fold._children):
                child_index = fold._children.index(self._selected_child)
            else:
                child_index = -1
            if branch or fold._last_child_selected is not None:
                fold._emit_child_selected(child_index)
        if self._settings_item is not None:
            self._settings_item._set_selected(self._settings_selected)

    def _notify_selected_changed(self) -> None:
        key = self._selection_key()
        value = self._selection_index()
        if key == self._last_selected_key and value == self._last_selected_index:
            return
        self._last_selected_key = key
        self._last_selected_index = value
        self.selectedChanged.emit(value)

    def _push_history(self) -> None:
        snapshot = {
            "top": self._selected_top,
            "child": self._selected_child,
            "settings": self._settings_selected,
            "folds": {fold: fold._expanded for fold in self._fold_items
                      if fold.isValid()},
        }
        self._history.append(snapshot)
        while len(self._history) > self._history_limit:
            self._history.pop(0)
        self._update_back_enabled()

    def _update_back_enabled(self) -> None:
        if self._back is None:
            return
        available = bool(self._history)
        if self._auto_hide_back:
            visible = available
            self._back.setEnabled(True)
        else:
            visible = True
            self._back.setEnabled(available)
        self._back.setVisible(visible)
        if getattr(self, "_header", None) is not None:
            self._update_header(self._visually_expanded())
        self.backVisibilityChanged.emit(visible)

    def setAutoHideBack(self, enabled: bool) -> None:
        """True：没有可返回的历史时隐藏返回按钮；False：禁用而不是隐藏。"""
        enabled = bool(enabled)
        if enabled == self._auto_hide_back:
            return
        self._auto_hide_back = enabled
        self._update_back_enabled()

    def autoHideBack(self) -> bool:
        return self._auto_hide_back

    def backButtonVisible(self) -> bool:
        """返回按钮当前是否应当显示（不受父窗口是否可见影响）。"""
        return self._back is not None and not self._back.isHidden()

    # ------------------------------------------------------------------
    # TitleBar 集成
    # ------------------------------------------------------------------
    def _attach_titlebar(self, titlebar, move_buttons: bool) -> None:
        if self._titlebar is titlebar and self._buttons_external == bool(move_buttons):
            self._update_back_enabled()
            return
        if self._titlebar is not None:
            self._detach_titlebar()
        self._titlebar = titlebar
        self._buttons_external = bool(move_buttons)
        if self._buttons_external:
            buttons = self._header.detach_buttons()
            titlebar.attach_navigation_buttons(buttons)
        self._update_back_enabled()

    def _detach_titlebar(self) -> None:
        titlebar = self._titlebar
        self._titlebar = None
        was_external = self._buttons_external
        self._buttons_external = False
        if titlebar is not None:
            buttons = titlebar.detach_navigation_buttons()
            if buttons:
                for button in buttons:
                    button.set_button_size(*HEADER_BUTTON_SIZE)
                    button.show()
                self._header.attach_buttons(buttons)
        if was_external:
            self._update_back_enabled()

    def _sanitize_history(self) -> None:
        """结构性删除后移除失效目标，保留仍然可用的返回步骤。"""
        cleaned = []
        for snapshot in self._history:
            top = snapshot.get("top")
            child = snapshot.get("child")
            if top is not None and not getattr(top, "isValid", lambda: False)():
                continue
            if child is not None:
                if not getattr(child, "isValid", lambda: False)():
                    continue
                if not getattr(child._fold, "isValid", lambda: False)():
                    continue
            folds = {}
            for fold, expanded in snapshot.get("folds", {}).items():
                if getattr(fold, "isValid", lambda: False)():
                    folds[fold] = expanded
            snapshot["folds"] = folds
            cleaned.append(snapshot)
        self._history = cleaned
        self._update_back_enabled()

    def _select_target(self, *, top, child, settings: bool,
                       animate: bool, record: bool) -> None:
        new_top = None if settings else top
        new_child = None if settings else child
        if (settings == self._settings_selected and
                new_top is self._selected_top and
                new_child is self._selected_child):
            return
        if record:
            self._push_history()
        self._settings_selected = bool(settings)
        self._selected_top = new_top
        self._selected_child = new_child

        if (new_child is not None and self._visually_expanded() and
                not new_child._fold._expanded):
            self._set_fold_expanded(new_child._fold, True,
                                    animate=animate, sync_indicator=False)

        self._sync_selection_models()
        self._update_indicator(animate=animate)
        self._show_content_for(self._current_target(), animate=animate)
        self._notify_selected_changed()
        self._update_back_enabled()

    def _clear_selection(self, notify: bool = True) -> None:
        if (self._selected_top is None and self._selected_child is None and
                not self._settings_selected):
            return
        self._selected_top = None
        self._selected_child = None
        self._settings_selected = False
        self._sync_selection_models()
        self._update_indicator(animate=False)
        self._show_content_for(None, animate=False)
        if notify:
            self._notify_selected_changed()

    def _go_back(self) -> None:
        if not self._history:
            return
        snapshot = self._history.pop()
        self._close_submenu(animate=False)

        folds = snapshot.get("folds", {})
        if self._visually_expanded():
            for fold, expanded in folds.items():
                if isinstance(fold, NavFoldItem) and fold.isValid():
                    self._set_fold_expanded(fold, bool(expanded),
                                            animate=True, sync_indicator=False)
        else:
            self._remembered_folds = {
                fold for fold, expanded in folds.items()
                if expanded and isinstance(fold, NavFoldItem) and fold.isValid()
            }

        top = snapshot.get("top")
        child = snapshot.get("child")
        settings = bool(snapshot.get("settings"))
        if top is not None and not getattr(top, "isValid", lambda: False)():
            top = None
        if child is not None and not getattr(child, "isValid", lambda: False)():
            child = None
        if child is not None:
            parent = child._fold
            if not parent.isValid():
                child = None
            elif top is not parent:
                top = parent
        if settings and self._settings_item is not None:
            self._selected_top = None
            self._selected_child = None
            self._settings_selected = True
        else:
            self._settings_selected = False
            self._selected_top = top
            self._selected_child = child
        if (self._selected_child is not None and self._visually_expanded() and
                not self._selected_child._fold._expanded):
            self._set_fold_expanded(self._selected_child._fold, True,
                                    animate=True, sync_indicator=False)

        self._sync_selection_models()
        self._update_indicator(animate=True)
        self._show_content_for(self._current_target(), animate=True)
        self._notify_selected_changed()
        self._update_back_enabled()

    # ------------------------------------------------------------------
    # 交互入口
    # ------------------------------------------------------------------
    def _activate_nav_item(self, item: NavItem) -> None:
        if not item.isValid():
            return
        self._close_submenu(animate=False)
        if item._fold is not None:
            self._activate_child(item)
            return
        self._select_target(top=item, child=None, settings=False,
                            animate=True, record=True)

    def _activate_fold(self, fold: NavFoldItem) -> None:
        if not fold.isValid():
            return
        if not self._visually_expanded():
            if fold.layout is not None:
                self._select_target(top=fold, child=None, settings=False,
                                    animate=True, record=True)
            self._toggle_submenu(fold)
            return

        self._close_submenu(animate=False)
        self._set_fold_expanded(fold, not fold._expanded, animate=True)
        if fold.layout is not None:
            self._select_target(top=fold, child=None, settings=False,
                                animate=True, record=True)

    def _activate_child(self, child: NavItem, from_submenu: bool = False) -> None:
        if not child.isValid():
            return
        self._select_target(top=child._fold, child=child, settings=False,
                            animate=True, record=True)
        if from_submenu:
            self._close_submenu(animate=True)

    def _activate_settings(self) -> None:
        if self._settings_item is None or not self._settings_item.isValid():
            return
        self._close_submenu(animate=False)
        self._select_target(top=None, child=None, settings=True,
                            animate=True, record=True)

    # ------------------------------------------------------------------
    # 折叠 / 指示器 / 内容
    # ------------------------------------------------------------------
    def _set_fold_expanded(self, fold: NavFoldItem, expanded: bool,
                           animate: bool = True,
                           sync_indicator: bool = True) -> None:
        if not fold.isValid():
            return
        expanded = bool(expanded)
        if expanded and not self._visually_expanded():
            # 压缩/隐藏时只记住状态，展开分类时再恢复。
            self._remembered_folds.add(fold)
            return
        if (not expanded and not self._visually_expanded() and
                not fold._expanded):
            self._remembered_folds.discard(fold)
            return
        if fold._expanded == expanded:
            if fold._group is not None:
                fold._group.set_expanded(expanded, animate=False)
            return
        fold._set_expanded(expanded)
        if fold._group is not None:
            fold._group.set_expanded(expanded, animate=animate)
        if sync_indicator:
            self._update_indicator(animate=animate)

    def _indicator_target(self):
        if self._settings_selected:
            return self._settings_item
        if self._selected_child is not None:
            fold = self._selected_child._fold
            if (self._submenu is not None and fold.layout is None and
                    self._submenu.fold() is fold):
                return None
            if self._visually_expanded() and fold._expanded:
                return self._selected_child
            return fold
        return self._selected_top

    def _update_indicator(self, animate: bool = True, retry: bool = True) -> None:
        target = self._indicator_target()
        row = target._row if target is not None else None
        indicator = self._pane.indicator()
        indicator.set_row(row, animate=animate)
        for fold in self._fold_items:
            if fold.isValid() and fold._row is not None:
                fold._row.set_selected(target is fold)
        self._update_submenu_selection()
        # 刚添加到滚动区、尚未完成布局的行会暂时不可见；下一轮事件循环再刷新一次。
        if retry and row is not None and indicator._row is None:
            QTimer.singleShot(0, lambda: self._update_indicator(False, retry=False))

    def _update_submenu_selection(self) -> None:
        if self._submenu is None:
            return
        for child in self._submenu.fold().children():
            row = self._submenu.row_for(child)
            if row is not None:
                row.set_selected(self._selected_child is child)

    def _on_layout_shifted(self) -> None:
        if self._pane.indicator().is_animating():
            return
        self._update_indicator(animate=False)

    def _ensure_page(self, item: NavItem | NavFoldItem) -> _ContentPage | None:
        if item is None or not item.isValid() or item.layout is None:
            return None
        page = item._page
        if page is None:
            page = _ContentPage()
            self._content_host.register_page(page)
            item._page = page
        key = id(item.layout)
        entry = self._layout_registry.get(key)
        if entry is None or entry[0] is not item.layout:
            return None
        host = entry[1]
        self._detach_host_from_pages(host)
        page.add_host(host)
        host.show()
        return page

    def _show_content_for(self, target, animate: bool) -> None:
        if (target is None or
                not getattr(target, "isValid", lambda: True)() or
                getattr(target, "layout", None) is None):
            if self._content_host.current_page() is not None:
                self._content_host.show_page(None, False)
                self._content_revision += 1
            return
        page = self._ensure_page(target)
        if page is None:
            return
        changed = self._content_host.current_page() is not page
        self._content_host.show_page(page, animate if changed else False)
        if changed:
            self._content_revision += 1
            self._schedule_pane_snapshot()

    def _drop_page(self, item) -> None:
        page = getattr(item, "_page", None)
        if page is not None:
            self._content_host.remove_page(page)
            item._page = None

    def _detach_host_from_pages(self, host: QWidget) -> None:
        for page in self._content_host.pages():
            page.remove_host(host)

    # ------------------------------------------------------------------
    # Layout 所有权
    # ------------------------------------------------------------------
    def _make_host(self, layout) -> QWidget:
        if isinstance(layout, QWidget):
            return layout
        if not isinstance(layout, QLayout):
            raise TypeError("Layout must be QLayout or QWidget.")
        parent_widget = layout.parentWidget()
        if parent_widget is not None and parent_widget.layout() is layout:
            return parent_widget
        if layout.parent() is not None:
            raise ValueError("Layout mustn`t be the child of another layout.")
        host = _LayoutHost()
        host.setAutoFillBackground(False)
        host.setLayout(layout)
        return host

    def _host_for_layout(self, layout) -> QWidget:
        key = id(layout)
        entry = self._layout_registry.get(key)
        if entry is not None and entry[0] is layout:
            return entry[1]
        host = self._make_host(layout)
        self._layout_registry[key] = (layout, host)
        return host

    def _park_host(self, host: QWidget) -> None:
        self._detach_host_from_pages(host)
        host.hide()
        host.setParent(self._layout_pool)

    def _unmount_layout(self, item) -> None:
        layout = getattr(item, "_layout", None)
        if layout is None:
            return
        key = id(layout)
        item._layout = None
        if self._layout_owner.get(key) is item:
            self._layout_owner.pop(key, None)
        entry = self._layout_registry.get(key)
        if entry is not None:
            self._park_host(entry[1])
        if self._current_target() is item:
            self._show_content_for(None, animate=False)

    def _set_item_layout(self, item, layout) -> None:
        if not item.isValid():
            raise RuntimeError("This item is no longer valid. ")
        if layout is item._layout:
            return
        if item._layout is not None:
            self._unmount_layout(item)

        if layout is None:
            if self._current_target() is item:
                self._show_content_for(None, animate=False)
            self._content_revision += 1
            self._schedule_pane_snapshot()
            return

        existing = self._layout_owner.get(id(layout))
        if existing is not None and existing is not item:
            warnings.warn(
                f"layout is already mounted on {existing!r}, the later mounted {item!r} will take effect,"
                "the previous menu item has been unmounted",
                RuntimeWarning, stacklevel=3,
            )
            if getattr(existing, "_layout", None) is layout:
                existing._layout = None
                self._layout_owner.pop(id(layout), None)
                entry = self._layout_registry.get(id(layout))
                if entry is not None:
                    self._park_host(entry[1])
                if self._current_target() is existing:
                    self._show_content_for(None, animate=False)

        host = self._host_for_layout(layout)
        self._layout_owner[id(layout)] = item
        item._layout = layout
        page = self._ensure_page(item)
        if page is not None:
            self._detach_host_from_pages(host)
            page.add_host(host)
            host.show()
        if self._current_target() is item:
            self._show_content_for(item, animate=False)
        self._content_revision += 1
        self._schedule_pane_snapshot()

    def _schedule_pane_snapshot(self) -> None:
        if (self._effective_state is PaneStateEnum.Expanded and
                self._presentation_flyout):
            self._pane_snapshot_timer.start(ANIM_MS + 30)

    def _refresh_item(self, item) -> None:
        row = getattr(item, "_row", None)
        if row is not None:
            row.refresh_content()
        if self._submenu is not None and isinstance(item, NavItem):
            flyout_row = self._submenu.row_for(item)
            if flyout_row is not None:
                flyout_row.refresh_content()

    # ------------------------------------------------------------------
    # 形态计算
    # ------------------------------------------------------------------
    def _base_state(self) -> PaneStateEnum:
        state = self._pane_state
        width = max(1, self.width())
        if state is PaneStateEnum.Auto:
            if width > self._compact_threshold:
                return PaneStateEnum.Expanded
            if width < self._hide_threshold:
                return PaneStateEnum.Hide
            return PaneStateEnum.Compact
        if state is PaneStateEnum.Expanded:
            return PaneStateEnum.Expanded
        if state in (PaneStateEnum.Compact, PaneStateEnum.ForceCompact):
            return PaneStateEnum.Compact
        return PaneStateEnum.Hide

    def _is_flyout_presentation(self) -> bool:
        mode = self._show_inline
        if mode is PaneShowInlineEnum.Inline:
            return False
        if mode is PaneShowInlineEnum.Flyout:
            return True
        if self._pane_state in (PaneStateEnum.Compact, PaneStateEnum.Expanded):
            return False
        if self._pane_state in (PaneStateEnum.ForceCompact, PaneStateEnum.Hide):
            return True
        return self.width() <= self._compact_threshold

    def _reset_open_flags(self) -> None:
        base = self._base_state()
        flyout = self._is_flyout_presentation()
        self._last_base = base
        if base is PaneStateEnum.Expanded:
            self._pane_flyout_open = flyout
            self._pane_open_inline = not flyout
        else:
            self._pane_flyout_open = False
            self._pane_open_inline = False

    def _compute_effective(self) -> tuple[PaneStateEnum, bool]:
        base = self._base_state()
        flyout = self._is_flyout_presentation()
        if base is PaneStateEnum.Expanded:
            opened = self._pane_flyout_open if flyout else self._pane_open_inline
            return (PaneStateEnum.Expanded if opened else PaneStateEnum.Compact), flyout
        if base is PaneStateEnum.Compact:
            opened = self._pane_flyout_open if flyout else self._pane_open_inline
            return (PaneStateEnum.Expanded if opened else PaneStateEnum.Compact), flyout
        opened = self._pane_flyout_open if flyout else self._pane_open_inline
        return (PaneStateEnum.Expanded if opened else PaneStateEnum.Hide), flyout

    def _target_geometry(self) -> dict:
        base = self._base_state()
        rail = 0 if base is PaneStateEnum.Hide else COMPACT_WIDTH
        height = float(max(1, self.height()))
        effective = self._effective_state or base
        if effective is PaneStateEnum.Expanded:
            if self._presentation_flyout:
                return {
                    "pane_width": float(EXPANDED_WIDTH), "pane_x": 4.0,
                    "pane_y": 4.0, "pane_height": max(0.0, height - 8),
                    "content_x": float(rail), "flyout": True,
                }
            return {
                "pane_width": float(EXPANDED_WIDTH), "pane_x": 0.0,
                "pane_y": 0.0, "pane_height": height,
                "content_x": float(EXPANDED_WIDTH), "flyout": False,
            }
        if effective is PaneStateEnum.Compact:
            return {
                "pane_width": float(rail), "pane_x": 0.0,
                "pane_y": 0.0, "pane_height": height,
                "content_x": float(rail), "flyout": False,
            }
        return {
            "pane_width": 0.0, "pane_x": 0.0, "pane_y": 0.0,
            "pane_height": height, "content_x": 0.0, "flyout": False,
        }

    def _apply_pane_state(self, manual: bool, animate: bool = True,
                          force: bool = False) -> None:
        base = self._base_state()
        presentation = self._is_flyout_presentation()
        effective, _ = self._compute_effective()
        old_effective = self._effective_state
        old_presentation = self._presentation_flyout
        was_flyout_visible = (old_effective is PaneStateEnum.Expanded and
                              old_presentation)

        new_tuple = (effective, presentation)
        if (not force and old_effective is not None and
                new_tuple == self._last_state_tuple):
            self._sync_geometry()
            return

        if (effective is not PaneStateEnum.Compact and
                self._submenu is not None):
            self._close_submenu(animate=False)

        self._effective_state = effective
        self._presentation_flyout = presentation
        self._last_base = base
        self._root.set_base_width(0 if base is PaneStateEnum.Hide else COMPACT_WIDTH)

        expanded = effective is PaneStateEnum.Expanded
        flyout_visual = ((expanded and presentation) or
                         (not expanded and was_flyout_visible and animate))
        self._pane.set_flyout(flyout_visual)
        self._update_header(expanded)
        if expanded and presentation:
            self._capture_pane_snapshot_if_needed()
        self._apply_visual_expansion(expanded, animate=animate)
        self._pane.set_compact(not expanded)

        target = self._target_geometry()
        duration = ANIM_MS if animate and self.isVisible() else 0

        def finish() -> None:
            if not expanded or not presentation:
                self._pane.set_flyout(False)
                self._root.set_flyout_mode(False)
            if expanded and presentation:
                self._capture_pane_snapshot_if_needed()

        self._root.animate_to(
            pane_width=target["pane_width"],
            pane_x=target["pane_x"],
            pane_y=target["pane_y"],
            pane_height=target["pane_height"],
            content_x=target["content_x"],
            duration=duration,
            flyout=flyout_visual,
            on_finished=finish,
        )

        if old_effective is not None and new_tuple != self._last_state_tuple:
            self.paneStateChanged.emit(manual, old_effective, effective,
                                       presentation)
        self._last_state_tuple = new_tuple
        self._sync_app_filter()

    def _sync_geometry(self) -> None:
        if self._effective_state is None:
            return
        target = self._target_geometry()
        self._root.animate_to(
            pane_width=target["pane_width"],
            pane_x=target["pane_x"],
            pane_y=target["pane_y"],
            pane_height=target["pane_height"],
            content_x=target["content_x"],
            duration=0,
            flyout=target["flyout"],
        )
        if target["flyout"]:
            self._pane_snapshot_timer.start(0)
            self._pane.set_flyout(True)
        else:
            self._pane.set_flyout(False)
        self._update_header(self._visually_expanded())

    def _apply_visual_expansion(self, expanded: bool, animate: bool) -> None:
        previous = self._was_visually_expanded
        if expanded:
            if previous is not True:
                restore = set(self._remembered_folds)
                if self._selected_child is not None:
                    restore.add(self._selected_child._fold)
                for fold in list(restore):
                    if (isinstance(fold, NavFoldItem) and fold.isValid() and
                            not fold._expanded):
                        self._set_fold_expanded(fold, True, animate=animate,
                                                sync_indicator=False)
            self._set_rows_compact(False)
            for separator in self._separators():
                separator.set_compact(False, animate=animate)
            for line in self._lines():
                line.setVisible(True)
        else:
            if previous is True:
                self._remembered_folds = {
                    fold for fold in self._fold_items
                    if fold.isValid() and fold._expanded
                }
                for fold in list(self._fold_items):
                    if fold.isValid() and fold._expanded:
                        self._set_fold_expanded(fold, False, animate=animate,
                                                sync_indicator=False)
            self._set_rows_compact(True)
            for separator in self._separators():
                separator.set_compact(True, animate=animate)
            for line in self._lines():
                line.setVisible(False)
        self._was_visually_expanded = expanded
        self._update_indicator(animate=animate)

    def _set_rows_compact(self, compact: bool) -> None:
        for item in self._nav_items:
            if item.isValid() and item._row is not None:
                item._row.set_compact(compact)
                item._row.refresh_content()
        for fold in self._fold_items:
            if fold.isValid() and fold._row is not None:
                fold._row.set_compact(compact)
                fold._row.refresh_content()
            for child in fold._children:
                if child.isValid() and child._row is not None:
                    child._row.set_compact(compact)
                    child._row.refresh_content()
        if self._settings_row is not None:
            self._settings_row.set_compact(compact)
            self._settings_row.refresh_content()

    def _separators(self) -> list[_SeparatorWidget]:
        return [entry.widget for entry in self._menu_entries
                if isinstance(entry, _SeparatorEntry) and entry.widget is not None]

    def _lines(self) -> list[QWidget]:
        return [entry.widget for entry in self._menu_entries
                if isinstance(entry, _LineEntry) and entry.widget is not None]

    def _update_header(self, expanded: bool) -> None:
        if self._header is None:
            return
        if self._buttons_external:
            self._header.hide()
            self._pane.set_header_height(0)
            clearance = 0
            titlebar = self._titlebar
            if titlebar is not None:
                try:
                    titlebar.refreshNavigationButtons()
                except RuntimeError:
                    self._titlebar = None
                    self._buttons_external = False
        else:
            self._header.set_vertical(True)
            self._header.refresh_layout()
            visible = not self._header.is_empty()
            self._header.setVisible(visible)
            self._pane.set_header_height(self._header.height() if visible else 0)
            clearance = 0
            if (self._effective_state is PaneStateEnum.Hide and visible):
                clearance = self._header.height() + 4
        if clearance != self._last_clearance:
            self._last_clearance = clearance
            self._content_revision += 1
        self._content_card.set_top_clearance(clearance)

    # ------------------------------------------------------------------
    # 汉堡 / Flyout / 事件
    # ------------------------------------------------------------------
    def _toggle_pane(self) -> None:
        self._close_submenu(animate=False)
        presentation = self._is_flyout_presentation()
        if self._effective_state is PaneStateEnum.Expanded:
            if presentation:
                self._pane_flyout_open = False
            else:
                self._pane_open_inline = False
        else:
            if presentation:
                self._pane_flyout_open = True
                self._pane_open_inline = False
            else:
                self._pane_open_inline = True
                self._pane_flyout_open = False
        self._apply_pane_state(manual=True, animate=True, force=True)

    def _toggle_submenu(self, fold: NavFoldItem) -> None:
        if self._submenu is not None and self._submenu.fold() is fold:
            self._close_submenu(animate=True)
            return
        if not fold.children():
            return
        self._open_submenu(fold)

    def _open_submenu(self, fold: NavFoldItem) -> None:
        self._close_submenu(animate=False)
        flyout = _SubmenuFlyout(self, fold)
        self._submenu = flyout
        flyout.show_flyout()
        # 某些平台上 Tool 窗口首次 show 后需要再抬一次，避免被主窗口盖住。
        QTimer.singleShot(0, self._raise_submenu)
        self._update_indicator(animate=False)
        self._sync_app_filter()

    def _raise_submenu(self) -> None:
        if self._submenu is not None and self._submenu.isVisible():
            self._submenu.raise_()

    def _close_submenu(self, animate: bool = True) -> None:
        flyout = self._submenu
        if flyout is None:
            return
        flyout.close_flyout(animate=animate)
        if not animate:
            self._submenu = None
            self._update_indicator(animate=False)
        self._sync_app_filter()

    def _on_submenu_closed(self, flyout: _SubmenuFlyout) -> None:
        if self._submenu is flyout:
            self._submenu = None
        flyout.deleteLater()
        self._update_indicator(animate=False)
        self._sync_app_filter()

    def _widget_in_pane(self, widget: QWidget | None) -> bool:
        if widget is None:
            return False
        return widget is self._pane or self._pane.isAncestorOf(widget)

    def _widget_in_header(self, widget: QWidget | None) -> bool:
        if widget is None:
            return False
        if self._header is not None and (
                widget is self._header or self._header.isAncestorOf(widget)):
            return True
        titlebar = self._titlebar
        if self._buttons_external and titlebar is not None:
            return titlebar.owns_navigation_widget(widget)
        return False

    def _handle_outside_press(self, widget: QWidget | None) -> None:
        if self._submenu is not None and self._submenu.isVisible():
            if not self._submenu.contains_widget(widget):
                trigger_row = self._submenu.fold()._row
                on_trigger = (widget is trigger_row or
                              (trigger_row is not None and
                               trigger_row.isAncestorOf(widget)))
                if not on_trigger:
                    self._close_submenu(animate=True)
                    return
        if (self._pane_flyout_open and self._presentation_flyout and
                self._effective_state is PaneStateEnum.Expanded):
            if not (self._widget_in_pane(widget) or
                    self._widget_in_header(widget)):
                self._pane_flyout_open = False
                self._apply_pane_state(manual=True, animate=True, force=True)

    def eventFilter(self, obj, event) -> bool:
        watch = getattr(self, "_glass_watch_window", None)
        if obj is watch and watch is not self:
            event_type = event.type()
            if event_type == QEvent.Type.Move:
                self._follow_window_move()
            elif event_type == QEvent.Type.Resize:
                self._refresh_glass()
            return False
        if not self.isVisible():
            return False
        event_type = event.type()
        if event_type == QEvent.Type.MouseButtonPress:
            try:
                position = event.globalPosition().toPoint()
            except AttributeError:
                position = None
            if position is not None:
                self._handle_outside_press(QApplication.widgetAt(position))
            return False
        if event_type == QEvent.Type.KeyPress and event.key() == Qt.Key_Escape:
            if self._submenu is not None:
                self._close_submenu(animate=True)
                return True
            if (self._pane_flyout_open and self._presentation_flyout and
                    self._effective_state is PaneStateEnum.Expanded):
                self._pane_flyout_open = False
                self._apply_pane_state(manual=True, animate=True, force=True)
                return True
        return False

    def _install_app_filter(self) -> None:
        app = QApplication.instance()
        if app is not None and not self._app_filter_installed:
            app.installEventFilter(self)
            self._app_filter_installed = True

    def _remove_app_filter(self) -> None:
        app = QApplication.instance()
        if app is not None and self._app_filter_installed:
            app.removeEventFilter(self)
            self._app_filter_installed = False

    def _sync_app_filter(self) -> None:
        """只在有 Flyout 打开时监听全局点击，避免无谓的全局事件过滤。"""
        needed = (self.isVisible() and
                  (self._submenu is not None or
                   (self._pane_flyout_open and self._presentation_flyout and
                    self._effective_state is PaneStateEnum.Expanded)))
        if needed:
            self._install_app_filter()
        else:
            self._remove_app_filter()

    # ------------------------------------------------------------------
    # 快照
    # ------------------------------------------------------------------
    def _blurred_grab(self, widget: QWidget, cache_attr: str,
                      style: FrostStyle = FLYOUT_GLASS):
        origin = widget.mapToGlobal(QPoint(0, 0))
        dpr_hint = float(widget.devicePixelRatioF() or 1.0)
        key = (widget.width(), widget.height(), origin.x(), origin.y(),
               dpr_hint, self._content_revision,
               style.blur, style.brightness, style.saturation)
        cached = getattr(self, cache_attr, None)
        if cached is not None and cached[0] == key:
            return cached[1]
        if widget.width() <= 0 or widget.height() <= 0:
            return None
        pixmap = widget.grab()
        if pixmap.isNull():
            return None
        image = pixmap.toImage()
        dpr = float(image.devicePixelRatio() or dpr_hint)
        blurred = blur_qimage(
            image,
            style.blur * dpr,
            style.brightness,
            style.saturation,
        )
        blurred.setDevicePixelRatio(dpr)
        result = (blurred, origin)
        setattr(self, cache_attr, (key, result))
        return result

    def _grab_window_snapshot(self, style: FrostStyle = FLYOUT_GLASS):
        return self._blurred_grab(self, "_window_snapshot_cache", style)

    def _capture_pane_snapshot_if_needed(self) -> None:
        if not self.isVisible():
            return
        if not (self._effective_state is PaneStateEnum.Expanded and
                self._presentation_flyout):
            return
        # 抓窗口时临时隐藏浮层，避免把 Flyout 自身画进快照；
        # 同时让快照覆盖侧边栏所在的窄条，消除玻璃接缝。
        hidden = []
        for widget in (self._pane, self._root.shadow(), self._header):
            if widget is not None and widget.isVisible():
                hidden.append(widget)
                widget.setVisible(False)
        try:
            snapshot = self._blurred_grab(self, "_pane_snapshot_cache")
        finally:
            for widget in hidden:
                widget.setVisible(True)
        self._last_window_pos = self.mapToGlobal(QPoint(0, 0))
        if snapshot is None:
            self._pane.set_snapshot(None, QPoint(0, 0))
        else:
            self._pane.set_snapshot(snapshot[0], snapshot[1])

    # ------------------------------------------------------------------
    # 窗口事件
    # ------------------------------------------------------------------
    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._sync_glass_window_watch()
        try:
            self._glass_last_window_pos = self.window().mapToGlobal(QPoint(0, 0))
        except RuntimeError:
            pass
        if self._ready:
            self._last_window_pos = self.mapToGlobal(QPoint(0, 0))
            self._content_revision += 1
            self._sync_geometry()
            self._update_indicator(animate=False)
            QTimer.singleShot(0, lambda: self._update_indicator(animate=False))
            self._sync_app_filter()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if not self._ready:
            return
        self._content_revision += 1
        if self._submenu is not None:
            self._close_submenu(animate=False)
        if self._pane_state is PaneStateEnum.Auto:
            base = self._base_state()
            if base is not self._last_base:
                self._reset_open_flags()
                self._apply_pane_state(manual=False, animate=True, force=True)
                return
        self._sync_geometry()

    def moveEvent(self, event) -> None:
        super().moveEvent(event)
        if not self._ready:
            return
        self._follow_window_move()

    # ------------------------------------------------------------------
    # 玻璃刷新 / 外层窗口跟随
    # ------------------------------------------------------------------
    def _sync_glass_window_watch(self) -> None:
        """监听真正的顶层窗口（宿主被嵌入到别的窗口时）。

        玻璃采样依赖窗口的全局坐标，Flyout 也要跟着主窗口移动；宿主是子控件
        时收不到外层窗口的 Move 事件，所以把事件过滤器挂到顶层窗口上。
        """
        try:
            window = self.window()
        except RuntimeError:
            return
        if window is self._glass_watch_window:
            return
        if self._glass_watch_window is not None:
            try:
                self._glass_watch_window.removeEventFilter(self)
            except RuntimeError:
                pass
        self._glass_watch_window = window
        if window is not None and window is not self:
            window.installEventFilter(self)

    def _refresh_glass(self) -> None:
        """整块玻璃一起重绘（窗口移动 / 采样源更新后调用）。"""
        backdrop = getattr(self, "backdrop", None)
        if backdrop is not None:
            backdrop.update()
        for widget in (getattr(self, "_pane", None),
                       getattr(self, "_root", None),
                       getattr(self, "_content_card", None)):
            if widget is not None:
                widget.update()
        if self._submenu is not None:
            self._submenu.surface().update()

    def _follow_window_move(self) -> None:
        """窗口位置变化：玻璃重新采样，Flyout 保持相对位置一起移动。

        用窗口的实际位置计算位移：同一个 Move 事件可能同时被“顶层窗口
        过滤器”和“应用级过滤器”看到，重复处理会移动两次。
        """
        try:
            position = self.window().mapToGlobal(QPoint(0, 0))
        except RuntimeError:
            return
        delta = position - self._glass_last_window_pos
        self._glass_last_window_pos = position
        if not (delta.x() or delta.y()):
            return
        self._pane.shift_snapshot(delta.x(), delta.y())
        if self._submenu is not None:
            self._submenu.move_with_window(delta.x(), delta.y())
        self._refresh_glass()

    def _handle_activation_change(self) -> None:
        if self._submenu is None:
            return
        if self.isActiveWindow():
            return
        flyout = self._submenu
        active = QApplication.activeWindow()
        if (flyout.isActiveWindow() or active is flyout or
                (active is not None and flyout.isAncestorOf(active))):
            return
        self._close_submenu(animate=False)

    def changeEvent(self, event) -> None:
        if event.type() in (QEvent.Type.WindowDeactivate,
                            QEvent.Type.ActivationChange):
            self._handle_activation_change()
        super().changeEvent(event)

    def event(self, event):
        if event.type() == QEvent.Type.WindowDeactivate:
            self._handle_activation_change()
        elif event.type() == QEvent.Type.ParentChange:
            self._sync_glass_window_watch()
        return super().event(event)

    def hideEvent(self, event) -> None:
        if self._submenu is not None:
            self._close_submenu(animate=False)
        self._remove_app_filter()
        super().hideEvent(event)

    def closeEvent(self, event) -> None:
        self._close_submenu(animate=False)
        self._pane_snapshot_timer.stop()
        self._remove_app_filter()
        self._root.stop_animation()
        super().closeEvent(event)


__all__ = [
    "NavigationView",
    "NavItem",
    "NavFoldItem",
    "PaneStateEnum",
    "PaneShowInlineEnum",
    "HighLightPanel",
    "HoverToolTip",
    "TitleBarWindow"
]


# =============================================================================
# Windows 原生窗口效果（DWM 阴影 / 最小化最大化动画 / 圆角 / 贴靠布局）
# =============================================================================
#
# 核心做法（与 Chromium / Electron 的隐藏标题栏方案一致）：
#   1. 窗口本身仍然是一个“带边框”的普通 Win32 窗口（WS_OVERLAPPEDWINDOW），
#      因此 DWM 会照常提供：窗口阴影、最小化/最大化动画、Aero Snap、
#      Win+方向键贴靠、右键系统菜单、任务栏预览等原生效果；
#   2. 用 WM_NCCALCSIZE 把非客户区“算成 0”，让客户区铺满整个窗口，
#      从而把原生标题栏藏起来，由我们自己画；
#   3. 用 WM_NCHITTEST 把标题栏映射成 HTCAPTION，把三个按钮映射成
#      HTMINBUTTON / HTMAXBUTTON / HTCLOSE —— 这样点击、拖动、双击最大化、
#      右侧系统菜单、Windows 11 最大化按钮的“贴靠布局”悬浮面板全是系统行为；
#   4. 用 DWM 属性给窗口加圆角，并在系统主题变化时同步深/浅色。
#
# 注意：为了让 Qt 认为窗口没有边框（resize()/move() 不产生偏差），
#       窗口以 Qt.FramelessWindowHint 创建，随后再把原生边框样式补回去。
#       这是本文件里唯一“非标准”的一步，所有 DWM 效果都由补回样式保证。

_IS_WINDOWS = sys.platform == "win32"

# ------------------------------- Win32 常量 -------------------------------
WM_NCCALCSIZE = 0x0083
WM_NCHITTEST = 0x0084
WM_NCACTIVATE = 0x0086
WM_NCMOUSEMOVE = 0x00A0
WM_NCLBUTTONDOWN = 0x00A1
WM_NCLBUTTONUP = 0x00A2
WM_NCLBUTTONDBLCLK = 0x00A3
WM_NCRBUTTONDOWN = 0x00A4
WM_NCRBUTTONUP = 0x00A5
WM_NCMOUSELEAVE = 0x02A2
WM_CONTEXTMENU = 0x007B
WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_RBUTTONDOWN = 0x0204
WM_KEYDOWN = 0x0100
WM_SYSKEYDOWN = 0x0104
WM_SETCURSOR = 0x0020
WM_CAPTURECHANGED = 0x0215
WM_CANCELMODE = 0x001F
WM_SYSCOMMAND = 0x0112
WM_SETTINGCHANGE = 0x001A
WM_GETMINMAXINFO = 0x0024
WM_SIZE = 0x0005
WM_STYLECHANGED = 0x007D

SC_MINIMIZE = 0xF020
SC_MAXIMIZE = 0xF030
SC_RESTORE = 0xF120
SC_KEYMENU = 0xF100
WM_CLOSE = 0x0010

VK_SPACE = 0x20
VK_ESCAPE = 0x1B

HTCLIENT = 1
HTCAPTION = 2
HTMINBUTTON = 8
HTMAXBUTTON = 9
HTCLOSE = 20
HTLEFT = 10
HTRIGHT = 11
HTTOP = 12
HTTOPLEFT = 13
HTTOPRIGHT = 14
HTBOTTOM = 15
HTBOTTOMLEFT = 16
HTBOTTOMRIGHT = 17

GWL_STYLE = -16
GWL_EXSTYLE = -20
WS_POPUP = 0x80000000
WS_OVERLAPPEDWINDOW = 0x00CF0000  # WS_OVERLAPPED|WS_CAPTION|WS_SYSMENU|WS_THICKFRAME|WS_MINIMIZEBOX|WS_MAXIMIZEBOX
WS_SYSMENU = 0x00080000
WS_MINIMIZEBOX = 0x00020000
WS_MAXIMIZEBOX = 0x00010000
WS_EX_APPWINDOW = 0x00040000
WS_EX_TOOLWINDOW = 0x00000080

SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020

SM_CXSIZEFRAME = 32
SM_CYSIZEFRAME = 33
SM_CXPADDEDBORDER = 92
SM_CXCURSOR = 13
SM_CYCURSOR = 14

# 系统光标资源（MAKEINTRESOURCE 编号）
IDC_ARROW = 32512
IDC_SIZEWE = 32644
IDC_SIZENS = 32645
IDC_SIZEALL = 32646

DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_USE_IMMERSIVE_DARK_MODE_OLD = 19
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWCP_ROUND = 2

TME_LEAVE = 0x00000002
TME_NONCLIENT = 0x00000010

QWIDGETSIZE_MAX = 16777215


class _NCCALCSIZE_PARAMS(ctypes.Structure):
    _fields_ = [("rgrc", wt.RECT * 3), ("lppos", ctypes.c_void_p)]


class _MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("rcMonitor", wt.RECT),
                ("rcWork", wt.RECT), ("dwFlags", wt.DWORD)]


class _MINMAXINFO(ctypes.Structure):
    _fields_ = [("ptReserved", wt.POINT), ("ptMaxSize", wt.POINT),
                ("ptMaxPosition", wt.POINT), ("ptMinTrackSize", wt.POINT),
                ("ptMaxTrackSize", wt.POINT)]


class _TRACKMOUSEEVENT(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("dwFlags", wt.DWORD),
                ("hwndTrack", wt.HWND), ("dwHoverTime", wt.DWORD)]


if _IS_WINDOWS:
    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)

    _user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
    _user32.GetWindowLongPtrW.argtypes = [wt.HWND, ctypes.c_int]
    _user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
    _user32.SetWindowLongPtrW.argtypes = [wt.HWND, ctypes.c_int, ctypes.c_ssize_t]
    _user32.SetWindowPos.restype = wt.BOOL
    _user32.SetWindowPos.argtypes = [wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int,
                                     ctypes.c_int, ctypes.c_int, wt.UINT]
    _user32.DefWindowProcW.restype = ctypes.c_ssize_t
    _user32.DefWindowProcW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
    _user32.IsZoomed.restype = wt.BOOL
    _user32.IsZoomed.argtypes = [wt.HWND]
    _user32.GetClientRect.restype = wt.BOOL
    _user32.GetClientRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
    _user32.ScreenToClient.restype = wt.BOOL
    _user32.ScreenToClient.argtypes = [wt.HWND, ctypes.POINTER(wt.POINT)]
    _user32.MonitorFromWindow.restype = wt.HANDLE
    _user32.MonitorFromWindow.argtypes = [wt.HWND, wt.DWORD]
    _user32.GetMonitorInfoW.restype = wt.BOOL
    _user32.GetMonitorInfoW.argtypes = [wt.HANDLE, ctypes.POINTER(_MONITORINFO)]
    _user32.TrackMouseEvent.restype = wt.BOOL
    _user32.TrackMouseEvent.argtypes = [ctypes.POINTER(_TRACKMOUSEEVENT)]
    _user32.GetSystemMetrics.restype = ctypes.c_int
    _user32.GetSystemMetrics.argtypes = [ctypes.c_int]
    _user32.SetCapture.restype = wt.HWND
    _user32.SetCapture.argtypes = [wt.HWND]
    _user32.ReleaseCapture.restype = wt.BOOL
    _user32.ReleaseCapture.argtypes = []
    _user32.GetCapture.restype = wt.HWND
    _user32.GetCapture.argtypes = []
    _user32.GetCursorPos.restype = wt.BOOL
    _user32.GetCursorPos.argtypes = [ctypes.POINTER(wt.POINT)]
    _user32.PostMessageW.restype = wt.BOOL
    _user32.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
    _user32.GetWindowRect.restype = wt.BOOL
    _user32.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
    _user32.SetCursorPos.restype = wt.BOOL
    _user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
    _user32.SetCursor.restype = wt.HANDLE
    _user32.SetCursor.argtypes = [wt.HANDLE]
    _user32.LoadCursorW.restype = wt.HANDLE
    _user32.LoadCursorW.argtypes = [wt.HINSTANCE, ctypes.c_void_p]
    _dwmapi.DwmSetWindowAttribute.restype = ctypes.c_long
    _dwmapi.DwmSetWindowAttribute.argtypes = [wt.HWND, wt.DWORD, ctypes.c_void_p, wt.DWORD]

    try:  # Windows 10 1607+
        _user32.GetDpiForWindow.restype = wt.UINT
        _user32.GetDpiForWindow.argtypes = [wt.HWND]
        _user32.GetSystemMetricsForDpi.restype = ctypes.c_int
        _user32.GetSystemMetricsForDpi.argtypes = [ctypes.c_int, wt.UINT]
        _HAS_DPI_API = True
    except AttributeError:
        _HAS_DPI_API = False
else:
    _user32 = None
    _dwmapi = None
    _HAS_DPI_API = False


def _signed_lparam(lparam):
    """把 lParam 拆成屏幕坐标 (x, y)（考虑 16 位有符号）。"""
    lparam = int(lparam) & 0xFFFFFFFF
    x = lparam & 0xFFFF
    y = (lparam >> 16) & 0xFFFF
    if x >= 0x8000:
        x -= 0x10000
    if y >= 0x8000:
        y -= 0x10000
    return x, y


def _screen_point(lparam):
    x, y = _signed_lparam(lparam)
    return wt.POINT(x, y)


def _system_metrics_for_dpi(hwnd, index):
    """按窗口所在显示器的 DPI 取系统尺寸，保证 125%/150% 缩放下边框比例正确。"""
    dpi = 96
    if _HAS_DPI_API:
        try:
            dpi = _user32.GetDpiForWindow(hwnd) or 96
        except OSError:
            dpi = 96
    if _HAS_DPI_API:
        try:
            return _user32.GetSystemMetricsForDpi(index, dpi)
        except OSError:
            pass
    return _user32.GetSystemMetrics(index)


def _resize_border_size(hwnd):
    """返回 (左右, 上下) 的可缩放边框厚度（物理像素）。"""
    fx = (_system_metrics_for_dpi(hwnd, SM_CXSIZEFRAME)
          + _system_metrics_for_dpi(hwnd, SM_CXPADDEDBORDER))
    fy = (_system_metrics_for_dpi(hwnd, SM_CYSIZEFRAME)
          + _system_metrics_for_dpi(hwnd, SM_CXPADDEDBORDER))
    return max(fx, 1), max(fy, 1)


def _window_rect(hwnd):
    """窗口物理矩形（屏幕坐标）；失败返回 None。"""
    if not _IS_WINDOWS:
        return None
    rect = wt.RECT()
    try:
        if not _user32.GetWindowRect(wt.HWND(hwnd), ctypes.byref(rect)):
            return None
    except OSError:
        return None
    return rect


_CURSOR_CACHE = {}


def _system_cursor(cursor_id):
    """加载（并缓存）系统光标句柄；失败返回 None。"""
    if not _IS_WINDOWS:
        return None
    if cursor_id in _CURSOR_CACHE:
        return _CURSOR_CACHE[cursor_id]
    handle = None
    try:
        # MAKEINTRESOURCE：整数资源编号按 LPWSTR 指针传入
        handle = _user32.LoadCursorW(None, ctypes.c_void_p(cursor_id))
    except OSError:
        handle = None
    _CURSOR_CACHE[cursor_id] = handle
    return handle


def _dwm_set_int(hwnd, attribute, value):
    """DwmSetWindowAttribute 的 int 版本；旧系统不支持时静默失败。"""
    if not _IS_WINDOWS:
        return False
    data = ctypes.c_int(value)
    try:
        hr = _dwmapi.DwmSetWindowAttribute(
            wt.HWND(hwnd), attribute, ctypes.byref(data), ctypes.sizeof(data))
    except OSError:
        return False
    return hr == 0


def _apply_dwm_effects(hwnd, dark: bool, rounded: bool = True):
    """把 Win11 的深色标题栏与圆角交给 DWM（阴影/动画本来就是 DWM 的默认行为）。"""
    if not _IS_WINDOWS:
        return
    if not _dwm_set_int(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, 1 if dark else 0):
        # Windows 10 1903 ~ 20H1 之间的属性编号是 19
        _dwm_set_int(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE_OLD, 1 if dark else 0)
    if rounded:
        _dwm_set_int(hwnd, DWMWA_WINDOW_CORNER_PREFERENCE, DWMWCP_ROUND)


def _inject_native_frame_styles(hwnd):
    """把 Qt 的无边框窗口“变成”普通带边框窗口。

    Qt 创建 FramelessWindowHint 窗口时会用 WS_POPUP；这里补回
    WS_OVERLAPPEDWINDOW，DWM 才会给窗口阴影、动画和贴靠行为。
    WM_NCCALCSIZE 会把新增的非客户区全部算进客户区，所以视觉上依旧无边框。
    """
    if not _IS_WINDOWS:
        return
    style = _user32.GetWindowLongPtrW(wt.HWND(hwnd), GWL_STYLE)
    style = (style & ~(WS_POPUP | WS_OVERLAPPEDWINDOW)) | WS_OVERLAPPEDWINDOW
    _user32.SetWindowLongPtrW(wt.HWND(hwnd), GWL_STYLE, style)

    ex_style = _user32.GetWindowLongPtrW(wt.HWND(hwnd), GWL_EXSTYLE)
    ex_style = (ex_style | WS_EX_APPWINDOW) & ~WS_EX_TOOLWINDOW
    _user32.SetWindowLongPtrW(wt.HWND(hwnd), GWL_EXSTYLE, ex_style)

    # 让 Windows 重新计算窗口边框（不改变位置和大小）
    _user32.SetWindowPos(wt.HWND(hwnd), wt.HWND(0), 0, 0, 0, 0,
                         SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER
                         | SWP_NOACTIVATE | SWP_FRAMECHANGED)


def _monitor_work_area(hwnd):
    """窗口所在显示器的工作区（物理像素，已排除任务栏）。"""
    monitor = _user32.MonitorFromWindow(wt.HWND(hwnd), 2)  # MONITOR_DEFAULTTONEAREST
    info = _MONITORINFO()
    info.cbSize = ctypes.sizeof(_MONITORINFO)
    if not _user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        return None
    return info.rcWork


def system_is_dark() -> bool:
    """当前 Windows 系统是深色模式吗？（“个性化 → 颜色 → 应用模式”）"""
    if not _IS_WINDOWS:
        return False
    try:
        import winreg
    except ImportError:
        return False
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
        try:
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        finally:
            key.Close()
        return int(value) == 0
    except OSError:
        return False


# =============================================================================
# 标题栏主题（Windows 11 视觉规范）
# =============================================================================

_TITLEBAR_LIGHT = dict(
    bar="#F3F3F3",
    title="#1A1A1A",
    title_inactive="#6B6B6B",
    caption="#1A1A1A",
    caption_inactive="#8A8A8A",
    caption_hover="#E9E9E9",
    caption_pressed="#DBDBDB",
    close_hover="#C42B1C",
    close_pressed="#B01F14",
)

_TITLEBAR_DARK = dict(
    bar="#202020",
    title="#FFFFFF",
    title_inactive="#9A9A9A",
    caption="#FFFFFF",
    caption_inactive="#9A9A9A",
    caption_hover="#333333",
    caption_pressed="#454545",
    close_hover="#C42B1C",
    close_pressed="#B01F14",
)


def _titlebar_stylesheet(dark: bool = True, subtitle_color=None) -> str:
    c = _TITLEBAR_DARK if dark else _TITLEBAR_LIGHT
    subtitle = QColor(subtitle_color or "#cccccc").name()
    return f"""
QWidget#TitleBar {{
    background-color: {c['bar']};
}}
QLabel#TitleBarTitle {{
    color: {c['title']};
    background: transparent;
    font-size: 12px;
}}
QLabel#TitleBarTitle[active="false"] {{
    color: {c['title_inactive']};
}}
QLabel#TitleBarSubtitle {{
    color: {subtitle};
    background: transparent;
    font-size: 12px;
}}
QLabel#TitleBarSubtitle[active="false"] {{
    color: {subtitle};
}}
QLabel#CaptionButton {{
    background: transparent;
    color: {c['caption']};
}}
QLabel#CaptionButton[windowActive="false"] {{
    color: {c['caption_inactive']};
}}
QLabel#CaptionButton[captionState="hover"] {{
    background-color: {c['caption_hover']};
}}
QLabel#CaptionButton[captionState="pressed"] {{
    background-color: {c['caption_pressed']};
}}
/* 关闭按钮：悬停变红、图标变白（Windows 11 行为） */
QLabel#CaptionButton[captionRole="close"] {{
    color: {c['caption']};
}}
QLabel#CaptionButton[captionRole="close"][captionState="hover"] {{
    background-color: {c['close_hover']};
    color: #FFFFFF;
}}
QLabel#CaptionButton[captionRole="close"][captionState="pressed"] {{
    background-color: {c['close_pressed']};
    color: #FFFFFF;
}}
"""


def _repolish(widget):
    """动态属性改变后强制刷新 qss。"""
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


# =============================================================================
# 标题栏控件
# =============================================================================

_CAPTION_GLYPHS = {
    "minimize": "\uE921",
    "maximize": "\uE922",
    "restore": "\uE923",
    "close": "\uE8BB",
}

_CAPTION_ACCESSIBLE_NAMES = {
    "minimize": "最小化",
    "maximize": "最大化",
    "close": "关闭",
}

#: 标题栏默认高度（逻辑像素）。``TitleBar.HEIGHT`` 保留这个值，
#: 子类/老代码仍可覆盖类属性；实例高度请用构造参数 ``height=``。
_DEFAULT_TITLEBAR_HEIGHT = 48

#: 标题栏按钮宽度（逻辑像素）；按钮高度始终等于标题栏高度。
_CAPTION_BUTTON_WIDTH = 48

#: 标题栏 GAP 规格（逻辑像素）。
_TITLEBAR_LEADING = 12
_TITLEBAR_NAV_GAP = 16
_TITLEBAR_ICON_GAP = 16
_TITLEBAR_TITLE_GAP = 8
_TITLEBAR_SUBTITLE_GAP = 8
_TITLEBAR_CONTROLS_GAP = 48
_TITLEBAR_NAV_BUTTON_W = 40
_TITLEBAR_NAV_BUTTON_H = 48
_TITLEBAR_NAV_LEFT_MARGIN = 4
_TITLEBAR_NAV_ITEM_GAP = 4


class CaptionButton(FontIcon):
    """标题栏按钮（最小化 / 最大化 / 关闭）。

    默认（native_caption=True）由 Windows 非客户区命中测试接管：
    鼠标事件不会到达 Qt，按钮只负责画图标和悬停/按下背景。
    若标题栏使用 native_caption=False，则按钮自己处理鼠标事件，
    并发出 clicked 信号。

    按钮高度由标题栏高度决定（见 ``height`` 参数），保证点击/悬停区域
    与视觉上的按钮完全一致。
    """

    hovered = Signal(bool)
    pressed = Signal(bool)
    clicked = Signal()

    def __init__(self, role: str, parent=None, *,
                 height: int = _DEFAULT_TITLEBAR_HEIGHT):
        super().__init__(_CAPTION_GLYPHS[role], size=10, parent=parent)
        self._role = role
        self._height = max(1, int(height))
        self._caption_state = "normal"
        self.setObjectName("CaptionButton")
        self.setProperty("captionRole", role)
        self.setProperty("captionState", "normal")
        self.setProperty("windowActive", True)
        self.setAccessibleName(_CAPTION_ACCESSIBLE_NAMES[role])
        # Windows 11 标题栏按钮：宽度固定（_CAPTION_BUTTON_WIDTH），高度铺满标题栏
        self.setFixedSize(_CAPTION_BUTTON_WIDTH, self._height)
        self.setAlignment(Qt.AlignCenter)
        self.setFocusPolicy(Qt.NoFocus)
        self.setCursor(Qt.ArrowCursor)
        # 原生模式下鼠标事件由 Windows 非客户区命中测试接管；
        # Qt 交互模式下会由 set_qt_interactive(True) 打开。
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)

    # ---------------------------------------------------------------- 状态
    def role(self) -> str:
        return self._role

    def caption_height(self) -> int:
        """按钮当前高度（逻辑像素），始终等于标题栏高度。"""
        return self._height

    def set_caption_height(self, height: int):
        """跟随标题栏高度变化（按钮即命中区域，二者必须同步）。"""
        height = max(1, int(height))
        if height == self._height:
            return
        self._height = height
        self.setFixedSize(_CAPTION_BUTTON_WIDTH, height)

    def set_qt_interactive(self, enabled: bool):
        """切换成 Qt 交互模式（标题栏 native_caption=False 时使用）。"""
        self.setAttribute(Qt.WA_TransparentForMouseEvents, not enabled)
        if enabled:
            self.setAttribute(Qt.WA_Hover, True)
            self.setMouseTracking(True)

    def set_caption_state(self, state: str):
        state = state if state in ("hover", "pressed") else "normal"
        if state == self._caption_state:
            return
        self._caption_state = state
        self.setProperty("captionState", state)
        _repolish(self)

    def set_window_active(self, active: bool):
        if bool(self.property("windowActive")) == active:
            return
        self.setProperty("windowActive", active)
        _repolish(self)

    def set_glyph(self, glyph: str):
        if self.text() != glyph:
            self.setText(glyph)

    # ---------------------------------------------------- Qt 交互模式（可选）
    def enterEvent(self, event):
        self.hovered.emit(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.hovered.emit(False)
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.pressed.emit(True)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            inside = self.rect().contains(event.position().toPoint())
            self.pressed.emit(False)
            if inside:
                self.clicked.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)


class _TitleLabel(QLabel):
    """会自动省略末尾的标题文本（窗口变窄时显示 …）。"""

    def __init__(self, text: str = "", parent=None,
                 object_name: str = "TitleBarTitle"):
        super().__init__(parent)
        self._full_text = ""
        self.setObjectName(object_name)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        self.setMinimumWidth(0)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.set_full_text(text)

    def set_full_text(self, text: str):
        self._full_text = text or ""
        self._update_elide()

    def full_text(self) -> str:
        return self._full_text

    def sizeHint(self) -> QSize:
        """按完整文本给出尺寸提示，实际显示时再按可用宽度省略。"""
        metrics = QFontMetrics(self.font())
        return QSize(metrics.horizontalAdvance(self._full_text),
                     metrics.height())

    def minimumSizeHint(self) -> QSize:
        metrics = QFontMetrics(self.font())
        return QSize(0, metrics.height())

    def _update_elide(self):
        available = max(0, self.width())
        metrics = self.fontMetrics()
        elided = metrics.elidedText(self._full_text, Qt.ElideRight, available)
        if elided != self.text():
            super().setText(elided)
        self.setToolTip(self._full_text if elided != self._full_text else "")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_elide()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() in (QEvent.FontChange, QEvent.StyleChange):
            self.updateGeometry()
            self._update_elide()


class _TitleBarGap(QWidget):
    """标题栏 GAP 占位控件：固定宽度、鼠标穿透、可随相邻元素隐藏。"""

    def __init__(self, width: int, parent=None):
        super().__init__(parent)
        self.setFixedWidth(max(0, int(width)))
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)


# =============================================================================
# Qt 自绘系统菜单（Windows 11 风格）
# =============================================================================

#: 菜单主题（无深色适配）
_MENU_BG = "#F9F9F9"
_MENU_BORDER = "#E8E8E8"
_MENU_SEPARATOR = "#E2E2E2"
_MENU_TEXT = "#000000"
_MENU_HOVER_BG = "#F0F0F0"
_MENU_DISABLED_TEXT = "#ABABAB"
_MENU_FONT_PX = 12
_MENU_ICON_PX = 8
#: 固定菜单宽度（逻辑像素，按 96 DPI 设计）；可见面板宽度
_MENU_PANEL_WIDTH = 200
_MENU_RADIUS = 4
_MENU_OUTER_MARGIN = 8
#: 行内容/悬停高亮/分割线相对面板左右边缘的留白
_MENU_CONTENT_INSET = 8
#: fonticon 左边缘距面板左侧；描述文字左边缘距面板左侧
_MENU_ICON_LEFT = 16
_MENU_ICON_SLOT = 16
_MENU_TEXT_LEFT = 32
#: 右侧 Alt+F4 距面板右边缘
_MENU_SHORTCUT_RIGHT = 16
_MENU_ITEM_V_MARGIN = 4
_MENU_SEPARATOR_H = 1
_MENU_SHORTCUT_GAP = 16
_MENU_FADE_MS = 250
_MENU_SPACE_GAP = 16
#: 双击图标“第二次按下”的位置容差（逻辑像素）
_ICON_DOUBLE_CLICK_SLOP = 8

_MENU_SEPARATOR_KEY = "separator"


def _system_menu_position(anchor: QPoint, panel_size: QSize,
                          available: QRect, full: QRect, *,
                          margin: int = _MENU_OUTER_MARGIN,
                          gap: int = _MENU_SPACE_GAP) -> QPoint:
    """计算系统菜单弹窗左上角（Qt 逻辑坐标）。

    * 默认：可见面板左上角对准 ``anchor``；
    * 下方空间不足（离任务栏/显示器下边界 < ``gap``）：可见面板左下角对准
      ``anchor``（菜单向上展开）；
    * 水平超出工作区 / 翻转后超出屏幕顶部时贴边。
    """
    popup_w = panel_size.width() + 2 * margin
    popup_h = panel_size.height() + 2 * margin

    x = anchor.x() - margin
    y = anchor.y() - margin

    # 任务栏可见时用工作区下边界；自动隐藏/无任务栏时用显示器下边界
    boundary = (available.bottom() if available.bottom() < full.bottom()
                else full.bottom())
    if boundary - (anchor.y() + panel_size.height()) < gap:
        y = anchor.y() - panel_size.height() - margin

    # 水平贴边
    if x + popup_w > available.right() + 1:
        x = available.right() + 1 - popup_w
    if x < available.left():
        x = available.left()

    # 垂直贴边（翻转后可能超出屏幕顶部）
    if y < available.top():
        y = available.top()
    if y + popup_h > full.bottom() + 1:
        y = full.bottom() + 1 - popup_h
    return QPoint(x, y)


class _SystemMenuItem:
    """菜单项数据（纯数据 + 弹窗本地矩形）。"""

    __slots__ = ("key", "text", "glyph", "shortcut", "enabled",
                 "separator", "rect")

    def __init__(self, key, text, glyph="", shortcut="", *,
                 enabled=True, separator=False):
        self.key = key
        self.text = text
        self.glyph = glyph
        self.shortcut = shortcut
        self.enabled = bool(enabled)
        self.separator = bool(separator)
        self.rect = QRect()

    @classmethod
    def make_separator(cls):
        return cls(_MENU_SEPARATOR_KEY, "", separator=True)


class SystemMenu(QWidget):
    """Qt 自绘系统菜单（还原/移动/大小/最小化/最大化/关闭）。

    由 ``TitleBar.show_system_menu()`` 创建和弹出；也可单独实例化用于测试。
    可见面板固定 200px 宽（96 DPI 逻辑像素）、4px 圆角；行高随字体自适应。
    弹窗自身负责：定位、渐显（125ms，无渐隐）、悬停/按下、圆角阴影绘制、
    点击任意位置关闭（Qt::Popup 的全局鼠标抓取 + WA_NoMouseReplay）。
    """

    actionTriggered = Signal(str)
    iconDoubleClicked = Signal()

    def __init__(self, window=None, parent=None):
        super().__init__(parent)
        self._window = window
        self._items = []
        self._panel_size = QSize(_MENU_PANEL_WIDTH, 1)
        self._text_x = _MENU_OUTER_MARGIN + _MENU_TEXT_LEFT
        self._icon_x = _MENU_OUTER_MARGIN + _MENU_ICON_LEFT
        self._shortcut_right = (_MENU_OUTER_MARGIN + _MENU_PANEL_WIDTH
                                - _MENU_SHORTCUT_RIGHT)
        self._hover_index = -1
        self._pressed_index = -1
        self._has_press = False

        # 双击图标关闭：只对“左键图标打开”的菜单生效
        self._allow_icon_double_click = False
        self._icon_anchor = QPoint()
        self._opened_timer = QElapsedTimer()

        self._fade_anim = None

        self._label_font = QFont(self.font())
        self._label_font.setPixelSize(_MENU_FONT_PX)
        self._label_font.setWeight(QFont.Normal)
        self._bold_font = QFont(self._label_font)
        self._bold_font.setWeight(QFont.Bold)
        self._icon_font = QFont()
        self._icon_font.setFamilies(_FONT_FAMILIES)
        self._icon_font.setPixelSize(_MENU_ICON_PX)
        self._icon_font.setWeight(QFont.Normal)

        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint
                            | Qt.NoDropShadowWindowHint
                            | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_NoMouseReplay, True)
        self.setFocusPolicy(Qt.NoFocus)
        self.setMouseTracking(True)

    # ------------------------------------------------------------------ 构建
    def _rebuild(self, maximized: bool, supports_hints: bool):
        glyphs = _CAPTION_GLYPHS
        self._items = [
            _SystemMenuItem("restore", "还原(R)", glyphs["restore"],
                            enabled=maximized),
            _SystemMenuItem("move", "移动(M)",
                            enabled=(not maximized and supports_hints)),
            _SystemMenuItem("size", "大小(S)",
                            enabled=(not maximized and supports_hints)),
            _SystemMenuItem("minimize", "最小化(N)", glyphs["minimize"]),
            _SystemMenuItem("maximize", "最大化(X)", glyphs["maximize"],
                            enabled=not maximized),
            _SystemMenuItem.make_separator(),
            _SystemMenuItem("close", "关闭(C)", glyphs["close"], "Alt+F4"),
        ]
        self._layout_items()
        self._hover_index = -1
        self._pressed_index = -1
        self._has_press = False

    def _layout_items(self):
        label_fm = QFontMetrics(self._label_font)
        icon_fm = QFontMetrics(self._icon_font)
        row_h = max(label_fm.height(), icon_fm.height()) + 2 * _MENU_ITEM_V_MARGIN

        # 宽度固定（按 96 DPI 设计），高度按行数自适应
        panel_w = _MENU_PANEL_WIDTH
        panel_h = 0
        for item in self._items:
            panel_h += (_MENU_SEPARATOR_H if item.separator else row_h)

        # 放置每行（弹窗本地坐标，含 8px 阴影外边距）
        y = _MENU_OUTER_MARGIN
        for item in self._items:
            if item.separator:
                item.rect = QRect(_MENU_OUTER_MARGIN, y, panel_w,
                                  _MENU_SEPARATOR_H)
                y += _MENU_SEPARATOR_H
            else:
                item.rect = QRect(_MENU_OUTER_MARGIN, y, panel_w, row_h)
                y += row_h

        self._panel_size = QSize(panel_w, panel_h)
        self._text_x = _MENU_OUTER_MARGIN + _MENU_TEXT_LEFT
        self._icon_x = _MENU_OUTER_MARGIN + _MENU_ICON_LEFT
        self._shortcut_right = (_MENU_OUTER_MARGIN + panel_w
                                - _MENU_SHORTCUT_RIGHT)
        self.resize(panel_w + 2 * _MENU_OUTER_MARGIN,
                    panel_h + 2 * _MENU_OUTER_MARGIN)

    # ------------------------------------------------------------------ 弹出
    def panel_size(self) -> QSize:
        """可见面板尺寸（不含 8px 阴影外边距）。"""
        return QSize(self._panel_size)

    def popup_at(self, anchor: QPoint, *, icon_press: bool = False):
        window = self._window
        if window is None:
            return
        try:
            maximized = bool(window.isMaximized())
        except RuntimeError:
            return
        helper = getattr(window, "_frame_helper", None)
        self._rebuild(maximized, _IS_WINDOWS and helper is not None)

        anchor = QPoint(anchor)
        self._allow_icon_double_click = bool(icon_press)
        self._icon_anchor = QPoint(anchor)
        self._opened_timer.start()

        try:
            screen = QGuiApplication.screenAt(anchor) or self._window.screen()
        except RuntimeError:
            screen = QGuiApplication.primaryScreen()
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        pos = _system_menu_position(anchor, self._panel_size,
                                    screen.availableGeometry(),
                                    screen.geometry())
        self.setGeometry(QRect(pos, self.size()))
        self.setWindowOpacity(0.0)
        self.show()
        self.raise_()
        self._start_fade()
        self.update()

    def _start_fade(self):
        self._fade_anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade_anim.setDuration(_MENU_FADE_MS)
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._fade_anim.start()

    def hideEvent(self, event):
        if self._fade_anim is not None:
            self._fade_anim.stop()
            self._fade_anim = None
        self.setWindowOpacity(1.0)
        self._hover_index = -1
        self._pressed_index = -1
        self._has_press = False
        self._allow_icon_double_click = False
        super().hideEvent(event)

    # ------------------------------------------------------------------ 交互
    def _item_at(self, point: QPoint) -> int:
        for index, item in enumerate(self._items):
            if item.separator:
                continue
            if item.rect.contains(point):
                return index
        return -1

    def mouseMoveEvent(self, event):
        index = self._item_at(event.position().toPoint())
        if index != self._hover_index:
            self._hover_index = index
            self.update()
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event):
        # 双击图标关闭：第二次按下落在菜单窗口上（位置/时间都匹配）时关窗
        if (event.button() == Qt.LeftButton
                and self._allow_icon_double_click
                and self._opened_timer.isValid()
                and self._opened_timer.elapsed() <= QApplication.doubleClickInterval()
                and (event.globalPosition().toPoint() - self._icon_anchor)
                .manhattanLength() <= _ICON_DOUBLE_CLICK_SLOP):
            self._allow_icon_double_click = False
            self.hide()
            self.iconDoubleClicked.emit()
            event.accept()
            return

        if event.button() == Qt.RightButton:
            # 菜单里右键也视为“点击任一地方消除”
            self.hide()
            event.accept()
            return

        if event.button() == Qt.LeftButton:
            self._pressed_index = self._item_at(event.position().toPoint())
            self._has_press = True
            self.update()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._has_press:
            self._has_press = False
            index = self._item_at(event.position().toPoint())
            if index == self._pressed_index and index >= 0:
                item = self._items[index]
                if item.enabled:
                    self.hide()
                    self.actionTriggered.emit(item.key)
                    event.accept()
                    return
            self.hide()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def leaveEvent(self, event):
        if self._hover_index != -1:
            self._hover_index = -1
            self.update()
        super().leaveEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.hide()
            event.accept()
            return
        super().keyPressEvent(event)

    # ------------------------------------------------------------------ 绘制
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)

        margin = _MENU_OUTER_MARGIN
        panel = QRectF(self.rect()).adjusted(margin, margin, -margin, -margin)
        path = QPainterPath()
        path.addRoundedRect(panel, _MENU_RADIUS, _MENU_RADIUS)

        self._paint_shadow(painter, panel)
        painter.fillPath(path, QColor(_MENU_BG))

        painter.save()
        painter.setClipPath(path)

        for index, item in enumerate(self._items):
            if item.separator:
                y = item.rect.top() + 0.5
                painter.setPen(QPen(QColor(_MENU_SEPARATOR), 1))
                painter.drawLine(
                    QPointF(panel.left() + _MENU_CONTENT_INSET, y),
                    QPointF(panel.right() - _MENU_CONTENT_INSET, y))
                continue

            if index in (self._hover_index, self._pressed_index):
                hover_rect = QRectF(item.rect).adjusted(
                    _MENU_CONTENT_INSET, 0, -_MENU_CONTENT_INSET, 0)
                painter.fillRect(hover_rect, QColor(_MENU_HOVER_BG))

            color = QColor(_MENU_TEXT if item.enabled else _MENU_DISABLED_TEXT)
            content_h = item.rect.height() - 2 * _MENU_ITEM_V_MARGIN
            is_close = item.key == "close"

            if item.glyph:
                painter.setFont(self._icon_font)
                painter.setPen(color)
                painter.drawText(
                    QRectF(self._icon_x, item.rect.top() + _MENU_ITEM_V_MARGIN,
                           _MENU_ICON_SLOT, content_h),
                    Qt.AlignLeft | Qt.AlignVCenter, item.glyph)

            text_font = self._bold_font if is_close else self._label_font
            painter.setFont(text_font)
            painter.setPen(color)
            text_rect = QRectF(self._text_x, item.rect.top(),
                               max(0.0, self._shortcut_right - self._text_x),
                               item.rect.height())
            if item.shortcut:
                shortcut_w = QFontMetrics(self._bold_font).horizontalAdvance(
                    item.shortcut)
                text_rect.setWidth(max(0.0, text_rect.width()
                                       - shortcut_w - _MENU_SHORTCUT_GAP))
                shortcut_rect = QRectF(self._shortcut_right - shortcut_w,
                                       item.rect.top(), shortcut_w,
                                       item.rect.height())
                painter.setFont(self._bold_font)
                painter.drawText(shortcut_rect,
                                 Qt.AlignRight | Qt.AlignVCenter, item.shortcut)
                painter.setFont(text_font)
            painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter,
                             item.text)

        painter.restore()

        # 边框画在 panel 内侧半像素处，保证 1px 在 100% 缩放下不糊
        painter.setPen(QPen(QColor(_MENU_BORDER), 1))
        painter.setBrush(Qt.NoBrush)
        border_rect = panel.adjusted(0.5, 0.5, -0.5, -0.5)
        border_path = QPainterPath()
        border_path.addRoundedRect(border_rect, _MENU_RADIUS - 0.5,
                                   _MENU_RADIUS - 0.5)
        painter.drawPath(border_path)

    @staticmethod
    def _paint_shadow(painter: QPainter, panel: QRectF):
        """在 8px 透明外边距内画柔和阴影（不依赖 QGraphicsEffect）。"""
        for step in range(5, 0, -1):
            alpha = 6 + (5 - step) * 4
            rect = panel.adjusted(-step, -step + 2, step, step + 2)
            shadow_path = QPainterPath()
            shadow_path.addRoundedRect(rect, _MENU_RADIUS + step,
                                       _MENU_RADIUS + step)
            painter.fillPath(shadow_path, QColor(0, 0, 0, alpha))


class TitleBar(QWidget):
    """Windows 11 风格标题栏：图标 + 标题 + 最小化/最大化/关闭。

    通常不需要手动创建，直接继承 ``TitleBarWindow`` / ``TitleBarMainWindow``
    即可；也可以把它放进 ``TitleBarMainWindow.setMenuWidget()`` 之类的位置。

    参数
    ----
    window:
        所属顶层窗口。Qt 交互模式下按钮要调用窗口的最小化/最大化/关闭。
    title:
        窗口标题，过长会自动省略。
    icon:
        标题左侧的 16x16 图标；传 None 则不显示图标。
    height:
        标题栏高度（逻辑像素），None（默认）表示使用类属性 ``HEIGHT``。
        三个标题栏按钮的高度、非客户区命中测试区域都会跟着变，
        不会出现“栏变高了、按钮碰撞箱还是旧值”的问题。
    native_caption:
        True（默认）时使用 Windows 原生非客户区命中测试：悬停高亮、
        Windows 11 贴靠布局悬浮面板都由系统提供，点击由组件转换成
        WM_SYSCOMMAND（动画仍是 DWM 原生）。False 时按钮由 Qt 处理，
        没有贴靠布局悬浮面板。
    dark:
        深/浅色主题；None 表示跟随系统。

    自定义控件
    --------
    标题栏里放置的按钮/输入框等控件默认会被当作“拖动区”。
    需要响应鼠标的控件请设置 ``widget.setProperty("titlebarInteractive", True)``，
    命中测试会把该区域交回 Qt。

    标题区 / 自定义区
    ----------------
    * ``setTitle`` / ``setSubTitle`` / ``setIcon``：主标题、副标题、图标；
      传 None 隐藏对应元素（连同其后的 GAP 一起隐藏）。
    * ``setLayout(layout)``：设置标题区与控制区之间的自定义区；支持 QLayout、
      QWidget 或 None。注意该方法的语义是“自定义区布局”，不会替换 TitleBar
      自身的根布局。
    * ``removeTitleArea()``：删除图标/标题/副标题，自定义区左拉长；此后双击
      图标关闭窗口、左键图标弹菜单失效，标题栏右键系统菜单保留。
    * ``setControlHeight(0|正整数)``：右侧最小化/最大化/关闭按钮的高度；
      0 跟随 TitleBar，正整数固定高度（顶部对齐，超出裁剪），负数报错。
    * ``initNavigationView(nav, move_animate_button=True)``：把 NavigationView
      自动加入窗口内容区；``move_animate_button=True`` 时把返回/汉堡按钮迁移到
      TitleBar（固定 40×48），并在内容卡片上启用深色底与左上圆角。

    标题栏背景可由 ``set_glass()`` 保持透明玻璃；不调用时使用 QSS 配色。
    系统菜单
    --------
    左键按下应用图标、右键按下标题栏（CaptionButton 区域除外）或按
    ``Alt+Space`` 会弹出 Qt 自绘的系统菜单（``SystemMenu``）：
    还原/移动/大小/最小化/最大化/关闭。``移动``/``大小`` 由
    ``WindowsFrameHelper.begin_system_menu_hint()`` 实现；关闭窗口用
    ``window.close()``。也可以手动调用 ``show_system_menu()``。
    """

    HEIGHT = _DEFAULT_TITLEBAR_HEIGHT

    #: 深/浅色主题变化时发出（跟随系统主题切换时也会发出），
    #: 方便把窗口内容区一起换色。
    themeChanged = Signal(bool)

    #: 标题栏高度变化时发出（参数为新高度，逻辑像素）。
    heightChanged = Signal(int)

    def get_subtitle_color(self) -> QColor:
        return getattr(self, "_subtitle_color", QColor("#cccccc"))

    def set_subtitle_color(self, color):
        color = QColor(color)
        if color == getattr(self, "_subtitle_color", None):
            return
        self._subtitle_color = color
        self._apply_titlebar_stylesheet()

    subtitleColor = Property(QColor, get_subtitle_color, set_subtitle_color)

    def __init__(self, window=None, title: str = "", icon: Optional[QIcon] = None,
                 *, height: Optional[int] = None, native_caption: bool = True,
                 dark: Optional[bool] = None, parent=None):
        super().__init__(parent)
        self._window = window
        # 实例高度：显式 height 参数优先，否则取类属性 HEIGHT（子类可覆盖）。
        # 必须在 _build_layout() 之前确定，按钮会按它定尺寸。
        self._height = self._resolve_height(height)
        self._native_caption = bool(native_caption)
        self._dark = system_is_dark() if dark is None else bool(dark)
        self._active = True
        self._maximized = False
        self._hover_role = None
        self._pressed_role = None
        #: 右侧控制按钮高度：0 = 跟随 TitleBar。
        self._control_height = 0
        #: 副标题颜色（QProperty，QSS: qproperty-subtitleColor）。
        self._subtitle_color = QColor("#cccccc")
        self._applying_style = False
        #: 标题区是否已被 removeTitleArea() 移除。
        self._title_area_removed = False
        #: 自定义区 host（由 setLayout() 替换）。
        self._custom_host: QWidget | None = None
        #: NavigationView 集成。
        self._nav_view = None
        self._nav_buttons: list[AnimatedIconButton] = []
        self._nav_cluster: QWidget | None = None
        #: 惰性创建的自绘系统菜单
        self._system_menu = None
        self._icon_close_in_progress = False
        #: 可选玻璃背景：由内容区（如 NavigationView）的 backdrop 提供采样源，
        #: 见 set_glass()。为 None 时保持 QSS 纯色标题栏。
        self._glass_backdrop = None
        self._glass_style = None
        self._glass_window: Optional[QWidget] = None

        self.setObjectName("TitleBar")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedHeight(self._height)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFocusPolicy(Qt.NoFocus)

        self._icon = None
        self._build_layout()
        self.set_icon(icon)
        self.set_title(title)
        self.set_dark(self._dark)
        self.set_active(True)
        self.set_maximized(False)

        if not self._native_caption:
            for button in self._buttons.values():
                button.set_qt_interactive(True)

    @classmethod
    def _resolve_height(cls, height: Optional[int]) -> int:
        value = cls.HEIGHT if height is None else int(height)
        if value <= 0:
            raise ValueError("TitleBar height must be positive integer.")
        return value

    # ------------------------------------------------------------------ 构建
    def _build_layout(self):
        self._buttons = {}
        root = QHBoxLayout()
        # 用 QWidget.setLayout 显式安装根布局，避免与公共的
        # TitleBar.setLayout(layout)（设置自定义区）冲突。
        QWidget.setLayout(self, root)
        self._main_layout = root
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 无导航按钮时的 12px 起始留白。
        self._leading_gap = _TitleBarGap(_TITLEBAR_LEADING, self)
        root.addWidget(self._leading_gap)

        # 移动进来的返回 / 汉堡按钮容器。
        self._nav_cluster = QWidget(self)
        self._nav_cluster.setAutoFillBackground(False)
        self._nav_cluster.hide()
        root.addWidget(self._nav_cluster)

        self._nav_gap = _TitleBarGap(_TITLEBAR_NAV_GAP, self)
        self._nav_gap.hide()
        root.addWidget(self._nav_gap)

        # 标题区：图标 16 → 标题 → 8 → 副标题 → 8。
        self._title_area = QWidget(self)
        self._title_area.setAutoFillBackground(False)
        title_layout = QHBoxLayout(self._title_area)
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(0)

        self._icon_label = QLabel(self._title_area)
        self._icon_label.setObjectName("TitleBarIcon")
        self._icon_label.setFixedSize(16, 16)
        self._icon_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._icon_label.hide()

        self._gap_icon_title = _TitleBarGap(_TITLEBAR_ICON_GAP, self._title_area)
        self._gap_icon_title.hide()

        self._title_label = _TitleLabel("", self._title_area, "TitleBarTitle")

        self._gap_title_subtitle = _TitleBarGap(_TITLEBAR_TITLE_GAP,
                                                self._title_area)
        self._gap_title_subtitle.hide()

        self._subtitle_label = _TitleLabel("", self._title_area,
                                           "TitleBarSubtitle")

        self._gap_subtitle_custom = _TitleBarGap(_TITLEBAR_SUBTITLE_GAP,
                                                 self._title_area)
        self._gap_subtitle_custom.hide()

        title_layout.addWidget(self._icon_label)
        title_layout.addWidget(self._gap_icon_title)
        title_layout.addWidget(self._title_label, 1)
        title_layout.addWidget(self._gap_title_subtitle)
        title_layout.addWidget(self._subtitle_label)
        title_layout.addWidget(self._gap_subtitle_custom)
        root.addWidget(self._title_area)

        # 自定义区：标题区到控制区之间，占满剩余宽度。
        self._custom_area = QWidget(self)
        self._custom_area.setAutoFillBackground(False)
        self._custom_layout = QHBoxLayout(self._custom_area)
        self._custom_layout.setContentsMargins(0, 0, 0, 0)
        self._custom_layout.setSpacing(0)
        root.addWidget(self._custom_area, 1)

        self._controls_gap = _TitleBarGap(_TITLEBAR_CONTROLS_GAP, self)
        root.addWidget(self._controls_gap)

        # 右侧：最小化 / 最大化 / 关闭（从左到右），顶部对齐以支持自定义高度。
        for role in ("minimize", "maximize", "close"):
            button = CaptionButton(role, self, height=self._height)
            self._buttons[role] = button
            button.hovered.connect(
                lambda on, r=role: self._set_hover_role(r if on else None))
            button.pressed.connect(
                lambda on, r=role: self._set_pressed_role(r if on else None))
            button.clicked.connect(lambda r=role: self._on_button_clicked(r))
            root.addWidget(button, 0, Qt.AlignTop)
        self._sync_maximize_glyph()
        self._sync_title_area()

    # -------------------------------------------------------- 标题区 / 自定义区
    def _sync_title_area(self) -> None:
        if self._title_area_removed:
            self._title_area.hide()
            return
        self._title_area.show()
        has_icon = self._icon is not None and not self._icon.isNull()
        self._icon_label.setVisible(has_icon)
        self._gap_icon_title.setVisible(has_icon)
        has_title = bool(self._title_label.full_text())
        self._title_label.setVisible(has_title)
        self._gap_title_subtitle.setVisible(has_title)
        has_subtitle = bool(self._subtitle_label.full_text())
        self._subtitle_label.setVisible(has_subtitle)
        self._gap_subtitle_custom.setVisible(has_subtitle)
        layout = self._title_area.layout()
        if layout is not None:
            layout.activate()
        self._main_layout.activate()
        self.updateGeometry()

    def setLayout(self, layout):
        """设置标题栏自定义区内容（QLayout 或 QWidget）；None 清空。

        注意：该公共 API 接管了 ``QWidget.setLayout`` 的语义，但不会改变
        TitleBar 自身的根布局（``self.layout()`` 仍返回根 QHBoxLayout）。
        """
        while self._custom_layout.count():
            item = self._custom_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
        if self._custom_host is not None:
            self._custom_host.deleteLater()
            self._custom_host = None
        if layout is None:
            self._main_layout.activate()
            return

        if isinstance(layout, QWidget):
            host = layout
            host.setParent(self._custom_area)
            self._custom_host = host
        elif isinstance(layout, QLayout):
            host = _LayoutHost(self._custom_area)
            host.setLayout(layout)
            self._custom_host = host
        else:
            raise TypeError("Layout must be QLayout, QWidget or None.")
        self._custom_layout.addWidget(host)
        host.show()
        self._main_layout.activate()

    def customLayout(self):
        return self._custom_host

    def removeTitleArea(self) -> None:
        """删除标题区（图标/标题/副标题），自定义区左拉长，控制区不变。"""
        self._title_area_removed = True
        self._sync_title_area()

    def showTitleArea(self) -> None:
        if not self._title_area_removed:
            return
        self._title_area_removed = False
        self._sync_title_area()

    def setSubTitle(self, subtitle: Optional[str]):
        self._subtitle_label.set_full_text(subtitle or "")
        self._sync_title_area()

    def subtitle(self) -> str:
        return self._subtitle_label.full_text()

    # ------------------------------------------------------ NavigationView 集成
    def initNavigationView(self, navigation_view: NavigationView,
                           move_animate_button: bool = True) -> None:
        """初始化 NavigationView：自动加入窗口内容区，可迁移汉堡/返回按钮。"""
        if navigation_view is None:
            raise TypeError("navigation_view cannot be None")

        self.set_glass(navigation_view.backdrop)
        if (self._nav_view is navigation_view
                and getattr(navigation_view, "_titlebar", None) is self
                and getattr(navigation_view, "_buttons_external", False)
                == bool(move_animate_button)):
            card = getattr(navigation_view, "_content_card", None)
            if card is not None:
                card.enable_titlebar_corner()
            if self._glass_style is not None:
                try:
                    navigation_view.setBrush(self._glass_style)
                except (RuntimeError, AttributeError):
                    pass
            self._sync_nav_cluster()
            return
        if self._nav_view is not None:
            try:
                self._nav_view.backVisibilityChanged.disconnect(
                    self.refreshNavigationButtons)
            except (RuntimeError, TypeError):
                pass
        if self._nav_view is not None and self._nav_view is not navigation_view:
            try:
                self._nav_view._detach_titlebar()
            except RuntimeError:
                pass
        self._nav_view = navigation_view

        if navigation_view.parent() is None:
            window = self._window or self.window()
            body_layout = getattr(window, "body_layout", None)
            if body_layout is not None:
                body_layout.addWidget(navigation_view, 1)
            elif isinstance(window, QMainWindow):
                current = window.centralWidget()
                if current is not None and current is not navigation_view:
                    raise RuntimeError(
                        "TitleBarMainWindow already has a centralWidget, can't automatically add 'NavigationView'")
                window.setCentralWidget(navigation_view)
            elif window is not None and window.layout() is not None:
                window.layout().addWidget(navigation_view)
            else:
                raise RuntimeError(
                    "Cannot automatically add NavigationView: the host window has no available layout")

        try:
            navigation_view.backVisibilityChanged.connect(
                self.refreshNavigationButtons)
        except (RuntimeError, TypeError):
            pass

        navigation_view._attach_titlebar(self, bool(move_animate_button))

        # TitleBar 集成后启用内容卡片的玻璃叠层与左上圆角。
        card = getattr(navigation_view, "_content_card", None)
        if card is not None:
            card.enable_titlebar_corner()

        # 整个应用背景使用与标题栏一致的玻璃材质。
        if self._glass_style is not None:
            try:
                navigation_view.setBrush(self._glass_style)
            except (RuntimeError, AttributeError):
                pass
        self._sync_nav_cluster()

    def attach_navigation_buttons(self, buttons) -> None:
        self._nav_buttons = [button for button in buttons if button is not None]
        for button in self._nav_buttons:
            button.setParent(self._nav_cluster)
            button.setProperty("titlebarInteractive", True)
            button.set_button_size(_TITLEBAR_NAV_BUTTON_W,
                                   _TITLEBAR_NAV_BUTTON_H)
            button.show()
            button.raise_()
        self._sync_nav_cluster()

    def detach_navigation_buttons(self) -> list:
        buttons = list(self._nav_buttons)
        self._nav_buttons = []
        self._sync_nav_cluster()
        return buttons

    def owns_navigation_widget(self, widget: QWidget | None) -> bool:
        if widget is None:
            return False
        for button in self._nav_buttons:
            if widget is button or button.isAncestorOf(widget):
                return True
        return False

    def refreshNavigationButtons(self, *_args) -> None:
        self._sync_nav_cluster()

    def _sync_nav_cluster(self) -> None:
        visible = [button for button in self._nav_buttons
                   if not button.isHidden()]
        if not visible:
            self._nav_cluster.hide()
            self._nav_cluster.setFixedSize(0, 0)
            self._leading_gap.show()
            self._nav_gap.hide()
        else:
            self._nav_cluster.show()
            self._leading_gap.hide()
            self._nav_gap.show()
            width = (_TITLEBAR_NAV_LEFT_MARGIN
                     + len(visible) * _TITLEBAR_NAV_BUTTON_W
                     + (len(visible) - 1) * _TITLEBAR_NAV_ITEM_GAP)
            self._nav_cluster.setFixedSize(width, self._height)
            x = _TITLEBAR_NAV_LEFT_MARGIN
            y = max(0, (self._height - _TITLEBAR_NAV_BUTTON_H) // 2)
            for button in visible:
                button.set_button_size(_TITLEBAR_NAV_BUTTON_W,
                                       _TITLEBAR_NAV_BUTTON_H)
                button.setGeometry(x, y, _TITLEBAR_NAV_BUTTON_W,
                                   _TITLEBAR_NAV_BUTTON_H)
                button.raise_()
                x += _TITLEBAR_NAV_BUTTON_W + _TITLEBAR_NAV_ITEM_GAP
        self._main_layout.activate()
        self.updateGeometry()
        self.update()

    # ------------------------------------------------------------------ 属性
    @property
    def buttons(self) -> dict:
        return dict(self._buttons)

    def title_bar_height(self) -> int:
        """标题栏高度（逻辑像素）。"""
        return self._height

    def set_title_bar_height(self, height: int):
        """运行时修改标题栏高度（右侧控制按钮与命中区域同步更新）。

        移动进 TitleBar 的导航按钮固定 40×48，只调整位置，不改变尺寸。
        """
        height = int(height)
        if height <= 0:
            raise ValueError("TitleBar height must be positive integer")
        if height == self._height:
            return
        self._height = height
        self.setFixedHeight(height)
        self._sync_control_heights()
        self._sync_nav_cluster()
        if self._main_layout is not None:
            self._main_layout.activate()
        self.updateGeometry()
        self.heightChanged.emit(height)

    def setControlHeight(self, height: int) -> None:
        """右侧最小化/最大化/关闭按钮的高度。

        0（默认）表示跟随 TitleBar；正整数表示固定高度（顶部对齐、向下伸展）；
        负数抛 ValueError。超过 TitleBar 的部分会被裁剪，但不报错。
        """
        height = int(height)
        if height < 0:
            raise ValueError("Control button height must be positive integer")
        self._control_height = height
        self._sync_control_heights()
        if self._main_layout is not None:
            self._main_layout.activate()

    def controlHeight(self) -> int:
        return self._control_height

    def _sync_control_heights(self) -> None:
        height = self._height if self._control_height == 0 else self._control_height
        for button in self._buttons.values():
            button.set_caption_height(height)

    def set_title(self, title: str):
        self._title_label.set_full_text(title or "")
        self._sync_title_area()

    def setTitle(self, title: str):
        """``set_title`` 的驼峰别名（与 setSubTitle/setIcon 保持同一风格）。"""
        self.set_title(title)

    def title(self) -> str:
        return self._title_label.full_text()

    # ---------------------------------------------------------------- 系统菜单
    def icon_rect(self) -> QRectF:
        """应用图标在标题栏本地坐标中的矩形；没有图标时返回空矩形。"""
        label = getattr(self, "_icon_label", None)
        if (label is None or label.isHidden() or self._title_area_removed):
            return QRectF()
        top_left = label.mapTo(self, QPoint(0, 0))
        return QRectF(top_left, label.size())

    def show_system_menu(self, global_pos: Optional[QPoint] = None, *,
                         icon_press: bool = False):
        """在 ``global_pos``（屏幕逻辑坐标）弹出系统菜单。

        ``icon_press=True`` 表示由“左键按下图标”触发，此时菜单会额外识别
        “双击图标”的第二按并发出 ``iconDoubleClicked``（见 ``_on_icon_double_clicked``）。
        """
        window = self._window or self.window()
        if window is None:
            return
        if self._system_menu is not None and self._system_menu.isVisible():
            return
        if global_pos is None:
            global_pos = QCursor.pos()
        if self._system_menu is None:
            self._system_menu = SystemMenu(window, parent=window)
            self._system_menu.actionTriggered.connect(self._on_system_menu_action)
            self._system_menu.iconDoubleClicked.connect(self._on_icon_double_clicked)
        self._icon_close_in_progress = False
        self._set_hover_role(None)
        self._set_pressed_role(None)
        self._system_menu.popup_at(QPoint(global_pos), icon_press=icon_press)

    def hide_system_menu(self):
        if self._system_menu is not None:
            self._system_menu.hide()

    def system_menu_visible(self) -> bool:
        return self._system_menu is not None and self._system_menu.isVisible()

    def _on_icon_double_clicked(self):
        """菜单收到“双击图标”的第二次按下：直接关闭窗口。"""
        if self._icon_close_in_progress:
            return
        self._icon_close_in_progress = True
        window = self._window or self.window()
        if window is not None:
            QTimer.singleShot(0, window, window.close)

    def _on_system_menu_action(self, key: str):
        window = self._window or self.window()
        if window is None:
            return
        handler = getattr(window, "handle_system_menu_action", None)
        if callable(handler):
            try:
                if handler(key):
                    return
            except Exception:
                traceback.print_exc()
        # 独立使用 TitleBar（窗口没有原生 helper）时的兜底
        if key == "restore":
            window.showNormal()
        elif key == "minimize":
            window.showMinimized()
        elif key == "maximize":
            window.showMaximized()
        elif key == "close":
            window.close()
        elif key == "move":
            handle = window.windowHandle()
            if handle is not None:
                handle.startSystemMove()

    def set_icon(self, icon: Optional[QIcon]):
        self._icon = icon
        if icon is None or icon.isNull():
            self._icon_label.hide()
            self._sync_title_area()
            return
        dpr = self.devicePixelRatioF() or 1.0
        try:
            pixmap = icon.pixmap(QSize(16, 16), dpr)
        except TypeError:  # 极老的 Qt
            pixmap = icon.pixmap(QSize(16, 16))
        self._icon_label.setPixmap(pixmap)
        self._sync_title_area()

    def setIcon(self, icon: Optional[QIcon]):
        """``set_icon`` 的驼峰别名。"""
        self.set_icon(icon)

    # ------------------------------------------------------------------ 玻璃
    def set_glass(self, backdrop, style: Optional[FrostStyle] = None,
                  *, enabled: bool = True) -> None:
        """让标题栏用内容区的玻璃材质绘制背景（默认与侧边栏同款）。

        ``backdrop`` 传 ``NavigationView.backdrop`` 之类的 ``GlassBackdrop``：
        标题栏与侧边栏共用同一个采样源，模糊、亮度、色调因此完全一致，标题栏
        不再是一块与内容区割裂的纯色。传 ``None``（或 ``enabled=False``）
        恢复 QSS 纯色背景。

        玻璃采样依赖窗口的全局位置，所以这里同时监听顶层窗口的 Move/Resize
        以及背景玻璃的重绘（桌面帧、节能模式过渡），避免标题栏停在旧画面上。
        """
        source = backdrop if enabled else None
        self._detach_glass()
        if source is None:
            # 关闭标题栏玻璃时，应用背景回到 window glass。
            if self._nav_view is not None:
                try:
                    self._nav_view.setBrush(BUBBLE_BACKGROUND_NORMAL)
                except (RuntimeError, AttributeError):
                    pass
            return
        self._glass_backdrop = source
        self._glass_style = SIDEBAR_GLASS if style is None else style
        # 整个应用背景使用与标题栏一致的玻璃材质。
        if self._nav_view is not None:
            try:
                self._nav_view.setBrush(self._glass_style)
            except (RuntimeError, AttributeError):
                pass
        source.installEventFilter(self)
        source.destroyed.connect(self._on_glass_destroyed)
        self._sync_glass_window()
        self.update()

    def glass_backdrop(self):
        """当前为标题栏提供采样源的玻璃对象；纯色标题栏时为 None。"""
        return self._glass_backdrop

    def _detach_glass(self) -> None:
        backdrop, self._glass_backdrop = self._glass_backdrop, None
        self._glass_style = None
        window, self._glass_window = self._glass_window, None
        for widget in (backdrop, window):
            if widget is None:
                continue
            try:
                widget.removeEventFilter(self)
            except RuntimeError:
                pass
        if backdrop is not None:
            try:
                backdrop.destroyed.disconnect(self._on_glass_destroyed)
            except (RuntimeError, TypeError):
                pass

    def _on_glass_destroyed(self, *_args) -> None:
        # 玻璃来源先于标题栏销毁：丢掉引用，paintEvent 自动退回纯色背景。
        self._detach_glass()

    def _sync_glass_window(self) -> None:
        """监听真正的顶层窗口：玻璃采样跟着窗口全局位置走。"""
        try:
            window = self.window()
        except RuntimeError:
            return
        if window is self._glass_window:
            return
        if self._glass_window is not None:
            try:
                self._glass_window.removeEventFilter(self)
            except RuntimeError:
                pass
        self._glass_window = window
        if window is not None and window is not self:
            window.installEventFilter(self)

    def eventFilter(self, obj, event) -> bool:
        backdrop = getattr(self, "_glass_backdrop", None)
        event_type = event.type()
        if obj is backdrop and backdrop is not None:
            # 背景玻璃重绘（桌面帧 / 节能模式过渡 / 窗口移动）时标题栏跟着
            # 重绘，否则两块玻璃会停在不同的一帧上。
            if event_type in (QEvent.Type.Paint, QEvent.Type.UpdateRequest):
                self.update()
        elif obj is getattr(self, "_glass_window", None):
            if event_type in (QEvent.Type.Move, QEvent.Type.Resize):
                self.update()
        return super().eventFilter(obj, event)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if getattr(self, "_glass_backdrop", None) is not None:
            self._sync_glass_window()
            self.update()

    # ------------------------------------------------------------------ 绘制
    def paintEvent(self, event) -> None:
        backdrop = getattr(self, "_glass_backdrop", None)
        style = getattr(self, "_glass_style", None)
        if backdrop is None or style is None:
            super().paintEvent(event)
            return
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            rect = QRectF(self.rect())
            energy = getattr(backdrop, "energy", None)
            if energy is not None and energy.active:
                # 与侧边栏一致：节能模式用材质的 tint 纯色，不做实时采样。
                painter.fillRect(rect, QColor(style.tint))
            else:
                global_rect = QRect(self.mapToGlobal(QPoint(0, 0)), self.size())
                backdrop.paint_material(painter, rect, global_rect, style)
        except RuntimeError:
            # 玻璃来源的 C++ 对象先于标题栏销毁：丢掉引用，退回纯色背景。
            self._detach_glass()
        finally:
            painter.end()
        if getattr(self, "_glass_backdrop", None) is None:
            super().paintEvent(event)

    def changeEvent(self, event):
        super().changeEvent(event)
        # 窗口拖到不同缩放比例的显示器时，重新取高分图标
        dpr_event = getattr(QEvent, "DevicePixelRatioChange", None)
        if dpr_event is not None and event.type() == dpr_event:
            if self._icon is not None:
                self.set_icon(self._icon)

    def is_dark(self) -> bool:
        return self._dark

    def set_dark(self, dark: bool):
        self._dark = bool(dark)
        self._apply_titlebar_stylesheet()
        self.themeChanged.emit(self._dark)

    def _apply_titlebar_stylesheet(self) -> None:
        if self._applying_style:
            return
        self._applying_style = True
        try:
            self.setStyleSheet(_titlebar_stylesheet(self._dark,
                                                    self._subtitle_color))
            _repolish(self)
            for label in (getattr(self, "_title_label", None),
                          getattr(self, "_subtitle_label", None)):
                if label is not None:
                    _repolish(label)
            for button in getattr(self, "_buttons", {}).values():
                _repolish(button)
        finally:
            self._applying_style = False

    def set_active(self, active: bool):
        active = bool(active)
        if active == self._active:
            return
        self._active = active
        self._title_label.setProperty("active", active and "true" or "false")
        _repolish(self._title_label)
        self._subtitle_label.setProperty("active",
                                         active and "true" or "false")
        _repolish(self._subtitle_label)
        for button in self._buttons.values():
            button.set_window_active(active)

    def set_maximized(self, maximized: bool):
        maximized = bool(maximized)
        if maximized == self._maximized:
            return
        self._maximized = maximized
        self._sync_maximize_glyph()

    def _sync_maximize_glyph(self):
        button = self._buttons.get("maximize")
        if button is None:
            return
        button.set_glyph(_CAPTION_GLYPHS["restore" if self._maximized else "maximize"])

    # ----------------------------------------------------- 命中测试 / 按钮状态
    def hit_test(self, position: QPointF) -> Optional[str]:
        """返回点击区域类型：close / minimize / maximize / caption / client。

        position 为标题栏本地坐标（逻辑像素）；不在标题栏内返回 None。
        """
        rect = QRectF(self.rect())
        if not rect.contains(position):
            return None

        if self._native_caption:
            role = self._button_at(position)
            if role is not None:
                return role
        else:
            if self._button_at(position) is not None:
                return "client"

        widget = self.childAt(position.toPoint())
        while widget is not None and widget is not self:
            if widget.property("titlebarInteractive"):
                return "client"
            widget = widget.parentWidget()

        # 其余区域：交给系统拖动 / 双击最大化 / 右键系统菜单
        return "caption"

    def _button_at(self, position: QPointF) -> Optional[str]:
        for role, button in self._buttons.items():
            top_left = button.mapTo(self, QPoint(0, 0))
            if QRectF(top_left, button.size()).contains(position):
                return role
        return None

    def set_native_hover(self, hit_code: Optional[int]):
        self._set_hover_role(self._role_from_hit_code(hit_code))

    def set_native_pressed(self, hit_code: Optional[int]):
        role = self._role_from_hit_code(hit_code)
        self._set_pressed_role(role)
        if role is not None:
            self._set_hover_role(role)

    @staticmethod
    def _role_from_hit_code(hit_code: Optional[int]) -> Optional[str]:
        return {HTMINBUTTON: "minimize",
                HTMAXBUTTON: "maximize",
                HTCLOSE: "close"}.get(hit_code)

    def _set_hover_role(self, role: Optional[str]):
        if role == self._hover_role:
            return
        self._hover_role = role
        self._refresh_button_states()

    def _set_pressed_role(self, role: Optional[str]):
        if role == self._pressed_role:
            return
        self._pressed_role = role
        self._refresh_button_states()

    def _refresh_button_states(self):
        for role, button in self._buttons.items():
            if role == self._pressed_role:
                button.set_caption_state("pressed")
            elif role == self._hover_role:
                button.set_caption_state("hover")
            else:
                button.set_caption_state("normal")

    # ------------------------------------------------------------ Qt 交互模式
    def _on_button_clicked(self, role: str):
        window = self._window or self.window()
        if window is None:
            return
        if role == "minimize":
            window.showMinimized()
        elif role == "maximize":
            if window.isMaximized():
                window.showNormal()
            else:
                window.showMaximized()
        elif role == "close":
            window.close()

    # ------------------------------------------- Qt 交互模式的系统菜单触发
    def mousePressEvent(self, event):
        # 原生模式下这些区域走非客户区命中测试，不会到达这里；
        # 这里保证 TitleBar 单独使用（无 helper）时菜单仍然可用。
        pos = event.position()
        if event.button() == Qt.LeftButton and self.icon_rect().contains(pos):
            self.show_system_menu(event.globalPosition().toPoint(),
                                  icon_press=True)
            event.accept()
            return
        if event.button() == Qt.RightButton and self._button_at(pos) is None:
            self.show_system_menu(event.globalPosition().toPoint())
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if (event.button() == Qt.LeftButton
                and self.icon_rect().contains(event.position())):
            window = self._window or self.window()
            if window is not None:
                window.close()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event):
        if self._button_at(QPointF(event.pos())) is None:
            self.show_system_menu(event.globalPos())
            event.accept()
            return
        super().contextMenuEvent(event)


# =============================================================================
# 原生窗口框架助手
# =============================================================================

class WindowsFrameHelper:
    """把任意 Qt 顶层窗口变成“保留 Windows 原生效果”的自定义标题栏窗口。

    负责：
      * 补回 WS_OVERLAPPEDWINDOW（阴影、动画、贴靠、任务栏都靠它）；
      * WM_NCCALCSIZE 隐藏原生标题栏；
      * WM_NCHITTEST 把标题栏/按钮映射成系统 hit code；
      * WM_NCMOUSEMOVE / WM_NCMOUSELEAVE 维护按钮悬停；
      * WM_NCLBUTTONDOWN / WM_LBUTTONUP 自己处理按钮点击
        （不让 DefWindowProc 进入它的非客户区按钮跟踪：否则它会按标准
         标题栏位置把原生按钮画进客户区，还会取消我们的最小化/最大化）；
      * DWM 圆角与深色模式，并跟随系统主题。
    """

    def __init__(self, window: QWidget, title_bar: TitleBar, *,
                 native_caption: bool = True, dark: Optional[bool] = None,
                 rounded: bool = True, auto_theme: bool = True):
        self.window = window
        self.title_bar = title_bar
        self.native_caption = bool(native_caption)
        self.rounded = bool(rounded)
        self.auto_theme = bool(auto_theme)
        self._dark = system_is_dark() if dark is None else bool(dark)
        self._hwnd = None
        self._last_maximized = None
        self._restyle_pending = False
        self._restyling = False
        # 正在按下的标题栏按钮 hit code（HTMINBUTTON / HTMAXBUTTON / HTCLOSE）
        self._pressed_hit = None
        # 原生回调里不能直接创建 Qt 弹窗：延迟 0ms 弹出系统菜单
        self._menu_open_timer = QTimer(window)
        self._menu_open_timer.setSingleShot(True)
        self._menu_open_timer.timeout.connect(self._show_pending_system_menu)
        self._pending_menu_pos = None
        self._pending_icon_press = False
        # “移动/大小”提示模式（系统菜单里选择后进入）
        self._hint_mode = None
        self._hint_edge = None
        self._hint_dragging = False
        self._hint_capture = False
        self._hint_releasing = False
        self._hint_timer = QTimer(window)
        self._hint_timer.setInterval(15)
        self._hint_timer.timeout.connect(self._tick_hint)

    # ------------------------------------------------------------------ 安装
    def install(self):
        if not _IS_WINDOWS:
            return
        # 先创建原生窗口（此时窗口还不可见），再补回原生边框样式，
        # 避免出现“先弹出无边框窗口再变回带边框”的闪烁。
        hwnd = int(self.window.winId())
        self._hwnd = hwnd
        _inject_native_frame_styles(hwnd)
        _apply_dwm_effects(hwnd, self._dark, self.rounded)
        self.title_bar.set_dark(self._dark)
        self.title_bar.set_active(self.window.isActiveWindow())
        self.title_bar.set_maximized(self.window.isMaximized())
        self._last_maximized = bool(self.window.isMaximized())

    def _ensure_frame_styles(self, hwnd):
        """窗口样式被 Qt 重置（setWindowFlags / 全屏切换）时，安排一次补回。

        Qt 的 setWindowFlags()/showFullScreen() 会把窗口重新变回 WS_POPUP，
        从而丢掉阴影和动画；这里检测到之后用 0 延迟定时器补回，
        避免在 Qt 正在改样式的过程中重入。
        """
        if not _IS_WINDOWS:
            return
        if self._restyle_pending or self._restyling:
            return
        try:
            style = _user32.GetWindowLongPtrW(wt.HWND(hwnd), GWL_STYLE)
        except OSError:
            return
        if (style & WS_OVERLAPPEDWINDOW) == WS_OVERLAPPEDWINDOW and not (style & WS_POPUP):
            return
        self._restyle_pending = True
        QTimer.singleShot(0, self.window, self._restyle)

    def _restyle(self):
        self._restyle_pending = False
        window = self.window
        try:
            if window.isFullScreen():
                # 全屏时保持无边框（Windows 全屏窗口本来就没有阴影）
                return
            hwnd = int(window.winId())
        except (RuntimeError, OSError):
            return
        self._restyling = True
        try:
            self._hwnd = hwnd
            _inject_native_frame_styles(hwnd)
            _apply_dwm_effects(hwnd, self._dark, self.rounded)
        except OSError:
            pass
        finally:
            self._restyling = False

    def set_dark(self, dark: bool):
        self._dark = bool(dark)
        if self._hwnd:
            _apply_dwm_effects(self._hwnd, self._dark, self.rounded)
        self.title_bar.set_dark(self._dark)

    def is_dark(self) -> bool:
        return self._dark

    # -------------------------------------------------------------- 消息处理
    def handle_message(self, event_type, message):
        """由窗口的 nativeEvent() 调用；返回 (handled, result)。"""
        if not _IS_WINDOWS:
            return False, 0
        try:
            event_type = bytes(event_type)
        except TypeError:
            event_type = b""
        if event_type not in (b"windows_generic_MSG", b"windows_dispatcher_MSG"):
            return False, 0

        try:
            msg = wt.MSG.from_address(int(message))
        except (TypeError, ValueError):
            return False, 0

        # 原生窗口创建期间（winId() 尚未返回）不要调用 Qt API，否则会重入
        creating = self._hwnd is None
        if creating and message in (WM_SIZE, WM_NCACTIVATE, WM_NCMOUSEMOVE,
                                    WM_NCLBUTTONDOWN, WM_NCLBUTTONUP,
                                    WM_NCLBUTTONDBLCLK, WM_LBUTTONUP,
                                    WM_CAPTURECHANGED,
                                    WM_MOUSEMOVE, WM_GETMINMAXINFO,
                                    WM_STYLECHANGED):
            return False, 0

        try:
            return self._process(msg)
        except Exception:  # 原生回调里绝不能让异常穿回 C++，否则 Qt 会崩
            traceback.print_exc()
            return False, 0

    def _process(self, msg):
        message = msg.message
        hwnd = msg.hWnd

        # Qt 可能会重置原生样式（setWindowFlags / 全屏切换），发现丢失就补回
        if message in (WM_SIZE, WM_NCHITTEST, WM_NCMOUSEMOVE, WM_NCLBUTTONDOWN,
                       WM_NCLBUTTONUP, WM_STYLECHANGED):
            self._ensure_frame_styles(hwnd)

        if message == WM_STYLECHANGED:
            return False, 0

        # 移动/大小提示模式期间优先接管鼠标/光标消息
        if self._hint_mode is not None:
            handled = self._process_hint_message(msg)
            if handled is not None:
                return handled

        # Alt+Space：用自制菜单替换原生系统菜单
        if message == WM_SYSKEYDOWN and int(msg.wParam) == VK_SPACE:
            if int(msg.lParam) & (1 << 29):  # context 位：Alt 组合键
                if not int(msg.lParam) & (1 << 30):  # 忽略按住产生的重复
                    self._handle_alt_space()
                return True, 0
        if (message == WM_SYSCOMMAND
                and (int(msg.wParam) & 0xFFF0) == SC_KEYMENU
                and int(msg.lParam) == VK_SPACE):
            self._handle_alt_space()
            return True, 0

        # 右键标题栏（按钮区域除外）→ 自制菜单；同时吞掉原生菜单
        if message == WM_NCRBUTTONDOWN:
            if self._begin_caption_context_menu(hwnd, msg):
                return True, 0
            return False, 0

        if message == WM_NCRBUTTONUP:
            if self._consume_title_bar_context(hwnd, msg.lParam):
                return True, 0
            return False, 0

        if message == WM_CONTEXTMENU:
            if self._consume_title_bar_context(hwnd, msg.lParam):
                return True, 0
            return False, 0

        if message == WM_NCCALCSIZE:
            if not msg.wParam:
                return False, 0
            # 非客户区算成 0：客户区铺满整个窗口（原生标题栏被“藏”起来）
            if _user32.IsZoomed(hwnd):
                # 最大化时窗口矩形比屏幕大了一圈边框，客户区应正好是工作区
                work_area = _monitor_work_area(hwnd)
                if work_area is not None:
                    params = _NCCALCSIZE_PARAMS.from_address(int(msg.lParam))
                    params.rgrc[0] = work_area
            return True, 0

        if message == WM_NCHITTEST:
            hit = self._on_hit_test(hwnd, msg.lParam)
            if hit is None:
                return False, 0
            return True, int(hit)

        if message == WM_NCMOUSEMOVE:
            self.title_bar.set_native_hover(int(msg.wParam))
            # 让窗口在鼠标离开非客户区时收到 WM_NCMOUSELEAVE
            track = _TRACKMOUSEEVENT(ctypes.sizeof(_TRACKMOUSEEVENT),
                                     TME_LEAVE | TME_NONCLIENT,
                                     hwnd, 0)
            _user32.TrackMouseEvent(ctypes.byref(track))
            return False, 0

        if message == WM_NCMOUSELEAVE:
            if self._pressed_hit is None:
                self.title_bar.set_native_hover(None)
                self.title_bar.set_native_pressed(None)
            return False, 0

        if message == WM_NCLBUTTONDOWN:
            if self._begin_caption_menu(hwnd, msg):
                return True, 0
            if self._begin_caption_press(hwnd, int(msg.wParam)):
                # 自己处理标题栏按钮：不能再交给 DefWindowProc。
                # 否则 DefWindowProc 会进入它自己的“非客户区按钮跟踪”循环，
                # 按标准标题栏位置把原生按钮画到我们的客户区里（就是那个
                # 按下后出现在按钮旁边的“白底按钮”），而且因为我们的按钮
                # 位置和标准位置不一致，它会在鼠标移动后取消最小化/最大化。
                return True, 0
            self.title_bar.set_native_pressed(int(msg.wParam))
            return False, 0

        if message == WM_NCLBUTTONDBLCLK:
            if self._begin_caption_double_click(hwnd, msg):
                return True, 0
            if self._begin_caption_press(hwnd, int(msg.wParam)):
                return True, 0
            return False, 0

        if message == WM_LBUTTONUP:
            if self._pressed_hit is not None:
                self._finish_caption_press(hwnd)
                return True, 0
            return False, 0

        if message == WM_CAPTURECHANGED:
            if self._pressed_hit is not None:
                self._pressed_hit = None
                self.title_bar.set_native_pressed(None)
                self.title_bar.set_native_hover(None)
            return False, 0

        if message == WM_CANCELMODE:
            if self._pressed_hit is not None:
                self._pressed_hit = None
                try:
                    _user32.ReleaseCapture()
                except OSError:
                    pass
                self.title_bar.set_native_pressed(None)
                self.title_bar.set_native_hover(None)
            return False, 0

        if message == WM_NCLBUTTONUP:
            if self._pressed_hit is not None:
                self._finish_caption_press(hwnd)
                return True, 0
            self.title_bar.set_native_pressed(None)
            self.title_bar.set_native_hover(int(msg.wParam))
            return False, 0

        if message == WM_MOUSEMOVE:
            if self._pressed_hit is not None:
                # 按住按钮拖动时：鼠标在按钮上保持按下态，移出则恢复；
                # 这些消息不再交给 Qt，避免按住标题栏按钮时内容区跟着动。
                hit = self._hit_code_at_cursor(hwnd)
                if hit == self._pressed_hit:
                    self.title_bar.set_native_pressed(self._pressed_hit)
                else:
                    self.title_bar.set_native_pressed(None)
                    if hit in (HTMINBUTTON, HTMAXBUTTON, HTCLOSE):
                        self.title_bar.set_native_hover(hit)
                    else:
                        self.title_bar.set_native_hover(None)
                return True, 0
            # 鼠标进入客户区，标题栏按钮不应继续保持悬停
            self.title_bar.set_native_hover(None)
            return False, 0

        if message == WM_NCACTIVATE:
            self.title_bar.set_active(bool(msg.wParam))
            return False, 0

        if message == WM_SIZE:
            if bool(_user32.IsIconic(hwnd)):
                # 最小化后鼠标状态失效，清掉按钮的悬停/按下残留
                self._pressed_hit = None
                self.title_bar.set_native_pressed(None)
                self.title_bar.set_native_hover(None)
            maximized = bool(_user32.IsZoomed(hwnd))
            if maximized != self._last_maximized:
                self._last_maximized = maximized
                self.title_bar.set_maximized(maximized)
            return False, 0

        if message == WM_GETMINMAXINFO:
            self._apply_min_max_info(hwnd, msg.lParam)
            return False, 0

        if message == WM_SETTINGCHANGE:
            self._on_setting_change(msg.lParam)
            return False, 0

        return False, 0

    # -------------------------------------------------------- 标题栏按钮点击
    def _begin_caption_press(self, hwnd, hit_code):
        """按下标题栏按钮：自己 SetCapture，不让 DefWindowProc 介入。

        这样既能避免 DefWindowProc 按“标准标题栏”位置把原生按钮画进客户区
        （按下时旁边出现的白底按钮），也能避免它用标准位置的命中测试
        取消我们的最小化/最大化。
        """
        if hit_code not in (HTMINBUTTON, HTMAXBUTTON, HTCLOSE):
            return False
        self._pressed_hit = hit_code
        _user32.SetCapture(wt.HWND(hwnd))
        self.title_bar.set_native_pressed(hit_code)
        self.title_bar.set_native_hover(hit_code)
        return True

    def _finish_caption_press(self, hwnd):
        pressed = self._pressed_hit
        self._pressed_hit = None
        try:
            _user32.ReleaseCapture()
        except OSError:
            pass
        self.title_bar.set_native_pressed(None)

        # 松开时鼠标还在按钮上才执行（与系统标题栏行为一致）
        hit = self._hit_code_at_cursor(hwnd)
        if hit in (HTMINBUTTON, HTMAXBUTTON, HTCLOSE):
            self.title_bar.set_native_hover(hit)
        else:
            self.title_bar.set_native_hover(None)
        if pressed is not None and hit == pressed:
            self._perform_caption_action(hwnd, pressed)

    def _hit_code_at_cursor(self, hwnd):
        point = wt.POINT()
        if not _user32.GetCursorPos(ctypes.byref(point)):
            return None
        lparam = ((point.y & 0xFFFF) << 16) | (point.x & 0xFFFF)
        return self._on_hit_test(hwnd, lparam)

    def _perform_caption_action(self, hwnd, hit_code):
        """用系统命令执行按钮动作（动画/状态同步都交给 Windows 自己）。"""
        try:
            style = _user32.GetWindowLongPtrW(wt.HWND(hwnd), GWL_STYLE)
        except OSError:
            return
        if hit_code == HTCLOSE:
            if style & WS_SYSMENU:
                _user32.PostMessageW(wt.HWND(hwnd), WM_CLOSE, 0, 0)
        elif hit_code == HTMINBUTTON:
            if style & WS_MINIMIZEBOX:
                _user32.PostMessageW(wt.HWND(hwnd), WM_SYSCOMMAND, SC_MINIMIZE, 0)
        elif hit_code == HTMAXBUTTON:
            if style & WS_MAXIMIZEBOX:
                command = SC_RESTORE if _user32.IsZoomed(wt.HWND(hwnd)) else SC_MAXIMIZE
                _user32.PostMessageW(wt.HWND(hwnd), WM_SYSCOMMAND, command, 0)

    # ------------------------------------------------------------ 系统菜单触发
    def _title_bar_local(self, hwnd, lparam):
        """屏幕坐标 lParam -> 标题栏本地坐标；不在标题栏内返回 None。"""
        title_bar = self.title_bar
        try:
            if not title_bar.isVisible():
                return None
            point = _screen_point(lparam)
            if not _user32.ScreenToClient(hwnd, ctypes.byref(point)):
                return None
            dpr = self.window.devicePixelRatioF() or 1.0
            local = QPointF(point.x / dpr, point.y / dpr)
            origin = title_bar.mapTo(self.window, QPoint(0, 0))
            rect = QRectF(origin.x(), origin.y(),
                          title_bar.width(), title_bar.height())
            if not rect.contains(local):
                return None
            return local - QPointF(origin)
        except RuntimeError:
            return None

    def _title_bar_local_at_cursor(self):
        if self._hwnd is None:
            return None
        point = wt.POINT()
        if not _user32.GetCursorPos(ctypes.byref(point)):
            return None
        lparam = ((point.y & 0xFFFF) << 16) | (point.x & 0xFFFF)
        return self._title_bar_local(self._hwnd, lparam)

    def _open_system_menu(self, *, icon_press: bool = False, anchor=None):
        """记录锚点并用 0ms 定时器弹出菜单（避免在原生回调里造 Qt 窗口）。"""
        if not _IS_WINDOWS or self._hwnd is None:
            return
        self.cancel_system_menu_hint()
        self._pressed_hit = None
        try:
            self.title_bar.set_native_pressed(None)
            self.title_bar.set_native_hover(None)
        except RuntimeError:
            pass
        try:
            if not self.window.isActiveWindow():
                self.window.activateWindow()
        except RuntimeError:
            pass
        if anchor is None:
            anchor = QCursor.pos()
        self._pending_menu_pos = QPoint(anchor)
        self._pending_icon_press = bool(icon_press)
        self._menu_open_timer.start(0)

    def _show_pending_system_menu(self):
        pos = self._pending_menu_pos
        if pos is None:
            return
        icon_press = self._pending_icon_press
        self._pending_menu_pos = None
        self._pending_icon_press = False
        try:
            if self.title_bar.system_menu_visible():
                return
            self.title_bar.show_system_menu(pos, icon_press=icon_press)
        except RuntimeError:
            pass

    def _cancel_pending_system_menu(self):
        self._menu_open_timer.stop()
        self._pending_menu_pos = None
        self._pending_icon_press = False

    def _begin_caption_menu(self, hwnd, msg):
        """左键按下应用图标：弹出系统菜单（并阻止拖动）。"""
        if self._hint_mode is not None:
            # 移动/大小模式里自己 Post 的 WM_NCLBUTTONDOWN，不能再当菜单触发
            return False
        if int(msg.wParam) != HTCAPTION:
            return False
        local = self._title_bar_local(hwnd, msg.lParam)
        if local is None:
            return False
        icon_rect = self.title_bar.icon_rect()
        if icon_rect.isEmpty() or not icon_rect.contains(local):
            return False
        self._open_system_menu(icon_press=True)
        return True

    def _begin_caption_context_menu(self, hwnd, msg):
        """右键按下标题栏（CaptionButton 区域除外）：弹出系统菜单。"""
        if self._hint_mode is not None:
            return True  # 模式进行中：吞掉右键（等同取消前的保护）
        local = self._title_bar_local(hwnd, msg.lParam)
        if local is None:
            return False
        if self.title_bar._button_at(local) is not None:
            return True  # 按钮区域：吞掉，不弹原生菜单
        self._open_system_menu()
        return True

    def _consume_title_bar_context(self, hwnd, lparam):
        """吞掉标题栏上的 WM_NCRBUTTONUP / WM_CONTEXTMENU，防止原生菜单。"""
        if int(lparam) == -1:  # 键盘触发
            return False
        return self._title_bar_local(hwnd, lparam) is not None

    def _begin_caption_double_click(self, hwnd, msg):
        """双击应用图标：取消待弹菜单并关闭窗口。"""
        if self._hint_mode is not None:
            return False
        if int(msg.wParam) != HTCAPTION:
            return False
        local = self._title_bar_local(hwnd, msg.lParam)
        if local is None:
            return False
        icon_rect = self.title_bar.icon_rect()
        if icon_rect.isEmpty() or not icon_rect.contains(local):
            return False
        self._cancel_pending_system_menu()
        try:
            self.title_bar.hide_system_menu()
        except RuntimeError:
            pass
        _user32.PostMessageW(wt.HWND(hwnd), WM_CLOSE, 0, 0)
        return True

    def _handle_alt_space(self):
        """Alt+Space：弹出自制系统菜单，锚点 = 窗口左上角。"""
        try:
            if self.title_bar.system_menu_visible():
                self.title_bar.hide_system_menu()
                self._cancel_pending_system_menu()
                return
        except RuntimeError:
            pass
        try:
            anchor = self.window.mapToGlobal(QPoint(0, 0))
        except RuntimeError:
            anchor = QCursor.pos()
        self._open_system_menu(anchor=anchor)

    # -------------------------------------------------------- 移动/大小模式
    def begin_system_menu_hint(self, kind: str) -> bool:
        """进入“移动”或“大小”提示模式（系统菜单里选择后调用）。"""
        if not _IS_WINDOWS or self._hwnd is None:
            return False
        if kind not in ("move", "size"):
            return False
        try:
            hwnd = int(self.window.winId())
        except (RuntimeError, OSError):
            return False
        try:
            if _user32.IsZoomed(wt.HWND(hwnd)):
                return False
        except OSError:
            return False
        self.cancel_system_menu_hint()
        self._cancel_pending_system_menu()
        rect = _window_rect(hwnd)
        if rect is None:
            return False

        self._hint_mode = kind
        self._hint_edge = None
        self._hint_dragging = False
        self._hint_releasing = False

        if kind == "move":
            # 十字箭头热点在中心：让上箭头尖端正好落在窗口上边界
            cursor_h = _system_metrics_for_dpi(hwnd, SM_CYCURSOR) or 32
            target = QPoint((rect.left + rect.right) // 2,
                            rect.top + max(1, cursor_h // 2))
        else:
            target = QPoint((rect.left + rect.right) // 2,
                            (rect.top + rect.bottom) // 2)

        try:
            _user32.SetCapture(wt.HWND(hwnd))
            # SetCapture 可能因为窗口不在前台而失败，用 GetCapture 确认
            self._hint_capture = (_user32.GetCapture() or 0) == hwnd
        except OSError:
            self._hint_capture = False
        try:
            _user32.SetCursorPos(target.x(), target.y())
        except OSError:
            # 锁屏等情况下可能移动失败；模式本身仍可继续（光标提示照常）
            pass
        self._apply_hint_cursor()
        self._hint_timer.start()
        return True

    def cancel_system_menu_hint(self):
        """退出移动/大小模式并恢复光标（幂等）。"""
        self._hint_timer.stop()
        self._hint_mode = None
        self._hint_edge = None
        self._hint_dragging = False
        had_capture = self._hint_capture
        self._hint_capture = False
        if had_capture and _IS_WINDOWS:
            try:
                _user32.ReleaseCapture()
            except OSError:
                pass
        try:
            self.title_bar.unsetCursor()
            self.window.unsetCursor()
        except RuntimeError:
            pass
        handle = _system_cursor(IDC_ARROW)
        if handle:
            try:
                _user32.SetCursor(handle)
            except OSError:
                pass

    def _tick_hint(self):
        if self._hint_mode is not None:
            self._apply_hint_cursor()

    def _hint_cursor_id(self):
        if self._hint_mode == "size" and self._hint_edge:
            if self._hint_edge in ("left", "right"):
                return IDC_SIZEWE, Qt.SizeHorCursor
            return IDC_SIZENS, Qt.SizeVerCursor
        return IDC_SIZEALL, Qt.SizeAllCursor

    def _apply_hint_cursor(self):
        if self._hint_mode is None:
            return
        cursor_id, qt_cursor = self._hint_cursor_id()
        handle = _system_cursor(cursor_id)
        if handle:
            try:
                _user32.SetCursor(handle)
            except OSError:
                pass
        try:
            self.title_bar.setCursor(qt_cursor)
        except RuntimeError:
            pass

    def _edge_at_cursor(self):
        """大小模式：返回距离最近的那条边（严格单边，角落也不对角）。"""
        if self._hwnd is None:
            return None
        point = wt.POINT()
        if not _user32.GetCursorPos(ctypes.byref(point)):
            return None
        rect = _window_rect(self._hwnd)
        if rect is None:
            return None
        try:
            border_x, border_y = _resize_border_size(self._hwnd)
        except OSError:
            border_x = border_y = 8

        candidates = []
        left = abs(point.x - rect.left)
        right = abs(rect.right - point.x)
        top = abs(point.y - rect.top)
        bottom = abs(rect.bottom - point.y)
        if left <= border_x:
            candidates.append((left, 0, "left"))
        if right <= border_x:
            candidates.append((right, 0, "right"))
        if top <= border_y:
            candidates.append((top, 1, "top"))
        if bottom <= border_y:
            candidates.append((bottom, 1, "bottom"))
        if not candidates:
            return None
        candidates.sort(key=lambda candidate: (candidate[0], candidate[1]))
        return candidates[0][2]

    def _start_native_drag(self, hit_code):
        """交给 DefWindowProc 的原生拖动/缩放循环（保留 Snap/动画）。"""
        hwnd = self._hwnd
        if hwnd is None:
            return
        self._hint_dragging = True
        self._hint_releasing = True
        try:
            if self._hint_capture:
                self._hint_capture = False
                _user32.ReleaseCapture()
        except OSError:
            pass
        finally:
            self._hint_releasing = False
        point = wt.POINT()
        if not _user32.GetCursorPos(ctypes.byref(point)):
            self.cancel_system_menu_hint()
            return
        lparam = ((point.y & 0xFFFF) << 16) | (point.x & 0xFFFF)
        _user32.PostMessageW(wt.HWND(hwnd), WM_NCLBUTTONDOWN, hit_code, lparam)

    def _process_hint_message(self, msg):
        """移动/大小模式期间优先处理消息；返回 None 表示继续走原逻辑。"""
        if self._hint_mode is None:
            return None
        message = msg.message
        if message == WM_SETCURSOR:
            self._apply_hint_cursor()
            return True, 1
        if message == WM_MOUSEMOVE:
            if self._hint_mode == "size":
                self._hint_edge = self._edge_at_cursor()
            self._apply_hint_cursor()
            return False, 0
        if message == WM_LBUTTONDOWN:
            if self._hint_mode == "move":
                if self._title_bar_local_at_cursor() is not None:
                    self._start_native_drag(HTCAPTION)
                else:
                    self.cancel_system_menu_hint()
                return True, 0
            edge = self._edge_at_cursor()
            self._hint_edge = edge
            hit_code = {"left": HTLEFT, "right": HTRIGHT,
                        "top": HTTOP, "bottom": HTBOTTOM}.get(edge)
            if hit_code is None:
                self.cancel_system_menu_hint()
            else:
                self._start_native_drag(hit_code)
            return True, 0
        if message == WM_RBUTTONDOWN:
            self.cancel_system_menu_hint()
            return True, 0
        if message in (WM_LBUTTONUP, WM_NCLBUTTONUP):
            QTimer.singleShot(0, self.window, self.cancel_system_menu_hint)
            return False, 0
        if message == WM_CAPTURECHANGED:
            if self._hint_releasing or self._hint_dragging:
                return False, 0
            self.cancel_system_menu_hint()
            return False, 0
        if message == WM_CANCELMODE:
            self.cancel_system_menu_hint()
            return False, 0
        if message == WM_KEYDOWN and int(msg.wParam) == VK_ESCAPE:
            self.cancel_system_menu_hint()
            return True, 0
        return None

    # ---------------------------------------------------------------- 命中测试
    def _on_hit_test(self, hwnd, lparam):
        if self.title_bar is None:
            return None
        try:
            # 注意：窗口被系统最大化时，Qt 可能会把“无边框 + 铺满屏幕”误判成
            # 全屏（windowState 里同时出现 WindowFullScreen）。用 IsZoomed
            # 区分真正的全屏，否则最大化后标题栏按钮会失去命中测试。
            if not _user32.IsZoomed(hwnd) and self.window.isFullScreen():
                return None
        except (RuntimeError, OSError):
            return None

        hint = self._titlebar_hit_test(hwnd, lparam)
        if hint in ("minimize", "maximize", "close"):
            return {"minimize": HTMINBUTTON,
                    "maximize": HTMAXBUTTON,
                    "close": HTCLOSE}[hint]
        if hint == "client":
            # 交给 Qt 处理（Qt 交互模式的按钮、标题栏里的自定义控件）
            return None

        border = self._resize_border_hit_test(hwnd, lparam)
        if border is not None:
            return border
        if hint == "caption":
            return HTCAPTION
        return None

    def _titlebar_hit_test(self, hwnd, lparam):
        local = self._title_bar_local(hwnd, lparam)
        if local is None:
            return None
        return self.title_bar.hit_test(local)

    def _resize_border_hit_test(self, hwnd, lparam):
        """最大化时没有可拖拽边框；否则按系统边框厚度判断 8 个方向。"""
        try:
            if _user32.IsZoomed(hwnd):
                return None
        except OSError:
            return None
        point = _screen_point(lparam)
        if not _user32.ScreenToClient(hwnd, ctypes.byref(point)):
            return None
        client = wt.RECT()
        if not _user32.GetClientRect(hwnd, ctypes.byref(client)):
            return None
        width, height = client.right - client.left, client.bottom - client.top
        border_x, border_y = _resize_border_size(hwnd)
        x, y = point.x, point.y
        if not (0 <= x < width and 0 <= y < height):
            return None
        left = x < border_x
        right = x >= width - border_x
        top = y < border_y
        bottom = y >= height - border_y
        if top and left:
            return HTTOPLEFT
        if top and right:
            return HTTOPRIGHT
        if bottom and left:
            return HTBOTTOMLEFT
        if bottom and right:
            return HTBOTTOMRIGHT
        if left:
            return HTLEFT
        if right:
            return HTRIGHT
        if top:
            return HTTOP
        if bottom:
            return HTBOTTOM
        return None

    # --------------------------------------------------------------- 其他消息
    def _apply_min_max_info(self, hwnd, lparam):
        """把 QWidget 的 minimumSize / maximumSize 同步给系统的拖拽缩放。"""
        try:
            info = _MINMAXINFO.from_address(int(lparam))
            dpi = 96
            if _HAS_DPI_API:
                dpi = _user32.GetDpiForWindow(hwnd) or 96
            scale = dpi / 96.0
            minimum = self.window.minimumSize()
            maximum = self.window.maximumSize()
            if minimum.width() > 0:
                info.ptMinTrackSize.x = int(round(minimum.width() * scale))
            if minimum.height() > 0:
                info.ptMinTrackSize.y = int(round(minimum.height() * scale))
            if 0 < maximum.width() < QWIDGETSIZE_MAX:
                info.ptMaxTrackSize.x = int(round(maximum.width() * scale))
            if 0 < maximum.height() < QWIDGETSIZE_MAX:
                info.ptMaxTrackSize.y = int(round(maximum.height() * scale))
        except (RuntimeError, OSError):
            pass

    def _on_setting_change(self, lparam):
        if not self.auto_theme or not lparam:
            return
        try:
            text = ctypes.wstring_at(lparam)
        except (ValueError, OSError):
            return
        if text and "ImmersiveColorSet" in text:
            dark = system_is_dark()
            if dark != self._dark:
                self.set_dark(dark)


class _WindowsFrameMixin:
    """为窗口类提供 nativeEvent 转发（子类在 __init__ 里创建 self._frame_helper）。"""

    _frame_helper: Optional[WindowsFrameHelper] = None

    def nativeEvent(self, eventType, message):
        helper = getattr(self, "_frame_helper", None)
        if helper is not None:
            handled, result = helper.handle_message(eventType, message)
            if handled:
                return True, result
        return super().nativeEvent(eventType, message)

    def handle_system_menu_action(self, key: str) -> bool:
        """系统菜单动作路由：move/size 交给原生 helper，其余走 Qt 窗口方法。"""
        if key in ("move", "size"):
            helper = getattr(self, "_frame_helper", None)
            if helper is not None:
                return helper.begin_system_menu_hint(key)
            return False
        if key == "restore":
            self.showNormal()
        elif key == "minimize":
            self.showMinimized()
        elif key == "maximize":
            self.showMaximized()
        elif key == "close":
            self.close()
        else:
            return False
        return True

    def hideEvent(self, event):
        # 窗口隐藏/最小化/关闭时清理移动/大小模式（避免光标卡在十字箭头）
        helper = getattr(self, "_frame_helper", None)
        if helper is not None:
            try:
                helper.cancel_system_menu_hint()
                helper._cancel_pending_system_menu()
            except Exception:
                traceback.print_exc()
        title_bar = getattr(self, "_title_bar", None)
        if title_bar is not None:
            try:
                title_bar.hide_system_menu()
            except RuntimeError:
                pass
        super().hideEvent(event)


class TitleBarWindow(_WindowsFrameMixin, QWidget):
    """自带 Windows 11 风格标题栏的顶层窗口（QWidget 版）。

    内容放进 ``self.body``（它自带一个空的 QVBoxLayout，直接用即可）::

        class MyWindow(TitleBarWindow):
            def __init__(self):
                super().__init__(title="我的应用", height=40)
                self.body_layout.addWidget(QTextEdit())

    标题栏高度用 ``height=`` 指定（逻辑像素，默认取 ``HEIGHT``），运行时想改就调用
    ``set_title_bar_height()``；布局会自动重排，不需要手动设置固定尺寸。

    原生效果：窗口阴影、圆角、最小化/最大化动画、Aero Snap、Win+方向键、
    双击标题栏最大化、Qt 自绘系统菜单（左键图标 / 右键标题栏 / Alt+Space）、
    Windows 11 贴靠布局悬浮面板。双击应用图标可直接关闭窗口。
    """

    def __init__(self, title: str = "", icon: Optional[QIcon] = None,
                 parent=None, *, height: Optional[int] = None,
                 native_caption: bool = True,
                 dark: Optional[bool] = None, auto_theme: bool = True,
                 rounded: bool = True):
        # 非 Windows 平台没有原生无边框拖动逻辑，保留系统边框以免窗口不可操作
        flags = Qt.Window
        if _IS_WINDOWS:
            flags |= Qt.FramelessWindowHint
        super().__init__(parent, flags)

        self._build_title_bar(title, icon, native_caption, dark, height)
        self._frame_helper = WindowsFrameHelper(
            self, self._title_bar, native_caption=native_caption,
            dark=dark, rounded=rounded, auto_theme=auto_theme)

        self._frame_helper.install()

    # ------------------------------------------------------------------ 构建
    def _build_title_bar(self, title, icon, native_caption, dark, height=None):
        self._title_bar = TitleBar(self, title=title, icon=icon, height=height,
                                   native_caption=native_caption, dark=dark)
        self.setWindowTitle(title or "")
        if icon is not None:
            self.setWindowIcon(icon)

        self.body = QWidget(self)
        self.body.setObjectName("TitleBarWindowBody")
        self.body.setAttribute(Qt.WA_StyledBackground, True)
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(0)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._title_bar)
        layout.addWidget(self.body, 1)
        if not _IS_WINDOWS:
            # 非 Windows 平台保留系统标题栏，隐藏自绘标题栏以免出现两条
            self._title_bar.hide()

    # ------------------------------------------------------------------ 属性
    @property
    def title_bar(self) -> TitleBar:
        return self._title_bar

    def set_title_bar_height(self, height: int):
        """修改标题栏高度；布局会自动重排并同步按钮命中区域。"""
        self._title_bar.set_title_bar_height(height)

    def title_bar_height(self) -> int:
        return self._title_bar.title_bar_height()

    def set_title(self, title: str):
        self._title_bar.set_title(title)
        self.setWindowTitle(title)

    def set_title_bar_icon(self, icon: Optional[QIcon]):
        self._title_bar.set_icon(icon)

    def set_dark(self, dark: bool):
        if self._frame_helper is not None:
            self._frame_helper.set_dark(dark)
        else:
            self._title_bar.set_dark(dark)

    def is_dark(self) -> bool:
        return self._title_bar.is_dark()


class TitleBarMainWindow(_WindowsFrameMixin, QMainWindow):
    """自带自定义标题栏的 QMainWindow。

    标题栏固定在窗口最顶端，通过 ``setContentsMargins()`` 为它留出高度，
    所以 ``menuBar()`` / ``statusBar()`` / dock 等 QMainWindow 功能都能照常
    使用（菜单栏会显示在标题栏下方）。标题栏高度用 ``height=`` 指定
    （逻辑像素，默认取 ``HEIGHT``），之后也可以通过 ``set_title_bar_height()`` 修改，
    标题栏几何与内容区边距会一起同步。
    """

    def __init__(self, title: str = "", icon: Optional[QIcon] = None,
                 parent=None, *, height: Optional[int] = None,
                 native_caption: bool = True,
                 dark: Optional[bool] = None, auto_theme: bool = True,
                 rounded: bool = True):
        flags = Qt.Window
        if _IS_WINDOWS:
            flags |= Qt.FramelessWindowHint
        super().__init__(parent, flags)

        self._title_bar = TitleBar(self, title=title, icon=icon, height=height,
                                   native_caption=native_caption, dark=dark,
                                   parent=self)
        bar_height = self._title_bar.title_bar_height()
        self._title_bar.setGeometry(0, 0, self.width(), bar_height)
        self._title_bar.raise_()
        self.setContentsMargins(0, bar_height, 0, 0)
        self._title_bar.heightChanged.connect(self._on_title_bar_height_changed)
        self.setWindowTitle(title or "")
        if icon is not None:
            self.setWindowIcon(icon)
        if not _IS_WINDOWS:
            # 非 Windows 平台保留系统标题栏，隐藏自绘标题栏以免出现两条
            self._title_bar.hide()
            self.setContentsMargins(0, 0, 0, 0)

        self._frame_helper = WindowsFrameHelper(
            self, self._title_bar, native_caption=native_caption,
            dark=dark, rounded=rounded, auto_theme=auto_theme)
        self._frame_helper.install()

    def _on_title_bar_height_changed(self, height: int):
        """标题栏高度变化：重新确定标题栏几何，并为内容区留出同样高度。"""
        title_bar = getattr(self, "_title_bar", None)
        if title_bar is None or title_bar.isHidden():
            return
        title_bar.setGeometry(0, 0, self.width(), height)
        title_bar.raise_()
        self.setContentsMargins(0, height, 0, 0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        title_bar = getattr(self, "_title_bar", None)
        if title_bar is not None:
            title_bar.setGeometry(0, 0, self.width(),
                                  title_bar.title_bar_height())
            title_bar.raise_()

    @property
    def title_bar(self) -> TitleBar:
        return self._title_bar

    def set_title_bar_height(self, height: int):
        """修改标题栏高度；标题栏几何与内容区边距会一起同步。"""
        self._title_bar.set_title_bar_height(height)

    def title_bar_height(self) -> int:
        return self._title_bar.title_bar_height()

    def set_title(self, title: str):
        self._title_bar.set_title(title)
        self.setWindowTitle(title)

    def set_title_bar_icon(self, icon: Optional[QIcon]):
        self._title_bar.set_icon(icon)

    def set_dark(self, dark: bool):
        if self._frame_helper is not None:
            self._frame_helper.set_dark(dark)
        else:
            self._title_bar.set_dark(dark)

    def is_dark(self) -> bool:
        return self._title_bar.is_dark()
