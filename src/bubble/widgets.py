from .QUI import *
from .i18n import get_lang
from dataclasses import dataclass
import math

__all__ = ['VScrollArea', 'HScrollArea', 'UnitInputLayout', 'ToggleSwitch', 'DevFlagCard']

class VScrollArea(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        # 隐藏横向滚动条
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)  # 始终禁用水平滚动条
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)     # 按需显示垂直滚动条

class HScrollArea(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        # 隐藏纵向滚动条
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
          
class UnitInputLayout(QLayout):
    '''单位输入行布局：文本与下拉框使用真实尺寸，输入框拉伸填充空白，整行占满可用宽度'''
    def __init__(self, parent=None):
        super().__init__(parent)
        self._item_list = []         # 存储所有子项
        self._row_breaks = []        # 记录每行结束的索引位置（记录上一行最后一个项的索引）
        self._stretch_widgets = []   # 需要在行内拉伸填充剩余空间的控件
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item: QLayoutItem):
        '''添加子项到列表末尾'''
        self._item_list.append(item)

    def addWidget(self, widget: QWidget, stretch: int = 0):
        '''
        添加控件
        
        Args:
            widget: 要添加的控件
            stretch: 大于 0 时该控件会拉伸填充行内的剩余空间
        '''
        super().addWidget(widget)
        if stretch > 0:
            self._stretch_widgets.append(widget)

    def _is_stretch_item(self, item: QLayoutItem) -> bool:
        '''判断子项是否为需要拉伸填充剩余空间的控件'''
        widget = item.widget()
        return widget is not None and any(widget is w for w in self._stretch_widgets)

    def newRow(self):
        '''标记换行位置'''
        if self._item_list:  # 只有在有子项时才记录换行
            # 记录当前最后一个项的索引（从0开始）
            last_index = len(self._item_list) - 1
            # 如果还没有记录换行，或者当前最后一个项不在最近记录的换行中
            if not self._row_breaks or last_index > self._row_breaks[-1]:
                self._row_breaks.append(last_index)

    def count(self):
        '''返回子项数量'''
        return len(self._item_list)

    def itemAt(self, index):
        '''获取指定索引的子项'''
        if 0 <= index < len(self._item_list):
            return self._item_list[index]
        return None

    def takeAt(self, index):
        '''移除并返回指定索引的子项'''
        if 0 <= index < len(self._item_list):
            item = self._item_list.pop(index)

            # 不再追踪被移除子项的拉伸设置
            widget = item.widget()
            if widget is not None:
                self._stretch_widgets = [w for w in self._stretch_widgets if w is not widget]
            
            # 移除后需要更新换行标记
            for i in range(len(self._row_breaks)):
                if self._row_breaks[i] >= index:
                    self._row_breaks[i] -= 1
            
            # 移除已经无效的换行标记（如果换行标记指向的索引已经不存在）
            self._row_breaks = [r for r in self._row_breaks if r < len(self._item_list)]
            
            return item
        return None

    def sizeHint(self):
        '''返回布局的首选大小'''
        if not self._item_list:
            return QSize(0, 0)
        
        # 计算行数和每行的尺寸
        rows = self._get_rows()
        
        # 计算总宽度（取最宽的行）
        max_width = 0
        for row_items in rows:
            row_width = sum(item.sizeHint().width() for item in row_items)
            if row_items:  # 加上行内间距
                row_width += self.spacing() * (len(row_items) - 1)
            max_width = max(max_width, row_width)
        
        # 计算总高度（每行高度之和 + 行间距）
        total_height = 0
        for i, row_items in enumerate(rows):
            if row_items:
                row_height = max(item.sizeHint().height() for item in row_items)
                total_height += row_height
                if i < len(rows) - 1:  # 不是最后一行，添加行间距
                    total_height += self.spacing()
        
        # 加上边距
        margins = self.contentsMargins()
        return QSize(
            max_width + margins.left() + margins.right(),
            total_height + margins.top() + margins.bottom()
        )

    def _get_rows(self):
        '''将子项按行分组'''
        if not self._item_list:
            return []
        
        rows = []
        start_idx = 0
        
        # 根据换行标记分割行
        for break_idx in self._row_breaks:
            if break_idx < len(self._item_list):
                rows.append(self._item_list[start_idx:break_idx + 1])
                start_idx = break_idx + 1
        
        # 添加最后一行（如果有剩余项）
        if start_idx < len(self._item_list):
            rows.append(self._item_list[start_idx:])
        
        # 如果没有任何换行标记，所有项都在一行
        if not self._row_breaks and self._item_list:
            rows.append(self._item_list)
        
        return rows

    def setGeometry(self, rect: QRect):
        '''核心方法，按行排列所有子项：固定尺寸子项保持真实尺寸，可拉伸子项填充剩余空间'''
        super().setGeometry(rect)
        
        if not self._item_list:
            return
        
        # 获取可用区域（排除边距）
        margins = self.contentsMargins()
        available_rect = rect.adjusted(
            margins.left(),
            margins.top(),
            -margins.right(),
            -margins.bottom()
        )
        
        spacing = self.spacing()
        y = available_rect.y()
        
        # 遍历每一行
        for row_items in self._get_rows():
            if not row_items:
                continue
            
            # 计算当前行的最大高度
            row_height = max(item.sizeHint().height() for item in row_items)
            
            stretch_flags = [self._is_stretch_item(item) for item in row_items]
            stretch_count = sum(stretch_flags)
            
            # 固定尺寸子项占用真实尺寸，剩余空间由可拉伸子项均分
            fixed_width = sum(item.sizeHint().width() for item, is_stretch in zip(row_items, stretch_flags) if not is_stretch)
            remaining_width = max(0, available_rect.width() - fixed_width - spacing * (len(row_items) - 1))
            stretch_sizes = []
            if stretch_count:
                base_size, extra = divmod(remaining_width, stretch_count)
                # 多余的像素分给前面的拉伸项，保证整行占满可用宽度
                stretch_sizes = [base_size + 1] * extra + [base_size] * (stretch_count - extra)
            
            row_x = available_rect.x()
            for item, is_stretch in zip(row_items, stretch_flags):
                if is_stretch:
                    item_width = stretch_sizes.pop(0)
                else:
                    item_width = item.sizeHint().width()
                item_height = item.sizeHint().height()
                # 垂直居中
                item_y = y + (row_height - item_height) // 2
                item.setGeometry(QRect(row_x, item_y, item_width, item_height))
                row_x += item_width + spacing
            
            # 换行：更新y坐标，重置x坐标
            y += row_height + spacing

    def addUnitRow(self, text: str, input: QLineEdit, unit: QComboBox):
        '''添加单位选择控件：文本与下拉框使用真实尺寸，输入框拉伸填充空白'''
        self.newRow() # 换行
        self.addWidget(QLabel(text + ': '))
        self.addWidget(input, stretch=1)
        self.addWidget(unit)

