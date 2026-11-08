"""pyside6_levels.component —— 声明式组件 API。

用法一：类装饰器（推荐，自制组件“自己设置 +1”）

    @level_component(contribution=1)
    class Card(QFrame):
        ...

用法二：给任意内置控件/实例单独设置

    btn = QPushButton("普通按钮")          # 默认贡献 0
    manager.set_contribution(btn, 0)
    manager.set_override(inner_btn, 0)     # 只改这一个子控件的层级

用法三：不带参数时读取类属性 ``level_contribution``

    @level_component
    class Card(QFrame):
        level_contribution = 1
"""

from __future__ import annotations

import functools
from typing import Callable, Optional, TypeVar

from PySide6.QtWidgets import QWidget

from .manager import LevelManager

__all__ = [
    "level_component",
    "set_contribution",
    "set_level",
    "raw_level_of",
    "level_of",
]

_T = TypeVar("_T", bound=type)


def level_component(
    cls: Optional[_T] = None,
    *,
    contribution: Optional[int] = None,
    level: Optional[int] = None,
):
    """类装饰器：把这个组件类标记为“为子控件增加 ``contribution`` 层”。

    :param contribution: 层级贡献（≥0）。省略时读取类属性 ``level_contribution``。
    :param level: 需要强制指定该组件自身的基础层级时传入（等价于
        :meth:`LevelManager.set_override`）。

    装饰器在实例 ``__init__`` 之后生效，因此即使子控件在构造函数里创建、
    或实例尚无 parent，后续事件循环也会自动补齐层级。
    """

    def decorate(component_cls: _T) -> _T:
        # 类自己定义了 __init__ 就包装它；否则走父类（QWidget/QFrame）的初始化。
        own_init = component_cls.__dict__.get("__init__")

        def __init__(self, *args, **kwargs):
            if own_init is not None:
                own_init(self, *args, **kwargs)
            else:
                super(component_cls, self).__init__(*args, **kwargs)
            manager = LevelManager.instance()
            value = contribution
            if value is None:
                value = int(getattr(type(self), "level_contribution", 0))
            manager.set_contribution(self, value)
            if level is not None:
                manager.set_override(self, level)

        if own_init is not None:
            __init__ = functools.wraps(own_init)(__init__)

        component_cls.__init__ = __init__  # type: ignore[method-assign]
        if contribution is not None:
            component_cls.level_contribution = contribution  # type: ignore[attr-defined]
        return component_cls

    if cls is None:
        return decorate
    return decorate(cls)


# --------------------------------------------------------------------- 便捷函数
def set_contribution(widget: QWidget, contribution: int) -> None:
    """设置控件的层级贡献（≥0）。"""
    LevelManager.instance().set_contribution(widget, contribution)


def set_level(widget: QWidget, level: Optional[int]) -> None:
    """强制指定控件的基础层级（绝对覆盖父链），传 None 取消。"""
    LevelManager.instance().set_override(widget, level)


def raw_level_of(widget: QWidget) -> int:
    """控件自身的基础层级（祖先贡献之和，不含自身贡献）。"""
    return LevelManager.instance().raw_level(widget)


def level_of(widget: QWidget) -> int:
    """控件当前生效的样式层级（已按断点填充）。"""
    return LevelManager.instance().level(widget)
