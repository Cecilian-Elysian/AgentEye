"""v2 主面板。

- provider 行 (每行带 hover / 复制 / 右键菜单)
- 底部:状态栏 (下次刷新倒计时)
- 交互:拖拽带边缘磁吸,光标反馈,快捷键 (F5/Esc/Ctrl+Q)
- 颜色:基于消耗比的绿→黄→红渐变,主值与 detail 中所有金额/百分比同步上色
- 主题:读 ui.theme.PALETTE,主题切换时通过 _refresh_palette() 重画所有 row / header / footer / grip
"""

import re
import time
import tkinter as tk

import config as config_mod
from ui.theme import PALETTE, set_theme, on_theme_change, to_tk_color, to_tk_color_blended
from ui.scrollbar_style import make_dark_scrollbar

FONT = "Microsoft YaHei UI"

C = {
    "bg": to_tk_color(PALETTE.BG),
    "card": to_tk_color(PALETTE.CARD),
    "card_hover": to_tk_color(PALETTE.CARD_HOVER),
    "bar_bg": to_tk_color(PALETTE.BAR_BG),
    "text": to_tk_color(PALETTE.TEXT),
    "dim": to_tk_color_blended(PALETTE.TEXT_DIM),
    "ok": to_tk_color(PALETTE.OK),
    "warn": to_tk_color(PALETTE.WARN),
    "critical": to_tk_color(PALETTE.CRITICAL),
    "error": to_tk_color(PALETTE.ERROR),
    "off": to_tk_color(PALETTE.OFF),
    "card_amount": to_tk_color(PALETTE.CARD_AMOUNT),
}

LEVEL_COLOR = {k: C[k] for k in ("ok", "warn", "critical", "error")}
LEVEL_COLOR["unconfigured"] = C["off"]
LEVEL_COLOR["unknown"] = C["dim"]

EDGE_SNAP = 20
FIRST_RUN_FLAG = "~/.agenteye/.first_run_done"
MIN_W, MIN_H = 280, 180
MAX_W, MAX_H = 800, 900
RESIZE_GRIP = 16
BTN_BG = "#2a2a3a"
BTN_HOVER = "#34344a"


def _refresh_BTN():
    """主题切换时同步本模块的按钮颜色常量。"""
    global BTN_BG, BTN_HOVER
    BTN_BG = to_tk_color(PALETTE.CARD_HOVER)
    BTN_HOVER = to_tk_color(PALETTE.CARD_PRESSED)


def _refresh_C():
    """主题切换时同步刷新本模块的 C / LEVEL_COLOR 字典。"""
    C["bg"] = to_tk_color(PALETTE.BG)
    C["card"] = to_tk_color(PALETTE.CARD)
    C["card_hover"] = to_tk_color(PALETTE.CARD_HOVER)
    C["bar_bg"] = to_tk_color(PALETTE.BAR_BG)
    C["text"] = to_tk_color(PALETTE.TEXT)
    C["dim"] = to_tk_color_blended(PALETTE.TEXT_DIM)
    C["ok"] = to_tk_color(PALETTE.OK)
    C["warn"] = to_tk_color(PALETTE.WARN)
    C["critical"] = to_tk_color(PALETTE.CRITICAL)
    C["error"] = to_tk_color(PALETTE.ERROR)
    C["off"] = to_tk_color(PALETTE.OFF)
    C["card_amount"] = to_tk_color(PALETTE.CARD_AMOUNT)
    LEVEL_COLOR["ok"] = C["ok"]
    LEVEL_COLOR["warn"] = C["warn"]
    LEVEL_COLOR["critical"] = C["critical"]
    LEVEL_COLOR["error"] = C["error"]
    LEVEL_COLOR["unconfigured"] = C["off"]
    LEVEL_COLOR["unknown"] = C["dim"]


