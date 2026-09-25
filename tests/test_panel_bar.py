"""回归测试:row 进度条首帧渲染。

之前 ``panel._paint_row`` 用 ``bar.winfo_width() or 300`` 兜底,但 ``1 or 300 == 1``
(Tk 在 pack 当下 winfo_width=1),导致 rect 几乎不可见,需等到下一次 fetch
(updated_at 变 → 缓存 miss)才修正。

修复方案:bar 绑 ``<Configure>``,handler 在 Tk 布局完成后用 ``event.width``
(永远正确)重画 rect。同时 ``_paint_row`` 内即时绘制的兜底阈值改为
``width >= 2``。

这两个测试在**不调用** ``update_idletasks`` 的前提下,
1. 模拟首帧(rebuild 后立即 _update),断言 bar rect 坐标与 bar 实际宽度一致
2. resize 后断言 bar rect 跟随新宽度
"""
import unittest
from unittest import mock

import tkinter as tk

import ui.panel as panel_mod


def _make_panel(root):
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
    toplevel = tk.Toplevel(root)
    p = panel_mod.Panel(toplevel, state, cfg, actions)
    return p, toplevel


_PCT_RESULT = {"name": "Z", "type": "zhipu", "unit": "%", "level": "ok",
               "remaining": None, "used": None, "total": None,
               "pct": 80, "detail": "5h 80%", "error": None,
               "updated_at": 1.0}


class BarFirstFrame(unittest.TestCase):
    """首帧进度条:rebuild 后立即 _update,bar 应正确渲染。"""

    @classmethod
    def setUpClass(cls):
        cls._root = tk.Tk()
        cls._root.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls._root.destroy()

    def test_bar_drawn_after_layout(self):
        p, toplevel = _make_panel(self._root)
        try:
            toplevel.update_idletasks()
            p.state.results = [dict(_PCT_RESULT)]
            p._update()
            self.addCleanup(p._rows["Z"]["frame"].destroy)
            toplevel.update_idletasks()

            w = p._rows["Z"]
            self.assertIsNotNone(w["bar"])
            self.assertIsNotNone(w["rect"])
            bar = w["bar"]
            bar.update_idletasks()
            real_w = bar.winfo_width()
            self.assertGreaterEqual(real_w, 10)
            coords = bar.coords(w["rect"])
            x2 = coords[2]
            expected = int(real_w * 0.8)
            self.assertEqual(x2, expected,
                             f"bar x2={x2}, expected {expected} (real_w={real_w})")
        finally:
            try:
                toplevel.destroy()
            except tk.TclError:
                pass

    def test_bar_resize_handler_uses_event_width(self):
        """bar ``<Configure>`` handler 在 ``event.width`` 变化时应重画 rect。

        不依赖 ``overrideredirect`` 窗口实际几何,直接构造合成事件验证
        handler 逻辑(这正是 ``<Configure>`` 触发时 Tk 给的字段)。
        """
        p, toplevel = _make_panel(self._root)
        try:
            toplevel.update_idletasks()
            p.state.results = [dict(_PCT_RESULT)]
            p._update()
            p.root.update_idletasks()
            w = p._rows["Z"]
            bar = w["bar"]
            rect = w["rect"]

            ev = type("E", (), {"width": 600})()
            panel_mod._on_bar_configure(ev, bar, rect, w)
            self.assertEqual(bar.coords(rect)[2], 480)

            ev.width = 300
            panel_mod._on_bar_configure(ev, bar, rect, w)
            self.assertEqual(bar.coords(rect)[2], 240)

            ev.width = 0
            panel_mod._on_bar_configure(ev, bar, rect, w)
            self.assertEqual(bar.coords(rect)[2], 240)
        finally:
            try:
                toplevel.destroy()
            except tk.TclError:
                pass

    def test_first_paint_without_idle_still_draws_bar(self):
        """回归:首次 ``_update`` 后**不**调用 ``update_idletasks``,
        bar rect 也应在 Tk 完成 layout 后通过 ``<Configure>`` handler
        绘到正确宽度。

        这是用户报告的"刚打开看不见,现在看得见"的根因。
        """
        p, toplevel = _make_panel(self._root)
        try:
            p.state.results = [dict(_PCT_RESULT)]
            p._update()
            w = p._rows["Z"]
            bar = w["bar"]
            rect = w["rect"]
            pre = bar.coords(rect)
            self.assertEqual(pre[2], 0,
                             "首帧后 rect 应是 0 宽(未布局时,paint_row 的 winfo_width=1 "
                             "被 width>=2 守卫拦截)")

            bar.update_idletasks()
            post = bar.coords(rect)
            real_w = bar.winfo_width()
            self.assertGreaterEqual(real_w, 10)
            self.assertEqual(post[2], int(real_w * 0.8),
                             f"布局完成后 Configure handler 应把 rect 画到 "
                             f"int({real_w} * 0.8) = {int(real_w * 0.8)},实际 {post[2]}")
        finally:
            try:
                toplevel.destroy()
            except tk.TclError:
                pass


if __name__ == "__main__":
    unittest.main()