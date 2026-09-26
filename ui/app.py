"""macOS 风格窗口壳 + essential / standard 两态管理。

职责:
- 接管 Tk root,加 macOS 交通灯 + 标题 + DWM 圆角 + 系统级 backdrop
- 提供 standard / essential 两个槽位,装载不同视图
- 两态切换:几何尺寸 + min/max + 可见性 + 持久化
- 绿点交通灯打开设置对话框(按下 → SettingsDialog)
- 窗口拖拽边缘磁吸

设计:
- 不替换 tk.Tk(),仅在原 root 上叠加修饰
- 任何修饰失败都软降级,不阻塞主流程
- 与 ui.panel.Panel / ui.essential_bar.EssentialBar 完全兼容,
  它们各自管理自己的子控件,MacWindow 只管哪个可见
"""

import tkinter as tk

from ui.theme import PALETTE, Layout, set_theme, current_choice, on_theme_change, to_tk_color
from ui.fonts import fonts
from ui.vibrancy import apply_window_chrome


MODE_STANDARD = "standard"
MODE_ESSENTIAL = "essential"


class TrafficLight(tk.Canvas):
    """macOS 风格的圆点按钮。无 hover 效果,鼠标变手型表示可点击。"""

    def __init__(self, parent, kind, color, command, size=None):
        size = size or Layout.TRAFFIC_DOT
        super().__init__(
            parent,
            width=size, height=size,
            highlightthickness=0, bd=0,
            bg=PALETTE.BG,
            cursor="hand2",
        )
        self._size = size
        self._kind = kind
        self._color = color
        self._command = command
        self._is_header_dot = True
        self._dot = self.create_oval(1, 1, size - 1, size - 1,
                                     fill=color, outline="")
        self.bind("<Button-1>", self._on_click)

    def _on_click(self, _e=None):
        if self._command:
            try:
                self._command()
            except Exception:
                pass

    def refresh_palette(self, palette=None):
        """主题切换时由父组件调用,刷新画布 bg + 圆点 fill。"""
        palette = palette or PALETTE
        try:
            self.configure(bg=to_tk_color(palette.BG))
        except tk.TclError:
            pass
        fill_map = {
            "close": palette.TRAFFIC_RED,
            "minimize": palette.TRAFFIC_YELLOW,
            "settings": palette.TRAFFIC_GREEN,
        }
        try:
            self.itemconfig(self._dot, fill=fill_map.get(self._kind, self._color))
        except tk.TclError:
            pass


class MacHeader(tk.Frame):
    """macOS 风标题栏:中间标题,右侧三个交通灯 [黄(最小化) 绿(设置) 红(退出)]。

    标题位置根据右集群实际宽度做加权补偿,放在"左半区"的中点。
    """

    def __init__(self, parent, title, actions, fonts_dict,
                 on_drag_start, on_drag_motion):
        super().__init__(parent, bg=PALETTE.BG, height=Layout.HEADER_HEIGHT)
        self.pack_propagate(False)
        self._actions = actions or {}
        self._fonts_dict = fonts_dict

        right = tk.Frame(self, bg=PALETTE.BG)
        right.pack(side="right", padx=(0, Layout.PAD_X),
                   pady=(Layout.HEADER_HEIGHT - Layout.TRAFFIC_DOT) / 2)

        # 从右往左 pack → 视觉上从左到右是 [黄, 绿, 红]
        self.red_dot = TrafficLight(right, "close", PALETTE.TRAFFIC_RED,
                                    actions.get("quit"))
        self.red_dot.pack(side="right")

        self.settings_dot = TrafficLight(right, "settings", PALETTE.TRAFFIC_GREEN,
                                         actions.get("open_settings"))
        self.settings_dot.pack(side="right", padx=(0, Layout.TRAFFIC_GAP))

        self.yellow_dot = TrafficLight(right, "minimize", PALETTE.TRAFFIC_YELLOW,
                                       actions.get("minimize"))
        self.yellow_dot.pack(side="right", padx=(0, Layout.TRAFFIC_GAP))

        self.title_lbl = tk.Label(
            self, text=title, font=fonts_dict["title"],
            fg=to_tk_color(PALETTE.TEXT), bg=to_tk_color(PALETTE.BG),
        )
        # 默认占位,after_idle 时按真实宽度重摆,避免构造时 winfo_width=1
        self.title_lbl.place(relx=0.5, rely=0.5, anchor="center")

        for w in (self, self.title_lbl, right):
            w.bind("<Button-1>", on_drag_start, add="+")
            w.bind("<B1-Motion>", on_drag_motion, add="+")

        self._right_cluster = right
        self.bind("<Configure>", lambda _e: self.after_idle(self._reposition_title))
        self.after_idle(self._reposition_title)

    def _reposition_title(self):
        """把标题放在 [左边缘, 右集群起点] 的中点,补偿右集群宽度。"""
        try:
            if not self.winfo_exists():
                return
            header_w = self.winfo_width()
            right_x = self._right_cluster.winfo_x()
        except tk.TclError:
            return
        if header_w <= 1:
            return
        relx = (right_x / 2) / header_w
        try:
            self.title_lbl.place(relx=relx, rely=0.5, anchor="center")
        except tk.TclError:
            pass


