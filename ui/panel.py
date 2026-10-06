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
import weakref

import config as config_mod
from ui.theme import PALETTE, Layout, set_theme, bind_theme_listener, to_tk_color, to_tk_color_blended
from ui.scrollbar_style import make_dark_scrollbar
from ui.screen import work_area, snap_clamp

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
    "card_pressed": to_tk_color(PALETTE.CARD_PRESSED),
}

LEVEL_COLOR = {k: C[k] for k in ("ok", "warn", "critical", "error")}
LEVEL_COLOR["unconfigured"] = C["off"]
LEVEL_COLOR["paused"] = C["off"]
LEVEL_COLOR["unknown"] = C["dim"]

EDGE_SNAP = 20
FIRST_RUN_FLAG = "~/.agenteye/.first_run_done"
MIN_W, MIN_H = 280, 180
MAX_W, MAX_H = 800, 900
RESIZE_GRIP = 16
BTN_BG = "#2a2a3a"
BTN_HOVER = "#34344a"

# 活着且还在跑 1Hz 定时器的 Panel。测试之间由 conftest 统一 stop(),
# 生产代码不需要读它。
_LIVE_PANELS = weakref.WeakSet()


def _register_self(panel):
    _LIVE_PANELS.add(panel)


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
    C["card_pressed"] = to_tk_color(PALETTE.CARD_PRESSED)
    LEVEL_COLOR["ok"] = C["ok"]
    LEVEL_COLOR["warn"] = C["warn"]
    LEVEL_COLOR["critical"] = C["critical"]
    LEVEL_COLOR["error"] = C["error"]
    LEVEL_COLOR["unconfigured"] = C["off"]
    LEVEL_COLOR["paused"] = C["off"]
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
    if result.get("paused"):
        return "已暂停"
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
        # 主值与胶囊同口径:条长/条色画的是已消耗占比,数字就写"已用",
        # 不再显示剩余 pct——两者互补,并列展示必然有一边被误读。
        pct = result.get("pct")
        if pct is None:
            return "-"
        used = max(0.0, min(100.0, 100.0 - float(pct)))
        return f"已用 {used:.0f}%"
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
    否则用 used/total;百分比行用 (100-pct)/100。
    拿不到可算的分子分母就返回 None——绝不按 level 编一个假比例:
    假比例会被画进胶囊长度,deepseek 余额 ¥5000 和 ¥6 会一样长。

    注意:金额行**不**用 pct 兜底。opencode_go 的 percent 字段在
    providers 里存在"已用/剩余"两种读法(providers/opencode_go.py
    把它乘 limit 当已用,_level 把它当剩余),方向不明前宁可不算。
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
        return None
    if unit == "%" and isinstance(pct, (int, float)):
        return max(0.0, min(1.0, (100 - pct) / 100))

    return None


def _row_color(result):
    """行内数值与胶囊共用的颜色。

    - 有占比 → 按消耗比绿→黄→红渐变(与胶囊同源)
    - 无占比:level 是 warn/critical 时沿用等级色——余额类行
      (deepseek/中转订阅)拿不到占比但 _level 按 ¥5 阈值判级,
      余额 ¥1 显示灰字而标题点是红色,自相矛盾
    - 其余(unconfigured/paused/error/unknown/ok)→ 灰
    """
    ratio_val = _usage_ratio(result)
    if ratio_val is not None:
        return _usage_color(ratio_val), ratio_val
    level = result.get("level", "unknown")
    if level in ("warn", "critical"):
        return C[level], None
    return C["off"], None


