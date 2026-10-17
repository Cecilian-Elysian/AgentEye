"""ttk 滚动条样式。

Tk 默认滚动条是浅色硬矩形,与深色主题严重冲突。这里用 ttk.Style 注册一套
极简风格的滚动条:

- 滑块 (thumb): 圆角胶囊,THUMB_IDLE → THUMB_HOVER (hover/pressed)
- 槽 (trough): 与窗口同底,不画出来
- 上下箭头: 不显示
- 宽度: 6px

主题切换:refresh_style() 会把已注册的风格用当前 PALETTE 重配一遍。
以前这个函数只是把一个没人读的标志位清零,切到浅色主题后已有的滚动条
仍然是深色 thumb(AGENTS.md 规则 3 的坑)。ui/theme.set_theme 广播时
会回调它,见 theme.on_theme_change 的默认监听者。

注意:ttk 的 style 是**按解释器**注册的,和 Tk root 走的是同一条路,所以
这里必须记住建过的 Style 实例才能在切换后重配;只记一个最新的不够——
测试里会反复建销多个 root。
"""

import tkinter as tk
from tkinter import ttk

from ui.theme import PALETTE, on_theme_change, to_tk_color, to_tk_color_blended


_STYLE_NAME_V = "AgentEye.Vertical.TScrollbar"
_STYLE_NAME_H = "AgentEye.Horizontal.TScrollbar"

WIDTH = 6

# 建过的 ttk.Style 实例。弱引用不够:Style 是 tkinter 的代理对象,
# 滚动条 widget 还活着时它就不会被回收,但显式清理更省事。
_STYLES = []


def _slider_colors():
    """主题相关的滚动条滑块颜色。light mode 给低对比深灰避免白上加白。"""
    return to_tk_color(PALETTE.THUMB_IDLE), to_tk_color(PALETTE.THUMB_HOVER)


def _configure_style(style):
    """注册 / 覆盖 ttk 风格。重复调用是幂等的。"""
    idle, hover = _slider_colors()
    trough = to_tk_color(PALETTE.BG)
    arrow = to_tk_color_blended(PALETTE.TEXT_DIM)
    for name in (_STYLE_NAME_V, _STYLE_NAME_H):
        style.configure(
            name,
            troughcolor=trough,
            background=idle,
            darkcolor=trough,
            lightcolor=trough,
            bordercolor=trough,
            arrowcolor=arrow,
            borderwidth=0,
            arrowsize=0,
            gripcount=0,
            relief="flat",
            width=WIDTH,
        )
        style.map(
            name,
            background=[("active", hover), ("pressed", hover),
                        ("disabled", trough)],
            arrowcolor=[("disabled", trough)],
        )


def _ensure_style(root):
    """在 root 对应的解释器上注册滚动条风格,返回 ttk.Style。

    只在首次为该 root 建风格时切 theme_use("clam");重复调用幂等。
    """
    style = ttk.Style(root)
    if not any(s.master is root for s in _STYLES):
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
    _configure_style(style)
    if style not in _STYLES:
        _STYLES.append(style)
    return style


def refresh_style(*_args):
    """主题切换时用当前 PALETTE 重配所有已注册的滚动条风格。

    由 ui/theme.on_theme_change 广播驱动,签名兼容 (choice, palette, persist)。
    样式对象可能已随 root 销毁,逐个 try 掉,不让一条死 Style 阻断广播。
    """
    alive = []
    for style in list(_STYLES):
        try:
            _configure_style(style)
            alive.append(style)
        except tk.TclError:
            continue
        except Exception:
            alive.append(style)
    _STYLES[:] = alive


def make_dark_scrollbar(parent, orient="vertical", command=None):
    """工厂:返回 ttk.Scrollbar 实例,已应用深色风格。"""
    _ensure_style(parent.winfo_toplevel())
    style_name = _STYLE_NAME_V if orient == "vertical" else _STYLE_NAME_H
    return ttk.Scrollbar(parent, orient=orient, style=style_name,
                         command=command)


# 主题切换时重配一次。用 on_theme_change 而不是 bind_theme_listener:
# 本模块的生命周期跟 root 无关(ttk style 是按解释器注册的),
# 没有一个具体的 widget 可以挂 <Destroy> 反注册。
on_theme_change(refresh_style)


__all__ = ["make_dark_scrollbar", "_ensure_style", "refresh_style",
           "_STYLE_NAME_V", "_STYLE_NAME_H"]