@dataclass
class _Colors:
    track: QColor
    border: QColor
    thumb: QColor
    label: QColor

    def copy(self) -> "_Colors":
        return _Colors(
            QColor(self.track), QColor(self.border),
            QColor(self.thumb), QColor(self.label)
        )

def _mix_color(a: QColor, b: QColor, t: float) -> QColor:
    """在 sRGB 空间混合两个颜色（包含 alpha）。"""
    t = max(0.0, min(1.0, float(t)))
    return QColor.fromRgbF(
        a.redF() + (b.redF() - a.redF()) * t,
        a.greenF() + (b.greenF() - a.greenF()) * t,
        a.blueF() + (b.blueF() - a.blueF()) * t,
        a.alphaF() + (b.alphaF() - a.alphaF()) * t,
    )

class ToggleSwitch(QAbstractButton):
    """胶囊形开关，支持悬浮和拖动指示器。

    禁用（``setEnabled(False)``）时：用户无法用鼠标 / 键盘切换状态，
    但程序仍可通过 ``setChecked()`` 修改；配色由 qss 的 ``visualState`` 为
    ``disabled-off`` / ``disabled-on`` 的规则决定。
    """

    stateChanged = Signal(bool)

    # -- 几何尺寸 -----------------------------------------------------------
    _DEFAULT_GAP = 4.0          # 默认态：填充区边缘到指示器边缘
    _DEFAULT_RADIUS_EXTRA = 1.0 # 默认圆形额外增加的半径
    _HOVER_GAP = 2.0            # 悬浮态：填充区边缘到指示器边缘
    _PRESS_STRETCH = 4.0        # 按下时向中间额外拉伸的宽度
    _STRETCH_DURATION = 125     # 按下 / 松开拉伸动画时长（毫秒）
    _HITBOX_PADDING_Y = 8.0     # 碰撞箱上下额外扩展
    _LABEL_GAP = 12.0           # 文字与开关框的间距
    _BORDER_WIDTH = 1.0

    # 兜底颜色：样式表生效前使用，也用于没有加载任何样式表的场景。
    _OFF_TRACK = QColor("#272727")
    _OFF_BORDER = QColor("#9b9da6")
    _OFF_THUMB = QColor("#cecece")
    _OFF_LABEL = QColor("#ffffff")

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        state_text: tuple[str, str] | None = None,
        checked: bool = False,
        track_width: int = 40,
        track_height: int = 20,
        animation_duration: int = 250,
        easing_curve: QEasingCurve | int = QEasingCurve.OutCubic,
    ) -> None:
        super().__init__(parent)

        state_text = (get_lang('off', default='Off'), get_lang('on', default='On')) if state_text is None else state_text
        self._off_text, self._on_text = (str(state_text[0]), str(state_text[1]))

        self.setCheckable(True)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover, True)

        # ``track_width`` / ``track_height`` 表示胶囊填充区域尺寸。
        # 1px 边框绘制在填充区外侧，因此默认 track_height=20 时
        # 可见外框高度为 20 + 2px。
        self._track_width = max(32, int(track_width))
        self._track_height = max(12, int(track_height))
        self._border_width = float(self._BORDER_WIDTH)
        self._outer_height = self._track_height + 2.0 * self._border_width
        self._animation_duration = max(0, int(animation_duration))
        self._easing = QEasingCurve(easing_curve)
        self._label_gap = self._LABEL_GAP

        # 计算指示器尺寸
        self._thumb_normal = max(
            1.0,
            self._track_height
            - 2.0 * self._DEFAULT_GAP
            + 2.0 * self._DEFAULT_RADIUS_EXTRA,
        )
        self._thumb_hover = max(1.0, self._track_height - 2.0 * self._HOVER_GAP)
        self._thumb_pressed_w = self._thumb_hover + self._PRESS_STRETCH
        if self._track_width <= self._thumb_pressed_w:
            self._track_width = int(math.ceil(self._thumb_pressed_w)) + 20

        # 字体确定后再测量布局几何
        self._label_width = 0.0
        self._outer_left = 0.0
        self._body_left = 0.0
        self._left_center = 0.0
        self._right_center = 0.0
        self._center = 0.0
        self._geometry_ready = False

        # 交互状态
        self._hovered = False
        self._mouse_down = False
        self._press_mouse_x = 0.0
        self._press_center = 0.0
        self._press_direction = 1.0   # +1：关态向右拉伸；-1：开态向左拉伸
        self._stretch_direction = 1.0
        self._stretch = 0.0
        self._keyboard_focus = False

        # QSS 目标颜色和实际绘制颜色（颜色过渡时使用）
        self._target_colors = _Colors(
            self._OFF_TRACK, self._OFF_BORDER, self._OFF_THUMB, self._OFF_LABEL
        )
        self._display_colors = self._target_colors.copy()
        self._suppress_color_sync = False
        self._repolishing = False

        # 动画对象
        self._slide_anim: QVariantAnimation | None = None
        self._stretch_anim: QVariantAnimation | None = None
        self._color_anim: QVariantAnimation | None = None
        self._color_from = self._display_colors.copy()
        self._color_to = self._display_colors.copy()

        font = QFont(self.font())
        font.setWeight(QFont.Medium)
        self.setFont(font)

        self._set_visual_state("off")
        self.setAccessibleName("开关")

        self._refresh_size()
        self._sync_display_colours()

        # 基类信号还可用于键盘和程序化触发
        self.pressed.connect(self._update_visual_state)
        self.released.connect(self._update_visual_state)
        self.toggled.connect(self._on_toggled)

        if checked:
            self.setChecked(True)

    # ------------------------------------------------------------------ API
    def set_animation_duration(self, milliseconds: int) -> None:
        """设置状态切换动画时长（毫秒，默认 250）。"""
        self._animation_duration = max(0, int(milliseconds))

    def animation_duration(self) -> int:
        return self._animation_duration

    def set_easing_curve(self, curve: QEasingCurve | int) -> None:
        """设置状态切换使用的缓动曲线。"""
        self._easing = QEasingCurve(curve)

    def easing_curve(self) -> QEasingCurve:
        return QEasingCurve(self._easing)

    def set_state_text(self, state_text: tuple[str, str]) -> None:
        """按 ``(关文本, 开文本)`` 设置状态文字。"""
        if not isinstance(state_text, (tuple, list)) or len(state_text) != 2:
            raise ValueError("state_text 必须是 (关文本, 开文本) 二元组")
        self._off_text, self._on_text = (str(state_text[0]), str(state_text[1]))
        self._refresh_size()
        self.update()

    def state_text(self) -> tuple[str, str]:
        return self._off_text, self._on_text

    def sizeHint(self) -> QSize:
        metrics = QFontMetricsF(self.font())
        label_w = math.ceil(max(
            metrics.horizontalAdvance(self._off_text),
            metrics.horizontalAdvance(self._on_text),
        ))
        outer_w = self._track_width + 2.0 * self._border_width
        width = label_w + self._label_gap + outer_w
        height = max(self._outer_height, metrics.height()) + 2 * self._HITBOX_PADDING_Y
        height = int(round(height))
        # 保证轨道上下留白为整数距离。
        if (height - int(round(self._outer_height))) % 2:
            height += 1
        return QSize(int(math.ceil(width)), height)

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    # -- QSS 颜色属性 -------------------------------------------------------
    def _set_target_colour(self, field: str, value) -> None:
        c = QColor(value)
        if c == getattr(self._target_colors, field):
            return
        setattr(self._target_colors, field, c)
        self._on_target_colour_changed()

    def _get_track_color(self) -> QColor:
        return QColor(self._target_colors.track)

    def _set_track_color(self, value) -> None:
        self._set_target_colour("track", value)

    def _get_border_color(self) -> QColor:
        return QColor(self._target_colors.border)

    def _set_border_color(self, value) -> None:
        self._set_target_colour("border", value)

    def _get_thumb_color(self) -> QColor:
        return QColor(self._target_colors.thumb)

    def _set_thumb_color(self, value) -> None:
        self._set_target_colour("thumb", value)

    def _get_label_color(self) -> QColor:
        return QColor(self._target_colors.label)

    def _set_label_color(self, value) -> None:
        self._set_target_colour("label", value)

    # 这些属性由 STYLE_SHEET 中的 qproperty-trackColor 等声明提供。
    trackColor = Property(QColor, _get_track_color, _set_track_color)
    borderColor = Property(QColor, _get_border_color, _set_border_color)
    thumbColor = Property(QColor, _get_thumb_color, _set_thumb_color)
    labelColor = Property(QColor, _get_label_color, _set_label_color)

    # ------------------------------------------------------------------ Qt
    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)

        if event.type() == QEvent.EnabledChange:
            # 禁用时清除悬浮 / 按下 / 键盘焦点状态，避免交互视觉残留。
            self._hovered = False
            self._mouse_down = False
            self._keyboard_focus = False
            self._stop_stretch_animation()
            self._stretch = 0.0
            self.setCursor(Qt.PointingHandCursor if self.isEnabled() else Qt.ArrowCursor)
            self._update_visual_state()
            self._sync_display_colours()
            self.update()
            return

        if event.type() in (QEvent.FontChange, QEvent.StyleChange):
            self._refresh_size()
            if event.type() == QEvent.StyleChange:
                self._sync_display_colours()
            self.update()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._apply_visual_state(force=True)
        self._refresh_size()
        self._sync_display_colours()

    def enterEvent(self, event) -> None:
        super().enterEvent(event)
        if not self.isEnabled():
            return
        if not self._hovered:
            self._hovered = True
            if not self._mouse_down:
                self._stop_color_animation(snap=True)
            self._update_visual_state()
            self.update()

    def focusInEvent(self, event) -> None:
        super().focusInEvent(event)
        self._keyboard_focus = event.reason() in (
            Qt.TabFocusReason,
            Qt.BacktabFocusReason,
            Qt.ShortcutFocusReason,
        )
        self.update()

    def focusOutEvent(self, event) -> None:
        super().focusOutEvent(event)
        self._keyboard_focus = False
        self.update()

    def leaveEvent(self, event) -> None:
        super().leaveEvent(event)
        if self._hovered:
            self._hovered = False
            if not self._mouse_down:
                self._stop_color_animation(snap=True)
            self._update_visual_state()
            self.update()

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.LeftButton or not self.isEnabled():
            event.ignore()
            return
        if not self.rect().contains(event.position().toPoint()):
            event.ignore()
            return

        # 新的交互会终止正在运行的过渡动画。
        self._stop_slide_animation()
        self._stop_color_animation(snap=True)

        self.setFocus(Qt.MouseFocusReason)
        self._mouse_down = True
        self._press_mouse_x = event.position().x()
        self._press_direction = 1.0 if not self.isChecked() else -1.0
        self._stretch_direction = self._press_direction
        self._press_center = self._center
        self._animate_stretch(1.0)
        self.setDown(True)
        self._update_visual_state()
        self.update()
        event.accept()
        self.pressed.emit()

    def mouseMoveEvent(self, event) -> None:
        if not self._mouse_down:
            event.ignore()
            return
        dx = event.position().x() - self._press_mouse_x
        self._center = self._clamp_base_center(self._press_center + dx)
        self.update()
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        if (
            event.button() != Qt.LeftButton
            or not self._mouse_down
            or not self.isEnabled()
        ):
            event.ignore()
            return

        # 拉伸在 125 毫秒内收回，状态切换的滑动和颜色过渡则按各自时长运行。
        self._mouse_down = False
        self._animate_stretch(0.0)
        self.setDown(False)
        self.nextCheckState()
        self._update_visual_state()
        self.update()
        self.released.emit()
        self.clicked.emit()
        event.accept()

    def keyPressEvent(self, event) -> None:
        if not self.isEnabled():
            event.ignore()
            return
        # 空格 / 回车的键盘行为交给 QAbstractButton 处理。
        if event.key() in (Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter):
            if not event.isAutoRepeat():
                self.update()
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event) -> None:
        if not self.isEnabled():
            event.ignore()
            return
        super().keyReleaseEvent(event)
        self.update()

    def hitButton(self, pos) -> bool:
        # 整个控件矩形（含左侧文字和上下各 8px 留白）都是碰撞箱。
        point = pos.toPoint() if hasattr(pos, "toPoint") else pos
        return self.rect().contains(point)

    # ------------------------------------------------------------- 几何计算
    def _refresh_size(self) -> None:
        metrics = QFontMetricsF(self.font())
        label_w = math.ceil(max(
            metrics.horizontalAdvance(self._off_text),
            metrics.horizontalAdvance(self._on_text),
        ))
        outer_w = self._track_width + 2.0 * self._border_width
        width = label_w + self._label_gap + outer_w
        height = max(self._outer_height, metrics.height()) + 2 * self._HITBOX_PADDING_Y
        height = int(round(height))
        if (height - int(round(self._outer_height))) % 2:
            height += 1
        hint = QSize(int(math.ceil(width)), height)

        old_size = self.size()
        old_body_left = self._body_left
        if self.size() != hint:
            self.setFixedSize(hint)

        self._label_width = label_w
        self._outer_left = label_w + self._label_gap
        self._body_left = self._outer_left + self._border_width
        self._left_center = self._body_left + self._track_height / 2.0
        self._right_center = (
            self._body_left + self._track_width - self._track_height / 2.0
        )
        self._center += self._body_left - old_body_left

        geometry_changed = (
            old_size != hint or abs(self._body_left - old_body_left) > 0.001
        )
        if not self._geometry_ready:
            self._center = self._right_center if self.isChecked() else self._left_center
            self._geometry_ready = True
        elif (
            geometry_changed
            and self._slide_anim is None
            and self._stretch_anim is None
            and not self._mouse_down
            and self._stretch <= 0.001
        ):
            self._center = self._right_center if self.isChecked() else self._left_center

    def _outer_rect(self) -> QRectF:
        y = (self.height() - self._outer_height) / 2.0
        return QRectF(
            self._outer_left,
            y,
            self._track_width + 2.0 * self._border_width,
            self._outer_height,
        )

    def _body_rect(self) -> QRectF:
        return self._outer_rect().adjusted(
            self._border_width,
            self._border_width,
            -self._border_width,
            -self._border_width,
        )

    def _thumb_metrics(self) -> tuple[float, float, float]:
        """返回当前拉伸量对应的（宽、高、X 偏移）。"""
        stretched = self._hovered or self._mouse_down
        rest = self._thumb_hover if stretched else self._thumb_normal
        s = max(0.0, min(1.0, self._stretch))
        width = rest + (self._thumb_pressed_w - rest) * s
        height = rest + (self._thumb_hover - rest) * s
        offset = (
            self._stretch_direction
            * (self._thumb_pressed_w - self._thumb_hover)
            / 2.0
            * s
        )
        return width, height, offset

    def _thumb_rect(self) -> QRectF:
        track = self._body_rect()
        width, height, offset = self._thumb_metrics()
        center = self._center + offset
        low = track.left() + width / 2.0
        high = track.right() - width / 2.0
        if high < low:
            high = low
        center = max(low, min(high, center))
        return QRectF(
            center - width / 2.0,
            track.center().y() - height / 2.0,
            width,
            height,
        )

    def _clamp_base_center(self, center: float) -> float:
        track = self._body_rect()
        width, _height, offset = self._thumb_metrics()
        low = track.left() + width / 2.0 - offset
        high = track.right() - width / 2.0 - offset
        if high < low:
            high = low
        return max(low, min(high, float(center)))

    def _target_center(self, checked: bool) -> float:
        return self._right_center if checked else self._left_center

    # -------------------------------------------------------------- 颜色状态
    def _set_visual_state(self, state: str) -> None:
        if self.property("visualState") != state:
            self.setProperty("visualState", state)
            self._repolish()

    def _apply_visual_state(self, force: bool = False) -> None:
        if not self.isEnabled():
            # 禁用态与开 / 关组合，颜色由 qss 中 disabled-on / disabled-off 选择器提供
            state = "disabled-on" if self.isChecked() else "disabled-off"
        elif self._mouse_down:
            state = "on-pressed" if self.isChecked() else "off-pressed"
        elif self._hovered:
            state = "on-hover" if self.isChecked() else "off-hover"
        else:
            state = "on" if self.isChecked() else "off"
        if force and self.property("visualState") == state:
            self._repolish()
        else:
            self._set_visual_state(state)

    def _update_visual_state(self) -> None:
        self._apply_visual_state()
        self.update()

    def _repolish(self) -> None:
        if self._repolishing:
            return
        self._repolishing = True
        try:
            self.style().unpolish(self)
            self.style().polish(self)
        finally:
            self._repolishing = False

    def _on_target_colour_changed(self) -> None:
        # 由样式表 qproperty-* setter 在重新 polish 时调用。
        if self._suppress_color_sync:
            return
        if (
            self._color_anim is not None
            and self._color_anim.state() == QVariantAnimation.Running
        ):
            # 运行期间的外部配色变化不应让动画继续追逐旧目标色。
            self._color_to = self._target_colors.copy()
            return
        self._display_colors = self._target_colors.copy()
        self.update()

    def _sync_display_colours(self) -> None:
        if self._suppress_color_sync:
            return
        if self._color_anim is None:
            self._display_colors = self._target_colors.copy()
            self.update()

    # ------------------------------------------------------------ 滑动动画
    def _on_toggled(self, checked: bool) -> None:
        self._refresh_size()
        target_center = self._target_center(checked)

        # 先通知外部状态已经变化，再启动滑动 / 颜色动画，这样在槽函数里
        # 读到的 isChecked() 一定是新状态。
        self.stateChanged.emit(bool(checked))

        # 隐藏状态下直接切换，避免第一次显示时动画已经播放了一部分。
        if not self.isVisible():
            self._stop_slide_animation()
            self._stop_stretch_animation()
            self._stop_color_animation(snap=False)
            self._stretch = 0.0
            self._suppress_color_sync = True
            try:
                self._apply_visual_state(force=True)
                self._center = target_center
                self._display_colors = self._target_colors.copy()
            finally:
                self._suppress_color_sync = False
            self.update()
            return

        start_colors = self._display_colors.copy()
        start_center = self._center

        # 在切换新状态时暂时冻结颜色同步，以便捕获新的目标配色，
        # 然后再向目标颜色插值。
        self._suppress_color_sync = True
        try:
            self._stop_slide_animation()
            self._stop_color_animation(snap=False)
            self._apply_visual_state(force=True)
            target_colors = self._target_colors.copy()
        finally:
            self._suppress_color_sync = False

        if self._animation_duration == 0:
            self._center = target_center
            self._display_colors = target_colors
            self.update()
            return

        if abs(target_center - start_center) > 0.01:
            anim = QVariantAnimation(self)
            anim.setStartValue(0.0)
            anim.setEndValue(1.0)
            anim.setDuration(self._animation_duration)
            anim.setEasingCurve(self._easing)
            anim.valueChanged.connect(
                lambda value: self._on_slide_tick(value, start_center, target_center)
            )
            anim.finished.connect(
                lambda: self._on_slide_finished(target_center)
            )
            self._slide_anim = anim
            anim.start()
        else:
            self._center = target_center
            self.update()

        self._start_color_animation(start_colors, target_colors)

    def _on_slide_tick(self, value, start_center: float, target_center: float) -> None:
        center = start_center + (target_center - start_center) * float(value)
        # OutBack 等缓动曲线可能过冲，这里仍把指示器限制在胶囊内。
        self._center = self._clamp_base_center(center)
        self.update()

    def _on_slide_finished(self, target_center: float) -> None:
        self._center = target_center
        self._slide_anim = None
        self.update()

    def _stop_slide_animation(self) -> None:
        if self._slide_anim is not None:
            anim = self._slide_anim
            self._slide_anim = None
            anim.stop()
            anim.deleteLater()

    # -- 按下 / 松开拉伸 ---------------------------------------------------
    def _animate_stretch(self, target: float) -> None:
        target = max(0.0, min(1.0, float(target)))
        self._stop_stretch_animation()
        start = self._stretch
        if abs(target - start) <= 0.001:
            self._stretch = target
            self.update()
            return

        duration = self._STRETCH_DURATION
        if duration <= 0:
            self._stretch = target
            self.update()
            return

        anim = QVariantAnimation(self)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setDuration(duration)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.valueChanged.connect(
            lambda value: self._on_stretch_tick(value, start, target)
        )
        anim.finished.connect(lambda: self._on_stretch_finished(target))
        self._stretch_anim = anim
        anim.start()

    def _on_stretch_tick(self, value, start: float, target: float) -> None:
        self._stretch = start + (target - start) * float(value)
        self.update()

    def _on_stretch_finished(self, target: float) -> None:
        self._stretch = target
        self._stretch_anim = None
        self.update()

    def _stop_stretch_animation(self) -> None:
        if self._stretch_anim is not None:
            anim = self._stretch_anim
            self._stretch_anim = None
            anim.stop()
            anim.deleteLater()

    def _start_color_animation(self, start: _Colors, target: _Colors) -> None:
        self._stop_color_animation(snap=False)
        self._color_from = start.copy()
        self._color_to = target.copy()
        if self._animation_duration == 0:
            self._display_colors = target.copy()
            self.update()
            return

        anim = QVariantAnimation(self)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setDuration(self._animation_duration)
        anim.setEasingCurve(self._easing)
        anim.valueChanged.connect(self._on_color_tick)
        anim.finished.connect(self._on_color_finished)
        self._color_anim = anim
        anim.start()

    def _on_color_tick(self, value) -> None:
        t = float(value)
        self._display_colors = _Colors(
            _mix_color(self._color_from.track, self._color_to.track, t),
            _mix_color(self._color_from.border, self._color_to.border, t),
            _mix_color(self._color_from.thumb, self._color_to.thumb, t),
            _mix_color(self._color_from.label, self._color_to.label, t),
        )
        self.update()

    def _on_color_finished(self) -> None:
        self._display_colors = self._color_to.copy()
        self._color_anim = None
        self.update()

    def _stop_color_animation(self, snap: bool) -> None:
        if self._color_anim is not None:
            anim = self._color_anim
            self._color_anim = None
            anim.stop()
            anim.deleteLater()
        if snap:
            self._sync_display_colours()

    # --------------------------------------------------------------- 绘制
    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)

        outer = self._outer_rect()
        body = self._body_rect()
        border = self._display_colors.border

        # 1px 边框位于 20px 填充区域外侧。
        if border.alpha() > 0:
            outer_path = QPainterPath()
            outer_path.addRoundedRect(
                outer, outer.height() / 2.0, outer.height() / 2.0
            )
            painter.fillPath(outer_path, border)

        body_path = QPainterPath()
        body_path.addRoundedRect(body, body.height() / 2.0, body.height() / 2.0)
        painter.fillPath(body_path, self._display_colors.track)

        # 圆形指示器。
        painter.setPen(Qt.NoPen)
        painter.setBrush(self._display_colors.thumb)
        painter.drawEllipse(self._thumb_rect())

        # 左侧文字。
        painter.setFont(self.font())
        painter.setPen(self._display_colors.label)
        label_rect = QRectF(
            0.0,
            0.0,
            max(0.0, self._label_width),
            float(self.height()),
        )
        text = self._on_text if self.isChecked() else self._off_text
        painter.drawText(
            label_rect,
            Qt.AlignLeft | Qt.AlignVCenter,
            text,
        )

        if self.hasFocus() and self._keyboard_focus:
            focus_color = QColor(self._display_colors.label)
            focus_color.setAlpha(150)
            focus_pen = QPen(focus_color)
            focus_pen.setWidthF(1.0)
            painter.setPen(focus_pen)
            painter.setBrush(Qt.NoBrush)
            focus_path = QPainterPath()
            fr = body.adjusted(1.5, 1.5, -1.5, -1.5)
            focus_path.addRoundedRect(fr, fr.height() / 2.0, fr.height() / 2.0)
            painter.drawPath(focus_path)
