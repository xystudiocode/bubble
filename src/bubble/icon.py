from .QUI import *

from typing import Optional
from uiml import set_style

_FONT_FAMILIES = ["Segoe Fluent Icons", "Segoe MDL2 Assets"]

class FontIcon(QLabel):
    """图标字体标签（Segoe Fluent Icons / Segoe MDL2 Assets），支持原地旋转。

    angle 属性可直接交给 QPropertyAnimation 做旋转动画。
    icon_color / icon_size 也可由 qss 用 qproperty-* 覆盖。

    配色由 qss 决定：默认取 `.FontIcon`（或全局文字色）的 color；
    需要单独配色的位置在 qss 里用自己的 class 声明 color（如 `.ExpanderArrow`），
    代码只在显式传入 color 时才把颜色写进控件自身样式表。

    字号通过「控件自身样式表」设置：全局样式表里的 `* { font-size: ... }`
    会覆盖 setFont()，但覆盖不了控件自身样式表，因此图标字号不会被带跑。

    示例：
        icon = FontIcon("\uE799", size=24)                    # 颜色交给 qss 的 .FontIcon
        icon = FontIcon("\uE70D", size=12, color="#F7F7F7")   # 单独配色
        icon.set_angle(90)                                    # 原地旋转 90°
        # angle 是 Qt Property，可直接交给 QPropertyAnimation 做动画
    """

    STYLE_CLASS = "FontIcon"

    def __init__(self, icon="", size: int = 20, color: Optional[str] = None, parent=None):
        super().__init__(icon, parent)

        self._color = QColor(color) if color is not None else None
        self._icon_size = int(size)
        self._angle = 0.0
        self._pixmap = None
        self._pixmap_key = None

        self.setAlignment(Qt.AlignCenter)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
        self._apply_style()
        set_style(self, self.STYLE_CLASS)

    def _apply_style(self):
        """把字号写进控件自身样式表（优先级高于全局 `*` 规则）。

        只有显式指定颜色时才写入 color，否则交给 qss 的 `.FontIcon` 决定。
        """
        f = self.font()
        f.setPixelSize(self._icon_size)
        f.setFamilies(_FONT_FAMILIES)
        self.setFont(f)
        # 不在这里写 background：背景交给样式表按层级（level）决定
        css = f"font-size: {self._icon_size}px;"
        if self._color is not None:
            css += f" color: {self._color.name()};"
        self.setStyleSheet(css)
        self.updateGeometry()

    def _effective_color(self) -> QColor:
        """当前生效的图标颜色：显式颜色优先，否则取 qss 设置的前景色。"""
        if self._color is not None:
            return self._color
        return self.palette().color(self.foregroundRole())

    # --------------------------- 原地旋转 ---------------------------
    def get_angle(self) -> float:
        return self._angle

    def set_angle(self, angle: float):
        angle = float(angle)
        if angle != self._angle:
            self._angle = angle
            self.update()

    angle = Property(float, get_angle, set_angle)

    # --------------------------- 配色 / 字号 ---------------------------
    def get_icon_color(self) -> QColor:
        return self._effective_color()

    def set_icon_color(self, color):
        new_color = QColor(color) if color is not None else QColor()
        if not new_color.isValid():
            new_color = None
        if new_color != self._color:
            self._color = new_color
            # 旋转时由 _effective_color() 自绘；未旋转时 QLabel 取样式表的颜色
            self._apply_style()

    def get_icon_size(self) -> int:
        return self._icon_size

    def set_icon_size(self, size: int):
        size = int(size)
        if size != self._icon_size:
            self._icon_size = size
            self._apply_style()

    icon_color = Property(QColor, get_icon_color, set_icon_color)
    icon_size = Property(int, get_icon_size, set_icon_size)

    def _icon_pixmap(self) -> QPixmap:
        """先把图标按 0° 渲染成 pixmap，再整体旋转绘制。

        直接把文字交给旋转后的 painter 画，在部分平台上不会输出任何像素，
        因此这里始终先渲染成位图再旋转。
        """
        color = self._effective_color()
        dpr = self.devicePixelRatioF()
        key = (self.size(), self.text(), self.font().key(), color.rgba(), dpr)
        if self._pixmap is None or self._pixmap_key != key:
            pm = QPixmap(int(self.width() * dpr), int(self.height() * dpr))
            pm.setDevicePixelRatio(dpr)
            pm.fill(Qt.transparent)

            painter = QPainter(pm)
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setRenderHint(QPainter.TextAntialiasing, True)
            painter.setPen(color)
            painter.setFont(self.font())
            painter.drawText(QRect(QPoint(0, 0), self.size()), Qt.AlignCenter, self.text())
            painter.end()

            self._pixmap = pm
            self._pixmap_key = key
        return self._pixmap

    def changeEvent(self, event):
        # 主题 / 样式变化会改变 qss 决定的颜色，缓存的旋转位图必须失效
        if event.type() in (QEvent.PaletteChange, QEvent.StyleChange, QEvent.FontChange):
            self._pixmap = None
            self._pixmap_key = None
        super().changeEvent(event)

    def paintEvent(self, event):
        # 未旋转时走 QLabel 默认绘制，保证与普通图标标签完全一致
        if self._angle % 360.0 == 0.0:
            super().paintEvent(event)
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        rect = QRectF(self.rect())
        painter.translate(rect.center())
        painter.rotate(self._angle)
        painter.translate(-rect.center())
        painter.drawPixmap(0, 0, self._icon_pixmap())

