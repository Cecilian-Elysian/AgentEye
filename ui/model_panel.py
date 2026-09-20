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

    def __init__(self, parent, provider_name, models, on_probe=None):
        super().__init__(parent)
        self.title(f"{provider_name} · 模型列表")
        self.configure(bg="#1d1d2b")
        self.geometry("420x520")
        self.transient(parent)

        self.models = models or []
        self.filtered = list(self.models)
        self.on_probe = on_probe

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
                row = tk.Frame(self.inner, bg="#15151d")
                row.pack(fill="x", pady=1)
                tk.Label(row, text=m, bg="#15151d", fg=FG,
                         font=FONT, anchor="w").pack(side="left", padx=8, pady=4)
                if self.on_probe:
                    tk.Button(row, text="试调", font=(FONT[0], 8),
                              bg="#2a2a3a", fg=FG, relief="flat",
                              command=lambda model=m: self._probe(model)).pack(
                        side="right", padx=4, pady=2)

    def _probe(self, model):
        if not self.on_probe:
            return
        threading.Thread(target=self._probe_worker, args=(model,),
                         daemon=True).start()

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
