"""macOS Sonoma 风格调色板 + Dark / Light / Auto 主题切换。

设计:
- DarkPalette / LightPalette 两个类,字段一一对应
- 模块级 PALETTE 代理当前 active palette,所有调用方保持 PALETTE.BG / PALETTE.TEXT 不变
- set_theme("dark"|"light"|"auto") 切换;Auto 用 detect_system_theme()
- on_theme_change(cb) 注册监听,MacWindow.apply_theme() 会回调
- detect_system_theme() 优先 darkdetect,失败则平台 fallback

约定:
- HEX 默认 6 位;需要 alpha 时用 8 位 #RRGGBBAA 字符串
- 等级色 (ok/warn/critical/error/unknown) 直接挂在 LEVEL_COLOR
- 圆角 / 间距 / 字号统一在 LAYOUT / TYPOGRAPHY,便于一处改全局变
- to_tk_color() 把 8 位 hex 退成 6 位,给 Tk widget bg/fg 用
"""

import sys


LEVEL_OK = "ok"
LEVEL_WARN = "warn"
LEVEL_CRITICAL = "critical"
LEVEL_ERROR = "error"
LEVEL_UNCONFIGURED = "unconfigured"
LEVEL_UNKNOWN = "unknown"


class DarkPalette:
    """macOS Sonoma 深色调色板(默认)。"""

    BG = "#1E1E1E"
    BG_VIBRANCY = "#1E1E1ECC"
    CARD = "#2A2A2A"
    CARD_HOVER = "#323232"
    CARD_PRESSED = "#3A3A3A"
    BAR_BG = "#3A3A3A"
    BAR_BG_AMOUNT = "#2A2630"
    CARD_AMOUNT = "#1d1b25"
    TEXT = "#FFFFFF"
    TEXT_DIM = "#FFFFFFA0"
    TEXT_DISABLED = "#FFFFFF4D"
    DIVIDER = "#FFFFFF14"

    BLUE = "#0A84FF"
    GREEN = "#30D158"
    YELLOW = "#FFD60A"
    RED = "#FF453A"
    ORANGE = "#FF9F0A"
    PURPLE = "#BF5AF2"
    PINK = "#FF375F"
    GREY = "#8E8E93"

    TRAFFIC_RED = "#FF5F57"
    TRAFFIC_YELLOW = "#FEBC2E"
    TRAFFIC_GREEN = "#28C840"
    TRAFFIC_GREEN_HOVER = "#5BB85B"

    THUMB_IDLE = "#5C5C66"
    THUMB_HOVER = "#8E8E99"

    GLYPH_RED = "#4d0000"
    GLYPH_YELLOW = "#5a4500"
    GLYPH_GREEN = "#0d3d18"

    OK = GREEN
    WARN = YELLOW
    CRITICAL = RED
    ERROR = ORANGE
    OFF = GREY
    UNKNOWN = GREY

    IS_DARK = True


class LightPalette:
    """macOS Sonoma 浅色调色板。

    数值参考 Apple HIG Light mode + 一点点灰阶,
    卡片白底 + 浅灰底边,文字几乎全黑,辅助 80% 黑。
    """

    BG = "#F5F5F7"
    BG_VIBRANCY = "#F5F5F7E6"
    CARD = "#FFFFFF"
    CARD_HOVER = "#FAFAFC"
    CARD_PRESSED = "#F2F2F4"
    BAR_BG = "#E5E5EA"
    BAR_BG_AMOUNT = "#FAF8F2"
    CARD_AMOUNT = "#FBF9F2"
    TEXT = "#000000"
    TEXT_DIM = "#00000080"
    TEXT_DISABLED = "#00000033"
    DIVIDER = "#00000014"

    BLUE = "#007AFF"
    GREEN = "#34C759"
    YELLOW = "#FFCC00"
    RED = "#FF3B30"
    ORANGE = "#FF9500"
    PURPLE = "#AF52DE"
    PINK = "#FF2D55"
    GREY = "#8E8E93"

    TRAFFIC_RED = "#FF5F57"
    TRAFFIC_YELLOW = "#FEBC2E"
    TRAFFIC_GREEN = "#28C840"
    TRAFFIC_GREEN_HOVER = "#1E9E3D"

    THUMB_IDLE = "#B8B8C0"
    THUMB_HOVER = "#8E8E93"

    GLYPH_RED = "#4d0000"
    GLYPH_YELLOW = "#5a4500"
    GLYPH_GREEN = "#0d3d18"

    OK = GREEN
    WARN = YELLOW
    CRITICAL = RED
    ERROR = ORANGE
    OFF = GREY
    UNKNOWN = GREY

    IS_DARK = False


