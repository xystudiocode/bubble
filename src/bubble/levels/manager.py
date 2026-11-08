"""pyside6_levels.manager —— “组件层级（level）”核心实现。

术语
====
- contribution（层级贡献）：一个组件为它的**子控件**增加的层级，默认 0。
  内置按钮等普通控件贡献为 0；自制卡片组件通常贡献为 1。
- raw / base level（基础层级）：控件自身的层级 = 祖先链上所有组件贡献之和。
  组件**自己的贡献不计入自身**，只作用于后代。
- defined levels（断点）：用户在 QSS 里通过 ``[level="N"]`` 声明过的层级集合，
  永远包含 0（默认配色）。
- style level（样式层级）：按“就近向下填充”规则映射后的层级，写入控件的
  动态属性 ``level``，供 QSS 选择器匹配；真实层级写入 ``rawLevel`` 便于调试。

填充规则
========
对某个断点集合 D（例如 {0, 1, 3}）和控件的基础层级 r：

    style(r) = max { d ∈ D | d <= r }

即：层级 1、3 有定义时，2 使用 1 的配色，4 使用 3 的配色；D 中只有 0
（用户没写任何额外断点）时，所有层级都落到 0，也就是默认规则。

为什么必须运行时计算
====================
QSS 没有“最近的更低断点”选择器；``[level=1]`` 这种**不带引号的数字值**
在 Qt 的 CSS 解析器里是非法语法，会导致整份样式表解析失败。因此本模块在
``setStyleSheet()`` 中把 ``[level=1]`` 规范化为 ``[level="1"]``，再把每个
控件解析后的样式层级写进 ``level`` 动态属性并重新 polish，从而让用户仍可
用自然写法书写选择器。
"""

from __future__ import annotations

import re
from typing import Iterable, Optional

from PySide6.QtCore import QEvent, QObject, Qt, QTimer, Signal
from PySide6.QtWidgets import QApplication, QWidget

__all__ = [
    "LevelManager",
    "normalize_level_selectors",
    "parse_defined_levels",
]

# 私有状态挂在控件实例上（不用动态属性，避免污染 QSS 选择器命名空间）
_CONTRIB_ATTR = "_pyside6_level_contribution"
_OVERRIDE_ATTR = "_pyside6_level_override"
_MANAGER_ATTR = "_pyside6_level_manager"

#: 不带引号的层级选择器（Qt 不接受，需要规范化）
_UNQUOTED_LEVEL_RE = re.compile(r"\[\s*level\s*=\s*(-?\d+)\s*\]")
#: 任意写法的层级选择器（用于收集断点）
_LEVEL_VALUE_RE = re.compile(
    r"""\[\s*level\s*=\s*(?:"(-?\d+)"|'(-?\d+)'|(-?\d+))\s*\]"""
)
_QSS_COMMENT_RE = re.compile(r"/\*.*?\*/", re.S)


def _strip_comments(qss: str) -> str:
    """去掉 QSS 注释，避免把注释里的示例选择器当成断点。"""
    return _QSS_COMMENT_RE.sub("", qss)


def normalize_level_selectors(qss: str) -> str:
    """把 Qt 不接受的 ``[level=1]`` 改写成 ``[level="1"]``。

    对已经带引号、以及非 level 的属性选择器不做任何改动。
    """
    return _UNQUOTED_LEVEL_RE.sub(
        lambda m: '[level="%d"]' % max(0, int(m.group(1))), qss
    )


def parse_defined_levels(qss: str) -> "list[int]":
    """从 QSS 文本中收集所有 ``[level=N]`` 断点，排序并保证包含 0。"""
    text = _strip_comments(qss)
    levels = {0}
    for match in _LEVEL_VALUE_RE.finditer(text):
        for group in match.groups():
            if group is not None:
                levels.add(max(0, int(group)))
                break
    return sorted(levels)


