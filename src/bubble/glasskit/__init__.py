"""Core frosted-glass toolkit for PySide6.

The package contains the reusable pieces only:

* :class:`FrostStyle` / :func:`paint_frost_overlay` -- material model and paint
  helper.  All material controls, including the vignette, live here.  Every
  field is also exposed as a QSS ``qproperty-frost*`` on the painting widgets
  (:class:`GlassBackdrop`, :class:`GlassMenuBar`, :class:`GlassPanel`), so the
  four presets in :mod:`.config` can be tuned from the theme style sheet; see
  :func:`apply_glass_style` for the ``"thin"`` variants.
* :class:`BlurredGlassPanel` -- blur the content underneath one widget.
* :class:`DesktopSource` -- capture the screen and supply blurred regions for
  live window-level glass.
* :class:`WallpaperSource` -- static system-wallpaper backdrop that reloads
  only when the wallpaper changes (Mica-like idle behaviour).
* :class:`GlassRuntimeSettings` -- background source, FPS, GPU, energy saving
  and focus-loss behaviour.
* :class:`GpuSurface` -- optional QOpenGLWidget painting surface.
* :class:`EnergyModeController` -- standard/energy switching with an animated
  cross-fade, including automatic switching on focus loss.

Window chrome, parameter panels and demo styling belong to the application,
not to this library.
"""

from .energy import EnergyModeController
from .glass import (
    BlurSource,
    BlurredGlassPanel,
    FrostStyle,
    apply_glass_style,
    mix,
    paint_frost_overlay,
    qcolor,
    rounded_path,
    GlassMainWindow,
    GlassDialog,
    GlassMenuBar,
    GlassPanel,
    GlassBackdrop
)
from .gpu import GpuBackdrop, GpuSurface
from .imaging import (
    DesktopSource,
    WallpaperSource,
    blur_qimage,
    clear_texture_cache,
    exclude_window_from_capture,
    noise_texture,
    pil_to_qimage,
    qimage_to_pil,
    system_wallpaper_path,
)
from .settings import (
    BACKGROUND_SCREEN,
    BACKGROUND_WALLPAPER,
    GlassRuntimeSettings,
)
from .config import * # noqa: F403

__all__ = [
    "BACKGROUND_SCREEN",
    "BACKGROUND_WALLPAPER",
    "BlurSource",
    "BlurredGlassPanel",
    "DesktopSource",
    "EnergyModeController",
    "FrostStyle",
    "GlassRuntimeSettings",
    "GpuBackdrop",
    "GpuSurface",
    "WallpaperSource",
    "blur_qimage",
    "clear_texture_cache",
    "exclude_window_from_capture",
    "mix",
    "noise_texture",
    "paint_frost_overlay",
    "pil_to_qimage",
    "qcolor",
    "qimage_to_pil",
    "rounded_path",
    "system_wallpaper_path",
    "BUBBLE_BACKGROUND_NORMAL",
    "BUBBLE_BACKGROUND_THIN",
    "BUBBLE_SIDEBAR_NORMAL",
    "BUBBLE_SIDEBAR_THIN",
    "GlassMainWindow",
    "GlassDialog",
    "GlassMenuBar",
    "GlassPanel",
    "FROST_PRESETS",
    "apply_glass_style"
]
