"""设置对话框:刷新间隔 / 告警阈值 / 月度预算 / 汇率 + 同一页添加 Key。

入口:Header 的 ≡ 按钮 → actions['open_settings']()

布局:
    ┌─ 设置 ──────────────┐
    │  刷新间隔  [...]  提示 │
    │  告警阈值  [...]  提示 │
    │  ...                 │
    │  ─── 分隔 ───        │
    │  添加 Key            │
    │  [MiniMax][DeepSeek][智谱][OpenCode][中转]│
    │  Base URL  [____]    │
    │  API Key   [____]    │
    │  名称      [____]    │
    │  [预览]              │
    │        [取消] [保存] │
    └──────────────────────┘
"""

import threading
import time
import tkinter as tk
from tkinter import messagebox

from providers import detect as detect_mod


FONT = "Microsoft YaHei UI"
BG = "#1d1d2b"
BG_FIELD = "#15151d"
FG = "#e8e8f0"
DIM = "#8b8b9e"
OK = "#53d77a"
CRITICAL = "#ff5d5d"
BTN_BG = "#2a2a3a"


PRESETS = [
    ("MiniMax",    "minimax",     "https://api.minimaxi.com"),
    ("DeepSeek",   "deepseek",    "https://api.deepseek.com"),
    ("智谱 GLM",   "zhipu",       "https://open.bigmodel.cn"),
    ("OpenCode",   "opencode_go", "https://opencode.ai"),
    ("中转站",     "relay",       ""),
]


