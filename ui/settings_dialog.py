"""设置对话框:刷新间隔 / 告警阈值 / 月度预算 / 货币汇率 / 默认聚合单位。

入口:Header 的 ⚙ 按钮 → actions['open_settings']()

调用:
    SettingsDialog(parent, cfg, on_save=on_save_callback)
    on_save(new_cfg) 持久化后回调;父窗口可在回调里 reload 状态
"""

import tkinter as tk
from tkinter import messagebox, ttk

FONT = "Microsoft YaHei UI"
BG = "#1d1d2b"
BG_FIELD = "#15151d"
FG = "#e8e8f0"
DIM = "#8b8b9e"
OK = "#53d77a"
WARN = "#f0c24b"


class SettingsDialog(tk.Toplevel):
    INTERVAL_MIN, INTERVAL_MAX = 15, 3600
    PCT_MIN, PCT_MAX = 1, 99
    AMOUNT_MIN, AMOUNT_MAX = 0.0, 100000.0
    BUDGET_MIN, BUDGET_MAX = 0.0, 100000.0
    RATE_MIN, RATE_MAX = 0.1, 20.0

    def __init__(self, parent, cfg, on_save=None):
        super().__init__(parent)
        self.title("设置")
        self.configure(bg=BG)
        self.transient(parent)
        self.resizable(False, False)

        self._cfg = cfg
        self._on_save = on_save
        self._build_ui()
        self._bind_shortcuts()
        self._load(cfg)

        self.update_idletasks()
        self.grab_set()
        self.focus_set()

    def _build_ui(self):
        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=14, pady=12)

        rows = [
            ("刷新间隔(秒)", "refresh_interval_sec",
             "轮询各 provider 的周期;15–3600",
             self.INTERVAL_MIN, self.INTERVAL_MAX, "int"),
            ("金额告警阈值($)", "alert.warn_amount",
             "剩余金额低于此值时发橙色通知;0–100000",
             self.AMOUNT_MIN, self.AMOUNT_MAX, "float"),
            ("金额告警阈值(¥)", "alert.warn_amount_yuan",
             "人民币中转站告警阈值;0–100000",
             self.AMOUNT_MIN, self.AMOUNT_MAX, "float"),
            ("金额临界阈值($)", "alert.critical_amount",
             "剩余金额低于此值时发红色通知;0–100000",
             self.AMOUNT_MIN, self.AMOUNT_MAX, "float"),
            ("金额临界阈值(¥)", "alert.critical_amount_yuan",
             "人民币中转站临界阈值;0–100000",
             self.AMOUNT_MIN, self.AMOUNT_MAX, "float"),
            ("百分比告警阈值(%)", "alert.warn_pct",
             "剩余百分比低于此值时发橙色通知;1–99",
             self.PCT_MIN, self.PCT_MAX, "int"),
            ("百分比临界阈值(%)", "alert.critical_pct",
             "剩余百分比低于此值时发红色通知;1–99",
             self.PCT_MIN, self.PCT_MAX, "int"),
            ("告警冷却(分钟)", "alert.cooldown_min",
             "同一 provider 两次告警之间的最短间隔",
             0, 1440, "int"),
            ("月度预算($)", "aggregate.monthly_budget_usd",
             "底部汇总条参考线;0–100000",
             self.BUDGET_MIN, self.BUDGET_MAX, "float"),
            ("人民币兑美元汇率", "aggregate.currency_rate_cny_per_usd",
             "1 美元 = ? 人民币;用于聚合 CNY 列换算;0.1–20",
             self.RATE_MIN, self.RATE_MAX, "float"),
        ]

        self._vars = {}
        for i, (label, path, hint, lo, hi, vtype) in enumerate(rows):
            tk.Label(body, text=label, bg=BG, fg=FG,
                     font=(FONT, 10)).grid(row=i, column=0, sticky="w",
                                           pady=4, padx=(0, 8))
            v = tk.StringVar()
            e = tk.Entry(body, textvariable=v, width=14,
                         bg=BG_FIELD, fg=FG, insertbackground=FG,
                         font=(FONT, 10), relief="flat", justify="right")
            e.grid(row=i, column=1, sticky="e", pady=4)
            self._vars[path] = (v, vtype, lo, hi)
            tk.Label(body, text=hint, bg=BG, fg=DIM,
                     font=(FONT, 8)).grid(row=i, column=2, sticky="w",
                                          pady=4, padx=(8, 0))

        body.columnconfigure(2, weight=1)

        sep = tk.Frame(body, height=1, bg="#3a3a4a")
        sep.grid(row=len(rows), column=0, columnspan=3, sticky="ew", pady=(10, 6))

        btn_frame = tk.Frame(body, bg=BG)
        btn_frame.grid(row=len(rows) + 1, column=0, columnspan=3, sticky="e",
                        pady=(4, 0))
        tk.Button(btn_frame, text="取消", command=self.destroy,
                  bg="#2a2a3a", fg=FG, relief="flat", font=(FONT, 10),
                  width=10).pack(side="right", padx=(8, 0))
        tk.Button(btn_frame, text="保存", command=self._save,
                  bg=OK, fg="#15151d", relief="flat", font=(FONT, 10),
                  width=10).pack(side="right")

    def _bind_shortcuts(self):
        self.bind("<Escape>", lambda e: self.destroy())
        self.bind("<Return>", lambda e: self._save())

    def _load(self, cfg):
        for path, (var, vtype, lo, hi) in self._vars.items():
            parts = path.split(".")
            v = cfg
            for p in parts:
                if isinstance(v, dict):
                    v = v.get(p)
                else:
                    v = None
                    break
            if v is None:
                if vtype == "int":
                    v = lo if path.endswith("_min") or path.endswith("cooldown_min") else 30
                else:
                    v = 0.0
            var.set(f"{v:g}")

    def _save(self):
        cfg = self._cfg
        errors = []
        for path, (var, vtype, lo, hi) in self._vars.items():
            raw = var.get().strip()
            try:
                if vtype == "int":
                    val = int(float(raw))
                else:
                    val = float(raw)
            except ValueError:
                errors.append(f"{path}: 无效数字 '{raw}'")
                continue
            if val < lo or val > hi:
                errors.append(f"{path}: {val} 超出范围 [{lo}, {hi}]")
                continue
            parts = path.split(".")
            target = cfg
            for p in parts[:-1]:
                target = target.setdefault(p, {})
            target[parts[-1]] = val
        if errors:
            messagebox.showerror("设置错误", "\n".join(errors), parent=self)
            return
        if self._on_save:
            self._on_save(cfg)
        self.destroy()