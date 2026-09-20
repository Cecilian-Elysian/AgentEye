"""Model 详情弹窗:展示 provider 的模型列表 + 搜索 + 分组 + 试调。"""

import threading
import time
import tkinter as tk


class ModelPanel(tk.Toplevel):
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
                 on_reorder=None):
        super().__init__(parent)
        self.title(f"{provider_name} · 模型列表")
        self.configure(bg="#1d1d2b")
        self.geometry("420x520")
        self.transient(parent)

        self.models = list(models or [])
        self.filtered = list(self.models)
        self.on_probe = on_probe
        self.on_reorder = on_reorder
        self._drag = None

        BG = "#1d1d2b"
        FG = "#e8e8f0"
        DIM = "#8b8b9e"
        FONT = ("Microsoft YaHei UI", 10)

        top = tk.Frame(self, bg=BG)
        top.pack(fill="x", padx=12, pady=(12, 6))
        tk.Label(top, text=f"{len(self.models)} 个模型",
                 bg=BG, fg=DIM, font=FONT).pack(side="left")

        search_frame = tk.Frame(self, bg=BG)
        search_frame.pack(fill="x", padx=12)
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *a: self._apply_filter())
        tk.Entry(search_frame, textvariable=self.search_var,
                 bg="#15151d", fg=FG, insertbackground=FG,
                 font=FONT, relief="flat").pack(fill="x")

        calc_frame = tk.Frame(self, bg=BG)
        calc_frame.pack(fill="x", padx=12, pady=(4, 0))
        tk.Label(calc_frame, text="估算调用", bg=BG, fg=DIM,
                 font=(FONT, 9)).pack(side="left")
        self.calc_n_var = tk.StringVar(value="100")
        tk.Entry(calc_frame, textvariable=self.calc_n_var, width=6,
                 bg="#15151d", fg=FG, insertbackground=FG,
                 font=(FONT, 9), relief="flat").pack(side="left", padx=(4, 2))
        tk.Label(calc_frame, text="次 (按选定模型)", bg=BG, fg=DIM,
                 font=(FONT, 9)).pack(side="left")
        self.calc_cost_var = tk.StringVar(value="选择模型后查看")
        tk.Label(calc_frame, textvariable=self.calc_cost_var,
                 bg=BG, fg="#53d77a", font=(FONT, 9, "bold")).pack(
            side="right")

        list_frame = tk.Frame(self, bg=BG)
        list_frame.pack(fill="both", expand=True, padx=12, pady=8)

        self.canvas = tk.Canvas(list_frame, bg=BG, highlightthickness=0)
        self.scroll = tk.Scrollbar(list_frame, orient="vertical",
                                   command=self.canvas.yview)
        self.inner = tk.Frame(self.canvas, bg=BG)
        self.inner.bind("<Configure>",
                        lambda e: self.canvas.configure(
                            scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scroll.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scroll.pack(side="right", fill="y")
        self.canvas.bind_all("<MouseWheel>",
                             lambda e: self.canvas.yview_scroll(
                                 int(-1 * (e.delta / 120)), "units"))

        tk.Button(self, text="关闭", command=self.destroy,
                  bg="#2a2a3a", fg=FG, relief="flat", font=FONT,
                  width=10).pack(side="right", padx=12, pady=8)

        self.bind("<Escape>", lambda e: self.destroy())
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_y() + 40
        self.geometry(f"+{max(0, x)}+{max(0, y)}")
        self.grab_set()
        self.focus_set()

        self._render()

    def _apply_filter(self):
        q = self.search_var.get().lower().strip()
        if not q:
            self.filtered = list(self.models)
        else:
            self.filtered = [m for m in self.models if q in m.lower()]
        self._render()

    def _group(self, model_id):
        mid = model_id.lower()
        for group, keywords in self.GROUP_RULES:
            if any(k in mid for k in keywords):
                return group
        return "其他"

    def _render(self):
        for w in self.inner.winfo_children():
            w.destroy()

        if not self.filtered:
            tk.Label(self.inner, text="(无匹配)", bg="#1d1d2b",
                     fg="#8b8b9e", font=("Microsoft YaHei UI", 10)).pack(pady=20)
            return

        grouped = {}
        for m in self.filtered:
            grouped.setdefault(self._group(m), []).append(m)

        BG = "#1d1d2b"
        DIM = "#8b8b9e"
        FG = "#e8e8f0"
        FONT = ("Microsoft YaHei UI", 9)

        for group_name in ["Claude", "GPT", "Gemini", "Llama", "Qwen",
                           "DeepSeek", "GLM", "Embedding", "Image", "Audio", "其他"]:
            if group_name not in grouped:
                continue
            tk.Label(self.inner, text=group_name, bg=BG, fg=DIM,
                     font=(FONT[0], 9, "bold")).pack(anchor="w", pady=(8, 2))
            for m in grouped[group_name]:
                row = tk.Frame(self.inner, bg="#15151d", cursor="hand2")
                row.pack(fill="x", pady=1)
                row._model_id = m
                tk.Label(row, text=m, bg="#15151d", fg=FG,
                         font=FONT, anchor="w").pack(side="left", padx=8, pady=4)
                if self.on_probe:
                    tk.Button(row, text="试调", font=(FONT[0], 8),
                              bg="#2a2a3a", fg=FG, relief="flat",
                              command=lambda model=m: self._probe(model)).pack(
                        side="right", padx=4, pady=2)
                select_btn = tk.Label(row, text="选", font=(FONT[0], 8),
                                      bg="#2a2a3a", fg=FG, cursor="hand2")
                select_btn.pack(side="right", padx=(0, 4), pady=2)
                select_btn.bind("<Button-1>", lambda e, model=m: self._select_model(model))

                for child in row.winfo_children():
                    child.bind("<Button-1>", lambda e, mid=m: self._drag_press(e, mid), add="+")
                    child.bind("<B1-Motion>", lambda e, mid=m: self._drag_motion(e, mid), add="+")
                    child.bind("<ButtonRelease-1>", lambda e, mid=m: self._drag_release(e, mid), add="+")
                row.bind("<Button-1>", lambda e, mid=m: self._drag_press(e, mid), add="+")
                row.bind("<B1-Motion>", lambda e, mid=m: self._drag_motion(e, mid), add="+")
                row.bind("<ButtonRelease-1>", lambda e, mid=m: self._drag_release(e, mid), add="+")

    def _drag_press(self, event, mid):
        w = event.widget
        if isinstance(w, tk.Button):
            return
        try:
            if w.cget("text") == "选":
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
            if abs(event.y_root - d["start_y"]) <= 5:
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
        self._render()

    def _probe(self, model):
        if not self.on_probe:
            return
        threading.Thread(target=self._probe_worker, args=(model,),
                         daemon=True).start()

    def _select_model(self, model):
        self.calc_cost_var.set(_estimate_cost(model, self.calc_n_var.get()))

    def _on_calc_change(self):
        if hasattr(self, "_last_selected") and self._last_selected:
            self.calc_cost_var.set(_estimate_cost(self._last_selected, self.calc_n_var.get()))

    def _probe_worker(self, model):
        try:
            ok, latency_ms, error = self.on_probe(model)
        except Exception as e:
            ok, latency_ms, error = False, 0, str(e)
        self.after(0, self._probe_done, model, ok, latency_ms, error)

    def _probe_done(self, model, ok, latency_ms, error):
        msg = f"{'✓' if ok else '✗'} {model}"
        msg += f"  {latency_ms:.0f}ms" if ok else f"  {error}"
        print(msg)


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
