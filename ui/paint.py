"""绘制原语与可复用控件。

极简工具风的视觉规则全部收敛到这里,业务模块不再各画各的:

- 圆角矩形只有 rounded_points / draw_capsule 一个来源,全仓库不再手写点集
- 分割线只有 hairline 一个来源(1px PALETTE.DIVIDER)
- hover 只有 bind_hover_bg / FlatButton 一个来源,消除"外亮内暗"割裂环
- 输入框焦点环只有 FocusEntry 一个来源
- 窗口图标只有 make_icon / apply_icon 一个来源

配色一律走 ui.theme.PALETTE,本模块不持有任何颜色字面量;
需要半透明时用 theme.to_tk_color_blended 预混合到 PALETTE.BG。
"""

import math
import tkinter as tk

from ui.theme import (PALETTE, Layout, to_tk_color, to_tk_color_blended,
                      blend)


# 填充面上的文字要能读:实心按钮前景一律用窗口底色压在上面,
# 而不是 TEXT(深色按钮上白字、浅色按钮上黑字才是对的)。
_ON_FILL = to_tk_color(PALETTE.BG)


def rounded_points(x1, y1, x2, y2, r):
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


def capsule_items(canvas, height=None, radius=None):
    """在 canvas 上建一对胶囊图元(轨道 + 填充),返回 (track, rect)。

    两条都建成 state="hidden",由 draw_capsule 按实际占比点亮。
    轨道/填充的 z 序:轨道先建、填充后建,填充自然压在轨道上。
    """
    h = height if height is not None else Layout.ROW_BAR_HEIGHT
    r = radius if radius is not None else h / 2.0
    kw = {"outline": "", "width": 0, "smooth": True, "splinesteps": 12}
    track = canvas.create_polygon(0, 0, 0, 0, **kw)
    rect = canvas.create_polygon(0, 0, 0, 0, **dict(kw, state="hidden"))
    return track, rect


def draw_capsule(canvas, track, rect, width, frac, color,
                 track_color=None, height=None):
    """画胶囊轨道与填充。

    - 轨道永远画满 0..width,颜色 track_color(默认 PALETTE.BAR_BG)
    - 填充 0..int(width*frac);不足一个圆头直径(2r)时不画——
      12 点点集在 x2 < 2r 时会出现反向坐标,画出来是畸形,
      与其失真不如隐藏(不足 12px ≈ 用量 4%,肉眼本来不可辨)
    - frac 为 None(未知占比)等同 0,绝不画满格
    """
    if canvas is None or rect is None:
        return
    h = height if height is not None else Layout.ROW_BAR_HEIGHT
    r = h / 2.0
    try:
        if track is not None:
            canvas.coords(track, *rounded_points(0, 0, width, h, r))
            canvas.itemconfig(
                track,
                fill=track_color if track_color is not None
                else to_tk_color(PALETTE.BAR_BG),
                state="normal")
        x2 = int(width * max(0.0, min(1.0, frac or 0.0)))
        if x2 < 2 * r:
            canvas.itemconfig(rect, state="hidden")
            return
        canvas.coords(rect, *rounded_points(0, 0, x2, h, r))
        canvas.itemconfig(rect, fill=color, state="normal")
    except tk.TclError:
        pass


def hairline(parent, color=None, side="bottom"):
    """1px 分割线 Frame。

    极简风里行与行之间靠它分隔,而不是每行一个圆角底色块。
    color 默认 PALETTE.DIVIDER(8% alpha),不要用 TEXT_DIM——
    那是 50%,在 280px 宽的列表里比整行文字还抢眼。
    """
    return tk.Frame(parent, height=1, bd=0, highlightthickness=0,
                    bg=color if color is not None
                    else to_tk_color_blended(PALETTE.DIVIDER))


