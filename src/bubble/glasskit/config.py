from .settings import (
    BACKGROUND_WALLPAPER,
    GlassRuntimeSettings,
    FrostStyle
)

RUNTIME = GlassRuntimeSettings(
    background_mode=BACKGROUND_WALLPAPER,
    fps=24,
    gpu=False,
    auto_energy_on_focus_loss=True,
    transition_ms=250,
)
CAPTURE_SCALE = 0.5         # region capture scale; 1.0 = sharper, more CPU

# Whole-window desktop glass material.
BUBBLE_BACKGROUND_THIN = FrostStyle(
    tint="#4c4c4c",
    opacity=60,
    blur=24,
    frost=20,
    noise=5,
    sheen=15,
    saturation=100,
    brightness=100,
) # 透明模式

# Whole-window desktop glass material.
BUBBLE_BACKGROUND_NORMAL = FrostStyle(
    tint="#272727",
    opacity=90,
    blur=48,
    frost=3,
    noise=3,
    sheen=0,
    saturation=75,
    brightness=60,
) # 透明模式

# Whole-window desktop glass material.
BUBBLE_SIDEBAR_NORMAL = FrostStyle(
    tint="#202020",
    opacity=70,
    blur=48,
    frost=5,
    noise=0,
    sheen=40,
    saturation=80,
    brightness=55,
) # 透明模式

# Whole-window desktop glass material.
BUBBLE_SIDEBAR_THIN = FrostStyle(
    tint="#545454",
    opacity=30,
    blur=24,
    frost=5,
    noise=0,
    sheen=10,
    saturation=130,
    brightness=120,
) # 透明模式
#: The four built-in materials.  The same values are written to the theme
#: style sheets (`res/styles/dark.qss` / `light.qss`) as
#: `qproperty-frost*` rules; those QSS rules are applied at runtime and are
#: the recommended place to tune the material.  The presets below remain the
#: code-level defaults (what a standalone glasskit app gets without a style
#: sheet).  Widget mapping used by the theme style sheets:
#:
#: * `background_normal` / `background_thin` -> :class:GlassBackdrop
#: * `sidebar_normal` / `sidebar_thin` -> :class:GlassMenuBar
FROST_PRESETS = {
    "background_normal": BUBBLE_BACKGROUND_NORMAL,
    "background_thin": BUBBLE_BACKGROUND_THIN,
    "sidebar_normal": BUBBLE_SIDEBAR_NORMAL,
    "sidebar_thin": BUBBLE_SIDEBAR_THIN,
}
