"""Aggregate detail 弹窗:展示按贡献度排序的 provider 明细。"""

import tkinter as tk


class AggregateDetail(tk.Toplevel):
    def __init__(self, parent, agg):
        super().__init__(parent)
        self.title("总额度明细")
        self.configure(bg="#1d1d2b")
        self.resizable(False, False)
        self.transient(parent)

        BG = "#1d1d2b"
        FG = "#e8e8f0"
        DIM = "#8b8b9e"
        FONT = ("Microsoft YaHei UI", 10)

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=14, pady=12)

        header = f"剩余 ${agg['total_usd']:.2f}"
        if agg["used_usd"]:
            header += f"  ·  已用 ${agg['used_usd']:.2f}"
        if agg["total_budget_usd"] > 0:
            pct = agg.get("pct") or 0
            header += f"  ·  预算 ${agg['total_budget_usd']:.0f} ({pct:.0f}%)"

        tk.Label(body, text=header, font=(FONT[0], 11, "bold"),
                 bg=BG, fg=FG).pack(anchor="w", pady=(0, 8))

        tk.Frame(body, height=1, bg="#3a3a4a").pack(fill="x", pady=4)

        table = tk.Frame(body, bg=BG)
        table.pack(fill="both", expand=True)
        table.columnconfigure(1, weight=1)

        cols = [("Provider", 14), ("剩余 USD", 12), ("Level", 10)]
        for i, (name, w) in enumerate(cols):
            tk.Label(table, text=name, font=(FONT[0], 9, "bold"),
                     bg=BG, fg=DIM, width=w, anchor="w").grid(
                row=0, column=i, sticky="w", padx=(0, 12), pady=(4, 4))

        if not agg["breakdown"]:
            tk.Label(table, text="(无数据)", bg=BG, fg=DIM,
                     font=FONT).grid(row=1, column=0, columnspan=3, pady=8)
        else:
            colors = {"ok": "#53d77a", "warn": "#f0c24b",
                      "critical": "#ff5d5d", "error": "#ff8f6b",
                      "unconfigured": "#5b5b68", "unknown": "#8b8b9e"}
            for i, b in enumerate(agg["breakdown"], start=1):
                tk.Label(table, text=b["name"], bg=BG, fg=FG,
                         font=FONT).grid(row=i, column=0, sticky="w", padx=(0, 12), pady=2)
                tk.Label(table, text=f"${b['remaining_usd']:.2f}",
                         bg=BG, fg=FG, font=FONT).grid(
                    row=i, column=1, sticky="w", padx=(0, 12), pady=2)
                tk.Label(table, text=b["level"],
                         bg=BG, fg=colors.get(b["level"], DIM),
                         font=FONT).grid(row=i, column=2, sticky="w", pady=2)

        tk.Button(body, text="关闭", command=self.destroy,
                  bg="#2a2a3a", fg=FG, relief="flat", font=FONT,
                  width=10).pack(side="right", pady=(8, 0))

        self.bind("<Escape>", lambda e: self.destroy())
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_y() + 40
        self.geometry(f"+{max(0, x)}+{max(0, y)}")
        self.grab_set()
        self.focus_set()
