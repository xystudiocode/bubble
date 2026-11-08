"""Standard <-> energy-saving mode switching for glass windows.

The controller owns:

* explicit energy-saving state and optional automatic switching on focus loss
* a 0.25s cross-fade between the standard and energy backgrounds
* the paint hook for that transition

The host supplies a ``render_background(energy: bool) -> QPixmap`` callback and
reacts to ``energyChanged`` / ``transitionFinished`` to pause its desktop
source, hide/show a GPU surface, or update its controls.
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QObject,
    QTimer,
    Qt,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import QWidget


class EnergyModeController(QObject):
    """Drive standard/energy mode with an animated cross-fade."""

    energyChanged = Signal(bool)
    transitionFinished = Signal(bool)

    def __init__(self, window: QWidget,
                 render_background: Callable[[bool], QPixmap],
                 *, duration_ms: int = 250,
                 auto_on_focus_loss: bool = True,
                 parent: QObject | None = None):
        super().__init__(parent if parent is not None else window)
        self._window = window
        self._render_background = render_background
        self._duration_ms = max(0, int(duration_ms))
        self._auto = bool(auto_on_focus_loss)
        self._explicit = False
        self._energy_active = False
        self._transition_active = False
        self._transition_t = 0.0
        self._transition_from: QPixmap | None = None
        self._transition_to: QPixmap | None = None

        self._anim = QVariantAnimation(self)
        self._anim.setDuration(self._duration_ms)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._anim.valueChanged.connect(self._on_anim_value)
        self._anim.finished.connect(self._on_anim_finished)

        self._window.installEventFilter(self)

    # -- public state ------------------------------------------------------
    @property
    def active(self) -> bool:
        """Whether the energy configuration is the current target."""
        return self._energy_active

    @property
    def transitioning(self) -> bool:
        return self._transition_active

    @property
    def progress(self) -> float:
        return self._transition_t

    @property
    def explicit(self) -> bool:
        return self._explicit

    @property
    def auto_on_focus_loss(self) -> bool:
        return self._auto

    @property
    def duration_ms(self) -> int:
        return self._duration_ms

    def set_explicit(self, enabled: bool) -> None:
        self._explicit = bool(enabled)
        self._refresh()

    def set_auto_on_focus_loss(self, enabled: bool) -> None:
        self._auto = bool(enabled)
        self._refresh()

    def set_duration(self, duration_ms: int) -> None:
        self._duration_ms = max(0, int(duration_ms))
        self._anim.setDuration(self._duration_ms)

    # -- painting ----------------------------------------------------------
    def paint(self, painter: QPainter) -> bool:
        """Draw the cross-fade.  Returns True while a transition is active."""
        if not self._transition_active:
            return False
        if self._transition_from is not None:
            painter.drawPixmap(0, 0, self._transition_from)
        if self._transition_to is not None:
            painter.setOpacity(self._transition_t)
            painter.drawPixmap(0, 0, self._transition_to)
        return True

    # -- internal state ----------------------------------------------------
    def _refresh(self) -> None:
        if not self._window.isVisible():
            return
        target = bool(self._explicit or (self._auto and not self._window.isActiveWindow()))
        if target == self._energy_active:
            return
        self._start_transition(target)

    def _start_transition(self, target: bool) -> None:
        if self._transition_active:
            from_pixmap = self._render_transition_frame()
            self._transition_active = False
            self._anim.stop()
        else:
            from_pixmap = self._render_background(self._energy_active)

        self._energy_active = bool(target)
        self.energyChanged.emit(self._energy_active)

        if self._duration_ms <= 0:
            self._transition_active = False
            self.transitionFinished.emit(self._energy_active)
            self._window.update()
            return

        to_pixmap = self._render_background(self._energy_active)
        self._transition_from = from_pixmap
        self._transition_to = to_pixmap
        self._transition_t = 0.0
        self._transition_active = True
        self._anim.stop()
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.start()
        self._window.update()

    def _on_anim_value(self, value) -> None:
        if not self._transition_active:
            return
        self._transition_t = float(value)
        self._window.update()

    def _on_anim_finished(self) -> None:
        if not self._transition_active:
            return
        self._transition_active = False
        self._transition_from = None
        self._transition_to = None
        self._transition_t = 1.0
        self.transitionFinished.emit(self._energy_active)
        self._window.update()

    def _render_transition_frame(self) -> QPixmap:
        pixmap = QPixmap(self._window.size())
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        if self._transition_from is not None:
            painter.drawPixmap(0, 0, self._transition_from)
        if self._transition_to is not None:
            painter.setOpacity(self._transition_t)
            painter.drawPixmap(0, 0, self._transition_to)
        painter.end()
        return pixmap

    def _scale_snapshots(self) -> None:
        size = self._window.size()
        if self._transition_from is not None:
            self._transition_from = self._transition_from.scaled(
                size, Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        if self._transition_to is not None:
            self._transition_to = self._transition_to.scaled(
                size, Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )

    # -- focus / resize ----------------------------------------------------
    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if obj is self._window:
            event_type = event.type()
            if event_type == QEvent.Type.Show:
                QTimer.singleShot(0, self._refresh)
            elif event_type in (QEvent.Type.WindowActivate,
                                QEvent.Type.WindowDeactivate,
                                QEvent.Type.ActivationChange):
                self._refresh()
            elif event_type == QEvent.Type.Resize and self._transition_active:
                self._scale_snapshots()
        return super().eventFilter(obj, event)
