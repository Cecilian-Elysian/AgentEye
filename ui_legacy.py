import time
import tkinter as tk

from providers import fmt_countdown, fmt_main

FONT = "Microsoft YaHei UI"
ROW_W = 284
PAD = 10

C = {
    "bg": "#15151d",
    "card": "#1d1d2b",
    "bar_bg": "#2a2a3a",
    "text": "#e8e8f0",
    "dim": "#8b8b9e",
    "ok": "#53d77a",
    "warn": "#f0c24b",
    "critical": "#ff5d5d",
    "error": "#ff8f6b",
    "off": "#5b5b68",
}

LEVEL_COLOR = {
    "ok": C["ok"],
    "warn": C["warn"],
    "critical": C["critical"],
    "error": C["error"],
    "unconfigured": C["off"],
    "unknown": C["dim"],
}


class Panel:
    def __init__(self, root, state, cfg, actions):
        self.root = root
        self.state = state
        self.cfg = cfg
        self.actions = actions
        self._sig = None
        self._rows = {}

        root.title("AgentEye")
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.configure(bg=C["bg"])
        self._place_initial()

        header = tk.Frame(root, bg=C["bg"])
        header.pack(fill="x", padx=PAD, pady=(8, 2))
        tk.Label(
            header, text="AgentEye", font=(FONT, 10, "bold"), fg=C["text"], bg=C["bg"]
        ).pack(side="left")
        self.dot = tk.Label(header, text="●", font=(FONT, 9), fg=C["dim"], bg=C["bg"])
        self.dot.pack(side="right", padx=(0, 8))
        close = tk.Label(header, text="×", font=(FONT, 12), fg=C["dim"], bg=C["bg"])
        close.pack(side="right")
        close.bind("<Button-1>", lambda e: actions["quit"]())

        self.rows_frame = tk.Frame(root, bg=C["bg"])
        self.rows_frame.pack(fill="x", padx=PAD)

        self.footer = tk.Label(
            root, text="", font=(FONT, 8), fg=C["dim"], bg=C["bg"], anchor="w"
        )
        self.footer.pack(fill="x", padx=PAD, pady=(2, 8))

        for w in (root, header):
            w.bind("<Button-1>", self._drag_start)
            w.bind("<B1-Motion>", self._drag_move)
            w.bind("<ButtonRelease-1>", self._drag_end)

        self.menu = self._build_menu()
        root.bind("<Button-3>", self._popup_menu)

        self._tick()

    def _place_initial(self):
        ui = (self.cfg.get("ui") or {})
        x, y = ui.get("x"), ui.get("y")
        if x is None or y is None:
            sw = self.root.winfo_screenwidth()
            x, y = sw - ROW_W - 40, 60
        self.root.geometry(f"+{int(x)}+{int(y)}")

    def _build_menu(self):
        m = tk.Menu(self.root, tearoff=0)
        m.add_command(label="立即刷新", command=self.actions["refresh_now"])
        m.add_command(label="通知测试", command=self.actions["test_notify"])
        self._pause_idx = m.index("end")
        m.add_command(label="暂停轮询", command=self.actions["toggle_pause"])
        m.add_command(label="打开配置文件", command=self.actions["open_config"])
        m.add_separator()
        m.add_command(label="退出", command=self.actions["quit"])
        return m

    def _popup_menu(self, event):
        paused = self.state.paused
        self.menu.entryconfig(
            self._pause_idx + 1, label="恢复轮询" if paused else "暂停轮询"
        )
        self.menu.tk_popup(event.x_root, event.y_root)

    def _drag_start(self, event):
        self._ox = event.x_root - self.root.winfo_x()
        self._oy = event.y_root - self.root.winfo_y()

    def _drag_move(self, event):
        self.root.geometry(
            f"+{event.x_root - self._ox}+{event.y_root - self._oy}"
        )

    def _drag_end(self, event):
        self.actions["save_position"](
            self.root.winfo_x(), self.root.winfo_y()
        )

    def _tick(self):
        try:
            if self.root.winfo_exists():
                self._update()
                self.root.after(1000, self._tick)
        except tk.TclError:
            pass

    def _update(self):
        state = self.state
        self._sync_rows()
        levels = [r.get("level") for r in state.results]
        if state.paused:
            self.dot.config(fg=C["off"])
        elif "critical" in levels or "error" in levels:
            self.dot.config(fg=C["critical"])
        elif "warn" in levels:
            self.dot.config(fg=C["warn"])
        else:
            self.dot.config(fg=C["ok"])

        if state.paused:
            text = "已暂停轮询"
        elif state.fetching:
            text = "刷新中…"
        elif state.next_fetch:
            text = f"下次刷新 {fmt_countdown(state.next_fetch - time.time())}"
        else:
            text = "等待首次刷新…"
        self.footer.config(text=text)

    def _sync_rows(self):
        results = self.state.results
        sig = tuple((r.get("name"), r.get("type")) for r in results)
        if sig != self._sig:
            self._rebuild(results)
            self._sig = sig
        for r in results:
            widgets = self._rows.get(r.get("name"))
            if not widgets:
                continue
            self._paint_row(widgets, r)

    def _rebuild(self, results):
        for child in self.rows_frame.winfo_children():
            child.destroy()
        self._rows = {}
        if not results:
            box = self._row_skeleton("未配置任何额度源", str(_config_hint()))
            box["value"].config(text="-", fg=C["off"])
            self._paint_bar(box, None, C["off"])
            return
        for r in results:
            self._rows[r["name"]] = self._row_skeleton(r["name"], "")

    def _row_skeleton(self, name, detail):
        card = tk.Frame(self.rows_frame, bg=C["card"])
        card.pack(fill="x", pady=3)
        top = tk.Frame(card, bg=C["card"])
        top.pack(fill="x", padx=8, pady=(6, 0))
        name_lbl = tk.Label(
            top, text=name, font=(FONT, 9, "bold"), fg=C["text"], bg=C["card"]
        )
        name_lbl.pack(side="left")
        value_lbl = tk.Label(
            top, text="…", font=(FONT, 9), fg=C["dim"], bg=C["card"]
        )
        value_lbl.pack(side="right")
        det_lbl = tk.Label(
            card,
            text=detail,
            font=(FONT, 7),
            fg=C["dim"],
            bg=C["card"],
            anchor="w",
            wraplength=ROW_W - 24,
            justify="left",
        )
        det_lbl.pack(fill="x", padx=8)
        bar = tk.Canvas(card, height=5, bg=C["bar_bg"], highlightthickness=0)
        bar.pack(fill="x", padx=8, pady=(4, 7))
        rect = bar.create_rectangle(0, 0, 0, 5, outline="")
        return {
            "frame": card,
            "name": name_lbl,
            "value": value_lbl,
            "detail": det_lbl,
            "bar": bar,
            "rect": rect,
        }

    def _paint_row(self, widgets, r):
        level = r.get("level", "unknown")
        color = LEVEL_COLOR.get(level, C["dim"])
        widgets["value"].config(text=fmt_main(r), fg=color)
        detail = r.get("detail") or ""
        if r.get("error"):
            detail = r["error"]
        if not detail:
            updated = time.strftime("%H:%M:%S", time.localtime(r.get("updated_at", 0)))
            detail = f"更新于 {updated}"
        widgets["detail"].config(text=detail)
        pct = r.get("pct")
        frac = None
        if pct is not None:
            frac = max(0.0, min(1.0, float(pct) / 100.0))
        self._paint_bar(widgets, frac, color)

    def _paint_bar(self, widgets, frac, color):
        bar = widgets["bar"]
        rect = widgets["rect"]
        width = bar.winfo_width() or ROW_W - 24
        bar.coords(rect, 0, 0, width * (frac if frac is not None else 1.0), 5)
        bar.itemconfig(rect, fill=color)


def _config_hint():
    from pathlib import Path

    return Path.home() / ".agenteye" / "config.json"
