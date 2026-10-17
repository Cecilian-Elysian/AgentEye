"""危险操作确认对话框:要求输入指定名字才能确认。

典型场景:删除 provider。简单 messagebox.askyesno 不够稳(误点),
所以加一道"输入名字"门槛。
"""

import tkinter as tk

from ui.theme import PALETTE, Layout, Typography, to_tk_color
from ui.fonts import pick_ui_family
from ui.paint import FlatButton, FocusEntry
from ui.mac_toplevel import MacToplevel


FONT = pick_ui_family()


class ConfirmDeleteDialog(MacToplevel):
    """弹模态框,要求输入 expected_name 才能按"确认"。

    用法:
        ConfirmDeleteDialog(parent, name="元序",
                             message="删除 provider 不可恢复。",
                             on_confirm=lambda: do_delete())

    - grab_set() 模态,焦点不能跑到主面板
    - 默认确认按钮 disabled,输入 == name 时 enabled
    - Esc 取消
    """

    def __init__(self, parent, name, message="", on_confirm=None,
                 title="删除确认"):
        super().__init__(
            parent, title=title,
            on_close=self._cancel,
            show_minimize=False,
            width=420, height=240,
            resizable=False,
        )
        self.transient(parent)
        self._expected = str(name)
        self._on_confirm = on_confirm

        bg = to_tk_color(PALETTE.BG)
        body = tk.Frame(self.body, bg=bg)
        body.pack(fill="both", expand=True, padx=18, pady=14)

        tk.Label(
            body, text=message or f"删除 {self._expected} 不可恢复。",
            bg=bg, fg=to_tk_color(PALETTE.TEXT),
            font=(FONT, Typography.BODY_SIZE), wraplength=360, justify="left",
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))

        tk.Label(
            body, text=f"请输入名字 {self._expected} 以确认:",
            bg=bg, fg=to_tk_color(PALETTE.OFF),
            font=(FONT, Typography.DETAIL_SIZE),
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 4))

        self._var = tk.StringVar()
        self.entry = FocusEntry(
            body, textvariable=self._var, width=32,
            font=(FONT, Typography.BODY_SIZE),
        )
        self.entry.grid(row=2, column=0, columnspan=2, sticky="ew",
                        pady=(0, 12))
        self._var.trace_add("write", lambda *a: self._refresh_state())

        btn_frame = tk.Frame(body, bg=bg)
        btn_frame.grid(row=3, column=0, columnspan=2, sticky="e")
        FlatButton(btn_frame, variant="ghost", text="取消",
                   on_click=self._cancel, width=10).pack(side="right",
                                                          padx=(8, 0))
        self.confirm_btn = FlatButton(
            btn_frame, variant="danger", text="确认删除",
            on_click=self._do_confirm, width=10, state="disabled",
        )
        self.confirm_btn.pack(side="right")

        body.columnconfigure(0, weight=1)

        self.bind("<Escape>", lambda e: self._cancel())
        self.bind("<Return>", lambda e: self._do_confirm()
                  if str(self.confirm_btn["state"]) == "normal" else None)

        # grab 不能在构造里立即调:窗口尚未 map 时抛
        # "grab failed: window not viewable"。挂到 <Map>,映射后自动拿到
        self.bind("<Map>", self._grab_when_viewable, add="+")
        self.focus_set()
        self.entry.focus_set()

    def _grab_when_viewable(self, e=None):
        try:
            self.grab_set()
        except tk.TclError:
            pass

    def refresh_palette(self):
        """主题切换:逐个控件问它自己"新配色是什么"。

        旧实现是 walk 子树 + 读当前 fg/bg 猜语义(靠 `#8B8B9E` / `#FF5D5D`
        这类历史色值当哨兵),新控件一旦换了配色就猜错,而且哨兵会随主题
        一起失效。让每个控件自己 refresh_palette,加控件时不用改这里。
        """
        bg = to_tk_color(PALETTE.BG)
        try:
            self.body.configure(bg=bg)
            for w in self.body.winfo_children():
                self._walk_refresh(w, bg)
        except tk.TclError:
            pass

    def _walk_refresh(self, w, bg):
        refresh = getattr(w, "refresh_palette", None)
        if callable(refresh):
            try:
                refresh()
            except tk.TclError:
                pass
        else:
            try:
                if w.winfo_class() in ("Frame", "Label"):
                    w.configure(bg=bg)
            except tk.TclError:
                pass
        for c in w.winfo_children():
            self._walk_refresh(c, bg)

    def _refresh_state(self):
        if self._var.get() == self._expected:
            self.confirm_btn.config(state="normal")
        else:
            self.confirm_btn.config(state="disabled")

    def _do_confirm(self):
        if self._var.get() != self._expected:
            return
        cb = self._on_confirm
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()
        if cb:
            try:
                cb()
            except Exception:
                pass

    def _cancel(self):
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()
