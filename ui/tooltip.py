"""轻量 tooltip。

model_panel 原有一份私有实现,行卡也要用后抽成共享模块:
- attach(widget, get_text):进入 600ms 后显示,get_text() 返回 None
  则不显示(行卡的文本随轮询变化,所以传 getter 而不是静态串)
- 主题色实时取 PALETTE,不冻结
- Leave/按下/销毁都会收掉弹窗,不残留 overrideredirect 窗口
"""

import tkinter as tk

from ui.theme import PALETTE, to_tk_color


def attach(widget, get_text, delay_ms=600, owner=None):
    """给 widget 挂 tooltip。get_text() 返回展示文本,None 表示不弹。

    返回 _hide,便于调用方在销毁前手动收掉(一般不必,Tk 的
    <Destroy> 绑定已兜底)。
    """
    owner = owner or widget
    state = {"win": None, "aid": None}

    def _hide(_event=None):
        if state["aid"] is not None:
            try:
                owner.after_cancel(state["aid"])
            except tk.TclError:
                pass
            state["aid"] = None
        if state["win"] is not None:
            try:
                state["win"].destroy()
            except tk.TclError:
                pass
            state["win"] = None

    def _show():
        state["aid"] = None
        try:
            text = get_text()
        except Exception:
            text = None
        if not text or state["win"] is not None:
            return
        try:
            x = widget.winfo_rootx() + 16
            y = widget.winfo_rooty() + widget.winfo_height() + 4
        except tk.TclError:
            return
        win = tk.Toplevel(owner)
        win.wm_overrideredirect(True)
        win.wm_geometry(f"+{x}+{y}")
        tk.Label(win, text=text,
                 bg=to_tk_color(PALETTE.CARD_HOVER),
                 fg=to_tk_color(PALETTE.TEXT),
                 font=("Microsoft YaHei UI", 9),
                 justify="left", padx=8, pady=3,
                 relief="flat").pack()
        state["win"] = win

    def _schedule(_event=None):
        _hide()
        try:
            state["aid"] = owner.after(delay_ms, _show)
        except tk.TclError:
            pass

    widget.bind("<Enter>", _schedule, add="+")
    widget.bind("<Leave>", _hide, add="+")
    widget.bind("<ButtonPress>", _hide, add="+")
    widget.bind("<Destroy>", _hide, add="+")
    return _hide


__all__ = ["attach"]