def _sync_to_tk():
    """Tk 不接受 8 位 hex。widget 上的 bg/fg 已经在创建时用 to_tk_color,这里只是返回当前版本。"""
    return {
        "bg": to_tk_color(PALETTE.BG),
        "card": to_tk_color(PALETTE.CARD),
        "card_hover": to_tk_color(PALETTE.CARD_HOVER),
        "bar_bg": to_tk_color(PALETTE.BAR_BG),
        "text": to_tk_color(PALETTE.TEXT),
        "dim": to_tk_color(PALETTE.TEXT_DIM),
        "ok": to_tk_color(PALETTE.OK),
        "warn": to_tk_color(PALETTE.WARN),
        "critical": to_tk_color(PALETTE.CRITICAL),
        "error": to_tk_color(PALETTE.ERROR),
        "off": to_tk_color(PALETTE.OFF),
        "card_amount": to_tk_color(PALETTE.CARD_AMOUNT),
    }


def _fmt_main(result):
    if result.get("unconfigured"):
        return "未配置"
    if result.get("error"):
        return "查询失败"
    unit = result.get("unit") or ""
    prefix = "≈" if result.get("is_estimate") else ""
    if unit in ("$", "¥"):
        total = result.get("total")
        used_today = result.get("used_today")
        if isinstance(used_today, (int, float)):
            today_str = f"{prefix}{unit}{used_today:,.2f}"
            if total:
                return f"今日 {today_str} / {unit}{total:,.2f}"
            return f"今日 {today_str}"
        rem = result.get("remaining")
        if rem is None:
            return "-"
        if total:
            return f"{prefix}{unit}{rem:,.2f} / {unit}{total:,.2f}"
        return f"{prefix}{unit}{rem:,.2f}"
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
    """返回 0..1 之间的"消耗占比"。0=全新,1=耗尽。

    金额行优先用 used_today/total(贴近"今日消耗"语义),
    否则用 used/total,否则按 level 降级映射。
    """
    if result.get("unconfigured") or result.get("error"):
        return None
    unit = result.get("unit") or ""
    used = result.get("used")
    used_today = result.get("used_today")
    total = result.get("total")
    pct = result.get("pct")

    if unit in ("$", "¥", "额度") and isinstance(total, (int, float)) and total > 0:
        if isinstance(used_today, (int, float)):
            return max(0.0, min(1.0, used_today / total))
        if isinstance(used, (int, float)):
            return max(0.0, min(1.0, used / total))
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


def _on_bar_configure(event, bar, rect, widgets):
    """Tk 布局驱动:bar 实际 width 就绪 / 尺寸变化时重画 rect。

    替代原 ``bar.winfo_width() or 300`` 兜底:
    - 首帧布局完成 → ``<Configure>`` 触发,``event.width`` 正确 → 修"刚打开进度条看不见"
    - 窗口 resize → bar 跟随 pack(fill="x") 重排 → ``<Configure>`` 触发 → 修"resize 后 bar 不跟随"

    颜色/比例由 ``_paint_row`` 写入 ``widgets["_bar_color"]`` / ``widgets["_bar_frac"]``。
    两个键均未初始化时(placeholder 行)直接跳过,保持空 rect。
    """
    color = widgets.get("_bar_color")
    frac = widgets.get("_bar_frac")
    if color is None and frac is None:
        return
    width = getattr(event, "width", 0) or 0
    if width < 2:
        return
    if color is None:
        color = C["dim"]
    if frac is None:
        frac = 1.0
    try:
        bar.coords(rect, 0, 0, int(width * frac), 5)
        bar.itemconfig(rect, fill=color)
    except tk.TclError:
        pass


def _is_amount_mode(result):
    """判断一行是否"金额行"(显示 $¥ 而非 %)。

    判定:unit 是 $ / ¥ / 额度 / 元 / ￥ 任一 → 金额行。
    否则(包括 %、tokens、次、空)→ 额度行。
    """
    unit = (result.get("unit") or "").strip()
    return unit in ("$", "¥", "￥", "额度", "元")


