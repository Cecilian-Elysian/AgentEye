"""极简工具风调色板 + Dark / Light / Auto 主题切换。

设计:
- DarkPalette / LightPalette 两个类,字段一一对应
- 模块级 PALETTE 代理当前 active palette,所有调用方保持 PALETTE.BG / PALETTE.TEXT 不变
- set_theme("dark"|"light"|"auto") 切换;Auto 用 detect_system_theme()
- on_theme_change(cb) 注册监听,MacWindow.apply_theme() 会回调
- detect_system_theme() 走标准库 winreg,不依赖任何第三方库

约定:
- HEX 默认 6 位;需要 alpha 时用 8 位 #RRGGBBAA 字符串
- 等级色 (ok/warn/critical/error/unknown) 直接挂在 LEVEL_COLOR
- 灰阶是一条斜坡:BG < CARD < CARD_HOVER < CARD_PRESSED < BAR_BG,
  每一档都要能肉眼分开,不能有两档同色
- 圆角 / 间距 / 字号统一在 Layout / Typography,便于一处改全局变
- to_tk_color() 把 8 位 hex 退成 6 位,给 Tk widget bg/fg 用
"""

import sys


LEVEL_OK = "ok"
LEVEL_WARN = "warn"
LEVEL_CRITICAL = "critical"
LEVEL_ERROR = "error"
LEVEL_UNCONFIGURED = "unconfigured"
LEVEL_PAUSED = "paused"
LEVEL_UNKNOWN = "unknown"


class DarkPalette:
    """深色调色板(默认)。

    灰阶是一条五级斜坡,每级约 10 个通道值:
        BG < CARD < CARD_HOVER < CARD_PRESSED < BAR_BG
    原先 CARD_HOVER / BAR_BG / CARD_PRESSED 是同一个色,
    hover、进度轨道、按下三者视觉上完全分不开。

    CARD 只作"填充面"(输入框 / 菜单 / tooltip)的底,
    行卡不铺底色——行与行之间靠 DIVIDER 分割线分隔。
    """

    BG = "#101012"
    BG_VIBRANCY = "#101012E6"
    CARD = "#1A1A1F"
    CARD_HOVER = "#232329"
    CARD_PRESSED = "#2C2C34"
    BAR_BG = "#35353E"
    BAR_BG_AMOUNT = BAR_BG
    CARD_AMOUNT = CARD
    TEXT = "#F2F2F5"
    TEXT_DIM = "#FFFFFF8C"
    TEXT_DISABLED = "#FFFFFF40"
    DIVIDER = "#FFFFFF16"

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
    """浅色调色板。

    与深色同构的五级斜坡(每级约 10 个通道值,反向):
        BG > CARD > CARD_HOVER > CARD_PRESSED > BAR_BG
    BG 接近纯白而不是灰白:极简风里窗口底色越白,填充面(CARD)的
    那一层灰就越显得"有",不需要再压深 BG 制造层次。
    """

    BG = "#FCFCFD"
    BG_VIBRANCY = "#FCFCFDE6"
    CARD = "#F1F1F4"
    CARD_HOVER = "#E8E8ED"
    CARD_PRESSED = "#DEDEE4"
    BAR_BG = "#D2D2DA"
    BAR_BG_AMOUNT = BAR_BG
    CARD_AMOUNT = CARD
    TEXT = "#000000"
    TEXT_DIM = "#0000008C"
    TEXT_DISABLED = "#00000040"
    DIVIDER = "#00000016"

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
    """探测系统主题。Windows 走 winreg 的 AppsUseLightTheme,失败默认 dark。

    刻意不依赖第三方库:winreg 是标准库,行为在任何机器上一致。
    """
    if sys.platform == "win32":
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
            )
            try:
                value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            finally:
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


def bind_theme_listener(widget, callback):
    """注册主题监听,并保证 widget 销毁时自动反注册。

    之前各窗口/对话框直接 on_theme_change,关闭后监听器残留在
    _listeners 里:每次切主题都去刷一堆已销毁的控件(靠 except 吞
    TclError),对象也被闭包拽住无法回收。对话框每开一次就漏一个。
    """
    on_theme_change(callback)

    def _on_destroy(event):
        if event.widget is widget:
            off_theme_change(callback)

    try:
        widget.bind("<Destroy>", _on_destroy, add="+")
    except Exception:
        pass
    return lambda: off_theme_change(callback)


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
    LEVEL_PAUSED: PALETTE.OFF,
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
    LEVEL_COLOR[LEVEL_PAUSED] = PALETTE.OFF
    LEVEL_COLOR[LEVEL_UNKNOWN] = PALETTE.UNKNOWN