class MacWindow:
    """两态窗口:standard 主面板 / essential 单行条带。

    用法:
        root = tk.Tk()
        mac = MacWindow(root, cfg, actions)
        panel = Panel(mac.standard_slot, state, cfg, actions, root_window=root)
        bar = EssentialBar(mac.essential_slot, state, cfg, mac.fonts_dict,
                           on_expand=mac.toggle_mode)
        mac.show_initial_mode()
        root.mainloop()
    """

    def __init__(self, root, cfg, actions):
        self.root = root
        self.cfg = cfg or {}
        self.actions = actions or {}
        self._pinned = bool((self.cfg.get("ui") or {}).get("pinned", True))
        self._mode = (self.cfg.get("ui") or {}).get("mode", MODE_STANDARD)
        if self._mode not in (MODE_STANDARD, MODE_ESSENTIAL):
            self._mode = MODE_STANDARD

        self.fonts_dict = fonts(root)

        root.title("AgentEye")
        root.overrideredirect(True)
        root.attributes("-topmost", self._pinned)
        root.configure(bg=PALETTE.BG)
        self._apply_chrome()

        self.outer = tk.Frame(root, bg=PALETTE.BG)
        self.outer.pack(fill="both", expand=True)

        self.header = MacHeader(
            self.outer, "AgentEye", self._safe_actions(),
            self.fonts_dict,
            on_drag_start=self._drag_start,
            on_drag_motion=self._drag_motion,
        )
        self.header.pack(fill="x", side="top")

        self.body = tk.Frame(self.outer, bg=PALETTE.BG)
        self.body.pack(fill="both", expand=True)

        self.standard_slot = tk.Frame(self.body, bg=PALETTE.BG)
        self.essential_slot = tk.Frame(self.body, bg=PALETTE.BG)

        self.standard_attached = None
        self.essential_attached = None

        self._drag_active = False
        self._bind_global_drag()

        on_theme_change(self._on_theme_change)

    def _on_theme_change(self, choice, palette, persist):
        """主题切换回调:重画 root/header/body/slots + 所有交通灯 + view.refresh_palette。"""
        try:
            bg = to_tk_color(palette.BG)
            self.root.configure(bg=bg)
            self.outer.configure(bg=bg)
            self.body.configure(bg=bg)
            self.standard_slot.configure(bg=bg)
            self.essential_slot.configure(bg=bg)
            self.header.configure(bg=bg)
            try:
                self.header.title_lbl.configure(bg=bg, fg=to_tk_color(palette.TEXT))
            except tk.TclError:
                pass
            for f in self.header.winfo_children():
                try:
                    f.configure(bg=bg)
                except tk.TclError:
                    pass
                # 第二层:刷新所有交通灯的画布 bg,修复浅色主题残留深色方框
                for sub in f.winfo_children():
                    if isinstance(sub, TrafficLight):
                        try:
                            sub.refresh_palette(palette)
                        except Exception:
                            pass
        except tk.TclError:
            pass
        for view in (self.standard_attached, self.essential_attached):
            if view is None:
                continue
            refresh = getattr(view, "refresh_palette", None)
            if callable(refresh):
                try:
                    refresh(choice, palette, persist)
                except Exception:
                    pass
        self._apply_chrome()

    def attach_standard(self, view):
        self.standard_attached = view

    def attach_essential(self, view):
        self.essential_attached = view

    def show_initial_mode(self):
        self._apply_mode(self._mode, animate=False)

    @property
    def mode(self):
        return self._mode

    def toggle_mode(self):
        new_mode = MODE_ESSENTIAL if self._mode == MODE_STANDARD else MODE_STANDARD
        self._apply_mode(new_mode, animate=True)

    def _apply_mode(self, mode, animate=False):
        if mode not in (MODE_STANDARD, MODE_ESSENTIAL):
            mode = MODE_STANDARD

        self._mode = mode
        if mode == MODE_STANDARD:
            self._show_standard()
        else:
            self._show_essential()

        self._resize_for_mode(mode)
        self._persist_mode(mode)

    def _show_standard(self):
        try:
            self.essential_slot.pack_forget()
        except tk.TclError:
            pass
        if self.standard_attached is not None:
            inner = self._view_root(self.standard_attached)
            try:
                inner.pack(fill="both", expand=True)
            except tk.TclError:
                pass

    def _show_essential(self):
        try:
            if self.standard_attached is not None:
                inner = self._view_root(self.standard_attached)
                try:
                    inner.pack_forget()
                except tk.TclError:
                    pass
        except tk.TclError:
            pass
        if self.essential_attached is not None:
            inner = self._view_root(self.essential_attached)
            try:
                inner.pack(fill="both", expand=True)
            except tk.TclError:
                pass

    @staticmethod
    def _view_root(view):
        """取得视图的最外层 Frame。

        Panel 的最外层是 ``self.root``(在 mac 模式下是被传入的 Frame);
        EssentialBar 的最外层是 ``self.frame``。
        """
        for attr in ("frame", "root"):
            if hasattr(view, attr):
                cand = getattr(view, attr)
                if isinstance(cand, tk.Misc):
                    return cand
        return view

    def _resize_for_mode(self, mode):
        ui = self.cfg.setdefault("ui", {})
        try:
            x = self.root.winfo_x()
            y = self.root.winfo_y()
        except tk.TclError:
            x = ui.get("x") or 100
            y = ui.get("y") or 100

        if mode == MODE_ESSENTIAL:
            w = Layout.ESSENTIAL_W
            h = Layout.HEADER_HEIGHT + Layout.ESSENTIAL_H
            try:
                self.root.minsize(w, h)
                self.root.maxsize(w, h)
            except tk.TclError:
                pass
            try:
                self.root.geometry(f"{w}x{h}+{x}+{y}")
            except tk.TclError:
                pass
        else:
            w = ui.get("width") or 360
            h = ui.get("height") or 360
            try:
                self.root.minsize(Layout.MIN_W, Layout.MIN_H)
                self.root.maxsize(Layout.MAX_W, Layout.MAX_H)
            except tk.TclError:
                pass
            try:
                self.root.geometry(f"{int(w)}x{int(h)}+{x}+{y}")
            except tk.TclError:
                pass

    def _persist_mode(self, mode):
        ui = self.cfg.setdefault("ui", {})
        ui["mode"] = mode
        save_v2 = (self.actions or {}).get("save_ui")
        if save_v2:
            try:
                save_v2(dict(self.cfg))
            except Exception:
                pass

    def apply_theme(self, name, broadcast=True, persist=True):
        """对外接口:切换主题并广播。

        name ∈ {"dark","light","auto"}。返回实际生效的 palette key。
        """
        resolved = set_theme(name, broadcast=broadcast, persist=persist)
        return resolved

    def _safe_actions(self):
        a = dict(self.actions or {})
        if "toggle_mode" not in a:
            a["toggle_mode"] = self.toggle_mode
        if "minimize" not in a:
            a["minimize"] = self._stub_minimize
        if "quit" not in a:
            a["quit"] = self._stub_quit
        return a

    def _stub_minimize(self):
        try:
            self.root.overrideredirect(False)
            self.root.iconify()
        except tk.TclError:
            pass

    def _stub_quit(self):
        quit_fn = (self.actions or {}).get("quit")
        if quit_fn:
            try:
                quit_fn()
                return
            except Exception:
                pass
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def _apply_chrome(self):
        try:
            self.root.update_idletasks()
            apply_window_chrome(self.root, dark=PALETTE.IS_DARK)
        except Exception:
            pass

    def _drag_start(self, event):
        if not self._is_window_drag_target(event.widget):
            self._drag_active = False
            return
        self._drag_active = True
        self._drag_ox = event.x_root - self.root.winfo_x()
        self._drag_oy = event.y_root - self.root.winfo_y()

    def _drag_motion(self, event):
        if not self._drag_active:
            return
        x = event.x_root - self._drag_ox
        y = event.y_root - self._drag_oy
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        if x < Layout.EDGE_SNAP:
            x = 0
        elif sw - x < Layout.EDGE_SNAP:
            x = sw - self.root.winfo_width()
        if y < Layout.EDGE_SNAP:
            y = 0
        elif sh - y < Layout.EDGE_SNAP:
            y = sh - self.root.winfo_height()
        self.root.geometry(f"+{x}+{y}")

    def _drag_end(self, _event=None):
        if self._drag_active:
            self._drag_active = False
            save_pos = (self.actions or {}).get("save_position")
            if save_pos:
                try:
                    save_pos(self.root.winfo_x(), self.root.winfo_y())
                except Exception:
                    pass

    def _is_window_drag_target(self, widget):
        w = widget
        while w is not None:
            if isinstance(w, tk.Button):
                return False
            if w.winfo_class() == "Button":
                return False
            if getattr(w, "_provider_name", None):
                return False
            if getattr(w, "_is_header_dot", False):
                return False
            w = getattr(w, "master", None)
        return True

    def _bind_global_drag(self):
        self.root.bind("<ButtonRelease-1>", self._drag_end, add="+")


def build_mac_window(root, cfg, actions):
    return MacWindow(root, cfg, actions)


__all__ = ["MacWindow", "MacHeader", "TrafficLight", "build_mac_window",
           "MODE_STANDARD", "MODE_ESSENTIAL"]
