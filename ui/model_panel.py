"""Model 详情弹窗:展示 provider 的模型列表 + 搜索 + 分组 + 试调。"""

import threading
import time
import tkinter as tk

from ui.scrollbar_style import make_dark_scrollbar
from ui.theme import PALETTE, to_tk_color
from ui.mac_toplevel import MacToplevel


class ModelPanel(MacToplevel):
    GROUP_RULES = [
        ("Claude", ("claude",)),
        ("GPT", ("gpt-", "o1", "o3", "o4")),
        ("Gemini", ("gemini",)),
        ("Llama", ("llama",)),
        ("Qwen", ("qwen",)),
        ("DeepSeek", ("deepseek-",)),
        ("GLM", ("glm-",)),
        ("Embedding", ("embedding", "embed")),
        ("Image", ("dall-e", "image", "sdxl", "stable-diffusion")),
        ("Audio", ("whisper", "tts", "audio")),
    ]

    def __init__(self, parent, provider_name, models, on_probe=None,
                 on_reorder=None, on_after_reorder=None):
        super().__init__(
            parent, title=f"{provider_name} · 模型列表",
            on_close=self._on_close,
            show_minimize=True,
            width=440, height=540,
            resizable=True,
        )
        self.transient(parent)

        self.models = list(models or [])
        self.filtered = list(self.models)
        self.on_probe = on_probe
        self.on_reorder = on_reorder
        self.on_after_reorder = on_after_reorder
        self._drag = None

        BG = to_tk_color(PALETTE.CARD)
        FG = to_tk_color(PALETTE.TEXT)
        DIM = to_tk_color(PALETTE.TEXT_DIM)
        BG_FIELD = to_tk_color(PALETTE.BAR_BG)
        BTN_BG = to_tk_color(PALETTE.CARD_HOVER)
        OK = to_tk_color(PALETTE.OK)
        FONT = ("Microsoft YaHei UI", 10)

        top = tk.Frame(self.body, bg=BG)
        top.pack(fill="x", padx=12, pady=(12, 6))
        self.count_var = tk.StringVar(value=f"{len(self.models)} 个模型")
        tk.Label(top, textvariable=self.count_var,
                 bg=BG, fg=DIM, font=FONT).pack(side="left")

        search_frame = tk.Frame(self.body, bg=BG)
        search_frame.pack(fill="x", padx=12)
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *a: self._apply_filter())
        tk.Entry(search_frame, textvariable=self.search_var,
                 bg=BG_FIELD, fg=FG, insertbackground=FG,
                 font=FONT, relief="flat").pack(fill="x")

        calc_frame = tk.Frame(self.body, bg=BG)
        calc_frame.pack(fill="x", padx=12, pady=(4, 0))
        tk.Label(calc_frame, text="估算调用", bg=BG, fg=DIM,
                 font=(FONT, 9)).pack(side="left")
        self.calc_n_var = tk.StringVar(value="100")
        self.calc_n_var.trace_add("write", lambda *a: self._on_calc_change())
        tk.Entry(calc_frame, textvariable=self.calc_n_var, width=6,
                 bg=BG_FIELD, fg=FG, insertbackground=FG,
                 font=(FONT, 9), relief="flat").pack(side="left", padx=(4, 2))
        tk.Label(calc_frame, text="次 (按选定模型)", bg=BG, fg=DIM,
                 font=(FONT, 9)).pack(side="left")
        self.calc_cost_var = tk.StringVar(value="选择模型后查看")
        tk.Label(calc_frame, textvariable=self.calc_cost_var,
                 bg=BG, fg=OK, font=(FONT, 9, "bold")).pack(
            side="right")

        list_frame = tk.Frame(self.body, bg=BG)
        list_frame.pack(fill="both", expand=True, padx=12, pady=8)

        self.canvas = tk.Canvas(list_frame, bg=BG, highlightthickness=0)
        self.scroll = make_dark_scrollbar(list_frame, orient="vertical",
                                          command=self.canvas.yview)
        self.inner = tk.Frame(self.canvas, bg=BG)
        self.inner.bind("<Configure>",
                        lambda e: self.canvas.configure(
                            scrollregion=self.canvas.bbox("all")))
        self._list_window = self.canvas.create_window(
            (0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scroll.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scroll.pack(side="right", fill="y")
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind("<Enter>", self._wheel_enter)
        self.canvas.bind("<Leave>", self._wheel_leave)

        btn_frame = tk.Frame(self.body, bg=BG)
        btn_frame.pack(side="bottom", fill="x", padx=12, pady=8)
        tk.Button(btn_frame, text="关闭", command=self._on_close,
                  bg=BTN_BG, fg=FG, relief="flat", font=FONT,
                  width=10).pack(side="right")

        self.bind("<Escape>", lambda e: self._on_close())
        self.grab_set()
        self.focus_set()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._render()

    def refresh_palette(self):
        try:
            BG = to_tk_color(PALETTE.CARD)
            FG = to_tk_color(PALETTE.TEXT)
            DIM = to_tk_color(PALETTE.TEXT_DIM)
            BG_FIELD = to_tk_color(PALETTE.BAR_BG)
            BTN_BG = to_tk_color(PALETTE.CARD_HOVER)
            OK = to_tk_color(PALETTE.OK)
            try:
                self.body.configure(bg=BG)
            except tk.TclError:
                pass
            for w in self.body.winfo_children():
                self._walk_recolor(w, BG, FG, DIM, BG_FIELD, BTN_BG, OK)
            try:
                self.canvas.configure(bg=BG)
                self.inner.configure(bg=BG)
            except tk.TclError:
                pass
        except tk.TclError:
            pass

    def _walk_recolor(self, w, BG, FG, DIM, BG_FIELD, BTN_BG, OK):
        try:
            cls = w.winfo_class()
            if cls == "Frame":
                cur_bg = str(w.cget("bg") or "")
                if cur_bg.upper() == BG_FIELD.upper() or cur_bg.upper() == "#15151D":
                    w.configure(bg=BG_FIELD)
                else:
                    w.configure(bg=BG)
            elif cls == "Label":
                fg_now = str(w.cget("fg") or "").upper()
                if fg_now == OK.upper():
                    w.configure(fg=OK)
                elif fg_now == DIM.upper():
                    w.configure(fg=DIM)
                else:
                    w.configure(fg=FG)
            elif cls == "Entry":
                w.configure(bg=BG_FIELD, fg=FG, insertbackground=FG)
            elif cls == "Button":
                w.configure(bg=BTN_BG, fg=FG)
        except tk.TclError:
            pass
        for c in w.winfo_children():
            self._walk_recolor(c, BG, FG, DIM, BG_FIELD, BTN_BG, OK)

    def _apply_filter(self):
        q = self.search_var.get().lower().strip()
        if not q:
            self.filtered = list(self.models)
        else:
            self.filtered = [m for m in self.models if q in m.lower()]
        if hasattr(self, "count_var"):
            self.count_var.set(
                f"{len(self.filtered)} / {len(self.models)} 个模型")
        self._render()

    def _group(self, model_id):
        mid = model_id.lower()
        for group, keywords in self.GROUP_RULES:
            if any(k in mid for k in keywords):
                return group
        return "其他"

    def _render(self):
        try:
            scroll_pos = self.canvas.yview()[0]
        except (tk.TclError, AttributeError, IndexError):
            scroll_pos = 0.0

        for w in self.inner.winfo_children():
            w.destroy()

        if not self.filtered:
            tk.Label(self.inner, text="(无匹配)", bg=BG,
                     fg=DIM, font=("Microsoft YaHei UI", 10)).pack(pady=20)
            try:
                self.canvas.update_idletasks()
                self.canvas.yview_moveto(0.0)
            except tk.TclError:
                pass
            return

        grouped = {}
        for m in self.filtered:
            grouped.setdefault(self._group(m), []).append(m)

        BG = to_tk_color(PALETTE.CARD)
        DIM = to_tk_color(PALETTE.TEXT_DIM)
        FG = to_tk_color(PALETTE.TEXT)
        BG_FIELD = to_tk_color(PALETTE.BAR_BG)
        BTN_BG = to_tk_color(PALETTE.CARD_HOVER)
        FONT = ("Microsoft YaHei UI", 9)

        for group_name in ["Claude", "GPT", "Gemini", "Llama", "Qwen",
                           "DeepSeek", "GLM", "Embedding", "Image", "Audio", "其他"]:
            if group_name not in grouped:
                continue
            tk.Label(self.inner, text=group_name, bg=BG, fg=DIM,
                     font=(FONT[0], 9, "bold")).pack(anchor="w", pady=(8, 2))
            for m in grouped[group_name]:
                row = tk.Frame(self.inner, bg=BG_FIELD, cursor="hand2")
                row.pack(fill="x", pady=1)
                row._model_id = m
                tk.Label(row, text=m, bg=BG_FIELD, fg=FG,
                         font=FONT, anchor="w").pack(side="left", padx=8, pady=4)
                if self.on_probe:
                    self.probe_result_var = tk.StringVar(value="")
                    tk.Label(row, textvariable=self.probe_result_var,
                             bg=BG_FIELD, fg=DIM, font=(FONT[0], 8),
                             width=12, anchor="e").pack(
                        side="right", padx=4)
                    tk.Button(row, text="试调", font=(FONT[0], 8),
                              bg=BTN_BG, fg=FG, relief="flat",
                              command=lambda model=m: self._probe(model)).pack(
                        side="right", padx=4, pady=2)
                select_btn = tk.Label(row, text="估算", font=(FONT[0], 8),
                                      bg=BTN_BG, fg=FG, cursor="hand2")
                select_btn.pack(side="right", padx=(0, 4), pady=2)
                self._attach_tooltip(select_btn, "用于上方估算调用成本")
                select_btn.bind("<Button-1>", lambda e, model=m: self._select_model(model))

                for child in row.winfo_children():
                    child.bind("<Button-1>", lambda e, mid=m: self._drag_press(e, mid), add="+")
                    child.bind("<B1-Motion>", lambda e, mid=m: self._drag_motion(e, mid), add="+")
                    child.bind("<ButtonRelease-1>", lambda e, mid=m: self._drag_release(e, mid), add="+")
                row.bind("<Button-1>", lambda e, mid=m: self._drag_press(e, mid), add="+")
                row.bind("<B1-Motion>", lambda e, mid=m: self._drag_motion(e, mid), add="+")
                row.bind("<ButtonRelease-1>", lambda e, mid=m: self._drag_release(e, mid), add="+")

        try:
            self.canvas.update_idletasks()
            self.canvas.yview_moveto(scroll_pos)
        except tk.TclError:
            pass

    def _drag_press(self, event, mid):
        w = event.widget
        if isinstance(w, tk.Button):
            return
        try:
            if w.cget("text") in ("估算", "试调"):
                return
        except (tk.TclError, AttributeError):
            pass
        self._drag = {
            "mid": mid, "start_y": event.y_root,
            "active": False, "target": None, "indicator": None,
        }

    def _drag_motion(self, event, mid):
        d = getattr(self, "_drag", None)
        if not d or d["mid"] != mid:
            return
        if not d["active"]:
            if abs(event.y_root - d["start_y"]) <= 8:
                return
            d["active"] = True
            d["target"] = self._model_target_index(mid, event.y_root)
            self._show_model_indicator()
        if d["active"]:
            new_target = self._model_target_index(mid, event.y_root)
            if new_target != d["target"]:
                d["target"] = new_target
                self._show_model_indicator()

    def _drag_release(self, event, mid):
        d = getattr(self, "_drag", None)
        if not d or d["mid"] != mid:
            return
        if d["active"] and d["target"] is not None:
            self._commit_model_drag(mid, d["target"])
        self._clear_model_indicator()
        self._drag = None

    def _model_target_index(self, exclude_mid, y_root):
        rows = [w for w in self.inner.pack_slaves()
                if isinstance(w, tk.Frame) and hasattr(w, "_model_id")
                and w._model_id != exclude_mid]
        for i, w in enumerate(rows):
            try:
                top = w.winfo_rooty()
            except tk.TclError:
                continue
            mid_y = top + w.winfo_height() / 2
            if y_root < mid_y:
                return i
        return len(rows)

    def _show_model_indicator(self):
        self._clear_model_indicator()
        d = getattr(self, "_drag", None)
        if not d:
            return
        rows = [w for w in self.inner.pack_slaves()
                if isinstance(w, tk.Frame) and hasattr(w, "_model_id")
                and w._model_id != d["mid"]]
        indicator = tk.Frame(self.inner, height=2, bg="#ff5d5d")
        d["indicator"] = indicator
        idx = d["target"]
        if idx < len(rows):
            indicator.pack(fill="x", pady=0, before=rows[idx])
        else:
            indicator.pack(fill="x", pady=0)

    def _clear_model_indicator(self):
        d = getattr(self, "_drag", None)
        if d and d.get("indicator"):
            try:
                d["indicator"].destroy()
            except tk.TclError:
                pass
            d["indicator"] = None

    def _commit_model_drag(self, mid, new_index):
        if mid not in self.models:
            return
        self.models.remove(mid)
        self.models.insert(max(0, min(new_index, len(self.models))), mid)
        if hasattr(self, "filtered") and mid in self.filtered:
            self.filtered.remove(mid)
            self.filtered.insert(max(0, min(new_index, len(self.filtered))), mid)
        if self.on_reorder:
            try:
                self.on_reorder(list(self.models))
            except Exception:
                pass
        if self.on_after_reorder:
            try:
                self.on_after_reorder()
            except Exception:
                pass
        self._render()

    def _probe(self, model):
        if not self.on_probe:
            return
        threading.Thread(target=self._probe_worker, args=(model,),
                         daemon=True).start()

    def _select_model(self, model):
        self._last_selected = model
        self.calc_cost_var.set(_estimate_cost(model, self.calc_n_var.get()))

    def _on_calc_change(self):
        sel = getattr(self, "_last_selected", None)
        if sel:
            self.calc_cost_var.set(_estimate_cost(sel, self.calc_n_var.get()))

    def _probe_worker(self, model):
        try:
            ok, latency_ms, error = self.on_probe(model)
        except Exception as e:
            ok, latency_ms, error = False, 0, str(e)
        self.after(0, self._probe_done, model, ok, latency_ms, error)

    def _probe_done(self, model, ok, latency_ms, error):
        msg = f"{'✓' if ok else '✗'} {latency_ms:.0f}ms" if ok else f"{'✗'} {error}"
        var = getattr(self, "probe_result_var", None)
        if var is not None:
            var.set(msg)
            self.after(3000, lambda: self._clear_probe_result()
                       if var.get() == msg else None)
        print(f"{'✓' if ok else '✗'} {model}  {latency_ms:.0f}ms" if ok
              else f"{'✗'} {model}  {error}")

    def _clear_probe_result(self):
        if hasattr(self, "probe_result_var"):
            try:
                self.probe_result_var.set("")
            except tk.TclError:
                pass

    def _on_canvas_configure(self, event):
        try:
            self.canvas.itemconfig(self._list_window, width=event.width)
        except tk.TclError:
            pass

    def _on_wheel(self, event):
        try:
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        except tk.TclError:
            pass

    def _wheel_enter(self, event):
        try:
            self.canvas.bind_all("<MouseWheel>", self._on_wheel)
        except tk.TclError:
            pass

    def _wheel_leave(self, event):
        try:
            self.canvas.unbind_all("<MouseWheel>")
        except tk.TclError:
            pass

    def _on_close(self):
        try:
            self.canvas.unbind_all("<MouseWheel>")
        except tk.TclError:
            pass
        self.destroy()

    def _attach_tooltip(self, widget, text, delay_ms=600):
        tip = {"win": None, "after_id": None}

        def _show():
            if tip["win"] is not None:
                return
            try:
                x = widget.winfo_rootx() + 20
                y = widget.winfo_rooty() + widget.winfo_height() + 4
            except tk.TclError:
                return
            win = tk.Toplevel(self)
            win.wm_overrideredirect(True)
            win.wm_geometry(f"+{x}+{y}")
            tk.Label(win, text=text, bg="#2a2a3a", fg="#e8e8f0",
                     font=("Microsoft YaHei UI", 9), padx=8, pady=3,
                     relief="flat").pack()
            tip["win"] = win

        def _hide():
            if tip["after_id"]:
                try:
                    self.after_cancel(tip["after_id"])
                except tk.TclError:
                    pass
                tip["after_id"] = None
            if tip["win"] is not None:
                try:
                    tip["win"].destroy()
                except tk.TclError:
                    pass
                tip["win"] = None

        def _on_enter(e):
            tip["after_id"] = self.after(delay_ms, _show)

        def _on_leave(e):
            _hide()

        widget.bind("<Enter>", _on_enter, add="+")
        widget.bind("<Leave>", _on_leave, add="+")
        widget.bind("<Button-1>", _hide, add="+")


# 常见模型公开价(USD per 1M tokens),粗略。生产环境应从 provider /pricing 端点拉。
PRICE_TABLE = {
    "gpt-4o": (2.5, 10.0),
    "gpt-4o-mini": (0.15, 0.6),
    "gpt-4-turbo": (10.0, 30.0),
    "claude-3-5-sonnet": (3.0, 15.0),
    "claude-3-5-haiku": (0.8, 4.0),
    "claude-3-opus": (15.0, 75.0),
    "deepseek-chat": (0.27, 1.1),
    "deepseek-reasoner": (0.55, 2.19),
    "glm-4-plus": (7.0, 7.0),
    "glm-4-flash": (0.0, 0.0),
}


def _estimate_cost(model, n_calls):
    try:
        n = int(n_calls or 0)
    except ValueError:
        return "次数无效"
    if n <= 0:
        return "—"
    mid = model.lower()
    matched = None
    for key, price in PRICE_TABLE.items():
        if key in mid or mid in key:
            matched = price
            break
    if matched is None:
        return f"无价表 (需手填)"
    in_p, out_p = matched
    avg_in, avg_out = 500, 200
    cost = (in_p * avg_in + out_p * avg_out) / 1_000_000 * n
    return f"≈ ${cost:.4f}"
