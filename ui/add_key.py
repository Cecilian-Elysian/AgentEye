"""Add Key 表单(可内嵌,非独立窗口)。

粘贴 key → 自动探测 → 预览 → 保存。宿主决定容器:
- ui/settings_dialog.py 在同一窗口内切换「设置 ↔ 添加 Key」两个视图
- 面板工具栏的"添加"入口也走设置对话框,不再弹独立窗口

流程:
  0. 顶部一行 5 个 provider 预设按钮 (MiniMax/DeepSeek/智谱/OpenCode/中转站),
     点击自动填默认 base_url 和名称占位
  1. 用户输入 base_url (可选) 和 api_key
  2. FocusOut 触发 detect + 通用探测(超时 8s)
  3. 预览区显示识别结果 + 模型数 + 余额快照
  4. 用户填名称,点"保存"
  5. 回调 on_save(entry),随后 on_done()(宿主决定去向)
"""

import threading
import time
import tkinter as tk

from providers import detect as detect_mod
from ui.theme import PALETTE, on_theme_change, to_tk_color, to_tk_color_blended


PRESETS = [
    ("MiniMax",    "minimax",     "https://api.minimaxi.com"),
    ("DeepSeek",   "deepseek",    "https://api.deepseek.com"),
    ("智谱 GLM",   "zhipu",       "https://open.bigmodel.cn"),
    ("OpenCode",   "opencode_go", "https://opencode.ai"),
    ("中转站",     "relay",       ""),
]

FONT = "Microsoft YaHei UI"


