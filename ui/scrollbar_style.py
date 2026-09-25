"""macOS 风格 ttk 滚动条。

Tk 默认 Scrollbar 是浅色硬矩形,与深色主题严重冲突。
这里用 ttk.Style 注册一套深色风格:

- 滑块 (thumb): 圆形胶囊,#FFFFFF80 → #FFFFFFB3 (hover)
- 槽 (trough): 透明,只留 6px 宽
- 上下箭头: 不显示 (macOS 风)
- 宽度: 8px

使用:
    from ui.scrollbar_style import make_dark_scrollbar
    sb = make_dark_scrollbar(parent, orient="vertical", command=...)
"""

import tkinter as tk
from tkinter import ttk

from ui.theme import PALETTE, Layout


_STYLE_NAME_V = "AgentEye.Vertical.TScrollbar"
_STYLE_NAME_H = "Agenteye.Horizontal.TScrollbar"

_SLIDER_IDLE = "#5C5C66"
_SLIDER_HOVER = "#8E8E99"
_TROUGH = PALETTE.BG


def _configure_style(style):
    """注册 / 覆盖 ttk 风格。重复调用是幂等的。"""
    try:
        style.element_create("CustomThumb", "image", _thumb_image(),
                             ("active", _thumb_image(active=True)))
    except tk.TclError:
        pass

    style.configure(
        _STYLE_NAME_V,
        troughcolor=_TROUGH,
        background=_SLIDER_IDLE,
        darkcolor=_TROUGH,
        lightcolor=_TROUGH,
        bordercolor=_TROUGH,
        arrowcolor=PALETTE.TEXT_DIM,
        borderwidth=0,
        arrowsize=0,
        gripcount=0,
        relief="flat",
        width=8,
    )
    style.map(
        _STYLE_NAME_V,
        background=[("active", _SLIDER_HOVER), ("pressed", _SLIDER_HOVER),
                    ("disabled", _TROUGH)],
        arrowcolor=[("disabled", _TROUGH)],
    )

    style.configure(
        _STYLE_NAME_H,
        troughcolor=_TROUGH,
        background=_SLIDER_IDLE,
        darkcolor=_TROUGH,
        lightcolor=_TROUGH,
        bordercolor=_TROUGH,
        arrowcolor=PALETTE.TEXT_DIM,
        borderwidth=0,
        arrowsize=0,
        gripcount=0,
        relief="flat",
        width=8,
    )
    style.map(
        _STYLE_NAME_H,
        background=[("active", _SLIDER_HOVER), ("pressed", _SLIDER_HOVER),
                    ("disabled", _TROUGH)],
        arrowcolor=[("disabled", _TROUGH)],
    )


_STYLE_CONFIGURED = False


def _ensure_style(root):
    global _STYLE_CONFIGURED
    if _STYLE_CONFIGURED:
        return
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    _configure_style(style)
    _STYLE_CONFIGURED = True


def _thumb_image(active=False):
    """生成 8x32 圆角胶囊 PNG,用 tk.PhotoImage 拼像素。

    仅用来让 element_create 不抛错;真正的视觉由 style.configure 的
    background 色块决定。这个函数若失败,style 仍可用,只是没有自定义 element。
    """
    color = _SLIDER_HOVER if active else _SLIDER_IDLE
    w, h = 8, 32
    img = tk.PhotoImage(width=w, height=h)
    img.put(color, to=(2, 8, w - 2, h - 8))
    img.put(color, to=(3, 4, w - 3, h - 4))
    img.put(color, to=(4, 2, w - 4, h - 2))
    return img


def make_dark_scrollbar(parent, orient="vertical", command=None):
    """工厂:返回 ttk.Scrollbar 实例,已应用 macOS 深色风格。"""
    _ensure_style(parent.winfo_toplevel())
    style_name = _STYLE_NAME_V if orient == "vertical" else _STYLE_NAME_H
    return ttk.Scrollbar(parent, orient=orient, style=style_name,
                         command=command)


__all__ = ["make_dark_scrollbar", "_ensure_style"]
