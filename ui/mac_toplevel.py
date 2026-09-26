"""macOS 风格的模态/非模态对话框基类 MacToplevel。

特性:
- 接管 tk.Toplevel,加 36px 标题栏 + 交通灯 + 拖拽移动
- 跨平台 vibrancy / 圆角 / 深色标题栏(Win11 / macOS / Linux 软降级)
- on_theme_change 自动调 refresh_palette 刷所有子 widget 配色
- 子类只需继承 + 在 _build_body(self, parent) 里加自己的 UI,
  不要覆盖 __init__,改用 _build_body() + 自定义 init_after_build()

用法:
    class MyDialog(MacToplevel):
        def __init__(self, parent, ...):
            super().__init__(
                parent, title="我的对话框",
                show_minimize=True, show_expand=False,
                on_close=self.destroy,
            )
            self._build_body(self.body)
            # 业务逻辑 ...
"""

import tkinter as tk

from ui.theme import PALETTE, Layout, on_theme_change, to_tk_color
from ui.vibrancy import apply_window_chrome


class MacToplevel(tk.Toplevel):
    """所有 macOS 风格对话框的基类。"""

    HEADER_HEIGHT = Layout.HEADER_HEIGHT

    def __init__(self, parent, title="", on_close=None, on_minimize=None,
                 show_minimize=True, show_expand=False,
                 width=460, height=400, resizable=True):
        super().__init__(parent)
        self._on_close = on_close or self.destroy
        self._on_minimize = on_minimize
        self._show_minimize = show_minimize
        self._show_expand = show_expand

        try:
            self.title(title or "")
        except tk.TclError:
            pass

        try:
            self.configure(bg=PALETTE.CARD)
        except tk.TclError:
            pass

        if resizable:
            self.resizable(True, True)
        else:
            self.resizable(False, False)

        self._drag_data = None
        self._header_widgets = []

        self.outer = tk.Frame(self, bg=PALETTE.CARD, bd=0,
                              highlightthickness=0)
        self.outer.pack(fill="both", expand=True)

        self.header = tk.Frame(
            self.outer, bg=PALETTE.CARD,
            height=self.HEADER_HEIGHT, bd=0, highlightthickness=0,
        )
        self.header.pack(side="top", fill="x")
        self.header.pack_propagate(False)

        self._build_header()

        self.body = tk.Frame(
            self.outer, bg=PALETTE.CARD, bd=0, highlightthickness=0,
        )
        self.body.pack(side="top", fill="both", expand=True)

        self._apply_chrome()
        self._center_on_parent(parent, width, height)

        on_theme_change(self._on_theme_change)

    def _build_header(self):
        """左侧交通灯 + 中间标题。"""
        left = tk.Frame(self.header, bg=PALETTE.CARD)
        left.pack(side="left", padx=(Layout.PAD_X, 0),
                  pady=(self.HEADER_HEIGHT - Layout.TRAFFIC_DOT) / 2)

        close = self._make_dot(left, PALETTE.TRAFFIC_RED, "×", "close")
        close.pack(side="left", padx=(0, Layout.TRAFFIC_GAP))
        self._close_dot = close

        if self._show_minimize:
            mini = self._make_dot(left, PALETTE.TRAFFIC_YELLOW, "−",
                                  "minimize")
            mini.pack(side="left", padx=(0, Layout.TRAFFIC_GAP))
            self._minimize_dot = mini
        else:
            self._minimize_dot = None

        if self._show_expand:
            exp = self._make_dot(left, PALETTE.TRAFFIC_GREEN, "↗", "expand")
            exp.pack(side="left")
            self._expand_dot = exp
        else:
            self._expand_dot = None

        from ui.fonts import fonts
        self._fonts_dict = fonts(self.winfo_toplevel())
        self.title_lbl = tk.Label(
            self.header, text=self.title() or "",
            font=self._fonts_dict.get("title", ("Segoe UI", 11, "bold")),
            fg=to_tk_color(PALETTE.TEXT), bg=to_tk_color(PALETTE.CARD),
        )
        self.title_lbl.place(relx=0.5, rely=0.5, anchor="center")

        for w in (self.header, self.title_lbl, left):
            self._header_widgets.append(w)
            w.bind("<Button-1>", self._drag_start, add="+")
            w.bind("<B1-Motion>", self._drag_motion, add="+")

    def _make_dot(self, parent, color, glyph, kind):
        from ui.app import TrafficLight
        if kind == "close":
            cmd = self._on_close
        elif kind == "minimize":
            cmd = self._on_minimize or self._stub_minimize
        else:
            cmd = self._stub_noop
        dot = TrafficLight(parent, kind, color, cmd,
                           size=Layout.TRAFFIC_DOT)
        dot._kind = kind
        dot._is_header_dot = True
        return dot

    def _stub_minimize(self):
        try:
            self.overrideredirect(False)
            self.iconify()
        except tk.TclError:
            pass

    def _stub_noop(self):
        pass

    def _drag_start(self, event):
        w = event.widget
        while w is not None:
            if getattr(w, "_is_header_dot", False):
                self._drag_data = None
                return
            cls = w.winfo_class()
            if cls in ("Button", "Entry", "Text"):
                self._drag_data = None
                return
            w = w.master
        try:
            self._drag_data = (event.x_root - self.winfo_x(),
                               event.y_root - self.winfo_y())
        except tk.TclError:
            self._drag_data = None

    def _drag_motion(self, event):
        if not self._drag_data:
            return
        ox, oy = self._drag_data
        try:
            self.geometry(f"+{event.x_root - ox}+{event.y_root - oy}")
        except tk.TclError:
            pass

    def _apply_chrome(self):
        try:
            self.update_idletasks()
            apply_window_chrome(self, dark=PALETTE.IS_DARK)
        except Exception:
            pass

    def _center_on_parent(self, parent, width, height):
        try:
            self.update_idletasks()
            pw = parent.winfo_width() if parent.winfo_width() > 1 else width
            ph = parent.winfo_height() if parent.winfo_height() > 1 else height
            px = parent.winfo_x()
            py = parent.winfo_y()
            w = max(width, self.winfo_width())
            h = max(height, self.winfo_height())
            x = px + (pw - w) // 2
            y = py + max(20, (ph - h) // 2)
            self.geometry(f"{int(w)}x{int(h)}+{max(0, x)}+{max(0, y)}")
        except tk.TclError:
            try:
                self.geometry(f"{int(width)}x{int(height)}")
            except tk.TclError:
                pass

    def _on_theme_change(self, _choice, palette, _persist):
        """主题切换时刷新 MacToplevel 自身配色 + 调用子类的 refresh_palette。"""
        try:
            bg = to_tk_color(palette.CARD)
            self.configure(bg=bg)
            self.outer.configure(bg=bg)
            self.header.configure(bg=bg)
            self.body.configure(bg=bg)
            self.title_lbl.configure(bg=bg, fg=to_tk_color(palette.TEXT))
            for w in self._header_widgets:
                try:
                    w.configure(bg=bg)
                except tk.TclError:
                    pass
            for dot in (self._close_dot, self._minimize_dot, self._expand_dot):
                if dot is None:
                    continue
                try:
                    dot.refresh_palette(palette)
                except Exception:
                    pass
        except tk.TclError:
            pass

        try:
            self._apply_chrome()
        except Exception:
            pass

        refresh = getattr(self, "refresh_palette", None)
        if callable(refresh):
            try:
                refresh()
            except Exception:
                pass

    def refresh_palette(self):
        """子类覆盖此方法,刷新自己的内部 widget 配色。"""
        return None


__all__ = ["MacToplevel"]