class IconImage(QLabel):
    """内嵌图片图标（QLabel + QPixmap）。

    与 FontIcon（图标字体）不同，它不依赖图标字体，图片直接内嵌在控件里，
    因此完全不受全局 `* { font-size / font-family }` 之类规则影响。

    参数：
        image —— QPixmap / QIcon / 图片文件路径；None 表示暂无图片
        size  —— 目标尺寸：int（正方形）或 QSize；None 表示按原图尺寸

    示例：
        logo = IconImage("logo.png", size=48)                  # 文件路径 + 48×48
        logo = IconImage(QPixmap(48, 48), size=QSize(48, 48))  # QPixmap + 指定尺寸
        logo.set_angle(90)                                     # 原地旋转（可做动画）
    """

    def __init__(self, image=None, size=None, parent=None):
        super().__init__(parent)

        self._source = QPixmap()      # 原图
        self._icon_size = QSize()     # 空 QSize 表示按原图
        self._angle = 0.0

        self.setAlignment(Qt.AlignCenter)
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
        self.setMinimumWidth(0)

        if size is not None:
            self.set_icon_size(size)
        if image is not None:
            self.set_image(image)

    # --------------------------- 图片 ---------------------------
    def set_image(self, image):
        """设置图片：QPixmap / QIcon / 文件路径。"""
        if isinstance(image, QPixmap):
            pixmap = image
        elif isinstance(image, QIcon):
            size = self._icon_size if not self._icon_size.isEmpty() else QSize(64, 64)
            pixmap = image.pixmap(size)
        elif isinstance(image, str):
            pixmap = QPixmap(image)
        elif image is None:
            pixmap = QPixmap()
        else:
            raise TypeError("image 必须是 QPixmap / QIcon / 文件路径")

        self._source = pixmap
        self._refresh()

    def image(self) -> QPixmap:
        return self._source

    def has_image(self) -> bool:
        return not self._source.isNull()

    def _refresh(self):
        """按目标尺寸等比缩放后显示（保持宽高比）。"""
        if self._source.isNull():
            self.clear()
        else:
            if self._icon_size.isEmpty():
                shown = self._source
            else:
                shown = self._source.scaled(self._icon_size, Qt.KeepAspectRatio,
                                            Qt.SmoothTransformation)
            super().setPixmap(shown)
            self.setFixedSize(shown.size())
        self.updateGeometry()

    # --------------------------- 尺寸 ---------------------------
    def get_icon_size(self) -> QSize:
        return self._icon_size

    def set_icon_size(self, size):
        size = QSize(size, size) if isinstance(size, int) else QSize(size)
        if size != self._icon_size:
            self._icon_size = size
            self._refresh()

    icon_size = Property(QSize, get_icon_size, set_icon_size)

    # --------------------------- 原地旋转（与 FontIcon 一致，可交给动画） ---------------------------
    def get_angle(self) -> float:
        return self._angle

    def set_angle(self, angle: float):
        angle = float(angle)
        if angle != self._angle:
            self._angle = angle
            self.update()

    angle = Property(float, get_angle, set_angle)

    def paintEvent(self, event):
        # 未旋转时走 QLabel 默认绘制
        if self._angle % 360.0 == 0.0 or self.pixmap() is None:
            super().paintEvent(event)
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        rect = QRectF(self.rect())
        painter.translate(rect.center())
        painter.rotate(self._angle)
        painter.translate(-rect.center())
        painter.drawPixmap(rect, self.pixmap(), QRectF(self.pixmap().rect()))