def bind_hover_bg(widgets, enter_bg, leave_bg):
    """把一串 widget 绑成同一个 hover 事件源,并让底色整链同步。

    之前每行只把 hover 绑在 card/top/name_lbl 上、且只改 card 的 bg:
    鼠标停在 detail 或进度条上零响应,停在 name 上时卡片外圈变亮而
    内部子 Frame 仍是原色,看起来是一圈亮边而不是整块卡亮起。

    enter_bg / leave_bg 收字符串或零参可调用对象——主题切换会原地
    改写色板字典,绑定期捕获到的字符串会变陈旧,必须延迟到事件时再取。
    """
    chain = [w for w in widgets if w is not None]
    if not chain:
        return

    def _resolve(v):
        return v() if callable(v) else v

    def _apply(color):
        for w in chain:
            try:
                w.configure(bg=color)
            except tk.TclError:
                pass

    def _on_enter(_e=None):
        _apply(_resolve(enter_bg))

    def _on_leave(_e=None):
        _apply(_resolve(leave_bg))

    for w in chain:
        w.bind("<Enter>", _on_enter, add="+")
        w.bind("<Leave>", _on_leave, add="+")


def bind_press_bg(widgets, press_bg, release_bg):
    """按下态:按下时压一档,松开恢复。与 bind_hover_bg 同样整链同步。"""
    chain = [w for w in widgets if w is not None]
    if not chain:
        return

    def _resolve(v):
        return v() if callable(v) else v

    def _apply(color):
        for w in chain:
            try:
                w.configure(bg=color)
            except tk.TclError:
                pass

    def _on_press(_e=None):
        _apply(_resolve(press_bg))

    def _on_release(_e=None):
        _apply(_resolve(release_bg))

    for w in chain:
        w.bind("<ButtonPress-1>", _on_press, add="+")
        w.bind("<ButtonRelease-1>", _on_release, add="+")


# ---- 列表滚轮 ------------------------------------------------------
#
# Canvas 里的子控件不继承父控件的 bindtags,所以想在"悬停在行上"时也能
# 滚列表,老实现用的是 bind_all("<MouseWheel>")。它有两个问题:
#   1) unbind_all(sequence) 会清掉 "all" tag 上该序列的**全部**绑定,
#      包括别的对话框刚挂上去的 → "面板 → 设置列表 → 移出"之后面板
#      滚轮就没了
#   2) 想只摘自己那一个,得写 unbind_all(sequence, funcid),而 tkinter
#      的 unbind_all 只接受一个参数 → 鼠标一移出列表就 TypeError,
#      绑定还留在 all tag 上,后面所有对话框都被面板抢滚轮
#
# 正确解法:给子树挂一个专属 bindtag,取消时把这个 tag 从 bindtags 摘掉。


def wheel_tag(root):
    """root 的专属滚轮 bindtag 名。同一个 root 重复调用返回同一个 tag。"""
    return f"AgentEyeWheel{id(root)}"


def tag_subtree(widget, tag):
    """把 tag 追加到 widget 及整棵子树的 bindtags 末尾。

    行是动态重建的,重建完必须重新打标,否则新行的 bindtags 里没有这个
    tag,悬停在新行上滚不动。
    """
    try:
        tags = list(widget.bindtags())
        if tag not in tags:
            widget.bindtags(tuple(tags) + (tag,))
    except tk.TclError:
        return
    for child in widget.winfo_children():
        tag_subtree(child, tag)


def untag_subtree(widget, tag):
    """把 tag 从 widget 及整棵子树的 bindtags 里摘掉。"""
    try:
        tags = tuple(t for t in widget.bindtags() if t != tag)
        widget.bindtags(tags)
    except tk.TclError:
        return
    for child in widget.winfo_children():
        untag_subtree(child, tag)


def bind_wheel_tree(root, callback, sequence="<MouseWheel>"):
    """给 root 及其整棵子树绑滚轮,返回解绑函数。

    绑完请在重建子节点后调用 tag_subtree(root, wheel_tag(root))。
    """
    tag = wheel_tag(root)

    def _on_wheel(event):
        try:
            callback(event)
        except tk.TclError:
            pass

    try:
        root.bind_class(tag, sequence, _on_wheel)
    except tk.TclError:
        return lambda: None
    tag_subtree(root, tag)

    def _unbind():
        try:
            untag_subtree(root, tag)
        except tk.TclError:
            pass
        try:
            root.tk.call("bind", tag, sequence, "")
        except tk.TclError:
            pass

    return _unbind


