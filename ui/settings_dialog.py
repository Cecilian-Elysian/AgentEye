"""设置对话框:仅保留最常用的 3 项 + 主题切换 + 添加 Key 入口。

入口:Header 的绿点(≡)按钮 → actions['open_settings']()

布局(全部在一屏内,560×420):
    ┌─ 设置 ────────────────────────────×
    │  主题: ○深色  ○浅色  ○跟随系统    │
    │  刷新间隔(秒):  [    ]            │
    │  金额临界阈值(¥): [    ]          │
    │  百分比告警阈值(%): [    ]        │
    │  ──────────────────────────────    │
    │  → 添加 API Key                    │  ← 打开独立的 AddKeyDialog
    │                  [取消] [保存设置]  │
    └────────────────────────────────────┘
"""
import tkinter as tk
from tkinter import messagebox

from ui.theme import PALETTE, set_theme, current_choice, to_tk_color, to_tk_color_blended
from ui.mac_toplevel import MacToplevel


FONT = "Microsoft YaHei UI"
BG = to_tk_color(PALETTE.BG)
BG_FIELD = to_tk_color(PALETTE.BAR_BG)
FG = to_tk_color(PALETTE.TEXT)
DIM = to_tk_color_blended(PALETTE.TEXT_DIM)
BTN_BG = to_tk_color(PALETTE.CARD_HOVER)


def _refresh_settings_palette():
    """主题切换时同步本模块的颜色常量。"""
    global BG, BG_FIELD, FG, DIM, BTN_BG
    BG = to_tk_color(PALETTE.BG)
    BG_FIELD = to_tk_color(PALETTE.BAR_BG)
    FG = to_tk_color(PALETTE.TEXT)
    DIM = to_tk_color_blended(PALETTE.TEXT_DIM)
    BTN_BG = to_tk_color(PALETTE.CARD_HOVER)


# 3 个保留设置项(label / cfg path / 提示 / lo / hi / vtype)
ROWS = [
    ("刷新间隔(秒)", "refresh_interval_sec",
     "轮询各 provider 的周期;15–3600",
     15, 3600, "int"),
    ("金额临界阈值(¥)", "alert.critical_amount_yuan",
     "人民币剩余金额 ≤ 此值时显示红色;0–100000",
     0.0, 100000.0, "float"),
    ("百分比告警阈值(%)", "alert.warn_pct",
     "剩余百分比 ≤ 此值时显示橙色;1–99",
     1, 99, "int"),
]

DEFAULTS = {
    "refresh_interval_sec": 30,
    "alert.critical_amount_yuan": 5.0,
    "alert.warn_pct": 30,
}


