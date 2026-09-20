"""v2 主面板。

- provider 行 (每行带 hover / 复制 / 右键菜单)
- 底部:状态栏 (下次刷新倒计时)
- 交互:拖拽带边缘磁吸,光标反馈,快捷键 (F5/Esc/Ctrl+Q)
- 颜色:基于消耗比的绿→黄→红渐变,主值与 detail 中所有金额/百分比同步上色
"""

import re
import time
import tkinter as tk

FONT = "Microsoft YaHei UI"

C = {
    "bg": "#15151d",
    "card": "#1d1d2b",
    "card_hover": "#232335",
    "bar_bg": "#2a2a3a",
    "text": "#e8e8f0",
    "dim": "#8b8b9e",
    "ok": "#53d77a",
    "warn": "#f0c24b",
    "critical": "#ff5d5d",
    "error": "#ff8f6b",
    "off": "#5b5b68",
}

LEVEL_COLOR = {k: C[k] for k in ("ok", "warn", "critical", "error")}
LEVEL_COLOR["unconfigured"] = C["off"]
LEVEL_COLOR["unknown"] = C["dim"]

EDGE_SNAP = 20
FIRST_RUN_FLAG = "~/.agenteye/.first_run_done"


def _fmt_main(result):
    if result.get("unconfigured"):
        return "未配置"
    if result.get("error"):
        return "查询失败"
    unit = result.get("unit") or ""
    prefix = "≈" if result.get("is_estimate") else ""
    if unit in ("$", "¥"):
        rem = result.get("remaining")
        if rem is None:
            return "-"
        text = f"{prefix}{unit}{rem:,.2f}"
        if result.get("total"):
            text += f" / {unit}{result['total']:,.2f}"
        return text
    if unit == "%":
        pct = result.get("pct")
        return f"{pct:.0f}%" if pct is not None else "-"
    rem = result.get("remaining")
    return f"{prefix}{rem:,.2f}{unit}" if rem is not None else "-"


def _fmt_countdown(sec):
    sec = max(0, int(sec))
    h, rem = sec // 3600, sec % 3600
    m, s = rem // 60, rem % 60
    return f"{h}h{m:02d}m{s:02d}s" if h else f"{m:02d}:{s:02d}"


def _time_ago(ts):
    if not ts:
        return "从未"
    delta = int(time.time() - ts)
    if delta < 60:
        return f"{delta} 秒前"
    if delta < 3600:
        return f"{delta // 60} 分钟前"
    if delta < 86400:
        return f"{delta // 3600} 小时前"
    return f"{delta // 86400} 天前"


def _usage_ratio(result):
    """返回 0..1 之间的"消耗占比"。0=全新,1=耗尽。"""
    if result.get("unconfigured") or result.get("error"):
        return None
    unit = result.get("unit") or ""
    used = result.get("used")
    total = result.get("total")
    pct = result.get("pct")

    if unit in ("$", "¥", "额度") and isinstance(total, (int, float)) and total > 0:
        u = used if isinstance(used, (int, float)) else 0
        return max(0.0, min(1.0, u / total))
    if unit == "%" and isinstance(pct, (int, float)):
        return max(0.0, min(1.0, (100 - pct) / 100))

    level = result.get("level", "ok")
    return {"ok": 0.15, "warn": 0.55, "critical": 0.85}.get(level, 0.15)


def _usage_color(ratio):
    """绿(0) → 黄(0.5) → 红(1) 三色插值。"""
    if ratio is None:
        return C["dim"]
    ratio = max(0.0, min(1.0, ratio))
    if ratio <= 0.5:
        t = ratio / 0.5
        r = int(0x53 + (0xf0 - 0x53) * t)
        g = int(0xd7 + (0xc2 - 0xd7) * t)
        b = int(0x7a + (0x4b - 0x7a) * t)
    else:
        t = (ratio - 0.5) / 0.5
        r = int(0xf0 + (0xff - 0xf0) * t)
        g = int(0xc2 + (0x5d - 0xc2) * t)
        b = int(0x4b + (0x5d - 0x4b) * t)
    return f"#{r:02x}{g:02x}{b:02x}"


_DETAIL_NUMBER_RE = re.compile(r"([\$¥][\d.,]+|\d+%)")


def _set_detail_with_tags(text_widget, text, fg):
    """清空 detail Text 并插入 text,$X/¥X/X% 数字段用 highlight tag,其余用 dim。

    highlight tag 的前景色会被实时重新配置为 fg。
    """
    text_widget.tag_config("highlight", foreground=fg)
    text_widget.config(state="normal")
    text_widget.delete("1.0", "end")
    pos = 0
    for m in _DETAIL_NUMBER_RE.finditer(text):
        if m.start() > pos:
            text_widget.insert("end", text[pos:m.start()], "dim")
        text_widget.insert("end", m.group(0), "highlight")
        pos = m.end()
    if pos < len(text):
        text_widget.insert("end", text[pos:], "dim")
    text_widget.config(state="disabled")