def _variant_colors(variant):
    """返回 (rest, hover, press, fg) 四元组,全部现取不缓存。"""
    if variant == "solid":
        base = to_tk_color(PALETTE.BLUE)
        return (base,
                blend(base, "#FFFFFF", 0.16),
                blend(base, "#000000", 0.12),
                _ON_FILL)
    if variant == "danger":
        base = to_tk_color(PALETTE.RED)
        return (base,
                blend(base, "#FFFFFF", 0.16),
                blend(base, "#000000", 0.12),
                _ON_FILL)
    if variant == "chip":
        # chip:静止就有一层填充,像一枚标签。给"快速选择""探测"这类
        # 需要读得出是控件、但不该和主操作抢注意力的按钮用。
        return (to_tk_color(PALETTE.CARD),
                to_tk_color(PALETTE.CARD_HOVER),
                to_tk_color(PALETTE.CARD_PRESSED),
                to_tk_color(PALETTE.TEXT))
    # ghost:静止时透明(与窗口同底),hover 才浮出填充
    return (to_tk_color(PALETTE.BG),
            to_tk_color(PALETTE.CARD_HOVER),
            to_tk_color(PALETTE.CARD_PRESSED),
            to_tk_color(PALETTE.TEXT))


class FlatButton(tk.Button):
    """极简工具风按钮。

    tk.Button 默认 bd=2,relief="flat" 下这两像素被吃掉变成一圈内缩空隙,
    按钮看上去比周围控件小一圈;Windows 默认 activebackground 是系统灰蓝,
    深色主题下按下会闪一下不属于本配色体系的颜色。这里统一 bd=0 并自管
    hover / press 三态,顺带把 borderwidth / highlight 全清掉。

    variant:
      "ghost"  静止透明、hover 填 CARD_HOVER —— 次要操作、列表行内按钮
      "chip"   静止填 CARD —— 预设标签、探测这类"要读得出是控件"的按钮
      "solid"  始终填强调色 —— 主操作(保存)
      "danger" 始终填 RED —— 破坏性操作(删除)

    disabled 由 configure 拦截后处理:Tk 只灰文字不灰底色,禁用态的主
    按钮仍是一整块强调蓝,读起来像"可点但点不动"。

    fg 缺省由 variant 决定;显式传了则以传入值为准,主题切换时重算。
    """

    def __init__(self, parent, variant="ghost", on_click=None, **kw):
        self._variant = variant
        self._custom_fg = kw.pop("fg", None)
        self._custom_bg = kw.pop("bg", None)
        rest, hover, press, fg = _variant_colors(variant)
        kw.setdefault("bd", 0)
        kw.setdefault("relief", "flat")
        kw.setdefault("highlightthickness", 0)
        kw.setdefault("borderwidth", 0)
        kw.setdefault("padx", 12)
        kw.setdefault("pady", 5)
        kw.setdefault("cursor", "hand2")
        kw.setdefault("bg", self._custom_bg or rest)
        kw.setdefault("activebackground", hover)
        kw.setdefault("fg", self._custom_fg or fg)
        kw.setdefault("activeforeground", self._custom_fg or fg)
        kw.setdefault("disabledforeground", to_tk_color_blended(
            PALETTE.TEXT_DISABLED))
        if on_click is not None:
            kw["command"] = on_click
        super().__init__(parent, **kw)
        self._rest_bg = self._custom_bg or rest
        self._hover_color = _variant_colors(variant)[1]
        self._disabled = False
        self.bind("<Enter>", lambda _e: self._set_bg(self._hover_color), add="+")
        self.bind("<Leave>", lambda _e: self._set_bg(self._rest_bg), add="+")

    def _set_bg(self, color):
        try:
            self.configure(bg=color, activebackground=color)
        except tk.TclError:
            pass

    def configure(self, cnf=None, **kw):
        """拦截 configure,让 state 的变化立刻反映到配色上。

        Tk 的 disabled 只把**文字**灰掉,底色照旧 —— 禁用态的主按钮仍是
        一整块强调蓝,读起来像"可点但点不动"。这里在 configure 之后按
        state 重刷:禁用 = 退回窗口底色 + 禁用文字色,和 ghost 一样安静。
        """
        result = super().configure(cnf, **kw)
        try:
            disabled = str(self["state"]) == "disabled"
        except tk.TclError:
            disabled = False
        if disabled != self._disabled:
            self._disabled = disabled
            self.refresh_palette()
        return result

    config = configure

    def refresh_palette(self):
        """主题切换时重算四态配色,并处理禁用态。"""
        rest, hover, press, fg = _variant_colors(self._variant)
        self._rest_bg = self._custom_bg or rest
        self._hover_color = hover
        fg = self._custom_fg or fg
        disabled_fg = to_tk_color_blended(PALETTE.TEXT_DISABLED)
        if self._disabled:
            # 禁用:退回窗口底色,不再有可点暗示
            try:
                self.configure(bg=to_tk_color(PALETTE.BG),
                               activebackground=to_tk_color(PALETTE.BG),
                               fg=disabled_fg, activeforeground=disabled_fg,
                               disabledforeground=disabled_fg)
            except tk.TclError:
                pass
            return
        try:
            self.configure(bg=self._rest_bg, activebackground=hover,
                           fg=fg, activeforeground=fg,
                           disabledforeground=disabled_fg)
        except tk.TclError:
            pass


