"""Optional GPU-backed painting surface for glass windows.

QWidget normally paints through Qt's raster engine on the CPU.  ``GpuSurface``
is a full-window ``QOpenGLWidget`` child that routes a QPainter scene through
Qt's OpenGL paint engine.  It is intentionally only a drawing surface: the
blur itself is still computed by the imaging helpers.

The surface is kept behind normal child widgets, so labels, buttons and panels
remain crisp and keep their normal QWidget behaviour.
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter
from PySide6.QtOpenGLWidgets import QOpenGLWidget


class GpuSurface(QOpenGLWidget):
    """A full-window GL surface that delegates painting to a callback."""

    def __init__(self, parent, render: Callable[[QPainter], None],
                 *, transparent_for_mouse: bool = True):
        super().__init__(parent)
        self._render = render
        if transparent_for_mouse:
            self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)
        self.setUpdateBehavior(QOpenGLWidget.UpdateBehavior.NoPartialUpdate)

    def paintGL(self) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self._render(painter)
        painter.end()


# Backwards-friendly name for code that used the demo-local class.
GpuBackdrop = GpuSurface
