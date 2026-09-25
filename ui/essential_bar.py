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

from ui.theme import PALETTE, Layout, usage_color, TEXT_TK, TEXT_DIM_TK, on_theme_change
from ui.fonts import fonts


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
    """返回单行消耗比 0..1,与 panel._usage_ratio 同语义。"""
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
        pct = row.get("pct")
        return _fmt_pct(pct), ""
    rem = row.get("remaining")
    if rem is not None:
        return f"{prefix}{rem:,.2f}{unit}", ""
    return "—", "—"


class EssentialBar:
    """240×56 单行总览视图。

    用法:
        bar = EssentialBar(parent, state, cfg, fonts_dict,
                           on_expand=lambda: mac.toggle_mode())
        bar.pack(...)
    """

    W = 240
    H = 56

    def __init__(self, parent, state, cfg, fonts_dict, on_expand=None,
                 on_pin_toggle=None):
        self.parent = parent
        self.state = state
        self.cfg = cfg or {}
        self.fonts_dict = fonts_dict
        self.on_expand = on_expand
        self.on_pin_toggle = on_pin_toggle

        self._sig = None
        self._last_paint = None

        self.frame = tk.Frame(parent, bg=PALETTE.BG,
                              width=self.W, height=self.H,
                              cursor="hand2")
        self.frame.pack_propagate(False)

        top = tk.Frame(self.frame, bg=PALETTE.BG)
        top.pack(fill="x", padx=Layout.PAD_X, pady=(8, 0))

        self.value_lbl = tk.Label(
            top, text="—",
            font=(fonts_dict["mono"], 13, "bold"),
            fg=TEXT_TK, bg=PALETTE.BG, anchor="w",
        )
        self.value_lbl.pack(side="left")

        self.sub_lbl = tk.Label(
            top, text="",
            font=(fonts_dict["ui"], 10),
            fg=TEXT_DIM_TK, bg=PALETTE.BG, anchor="w",
        )
        self.sub_lbl.pack(side="left", padx=(6, 0))

        self.pct_lbl = tk.Label(
            top, text="",
            font=(fonts_dict["ui"], 10, "bold"),
            fg=TEXT_TK, bg=PALETTE.BG, anchor="e",
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

        self.bar_rect = self.bar_canvas.create_rectangle(
            0, 0, 0, Layout.BAR_HEIGHT, outline="", fill=PALETTE.GREEN,
        )
        self.bar_canvas.bind(
            "<Configure>",
            lambda e: self._on_bar_configure(e),
        )

        self.countdown_lbl = tk.Label(
            bar_holder, text="",
            font=(fonts_dict["ui"], 9),
            fg=TEXT_DIM_TK, bg=PALETTE.BG, anchor="e",
        )
        self.countdown_lbl.pack(side="right", padx=(6, 0))

        self._last_bar_width = 0
        self._last_bar_color = PALETTE.GREEN
        self._last_bar_frac = 0.0

        self.frame.bind("<Button-1>", self._on_click)
        for w in (top, self.value_lbl, self.sub_lbl, self.pct_lbl,
                  bar_holder, self.bar_canvas, self.countdown_lbl):
            w.bind("<Button-1>", self._on_click, add="+")

        on_theme_change(self.refresh_palette)
        self._tick()

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
                        w.configure(fg=TEXT_DIM_TK)
                    else:
                        w.configure(fg=TEXT_TK)
                except tk.TclError:
                    pass
            self.bar_canvas.configure(bg=PALETTE.BAR_BG)
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
        try:
            x2 = int(self._last_bar_width * self._last_bar_frac)
            self.bar_canvas.coords(self.bar_rect, 0, 0, x2, Layout.BAR_HEIGHT)
            self.bar_canvas.itemconfig(self.bar_rect, fill=self._last_bar_color)
        except tk.TclError:
            pass

    def _tick(self):
        try:
            if self.frame.winfo_exists():
                self._update()
                self.frame.after(1000, self._tick)
        except tk.TclError:
            pass

    def _update(self):
        results = list(self.state.results or [])
        sig = tuple((r.get("name"), r.get("level"),
                     r.get("remaining"), r.get("total"),
                     r.get("used_today"), r.get("pct"),
                     r.get("reset_at")) for r in results)
        if sig == self._sig:
            self._update_countdown(results)
            return
        self._sig = sig

        worst, ratio = _worst(results)
        color = usage_color(ratio) if ratio is not None else PALETTE.GREY

        main, sub = _main_value(worst)
        pct_text = ""
        if worst is not None:
            pct = worst.get("pct")
            if isinstance(pct, (int, float)):
                pct_text = _fmt_pct(pct)
        self.value_lbl.config(text=main, fg=color)
        self.sub_lbl.config(text=sub, fg=TEXT_DIM_TK)
        self.pct_lbl.config(text=pct_text, fg=color)

        self._last_bar_color = color
        self._last_bar_frac = ratio if ratio is not None else 0.0
        self._redraw_bar()

        self._last_countdown_results = results
        self._update_countdown(results)

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
