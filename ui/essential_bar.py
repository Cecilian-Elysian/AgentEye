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

from ui.theme import PALETTE, Layout, usage_color, bind_theme_listener, to_tk_color, to_tk_color_blended
from ui.fonts import fonts
from ui.panel import _usage_ratio, _rounded_points

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


def _fmt_pct(value):
    if value is None:
        return "-"
    try:
        return f"{int(round(value))}%"
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


class EssentialBar:
    """240×56 单行总览视图。

    用法:
        bar = EssentialBar(parent, state, cfg, fonts_dict,
                           on_expand=lambda: mac.toggle_mode(),
                           on_open_models=lambda name: open_model_panel(name))
        bar.pack(...)
    """

    W = 240
    H = 56

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

        self.frame = tk.Frame(parent, bg=PALETTE.BG,
                              width=self.W, height=self.H,
                              cursor="hand2")
        self.frame.pack_propagate(False)

        top = tk.Frame(self.frame, bg=PALETTE.BG)
        top.pack(fill="x", padx=Layout.PAD_X, pady=(8, 0))

        self.value_lbl = tk.Label(
            top, text="—",
            font=(fonts_dict["mono"], 13, "bold"),
            fg=to_tk_color(PALETTE.TEXT), bg=PALETTE.BG, anchor="w",
        )
        self.value_lbl.pack(side="left")

        self.sub_lbl = tk.Label(
            top, text="",
            font=(fonts_dict["ui"], 10),
            fg=to_tk_color_blended(PALETTE.TEXT_DIM), bg=PALETTE.BG, anchor="w",
        )
        self.sub_lbl.pack(side="left", padx=(6, 0))

        self._chevron = tk.Label(
            top, text="›",
            font=(fonts_dict["ui"], 14, "bold"),
            fg=to_tk_color_blended(PALETTE.TEXT_DIM), bg=PALETTE.BG, anchor="e", cursor="hand2",
        )
        self._chevron.pack(side="right", padx=(4, 0))
        self._chevron.bind("<Enter>", lambda e: self._chevron.config(fg=to_tk_color(PALETTE.TEXT)))
        self._chevron.bind("<Leave>",
                           lambda e: self._chevron.config(fg=to_tk_color_blended(PALETTE.TEXT_DIM)))
        self._chevron.bind("<Button-1>", self._on_chevron_click, add="+")

        self.pct_lbl = tk.Label(
            top, text="",
            font=(fonts_dict["ui"], 10, "bold"),
            fg=to_tk_color(PALETTE.TEXT), bg=PALETTE.BG, anchor="e",
        )
        self.pct_lbl.pack(side="right")

        bar_holder = tk.Frame(self.frame, bg=PALETTE.BG)
        bar_holder.pack(fill="x", padx=Layout.PAD_X,
                        pady=(6, 0))

        self.bar_canvas = tk.Canvas(
            bar_holder, height=Layout.BAR_HEIGHT,
            bg=PALETTE.BAR_BG, highlightthickness=0, bd=0,
        )
        self.bar_canvas.pack(side="left", fill="x", expand=True)

        # 与展开面板的行内条同款胶囊(12 点圆角),直角矩形版废弃
        poly_kw = {"outline": "", "width": 0, "smooth": True,
                   "splinesteps": 12}
        self.bar_track = self.bar_canvas.create_polygon(0, 0, 0, 0, **poly_kw)
        self.bar_rect = self.bar_canvas.create_polygon(
            0, 0, 0, 0, **dict(poly_kw, state="hidden"))
        self.bar_canvas.bind(
            "<Configure>",
            lambda e: self._on_bar_configure(e),
        )

        self.countdown_lbl = tk.Label(
            bar_holder, text="",
            font=(fonts_dict["ui"], 9),
            fg=to_tk_color_blended(PALETTE.TEXT_DIM), bg=PALETTE.BG, anchor="e",
        )
        self.countdown_lbl.pack(side="right", padx=(6, 0))

        self._last_bar_width = 0
        self._last_bar_color = PALETTE.GREEN
        self._last_bar_frac = 0.0
        self._disp_frac = None
        self._bar_target = 0.0
        self._animating = False

        self.frame.bind("<Button-1>", self._on_click)
        for w in (top, self.value_lbl, self.sub_lbl, self.pct_lbl,
                  bar_holder, self.bar_canvas, self.countdown_lbl):
            w.bind("<Button-1>", self._on_click, add="+")

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
        """主题切换时刷新所有 widget 的 bg/fg。"""
        try:
            bg = PALETTE.BG
            self.frame.configure(bg=bg)
            for w in self.frame.winfo_children():
                try:
                    w.configure(bg=bg)
                except tk.TclError:
                    pass
            for w in (self.value_lbl, self.sub_lbl,
                      self.pct_lbl, self.countdown_lbl):
                try:
                    if w is self.sub_lbl or w is self.countdown_lbl:
                        w.configure(fg=to_tk_color_blended(PALETTE.TEXT_DIM))
                    else:
                        w.configure(fg=to_tk_color(PALETTE.TEXT))
                except tk.TclError:
                    pass
            try:
                self._chevron.configure(bg=bg, fg=to_tk_color_blended(PALETTE.TEXT_DIM))
            except (tk.TclError, AttributeError):
                pass
            self.bar_canvas.configure(bg=PALETTE.BAR_BG)
            try:
                self.bar_canvas.itemconfig(self.bar_track, fill=PALETTE.BAR_BG)
            except (tk.TclError, AttributeError):
                pass
        except tk.TclError:
            pass
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
        h = Layout.BAR_HEIGHT
        r = h / 2.0
        w = self._last_bar_width
        try:
            self.bar_canvas.coords(self.bar_track,
                                   *_rounded_points(0, 0, w, h, r))
            self.bar_canvas.itemconfig(self.bar_track, fill=PALETTE.BAR_BG,
                                       state="normal")
            x2 = int(w * self._last_bar_frac)
            if x2 < 2 * r:
                # 不足一个圆头直径不画,与行内条同一策略
                self.bar_canvas.itemconfig(self.bar_rect, state="hidden")
            else:
                self.bar_canvas.coords(self.bar_rect,
                                       *_rounded_points(0, 0, x2, h, r))
                self.bar_canvas.itemconfig(self.bar_rect,
                                           fill=self._last_bar_color,
                                           state="normal")
        except tk.TclError:
            pass

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
            pct_text = ""
            if worst is not None:
                pct = worst.get("pct")
                if isinstance(pct, (int, float)) and not isinstance(pct, bool):
                    pct_text = _fmt_pct(pct)
            self.value_lbl.config(text=main, fg=color)
            self.sub_lbl.config(text=sub, fg=to_tk_color_blended(PALETTE.TEXT_DIM))
            self.pct_lbl.config(text=pct_text, fg=color)

            self._last_bar_color = color
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
            self.countdown_lbl.config(text=f"⏱ {_short_countdown(nearest - now)}")

    def destroy(self):
        try:
            self.frame.destroy()
        except tk.TclError:
            pass


__all__ = ["EssentialBar"]
