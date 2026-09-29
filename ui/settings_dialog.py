"""设置对话框:主题 + 3 项常用设置 + provider 管理,全部集成在单一视图内。

入口:Header 的绿点(≡)按钮 → actions['open_settings']()

单窗口单视图(560×620),仅中间区在「列表 ↔ 表单」间切换:
┌─ 设置 ────────────────────────────×
│  主题: ○深色  ○浅色  ○跟随系统    │
│  刷新间隔(秒):  [    ]            │
│  金额临界阈值(¥): [    ]          │
│  百分比告警阈值(%): [    ]        │
│  ──────────────────────────────    │
│  API 管理                    共 N 个│
│  ┌ name  kind        [编辑][删除] ┐│
│  └ base_url                      ┘│
│  (可滚动;空列表显示提示)          │
│              → 添加 API Key        │
│  ── 表单模式(点添加/编辑后)──    │
│  ← 返回列表                        │
│  (AddKeyForm:空白或预填)          │
│                  [取消] [保存设置]  │
└────────────────────────────────────┘

行为:
- 添加/编辑/删除均即时生效落盘(宿主回调),“保存设置”只管数值项
- 表单模式下“保存设置”置灰,避免与表单“保存”混淆
- initial_view: None → 列表;"add_key" → 空白表单;("edit", pid) → 预填表单
"""
import tkinter as tk
from tkinter import messagebox

from config import plain_key
from ui.theme import PALETTE, set_theme, current_choice, to_tk_color, to_tk_color_blended
from ui.mac_toplevel import MacToplevel
from ui.scrollbar_style import make_dark_scrollbar

VIEW_SETTINGS = "settings"
VIEW_ADD_KEY = "add_key"