class AddKeyForm(tk.Frame):
    PROBE_TIMEOUT = 8.0

    def __init__(self, parent, on_save=None, on_done=None, generic_probe=None,
                 current_count=0, show_count=True):
        super().__init__(parent, bg=to_tk_color(PALETTE.BG))
        self.on_save = on_save
        self.on_done = on_done
        self.generic_probe = generic_probe or _generic_probe_stub
        self._probe_thread = None
        self._probe_result = None
        self._probe_started_at = 0.0
        self._show_count = show_count

        self._build_ui(current_count)
        on_theme_change(self.refresh_palette)

    # ---------- 配色 ----------

    def refresh_palette(self, *_args):
        """主题切换时重画表单配色。"""
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return
        try:
            self._walk_recolor(self)
        except tk.TclError:
            pass

    def _walk_recolor(self, w):
        BG = to_tk_color(PALETTE.BG)
        BG_FIELD = to_tk_color(PALETTE.BAR_BG)
        FG = to_tk_color(PALETTE.TEXT)
        DIM = to_tk_color_blended(PALETTE.TEXT_DIM)
        BTN_BG = to_tk_color(PALETTE.CARD_HOVER)
        BTN_HOVER = to_tk_color(PALETTE.CARD_PRESSED)
        OK = to_tk_color(PALETTE.OK)
        FG_ON_OK = to_tk_color(PALETTE.BG)

        try:
            cls = w.winfo_class()
            if cls in ("Frame", "Toplevel"):
                w.configure(bg=BG)
            elif cls == "Label":
                fg = str(w.cget("fg") or "").upper()
                if fg in (DIM.upper(), "#8B8B9E"):
                    w.configure(bg=BG, fg=DIM)
                elif fg == OK.upper():
                    w.configure(bg=BG, fg=OK)
                else:
                    w.configure(bg=BG, fg=FG)
            elif cls == "Entry":
                w.configure(bg=BG_FIELD, fg=FG, insertbackground=FG)
            elif cls == "Button":
                fg = str(w.cget("fg") or "").upper()
                if fg == FG_ON_OK.upper():
                    w.configure(bg=OK, fg=FG_ON_OK)
                else:
                    w.configure(bg=BTN_BG, fg=FG)
        except tk.TclError:
            pass
        for c in w.winfo_children():
            self._walk_recolor(c)

    # ---------- UI ----------

    def _build_ui(self, current_count):
        PAD = {"padx": 12, "pady": 6}
        BG = to_tk_color(PALETTE.BG)
        FG = to_tk_color(PALETTE.TEXT)
        DIM = to_tk_color_blended(PALETTE.TEXT_DIM)
        BG_FIELD = to_tk_color(PALETTE.BAR_BG)
        BTN_BG = to_tk_color(PALETTE.CARD_HOVER)
        BTN_HOVER = to_tk_color(PALETTE.CARD_PRESSED)
        OK = to_tk_color(PALETTE.OK)
        FG_ON_OK = to_tk_color(PALETTE.BG)

        top_row = tk.Frame(self, bg=BG)
        top_row.pack(fill="x", padx=4, pady=(0, 4))
        count_text = f"当前已配置 {current_count} 个" if self._show_count else ""
        tk.Label(top_row, text=count_text, bg=BG, fg=DIM,
                 font=(FONT, 9)).pack(side="right")

        tk.Label(self, text="快速选择", bg=BG, fg=DIM,
                 font=(FONT, 10)).pack(anchor="w", padx=4, pady=(2, 4))
        preset_frame = tk.Frame(self, bg=BG)
        preset_frame.pack(anchor="w", padx=4)
        for label, kind, url in PRESETS:
            b = tk.Label(preset_frame, text=label, font=(FONT, 9),
                         bg=BTN_BG, fg=FG, padx=10, pady=4, cursor="hand2")
            b.pack(side="left", padx=(0, 6))
            b.bind("<Button-1>",
                   lambda e, k=kind, u=url, lbl=label: self._apply_preset(k, u, lbl))
            b.bind("<Enter>", lambda e, w=b: w.config(bg=BTN_HOVER))
            b.bind("<Leave>", lambda e, w=b: w.config(bg=BTN_BG))

        row_url = tk.Frame(self, bg=BG)
        row_url.pack(fill="x", pady=(8, 0))
        tk.Label(row_url, text="Base URL (可选)", bg=BG, fg=DIM,
                 font=(FONT, 10)).pack(side="left")
        self.url_var = tk.StringVar()
        self.url_entry = tk.Entry(row_url, textvariable=self.url_var, width=36,
                                  bg=BG_FIELD, fg=FG, insertbackground=FG,
                                  font=(FONT, 10), relief="flat")
        self.url_entry.pack(side="left", padx=8, fill="x", expand=True)
        self.url_entry.insert(0, "")
        self.url_entry.config(foreground=DIM)
        self._url_placeholder = False
        self.url_entry.bind("<FocusIn>", self._url_focus_in)
        self.url_entry.bind("<FocusOut>", self._url_focus_out)
        self.url_entry.bind("<FocusOut>", lambda e: self._schedule_probe(), add="+")

        row_key = tk.Frame(self, bg=BG)
        row_key.pack(fill="x", pady=(4, 0))
        tk.Label(row_key, text="API Key", bg=BG, fg=FG,
                 font=(FONT, 10)).pack(side="left")
        self.key_var = tk.StringVar()
        self.key_entry = tk.Entry(row_key, textvariable=self.key_var, width=36,
                                  bg=BG_FIELD, fg=FG,
                                  insertbackground=FG, font=(FONT, 10),
                                  relief="flat")
        self.key_entry.pack(side="left", padx=8, fill="x", expand=True)
        self.key_entry.insert(0, "sk-... 粘贴 key")
        self.key_entry.config(foreground=DIM)
        self._key_placeholder = True
        self.key_entry.bind("<FocusIn>", self._key_focus_in)
        self.key_entry.bind("<FocusOut>", self._key_focus_out)
        self.key_entry.bind("<FocusOut>", lambda e: self._schedule_probe(), add="+")
        self.key_entry.bind("<KeyRelease>", lambda e: self._schedule_probe(delay=0.6))
        self.key_entry.bind("<Return>", lambda e: self._save()
                            if str(self.save_btn["state"]) == "normal" else None)

        self.detect_btn = tk.Button(row_url, text="探测", command=self._probe_now,
                                    bg=BTN_BG, fg=FG, relief="flat",
                                    activebackground=BTN_HOVER, font=(FONT, 10))
        self.detect_btn.pack(side="right", padx=(8, 0))

        sep = tk.Frame(self, height=1, bg=BTN_HOVER)
        sep.pack(fill="x", pady=(8, 4))

        tk.Label(self, text="识别结果", bg=BG, fg=DIM,
                 font=(FONT, 10)).pack(anchor="w", padx=4)
        self.preview = tk.Text(self, height=7, bg=BG_FIELD, fg=FG,
                               font=(FONT, 9), relief="flat",
                               wrap="word", state="disabled")
        self.preview.pack(fill="x", padx=4, pady=(2, 4))

        row_name = tk.Frame(self, bg=BG)
        row_name.pack(fill="x", pady=(2, 0))
        tk.Label(row_name, text="显示名称", bg=BG, fg=FG,
                 font=(FONT, 10)).pack(side="left")
        self.name_var = tk.StringVar()
        tk.Entry(row_name, textvariable=self.name_var, width=36,
                 bg=BG_FIELD, fg=FG, insertbackground=FG,
                 font=(FONT, 10), relief="flat").pack(
            side="left", padx=8, fill="x", expand=True)

        btn_frame = tk.Frame(self, bg=BG)
        btn_frame.pack(fill="x", pady=(10, 0))
        self.save_btn = tk.Button(btn_frame, text="保存", command=self._save,
                                  bg=OK, fg=FG_ON_OK, relief="flat",
                                  font=(FONT, 10), width=10, state="disabled")
        self.save_btn.pack(side="right")

        self._set_preview("等待输入 key …")

    # ---------- placeholder ----------

    def _url_focus_in(self, e):
        if self._url_placeholder:
            self.url_entry.delete(0, "end")
            self.url_entry.config(foreground="#e8e8f0")
            self._url_placeholder = False

    def _url_focus_out(self, e):
        if not self.url_var.get().strip():
            self.url_entry.delete(0, "end")
            self.url_entry.insert(0, "中转站可留空,其他建议填默认")
            self.url_entry.config(foreground="#8b8b9e")
            self._url_placeholder = True

    def _key_focus_in(self, e):
        if self._key_placeholder:
            self.key_entry.delete(0, "end")
            self.key_entry.config(foreground="#e8e8f0", show="•")
            self._key_placeholder = False

    def _key_focus_out(self, e):
        if not self.key_var.get().strip():
            self.key_entry.delete(0, "end")
            self.key_entry.insert(0, "sk-... 粘贴 key")
            self.key_entry.config(foreground="#8b8b9e", show="")
            self._key_placeholder = True

    # ---------- 逻辑 ----------

    def _apply_preset(self, kind, url, label):
        if self._url_placeholder:
            self._url_focus_out(None)
        self.url_var.set(url)
        self._url_placeholder = False
        self.url_entry.config(foreground="#e8e8f0")
        if not self.name_var.get().strip():
            self.name_var.set(label)
        self.key_entry.focus_set()

    def _set_preview(self, text):
        self.preview.config(state="normal")
        self.preview.delete("1.0", "end")
        self.preview.insert("1.0", text)
        self.preview.config(state="disabled")

    def _schedule_probe(self, delay=0.3):
        if self._probe_thread and self._probe_thread.is_alive():
            return
        self.after(int(delay * 1000), self._probe_now)

    def _probe_now(self):
        if self._probe_thread and self._probe_thread.is_alive():
            return
        if self._key_placeholder:
            self._set_preview("等待输入 key …")
            self.save_btn.config(state="disabled")
            return
        key = self.key_var.get().strip()
        url = "" if self._url_placeholder else self.url_var.get().strip()
        if not key:
            self._set_preview("等待输入 key …")
            self.save_btn.config(state="disabled")
            return
        self._set_preview("探测中 …")
        self.detect_btn.config(state="disabled")
        self.save_btn.config(state="disabled")
        self._probe_started_at = time.time()
        self._probe_thread = threading.Thread(
            target=self._probe_worker, args=(key, url), daemon=True)
        self._probe_thread.start()

    def _probe_worker(self, key, url):
        detected = detect_mod.detect(key, url)
        probe_result = None
        if detected["kind"] in ("minimax", "deepseek", "zhipu", "opencode_go",
                                "generic_openai") and detected["base_url"]:
            try:
                probe_result = self.generic_probe(detected["base_url"], key,
                                                  timeout=self.PROBE_TIMEOUT)
            except Exception as e:
                probe_result = {"error": str(e)}
        elapsed = time.time() - self._probe_started_at
        self.after(0, self._probe_done, detected, probe_result, elapsed)

    def _probe_done(self, detected, probe_result, elapsed):
        self.detect_btn.config(state="normal")
        lines = [
            f"类型:     {detected['kind']}",
            f"置信度:   {detected['confidence']}",
            f"Base URL: {detected['base_url'] or '(未提供)'}",
            f"依据:     {detected['notes']}",
        ]
        if probe_result is not None:
            if probe_result.get("error"):
                lines.append(f"探测:     失败 - {probe_result['error']}")
            else:
                models = probe_result.get("models") or []
                lines.append(f"模型数:   {len(models)}")
                for m in models[:5]:
                    lines.append(f"          · {m}")
                if len(models) > 5:
                    lines.append(f"          · … 共 {len(models)} 个")
                if probe_result.get("quota_endpoint"):
                    lines.append(f"额度端点: {probe_result['quota_endpoint']}")
                if probe_result.get("remaining") is not None:
                    unit = probe_result.get("unit", "")
                    lines.append(f"余额:     {unit}{probe_result['remaining']:.2f}")
        lines.append(f"\n耗时:     {elapsed:.1f}s")
        self._set_preview("\n".join(lines))
        if not self.name_var.get().strip() and detected["kind"]:
            pretty = {"minimax": "MiniMax", "deepseek": "DeepSeek",
                      "zhipu": "智谱 GLM", "opencode_go": "OpenCode Go",
                      "relay": "中转站"}.get(detected["kind"], detected["kind"])
            self.name_var.set(pretty)
        ok = detected["kind"] and (detected["base_url"] or detected["kind"] != "generic_openai")
        if ok and probe_result and not probe_result.get("error"):
            self.save_btn.config(state="normal")
        elif ok and detected["kind"] != "generic_openai":
            self.save_btn.config(state="normal")
        else:
            self.save_btn.config(state="disabled")

    def _save(self):
        if self._key_placeholder:
            return
        key = self.key_var.get().strip()
        url = "" if self._url_placeholder else self.url_var.get().strip()
        name = self.name_var.get().strip() or "未命名"
        if not key:
            return
        entry = {
            "name": name,
            "key": key,
            "base_url": url,
        }
        if self.on_save:
            self.on_save(entry)
        if self.on_done:
            self.on_done()


def _generic_probe_stub(base_url, key, timeout=8.0):
    """未注入时返回 None 让 Add Key 仅完成 detect,跳过模型探测。"""
    return None
