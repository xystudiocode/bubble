"""Reusable runtime settings for desktop-glass surfaces.

Material values live in :class:`glasskit.glass.FrostStyle` (including the
vignette).  This module only holds the non-visual/runtime switches shared by
desktop-glass windows:

* background source: static system wallpaper or live screen tracking
* screen-tracking frame rate
* optional GPU composition
* explicit energy saving
* automatic energy saving when the window loses focus
* transition duration between standard and energy configurations
* capture compatibility for screen tracking

``background_mode`` defaults to ``"wallpaper"``.  That is the Mica-like path:
the wallpaper is sampled once, blurred by glasskit, and only reloaded when
Windows reports a wallpaper change.  ``"screen"`` keeps the original live
desktop tracking, which needs Windows' capture exclusion while it is active.

``allow_capture`` only applies to ``"screen"`` mode.  It pauses live sampling
and reuses the last frame so the window itself becomes visible to OBS and
screenshot tools.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

BACKGROUND_WALLPAPER = "wallpaper"
BACKGROUND_SCREEN = "screen"


@dataclass
class GlassRuntimeSettings:
    background_mode: str = BACKGROUND_WALLPAPER
    fps: int = 15
    gpu: bool = False
    energy_saving: bool = False
    auto_energy_on_focus_loss: bool = True
    transition_ms: int = 250
    allow_capture: bool = False

    def __post_init__(self) -> None:
        if self.background_mode not in (BACKGROUND_WALLPAPER, BACKGROUND_SCREEN):
            self.background_mode = BACKGROUND_WALLPAPER
        self.fps = max(1, min(30, int(self.fps)))
        self.transition_ms = max(0, int(self.transition_ms))

    @property
    def wallpaper(self) -> bool:
        return self.background_mode == BACKGROUND_WALLPAPER

    @property
    def screen_tracking(self) -> bool:
        return self.background_mode == BACKGROUND_SCREEN

    def copy(self) -> "GlassRuntimeSettings":
        return replace(self)

@dataclass
class FrostStyle:
    """All user-tunable properties of a frosted surface."""

    tint: str = "#272727"
    opacity: int = 74
    blur: int = 32
    frost: int = 16
    noise: int = 9
    sheen: int = 34
    saturation: int = 102
    brightness: int = 94
    border: int = 24
    radius: int = 18
    vignette: int = 0

    def copy(self) -> "FrostStyle":
        return replace(self)

    def snapshot(self) -> tuple:
        return (self.tint, self.opacity, self.blur, self.frost, self.noise,
                self.sheen, self.saturation, self.brightness, self.border,
                self.radius, self.vignette)