class Panel:
    def __init__(self, root, state, cfg, actions):
        self.root = root
        self.state = state
        self.cfg = cfg
        self.actions = actions

        self._sig = None
        self._rows = {}
        self._last_paint = {}
        self._last_results = []

        root.title("AgentEye")
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.configure(bg=C["bg"])
        self._place_initial()

        self._build_header()
        self.rows_frame = tk.Frame(root, bg=C["bg"])
        self.rows_frame.pack(fill="x", padx=10)
        self.footer = tk.Label(
            root, text="", font=(FONT, 8), fg=C["dim"], bg=C["bg"], anchor="w")
        self.footer.pack(fill="x", padx=10, pady=(2, 8))

        for w in (root,):
            w.bind("<Button-1>", self._drag_start)
            w.bind("<B1-Motion>", self._drag_move)
            w.bind("<ButtonRelease-1>", self._drag_end)
            w.bind("<FocusIn>", lambda e: actions["refresh_now"]())

        self.menu = self._build_menu()
        root.bind("<Button-3>", self._popup_main_menu)
        root.bind("<F5>", lambda e: actions["refresh_now"]())
        root.bind("<Control-q>", lambda e: actions["quit"]())
        root.bind("<Escape>", lambda e: self._close_any_popup())

        self._tick()
        self._maybe_welcome()

    def _place_initial(self):
        ui = self.cfg.get("ui") or {}
        x, y = ui.get("x"), ui.get("y")
        if x is None or y is None:
            sw = self.root.winfo_screenwidth()
            x, y = sw - 320 - 20, 60
        self.root.geometry(f"+{int(x)}+{int(y)}")

    def _build_header(self):
        header = tk.Frame(self.root, bg=C["bg"])
        header.pack(fill="x", padx=10, pady=(8, 2))
        tk.Label(header, text="AgentEye", font=(FONT, 10, "bold"),
                 fg=C["text"], bg=C["bg"]).pack(side="left")
        self.dot = tk.Label(header, text="●", font=(FONT, 9),
                            fg=C["dim"], bg=C["bg"])
        self.dot.pack(side="right", padx=(0, 8))
        close = tk.Label(header, text="×", font=(FONT, 12),
                         fg=C["dim"], bg=C["bg"], cursor="hand2")
        close.pack(side="right")
        close.bind("<Button-1>", lambda e: self.actions["quit"]())
        close.bind("<Enter>", lambda e: close.config(fg=C["critical"]))
        close.bind("<Leave>", lambda e: close.config(fg=C["dim"]))

        add_btn = tk.Label(header, text="+", font=(FONT, 12, "bold"),
                           fg=C["dim"], bg=C["bg"], cursor="hand2")
        add_btn.pack(side="right", padx=(0, 4))
        add_btn.bind("<Button-1>", lambda e: self.actions.get("add_key", lambda: None)())
        add_btn.bind("<Enter>", lambda e: add_btn.config(fg=C["ok"]))
        add_btn.bind("<Leave>", lambda e: add_btn.config(fg=C["dim"]))

    def _build_menu(self):
        m = tk.Menu(self.root, tearoff=0)
        m.add_command(label="立即刷新", command=self.actions["refresh_now"])
        m.add_command(label="通知测试", command=self.actions["test_notify"])
        m.add_command(label="添加 Key…",
                      command=self.actions.get("add_key", lambda: None))
        self._pause_idx = m.index("end")
        m.add_command(label="暂停轮询", command=self.actions["toggle_pause"])
        m.add_command(label="打开配置文件", command=self.actions["open_config"])
        m.add_separator()
        m.add_command(label="退出", command=self.actions["quit"])
        return m

    def _popup_main_menu(self, event):
        if event.widget is self.root:
            paused = self.state.paused
            self.menu.entryconfig(
                self._pause_idx + 1,
                label="恢复轮询" if paused else "暂停轮询")
            try:
                self.menu.tk_popup(event.x_root, event.y_root)
            finally:
                self.menu.grab_release()

    def _drag_start(self, event):
        self._ox = event.x_root - self.root.winfo_x()
        self._oy = event.y_root - self.root.winfo_y()
        self.root.config(cursor="fleur")

    def _drag_move(self, event):
        x = event.x_root - self._ox
        y = event.y_root - self._oy
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        if x < EDGE_SNAP:
            x = 0
        elif sw - x < EDGE_SNAP:
            x = sw - self.root.winfo_width()
        if y < EDGE_SNAP:
            y = 0
        elif sh - y < EDGE_SNAP:
            y = sh - self.root.winfo_height()
        self.root.geometry(f"+{x}+{y}")

    def _drag_end(self, event):
        self.root.config(cursor="")
        self.actions["save_position"](
            self.root.winfo_x(), self.root.winfo_y())

    def _close_any_popup(self):
        for w in self.root.winfo_children():
            if isinstance(w, tk.Toplevel):
                w.destroy()
                return

    def _maybe_welcome(self):
        import os
        flag = os.path.expanduser(FIRST_RUN_FLAG)
        if os.path.exists(flag):
            return
        try:
            os.makedirs(os.path.dirname(flag), exist_ok=True)
            open(flag, "w").close()
        except OSError:
            return
        try:
            import notify
            notify.alert("AgentEye", "右键 + 添加你的第一个 Key,或打开配置文件")
        except Exception:
            pass

    def _tick(self):
        try:
            if self.root.winfo_exists():
                self._update()
                self.root.after(1000, self._tick)
        except tk.TclError:
            pass

    def _update(self):
        results = list(self.state.results or [])
        sig = tuple((r.get("name"), r.get("type")) for r in results)
        if sig != self._sig:
            self._rebuild(results)
            self._sig = sig
        for r in results:
            widgets = self._rows.get(r.get("name"))
            if widgets:
                self._paint_row(widgets, r)

        levels = [r.get("level") for r in results]
        if self.state.paused:
            self.dot.config(fg=C["off"])
        elif "critical" in levels:
            self.dot.config(fg=C["critical"])
        elif "error" in levels:
            self.dot.config(fg=C["error"])
        elif "warn" in levels:
            self.dot.config(fg=C["warn"])
        else:
            self.dot.config(fg=C["ok"])

        if self.state.paused:
            text = "已暂停轮询"
        elif self.state.fetching:
            text = "刷新中…"
        elif self.state.next_fetch:
            text = f"下次刷新 {_fmt_countdown(self.state.next_fetch - time.time())}"
        else:
            text = "等待首次刷新…"
        self.footer.config(text=text)

    def _rebuild(self, results):
        for child in self.rows_frame.winfo_children():
            child.destroy()
        self._rows = {}
        if not results:
            box = self._row_skeleton("未配置任何 provider", "右键 + 添加 Key")
            box["value"].config(text="-", fg=C["off"])
            return
        for r in results:
            self._rows[r["name"]] = self._row_skeleton(r["name"], "")

    def _row_skeleton(self, name, detail):
        card = tk.Frame(self.rows_frame, bg=C["card"], cursor="hand2")
        card.pack(fill="x", pady=3)
        top = tk.Frame(card, bg=C["card"])
        top.pack(fill="x", padx=8, pady=(6, 0))
        name_lbl = tk.Label(top, text=name, font=(FONT, 9, "bold"),
                            fg=C["text"], bg=C["card"])
        name_lbl.pack(side="left")
        value_lbl = tk.Label(top, text="…", font=(FONT, 9),
                             fg=C["dim"], bg=C["card"], cursor="hand2")
        value_lbl.pack(side="right")
        det_lbl = tk.Text(card, font=(FONT, 9), fg=C["dim"], bg=C["card"],
                          wrap="word", height=1, bd=0, highlightthickness=0,
                          padx=0, pady=2, cursor="arrow", takefocus=0)
        det_lbl.pack(fill="x", padx=8)
        det_lbl.tag_config("dim", foreground=C["dim"])
        det_lbl.tag_config("highlight", foreground=C["dim"])
        det_lbl.tag_raise("sel", "dim")
        det_lbl.insert("end", detail or "")
        det_lbl.config(state="disabled")
        bar = tk.Canvas(card, height=5, bg=C["bar_bg"], highlightthickness=0)
        bar.pack(fill="x", padx=8, pady=(4, 7))
        rect = bar.create_rectangle(0, 0, 0, 5, outline="")

        widgets = {"frame": card, "name": name_lbl, "value": value_lbl,
                   "detail": det_lbl, "bar": bar, "rect": rect,
                   "provider_name": name}

        for w in (card, top, name_lbl):
            w.bind("<Enter>", lambda e, ww=card: ww.config(bg=C["card_hover"]))
            w.bind("<Leave>", lambda e, ww=card: ww.config(bg=C["card"]))
        value_lbl.bind("<Button-1>", lambda e, n=name: self._copy_value(n))
        value_lbl.bind("<Enter>", lambda e: value_lbl.config(fg=C["ok"]))
        value_lbl.bind("<Leave>", lambda e: value_lbl.config(fg=C["dim"]))

        card.bind("<Button-3>", lambda e, n=name: self._popup_row_menu(e, n))
        name_lbl.bind("<Button-3>", lambda e, n=name: self._popup_row_menu(e, n))

        return widgets

    def _copy_value(self, name):
        for r in self.state.results or []:
            if r.get("name") == name:
                rem = r.get("remaining")
                if rem is not None:
                    self.root.clipboard_clear()
                    self.root.clipboard_append(str(rem))
                return

    def _popup_row_menu(self, event, name):
        self._popup_target_name = name
        from ui.row_menu import RowMenu
        if not hasattr(self, "_row_menu_inst"):
            self._row_menu_inst = RowMenu(
                self.root,
                on_refresh=lambda: (self._popup_target_name,
                                    self.actions["refresh_now"]()),
                on_pause=lambda: self.actions.get("pause_provider", lambda n: None)(
                    self._popup_target_name),
                on_edit=lambda: self.actions.get("edit_provider", lambda n: None)(
                    self._popup_target_name),
                on_delete=lambda: self.actions.get("delete_provider", lambda n: None)(
                    self._popup_target_name),
                on_copy_key=lambda: self._copy_key(self._popup_target_name),
                on_copy_url=lambda: self._copy_url(self._popup_target_name),
                on_show_models=lambda: self._show_models(self._popup_target_name),
                on_probe=lambda: self.actions.get("probe_models", lambda n: None)(
                    self._popup_target_name),
            )
        try:
            self._row_menu_inst.menu.tk_popup(event.x_root, event.y_root)
        finally:
            self._row_menu_inst.menu.grab_release()

    def _copy_key(self, name):
        for p in self.cfg.get("providers") or []:
            if p.get("name") == name:
                key = p.get("key") or ""
                if key:
                    self.root.clipboard_clear()
                    self.root.clipboard_append(key)
                return

    def _copy_url(self, name):
        for p in self.cfg.get("providers") or []:
            if p.get("name") == name:
                url = p.get("base_url") or ""
                if url:
                    self.root.clipboard_clear()
                    self.root.clipboard_append(url)
                return

    def _show_models(self, name):
        provider_cfg = None
        for p in self.cfg.get("providers") or []:
            if p.get("name") == name:
                provider_cfg = p
                break
        if not provider_cfg:
            return
        base_url = provider_cfg.get("base_url") or ""
        key = provider_cfg.get("key") or ""
        models = None
        for r in (self.state.results or []):
            if r.get("name") == name:
                models = r.get("models")
                break
        if not models:
            try:
                import notify
                notify.alert("AgentEye", f"{name}: 无模型数据,可能未启用 /v1/models")
            except Exception:
                pass
            return
        from ui.model_panel import ModelPanel

        def _probe_cb(model_id):
            fn = self.actions.get("probe_model")
            if not fn:
                return False, 0.0, "未配置 probe_model"
            return fn(model_id, base_url, key)

        ModelPanel(self.root, name, models, on_probe=_probe_cb)

    def _paint_row(self, widgets, r):
        ratio_val = _usage_ratio(r)
        color = _usage_color(ratio_val)
        key = (r.get("name"), r.get("level"), r.get("remaining"),
               r.get("total"), r.get("pct"), r.get("detail"), r.get("error"),
               r.get("updated_at"), ratio_val)
        if self._last_paint.get(widgets["provider_name"]) == key:
            return
        self._last_paint[widgets["provider_name"]] = key

        level = r.get("level", "unknown")
        if ratio_val is None or r.get("unconfigured"):
            color = C["off"]
        elif level in ("error",):
            color = C["error"]
        elif level == "unknown":
            color = C["dim"]
        widgets["value"].config(text=_fmt_main(r), fg=color)

        detail = r.get("detail") or ""
        if r.get("error"):
            detail = r["error"]
        if level == "error":
            ago = _time_ago(r.get("updated_at"))
            if "上次失败" not in detail and ago != "从未":
                detail = f"{detail} · 上次失败 {ago}" if detail else f"上次失败 {ago}"
        if not detail:
            detail = f"更新于 {time.strftime('%H:%M:%S', time.localtime(r.get('updated_at', 0)))}"
        _set_detail_with_tags(widgets["detail"], detail, color)

        pct = r.get("pct")
        frac = None
        if pct is not None:
            frac = max(0.0, min(1.0, float(pct) / 100.0))
        bar = widgets["bar"]
        rect = widgets["rect"]
        width = bar.winfo_width() or 300
        bar.coords(rect, 0, 0, width * (frac if frac is not None else 1.0), 5)
        bar.itemconfig(rect, fill=color)
