"""胶囊进度条(_draw_capsule/_rounded_points)与 _row_color 的单元测试。"""
import types
import unittest

import ui.panel as panel
from ui.theme import Layout


def _make_canvas(root):
    import tkinter as tk
    return tk.Canvas(root, height=Layout.ROW_BAR_HEIGHT, highlightthickness=0)


def _make_widgets(bar):
    poly_kw = {"outline": "", "width": 0, "smooth": True,
               "splinesteps": 12, "state": "hidden"}
    return {
        "track": bar.create_polygon(0, 0, 0, 0, **poly_kw),
        "rect": bar.create_polygon(0, 0, 0, 0, **poly_kw),
    }


class RoundedPoints(unittest.TestCase):
    def test_shape(self):
        pts = panel._rounded_points(0, 0, 300, 12, 6)
        self.assertEqual(len(pts), 24)
        xs, ys = pts[0::2], pts[1::2]
        self.assertEqual(max(xs), 300)
        self.assertEqual(min(xs), 0)
        self.assertEqual(max(ys), 12)
        self.assertEqual(min(ys), 0)
        # 右边界 x2 必须能从偶数下标里读到(测试与 _fill_x2 都依赖这点)
        self.assertEqual(max(xs), 300)

    def test_corner_radius_is_half_height(self):
        r = Layout.ROW_BAR_HEIGHT / 2
        pts = panel._rounded_points(0, 0, 300, Layout.ROW_BAR_HEIGHT, r)
        self.assertIn(r, pts[1::2])
        self.assertIn(Layout.ROW_BAR_HEIGHT - r, pts[1::2])