class LevelManager(QObject):
    """应用级单例：维护控件层级、解析断点、刷新 QSS 样式。"""

    #: 任意控件的层级或断点变化、并完成一次重算后发出（可用于调试面板刷新）
    levels_changed = Signal()

    def __init__(self, app: Optional[QApplication] = None) -> None:
        app = app or QApplication.instance()
        if app is None:
            raise RuntimeError("请先创建 QApplication，再使用 LevelManager")
        super().__init__(app)
        self._app: QApplication = app
        self._levels: "list[int]" = [0]
        self._raw_stylesheet: str = ""
        self._in_recompute: bool = False
        self._pending: bool = False

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(0)
        self._timer.timeout.connect(self.recompute)

        app.installEventFilter(self)
        # 接管之前已经创建的控件
        self.recompute()

    # ------------------------------------------------------------------ 单例
    @classmethod
    def instance(cls) -> "LevelManager":
        """取得（必要时创建）当前 QApplication 对应的管理器。"""
        app = QApplication.instance()
        if app is None:
            raise RuntimeError("请先创建 QApplication，再使用 LevelManager")
        manager = getattr(app, _MANAGER_ATTR, None)
        if manager is None:
            manager = cls(app)
            setattr(app, _MANAGER_ATTR, manager)
        return manager

    # ------------------------------------------------------------ 样式表/断点
    @property
    def stylesheet(self) -> str:
        """最近一次通过 :meth:`setStyleSheet` 传入的原始 QSS。"""
        return self._raw_stylesheet

    def defined_levels(self) -> "tuple[int, ...]":
        """当前断点集合（升序，必含 0）。"""
        return tuple(self._levels)

    def set_defined_levels(self, levels: Iterable[int]) -> None:
        """手动指定断点集合。

        适用于样式表不由 :meth:`setStyleSheet` 管理、或需要额外断点的场景。
        调用 :meth:`setStyleSheet` 会以 QSS 中解析出的断点**替换**本集合。
        """
        new_levels = sorted({0} | {max(0, int(level)) for level in levels})
        if new_levels != self._levels:
            self._levels = new_levels
            self.recompute()

    def setStyleSheet(self, qss: str) -> None:
        """设置应用样式表：收集断点 → 规范化选择器 → 设置样式表 → 重算。

        这是推荐的唯一入口。若直接调用 ``app.setStyleSheet()``，管理器无法
        知道断点，也无法把 ``[level=1]`` 规范化成 Qt 认识的写法。
        """
        self._raw_stylesheet = qss
        normalized = normalize_level_selectors(qss)
        self._levels = parse_defined_levels(normalized)
        # Qt 在 setStyleSheet 时会对已有控件整体重新应用样式；随后 recompute
        # 把新算出的 level 写进控件，并对发生变化的控件重新 polish。
        self._app.setStyleSheet(normalized)
        self.recompute()

    # ------------------------------------------------------------------ 层级
    def contribution(self, widget: QWidget) -> int:
        """控件为其子控件增加的层级（默认 0）。"""
        return int(getattr(widget, _CONTRIB_ATTR, 0))

    def set_contribution(self, widget: QWidget, contribution: int) -> None:
        """设置控件的层级贡献（≥0）。自制组件一般在 ``__init__`` 里调用。"""
        contribution = max(0, int(contribution))
        if getattr(widget, _CONTRIB_ATTR, None) != contribution:
            setattr(widget, _CONTRIB_ATTR, contribution)
            self.schedule()

    def override(self, widget: QWidget) -> Optional[int]:
        """控件的绝对基础层级覆盖；未设置时为 None。"""
        return getattr(widget, _OVERRIDE_ATTR, None)

    def set_override(self, widget: QWidget, level: Optional[int]) -> None:
        """强制指定控件的基础层级（绝对覆盖，不看父链）。

        典型用途：
        - 独立创建、尚无 parent 的控件；
        - 挂在主窗口下、但视觉上属于另一个层级的弹窗/浮层；
        - 组件内单独调整某个子控件的层级。
        传 ``None`` 取消覆盖。
        """
        if level is None:
            if getattr(widget, _OVERRIDE_ATTR, None) is not None:
                delattr(widget, _OVERRIDE_ATTR)
                self.schedule()
            return
        level = max(0, int(level))
        if getattr(widget, _OVERRIDE_ATTR, None) != level:
            setattr(widget, _OVERRIDE_ATTR, level)
            self.schedule()

    def raw_level(self, widget: QWidget) -> int:
        """控件自身的基础层级（祖先贡献之和；覆盖优先；不含自身贡献）。"""
        return self._raw_level(widget, {})

    def style_level(self, raw_level: int) -> int:
        """把基础层级按断点填充规则映射为样式层级。"""
        raw_level = max(0, int(raw_level))
        result = 0
        for level in self._levels:
            if level <= raw_level:
                result = level
            else:
                break
        return result

    def level(self, widget: QWidget) -> int:
        """控件当前应使用的样式层级（实时计算，不依赖事件循环）。"""
        return self.style_level(self.raw_level(widget))

    # ------------------------------------------------------------------ 刷新
    def schedule(self) -> None:
        """请求一次合并重算（0ms 单次定时器，适合 parent 尚未设置等异步场景）。"""
        if not self._timer.isActive():
            self._timer.start()

    def flush(self) -> None:
        """立即执行挂起的重算（测试、截图、需要同步读取 ``level`` 属性时使用）。"""
        self._timer.stop()
        self._pending = False
        self.recompute()

    def recompute(self) -> None:
        """重算所有控件的 rawLevel / level 动态属性，并在变化时重新 polish。"""
        if self._in_recompute:
            self._pending = True
            return
        self._timer.stop()
        self._in_recompute = True
        changed_widgets: "list[QWidget]" = []
        try:
            raw_cache: "dict[int, int]" = {}
            for widget in QApplication.allWidgets():
                try:
                    raw = self._raw_level(widget, raw_cache)
                    target = self.style_level(raw)
                    old_raw = widget.property("rawLevel")
                    old_level = widget.property("level")
                    if old_raw != raw:
                        widget.setProperty("rawLevel", raw)
                    if old_level != target:
                        widget.setProperty("level", target)
                    if old_raw != raw or old_level != target:
                        changed_widgets.append(widget)
                except RuntimeError:  # 底层 C++ 对象已销毁
                    continue
        finally:
            self._in_recompute = False

        if changed_widgets:
            # 除控件自身外，还要刷新它的后代：祖先的属性可能参与
            # `QFrame[level="1"] QPushButton` 这类后代选择器。
            self._refresh_styles(changed_widgets)
            self.levels_changed.emit()
        if self._pending:
            self._pending = False
            self.schedule()

    def _refresh_styles(self, changed_widgets: "list[QWidget]") -> None:
        """对“自身或祖先发生变化、且已经 polish 过”的控件重新 polish。

        从未 polish 过的控件不用处理：首次 show / 挂载 / grab 时的 polish
        会读到最新的 ``level`` 属性。遍历整棵控件树一次，避免逐个子树重复遍历。
        """
        changed_ids = {id(widget) for widget in changed_widgets}
        children: "dict[int, list[QWidget]]" = {}
        roots: "list[QWidget]" = []
        for widget in QApplication.allWidgets():
            try:
                parent = widget.parentWidget()
            except RuntimeError:
                continue
            if parent is None:
                roots.append(widget)
            else:
                children.setdefault(id(parent), []).append(widget)

        stack = [(root, False) for root in roots]
        while stack:
            widget, ancestor_changed = stack.pop()
            dirty = ancestor_changed or id(widget) in changed_ids
            if dirty:
                try:
                    if widget.testAttribute(Qt.WidgetAttribute.WA_WState_Polished):
                        self._repolish(widget)
                except RuntimeError:
                    continue
            for child in children.get(id(widget), ()):
                stack.append((child, dirty))

    # ------------------------------------------------------------------ 内部
    def _raw_level(self, widget: QWidget, cache: "dict[int, int]") -> int:
        key = id(widget)
        cached = cache.get(key)
        if cached is not None:
            return cached
        override = self.override(widget)
        if override is not None:
            value = override
        else:
            parent = widget.parentWidget()
            if parent is None:
                value = 0
            else:
                value = self._raw_level(parent, cache) + self.contribution(parent)
        cache[key] = value
        return value

    @staticmethod
    def _repolish(widget: QWidget) -> None:
        """动态属性变化后必须重新 polish，QSS 属性选择器才会重新匹配。"""
        try:
            style = widget.style()
            style.unpolish(widget)
            style.polish(widget)
            widget.update()
        except RuntimeError:
            pass

    # ------------------------------------------------------------------ 事件
    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        # parent 变化、子控件增删都会改变层级；用 0ms 定时器合并，避免构造期抖动
        event_type = event.type()
        if event_type in (
            QEvent.Type.ParentChange,
            QEvent.Type.ChildAdded,
            QEvent.Type.ChildRemoved,
        ):
            self.schedule()
        return False