def _row_bg(result):
    """金额行返回金色微调底色,额度行不变。"""
    return C["card_amount"] if _is_amount_mode(result) else C["card"]


def _compute_target_static(rows, y_root):
    """纯函数:计算 y_root 应该落在哪个 row 索引。

    rows 是 winfo_rooty/winfo_height 可调用的对象序列。
    返回 0..len(rows) 之间的索引。
    """
    for i, w in enumerate(rows):
        top = w.winfo_rooty()
        mid = top + w.winfo_height() / 2
        if y_root < mid:
            return i
    return len(rows)


class Panel:
    def __init__(self, root, state, cfg, actions, root_window=None):
        self.root = root
        self.state = state
        self.cfg = cfg
        self.actions = actions
        self.root_window = root_window

        self._sig = None
        self._rows = {}
        self._last_paint = {}
        self._last_results = []
        self._minimized = False
        self._drag_ok = False

        is_frame = isinstance(root, tk.Frame) and not isinstance(root, tk.Toplevel)
        if is_frame and root_window is None:
            raise ValueError(
                "Panel 收到 Frame 作为 parent 时,必须显式传入 root_window=Tk 根窗口 "
                "(用于 title/overrideredirect/attributes/minsize/maxsize/geometry 等窗口级操作)"
            )
        if not is_frame:
            root.title("AgentEye")
            root.overrideredirect(True)
            root.attributes("-topmost", True)
            root.configure(bg=C["bg"])
            self._place_initial()

        if is_frame:
            self._mac_mode = True
            self._build_header = self._skip_build_header
            self._build_resize_grip = self._skip_build_resize_grip
        else:
            self._mac_mode = False

        self._build_header()
        self.rows_container = tk.Frame(root, bg=C["bg"])
        self.rows_container.pack(fill="both", expand=True, padx=(10, 0),
                                  pady=(0, 0))
        self.rows_canvas = tk.Canvas(self.rows_container, bg=C["bg"],
                                     highlightthickness=0, bd=0)
        self.rows_scroll = make_dark_scrollbar(self.rows_container, orient="vertical",
                                               command=self.rows_canvas.yview)
        self.rows_frame = tk.Frame(self.rows_canvas, bg=C["bg"])
        self.rows_frame.bind(
            "<Configure>",
            lambda e: self.rows_canvas.configure(
                scrollregion=self.rows_canvas.bbox("all")),
        )
        self._rows_window = self.rows_canvas.create_window(
            (0, 0), window=self.rows_frame, anchor="nw")
        self.rows_canvas.configure(yscrollcommand=self.rows_scroll.set)
        self.rows_canvas.pack(side="left", fill="both", expand=True)
        self.rows_scroll.pack(side="right", fill="y", padx=(0, 10))
        self.rows_canvas.bind("<Configure>", self._on_rows_canvas_configure)
        self.rows_canvas.bind("<Enter>", self._rows_wheel_enter)
        self.rows_canvas.bind("<Leave>", self._rows_wheel_leave)
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
        root.bind("<Map>", self._on_map)
        root.bind("<F5>", lambda e: actions["refresh_now"]())
        root.bind("<Control-q>", lambda e: actions["quit"]())
        root.bind("<Escape>", lambda e: self._close_any_popup())

        self._tick()
        self._maybe_welcome()
        self._build_resize_grip()
        self.root.bind("<Configure>", self._on_root_configure)

        on_theme_change(self.refresh_palette)

    def _place_initial(self):
        ui = self.cfg.get("ui") or {}
        x, y = ui.get("x"), ui.get("y")
        w = ui.get("width") or 360
        h = ui.get("height") or 360
        if x is None or y is None:
            sw = self.root.winfo_screenwidth()
            x, y = sw - w - 20, 60
        self.root.update_idletasks()
        self.root.geometry(f"{int(w)}x{int(h)}+{int(x)}+{int(y)}")
        self.root.minsize(MIN_W, MIN_H)
        self.root.maxsize(MAX_W, MAX_H)

    def _make_hdr_btn(self, parent, text, fg=None, hover_fg=None, size=10):
        """Header 统一按钮:flat + #2a2a3a 底,与设置对话框按钮同风格。"""
        base_fg = fg or C["text"]
        btn = tk.Button(parent, text=text, font=(FONT, size),
                        bg=BTN_BG, fg=base_fg, relief="flat", bd=0,
                        activebackground=BTN_HOVER, activeforeground=hover_fg or base_fg,
                        highlightthickness=0, takefocus=0, cursor="hand2",
                        padx=7, pady=0, width=1)
        btn._fg = base_fg
        btn._hover_fg = hover_fg or base_fg
        btn.bind("<Enter>", lambda e: btn.config(bg=BTN_HOVER, fg=btn._hover_fg))
        btn.bind("<Leave>", lambda e: btn.config(bg=BTN_BG, fg=btn._fg))
        return btn

    def _skip_build_header(self):
        return None

    def _skip_build_resize_grip(self):
        return None

    def _build_header(self):
        header = tk.Frame(self.root, bg=C["bg"])
        header.pack(fill="x", padx=10, pady=(8, 2))
        tk.Label(header, text="AgentEye", font=(FONT, 10, "bold"),
                 fg=C["text"], bg=C["bg"]).pack(side="left")
        self.dot = tk.Label(header, text="●", font=(FONT, 9),
                            fg=C["dim"], bg=C["bg"])
        self.dot.pack(side="right", padx=(0, 8))

        close = self._make_hdr_btn(header, "×", fg=C["dim"], hover_fg=C["critical"])
        close.pack(side="right")
        close.config(command=self.actions["quit"])

        min_btn = self._make_hdr_btn(header, "–", fg=C["dim"], hover_fg=C["text"])
        min_btn.pack(side="right", padx=(0, 4))
        min_btn.config(command=self._minimize)

        self._pinned = bool((self.cfg.get("ui") or {}).get("pinned", True))
        self.pin_btn = self._make_hdr_btn(header, "⊙" if self._pinned else "○",
                                          fg=C["ok"] if self._pinned else C["dim"],
                                          hover_fg=C["warn"] if self._pinned else C["ok"])
        self.pin_btn.pack(side="right", padx=(0, 4))
        self.pin_btn.config(command=self._toggle_pin)
        if self._pinned:
            self.root.attributes("-topmost", True)

        gear_btn = self._make_hdr_btn(header, "≡", fg=C["dim"], hover_fg=C["text"])
        gear_btn.pack(side="right", padx=(0, 4))
        gear_btn.config(command=lambda: self.actions.get("open_settings", lambda: None)())
        self.gear_btn = gear_btn

    def _minimize(self):
        """overrideredirect 窗口最小化:临时恢复装饰 iconify,还原时重新隐藏边框。"""
        self._minimized = True
        try:
            self.root.overrideredirect(False)
            self.root.iconify()
        except tk.TclError:
            self._minimized = False

    def _on_map(self, event):
        if event.widget is not self.root or not getattr(self, "_minimized", False):
            return
        self._minimized = False
        try:
            self.root.overrideredirect(True)
            self.root.attributes("-topmost", self._pinned)
        except tk.TclError:
            pass

    def _toggle_pin(self):
        self._pinned = not self._pinned
        self.root.attributes("-topmost", self._pinned)
        fg = C["ok"] if self._pinned else C["dim"]
        self.pin_btn.config(text="⊙" if self._pinned else "○", fg=fg)
        self.pin_btn._fg = fg
        self.pin_btn._hover_fg = C["warn"] if self._pinned else C["ok"]
        save_pin = self.actions.get("save_pin")
        if save_pin:
            save_pin(self._pinned)

    def _build_menu(self):
        m = tk.Menu(self.root, tearoff=0)
        m.add_command(label="立即刷新", command=self.actions["refresh_now"])
        m.add_command(label="通知测试", command=self.actions["test_notify"])
        m.add_command(label="添加 Key…",
                      command=self.actions.get("add_key", lambda: None))
        self._pause_idx = m.index("end")
        m.add_command(label="暂停轮询", command=self.actions["toggle_pause"])
        m.add_command(label="切换为单行模式",
                      command=self.actions.get("toggle_mode", lambda: None))
        m.add_command(label="打开配置文件", command=self.actions["open_config"])
        m.add_command(label="设置…",
                      command=self.actions.get("open_settings", lambda: None))
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

    def _is_window_drag_target(self, widget):
        """root 绑定对所有子控件生效;交互控件按下时不启动窗口拖动。

        - resize grip(含内部圆点): 交给 _resize_* 处理
        - provider 行卡片: 交给行拖拽重排/复制逻辑
        - Header 按钮(tk.Button): 交给自身 command
        """
        w = widget
        while w is not None:
            if w is self._resize_grip or getattr(w, "_provider_name", None):
                return False
            if w.winfo_class() == "Button":
                return False
            w = getattr(w, "master", None)
        return True

    def _drag_start(self, event):
        self._drag_ok = self._is_window_drag_target(event.widget)
        if not self._drag_ok:
            return
        self._ox = event.x_root - self.root.winfo_x()
        self._oy = event.y_root - self.root.winfo_y()
        self.root.config(cursor="fleur")

    def _drag_move(self, event):
        if not self._drag_ok:
            return
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
        if not self._drag_ok:
            return
        self._drag_ok = False
        self.root.config(cursor="")
        self.actions["save_position"](
            self.root.winfo_x(), self.root.winfo_y())
        save_size = self.actions.get("save_size")
        if save_size:
            save_size(self.root.winfo_width(), self.root.winfo_height())

    def _build_resize_grip(self):
        grip = tk.Frame(self.root, bg=C["bg"], cursor="size_nw_se",
                        width=RESIZE_GRIP, height=RESIZE_GRIP)
        grip.pack(side="bottom", anchor="se")
        grip.bind("<Button-1>", self._resize_start)
        grip.bind("<B1-Motion>", self._resize_move)
        grip.bind("<ButtonRelease-1>", self._resize_end)
        for i in range(3):
            r = tk.Frame(grip, bg=C["dim"], width=2, height=2)
            r.place(x=RESIZE_GRIP - 2 - i * 4, y=RESIZE_GRIP - 2 - i * 4)
        self._resize_grip = grip

    def _resize_start(self, event):
        self._rx = event.x_root
        self._ry = event.y_root
        self._rw = self.root.winfo_width()
        self._rh = self.root.winfo_height()
        self._resize_saved = False

    def _resize_move(self, event):
        dx = event.x_root - self._rx
        dy = event.y_root - self._ry
        new_w = max(MIN_W, min(MAX_W, self._rw + dx))
        new_h = max(MIN_H, min(MAX_H, self._rh + dy))
        self.root.geometry(f"{int(new_w)}x{int(new_h)}")

    def _resize_end(self, event):
        save_size = self.actions.get("save_size")
        if save_size:
            save_size(self.root.winfo_width(), self.root.winfo_height())

    def refresh_palette(self, *_args):
        """主题切换时:刷新 C / LEVEL_COLOR、重画所有 row 的 bg 与 fg。

        on_theme_change 监听回调签名 cb(choice, palette, persist);忽略参数。
        """
        try:
            _refresh_C()
            _refresh_BTN()
        except Exception:
            pass
        try:
            if not self._mac_mode:
                self.root.configure(bg=C["bg"])
            self.rows_container.configure(bg=C["bg"])
            self.rows_canvas.configure(bg=C["bg"])
            self.rows_frame.configure(bg=C["bg"])
            self.footer.configure(bg=C["bg"], fg=C["dim"])
        except tk.TclError:
            pass

        for name, widgets in list(self._rows.items()):
            if not isinstance(widgets, dict):
                continue
            try:
                bg = _row_bg({"unit": ("$" if widgets.get("is_amount") else "")})
                card = widgets.get("frame")
                if card:
                    card.configure(bg=bg)
                    card._bg = bg
                    for child in card.winfo_children():
                        try:
                            child.configure(bg=bg)
                        except tk.TclError:
                            pass
                bar = widgets.get("bar")
                if bar is not None:
                    bar.configure(bg=C["bar_bg"])
                for key in ("name", "value", "detail"):
                    w = widgets.get(key)
                    if w is None:
                        continue
                    try:
                        if key == "name":
                            w.configure(fg=C["text"], bg=bg)
                        elif key == "value":
                            w.configure(bg=bg)
                        elif key == "detail":
                            w.configure(fg=C["dim"], bg=bg)
                    except tk.TclError:
                        pass
            except Exception:
                continue

        results = list(getattr(self.state, "results", None) or [])
        if results:
            try:
                self._rebuild(results)
            except Exception:
                pass

    def _on_root_configure(self, event):
        if event.widget is not self.root:
            return
        try:
            width = self.root.winfo_width()
        except tk.TclError:
            return
        if width <= 1:
            return
        wrap = max(120, width - 36)
        for w in self._rows.values():
            d = w.get("detail")
            if d is not None:
                try:
                    d.configure(wraplength=wrap)
                except tk.TclError:
                    pass

    def _close_any_popup(self):
        for w in self.root.winfo_children():
            if isinstance(w, tk.Toplevel):
                w.destroy()
                return

    def _on_rows_canvas_configure(self, event):
        try:
            self.rows_canvas.itemconfig(self._rows_window, width=event.width)
        except tk.TclError:
            pass

    def _on_rows_wheel(self, event):
        try:
            delta = int(-1 * (event.delta / 120))
            self.rows_canvas.yview_scroll(delta, "units")
        except tk.TclError:
            pass

    def _rows_wheel_enter(self, event):
        try:
            self.rows_canvas.bind_all("<MouseWheel>", self._on_rows_wheel)
        except tk.TclError:
            pass

    def _rows_wheel_leave(self, event):
        try:
            self.rows_canvas.unbind_all("<MouseWheel>")
        except tk.TclError:
            pass

    def _drag_press(self, event, name):
        value_lbl = self._rows.get(name, {}).get("value")
        self._drag = {
            "name": name,
            "start_y": event.y_root,
            "start_x": event.x_root,
            "active": False,
            "target": None,
            "original_index": None,
            "is_value_click": event.widget is value_lbl,
        }

    def _drag_motion(self, event, name):
        d = getattr(self, "_drag", None)
        if not d or d["name"] != name:
            return
        if not d["active"]:
            if abs(event.y_root - d["start_y"]) <= 8:
                return
            d["active"] = True
            widgets = self._rows.get(name)
            if not widgets:
                return
            card = widgets["frame"]
            d["widget"] = card
            d["original_index"] = list(self.rows_frame.pack_slaves()).index(card)
            d["target"] = d["original_index"]
            self.root.config(cursor="hand2")
            self._show_drag_indicator()
        if d["active"]:
            new_target = self._compute_drag_target(event.y_root, name)
            if new_target != d["target"]:
                d["target"] = new_target
                self._show_drag_indicator()

    def _drag_release(self, event, name):
        d = getattr(self, "_drag", None)
        if not d or d["name"] != name:
            return
        if d["active"]:
            self._clear_drag_indicator()
            self._commit_drag(name, d["target"])
            self.root.config(cursor="")
        elif d.get("is_value_click"):
            self._copy_value(name)
        else:
            self._clear_drag_indicator()
        self._drag = None

    def _compute_drag_target(self, y_root, exclude_name):
        cards = [w for w in self.rows_frame.pack_slaves()
                 if getattr(w, "_provider_name", None) != exclude_name]
        return _compute_target_static(cards, y_root)

    def _show_drag_indicator(self):
        self._clear_drag_indicator()
        d = getattr(self, "_drag", None)
        if not d:
            return
        cards = [w for w in self.rows_frame.pack_slaves()
                 if w is not d.get("widget")]
        indicator = tk.Frame(self.rows_frame, height=3,
                             bg=PALETTE.BLUE)
        d["indicator"] = indicator
        idx = d["target"]
        if idx < len(cards):
            indicator.pack(fill="x", pady=0, before=cards[idx])
        else:
            indicator.pack(fill="x", pady=0)

        dragged = d.get("widget")
        if dragged is not None:
            try:
                dragged._drag_active = True
                dragged.configure(bg=C["card_pressed"])
                for child in dragged.winfo_children():
                    try:
                        child.configure(bg=C["card_pressed"])
                    except tk.TclError:
                        pass
            except tk.TclError:
                pass

    def _clear_drag_indicator(self):
        d = getattr(self, "_drag", None)
        if d and d.get("indicator"):
            try:
                d["indicator"].destroy()
            except tk.TclError:
                pass
            d["indicator"] = None
        if d and d.get("widget"):
            w = d["widget"]
            try:
                original_bg = getattr(w, "_bg", C["card"])
                w.configure(bg=original_bg)
                for child in w.winfo_children():
                    try:
                        child.configure(bg=original_bg)
                    except tk.TclError:
                        pass
                w._drag_active = False
            except tk.TclError:
                pass

    def _commit_drag(self, name, new_index):
        widgets = self._rows.get(name)
        if not widgets:
            return
        card = widgets["frame"]
        cards = [w for w in self.rows_frame.pack_slaves() if w is not card]
        cards.insert(max(0, min(new_index, len(cards))), card)
        for w in self.rows_frame.pack_slaves():
            w.pack_forget()
        for w in cards:
            w.pack(fill="x", pady=3)
        new_order = [getattr(c, "_provider_name", "") for c in cards]
        save_order = self.actions.get("save_order")
        if save_order:
            save_order(new_order)
        self._sig = None

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
        dot = getattr(self, "dot", None)
        if dot is not None:
            if self.state.paused:
                dot.config(fg=C["off"])
            elif "critical" in levels:
                dot.config(fg=C["critical"])
            elif "error" in levels:
                dot.config(fg=C["error"])
            elif "warn" in levels:
                dot.config(fg=C["warn"])
            else:
                dot.config(fg=C["ok"])

        footer = getattr(self, "footer", None)
        if footer is not None:
            if self.state.paused:
                text = "已暂停轮询"
            elif self.state.fetching:
                text = "刷新中…"
            elif self.state.next_fetch:
                text = f"下次刷新 {_fmt_countdown(self.state.next_fetch - time.time())}"
            else:
                text = "等待首次刷新…"
            footer.config(text=text)

    def _rebuild(self, results):
        for child in self.rows_frame.winfo_children():
            child.destroy()
        self._rows = {}
        self._last_paint = {}
        if not results:
            box = self._row_skeleton("未配置任何 provider", "右键 + 添加 Key",
                                      {"unit": ""})
            box["value"].config(text="-", fg=C["off"])
            return
        order = []
        get_order = self.actions.get("get_order")
        if get_order:
            order = get_order()
        name_to_result = {r["name"]: r for r in results}
        ordered = [name_to_result[n] for n in order if n in name_to_result]
        ordered += [r for r in results if r["name"] not in order]
        for r in ordered:
            self._rows[r["name"]] = self._row_skeleton(r["name"], "", r)

    def _row_skeleton(self, name, detail, result=None):
        result = result or {}
        bg = _row_bg(result)
        is_amount = _is_amount_mode(result)
        card = tk.Frame(self.rows_frame, bg=bg, cursor="hand2")
        card.pack(fill="x", pady=3)
        card._provider_name = name
        card._bg = bg
        top = tk.Frame(card, bg=bg)
        top.pack(fill="x", padx=8, pady=(6, 0))
        prefix = "💰 " if is_amount else ""
        name_lbl = tk.Label(top, text=prefix + name, font=(FONT, 9, "bold"),
                            fg=C["text"], bg=bg)
        name_lbl.pack(side="left")
        value_lbl = tk.Label(top, text="…", font=(FONT, 9),
                             fg=C["dim"], bg=bg, cursor="hand2")
        value_lbl.pack(side="right")
        det_lbl = tk.Text(card, font=(FONT, 9), fg=C["dim"], bg=bg,
                          wrap="word", height=1, bd=0, highlightthickness=0,
                          padx=0, pady=2, cursor="arrow", takefocus=0)
        det_lbl.pack(fill="x", padx=8)
        det_lbl.tag_config("dim", foreground=C["dim"])
        det_lbl.tag_config("highlight", foreground=C["dim"])
        det_lbl.tag_raise("sel", "dim")
        det_lbl.insert("end", detail or "")
        det_lbl.config(state="disabled")
        bar = None
        rect = None
        if not is_amount:
            bar = tk.Canvas(card, height=5, bg=C["bar_bg"], highlightthickness=0)
            bar.pack(fill="x", padx=8, pady=(4, 7))
            rect = bar.create_rectangle(0, 0, 0, 5, outline="")

        widgets = {"frame": card, "name": name_lbl, "value": value_lbl,
                   "detail": det_lbl, "bar": bar, "rect": rect,
                   "provider_name": name, "is_amount": is_amount}

        if bar is not None:
            bar.bind(
                "<Configure>",
                lambda e, b=bar, r=rect, w=widgets: _on_bar_configure(e, b, r, w),
                add="+",
            )

        for w in (card, top, name_lbl):
            w.bind("<Enter>", lambda e, ww=card: ww.config(bg=C["card_hover"]))
            w.bind("<Leave>", lambda e, ww=card: ww.config(bg=ww._bg))
        value_lbl.bind("<Enter>", lambda e: value_lbl.config(fg=C["ok"]))
        value_lbl.bind("<Leave>", lambda e: value_lbl.config(fg=C["dim"]))

        card.bind("<Button-3>", lambda e, n=name: self._popup_row_menu(e, n))
        name_lbl.bind("<Button-3>", lambda e, n=name: self._popup_row_menu(e, n))

        drag_widgets = [w for w in (card, top, name_lbl, det_lbl, bar) if w is not None]
        for w in drag_widgets:
            w.bind("<Button-1>", lambda e, n=name: self._drag_press(e, n), add="+")
            w.bind("<B1-Motion>", lambda e, n=name: self._drag_motion(e, n), add="+")
            w.bind("<ButtonRelease-1>", lambda e, n=name: self._drag_release(e, n), add="+")

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
        self._row_menu_inst.set_target(name)
        try:
            self._row_menu_inst.menu.tk_popup(event.x_root, event.y_root)
        finally:
            self._row_menu_inst.menu.grab_release()

    def _copy_key(self, name):
        for p in self.cfg.get("providers") or []:
            if p.get("name") == name:
                key = config_mod.plain_key(p)
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
        key = config_mod.plain_key(provider_cfg)
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

        save_model_order = self.actions.get("save_model_order")
        def _on_reorder(new_order):
            if save_model_order:
                save_model_order(name, base_url, key, new_order)
        ModelPanel(self.root, name, models, on_probe=_probe_cb,
                   on_reorder=_on_reorder,
                   on_after_reorder=lambda: self.actions["refresh_now"]())

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
        if bar is None or rect is None:
            return
        widgets["_bar_frac"] = frac if frac is not None else 1.0
        widgets["_bar_color"] = color
        try:
            width = bar.winfo_width()
        except tk.TclError:
            width = 0
        if width >= 2:
            bar.coords(rect, 0, 0, int(width * widgets["_bar_frac"]), 5)
            bar.itemconfig(rect, fill=widgets["_bar_color"])