class DrawCapsule(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import tkinter as tk
        cls.root = tk.Tk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def test_full_draw(self):
        bar = _make_canvas(self.root)
        w = _make_widgets(bar)
        panel._draw_capsule(bar, w, 300, 1.0, "#ff0000")
        self.assertEqual(max(bar.coords(w["rect"])[0::2]), 300)
        self.assertEqual(str(bar.itemcget(w["rect"], "state")), "normal")
        self.assertEqual(str(bar.itemcget(w["track"], "state")), "normal")
        self.assertEqual(max(bar.coords(w["track"])[0::2]), 300)

    def test_half_draw(self):
        bar = _make_canvas(self.root)
        w = _make_widgets(bar)
        panel._draw_capsule(bar, w, 300, 0.5, "#ff0000")
        self.assertEqual(max(bar.coords(w["rect"])[0::2]), 150)

    def test_tiny_frac_hidden(self):
        """不足一个圆头直径(12px)时不画,点集会出现反向坐标。"""
        bar = _make_canvas(self.root)
        w = _make_widgets(bar)
        panel._draw_capsule(bar, w, 300, 0.03, "#ff0000")
        self.assertEqual(str(bar.itemcget(w["rect"], "state")), "hidden")

    def test_zero_and_none_hidden(self):
        bar = _make_canvas(self.root)
        w = _make_widgets(bar)
        panel._draw_capsule(bar, w, 300, 0.0, "#ff0000")
        self.assertEqual(str(bar.itemcget(w["rect"], "state")), "hidden")
        panel._draw_capsule(bar, w, 300, None, "#ff0000")
        self.assertEqual(str(bar.itemcget(w["rect"], "state")), "hidden")

    def test_frac_clamped(self):
        bar = _make_canvas(self.root)
        w = _make_widgets(bar)
        panel._draw_capsule(bar, w, 300, 1.5, "#ff0000")
        self.assertEqual(max(bar.coords(w["rect"])[0::2]), 300)


class RowColor(unittest.TestCase):
    def test_ratio_not_none_uses_gradient(self):
        color, ratio = panel._row_color(
            {"unit": "%", "pct": 80, "level": "ok"})
        self.assertEqual(color, panel._usage_color(0.2))
        self.assertAlmostEqual(ratio, 0.2)

    def test_no_ratio_critical_uses_level_color(self):
        """deepseek 余额 ¥1:占比拿不到,但等级是 critical,数值不能灰。"""
        color, ratio = panel._row_color(
            {"unit": "¥", "remaining": 1.0, "total": None,
             "pct": None, "level": "critical"})
        self.assertEqual(color, panel.C["critical"])
        self.assertIsNone(ratio)

    def test_no_ratio_warn_uses_level_color(self):
        color, _ = panel._row_color(
            {"unit": "¥", "remaining": 3.0, "level": "warn"})
        self.assertEqual(color, panel.C["warn"])

    def test_no_ratio_ok_stays_off(self):
        color, ratio = panel._row_color(
            {"unit": "$", "remaining": 500.0, "level": "ok"})
        self.assertEqual(color, panel.C["off"])
        self.assertIsNone(ratio)

    def test_error_stays_off(self):
        color, ratio = panel._row_color(
            {"unit": "%", "pct": None, "error": "boom", "level": "error"})
        self.assertEqual(color, panel.C["off"])
        self.assertIsNone(ratio)

    def test_unconfigured_off(self):
        color, _ = panel._row_color({"unconfigured": True, "level": "unconfigured"})
        self.assertEqual(color, panel.C["off"])


class RebuildOnUnitChange(unittest.TestCase):
    """unit 进入重建签名:金额行首帧失败(unit="")建了胶囊,
    之后拿到 "$" 必须重建为无胶囊行,不能永久残留空条。"""

    @classmethod
    def setUpClass(cls):
        import tkinter as tk
        cls.root = tk.Tk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def _panel(self):
        import tkinter as tk
        actions = {"refresh_now": lambda: None, "toggle_pause": lambda: None,
                   "test_notify": lambda: None, "quit": lambda: None,
                   "save_position": lambda *a: None,
                   "save_size": lambda *a: None,
                   "save_order": lambda *a: None,
                   "save_pin": lambda *a: None, "get_order": lambda: [],
                   "open_config": lambda: None, "open_settings": lambda: None,
                   "add_key": lambda: None}
        toplevel = tk.Toplevel(self.root)
        self.addCleanup(toplevel.destroy)
        return panel.Panel(toplevel, self._state(), {}, actions)

    @staticmethod
    def _state():
        class _S:
            results = []
            paused = False
            paused_providers = set()
            fetching = False
            poll_error = None
            save_error = None
            next_fetch = 0.0
        return _S()

    @staticmethod
    def _result(unit):
        return {"name": "DS", "type": "deepseek", "unit": unit,
                "level": "ok", "remaining": 12.0, "used": None,
                "total": None, "pct": None, "detail": "d",
                "error": None, "updated_at": 1.0}

    def test_amount_row_rebuilt_without_bar(self):
        p = self._panel()
        p.stop()
        p.state.results = [self._result("")]
        p._update()
        self.assertIsNotNone(p._rows["DS"]["bar"])

        p.state.results = [self._result("$")]
        p._update()
        self.assertIsNone(p._rows["DS"]["bar"],
                          "unit 变化必须触发行重建,金额行不该残留胶囊")


class ThemeRefreshTrack(unittest.TestCase):
    """主题切换后胶囊轨道色必须跟着 PALETTE 走。

    canvas 的 bg 会被 refresh_palette 的 child 循环刷成卡片色,
    而轨道是 canvas 图元,configure(bg) 够不到——漏刷就是浅色主题
    残留深色轨道(AGENTS.md 规则 3 的坑)。
    """

    @classmethod
    def setUpClass(cls):
        import tkinter as tk
        cls.root = tk.Tk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def test_track_fill_follows_theme(self):
        import tkinter as tk
        from ui.theme import PALETTE, set_theme, to_tk_color
        set_theme("dark", broadcast=False)
        self.addCleanup(set_theme, "dark", broadcast=False, persist=False)

        actions = {"refresh_now": lambda: None, "toggle_pause": lambda: None,
                   "test_notify": lambda: None, "quit": lambda: None,
                   "save_position": lambda *a: None,
                   "save_size": lambda *a: None,
                   "save_order": lambda *a: None,
                   "save_pin": lambda *a: None, "get_order": lambda: [],
                   "open_config": lambda: None, "open_settings": lambda: None,
                   "add_key": lambda: None}
        toplevel = tk.Toplevel(self.root)
        self.addCleanup(toplevel.destroy)

        class _S:
            results = []
            paused = False
            paused_providers = set()
            fetching = False
            poll_error = None
            save_error = None
            next_fetch = 0.0

        state = _S()
        state.results = [{"name": "Z", "type": "zhipu", "unit": "%",
                          "level": "ok", "remaining": None, "used": None,
                          "total": None, "pct": 80, "detail": "d",
                          "error": None, "updated_at": 1.0}]
        p = panel.Panel(toplevel, state, {}, actions)
        p.stop()
        p._update()
        track = p._rows["Z"]["track"]
        self.assertIsNotNone(track)

        set_theme("light", broadcast=False)
        p.refresh_palette()
        # refresh_palette 末尾 _rebuild 会销毁重建所有行,旧图元引用作废;
        # 新行的 canvas 要等布局就绪(生产里是 1Hz tick + <Configure>)才重画。
        toplevel.update_idletasks()
        p._update()
        new_track = p._rows["Z"]["track"]
        self.assertIsNotNone(new_track)
        self.assertEqual(
            p._rows["Z"]["bar"].itemcget(new_track, "fill"),
            to_tk_color(PALETTE.BAR_BG),
            "主题切换后轨道色必须重设,否则浅色主题残留深色轨道")


class ValueCopy(unittest.TestCase):
    """点击行数值复制主值。

    背景:value_lbl 曾被漏在 drag_widgets 之外,is_value_click 恒 False,
    「点击数值复制」整个入口不可达。复制内容须是所见即所得的主值,
    而不是裸 remaining(% 行是小数甚至 None,会静默无反应)。
    """

    @classmethod
    def setUpClass(cls):
        import tkinter as tk
        cls.root = tk.Tk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def _panel(self, result):
        import tkinter as tk
        actions = {"refresh_now": lambda: None, "toggle_pause": lambda: None,
                   "test_notify": lambda: None, "quit": lambda: None,
                   "save_position": lambda *a: None,
                   "save_size": lambda *a: None,
                   "save_order": lambda *a: None,
                   "save_pin": lambda *a: None, "get_order": lambda: [],
                   "open_config": lambda: None, "open_settings": lambda: None,
                   "add_key": lambda: None}
        toplevel = tk.Toplevel(self.root)
        self.addCleanup(toplevel.destroy)

        class _S:
            paused = False
            paused_providers = set()
            fetching = False
            poll_error = None
            save_error = None
            next_fetch = 0.0

        state = _S()
        state.results = [result]
        p = panel.Panel(toplevel, state, {}, actions)
        self.addCleanup(p.stop)
        p._update()
        return p

    def test_click_value_copies_display_string(self):
        p = self._panel({"name": "Z", "type": "zhipu", "unit": "%",
                         "level": "ok", "remaining": None, "used": None,
                         "total": None, "pct": 73, "detail": "d",
                         "error": None, "updated_at": 1.0})
        value = p._rows["Z"]["value"]
        press = types.SimpleNamespace(widget=value, x_root=0, y_root=0)
        p._drag_press(press, "Z")
        release = types.SimpleNamespace(widget=value, x_root=0, y_root=0)
        p._drag_release(release, "Z")
        self.assertEqual(p.root.clipboard_get(), "已用 27%",
                         "复制的是展示主值,不是裸 remaining")

    def test_click_non_value_widget_does_not_copy(self):
        p = self._panel({"name": "Z", "type": "zhipu", "unit": "%",
                         "level": "ok", "remaining": None, "used": None,
                         "total": None, "pct": 73, "detail": "d",
                         "error": None, "updated_at": 1.0})
        # 剪贴板进程级共享:上个用例可能留了同样的内容,先清空
        p.root.clipboard_clear()
        p.root.update()
        card = p._rows["Z"]["frame"]
        press = types.SimpleNamespace(widget=card, x_root=0, y_root=0)
        p._drag_press(press, "Z")
        release = types.SimpleNamespace(widget=card, x_root=0, y_root=0)
        p._drag_release(release, "Z")
        try:
            text = p.root.clipboard_get()
        except Exception:
            text = ""
        self.assertNotEqual(text, "已用 27%",
                            "点行卡片空白区不该触发复制")


class ThemeKeepsScroll(unittest.TestCase):
    """refresh_palette 的 _rebuild 不得把列表滚回顶部。"""

    @classmethod
    def setUpClass(cls):
        import tkinter as tk
        cls.root = tk.Tk()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def test_scroll_position_survives_refresh(self):
        import tkinter as tk

        def _row(i):
            return {"name": f"p{i}", "type": "zhipu", "unit": "%",
                    "level": "ok", "remaining": None, "used": None,
                    "total": None, "pct": 50, "detail": "d",
                    "error": None, "updated_at": 1.0}

        actions = {"refresh_now": lambda: None, "toggle_pause": lambda: None,
                   "test_notify": lambda: None, "quit": lambda: None,
                   "save_position": lambda *a: None,
                   "save_size": lambda *a: None,
                   "save_order": lambda *a: None,
                   "save_pin": lambda *a: None, "get_order": lambda: [],
                   "open_config": lambda: None, "open_settings": lambda: None,
                   "add_key": lambda: None}
        toplevel = tk.Toplevel(self.root)
        toplevel.geometry("320x400")
        self.addCleanup(toplevel.destroy)

        class _S:
            paused = False
            paused_providers = set()
            fetching = False
            poll_error = None
            save_error = None
            next_fetch = 0.0

        state = _S()
        state.results = [_row(i) for i in range(40)]
        p = panel.Panel(toplevel, state, {}, actions)
        self.addCleanup(p.stop)
        toplevel.update_idletasks()
        p._update()
        canvas = p.rows_canvas
        canvas.yview_moveto(0.5)
        toplevel.update_idletasks()
        before = canvas.yview()[0]
        self.assertGreater(before, 0.3, "前置条件:40 行列表必须可滚动")
        p.refresh_palette()
        toplevel.update_idletasks()
        after = canvas.yview()[0]
        self.assertGreater(after, 0.3,
                           "主题刷新(_rebuild)后滚动位置不得跳回顶部")


if __name__ == "__main__":
    unittest.main()