class FocusEntry(tk.Entry):
    """带 1px 焦点环的输入框。

    Windows 默认 Entry 有 1px 系统边框 + 1px 系统焦点高亮:深色主题下
    常态边框几乎看不见,聚焦时的环是系统蓝灰而不是主题强调蓝,和整体
    配色脱节。这里统一成 常态 1px CARD_HOVER / 聚焦 1px BLUE。

    注意 tk.Entry 没有 padx/pady 选项(那是 Text/Button 的),框内留白只能
   靠 bd + highlightthickness;真要更多内边距得套一层 Frame。
    """

    def __init__(self, parent, **kw):
        kw.setdefault("bd", 0)
        kw.setdefault("relief", "flat")
        kw.setdefault("borderwidth", 0)
        kw.setdefault("highlightthickness", 1)
        kw.setdefault("highlightbackground", to_tk_color(PALETTE.CARD_HOVER))
        kw.setdefault("highlightcolor", to_tk_color(PALETTE.BLUE))
        kw.setdefault("bg", to_tk_color(PALETTE.CARD))
        kw.setdefault("fg", to_tk_color(PALETTE.TEXT))
        kw.setdefault("disabledforeground", to_tk_color_blended(
            PALETTE.TEXT_DISABLED))
        kw.setdefault("insertbackground", to_tk_color(PALETTE.TEXT))
        kw.setdefault("insertwidth", 1)
        super().__init__(parent, **kw)
        self.bind("<FocusIn>", self._set_ring, add="+")
        self.bind("<FocusOut>", self._set_ring, add="+")

    def _set_ring(self, _event=None):
        """常态环 = CARD_HOVER,聚焦环 = BLUE。

        highlightcolor 由 Tk 自己按焦点状态切换,所以这里把两个颜色都
        写一遍就行,不需要按事件分支。
        """
        try:
            self.configure(highlightbackground=to_tk_color(PALETTE.CARD_HOVER),
                           highlightcolor=to_tk_color(PALETTE.BLUE))
        except tk.TclError:
            pass

    def refresh_palette(self):
        try:
            self.configure(bg=to_tk_color(PALETTE.CARD),
                           fg=to_tk_color(PALETTE.TEXT),
                           insertbackground=to_tk_color(PALETTE.TEXT),
                           disabledforeground=to_tk_color_blended(
                               PALETTE.TEXT_DISABLED),
                           highlightbackground=to_tk_color(
                               PALETTE.CARD_HOVER),
                           highlightcolor=to_tk_color(PALETTE.BLUE))
        except tk.TclError:
            pass


class FocusText(tk.Text):
    """与 FocusEntry 同款焦点环的多行输入框(预览区用)。"""

    def __init__(self, parent, **kw):
        kw.setdefault("bd", 0)
        kw.setdefault("relief", "flat")
        kw.setdefault("borderwidth", 0)
        kw.setdefault("highlightthickness", 1)
        kw.setdefault("highlightbackground", to_tk_color(PALETTE.CARD_HOVER))
        kw.setdefault("highlightcolor", to_tk_color(PALETTE.BLUE))
        kw.setdefault("bg", to_tk_color(PALETTE.CARD))
        kw.setdefault("fg", to_tk_color(PALETTE.TEXT))
        kw.setdefault("insertbackground", to_tk_color(PALETTE.TEXT))
        kw.setdefault("insertwidth", 1)
        kw.setdefault("padx", 8)
        kw.setdefault("pady", 6)
        super().__init__(parent, **kw)
        self.bind("<FocusIn>", self._set_ring, add="+")
        self.bind("<FocusOut>", self._set_ring, add="+")

    def _set_ring(self, _event=None):
        try:
            self.configure(highlightbackground=to_tk_color(PALETTE.CARD_HOVER),
                           highlightcolor=to_tk_color(PALETTE.BLUE))
        except tk.TclError:
            pass

    def refresh_palette(self):
        try:
            self.configure(bg=to_tk_color(PALETTE.CARD),
                           fg=to_tk_color(PALETTE.TEXT),
                           insertbackground=to_tk_color(PALETTE.TEXT),
                           highlightbackground=to_tk_color(
                               PALETTE.CARD_HOVER),
                           highlightcolor=to_tk_color(PALETTE.BLUE))
        except tk.TclError:
            pass


