"""测试 panel.Panel 的滚动条结构和 header 字符。"""
import unittest
from unittest import mock

import tkinter as tk

import ui.panel as panel_mod


class PanelStructure(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._root = tk.Tk()
        cls._root.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls._root.destroy()

    def _make_panel(self):
        cfg = {
            "schema_version": 2,
            "refresh_interval_sec": 30,
            "ui": {"x": 100, "y": 100, "width": 360, "height": 360,
                    "pinned": True, "order": []},
            "providers": [],
            "alert": {},
            "aggregate": {},
        }
        state = mock.MagicMock()
        state.results = []
        state.paused = False
        state.fetching = False
        state.next_fetch = 0
        actions = {
            "refresh_now": lambda: None,
            "toggle_pause": lambda: None,
            "test_notify": lambda: None,
            "quit": lambda: None,
            "save_position": lambda *a: None,
            "save_size": lambda *a: None,
            "save_order": lambda *a: None,
            "save_pin": lambda *a: None,
            "get_order": lambda: [],
            "open_settings": lambda: None,
            "add_key": lambda: None,
            "open_config": lambda: None,
        }
        root = tk.Toplevel(self._root)
        p = panel_mod.Panel(root, state, cfg, actions)
        root.update_idletasks()
        self.addCleanup(root.destroy)
        return p

    def test_rows_canvas_exists(self):
        p = self._make_panel()
        self.assertIsInstance(p.rows_canvas, tk.Canvas)

    def test_rows_frame_embedded_in_canvas(self):
        p = self._make_panel()
        window_ids = [i for i in p.rows_canvas.find_all()
                      if p.rows_canvas.type(i) == "window"]
        self.assertGreaterEqual(len(window_ids), 1)

    def test_scrollbar_attached(self):
        p = self._make_panel()
        self.assertIsInstance(p.rows_scroll, tk.Scrollbar)

    def test_wheel_handlers_exist(self):
        p = self._make_panel()
        for name in ("_rows_wheel_enter", "_rows_wheel_leave",
                     "_on_rows_wheel", "_on_rows_canvas_configure"):
            self.assertTrue(callable(getattr(p, name, None)),
                            f"missing {name}")

    def test_header_gear_char(self):
        p = self._make_panel()
        self.assertEqual(p.gear_btn.cget("text"), "≡")

    def test_header_pin_char_pinned(self):
        p = self._make_panel()
        self.assertEqual(p.pin_btn.cget("text"), "⊙")

    def test_no_plus_button_in_header(self):
        p = self._make_panel()
        for btn in (p.gear_btn, p.pin_btn):
            self.assertNotEqual(btn.cget("text"), "+")

    def test_button_width_forces_equal(self):
        p = self._make_panel()
        self.assertEqual(p.gear_btn.cget("width"), 1)
        self.assertEqual(p.pin_btn.cget("width"), 1)


class RebuildRepaint(unittest.TestCase):
    """回归:拖动行触发 _rebuild 后,数据未变也必须立即重绘,不能停在 "…"。"""

    @classmethod
    def setUpClass(cls):
        cls._root = tk.Tk()
        cls._root.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls._root.destroy()

    def _make_panel(self):
        cfg = {
            "schema_version": 2,
            "refresh_interval_sec": 30,
            "ui": {"x": 100, "y": 100, "width": 360, "height": 360,
                    "pinned": True, "order": []},
            "providers": [],
            "alert": {},
            "aggregate": {},
        }
        state = mock.MagicMock()
        state.results = []
        state.paused = False
        state.fetching = False
        state.next_fetch = 0
        actions = {
            "refresh_now": lambda: None,
            "toggle_pause": lambda: None,
            "test_notify": lambda: None,
            "quit": lambda: None,
            "save_position": lambda *a: None,
            "save_size": lambda *a: None,
            "save_order": lambda *a: None,
            "save_pin": lambda *a: None,
            "get_order": lambda: [],
            "open_settings": lambda: None,
            "add_key": lambda: None,
            "open_config": lambda: None,
        }
        root = tk.Toplevel(self._root)
        p = panel_mod.Panel(root, state, cfg, actions)
        root.update_idletasks()
        self.addCleanup(root.destroy)
        return p

    _RESULT = {"name": "A", "type": "t", "unit": "", "level": "ok",
               "remaining": 12.5, "total": 100, "pct": None,
               "detail": "detail-text", "error": "", "updated_at": 1}

    def test_rebuild_clears_last_paint(self):
        p = self._make_panel()
        p._last_paint = {"A": ("stale",)}
        p._rebuild([dict(self._RESULT)])
        self.assertEqual(p._last_paint, {})

    def test_row_not_stuck_at_placeholder_after_rebuild(self):
        p = self._make_panel()
        p.state.results = [dict(self._RESULT)]
        p._update()
        value = p._rows["A"]["value"]
        self.assertNotEqual(value.cget("text"), "…")
        p._sig = None
        p._update()
        value = p._rows["A"]["value"]
        self.assertNotEqual(value.cget("text"), "…")
        self.assertEqual(value.cget("text"), "12.50")


if __name__ == "__main__":
    unittest.main()
