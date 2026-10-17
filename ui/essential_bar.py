"""Essential 紧凑条带视图(240×56)。

把多个 provider 折算成一行总览:
- 主值:总余额 / 今日已用 / 总百分比中取最严重的一项
- 副值:最高 5h% / 周% / 倒计时
- 单条胶囊进度条:取所有 provider 中最大消耗比

点击条带任一处 → 触发 on_expand 回调,M2 在 MacWindow 里切到 standard。

数据源:与 Panel 相同的 self.state.results,签名一致,
关键字段 unit / remaining / total / used_today / pct / detail / reset_at / level。
"""

import time
import tkinter as tk
import weakref

from ui.theme import (PALETTE, Layout, Typography, usage_color,
                      bind_theme_listener, to_tk_color, to_tk_color_blended)
from ui.fonts import fonts, pick_ui_family
from ui.paint import (capsule_items, draw_capsule, bind_hover_bg,
                      bind_press_bg)
from ui.panel import _usage_ratio


def _font(fonts_dict, key, fallback_size, bold=False):
    """从 fonts_dict 取字号规格,缺键退回本模块自建的阶梯。

    调用方传的字典不一定带全 Typography 的每个键(测试里就只给
    ui/mono/title 三个),缺键直接 KeyError 会让 EssentialBar 整个建不起来,
    而这条带的构造在窗口初始化路径上,炸在这里等于整个应用起不来。

    fonts() 里 "ui"/"mono" 两项只是 family 字符串(不是 (family,size)
    元组),所以取到字符串时要把 fallback_size 补上,否则等于没指定字号。
    """
    spec = (fonts_dict or {}).get(key)
    if isinstance(spec, (tuple, list)) and spec:
        return tuple(spec)
    family = spec if isinstance(spec, str) else (fonts_dict or {}).get("ui")
    if not isinstance(family, str):
        family = pick_ui_family()
    return (family, fallback_size, "bold") if bold else (family, fallback_size)

# 活着且还在跑 1Hz 定时器的 EssentialBar。测试之间由 conftest 统一
# stop(),生产代码不需要读它。
_LIVE_BARS = weakref.WeakSet()


def _fmt_money(unit, value):
    if value is None:
        return "-"
    try:
        return f"{unit}{value:,.2f}"
    except (TypeError, ValueError):
        return "-"


def _short_countdown(sec):
    """比 Panel._fmt_countdown 更紧凑:只给 h+m 组合,满 1 天给 d+h。"""
    sec = max(0, int(sec))
    if sec >= 86400:
        d = sec // 86400
        h = (sec % 86400) // 3600
        return f"{d}d{h}h"
    h = sec // 3600
    m = (sec % 3600) // 60
    if h:
        return f"{h}h{m:02d}m"
    return f"{m}m"


def _row_ratio(result):
    """返回单行消耗比 0..1。

    委托 panel._usage_ratio,两份视图共用同一套口径。
    之前这里有一份手工拷贝,panel 删掉 level 假值后两边会漂移,
    折叠态与展开态会对同一份数据画出不同的胶囊。
    """
    return _usage_ratio(result)


def _worst(results):
    """从 results 挑出 worst-row + worst_ratio。

    worst = 消耗比最大的有效行;若全 None,返回 (None, None)。
    同时把 5h% / 周% / 倒计时合并成"最严重那一项"。
    """
    worst_ratio = None
    worst_row = None
    for r in results:
        if r.get("unconfigured") or r.get("error"):
            continue
        ratio = _row_ratio(r)
        if ratio is None:
            continue
        if worst_ratio is None or ratio > worst_ratio:
            worst_ratio = ratio
            worst_row = r
    return worst_row, worst_ratio