class RadioPill(tk.Canvas):
    """自绘单选胶囊,替掉 tk.Radiobutton 的 Windows 原生 3D 指示器。

    原生指示器是一颗带立体描边的圆点,和整窗扁平无边框的观感正面冲突。
    这里画成圆点 + 文字:选中时圆点填强调色并放大一档,hover 时底色浮出
    CARD_HOVER。整块可点,不需要精确点在圆点上。
    """

    DOT = 10
    PAD_X = 8
    PAD_Y = 5

    def __init__(self, parent, variable, value, text, command=None,
                 font=None):
        self._variable = variable
        self._value = value
        self._command = command
        self._text = text
        self._font_spec = font
        self._pad_x = self.PAD_X
        self._pad_y = self.PAD_Y
        super().__init__(parent, highlightthickness=0, bd=0,
                         bg=to_tk_color(PALETTE.BG), cursor="hand2")
        self._dot = None
        self._label = None
        self._hovering = False
        self._build()
        self.bind("<Button-1>", self._on_click, add="+")
        self.bind("<Enter>", self._on_enter, add="+")
        self.bind("<Leave>", self._on_leave, add="+")

    # -- 度量 ---------------------------------------------------------
    def _text_width(self):
        try:
            import tkinter.font as tkfont
            f = (tkfont.Font(self, font=self._font_spec)
                 if self._font_spec else tkfont.nametofont("TkDefaultFont"))
            return int(f.measure(self._text))
        except Exception:
            return max(8, len(self._text) * 8)

    def _width_for(self):
        return (self._pad_x * 2 + self.DOT + 6 + self._text_width())

    def _height_for(self):
        return self.DOT + self._pad_y * 2

    def _build(self):
        self.configure(width=self._width_for(), height=self._height_for())
        bg = to_tk_color(PALETTE.BG)
        cy = self._height_for() / 2.0
        cx = self._pad_x + self.DOT / 2.0
        ring = to_tk_color(PALETTE.DIVIDER)
        fg = to_tk_color(PALETTE.TEXT)
        self._ring = self.create_oval(cx - self.DOT / 2, cy - self.DOT / 2,
                                      cx + self.DOT / 2, cy + self.DOT / 2,
                                      fill="", outline=ring, width=1)
        self._dot = self.create_oval(cx - 2.5, cy - 2.5, cx + 2.5, cy + 2.5,
                                     fill=fg, outline="", state="hidden")
        self._label = self.create_text(
            self._pad_x * 2 + self.DOT + 6, cy, text=self._text,
            anchor="w", fill=fg,
            font=self._font_spec if self._font_spec else "")

    # -- 状态 ---------------------------------------------------------
    def refresh_palette(self):
        bg = to_tk_color(PALETTE.BG)
        fg = to_tk_color(PALETTE.TEXT)
        ring = to_tk_color_blended(PALETTE.DIVIDER)
        try:
            self.configure(bg=bg)
            self.itemconfig(self._ring, outline=ring)
            self.itemconfig(self._label, fill=fg)
            self.itemconfig(self._dot, fill=fg)
        except tk.TclError:
            pass
        self.sync()

    def sync(self):
        """按 variable 当前值刷新选中态。外部改 var 时调用。"""
        try:
            selected = (self._variable.get() == self._value)
        except Exception:
            selected = False
        color = (to_tk_color(PALETTE.BLUE) if selected
                 else to_tk_color_blended(PALETTE.DIVIDER))
        try:
            self.itemconfig(self._dot,
                            fill=color,
                            state="normal" if selected else "hidden")
            self.itemconfig(self._ring, outline=color)
            self.itemconfig(self._label, fill=to_tk_color(PALETTE.TEXT))
        except tk.TclError:
            pass

    def _on_click(self, _event=None):
        try:
            self._variable.set(self._value)
        except Exception:
            pass
        if self._command:
            try:
                self._command()
            except Exception:
                pass
        self.sync()

    def _on_enter(self, _event=None):
        self._hovering = True
        try:
            self.configure(bg=to_tk_color(PALETTE.CARD_HOVER))
            self.itemconfig(self._label, fill=to_tk_color(PALETTE.TEXT))
        except tk.TclError:
            pass

    def _on_leave(self, _event=None):
        self._hovering = False
        try:
            self.configure(bg=to_tk_color(PALETTE.BG))
        except tk.TclError:
            pass
        self.sync()