def _usage_color(ratio):
    """绿(0) → 黄(0.5) → 红(1) 三色插值,端点实时取 PALETTE。

    原先把 #53d77a/#f0c24b/#ff5d5d 写死在函数体里,浅色主题下这组
    颜色偏深,且与等级色(LEVEL_COLOR)不来自同一来源。
    """
    if ratio is None:
        return C["dim"]
    stops = (to_tk_color(PALETTE.OK), to_tk_color(PALETTE.WARN),
             to_tk_color(PALETTE.CRITICAL))
    rgb = [tuple(int(s[i:i + 2], 16) for i in (1, 3, 5)) for s in stops]
    ratio = max(0.0, min(1.0, ratio))
    seg = 0 if ratio <= 0.5 else 1
    t = (ratio - 0.5 * seg) / 0.5
    c0, c1 = rgb[seg], rgb[seg + 1]
    r, g, b = (int(c0[i] + (c1[i] - c0[i]) * t) for i in range(3))
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


def _rounded_points(x1, y1, x2, y2, r):
    """12 点圆角矩形点集,配合 create_polygon(smooth=True) 画胶囊。

    每个角给两个相邻边上的点,smooth 样条自动把角部圆化;
    半径由角点间距决定,r 取条高一半即得全圆角(胶囊)。
    """
    return (x1 + r, y1, x2 - r, y1,
            x2, y1, x2, y1 + r,
            x2, y2 - r, x2, y2,
            x2 - r, y2, x1 + r, y2,
            x1, y2, x1, y2 - r,
            x1, y1 + r, x1, y1)


def _draw_capsule(bar, widgets, width, frac, color):
    """画胶囊轨道与填充。width 来自 <Configure> 或 winfo_width。

    - 轨道永远画满 0..width,颜色 C["bar_bg"]
    - 填充 0..int(width*frac);不足一个圆头直径(2r)时不画——
      12 点点集在 x2 < 2r 时会出现反向坐标,画出来是畸形,
      与其失真不如隐藏(不足 12px ≈ 用量 4%,肉眼本来不可辨)
    - frac 为 None(未知占比)等同 0,绝不画满格
    """
    h = Layout.ROW_BAR_HEIGHT
    r = h / 2.0
    rect = widgets.get("rect")
    track = widgets.get("track")
    if bar is None or rect is None:
        return
    try:
        if track is not None:
            bar.coords(track, *_rounded_points(0, 0, width, h, r))
            bar.itemconfig(track, fill=C["bar_bg"], state="normal")
        x2 = int(width * max(0.0, min(1.0, frac or 0.0)))
        if x2 < 2 * r:
            bar.itemconfig(rect, state="hidden")
            return
        bar.coords(rect, *_rounded_points(0, 0, x2, h, r))
        bar.itemconfig(rect, fill=color, state="normal")
    except tk.TclError:
        pass