class Layout:
    """圆角与间距。

    这些常量以前是"定义了但没人引用"的死配置——圆角交给 DWM、间距散落
    成几十处 magic number。现在 ui.paint / ui.panel / ui.essential_bar 都从
    这里取值,改一处即全局生效。

    RADIUS_WIN 只是一个参照值:窗口走 overrideredirect,圆角由 DWM 的
    DWMWCP_ROUND 决定,这个值控制不了它。
    """

    RADIUS_WIN = 10
    RADIUS_CARD = 8
    RADIUS_BTN = 5
    # 与胶囊的 r = h/2 一致:ROW_BAR_HEIGHT 12 → 6,BAR_HEIGHT 6 → 3,
    # 最小的一档是 3,所以常量取 3 才与实绘半径不打架。
    RADIUS_BAR = 3

    BAR_HEIGHT = 6
    ROW_BAR_HEIGHT = 12

    PAD = 10
    PAD_X = 12
    PAD_Y = 8
    # 行与行之间靠分割线而不是圆角底色块分隔,这两个值只管
    # 分割线上下的留白,别再加行内底色,那会把斜坡压平。
    ROW_GAP = 2
    ROW_PAD_Y = 7

    TRAFFIC_DOT = 12
    TRAFFIC_GAP = 8

    # 拖拽落位指示线的高度。ui/model_panel.py 也画同一条线,以前一个 3px
    # 一个 2px,同一屏出现两种粗细的指示线。
    DRAG_MARKER = 2

    HEADER_HEIGHT = 36
    FOOTER_HEIGHT = 24

    MIN_W = 280
    MIN_H = 180
    MAX_W = 800
    MAX_H = 900

    ESSENTIAL_W = 240
    # 56 装不下:Typography.NUM_SIZE(20pt)在 YaHei UI 下行高约 41px,
    # 加上 8px 顶留白和 6px 条 + 12px 留白,进度条被挤到可视区外——
    # 折叠态只剩一行大字,滑块不见了。64 才有"大数字 + 一条胶囊"的余地。
    ESSENTIAL_H = 64

    EDGE_SNAP = 20
    RESIZE_GRIP = 16


class Typography:
    """字号规范。Family 由 ui.fonts 决定,这里只管 size 与 weight。

    最小可读字号是 10:原来 8pt/9pt 的中文在 Windows 上笔画粘连,
    且与 10/13/14 混用不成阶梯。现在只有 9/10/11/12 四档正文 + 20 大数字。
    """

    TITLE_SIZE = 12
    TITLE_WEIGHT = "bold"
    BODY_SIZE = 11
    NUM_SIZE = 20
    NUM_SMALL_SIZE = 12
    DETAIL_SIZE = 10
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


def to_tk_color_blended(hex_with_alpha_or_6, bg_hex=None):
    """Tk widget 的 8 位 hex 看不到 alpha,得预混合到 bg 上。

    输入 8 位:解析 AA 通道,把前景 alpha 混合到 bg_hex(默认 PALETTE.BG)。
    输入 6 位:直接返回。
    返回 6 位 hex,可直接喂给 widget bg/fg。
    """
    h = hex_with_alpha_or_6.lstrip("#")
    if len(h) == 6:
        return hex_with_alpha_or_6
    if len(h) != 8:
        return "#000000"
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    a = int(h[6:8], 16) / 255.0
    bg = bg_hex or PALETTE.BG
    bg = bg.lstrip("#")
    if len(bg) == 8:
        bg = bg[:6]
    br, bg_, bb = int(bg[0:2], 16), int(bg[2:4], 16), int(bg[4:6], 16)
    r = int(r * a + br * (1 - a))
    g = int(g * a + bg_ * (1 - a))
    b = int(b * a + bb * (1 - a))
    return f"#{r:02x}{g:02x}{b:02x}"


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
    "LEVEL_UNCONFIGURED", "LEVEL_PAUSED", "LEVEL_UNKNOWN",
    "hex_with_alpha", "to_tk_color", "to_tk_color_blended",
    "blend", "usage_color",
    "set_theme", "current_palette", "current_choice", "is_dark",
    "on_theme_change", "off_theme_change", "detect_system_theme",
    "THEME_CHOICES",
]