class SettingsDialog(tk.Toplevel):
    INTERVAL_MIN, INTERVAL_MAX = 15, 3600
    PCT_MIN, PCT_MAX = 1, 99
    AMOUNT_MIN, AMOUNT_MAX = 0.0, 100000.0
    BUDGET_MIN, BUDGET_MAX = 0.0, 100000.0
    RATE_MIN, RATE_MAX = 0.1, 20.0
    PROBE_TIMEOUT = 8.0

    def __init__(self, parent, cfg, on_save=None, on_add_key=None,
                 generic_probe=None, current_count=0):
        super().__init__(parent)
        self.title("设置")
        self.configure(bg=BG)
        self.transient(parent)
        self.resizable(True, True)

        self._cfg = cfg
        self._on_save = on_save
        self._on_add_key = on_add_key
        self._generic_probe = generic_probe or (lambda *a, **k: None)
        self._current_count = current_count
        self._probe_thread = None

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
        sep.grid(row=len(rows), column=0, columnspan=3, sticky="ew",
                 pady=(10, 8))

        self._build_add_key_section(body, start_row=len(rows) + 1)

    def _build_add_key_section(self, parent, start_row):
        tk.Label(parent, text="添加 Key", bg=BG, fg=FG,
                 font=(FONT, 10, "bold")).grid(
            row=start_row, column=0, columnspan=3, sticky="w",
            pady=(2, 6))

        FONT_S = (FONT, 9)

        preset_frame = tk.Frame(parent, bg=BG)
        preset_frame.grid(row=start_row + 1, column=0, columnspan=3,
                          sticky="w", pady=(0, 6))
        for i, (label, kind, url) in enumerate(PRESETS):
            b = tk.Label(preset_frame, text=label, font=FONT_S,
                         bg=BTN_BG, fg=FG, padx=10, pady=4, cursor="hand2")
            b.grid(row=0, column=i, padx=(0, 6))
            b.bind("<Button-1>",
                   lambda e, k=kind, u=url, lbl=label:
                       self._apply_add_preset(k, u, lbl))
            b.bind("<Enter>", lambda e, w=b: w.config(bg="#3a3a4a"))
            b.bind("<Leave>", lambda e, w=b: w.config(bg=BTN_BG))

        tk.Label(parent, text="Base URL", bg=BG, fg=FG,
                 font=(FONT, 10)).grid(row=start_row + 2, column=0,
                                       sticky="w", pady=4, padx=(0, 8))
        self.add_url_var = tk.StringVar()
        tk.Entry(parent, textvariable=self.add_url_var, width=44,
                 bg=BG_FIELD, fg=FG, insertbackground=FG,
                 font=(FONT, 10), relief="flat").grid(
            row=start_row + 2, column=1, columnspan=2, sticky="ew",
            pady=4)

        tk.Label(parent, text="API Key", bg=BG, fg=FG,
                 font=(FONT, 10)).grid(row=start_row + 3, column=0,
                                       sticky="w", pady=4, padx=(0, 8))
        self.add_key_var = tk.StringVar()
        self.add_key_entry = tk.Entry(parent, textvariable=self.add_key_var,
                                      width=44, bg=BG_FIELD, fg=FG,
                                      insertbackground=FG, font=(FONT, 10),
                                      relief="flat", show="•")
        self.add_key_entry.grid(row=start_row + 3, column=1, columnspan=2,
                                sticky="ew", pady=4)
        self.add_key_entry.insert(0, "粘贴 API key")
        self.add_key_entry.config(foreground=DIM)
        self._add_key_placeholder = True
        self.add_key_entry.bind("<FocusIn>", self._add_key_focus_in)
        self.add_key_entry.bind("<FocusOut>", self._add_key_focus_out)
        self.add_key_entry.bind("<KeyRelease>",
                                lambda e: self._schedule_probe(delay=0.6))

        tk.Label(parent, text="显示名称", bg=BG, fg=FG,
                 font=(FONT, 10)).grid(row=start_row + 4, column=0,
                                       sticky="w", pady=4, padx=(0, 8))
        self.add_name_var = tk.StringVar()
        tk.Entry(parent, textvariable=self.add_name_var, width=44,
                 bg=BG_FIELD, fg=FG, insertbackground=FG,
                 font=(FONT, 10), relief="flat").grid(
            row=start_row + 4, column=1, columnspan=2, sticky="ew",
            pady=4)

        tk.Label(parent, text="预览", bg=BG, fg=DIM,
                 font=(FONT, 9)).grid(row=start_row + 5, column=0,
                                       sticky="nw", pady=(6, 4),
                                       padx=(0, 8))
        self.add_preview = tk.Text(parent, height=5, width=50,
                                   bg=BG_FIELD, fg=FG, font=FONT_S,
                                   relief="flat", wrap="word",
                                   state="disabled")
        self.add_preview.grid(row=start_row + 5, column=1, columnspan=2,
                              sticky="ew", pady=(6, 4))
        self._set_add_preview("等待输入 key …")

        sep2 = tk.Frame(parent, height=1, bg="#3a3a4a")
        sep2.grid(row=start_row + 6, column=0, columnspan=3, sticky="ew",
                  pady=(10, 6))

        btn_frame = tk.Frame(parent, bg=BG)
        btn_frame.grid(row=start_row + 7, column=0, columnspan=3,
                       sticky="e", pady=(4, 0))
        tk.Button(btn_frame, text="取消", command=self.destroy,
                  bg=BTN_BG, fg=FG, relief="flat", font=(FONT, 10),
                  width=10).pack(side="right", padx=(8, 0))
        self.add_btn = tk.Button(btn_frame, text="添加", command=self._add_now,
                                 bg=OK, fg="#15151d", relief="flat",
                                 font=(FONT, 10), width=10, state="disabled")
        self.add_btn.pack(side="right", padx=(8, 0))
        tk.Button(btn_frame, text="保存设置", command=self._save,
                  bg="#3a3a4a", fg=FG, relief="flat", font=(FONT, 10),
                  width=10).pack(side="right")

    def _add_key_focus_in(self, e):
        if self._add_key_placeholder:
            self.add_key_entry.delete(0, "end")
            self.add_key_entry.config(foreground=FG, show="•")
            self._add_key_placeholder = False

    def _add_key_focus_out(self, e):
        if not self.add_key_var.get().strip():
            self.add_key_entry.delete(0, "end")
            self.add_key_entry.insert(0, "粘贴 API key")
            self.add_key_entry.config(foreground=DIM, show="")
            self._add_key_placeholder = True

    def _apply_add_preset(self, kind, url, label):
        self.add_url_var.set(url)
        if not self.add_name_var.get().strip():
            self.add_name_var.set(label)
        self.add_key_entry.focus_set()

    def _set_add_preview(self, text):
        self.add_preview.config(state="normal")
        self.add_preview.delete("1.0", "end")
        self.add_preview.insert("1.0", text)
        self.add_preview.config(state="disabled")

    def _schedule_probe(self, delay=0.3):
        if self._probe_thread and self._probe_thread.is_alive():
            return
        self.after(int(delay * 1000), self._probe_now)

    def _probe_now(self):
        if self._probe_thread and self._probe_thread.is_alive():
            return
        if self._add_key_placeholder:
            self._set_add_preview("等待输入 key …")
            self.add_btn.config(state="disabled")
            return
        key = self.add_key_var.get().strip()
        url = self.add_url_var.get().strip()
        if not key:
            self._set_add_preview("等待输入 key …")
            self.add_btn.config(state="disabled")
            return
        self._set_add_preview("探测中 …")
        self.add_btn.config(state="disabled")
        self._probe_started_at = time.time()
        self._probe_thread = threading.Thread(
            target=self._probe_worker, args=(key, url), daemon=True)
        self._probe_thread.start()

    def _probe_worker(self, key, url):
        detected = detect_mod.detect(key, url)
        probe_result = None
        if detected["kind"] in ("minimax", "deepseek", "zhipu", "opencode_go",
                                "generic_openai") and detected["base_url"]:
            try:
                probe_result = self._generic_probe(detected["base_url"], key,
                                                   timeout=self.PROBE_TIMEOUT)
            except Exception as e:
                probe_result = {"error": str(e)}
        elapsed = time.time() - self._probe_started_at
        self.after(0, self._probe_done, detected, probe_result, elapsed)

    def _probe_done(self, detected, probe_result, elapsed):
        lines = [
            f"类型:     {detected['kind']}",
            f"置信度:   {detected['confidence']}",
            f"Base URL: {detected['base_url'] or '(未提供)'}",
            f"依据:     {detected['notes']}",
        ]
        if probe_result is not None:
            if probe_result.get("error"):
                lines.append(f"探测:     失败 - {probe_result['error']}")
            else:
                models = probe_result.get("models") or []
                lines.append(f"模型数:   {len(models)}")
                for m in models[:5]:
                    lines.append(f"          · {m}")
                if len(models) > 5:
                    lines.append(f"          · … 共 {len(models)} 个")
                if probe_result.get("quota_endpoint"):
                    lines.append(f"额度端点: {probe_result['quota_endpoint']}")
                if probe_result.get("remaining") is not None:
                    unit = probe_result.get("unit", "")
                    lines.append(f"余额:     {unit}{probe_result['remaining']:.2f}")
        lines.append(f"\n耗时:     {elapsed:.1f}s")
        self._set_add_preview("\n".join(lines))
        if not self.add_name_var.get().strip() and detected["kind"]:
            pretty = {"minimax": "MiniMax", "deepseek": "DeepSeek",
                      "zhipu": "智谱 GLM", "opencode_go": "OpenCode Go",
                      "relay": "中转站"}.get(detected["kind"], detected["kind"])
            self.add_name_var.set(pretty)
        ok = detected["kind"] and (detected["base_url"]
                                    or detected["kind"] != "generic_openai")
        if ok and probe_result and not probe_result.get("error"):
            self.add_btn.config(state="normal")
        elif ok and detected["kind"] != "generic_openai":
            self.add_btn.config(state="normal")
        else:
            self.add_btn.config(state="disabled")

    def _add_now(self):
        if self._add_key_placeholder:
            return
        key = self.add_key_var.get().strip()
        url = self.add_url_var.get().strip()
        name = self.add_name_var.get().strip() or "未命名"
        if not key:
            return
        entry = {"name": name, "key": key, "base_url": url}
        if self._on_add_key:
            try:
                self._on_add_key(entry)
            except Exception:
                pass
        self._current_count += 1
        self.add_key_var.set("")
        self.add_url_var.set("")
        self.add_name_var.set("")
        self._add_key_placeholder = True
        self.add_key_entry.delete(0, "end")
        self.add_key_entry.insert(0, "粘贴 API key")
        self.add_key_entry.config(foreground=DIM, show="")
        self._set_add_preview(f"已添加 {name}。可继续添加下一个,或点保存设置关闭窗口。")

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

    def _bind_shortcuts(self):
        self.bind("<Escape>", lambda e: self.destroy())

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
