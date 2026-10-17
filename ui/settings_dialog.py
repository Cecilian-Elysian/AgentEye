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
from ui.theme import (PALETTE, Layout, Typography, set_theme, current_choice,
                      to_tk_color, to_tk_color_blended)
from ui.fonts import pick_ui_family
from ui.paint import (FlatButton, FocusEntry, RadioPill, hairline,
                      bind_hover_bg, bind_wheel_tree, tag_subtree, wheel_tag)
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

FONT = pick_ui_family()


# 3 个保留设置项(label / cfg path / 提示 / lo / hi / vtype)
ROWS = [
    ("刷新间隔(秒)", "refresh_interval_sec",
     "轮询周期 15–3600",
     15, 3600, "int"),
    ("金额临界阈值(¥)", "alert.critical_amount_yuan",
     "余额 ≤ 此值显示红色 0–100000",
     0.0, 100000.0, "float"),
    ("百分比告警阈值(%)", "alert.warn_pct",
     "剩余 ≤ 此值显示橙色 1–99",
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
        self._unbind_wheel = None

        self._holder = tk.Frame(self.body, bg=to_tk_color(PALETTE.BG))
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

        self.goto(initial_view)

        # 本模块不再持有 import 期的颜色快照,配色全部现取 PALETTE;
        # 构造完仍主动刷一次,让浅色主题下首帧就是浅色。
        self.refresh_palette()

    # ---------- 公共 ----------

    def goto(self, view=None):
        """切到指定视图。宿主重复打开设置时复用同一个窗口,靠它换视图。

        view: None → 列表;"add_key" → 空白表单;("edit", pid) → 预填表单。
        目标不存在时退回列表,不抛异常。
        """
        if not self.winfo_exists():
            return
        edit_pid = None
        if (isinstance(view, (tuple, list)) and len(view) == 2
                and view[0] == "edit"):
            edit_pid = view[1]

        if view == VIEW_ADD_KEY:
            self._swap_center_form(None)
        elif edit_pid is not None and self._find_provider(edit_pid):
            self._swap_center_form(edit_pid)
        else:
            self._swap_center_list()

    def raise_(self):
        """已打开时置顶并聚焦,让用户看得到刚点的按钮生效了。"""
        if not self.winfo_exists():
            return
        try:
            self.deiconify()
            self.lift()
            self.focus_force()
        except tk.TclError:
            pass

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
        """主题切换:用新配色重建中间区(列表模式)+ 逐控件自刷新。

        旧实现靠 walk 子树读当前 fg/bg 猜语义,再靠 `#8B8B9E` 这类历史
        色值当哨兵判断"这是次要文字还是正文"。哨兵跟着主题一起失效,
        于是浅色主题下次要文字被刷成正文色、输入框停在深色快照。
        现在每个控件自己报"新配色是什么",加控件时这里不用改。
        """
        try:
            center = getattr(self, "_center", None)
            if center is not None and self._form is None:
                self._swap_center_list()
            self._apply_colors_to_tree()
        except tk.TclError:
            pass

    def _apply_colors_to_tree(self, root=None):
        """遍历当前视图子树,让每个控件自己重算配色。

        中间区(_center)子树跳过 —— 列表模式由 refresh_palette 整体重建,
        表单模式 AddKeyForm 自己注册了 on_theme_change,自管配色。
        """
        if root is None:
            # 从 _holder 起步而不是 _body_inner:_holder 是 _body_inner 的
            # 父容器,从 body_inner 起步会把它自己漏掉,浅色主题下外圈留一圈
            # import 时的深色快照。
            root = getattr(self, "_holder", None) or self._body_inner
            if root is None:
                return
        if root is getattr(self, "_center", None):
            return
        bg = to_tk_color(PALETTE.BG)
        refresh = getattr(root, "refresh_palette", None)
        if callable(refresh):
            try:
                refresh()
            except tk.TclError:
                pass
        else:
            try:
                if root.winfo_class() in ("Frame", "Toplevel", "Label"):
                    root.configure(bg=bg)
            except tk.TclError:
                pass
        for w in root.winfo_children():
            if w is getattr(self, "_center", None):
                continue
            self._apply_colors_to_tree(w)

    # ---------- 静态框架 ----------

    def _build_settings_view(self):
        try:
            self.geometry("560x620")
        except tk.TclError:
            pass
        bg = to_tk_color(PALETTE.BG)
        fg = to_tk_color(PALETTE.TEXT)
        dim = to_tk_color_blended(PALETTE.TEXT_DIM)
        body = tk.Frame(self._holder, bg=bg)
        body.pack(fill="both", expand=True, padx=18, pady=14)
        self._body_inner = body

        # 主题 radio
        theme_frame = tk.Frame(body, bg=bg)
        theme_frame.grid(row=0, column=0, columnspan=3, sticky="we",
                         pady=(0, Layout.PAD))
        tk.Label(theme_frame, text="主题", bg=bg, fg=fg,
                 font=(FONT, Typography.BODY_SIZE)).grid(row=0, column=0,
                                                         sticky="w",
                                                         padx=(0, 8))
        self._theme_pills = []
        for i, choice in enumerate(("dark", "light", "auto")):
            label = {"dark": "深色", "light": "浅色", "auto": "跟随系统"}[choice]
            rb = RadioPill(
                theme_frame, variable=self._theme_var, value=choice,
                text=label, font=(FONT, Typography.BODY_SIZE),
                command=self._on_theme_radio_click,
            )
            rb.grid(row=0, column=i + 1, padx=(0, 12), sticky="w")
            self._theme_pills.append(rb)
        theme_frame.columnconfigure(4, weight=1)

        # 3 个核心设置
        self._entries = []
        for i, (label, path, hint, lo, hi, vtype) in enumerate(ROWS):
            row_idx = i + 1
            tk.Label(body, text=label, bg=bg, fg=fg,
                     font=(FONT, Typography.BODY_SIZE)).grid(
                row=row_idx, column=0, sticky="w", pady=5, padx=(0, 8))
            v, _, _, _ = self._vars[path]
            e = FocusEntry(body, textvariable=v, width=14,
                           font=(FONT, Typography.BODY_SIZE), justify="right")
            e.grid(row=row_idx, column=1, sticky="e", pady=5)
            self._entries.append(e)
            tk.Label(body, text=hint, bg=bg, fg=dim,
                     font=(FONT, Typography.DETAIL_SIZE)).grid(
                row=row_idx, column=2, sticky="w", pady=5, padx=(10, 0))
        body.columnconfigure(2, weight=1)

        # 分隔线
        self._sep = hairline(body)
        self._sep.grid(row=4, column=0, columnspan=3, sticky="ew",
                       pady=(12, 8))

        # 中间区:provider 列表 / 添加·编辑表单 二选一
        self._center = tk.Frame(body, bg=bg)
        self._center.grid(row=5, column=0, columnspan=3, sticky="nsew")
        body.rowconfigure(5, weight=1)

        # 底部按钮行
        btn_frame = tk.Frame(body, bg=bg)
        btn_frame.grid(row=6, column=0, columnspan=3, sticky="e", pady=(8, 0))
        # 主操作在最右:pack 按创建顺序分配,先建 取消(side=right)会把它
        # 排在右边,再建 保存设置 落在它左边 —— 与"确认在右"的惯例相反。
        self._save_settings_btn = FlatButton(
            btn_frame, text="保存设置", variant="solid", width=10,
            on_click=self._save, font=(FONT, Typography.BODY_SIZE))
        self._save_settings_btn.pack(side="right")
        FlatButton(btn_frame, text="取消", variant="ghost", width=10,
                   on_click=self._on_close_request,
                   font=(FONT, Typography.BODY_SIZE)).pack(side="right",
                                                           padx=(0, 8))

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

        bg = to_tk_color(PALETTE.BG)
        fg = to_tk_color(PALETTE.TEXT)
        dim = to_tk_color_blended(PALETTE.TEXT_DIM)
        center = self._center

        head = tk.Frame(center, bg=bg)
        head.pack(fill="x", pady=(0, Layout.ROW_GAP))
        tk.Label(head, text="API 管理", bg=bg, fg=fg,
                 font=(FONT, Typography.BODY_SIZE,
                       Typography.TITLE_WEIGHT)).pack(side="left")
        providers = [p for p in (self._cfg.get("providers") or [])
                     if isinstance(p, dict)]
        tk.Label(head, text=f"共 {len(providers)} 个", bg=bg, fg=dim,
                 font=(FONT, Typography.DETAIL_SIZE)).pack(side="left",
                                                            padx=(8, 0))

        # 底部添加链接(先 pack,保证列表 expand 时不挤掉它)
        add_link = tk.Label(center, text="→ 添加 API Key", bg=bg, fg=fg,
                            font=(FONT, Typography.BODY_SIZE, "underline"),
                            cursor="hand2")
        add_link.pack(side="bottom", anchor="e", pady=(6, 0))
        add_link.bind("<Button-1>", lambda e: self._swap_center_form(None))
        # 可点的文字却零 hover 反馈:光标是手型,划过去没有变化,
        # 用户不知道这是个链接而不是一行说明。
        bind_hover_bg([add_link], lambda: to_tk_color(PALETTE.CARD_HOVER),
                      lambda: bg)

        list_wrap = tk.Frame(center, bg=bg)
        list_wrap.pack(fill="both", expand=True)
        canvas = tk.Canvas(list_wrap, bg=bg, highlightthickness=0, bd=0)
        scroll = make_dark_scrollbar(list_wrap, orient="vertical",
                                     command=canvas.yview)
        inner = tk.Frame(canvas, bg=bg)
        inner.bind("<Configure>",
                   lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        # 画布里的窗口项默认取 inner 的自然宽度;不撑满画布的话,空态文案
        # 会缩在左侧一小块里"居中"。
        self._list_win = canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.bind(
            "<Configure>",
            lambda e: canvas.itemconfigure(self._list_win, width=e.width))
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self._unbind_wheel = bind_wheel_tree(inner, self._on_wheel)
        self._list_canvas = canvas

        if not providers:
            box = tk.Frame(inner, bg=bg)
            box.pack(fill="x", pady=Layout.PAD * 2)
            tk.Label(box, text="还没有添加任何 API Key", bg=bg, fg=fg,
                     font=(FONT, Typography.BODY_SIZE)).pack(
                pady=(0, 4), anchor="center")
            tk.Label(box, text="添加后即可在这里管理名称、地址与密钥",
                     bg=bg, fg=dim,
                     font=(FONT, Typography.DETAIL_SIZE)).pack(anchor="center")
        for p in providers:
            self._build_provider_row(inner, p)
        # provider 行是刚建出来的,重新打一遍滚轮 tag
        tag_subtree(inner, wheel_tag(inner))

    def _build_provider_row(self, parent, p):

        """provider 行:静止不铺色块,hover 才浮出一层填充。

        原来每行都铺 BG_FIELD(进度轨道色),4 条 provider 排下来是一片
        灰砖,而"这是哪一行"的信息靠底色深浅给,并不比 hover 更清楚。
        """
        pid = p.get("id")
        name = p.get("name") or "未命名"
        kind = p.get("kind") or ""
        url = p.get("base_url") or "(未填 base_url)"

        bg = to_tk_color(PALETTE.BG)
        fg = to_tk_color(PALETTE.TEXT)
        dim = to_tk_color_blended(PALETTE.TEXT_DIM)

        row = tk.Frame(parent, bg=bg)
        row.pack(fill="x")
        top = tk.Frame(row, bg=bg)
        top.pack(fill="x", padx=8, pady=(Layout.ROW_PAD_Y, 0))
        tk.Label(top, text=name, bg=bg, fg=fg,
                 font=(FONT, Typography.BODY_SIZE,
                       Typography.TITLE_WEIGHT)).pack(side="left")
        tk.Label(top, text=KIND_LABELS.get(kind, kind) or "未知类型",
                 bg=bg, fg=dim,
                 font=(FONT, Typography.DETAIL_SIZE)).pack(side="left",
                                                           padx=(8, 0))
        FlatButton(top, text="编辑", variant="ghost", width=4, padx=6, pady=2,
                   font=(FONT, Typography.DETAIL_SIZE),
                   on_click=lambda: self._swap_center_form(pid)).pack(side="right")
        FlatButton(top, text="删除", variant="ghost", width=4, padx=6, pady=2,
                   font=(FONT, Typography.DETAIL_SIZE),
                   on_click=lambda: self._confirm_delete(pid)).pack(
            side="right", padx=(0, 6))
        url_lbl = tk.Label(row, text=url, bg=bg, fg=dim,
                           font=(FONT, Typography.DETAIL_SIZE), anchor="w")
        url_lbl.pack(fill="x", padx=8, pady=(0, Layout.ROW_PAD_Y))

        chain = [row, top, url_lbl]
        bind_hover_bg(chain, lambda: to_tk_color(PALETTE.CARD_HOVER), lambda: bg)
        hairline(row).pack(side="bottom", fill="x")

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
        back = tk.Label(center, text="← 返回列表", bg=to_tk_color(PALETTE.BG),
                        fg=to_tk_color(PALETTE.TEXT),
                        font=(FONT, Typography.BODY_SIZE, "underline"),
                        cursor="hand2")
        back.pack(anchor="w", pady=(0, 6))
        back.bind("<Button-1>", lambda e: self._swap_center_list())
        bind_hover_bg([back], lambda: to_tk_color(PALETTE.CARD_HOVER),
                      lambda: to_tk_color(PALETTE.BG))

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
        """表单保存 → 回调宿主写 cfg(新增或更新)→ 回到列表模式。

        宿主写盘失败(ConfigError 族)时弹错并留在表单:原先异常被
        吞掉还照样切回列表,用户以为存上了,实际配置文件根本没写。
        """
        try:
            if self._editing_id:
                if self._on_update_provider:
                    self._on_update_provider(self._editing_id, entry)
            else:
                if self._on_add_key:
                    self._on_add_key(entry)
        except Exception as e:
            if self.winfo_exists():
                messagebox.showerror(
                    "保存失败", str(e) or e.__class__.__name__, parent=self)
            return
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
        """已废弃:滚轮改由 bind_wheel_tree 常驻挂在 inner 子树上。

        旧的 <Enter>/<Leave> + bind_all 组合会在移出列表时用
        unbind_all(sequence, funcid) 摘绑定,而 tkinter 的 unbind_all 只
        接受一个参数 → TypeError;而且没摘干净的全局绑定会把主面板的
        滚轮抢走(这正是原注释里担心的那个 bug)。
        """
        return None

    def _wheel_leave(self, _event=None):
        unbind = getattr(self, "_unbind_wheel", None)
        if unbind is None:
            return
        try:
            unbind()
        except tk.TclError:
            pass
        self._unbind_wheel = None

    def _destroy_center(self):
        for w in self._center.winfo_children():
            w.destroy()
        self._list_canvas = None

    # ---------- 设置项 ----------

    def _on_theme_radio_click(self):
        """Radio 点击立即应用并落盘主题。

        persist=False 不落盘的话,用户切完主题直接关窗口,重启就回退;
        而走 _save() 又会把表单里没保存的其他改动一起写进去。
        所以这里只把 theme 字段写进 cfg 并走一次保存回调。
        """
        choice = self._theme_var.get()
        set_theme(choice, broadcast=True, persist=False)
        (self._cfg.setdefault("ui", {}))["theme"] = choice
        if self._on_save:
            try:
                self._on_save(self._cfg)
            except Exception:
                pass

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