PALETTES = {
    "dark": DarkPalette,
    "light": LightPalette,
}

THEME_CHOICES = ("dark", "light", "auto")

_current_choice = "dark"
_active_palette = DarkPalette
_listeners = []


def _resolve(name):
    """name ∈ THEME_CHOICES → 返回实际要用的 palette key(dark/light)。"""
    if name == "auto":
        return detect_system_theme()
    return name if name in PALETTES else "dark"


def detect_system_theme():
    """探测系统主题。优先 darkdetect,失败则平台 fallback,最后默认 dark。"""
    try:
        import darkdetect
        result = darkdetect.theme()
        if result and result.lower() in ("dark", "light"):
            return result.lower()
    except Exception:
        pass

    if sys.platform == "win32":
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
            )
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            winreg.CloseKey(key)
            return "light" if value == 1 else "dark"
        except Exception:
            pass

    return "dark"


def current_palette():
    return _active_palette


def current_choice():
    """返回用户设置值("dark"/"light"/"auto"),不是解析后的实际 key。"""
    return _current_choice


def is_dark():
    return getattr(_active_palette, "IS_DARK", True)


def set_theme(name, broadcast=True, persist=True):
    """name ∈ {"dark","light","auto"}。切换 PALETTE + 广播给监听者。

    返回实际生效的 palette key (dark/light),即使 name 是 auto 也会解析。
    """
    global _current_choice, _active_palette
    if name not in THEME_CHOICES:
        name = "dark"
    resolved = _resolve(name)
    if resolved not in PALETTES:
        resolved = "dark"
    _current_choice = name
    _active_palette = PALETTES[resolved]
    _refresh_level_color()
    if broadcast:
        for cb in list(_listeners):
            try:
                cb(_current_choice, _active_palette, persist)
            except Exception:
                pass
    return resolved


def on_theme_change(callback):
    """注册主题变更监听。回调签名 cb(choice, palette, persist) → None。"""
    _listeners.append(callback)


def off_theme_change(callback):
    try:
        _listeners.remove(callback)
    except ValueError:
        pass


class _PaletteProxy:
    """模块级 PALETTE 是这个类的实例,__getattr__ 代理到当前 active palette。

    调用方写法不变:PALETTE.BG / PALETTE.GREEN / PALETTE.OK,自动跟随主题。
    """

    def __getattr__(self, name):
        return getattr(_active_palette, name)

    def __setattr__(self, name, value):
        raise AttributeError("PALETTE 是只读代理,请用 set_theme()")


PALETTE = _PaletteProxy()


LEVEL_COLOR = {
    LEVEL_OK: PALETTE.OK,
    LEVEL_WARN: PALETTE.WARN,
    LEVEL_CRITICAL: PALETTE.CRITICAL,
    LEVEL_ERROR: PALETTE.ERROR,
    LEVEL_UNCONFIGURED: PALETTE.OFF,
    LEVEL_UNKNOWN: PALETTE.UNKNOWN,
}


def level_color(level):
    """按当前主题返回等级色。与 LEVEL_COLOR[level] 同义,但更明显。"""
    return LEVEL_COLOR.get(level, PALETTE.UNKNOWN)


def _refresh_level_color():
    """主题切换时同步更新 LEVEL_COLOR 字典。"""
    LEVEL_COLOR[LEVEL_OK] = PALETTE.OK
    LEVEL_COLOR[LEVEL_WARN] = PALETTE.WARN
    LEVEL_COLOR[LEVEL_CRITICAL] = PALETTE.CRITICAL
    LEVEL_COLOR[LEVEL_ERROR] = PALETTE.ERROR
    LEVEL_COLOR[LEVEL_UNCONFIGURED] = PALETTE.OFF
    LEVEL_COLOR[LEVEL_UNKNOWN] = PALETTE.UNKNOWN