class SettingsDialog(MacToplevel):
    def __init__(self, parent, cfg, on_save=None, on_add_key=None):
        super().__init__(
            parent, title="设置",
            on_close=self._on_close_request,
            show_minimize=False,
            width=560, height=420,
            resizable=False,
        )
        self.transient(parent)

        self._cfg = cfg
        self._on_save = on_save
        self._on_add_key = on_add_key

        self._build_ui()
        self._load()
        self._bind_shortcuts()

        try:
            saved_theme = (cfg.get("ui") or {}).get("theme")
            if saved_theme in ("dark", "light", "auto"):
                self._theme_var.set(saved_theme)
        except Exception:
            pass

        self.update_idletasks()
        # 非模态:不 grab_set(),让用户能拖动主面板、点其他视图;
        # transient() 保证窗口始终浮在主窗口之上。
        self.focus_set()

    def _on_close_request(self):
        try:
            self.destroy()
        except tk.TclError:
            pass

    def refresh_palette(self):
        """主题切换时同步本地常量 + 重画 SettingsDialog 自己的 widget 配色。"""
        _refresh_settings_palette()
        try:
            self._apply_colors_to_tree()
            # 分隔线被 _apply_colors_to_tree 当普通 Frame 刷成背景色,单独补涂
            if getattr(self, "_sep", None) is not None:
                self._sep.config(bg=DIM)
        except tk.TclError:
            pass

    def _apply_colors_to_tree(self, root=None):
        """遍历 self.body 子树,按 widget class 套用 PALETTE 配色。"""
        if root is None:
            root = getattr(self, "_body_inner", None)
            if root is None:
                return
        try:
            cls = root.winfo_class()
            if cls in ("Frame", "Toplevel"):
                cur = str(root.cget("bg") or "")
                if cur not in ("", "#000000"):
                    root.configure(bg=BG)
        except tk.TclError:
            pass
        for w in root.winfo_children():
            cls = w.winfo_class()
            try:
                if cls in ("Frame", "Toplevel"):
                    if w.cget("bg") not in ("", "#000000"):
                        w.configure(bg=BG)
                elif cls == "Label":
                    fg = w.cget("fg")
                    if fg and isinstance(fg, str):
                        u = fg.upper()
                        if u in (DIM.upper(), "#8B8B9E", "#8b8b9e"):
                            w.configure(bg=BG, fg=DIM)
                        else:
                            w.configure(bg=BG, fg=FG)
                    else:
                        w.configure(bg=BG, fg=FG)
                elif cls == "Entry":
                    w.configure(bg=BG_FIELD, fg=FG, insertbackground=FG)
                elif cls == "Button":
                    w.configure(bg=BTN_BG, fg=FG)
                elif cls == "Radiobutton":
                    w.configure(bg=BG, fg=FG, selectcolor=BG_FIELD,
                                activebackground=BG, activeforeground=FG)
            except tk.TclError:
                pass
            self._apply_colors_to_tree(w)

    def _build_ui(self):
        body = tk.Frame(self.body, bg=BG)
        body.pack(fill="both", expand=True, padx=18, pady=14)
        self._body_inner = body

        # 主题 radio
        self._theme_var = tk.StringVar(value=current_choice())
        theme_frame = tk.Frame(body, bg=BG)
        theme_frame.grid(row=0, column=0, columnspan=3, sticky="we", pady=(0, 10))
        tk.Label(theme_frame, text="主题", bg=BG, fg=FG,
                 font=(FONT, 10)).grid(row=0, column=0, sticky="w",
                                       padx=(0, 8))
        for i, choice in enumerate(("dark", "light", "auto")):
            label = {"dark": "深色", "light": "浅色", "auto": "跟随系统"}[choice]
            rb = tk.Radiobutton(
                theme_frame, text=label, variable=self._theme_var, value=choice,
                bg=BG, fg=FG, selectcolor=BG_FIELD, activebackground=BG,
                activeforeground=FG, font=(FONT, 10), cursor="hand2",
                command=self._on_theme_radio_click,
            )
            rb.grid(row=0, column=i + 1, padx=(0, 12), sticky="w")
        theme_frame.columnconfigure(4, weight=1)

        # 3 个核心设置
        self._vars = {}
        for i, (label, path, hint, lo, hi, vtype) in enumerate(ROWS):
            row_idx = i + 1
            tk.Label(body, text=label, bg=BG, fg=FG,
                     font=(FONT, 10)).grid(row=row_idx, column=0, sticky="w",
                                           pady=5, padx=(0, 8))
            v = tk.StringVar()
            e = tk.Entry(body, textvariable=v, width=14,
                         bg=BG_FIELD, fg=FG, insertbackground=FG,
                         font=(FONT, 10), relief="flat", justify="right")
            e.grid(row=row_idx, column=1, sticky="e", pady=5)
            self._vars[path] = (v, vtype, lo, hi)
            tk.Label(body, text=hint, bg=BG, fg=DIM,
                     font=(FONT, 8)).grid(row=row_idx, column=2, sticky="w",
                                          pady=5, padx=(10, 0))
        body.columnconfigure(2, weight=1)

        # 添加 Key 入口(指向独立 AddKeyDialog)
        self._sep = tk.Frame(body, height=1, bg=DIM)
        self._sep.grid(row=len(ROWS) + 1, column=0, columnspan=3, sticky="ew",
                       pady=(12, 6))
        link = tk.Label(body, text="→ 添加 API Key", bg=BG, fg=FG,
                        font=(FONT, 10, "underline"), cursor="hand2")
        link.grid(row=len(ROWS) + 2, column=0, columnspan=3, sticky="w",
                  pady=(2, 4))
        link.bind("<Button-1>", self._open_add_key)
        tk.Label(body, text="在独立窗口里填 Base URL / API Key / 默认模型",
                 bg=BG, fg=DIM, font=(FONT, 8)).grid(
            row=len(ROWS) + 3, column=0, columnspan=3, sticky="w", pady=(0, 8))

        # 按钮行
        btn_frame = tk.Frame(body, bg=BG)
        btn_frame.grid(row=len(ROWS) + 4, column=0, columnspan=3,
                       sticky="e", pady=(8, 0))
        tk.Button(btn_frame, text="取消", command=self.destroy,
                  bg=BTN_BG, fg=FG, relief="flat", font=(FONT, 10),
                  width=10).pack(side="right", padx=(8, 0))
        tk.Button(btn_frame, text="保存设置", command=self._save,
                  bg="#3a3a4a", fg=FG, relief="flat", font=(FONT, 10),
                  width=10).pack(side="right")

    def _open_add_key(self, _event=None):
        """点击链接 → 打开独立 AddKeyDialog。"""
        if self._on_add_key:
            try:
                self._on_add_key()
            except Exception:
                pass

    def _on_theme_radio_click(self):
        """Radio 点击立即应用主题。"""
        choice = self._theme_var.get()
        set_theme(choice, broadcast=True, persist=False)

    def _save(self):
        cfg = self._cfg
        errors = []
        validated = []
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
            validated.append((path, val))
        if errors:
            messagebox.showerror("设置错误", "\n".join(errors), parent=self)
            return
        # 全部校验通过后才写入,避免校验失败时半改 cfg
        for path, val in validated:
            parts = path.split(".")
            target = cfg
            for p in parts[:-1]:
                target = target.setdefault(p, {})
            target[parts[-1]] = val
        ui = cfg.setdefault("ui", {})
        ui["theme"] = self._theme_var.get()
        set_theme(ui["theme"], broadcast=True, persist=False)
        if self._on_save:
            self._on_save(cfg)
        self.destroy()

    def _bind_shortcuts(self):
        self.bind("<Escape>", lambda e: self.destroy())

    def _load(self):
        """从 cfg 读 3 个 key,缺失走默认。"""
        cfg = self._cfg
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
                v = DEFAULTS.get(path, 0 if vtype == "int" else 0.0)
            var.set(f"{v:g}")