"""Add Key 对话框:粘贴 key → 自动探测 → 预览 → 保存。

流程:
  1. 用户输入 base_url (可选) 和 api_key
  2. FocusOut 触发 detect + 通用探测(超时 8s)
  3. 预览区显示识别结果 + 模型数 + 余额快照
  4. 用户填名称,点"保存"
  5. 写入 config (通过 on_save 回调),关闭对话框
"""

import threading
import time
import tkinter as tk
from tkinter import ttk

from providers import detect as detect_mod


class AddKeyDialog(tk.Toplevel):
    PROBE_TIMEOUT = 8.0

    def __init__(self, parent, on_save, generic_probe=None):
        super().__init__(parent)
        self.title("添加 Key")
        self.configure(bg="#1d1d2b")
        self.resizable(False, False)
        self.transient(parent)

        self.on_save = on_save
        self.generic_probe = generic_probe or _generic_probe_stub
        self._probe_thread = None
        self._probe_result = None
        self._probe_started_at = 0.0

        self._build_ui()
        self._bind_shortcuts()

        self.update_idletasks()
        self.grab_set()
        self.focus_set()

    def _build_ui(self):
        PAD = {"padx": 12, "pady": 6}
        BG = "#1d1d2b"
        FG = "#e8e8f0"
        DIM = "#8b8b9e"
        FONT = ("Microsoft YaHei UI", 10)

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=14, pady=12)

        tk.Label(body, text="Base URL (可选)", bg=BG, fg=DIM, font=FONT).grid(
            row=0, column=0, sticky="w", **PAD)
        self.url_var = tk.StringVar()
        self.url_entry = tk.Entry(body, textvariable=self.url_var, width=44,
                                  bg="#15151d", fg=FG, insertbackground=FG,
                                  font=FONT, relief="flat")
        self.url_entry.grid(row=0, column=1, sticky="ew", **PAD)
        self.url_entry.bind("<FocusOut>", lambda e: self._schedule_probe())

        tk.Label(body, text="API Key", bg=BG, fg=FG, font=FONT).grid(
            row=1, column=0, sticky="w", **PAD)
        self.key_var = tk.StringVar()
        self.key_entry = tk.Entry(body, textvariable=self.key_var, width=44,
                                  show="•", bg="#15151d", fg=FG,
                                  insertbackground=FG, font=FONT, relief="flat")
        self.key_entry.grid(row=1, column=1, sticky="ew", **PAD)
        self.key_entry.bind("<FocusOut>", lambda e: self._schedule_probe())
        self.key_entry.bind("<KeyRelease>", lambda e: self._schedule_probe(delay=0.6))

        self.detect_btn = tk.Button(body, text="探测", command=self._probe_now,
                                    bg="#2a2a3a", fg=FG, relief="flat",
                                    activebackground="#3a3a4a", font=FONT)
        self.detect_btn.grid(row=0, column=2, rowspan=2, sticky="ns", padx=8)

        sep = tk.Frame(body, height=1, bg="#3a3a4a")
        sep.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(8, 4))

        tk.Label(body, text="识别结果", bg=BG, fg=DIM, font=FONT).grid(
            row=3, column=0, sticky="nw", **PAD)
        self.preview = tk.Text(body, height=8, width=50, bg="#15151d", fg=FG,
                               font=("Microsoft YaHei UI", 9), relief="flat",
                               wrap="word", state="disabled")
        self.preview.grid(row=3, column=1, columnspan=2, sticky="ew", **PAD)

        tk.Label(body, text="显示名称", bg=BG, fg=FG, font=FONT).grid(
            row=4, column=0, sticky="w", **PAD)
        self.name_var = tk.StringVar()
        tk.Entry(body, textvariable=self.name_var, width=44,
                 bg="#15151d", fg=FG, insertbackground=FG,
                 font=FONT, relief="flat").grid(row=4, column=1, columnspan=2,
                                                sticky="ew", **PAD)

        sep2 = tk.Frame(body, height=1, bg="#3a3a4a")
        sep2.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(8, 4))

        btn_frame = tk.Frame(body, bg=BG)
        btn_frame.grid(row=6, column=0, columnspan=3, sticky="e", pady=(4, 0))
        tk.Button(btn_frame, text="取消", command=self.destroy,
                  bg="#2a2a3a", fg=FG, relief="flat", font=FONT,
                  width=10).pack(side="right", padx=(8, 0))
        self.save_btn = tk.Button(btn_frame, text="保存", command=self._save,
                                  bg="#53d77a", fg="#15151d", relief="flat",
                                  font=FONT, width=10, state="disabled")
        self.save_btn.pack(side="right")

        body.columnconfigure(1, weight=1)
        self._set_preview("等待输入 key …")

    def _bind_shortcuts(self):
        self.bind("<Escape>", lambda e: self.destroy())
        self.bind("<Return>", lambda e: self._save() if self.save_btn["state"] == "normal" else None)
        self.url_entry.focus_set()

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
        key = self.key_var.get().strip()
        url = self.url_var.get().strip()
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
        if detected["kind"] == "generic_openai" and detected["base_url"]:
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
        key = self.key_var.get().strip()
        url = self.url_var.get().strip()
        name = self.name_var.get().strip() or "未命名"
        if not key:
            return
        self.on_save({
            "name": name,
            "key": key,
            "base_url": url,
        })
        self.destroy()


def _generic_probe_stub(base_url, key, timeout=8.0):
    """未注入时返回 None 让 Add Key 仅完成 detect,跳过模型探测。"""
    return None
