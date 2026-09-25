"""macOS Sonoma 风格调色板常量与等级颜色映射。

所有 UI 模块从这里取色,避免硬编码。
颜色按 macOS HIG(深色模式)取,SoloDark 风格参考。

约定:
- HEX 默认 6 位;需要 alpha 时用 8 位 #RRGGBBAA 字符串
- 等级色 (ok/warn/critical/error/unknown) 直接挂在 LEVEL_COLOR
- 圆角 / 间距 / 字号统一在 LAYOUT / TYPOGRAPHY,便于一处改全局变
"""

LEVEL_OK = "ok"
LEVEL_WARN = "warn"
LEVEL_CRITICAL = "critical"
LEVEL_ERROR = "error"
LEVEL_UNCONFIGURED = "unconfigured"
LEVEL_UNKNOWN = "unknown"


class Palette:
    """macOS Sonoma 深色调色板。

    半透明效果依赖 DWM Acrylic / NSVisualEffectView;
    fallback 是 alpha=0.95 的实色。
    """

    BG = "#1E1E1E"
    BG_VIBRANCY = "#1E1E1ECC"
    CARD = "#2A2A2A"
    CARD_HOVER = "#323232"
    CARD_PRESSED = "#3A3A3A"
    BAR_BG = "#3A3A3A"
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

    OK = GREEN
    WARN = YELLOW
    CRITICAL = RED
    ERROR = ORANGE
    OFF = GREY
    UNKNOWN = GREY


PALETTE = Palette()


LEVEL_COLOR = {
    LEVEL_OK: PALETTE.OK,
    LEVEL_WARN: PALETTE.WARN,
    LEVEL_CRITICAL: PALETTE.CRITICAL,
    LEVEL_ERROR: PALETTE.ERROR,
    LEVEL_UNCONFIGURED: PALETTE.OFF,
    LEVEL_UNKNOWN: PALETTE.UNKNOWN,
}


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
    """绿 → 黄 → 红 三段插值,语义与 panel._usage_color 一致。

    ratio=0 全绿 (PALETTE.GREEN),ratio=0.5 黄,ratio=1 红 (PALETTE.CRITICAL)。
    ratio=None 时返回 dim 灰。
    """
    if ratio is None:
        return PALETTE.UNKNOWN
    r = max(0.0, min(1.0, ratio))
    if r <= 0.5:
        return blend(PALETTE.GREEN, PALETTE.YELLOW, r / 0.5)
    return blend(PALETTE.YELLOW, PALETTE.CRITICAL, (r - 0.5) / 0.5)


__all__ = [
    "Palette", "PALETTE",
    "Layout", "Typography",
    "LEVEL_COLOR",
    "LEVEL_OK", "LEVEL_WARN", "LEVEL_CRITICAL", "LEVEL_ERROR",
    "LEVEL_UNCONFIGURED", "LEVEL_UNKNOWN",
    "hex_with_alpha", "blend", "usage_color",
]
