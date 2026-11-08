"""pyside6_levels —— 为 PySide6 提供“组件层级(level)”概念。

一个控件（组件）可以声明自己为**子控件**增加多少层级（contribution），
所有祖先贡献之和就是控件的基础层级；QSS 通过 ``level`` 动态属性按层级配色，
未定义的中间层级自动就近向下填充。
"""

from .component import (
    level_component,
    level_of,
    raw_level_of,
    set_contribution,
    set_level,
)
from .manager import (
    LevelManager,
    normalize_level_selectors,
    parse_defined_levels,
)

__version__ = "0.1.0"

__all__ = [
    "LevelManager",
    "level_component",
    "set_contribution",
    "set_level",
    "raw_level_of",
    "level_of",
    "normalize_level_selectors",
    "parse_defined_levels",
]