KIND_LABELS = {
    "minimax": "MiniMax",
    "deepseek": "DeepSeek",
    "zhipu": "智谱 GLM",
    "opencode_go": "OpenCode Go",
    "relay": "中转站",
    "generic_openai": "OpenAI 兼容",
}

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
    def __init__(self, parent, cfg, on_save=None, on_add_key=None,
                 on_delete_provider=None, on_update_provider=None,
                 initial_view=None):
        super().__init__(
            parent, title="设置",
            on_close=self._on_close_request,
            show_minimize=False,
            width=560, height=620,
            resizable=False,
        )
        self.transient(parent)

        self._cfg = cfg
        self._on_save = on_save
        self._on_add_key = on_add_key
        self._on_delete_provider = on_delete_provider
        self._on_update_provider = on_update_provider
        self._form = None
        self._editing_id = None
        self._sep = None
        self._body_inner = None
        self._center = None
        self._list_canvas = None
        self._wheel_bound = False

        self._holder = tk.Frame(self.body, bg=BG)
        self._holder.pack(fill="both", expand=True)

        self._init_vars()
        self._load()
        self._bind_shortcuts()

        try:
            saved_theme = (cfg.get("ui") or {}).get("theme")
            if saved_theme in ("dark", "light", "auto"):
                self._theme_var.set(saved_theme)
        except Exception:
            pass

        self._build_settings_view()

        self.update_idletasks()
        # 非模态:不 grab_set(),让用户能拖动主面板、点其他视图;
        # transient() 保证窗口始终浮在主窗口之上。
        self.focus_set()

        edit_pid = None
        if (isinstance(initial_view, (tuple, list)) and len(initial_view) == 2
                and initial_view[0] == "edit"):
            edit_pid = initial_view[1]

        if initial_view == VIEW_ADD_KEY:
            self._swap_center_form(None)
        elif edit_pid is not None and self._find_provider(edit_pid):
            self._swap_center_form(edit_pid)
        else:
            self._swap_center_list()

    # ---------- 公共 ----------

    def _init_vars(self):
        """主题 var + 3 个设置项的 StringVar,独立于视图构建,供 _load 使用。"""
        self._theme_var = tk.StringVar(value=current_choice())
        self._vars = {}
        for label, path, hint, lo, hi, vtype in ROWS:
            self._vars[path] = (tk.StringVar(), vtype, lo, hi)

    def _find_provider(self, pid):
        for p in self._cfg.get("providers") or []:
            if isinstance(p, dict) and p.get("id") == pid:
                return p
        return None

    def _on_close_request(self):
        self._wheel_leave()
        try:
            self.destroy()
        except tk.TclError:
            pass

    def refresh_palette(self):
        """主题切换时同步本地常量 + 用新配色重建中间区(列表模式)。"""
        _refresh_settings_palette()
        try:
            center = getattr(self, "_center", None)
            if center is not None and self._form is None:
                self._swap_center_list()
            self._apply_colors_to_tree()
            # 分隔线被 _apply_colors_to_tree 当普通 Frame 刷成背景色,单独补涂
            if getattr(self, "_sep", None) is not None:
                self._sep.config(bg=DIM)
        except tk.TclError:
            pass

    def _apply_colors_to_tree(self, root=None):
        """遍历当前视图子树,按 widget class 套用 PALETTE 配色。

        中间区(_center)子树跳过 —— 列表模式由 refresh_palette 整体重建,
        表单模式 AddKeyForm 自己注册了 on_theme_change,自管配色。
        """
        if root is None:
            root = self._body_inner
            if root is None:
                return
        if root is getattr(self, "_center", None):
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
            if w is getattr(self, "_center", None):
                continue
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

    # ---------- 静态框架 ----------

    def _build_settings_view(self):
        try:
            self.geometry("560x620")
        except tk.TclError:
            pass
        body = tk.Frame(self._holder, bg=BG)
        body.pack(fill="both", expand=True, padx=18, pady=14)
        self._body_inner = body

        # 主题 radio
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
        for i, (label, path, hint, lo, hi, vtype) in enumerate(ROWS):
            row_idx = i + 1
            tk.Label(body, text=label, bg=BG, fg=FG,
                     font=(FONT, 10)).grid(row=row_idx, column=0, sticky="w",
                                           pady=5, padx=(0, 8))
            v, _, _, _ = self._vars[path]
            e = tk.Entry(body, textvariable=v, width=14,
                         bg=BG_FIELD, fg=FG, insertbackground=FG,
                         font=(FONT, 10), relief="flat", justify="right")
            e.grid(row=row_idx, column=1, sticky="e", pady=5)
            tk.Label(body, text=hint, bg=BG, fg=DIM,
                     font=(FONT, 8)).grid(row=row_idx, column=2, sticky="w",
                                          pady=5, padx=(10, 0))
        body.columnconfigure(2, weight=1)

        # 分隔线
        self._sep = tk.Frame(body, height=1, bg=DIM)
        self._sep.grid(row=4, column=0, columnspan=3, sticky="ew",
                       pady=(12, 8))

        # 中间区:provider 列表 / 添加·编辑表单 二选一
        self._center = tk.Frame(body, bg=BG)
        self._center.grid(row=5, column=0, columnspan=3, sticky="nsew")
        body.rowconfigure(5, weight=1)

        # 底部按钮行
        btn_frame = tk.Frame(body, bg=BG)
        btn_frame.grid(row=6, column=0, columnspan=3, sticky="e", pady=(8, 0))
        tk.Button(btn_frame, text="取消", command=self._on_close_request,
                  bg=BTN_BG, fg=FG, relief="flat", font=(FONT, 10),
                  width=10).pack(side="right", padx=(8, 0))
        self._save_settings_btn = tk.Button(btn_frame, text="保存设置",
                                            command=self._save,
                                            bg="#3a3a4a", fg=FG, relief="flat",
                                            font=(FONT, 10), width=10)
        self._save_settings_btn.pack(side="right")

    # ---------- 中间区:列表模式 ----------

    def _swap_center_list(self):
        self._editing_id = None
        self._wheel_leave()
        self._destroy_center()
        self._form = None
        try:
            self._save_settings_btn.config(state="normal")
        except (tk.TclError, AttributeError):
            pass

        center = self._center

        head = tk.Frame(center, bg=BG)
        head.pack(fill="x", pady=(0, 4))
        tk.Label(head, text="API 管理", bg=BG, fg=FG,
                 font=(FONT, 10, "bold")).pack(side="left")
        providers = [p for p in (self._cfg.get("providers") or [])
                     if isinstance(p, dict)]
        tk.Label(head, text=f"共 {len(providers)} 个", bg=BG, fg=DIM,
                 font=(FONT, 9)).pack(side="left", padx=(8, 0))

        # 底部添加链接(先 pack,保证列表 expand 时不挤掉它)
        add_link = tk.Label(center, text="→ 添加 API Key", bg=BG, fg=FG,
                            font=(FONT, 10, "underline"), cursor="hand2")
        add_link.pack(side="bottom", anchor="e", pady=(6, 0))
        add_link.bind("<Button-1>", lambda e: self._swap_center_form(None))

        list_wrap = tk.Frame(center, bg=BG)
        list_wrap.pack(fill="both", expand=True)
        canvas = tk.Canvas(list_wrap, bg=BG, highlightthickness=0, bd=0)
        scroll = make_dark_scrollbar(list_wrap, orient="vertical",
                                     command=canvas.yview)
        inner = tk.Frame(canvas, bg=BG)
        inner.bind("<Configure>",
                   lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        canvas.bind("<Enter>", self._wheel_enter)
        canvas.bind("<Leave>", self._wheel_leave)
        self._list_canvas = canvas

        if not providers:
            tk.Label(inner, text="暂无 provider,点击下方「添加 API Key」开始",
                     bg=BG, fg=DIM, font=(FONT, 9)).pack(
                anchor="w", padx=4, pady=16)
        for p in providers:
            self._build_provider_row(inner, p)

    def _build_provider_row(self, parent, p):
        pid = p.get("id")
        name = p.get("name") or "未命名"
        kind = p.get("kind") or ""
        url = p.get("base_url") or "(未填 base_url)"

        row = tk.Frame(parent, bg=BG_FIELD)
        row.pack(fill="x", pady=2)
        top = tk.Frame(row, bg=BG_FIELD)
        top.pack(fill="x", padx=8, pady=(4, 0))
        tk.Label(top, text=name, bg=BG_FIELD, fg=FG,
                 font=(FONT, 9, "bold")).pack(side="left")
        tk.Label(top, text=KIND_LABELS.get(kind, kind) or "未知类型",
                 bg=BG_FIELD, fg=DIM, font=(FONT, 8)).pack(
            side="left", padx=(8, 0))
        tk.Button(top, text="编辑", font=(FONT, 8), bg=BTN_BG, fg=FG,
                  relief="flat", bd=0, cursor="hand2", width=4,
                  command=lambda: self._swap_center_form(pid)).pack(side="right")
        tk.Button(top, text="删除", font=(FONT, 8), bg=BTN_BG, fg=FG,
                  relief="flat", bd=0, cursor="hand2", width=4,
                  command=lambda: self._confirm_delete(pid)).pack(
            side="right", padx=(0, 6))
        tk.Label(row, text=url, bg=BG_FIELD, fg=DIM,
                 font=(FONT, 8), anchor="w").pack(
            fill="x", padx=8, pady=(0, 4))

    # ---------- 中间区:表单模式 ----------

    def _swap_center_form(self, pid):
        self._wheel_leave()
        self._destroy_center()
        self._editing_id = pid
        try:
            self._save_settings_btn.config(state="disabled")
        except (tk.TclError, AttributeError):
            pass

        center = self._center
        back = tk.Label(center, text="← 返回列表", bg=BG, fg=FG,
                        font=(FONT, 10, "underline"), cursor="hand2")
        back.pack(anchor="w", pady=(0, 6))
        back.bind("<Button-1>", lambda e: self._swap_center_list())

        from ui.add_key import AddKeyForm
        provider = self._find_provider(pid) if pid else None
        initial = None
        if provider is not None:
            initial = {
                "name": provider.get("name") or "",
                "key": plain_key(provider),
                "base_url": provider.get("base_url") or "",
            }
        self._form = AddKeyForm(
            center,
            on_save=self._handle_entry_saved,
            current_count=len(self._cfg.get("providers") or []),
            show_count=provider is None,
            initial=initial,
            show_presets=provider is None,
            taken_names=self._taken_names(pid),
        )
        self._form.pack(fill="both", expand=True)

    def _taken_names(self, editing_id):
        """除正在编辑的那条外,已被占用的 provider 名字。"""
        names = set()
        for p in self._cfg.get("providers") or []:
            if not isinstance(p, dict):
                continue
            if editing_id is not None and p.get("id") == editing_id:
                continue
            name = (p.get("name") or "").strip()
            if name:
                names.add(name)
        return names

    def _handle_entry_saved(self, entry):
        """表单保存 → 回调宿主写 cfg(新增或更新)→ 回到列表模式。"""
        if self._editing_id:
            if self._on_update_provider:
                try:
                    self._on_update_provider(self._editing_id, entry)
                except Exception:
                    pass
        else:
            if self._on_add_key:
                try:
                    self._on_add_key(entry)
                except Exception:
                    pass
        if self.winfo_exists():
            self._swap_center_list()

    # ---------- 删除 ----------

    def _confirm_delete(self, pid):
        p = self._find_provider(pid)
        if not p:
            return
        from ui.confirm_delete import ConfirmDeleteDialog
        name = p.get("name") or "未命名"
        ConfirmDeleteDialog(
            self, name=name,
            message=(f"删除 provider {name} 不可恢复。"
                     "其模型列表缓存会被清空,试调日志保留。"),
            on_confirm=lambda: self._delete_confirmed(pid),
        )

    def _delete_confirmed(self, pid):
        if self._on_delete_provider:
            try:
                self._on_delete_provider(pid)
            except Exception:
                pass
        if self.winfo_exists():
            self._swap_center_list()

    # ---------- 列表滚动 ----------

    def _on_wheel(self, event):
        try:
            self._list_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        except (tk.TclError, AttributeError):
            pass

    def _wheel_enter(self, _event=None):
        if self._wheel_bound:
            return
        try:
            self._list_canvas.bind_all("<MouseWheel>", self._on_wheel, add="+")
            self._wheel_bound = True
        except (tk.TclError, AttributeError):
            pass

    def _wheel_leave(self, _event=None):
        if not self._wheel_bound:
            return
        try:
            self.unbind_all("<MouseWheel>")
        except tk.TclError:
            pass
        self._wheel_bound = False

    def _destroy_center(self):
        for w in self._center.winfo_children():
            w.destroy()
        self._list_canvas = None

    # ---------- 设置项 ----------

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
        self._on_close_request()

    def _bind_shortcuts(self):
        self.bind("<Escape>", lambda e: self._on_close_request())

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