class Layout:
    """macOS 风圆角与间距。

    与现有 v2.1 panel.py 的 MIN_W/MIN_H/EDGE_SNAP/RESIZE_GRIP 保持一致,
    新增的字段都是 macOS 风特有。
    """

    RADIUS_WIN = 12
    RADIUS_CARD = 10
    RADIUS_BTN = 6
    RADIUS_BAR = 4

    BAR_HEIGHT = 6
    PAD = 10
    PAD_X = 12
    PAD_Y = 8

    TRAFFIC_DOT = 12
    TRAFFIC_GAP = 8

    HEADER_HEIGHT = 36
    FOOTER_HEIGHT = 24

    MIN_W = 280
    MIN_H = 180
    MAX_W = 800
    MAX_H = 900

    ESSENTIAL_W = 240
    ESSENTIAL_H = 56

    EDGE_SNAP = 20
    RESIZE_GRIP = 16


class Typography:
    """字号规范。Family 由 ui.fonts 决定,这里只管 size 与 weight。"""

    TITLE_SIZE = 13
    TITLE_WEIGHT = "bold"
    BODY_SIZE = 13
    NUM_SIZE = 22
    NUM_SMALL_SIZE = 11
    DETAIL_SIZE = 11
    FOOTER_SIZE = 10
    BADGE_SIZE = 9


def hex_with_alpha(hex_color, alpha_0_255):
    """把 6 位 hex 扩展为 8 位 hex (RRGGBBAA),用于支持 alpha 的 Canvas。"""
    h = hex_color.lstrip("#")
    a = max(0, min(255, int(alpha_0_255)))
    return f"#{h}{a:02X}"


def to_tk_color(hex_color, fallback=None):
    """Tk widget 不接受 8 位 hex (alpha),只接受 6 位。

    若传入的是 8 位,剥离 alpha 通道取 RGB 部分。
    fallback 是 6 位 hex。
    """
    h = hex_color.lstrip("#")
    if len(h) == 8:
        return f"#{h[:6]}"
    if len(h) == 6:
        return hex_color
    return fallback or "#FFFFFF"


TEXT_TK = to_tk_color(PALETTE.TEXT)
TEXT_DIM_TK = to_tk_color(PALETTE.TEXT_DIM)
TEXT_DISABLED_TK = to_tk_color(PALETTE.TEXT_DISABLED)
DIVIDER_TK = to_tk_color(PALETTE.DIVIDER)


def blend(top_hex, bottom_hex, t):
    """颜色插值:t=0 取 top,t=1 取 bottom。返回 #RRGGBB。"""
    def _to_rgb(h):
        h = h.lstrip("#")
        if len(h) == 8:
            h = h[:6]
        return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))
    tr, tg, tb = _to_rgb(top_hex)
    br, bg, bb = _to_rgb(bottom_hex)
    t = max(0.0, min(1.0, t))
    r = int(tr + (br - tr) * t)
    g = int(tg + (bg - tg) * t)
    b = int(tb + (bb - tb) * t)
    return f"#{r:02x}{g:02x}{b:02x}"


def usage_color(ratio):
    """绿 → 黄 → 红 三段插值。ratio=None 时返回 UNKNOWN。"""
    if ratio is None:
        return PALETTE.UNKNOWN
    r = max(0.0, min(1.0, ratio))
    if r <= 0.5:
        return blend(PALETTE.GREEN, PALETTE.YELLOW, r / 0.5)
    return blend(PALETTE.YELLOW, PALETTE.CRITICAL, (r - 0.5) / 0.5)


__all__ = [
    "DarkPalette", "LightPalette", "PALETTES",
    "PALETTE", "Layout", "Typography",
    "LEVEL_COLOR", "level_color",
    "LEVEL_OK", "LEVEL_WARN", "LEVEL_CRITICAL", "LEVEL_ERROR",
    "LEVEL_UNCONFIGURED", "LEVEL_UNKNOWN",
    "hex_with_alpha", "to_tk_color", "blend", "usage_color",
    "set_theme", "current_palette", "current_choice", "is_dark",
    "on_theme_change", "off_theme_change", "detect_system_theme",
    "THEME_CHOICES", "TEXT_TK", "TEXT_DIM_TK", "TEXT_DISABLED_TK", "DIVIDER_TK",
]
