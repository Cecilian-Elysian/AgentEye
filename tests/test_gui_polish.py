"""批次 4 GUI 打磨的行为测试。

- essential 条带胶囊化:轨道/填充是 12 点圆角 polygon,宽度语义
  与行内条一致(不足圆头直径不画)
- 缓动动画:数据跳变时条滑向目标,收敛后回到 1Hz;颜色切换直接到位
- TrafficLight hover 提亮,主题刷新后 _color 同步(Leave 恢复成新色)
- RowMenu PALETTE 配色
- tooltip:有文本弹、无文本不弹、Leave 收掉
- 复制反馈闪烁(ok 绿 → 恢复)
"""
import time
import unittest
import tkinter as tk

import ui.panel as panel
import ui.essential_bar as eb
from ui.fonts import fonts
from ui.theme import PALETTE, Layout, to_tk_color, set_theme


def _actions():
    return {"refresh_now": lambda: None, "toggle_pause": lambda: None,
            "test_notify": lambda: None, "quit": lambda: None,
            "save_position": lambda *a: None, "save_size": lambda *a: None,
            "save_order": lambda *a: None, "save_pin": lambda *a: None,
            "get_order": lambda: [], "open_config": lambda: None,
            "open_settings": lambda: None, "add_key": lambda: None}


class _State:
    def __init__(self, results=None):
        self.results = results or []
        self.paused = False
        self.paused_providers = set()
        self.fetching = False
        self.poll_error = None
        self.save_error = None
        self.next_fetch = 0.0


def _pct_result(pct, name="Z"):
    return {"name": name, "type": "zhipu", "unit": "%", "level": "ok",
            "remaining": None, "used": None, "total": None, "pct": pct,
            "detail": "d", "error": None, "updated_at": 1.0}