# ---- 应用图标 ------------------------------------------------------
#
# 无边框窗口(overrideredirect)本身没有任务栏按钮,所以图标只在
# 最小化瞬间(临时摘掉无边框)和 Alt-Tab 的工具窗口列表里可见。
# 仍然要装:缺了它,任何一次"还原成普通窗口"的瞬间都是默认 Tk 图标。
#
# 图案用整数像素拼,不引二进制资源:32px 圆角方块 + 白色横条眼形 + 瞳孔。

_ICON_SIZE = 32
_ICON_RADIUS = 7


def _icon_pixel(x, y, size=_ICON_SIZE, radius=_ICON_RADIUS):
    """返回该像素应填的颜色 hex,或 None 表示透明。

    圆角方块判定走"圆角矩形与圆的差集"判定:四角各取一个中心在
    (r,r) 的圆,像素落在圆内即算在方块里。
    """
    r = radius
    cx = min(max(x, r), size - 1 - r)
    cy = min(max(y, r), size - 1 - r)
    dx, dy = x - cx, y - cy
    return (dx * dx + dy * dy) <= r * r


def make_icon(size=_ICON_SIZE):
    """程序化生成应用图标 tk.PhotoImage。

    只用整数矩形填充,形状按行计算,保证 32px 下边缘不发虚。
    透明像素不 put,Tk 默认留空即透明。
    """
    img = tk.PhotoImage(width=size, height=size)
    accent = to_tk_color(PALETTE.BLUE)

    # 眼形:上下两条对称弧,用逐行半宽近似
    ex_lo, ex_hi = 4, size - 5
    ey_top, ey_bot = 10, 21
    ecy = (ey_top + ey_bot) / 2.0
    ehalf = (ey_bot - ey_top) / 2.0
    ewide = (ex_hi - ex_lo) / 2.0
    ecx = (ex_hi + ex_lo) / 2.0

    for y in range(size):
        for x in range(size):
            if not _icon_pixel(x, y, size):
                continue
            color = accent
            if ey_top <= y <= ey_bot:
                t = (y - ecy) / ehalf
                half = ewide * math.sqrt(max(0.0, 1.0 - t * t))
                if ecx - half <= x <= ecx + half:
                    color = "#FFFFFF"
            img.put(color, to=(x, y, x + 1, y + 1))

    # 瞳孔:中心一枚圆点,用底色压回,眼形才读得出是"眼"
    pr = 3
    pcy = ecy
    for y in range(int(pcy - pr), int(pcy + pr) + 1):
        for x in range(int(ecx - pr), int(ecx + pr) + 1):
            if (x - ecx) ** 2 + (y - pcy) ** 2 <= pr * pr:
                if 0 <= x < size and 0 <= y < size and _icon_pixel(x, y, size):
                    img.put(accent, to=(x, y, x + 1, y + 1))
    return img


_ICON_REF = None


def apply_icon(root):
    """给窗口装上应用图标。返回 PhotoImage,失败返回 None。

    必须持有返回的引用:PhotoImage 是纯 Python 对象,被 GC 回收后
    图标会变成空白(Tk 只保留 Tcl 侧的拷贝)。
    """
    global _ICON_REF
    try:
        img = make_icon()
        root.iconphoto(True, img)
        _ICON_REF = img
        return img
    except tk.TclError:
        return None


__all__ = [
    "rounded_points", "capsule_items", "draw_capsule", "hairline",
    "bind_hover_bg", "bind_press_bg", "FlatButton", "FocusEntry",
    "FocusText", "RadioPill", "make_icon", "apply_icon",
    "wheel_tag", "tag_subtree", "untag_subtree", "bind_wheel_tree",
]