def _main_value(row):
    """主值文案:金额行 → '¥X / ¥Y' 或 '今日 ¥X / ¥Y';百分比行 → 'X%'。"""
    if row is None:
        return "—", "—"
    if row.get("paused"):
        return "已暂停", ""
    unit = row.get("unit") or ""
    prefix = "≈" if row.get("is_estimate") else ""
    if unit in ("$", "¥"):
        total = row.get("total")
        used_today = row.get("used_today")
        if isinstance(used_today, (int, float)):
            today = f"{prefix}{unit}{used_today:,.2f}"
            if total:
                return today, f"{unit}{total:,.2f}"
            return today, ""
        rem = row.get("remaining")
        if rem is not None and total:
            return f"{prefix}{unit}{rem:,.2f}", f"{unit}{total:,.2f}"
        if rem is not None:
            return f"{prefix}{unit}{rem:,.2f}", ""
        return "—", "—"
    if unit == "%":
        # 与 Panel._fmt_main 同口径:pct 字段存的是"剩余",主值写
        # "已用";条带颜色也按已消耗取色,两边方向一致
        pct = row.get("pct")
        if isinstance(pct, (int, float)) and not isinstance(pct, bool):
            used = max(0, min(100, 100.0 - float(pct)))
            return f"已用 {used:.0f}%", ""
        return "-", ""
    rem = row.get("remaining")
    if rem is not None:
        return f"{prefix}{rem:,.2f}{unit}", ""
    return "—", "—"


def _value_color(ratio, level):
    """主值的前景色。

    正常档返回 TEXT 而不是 ok 绿:折叠态整条带子只有这一个数字,把它染成
    高饱和绿会像一盏警示灯——而"额度还够"恰恰是不需要提醒的状态。
    warn / critical 才上色,让有限的颜色预算全花在异常上。
    """
    if ratio is None:
        return to_tk_color(PALETTE.TEXT)
    r = max(0.0, min(1.0, ratio))
    if r <= 0.5:
        return to_tk_color(PALETTE.WARN if r > 0.2 else PALETTE.TEXT)
    return to_tk_color(PALETTE.CRITICAL)