def _on_bar_configure(event, bar, rect, widgets):
    """Tk 布局驱动:bar 实际 width 就绪 / 尺寸变化时重画胶囊。

    替代原 ``bar.winfo_width() or 300`` 兜底:
    - 首帧布局完成 → ``<Configure>`` 触发,``event.width`` 正确 → 修"刚打开进度条看不见"
    - 窗口 resize → bar 跟随 pack(fill="x") 重排 → ``<Configure>`` 触发 → 修"resize 后 bar 不跟随"

    颜色/比例由 ``_paint_row`` 写入 ``widgets["_bar_color"]`` / ``widgets["_bar_frac"]``。
    两个键均未初始化时(placeholder 行)直接跳过;只有其一但 frac 缺失按 0 处理,
    不画满格——未初始化就显示满格额度是误导。
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
        frac = 0.0
    _draw_capsule(bar, widgets, width, frac, color)


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
        self._anim_rows = set()
        self._last_focus_refresh = 0.0
        self._tick_after_id = None
        _register_self(self)
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

        # 键盘/焦点类绑定必须挂到 Toplevel。挂在 slot(Frame)上时,
        # 行内 Text 一旦吃掉焦点,Frame 的 bindtag 链不含子控件,
        # F5 / Ctrl+Q / Esc 会全线失效。
        toplevel = self.root_window or root
        toplevel.bind("<FocusIn>", self._on_focus_in, add="+")
        toplevel.bind("<F5>", lambda e: actions["refresh_now"](), add="+")
        toplevel.bind("<Control-q>", lambda e: actions["quit"](), add="+")
        toplevel.bind("<Escape>", lambda e: self._close_any_popup(), add="+")
        # 右键菜单必须绑 toplevel:子控件的 bindtags 含 toplevel、不含父
        # Frame,绑在 root(=mac 模式的 standard_slot)上时面板体内点不到。
        toplevel.bind("<Button-3>", self._popup_main_menu, add="+")
        # 拖动窗口只绑在 toplevel 上:mac 模式下 MacHeader 已经在拖,
        # 面板 body 不再抢,否则两套拖拽逻辑打架。
        if not is_frame:
            for w in (root,):
                w.bind("<Button-1>", self._drag_start, add="+")
                w.bind("<B1-Motion>", self._drag_move, add="+")
                w.bind("<ButtonRelease-1>", self._drag_end, add="+")

        self.menu = self._build_menu()
        root.bind("<Map>", self._on_map, add="+")

        self._tick()
        self._maybe_welcome()
        self._build_resize_grip()
        self.root.bind("<Configure>", self._on_root_configure, add="+")

        bind_theme_listener(toplevel, self.refresh_palette)
        # 构造期 C 可能是深色快照(Panel 晚于 apply_theme 创建),
        # 这里主动刷一次,让首帧就用当前主题的色。
        self.refresh_palette()

    FOCUS_REFRESH_MIN_INTERVAL = 3.0

    def _on_focus_in(self, event=None):
        """窗口重新激活时刷新一次(去抖)。

        Tk 会为焦点控件**及其每一层祖先**各生成一个 FocusIn,而 bindtags
        里的 toplevel 是所有后代的第 3 个 tag —— 所以绑在 toplevel 上时,
        点设置对话框里任意输入框、模型面板搜索框都会触发一次全量轮询。
        README 说的是"窗口获得焦点",实际发生的却是"任何子控件"。

        两道闸:
        - 只认 toplevel 本身的 FocusIn(event.widget 是 toplevel),子控件
          点进来的 FocusIn 一律忽略;
        - 加最小间隔,防止开/关对话框这类连续动作连发多轮请求。
        """
        state = getattr(self, "state", None)
        if state is not None and getattr(state, "fetching", False):
            return
        top = self.root_window or self.root
        if event is not None and getattr(event, "widget", None) is not top:
            return
        now = time.time()
        if now - self._last_focus_refresh < self.FOCUS_REFRESH_MIN_INTERVAL:
            return
        self._last_focus_refresh = now
        self.actions["refresh_now"]()

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
        # mac 模式下 grip 由 MacWindow 接管(MacWindow._build_resize_grip)。
        # 必须显式置 None,否则 _is_window_drag_target 读 self._resize_grip
        # 会 AttributeError。
        self._resize_grip = None
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
        # 与 ui/row_menu 同一套配色:默认 tk.Menu 是系统灰,
        # 在深色窗口旁边非常突兀
        m = tk.Menu(
            self.root, tearoff=0, bd=0,
            bg=C["card"], fg=C["text"],
            activebackground=C["card_hover"],
            activeforeground=C["text"],
        )
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
        # 行卡片自己绑了 <Button-3> 走行菜单,这里只接管其余区域。
        # 门槛不能用 "event.widget is self.root":mac 模式下 self.root 是
        # standard_slot(Frame),而子控件的 bindtags 只有
        # "自身 → class → toplevel → all",不含父 Frame。绑在 slot 上时
        # 面板体内几乎任何位置右键都到不了这里,只有 slot 自身那 10px
        # 左边条能唤出菜单(README 承诺的 8 项入口实质不可达)。
        if getattr(event.widget, "_provider_name", None):
            return
        paused = self.state.paused
        self.menu.entryconfig(
            self._pause_idx + 1,
            label="恢复轮询" if paused else "暂停轮询")
        try:
            self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            try:
                self.menu.grab_release()
            except tk.TclError:
                pass


    def _is_window_drag_target(self, widget):
        """root 绑定对所有子控件生效;交互控件按下时不启动窗口拖动。

        - resize grip(含内部圆点): 交给 _resize_* 处理
        - provider 行卡片: 交给行拖拽重排/复制逻辑
        - Header 按钮(tk.Button): 交给自身 command
        """
        w = widget
        grip = getattr(self, "_resize_grip", None)
        while w is not None:
            if w is grip or getattr(w, "_provider_name", None):
                return False
            if w.winfo_class() == "Button":
                return False
            if w.winfo_class() == "Scrollbar":
                # 拖滚动条是把内容滚上去,不是把窗口拖走
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
        # 与 MacWindow 同款:按窗口当前坐标找最近的显示器吸附其工作区,
        # 主屏钳制在多显示器下会把副屏窗口强行拽回去
        x, y = snap_clamp(
            x, y, self.root.winfo_width(), self.root.winfo_height(),
            work_area(x, y, (self.root.winfo_screenwidth(),
                             self.root.winfo_screenheight())),
            EDGE_SNAP)
        self.root.geometry(f"+{int(x)}+{int(y)}")

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
                    # canvas 底色由上面的 child 循环刷成卡片色;胶囊本体
                    # (轨道/填充)是 canvas 图元,configure(bg) 够不到,
                    # 轨道色必须在这里重设,否则浅色主题残留深色轨道。
                    track = widgets.get("track")
                    if track is not None:
                        try:
                            bar.itemconfig(track, fill=C["bar_bg"])
                        except tk.TclError:
                            pass
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
                yview = self.rows_canvas.yview()
            except tk.TclError:
                yview = None
            try:
                self._rebuild(results)
            except Exception:
                pass
            # _rebuild 销毁重建所有行,scrollregion 塌缩会把 yview 钳回 0;
            # 不恢复的话每次主题切换列表都跳回顶部
            if yview:
                try:
                    self.rows_canvas.yview_moveto(yview[0])
                except tk.TclError:
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
        # detail 是 Text(wrap="word"),按像素自动换行;但 width 以
        # "平均字符"计且创建后固定,窗口拉宽后长 detail 不会利用新
        # 空间。按窗口宽估字符数同步放大(9pt 下 ≈7px/字符)。
        # 原实现 configure(wraplength=...) —— Text 没有该选项,每次
        # TclError 被吞,整个回调是死代码。
        chars = max(12, (width - 32) // 7)
        for w in self._rows.values():
            d = w.get("detail")
            if d is not None:
                try:
                    d.configure(width=chars)
                except tk.TclError:
                    pass

    def _close_any_popup(self):
        """Esc 关掉最上层的对话框。

        对话框的 parent 是 Tk 根窗口,不是 self.root(mac 模式下 =
        standard_slot),所以必须从 toplevel 往下找,否则 mac 模式
        按 Esc 永远没反应。

        走 wm_protocol 而不是直接 destroy:SettingsDialog._on_close_request
        里会 unbind_all("<MouseWheel>"),直接 destroy 会跳过它,
        之后整个应用的滚轮失效。
        """
        top = self.root_window or self.root
        try:
            tops = [w for w in top.winfo_children() if isinstance(w, tk.Toplevel)]
        except tk.TclError:
            return
        if not tops:
            return
        # 最上层 = 栈里最后一个
        dlg = tops[-1]
        try:
            dlg.wm_protocol("WM_DELETE_WINDOW")
            dlg.destroy()
        except tk.TclError:
            pass

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
            # 记下 funcid,离开时只摘自己那一个。unbind_all(sequence) 会把
            # "all" bindtag 上该序列的**所有**绑定清掉,包括设置对话框和
            # 模型面板的 —— 于是"面板行区 → 设置列表 → 移出"之后,
            # 面板的滚轮就没了,直到鼠标重新进出行区。
            self._rows_wheel_funcid = self.rows_canvas.bind_all(
                "<MouseWheel>", self._on_rows_wheel, add="+")
        except tk.TclError:
            pass

    def _rows_wheel_leave(self, event):
        fid = getattr(self, "_rows_wheel_funcid", None)
        self._rows_wheel_funcid = None
        if fid is None:
            return
        try:
            self.rows_canvas.unbind_all("<MouseWheel>", fid)
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
        # 占位行("未配置任何 provider")也挂在 rows_frame 下且带
        # _provider_name,不按真实结果过滤会把占位文本存进 order
        known = {r.get("name") for r in (self.state.results or [])}
        new_order = [n for n in new_order if n in known]
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
        self._tick_after_id = None
        try:
            if not self.root.winfo_exists():
                return
            self._update()
            # 有行在滑条缓动中 → 33ms 快 tick,收敛后回 1Hz
            delay = 33 if self._anim_rows else 1000
            self._tick_after_id = self.root.after(delay, self._tick)
        except tk.TclError:
            pass

    def stop(self):
        """停掉 1Hz 定时器。窗口销毁前必须调用。

        定时器只挂在 self.root 上,窗口被销毁时 Tk 会把该窗口的 after
        一起清掉,但如果 root 是被外部直接 destroy 掉、解释器随之拆掉,
        队列里残留的回调会在下一个事件循环里打到已销毁的解释器上,
        表现为整个进程崩在 Tk 内部(Windows fatal exception)。
        """
        aid, self._tick_after_id = self._tick_after_id, None
        if aid is not None:
            try:
                self.root.after_cancel(aid)
            except tk.TclError:
                pass

    def _update(self):
        results = list(self.state.results or [])
        # sig 必须含 unit:行的结构(有没有胶囊、卡片底色)由 is_amount
        # 在 _row_skeleton 时决定。首次拉取失败时 unit="" 会按"非金额行"
        # 建出胶囊,之后拿到 "$" 若不重建,那根胶囊就永久空着。
        sig = tuple((r.get("name"), r.get("type"), r.get("unit"))
                    for r in results)
        if sig != self._sig:
            self._rebuild(results)
            self._sig = sig
        for r in results:
            widgets = self._rows.get(r.get("name"))
            if widgets:
                self._paint_row(widgets, r)

        levels = [r.get("level") for r in results]
        poll_error = getattr(self.state, "poll_error", None)
        save_error = getattr(self.state, "save_error", None)
        dot = getattr(self, "dot", None)
        if dot is not None:
            if poll_error:
                dot.config(fg=C["error"])
            elif self.state.paused:
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
            fg = C["dim"]
            if poll_error:
                text = f"轮询出错:{poll_error}"
                fg = C["error"]
            elif save_error:
                text = f"配置未保存:{save_error}"
                fg = C["error"]
            elif self.state.paused:
                text = "已暂停轮询"
            elif self.state.fetching:
                text = "刷新中…"
            elif self.state.next_fetch:
                text = f"下次刷新 {_fmt_countdown(self.state.next_fetch - time.time())}"
            else:
                text = "等待首次刷新…"
            footer.config(text=text, fg=fg)

    def _rebuild(self, results):
        for child in self.rows_frame.winfo_children():
            child.destroy()
        self._rows = {}
        self._last_paint = {}
        # 行重建后旧动画目标全作废;不清理的话集合里留下死名,
        # _tick 永远跑 33ms 快档
        self._anim_rows = set()
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
        name_lbl = tk.Label(top, text=name, font=(FONT, 9, "bold"),
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
        track = None
        if not is_amount:
            bar = tk.Canvas(card, height=Layout.ROW_BAR_HEIGHT, bg=bg,
                            highlightthickness=0, bd=0)
            bar.pack(fill="x", padx=8, pady=(4, 7))
            poly_kw = {"outline": "", "width": 0, "smooth": True,
                       "splinesteps": 12, "state": "hidden"}
            track = bar.create_polygon(0, 0, 0, 0, **poly_kw)
            rect = bar.create_polygon(0, 0, 0, 0, **poly_kw)

        widgets = {"frame": card, "name": name_lbl, "value": value_lbl,
                   "detail": det_lbl, "bar": bar, "rect": rect,
                   "track": track,
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
        # 悬停只改卡片底色,不改数值前景色:数值颜色是等级语义(红/黄/绿),
        # 之前 <Leave> 把它写死成 dim,而 _paint_row 按签名去重不会再上色,
        # 于是鼠标划过一次,critical/warn 行就永久变灰。
        value_lbl.bind("<Enter>", lambda e, n=name: self._flash_value(n))
        value_lbl.bind("<Leave>", lambda e, n=name: self._unflash_value(n))


        for w in (card, top, name_lbl, det_lbl, bar, value_lbl):
            if w is None:      # 金额行没有 bar
                continue
            w.bind("<Button-3>", lambda e, n=name: self._popup_row_menu(e, n))
            # 按下态:点击时卡片压暗一档,松开恢复,给"按到了"的反馈
            w.bind("<ButtonPress-1>",
                   lambda e, ww=card: self._card_press(ww), add="+")
            w.bind("<ButtonRelease-1>",
                   lambda e, ww=card: self._card_release(ww), add="+")

        # tooltip:估算值说明 + 完整 detail(detail Text 只有 1 行高,
        # 长文案平时是被裁掉的,悬浮看全文)
        from ui.tooltip import attach as _attach_tip

        def _tip_text(n=name):
            for rr in (self.state.results or []):
                if rr.get("name") == n:
                    bits = []
                    if rr.get("is_estimate"):
                        bits.append("估算值,非官方精确口径")
                    d = rr.get("detail") or ""
                    if d:
                        bits.append(d)
                    return "\n".join(bits) or None
            return None

        _attach_tip(card, _tip_text)

        drag_widgets = [w for w in (card, top, name_lbl, det_lbl, bar,
                                    value_lbl) if w is not None]
        for w in drag_widgets:
            w.bind("<Button-1>", lambda e, n=name: self._drag_press(e, n), add="+")
            w.bind("<B1-Motion>", lambda e, n=name: self._drag_motion(e, n), add="+")
            w.bind("<ButtonRelease-1>", lambda e, n=name: self._drag_release(e, n), add="+")

        return widgets

    def _copy_value(self, name):
        for r in self.state.results or []:
            if r.get("name") == name:
                # 复制所见即所得的主值:% 行的 remaining 是裸小数甚至 None,
                # 直接复制会静默无反应或贴出 0.27 这种没人看得懂的数
                text = _fmt_main(r)
                if text:
                    self.root.clipboard_clear()
                    self.root.clipboard_append(text)
                    self._flash_copied(name)
                return

    def _card_press(self, card):
        try:
            card.configure(bg=C["card_pressed"])
        except tk.TclError:
            pass

    def _card_release(self, card):
        try:
            card.configure(bg=getattr(card, "_bg", C["card"]))
        except tk.TclError:
            pass

    def _flash_copied(self, name, which="value"):
        """复制成功后把该行标签短暂染成 ok 绿,给个可见反馈。

        只改前景色、不动文本,所以和 _paint_row 的签名去重不打架。
        """
        w = (self._rows.get(name) or {}).get(which)
        if w is None:
            return
        try:
            if which == "value":
                orig = self._value_color(name)
            else:
                orig = C["text"]
            w.config(fg=C["ok"])
            self.root.after(450, lambda: self._restore_fg(w, orig))
        except tk.TclError:
            pass

    @staticmethod
    def _restore_fg(w, orig):
        try:
            w.config(fg=orig)
        except tk.TclError:
            pass

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
                    self._flash_copied(name, "name")
                return

    def _copy_url(self, name):
        for p in self.cfg.get("providers") or []:
            if p.get("name") == name:
                url = p.get("base_url") or ""
                if url:
                    self.root.clipboard_clear()
                    self.root.clipboard_append(url)
                    self._flash_copied(name, "name")
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
            return fn(model_id, base_url, key, provider_name=name)

        save_model_order = self.actions.get("save_model_order")
        def _on_reorder(new_order):
            if save_model_order:
                save_model_order(name, base_url, key, new_order)
        # 单例:先收掉上一个,否则每点一次"模型列表"就叠一层 Toplevel
        prev = getattr(self, "_model_panel", None)
        if prev is not None:
            try:
                if prev.winfo_exists():
                    prev.destroy()
            except tk.TclError:
                pass
        self._model_panel = ModelPanel(self.root, name, models, on_probe=_probe_cb,
                                       on_reorder=_on_reorder,
                                       on_after_reorder=lambda: self.actions["refresh_now"]())

    def _value_color(self, name):
        """当前行的数值应该是什么颜色(按等级实算,不缓存)。"""
        for r in (self.state.results or []):
            if r.get("name") == name:
                return _row_color(r)[0]
        return C["dim"]

    def _flash_value(self, name):
        """悬停:提亮数值。离开时必须回到等级色,不能写死 dim。"""
        w = self._rows.get(name)
        if not w:
            return
        try:
            w["value"].config(fg=C["ok"])
        except tk.TclError:
            pass

    def _unflash_value(self, name):
        w = self._rows.get(name)
        if not w:
            return
        try:
            w["value"].config(fg=self._value_color(name))
        except tk.TclError:
            pass

    def _paint_row(self, widgets, r):
        color, ratio_val = _row_color(r)
        level = r.get("level", "unknown")
        name = r.get("name")
        # 滑条动画中的行跳过签名去重:否则目标值不变时 key 相同,
        # 每帧都被 early-return,动画永远收敛不了
        animating = name in self._anim_rows
        key = (r.get("name"), r.get("level"), r.get("remaining"),
               r.get("total"), r.get("pct"), r.get("detail"), r.get("error"),
               r.get("updated_at"), ratio_val, r.get("used_today"),
               r.get("used"), r.get("paused"), r.get("unconfigured"))
        if not animating and \
                self._last_paint.get(widgets["provider_name"]) == key:
            return
        self._last_paint[widgets["provider_name"]] = key

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

        bar = widgets["bar"]
        rect = widgets["rect"]
        if bar is None or rect is None:
            return
        # 条的长度与颜色必须来自同一个量。之前长度用 pct(=剩余),
        # 颜色用 ratio(=已消耗),于是剩 30% 的账号会画成一条 30% 宽的
        # 橙色条(按"已消耗 70%"取色),且与折叠条带画的 70% 互相矛盾。
        # 现在统一用"已消耗占比":越长越红,和颜色、与条带一致。
        # ratio 为 None(未配置/出错/拿不到数)时不画满格——满格灰条会被
        # 误读成"额度充足"。
        frac = 0.0 if ratio_val is None else max(0.0, min(1.0, ratio_val))
        widgets["_bar_frac"] = frac
        widgets["_bar_color"] = color
        # 缓动:条从当前显示值滑向目标,而不是瞬移。颜色(渐变插值)
        # 不跟随缓动、每帧直接用目标色:渐变色差肉眼几乎不可辨,
        # 而位置跳变很扎眼
        disp = widgets.get("_anim_frac")
        if disp is None:
            disp = frac
        else:
            diff = frac - disp
            disp = frac if abs(diff) <= 0.0025 else disp + diff * 0.35
        if disp != frac:
            self._anim_rows.add(name)
        else:
            self._anim_rows.discard(name)
        widgets["_anim_frac"] = disp
        try:
            width = bar.winfo_width()
        except tk.TclError:
            width = 0
        if width >= 2:
            _draw_capsule(bar, widgets, width, disp, color)
