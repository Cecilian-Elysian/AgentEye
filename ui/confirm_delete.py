"""危险操作确认对话框:要求输入指定名字才能确认。

典型场景:删除 provider。简单 messagebox.askyesno 不够稳(误点),
所以加一道"输入名字"门槛。
"""

import tkinter as tk
from tkinter import ttk


FONT = "Microsoft YaHei UI"
BG = "#1d1d2b"
BG_FIELD = "#15151d"
FG = "#e8e8f0"
DIM = "#8b8b9e"
OK = "#53d77a"
CRITICAL = "#ff5d5d"
BTN_BG = "#2a2a3a"


class ConfirmDeleteDialog(tk.Toplevel):
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
        super().__init__(parent)
        self._expected = str(name)
        self._on_confirm = on_confirm
        self.title(title)
        self.configure(bg=BG)
        self.resizable(False, False)
        self.transient(parent)

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=18, pady=14)

        tk.Label(
            body, text=message or f"删除 {self._expected} 不可恢复。",
            bg=BG, fg=FG, font=(FONT, 10), wraplength=360, justify="left",
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))

        tk.Label(
            body, text=f"请输入名字 {self._expected} 以确认:",
            bg=BG, fg=DIM, font=(FONT, 9),
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 4))

        self._var = tk.StringVar()
        entry = tk.Entry(
            body, textvariable=self._var, width=32,
            bg=BG_FIELD, fg=FG, insertbackground=FG,
            font=(FONT, 10), relief="flat",
        )
        entry.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0, 12))
        self._var.trace_add("write", lambda *a: self._refresh_state())

        btn_frame = tk.Frame(body, bg=BG)
        btn_frame.grid(row=3, column=0, columnspan=2, sticky="e")
        tk.Button(
            btn_frame, text="取消", command=self._cancel,
            bg=BTN_BG, fg=FG, relief="flat", font=(FONT, 10), width=10,
        ).pack(side="right", padx=(8, 0))
        self.confirm_btn = tk.Button(
            btn_frame, text="确认删除", command=self._do_confirm,
            bg=CRITICAL, fg="#15151d", relief="flat", font=(FONT, 10),
            width=10, state="disabled",
        )
        self.confirm_btn.pack(side="right")

        body.columnconfigure(0, weight=1)

        self.bind("<Escape>", lambda e: self._cancel())
        self.bind("<Return>", lambda e: self._do_confirm()
                  if str(self.confirm_btn["state"]) == "normal" else None)

        self.update_idletasks()
        try:
            x = parent.winfo_x() + (parent.winfo_width() - self.winfo_width()) // 2
            y = parent.winfo_y() + (parent.winfo_height() - self.winfo_height()) // 2
            self.geometry(f"+{max(0, x)}+{max(0, y)}")
        except tk.TclError:
            pass

        self.grab_set()
        self.focus_set()
        entry.focus_set()

    def _refresh_state(self):
        if self._var.get() == self._expected:
            self.confirm_btn.config(state="normal")
        else:
            self.confirm_btn.config(state="disabled")

    def _do_confirm(self):
        if self._var.get() != self._expected:
            return
        cb = self._on_confirm
        self.destroy()
        if cb:
            try:
                cb()
            except Exception:
                pass

    def _cancel(self):
        self.destroy()