class EssentialBar:
    """240×56 单行总览视图。

    用法:
        bar = EssentialBar(parent, state, cfg, fonts_dict,
                           on_expand=lambda: mac.toggle_mode(),
                           on_open_models=lambda name: open_model_panel(name))

    parent 由 MacWindow 负责 pack/unpack,本类会把自己 pack 进 parent。
    """

    W = Layout.ESSENTIAL_W
    H = Layout.ESSENTIAL_H

    def __init__(self, parent, state, cfg, fonts_dict, on_expand=None,
                 on_pin_toggle=None, on_open_models=None):
        self.parent = parent
        self.state = state
        self.cfg = cfg or {}
        self.fonts_dict = fonts_dict
        self.on_expand = on_expand
        self.on_pin_toggle = on_pin_toggle
        self.on_open_models = on_open_models
        self._current_worst_name = None

        self._sig = None
        self._last_paint = None
        self._tick_after_id = None
        _LIVE_BARS.add(self)

        self.frame = tk.Frame(parent, bg=to_tk_color(PALETTE.BG),
                              width=self.W, height=self.H,
                              cursor="hand2")
        self.frame.pack_propagate(False)
        # 自己 pack 进 parent:MacWindow 切模式时 pack 的是父 slot
        # (essential_slot)而不是视图根,把视图根 pack 进一个没被 pack 的
        # slot 会让它永远不 mapped——折叠模式整个是空窗。
        self.frame.pack(fill="both", expand=True)

        top = tk.Frame(self.frame, bg=to_tk_color(PALETTE.BG))
        top.pack(fill="x", padx=Layout.PAD_X, pady=(6, 0))

        self.value_lbl = tk.Label(
            top, text="—",
            font=_font(fonts_dict, "num", Typography.NUM_SIZE),
            fg=to_tk_color(PALETTE.TEXT), bg=to_tk_color(PALETTE.BG),
            anchor="w",
        )
        self.value_lbl.pack(side="left")

        self.sub_lbl = tk.Label(
            top, text="",
            font=_font(fonts_dict, "detail", Typography.DETAIL_SIZE),
            fg=to_tk_color_blended(PALETTE.TEXT_DIM),
            bg=to_tk_color(PALETTE.BG), anchor="w",
        )
        self.sub_lbl.pack(side="left", padx=(6, 0))

        self._chevron = tk.Label(
            top, text="›",
            font=_font(fonts_dict, "num", Typography.NUM_SIZE, bold=True),
            fg=to_tk_color_blended(PALETTE.TEXT_DIM),
            bg=to_tk_color(PALETTE.BG), cursor="hand2",
        )
        self._chevron.pack(side="right")
        self._chevron.bind("<Enter>", lambda e: self._chevron.config(fg=to_tk_color(PALETTE.TEXT)))
        self._chevron.bind("<Leave>",
                           lambda e: self._chevron.config(fg=to_tk_color_blended(PALETTE.TEXT_DIM)))
        self._chevron.bind("<Button-1>", self._on_chevron_click, add="+")

        bar_holder = tk.Frame(self.frame, bg=to_tk_color(PALETTE.BG))
        bar_holder.pack(fill="x", padx=Layout.PAD_X, pady=(4, 0))

        self.bar_canvas = tk.Canvas(
            bar_holder, height=Layout.BAR_HEIGHT,
            bg=to_tk_color(PALETTE.BAR_BG), highlightthickness=0, bd=0,
        )
        self.bar_canvas.pack(side="left", fill="x", expand=True)

        self.bar_track, self.bar_rect = capsule_items(
            self.bar_canvas, height=Layout.BAR_HEIGHT)
        self.bar_canvas.bind(
            "<Configure>",
            lambda e: self._on_bar_configure(e),
        )

        self.countdown_lbl = tk.Label(
            bar_holder, text="",
            # 倒计时是纯 ASCII,用等宽:三个字段刷新时数字不会左右跳
            font=_font(fonts_dict, "mono", Typography.BADGE_SIZE),
            fg=to_tk_color_blended(PALETTE.TEXT_DIM),
            bg=to_tk_color(PALETTE.BG), anchor="e",
        )
        self.countdown_lbl.pack(side="right", padx=(6, 0))

        self._last_bar_width = 0
        self._last_bar_color = to_tk_color(PALETTE.GREY)
        self._last_bar_frac = 0.0
        self._disp_frac = None
        self._bar_target = 0.0
        self._animating = False

        self.frame.bind("<Button-1>", self._on_click)
        chain = [self.frame, top, self.value_lbl, self.sub_lbl,
                 self._chevron, bar_holder, self.bar_canvas,
                 self.countdown_lbl]
        for w in chain:
            w.bind("<Button-1>", self._on_click, add="+")
        # 整条带子可点却零 hover 反馈:光标是手型,按下去也不知道按到了没有。
        # bar_canvas 也在链里,底色跟着一起变,不会留一条异色带。
        self._hover_chain = chain
        bind_hover_bg(chain, lambda: to_tk_color(PALETTE.CARD_HOVER),
                      lambda: to_tk_color(PALETTE.BG))
        bind_press_bg(chain, lambda: to_tk_color(PALETTE.CARD_PRESSED),
                      lambda: to_tk_color(PALETTE.BG))

        bind_theme_listener(self.frame, self.refresh_palette)
        self._tick()

    def _on_chevron_click(self, _event=None):
        """点击 › 触发 on_open_models(current_worst_name)。"""
        if not self.on_open_models or not self._current_worst_name:
            return
        try:
            self.on_open_models(self._current_worst_name)
        except Exception:
            pass

    def refresh_palette(self, *_args):
        """主题切换时刷新所有 widget 的 bg/fg,以及胶囊轨道色。

        胶囊的轨道/填充是 canvas 图元,configure(bg) 够不到,必须显式
        itemconfig——漏刷就是浅色主题残留深色轨道(AGENTS.md 规则 3)。
        """
        bg = to_tk_color(PALETTE.BG)
        dim = to_tk_color_blended(PALETTE.TEXT_DIM)
        try:
            self.frame.configure(bg=bg)
            for w in self.frame.winfo_children():
                try:
                    w.configure(bg=bg)
                except tk.TclError:
                    pass
            for w in (self.value_lbl, self.sub_lbl, self.countdown_lbl):
                try:
                    w.configure(fg=dim if w is not self.value_lbl
                                else to_tk_color(PALETTE.TEXT), bg=bg)
                except tk.TclError:
                    pass
            try:
                self._chevron.configure(bg=bg, fg=dim)
            except (tk.TclError, AttributeError):
                pass
            track_color = to_tk_color(PALETTE.BAR_BG)
            self.bar_canvas.configure(bg=track_color)
            try:
                self.bar_canvas.itemconfig(self.bar_track, fill=track_color)
            except (tk.TclError, AttributeError):
                pass
        except tk.TclError:
            pass
        # _update 只在签名变化时改主值颜色,所以这里要主动重算一次,
        # 否则切主题后主值停在旧色的等级色上。
        self._sig = None
        self._update()

    def _on_click(self, _event=None):
        if self.on_expand:
            try:
                self.on_expand()
            except Exception:
                pass

    def _on_bar_configure(self, event):
        width = max(0, int(getattr(event, "width", 0)))
        if width < 2:
            return
        self._last_bar_width = width
        self._redraw_bar()

    def _redraw_bar(self):
        if self._last_bar_width < 2:
            return
        draw_capsule(self.bar_canvas, self.bar_track, self.bar_rect,
                     self._last_bar_width, self._last_bar_frac,
                     self._last_bar_color,
                     track_color=to_tk_color(PALETTE.BAR_BG),
                     height=Layout.BAR_HEIGHT)

    def _tick(self):
        self._tick_after_id = None
        try:
            if not self.frame.winfo_exists():
                return
            self._update()
            # 条在缓动动画中 → 33ms 快 tick,收敛后回 1Hz
            delay = 33 if self._animating else 1000
            self._tick_after_id = self.frame.after(delay, self._tick)
        except tk.TclError:
            pass

    def stop(self):
        """停掉 1Hz 定时器。条被移除/销毁前必须调用,否则残留的 after
        回调会在解释器销毁后仍留在队列里,下一个事件循环会打到已销毁
        的解释器上(Windows fatal exception)。"""
        aid, self._tick_after_id = self._tick_after_id, None
        if aid is not None:
            try:
                self.frame.after_cancel(aid)
            except tk.TclError:
                pass

    def _update(self):
        results = list(self.state.results or [])
        sig = tuple((r.get("name"), r.get("level"),
                     r.get("remaining"), r.get("total"),
                     r.get("used_today"), r.get("pct"),
                     r.get("reset_at")) for r in results)
        if sig != self._sig:
            self._sig = sig

            worst, ratio = _worst(results)
            self._current_worst_name = worst.get("name") if worst else None
            color = usage_color(ratio) if ratio is not None else PALETTE.GREY

            main, sub = _main_value(worst)
            # 只留一个百分比:主值已经是「已用 27%」,再在右边挂一个剩余
            # 73% 是同一份数据的另一面,240px 宽里两处读同一个数,只会
            # 让人多看一眼却读不出新信息。剩余量由胶囊条承担。
            self.value_lbl.config(text=main,
                                  fg=_value_color(ratio,
                                                  (worst or {}).get("level")))
            self.sub_lbl.config(text=sub,
                                fg=to_tk_color_blended(PALETTE.TEXT_DIM))

            self._last_bar_color = to_tk_color(color)
            self._bar_target = ratio if ratio is not None else 0.0

        self._update_countdown(results)

        # 条的宽度朝目标缓动:数据跳变时滑过去,不再瞬移;
        # 颜色只在 sig 变化时更新,动画期间保持
        target = getattr(self, "_bar_target", 0.0)
        disp = getattr(self, "_disp_frac", None)
        if disp is None:
            disp = target
        else:
            diff = target - disp
            disp = target if abs(diff) <= 0.0025 else disp + diff * 0.35
        self._disp_frac = disp
        self._animating = disp != target
        self._last_bar_frac = disp
        self._redraw_bar()

    def _update_countdown(self, results):
        if not results:
            self.countdown_lbl.config(text="—")
            return
        nearest = None
        now = time.time()
        for r in results:
            reset_at = r.get("reset_at")
            if isinstance(reset_at, (int, float)) and reset_at > now:
                if nearest is None or reset_at < nearest:
                    nearest = reset_at
        if nearest is None:
            if self.state.fetching:
                self.countdown_lbl.config(text="刷新中…")
            elif self.state.next_fetch:
                left = self.state.next_fetch - now
                self.countdown_lbl.config(text=f"刷新 {_short_countdown(left)}")
            else:
                self.countdown_lbl.config(text="")
        else:
            # 不加 ⏱ 之类的符号前缀:那类字形靠 Segoe UI Symbol 兜底,
            # 换一台机器字形就不一样,倒计时是纯数字,自己就够表意了。
            self.countdown_lbl.config(text=_short_countdown(nearest - now))

    def destroy(self):
        try:
            self.frame.destroy()
        except tk.TclError:
            pass


__all__ = ["EssentialBar"]