class EssentialCapsule(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tk.Tk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def _bar(self, results):
        holder = tk.Frame(self.root)
        self.addCleanup(holder.destroy)
        bar = eb.EssentialBar(holder, _State(results), {}, fonts(self.root))
        self.addCleanup(bar.stop)
        return bar

    def test_bar_items_are_rounded_polygons(self):
        bar = self._bar([_pct_result(80)])
        bar._on_bar_configure(types_None := type("E", (), {"width": 200})())
        self.assertEqual(
            len(bar.bar_canvas.coords(bar.bar_track)) // 2, 12,
            "essential 条带轨道必须是 12 点圆角 polygon")

    def test_tiny_frac_hides_fill(self):
        bar = self._bar([_pct_result(99.8)])
        bar._update()
        bar._on_bar_configure(type("E", (), {"width": 200})())
        self.assertEqual(str(bar.bar_canvas.itemcget(bar.bar_rect, "state")),
                         "hidden", "不足圆头直径时不画填充")

    def test_fill_width_matches_frac(self):
        bar = self._bar([_pct_result(70)])
        bar._update()   # ratio = 0.3,disp 初次直接到位
        bar._on_bar_configure(type("E", (), {"width": 200})())
        x2 = max(bar.bar_canvas.coords(bar.bar_rect)[0::2])
        self.assertEqual(x2, 60)


class EssentialEasing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tk.Tk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def _bar(self, results):
        holder = tk.Frame(self.root)
        self.addCleanup(holder.destroy)
        bar = eb.EssentialBar(holder, _State(results), {}, fonts(self.root))
        self.addCleanup(bar.stop)
        return bar

    def test_eases_toward_target_then_settles(self):
        bar = self._bar([_pct_result(100)])
        bar._update()
        self.assertAlmostEqual(bar._bar_target, 0.0)
        self.assertFalse(bar._animating)

        bar.state.results = [_pct_result(50)]
        bar._update()
        self.assertAlmostEqual(bar._bar_target, 0.5)
        self.assertTrue(bar._animating, "目标跳变后应处于动画中")
        self.assertLess(bar._disp_frac, 0.5)

        for _ in range(40):
            bar._update()
        self.assertFalse(bar._animating, "缓动必须收敛")
        self.assertAlmostEqual(bar._disp_frac, 0.5, places=3)

    def test_first_paint_jumps_directly(self):
        bar = self._bar([_pct_result(30)])
        bar._update()
        self.assertAlmostEqual(bar._disp_frac, bar._bar_target)
        self.assertFalse(bar._animating)


class RowBarEasing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tk.Tk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def _panel(self, results):
        toplevel = tk.Toplevel(self.root)
        self.addCleanup(toplevel.destroy)
        p = panel.Panel(toplevel, _State(results), {}, _actions())
        p.stop()
        self.addCleanup(p._anim_rows.clear)
        return p

    def test_paint_row_animates_and_converges(self):
        p = self._panel([_pct_result(100)])
        p._update()
        w = p._rows["Z"]
        w["bar"].configure(width=200, height=Layout.ROW_BAR_HEIGHT)
        p.root.update_idletasks()
        p._paint_row(w, _pct_result(100))
        self.assertNotIn("Z", p._anim_rows)

        # 目标跳变:disp 应介于旧值与新目标之间,且登记动画中
        r2 = _pct_result(50)
        p._paint_row(w, r2)
        self.assertIn("Z", p._anim_rows)
        self.assertLess(w["_anim_frac"], 0.5)

        for _ in range(40):
            p._paint_row(w, r2)
        self.assertNotIn("Z", p._anim_rows)
        self.assertAlmostEqual(w["_anim_frac"], 0.5, places=3)

    def test_color_updates_immediately_while_position_eases(self):
        p = self._panel([_pct_result(100)])   # 已用 0%,条空,绿色
        p._update()
        w = p._rows["Z"]
        w["bar"].configure(width=200, height=Layout.ROW_BAR_HEIGHT)
        p.root.update_idletasks()
        p._paint_row(w, _pct_result(100))
        # pct 100 → 0:颜色(目标色)立即更新,位置仍从 0 开始滑
        p._paint_row(w, _pct_result(0))
        self.assertIn("Z", p._anim_rows)
        self.assertGreater(w["_anim_frac"], 0.0)
        self.assertEqual(w["_bar_color"], panel._usage_color(1.0))


class TrafficLightHover(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tk.Tk()
        # Enter/Leave 合成事件只投递给已映射的窗口,不能 withdraw
        cls.root.geometry("120x60+0+0")

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def test_hover_brightens_and_restores(self):
        from ui.app import TrafficLight
        holder = tk.Frame(self.root, bg=to_tk_color(PALETTE.BG))
        holder.pack()
        dot = TrafficLight(holder, "close", PALETTE.TRAFFIC_RED,
                           lambda: None)
        dot.pack()
        self.root.update()
        base = str(dot.itemcget(dot._dot, "fill"))
        dot.event_generate("<Enter>")
        self.assertEqual(str(dot.itemcget(dot._dot, "fill")),
                         dot._hover_fill())
        self.assertNotEqual(str(dot.itemcget(dot._dot, "fill")), base)
        dot.event_generate("<Leave>")
        self.assertEqual(str(dot.itemcget(dot._dot, "fill")), base)

    def test_refresh_palette_updates_hover_base(self):
        from ui.app import TrafficLight
        set_theme("dark", broadcast=False)
        self.addCleanup(set_theme, "dark", broadcast=False, persist=False)
        holder = tk.Frame(self.root, bg=to_tk_color(PALETTE.BG))
        holder.pack()
        dot = TrafficLight(holder, "close", PALETTE.TRAFFIC_RED,
                           lambda: None)
        dot.pack()
        set_theme("light", broadcast=False)
        dot.refresh_palette()
        self.assertEqual(dot._color, PALETTE.TRAFFIC_RED,
                         "主题刷新后 _color 必须换成新调色板的值,"
                         "否则 Leave 会恢复成旧主题的色")
        self.assertEqual(str(dot.itemcget(dot._dot, "fill")),
                         str(PALETTE.TRAFFIC_RED))


class MenuPalette(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tk.Tk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def test_row_menu_uses_palette(self):
        from ui.row_menu import RowMenu
        menu = RowMenu(
            self.root,
            on_refresh=lambda: None, on_pause=lambda: None,
            on_edit=lambda: None, on_delete=lambda: None,
            on_copy_key=lambda: None, on_copy_url=lambda: None,
            on_show_models=lambda: None, on_probe=lambda: None)
        self.assertEqual(str(menu.menu.cget("bg")),
                         to_tk_color(PALETTE.CARD))
        self.assertEqual(str(menu.menu.cget("activebackground")),
                         to_tk_color(PALETTE.CARD_HOVER))

    def test_main_menu_uses_palette(self):
        toplevel = tk.Toplevel(self.root)
        self.addCleanup(toplevel.destroy)
        p = panel.Panel(toplevel, _State(), {}, _actions())
        p.stop()
        m = p._build_menu()
        self.assertEqual(str(m.cget("bg")), panel.C["card"])


class Tooltip(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tk.Tk()
        # Enter/Leave 合成事件只投递给已映射的窗口,不能 withdraw
        cls.root.geometry("160x60+0+0")

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def _pump_until(self, pred, timeout=2.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            self.root.update()
            if pred():
                return True
            time.sleep(0.01)
        return False

    def test_shows_and_hides(self):
        from ui import tooltip as tip_mod
        lbl = tk.Label(self.root, text="hover me")
        lbl.pack()
        self.root.update()
        toplevels = lambda: [w for w in self.root.winfo_children()
                             if isinstance(w, tk.Toplevel)]
        hide = tip_mod.attach(lbl, lambda: "tip text", delay_ms=1,
                              owner=self.root)
        try:
            lbl.event_generate("<Enter>")
            self.assertTrue(
                self._pump_until(lambda: len(toplevels()) == 1),
                "有文本时 tooltip 应弹出")
            lbl.event_generate("<Leave>")
            self.assertTrue(
                self._pump_until(lambda: len(toplevels()) == 0),
                "Leave 后 tooltip 应销毁")
        finally:
            hide()

    def test_no_text_no_popup(self):
        from ui import tooltip as tip_mod
        lbl = tk.Label(self.root, text="hover me")
        lbl.pack()
        toplevels = lambda: [w for w in self.root.winfo_children()
                             if isinstance(w, tk.Toplevel)]
        hide = tip_mod.attach(lbl, lambda: None, delay_ms=1,
                              owner=self.root)
        try:
            lbl.event_generate("<Enter>")
            deadline = time.time() + 0.3
            while time.time() < deadline:
                self.root.update()
                time.sleep(0.01)
            self.assertEqual(len(toplevels()), 0, "无文本时不应弹窗")
        finally:
            hide()


class CopyFlash(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tk.Tk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def _pump_until(self, pred, timeout=2.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            self.root.update()
            if pred():
                return True
            time.sleep(0.01)
        return False

    def test_copy_value_flashes_green_then_restores(self):
        toplevel = tk.Toplevel(self.root)
        self.addCleanup(toplevel.destroy)
        state = _State([_pct_result(73, name="K")])
        p = panel.Panel(toplevel, state, {}, _actions())
        p.stop()
        p._update()
        value = p._rows["K"]["value"]
        orig = value.cget("fg")

        p.root.clipboard_clear()
        p._copy_value("K")
        self.assertEqual(value.cget("fg"), panel.C["ok"])
        self.assertTrue(
            self._pump_until(lambda: value.cget("fg") == orig),
            "450ms 后数值前景色应恢复")

    def test_copy_key_flashes_name_label(self):
        toplevel = tk.Toplevel(self.root)
        self.addCleanup(toplevel.destroy)
        # 行数据也要给:Panel 只按 state.results 建行,cfg 里的
        # providers 只供 _copy_key 查 key
        state = _State([_pct_result(100, name="K")])
        cfg = {"version": 2, "providers": [
            {"id": "p1", "kind": "deepseek", "name": "K",
             "key": "sk-test", "base_url": "https://x", "extra": {}}],
            "ui": {}, "alert": {}}
        p = panel.Panel(toplevel, state, cfg, _actions())
        p.stop()
        p._update()
        name_lbl = p._rows["K"]["name"]
        orig = name_lbl.cget("fg")

        p._copy_key("K")
        self.assertEqual(name_lbl.cget("fg"), panel.C["ok"])
        self.assertTrue(
            self._pump_until(lambda: name_lbl.cget("fg") == orig))


if __name__ == "__main__":
    unittest.main()
