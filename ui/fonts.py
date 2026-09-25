"""跨平台字体选择。

按平台挑 macOS 风优先的 UI 字体与等宽字体,fallback 链保证一定可用。
"""

import platform
import tkinter as tk
import tkinter.font as tkfont


_SF_PRO = "SF Pro Text"
_SF_PRO_DISPLAY = "SF Pro Display"
_SF_MONO = "SF Mono"
_HELVETICA = "Helvetica Neue"
_PINGFANG = "PingFang SC"
_SEGOE = "Segoe UI"
_SEGOE_VARIABLE = "Segoe UI Variable"
_CASCADIA = "Cascadia Mono"
_CASCADIA_VARIABLE = "Cascadia Mono Variable"
_NOTO = "Noto Sans CJK SC"
_NOTO_VARIABLE = "Noto Sans CJK SC Variable Font"
_DEJAVU_MONO = "DejaVu Sans Mono"


_CHAINS = {
    "Darwin": {
        "ui": [_SF_PRO, _SF_PRO_DISPLAY, _HELVETICA, _PINGFANG, "Arial"],
        "mono": [_SF_MONO, "Menlo", "Monaco", _CASCADIA, _DEJAVU_MONO],
    },
    "Windows": {
        "ui": [_SEGOE_VARIABLE, _SEGOE, _NOTO_VARIABLE, _NOTO, "Arial"],
        "mono": [_CASCADIA_VARIABLE, _CASCADIA, "Consolas", _DEJAVU_MONO],
    },
    "Linux": {
        "ui": [_NOTO_VARIABLE, _NOTO, "Ubuntu", "DejaVu Sans", "Arial"],
        "mono": [_DEJAVU_MONO, "Ubuntu Mono", "Liberation Mono", _CASCADIA],
    },
}


def _available_families():
    try:
        return set(tkfont.families())
    except Exception:
        return set()


def _pick(chain, available):
    for name in chain:
        if name in available:
            return name
    return None


def pick_ui_family(root=None):
    """返回当前系统可用的 UI 字体 family 字符串;找不到就回退 tk 默认。"""
    sysname = platform.system()
    chain = _CHAINS.get(sysname, _CHAINS["Linux"])["ui"]
    families = _available_families() if root is None else _ensure_families(root)
    name = _pick(chain, families)
    if name:
        return name
    try:
        return tkfont.nametofont("TkDefaultFont").actual("family")
    except Exception:
        return "TkDefaultFont"


def pick_mono_family(root=None):
    sysname = platform.system()
    chain = _CHAINS.get(sysname, _CHAINS["Linux"])["mono"]
    families = _available_families() if root is None else _ensure_families(root)
    name = _pick(chain, families)
    if name:
        return name
    try:
        return tkfont.nametofont("TkFixedFont").actual("family")
    except Exception:
        return "TkFixedFont"


_FAMILY_CACHE = {}


def _ensure_families(root):
    key = id(root)
    if key in _FAMILY_CACHE:
        return _FAMILY_CACHE[key]
    try:
        root.update_idletasks()
    except Exception:
        pass
    fams = _available_families()
    _FAMILY_CACHE[key] = fams
    return fams


def fonts(root):
    """返回一组 (family, size[, weight]) 元组,绑定到 root 上确保字体可用。

    注意 weight 在部分字体上不生效,这里只在 Mac/Win 的真名族上传 bold,
    否则用 size + 颜色对比度弥补。
    """
    _ensure_families(root)
    ui = pick_ui_family(root)
    mono = pick_mono_family(root)

    from ui.theme import Typography

    return {
        "ui": ui,
        "mono": mono,
        "title": (ui, Typography.TITLE_SIZE, Typography.TITLE_WEIGHT),
        "body": (ui, Typography.BODY_SIZE),
        "num": (mono, Typography.NUM_SIZE),
        "num_small": (mono, Typography.NUM_SMALL_SIZE),
        "detail": (ui, Typography.DETAIL_SIZE),
        "footer": (ui, Typography.FOOTER_SIZE),
        "badge": (ui, Typography.BADGE_SIZE),
    }


__all__ = [
    "pick_ui_family", "pick_mono_family", "fonts",
]
