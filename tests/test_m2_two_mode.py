"""M2 essential / standard 两态切换单元测试。"""
import os
import sys
import time
import tkinter as tk
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class _MockState:
    def __init__(self, results=None):
        self.results = results or []
        self.fetching = False
        self.next_fetch = time.time() + 60
        self.paused = False


class TestEssentialBarPure(unittest.TestCase):
    """纯函数测试,无需 Tk。"""

    def test_short_countdown_minutes(self):
        from ui.essential_bar import _short_countdown
        self.assertEqual(_short_countdown(60), "1m")
        self.assertEqual(_short_countdown(120), "2m")
        self.assertEqual(_short_countdown(3600), "1h00m")
        self.assertEqual(_short_countdown(3660), "1h01m")
        self.assertEqual(_short_countdown(86400), "1d0h")
        self.assertEqual(_short_countdown(90000), "1d1h")

    def test_short_countdown_zero(self):
        from ui.essential_bar import _short_countdown
        self.assertEqual(_short_countdown(0), "0m")

    def test_worst_picks_max_ratio(self):
        from ui.essential_bar import _worst
        results = [
            {"name": "A", "level": "ok", "unit": "$", "remaining": 10, "total": 10},
            {"name": "B", "level": "warn", "unit": "$", "remaining": 2, "total": 10},
            {"name": "C", "level": "critical", "unit": "$", "remaining": 1, "total": 10},
        ]
        row, ratio = _worst(results)
        self.assertEqual(row["name"], "C")
        self.assertGreater(ratio, 0.8)

    def test_worst_skips_unconfigured(self):
        from ui.essential_bar import _worst
        results = [
            {"name": "A", "level": "ok", "unit": "$", "remaining": 5, "total": 10},
            {"name": "B", "unconfigured": True},
            {"name": "C", "error": "timeout"},
        ]
        row, ratio = _worst(results)
        self.assertEqual(row["name"], "A")

    def test_worst_empty(self):
        from ui.essential_bar import _worst
        self.assertEqual(_worst([]), (None, None))

    def test_main_value_money_with_today(self):
        from ui.essential_bar import _main_value
        row = {"unit": "¥", "used_today": 1.5, "total": 10.0}
        main, sub = _main_value(row)
        self.assertEqual(main, "¥1.50")
        self.assertEqual(sub, "¥10.00")

    def test_main_value_money_remaining_only(self):
        from ui.essential_bar import _main_value
        row = {"unit": "$", "remaining": 8.5, "total": 10.0}
        main, sub = _main_value(row)
        self.assertEqual(main, "$8.50")
        self.assertEqual(sub, "$10.00")

    def test_main_value_percent(self):
        from ui.essential_bar import _main_value
        row = {"unit": "%", "pct": 62}
        main, sub = _main_value(row)
        self.assertEqual(main, "62%")
        self.assertEqual(sub, "")

    def test_main_value_none(self):
        from ui.essential_bar import _main_value
        main, sub = _main_value(None)
        self.assertEqual(main, "—")
        self.assertEqual(sub, "—")


class TestModeConstants(unittest.TestCase):
    def test_constants_distinct(self):
        from ui.app import MODE_STANDARD, MODE_ESSENTIAL
        self.assertNotEqual(MODE_STANDARD, MODE_ESSENTIAL)
        self.assertEqual(MODE_STANDARD, "standard")
        self.assertEqual(MODE_ESSENTIAL, "essential")


class TestMacWindowTwoMode(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
        cls.root = tk.Tk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.root.destroy()
        except Exception:
            pass

    def setUp(self):
        self.cfg = {"ui": {"x": 100, "y": 100, "width": 360, "height": 360, "pinned": True}}
        self.state = _MockState(results=[
            {"name": "Test", "level": "ok", "unit": "%", "pct": 50},
        ])
        self._saved_ui = []
        self.actions = {
            "save_position": lambda *a, **k: None,
            "save_size": lambda *a, **k: None,
            "save_order": lambda *a, **k: None,
            "save_pin": lambda *a, **k: None,
            "save_ui": lambda new_cfg=None: self._saved_ui.append(dict(self.cfg)),
            "get_order": lambda: [],
            "save_model_order": lambda *a, **k: None,
            "quit": lambda: None,
            "add_key": lambda: None,
            "delete_provider": lambda *a, **k: None,
            "probe_model": lambda *a, **k: (False, 0.0, ""),
            "refresh_now": lambda: None,
            "toggle_pause": lambda: None,
            "test_notify": lambda: None,
            "open_config": lambda: None,
            "open_settings": lambda: None,
            "minimize": lambda: None,
        }

    def _make(self, mode=None):
        if mode is not None:
            self.cfg["ui"]["mode"] = mode
        mac = __import__("ui.app", fromlist=["MacWindow"]).MacWindow(self.root, self.cfg, self.actions)
        return mac

    def test_default_mode_is_standard(self):
        mac = self._make()
        self.assertEqual(mac.mode, "standard")

    def test_essential_persisted_mode(self):
        mac = self._make(mode="essential")
        self.assertEqual(mac.mode, "essential")

    def test_invalid_mode_falls_back_to_standard(self):
        mac = self._make(mode="nonsense")
        self.assertEqual(mac.mode, "standard")

    def test_toggle_mode(self):
        from ui.app import MacWindow, MODE_STANDARD, MODE_ESSENTIAL
        from ui.essential_bar import EssentialBar
        mac = MacWindow(self.root, self.cfg, self.actions)

        panel = __import__("ui").Panel(mac.standard_slot, self.state, self.cfg, self.actions,
                                       root_window=self.root)
        bar = EssentialBar(mac.essential_slot, self.state, self.cfg, mac.fonts_dict,
                           on_expand=mac.toggle_mode)
        mac.attach_standard(panel)
        mac.attach_essential(bar)
        mac.show_initial_mode()

        self.assertEqual(mac.mode, MODE_STANDARD)
        mac.toggle_mode()
        self.assertEqual(mac.mode, MODE_ESSENTIAL)
        mac.toggle_mode()
        self.assertEqual(mac.mode, MODE_STANDARD)

    def test_toggle_persists_mode(self):
        from ui.app import MacWindow
        from ui.essential_bar import EssentialBar
        mac = MacWindow(self.root, self.cfg, self.actions)

        panel = __import__("ui").Panel(mac.standard_slot, self.state, self.cfg, self.actions,
                                       root_window=self.root)
        bar = EssentialBar(mac.essential_slot, self.state, self.cfg, mac.fonts_dict,
                           on_expand=mac.toggle_mode)
        mac.attach_standard(panel)
        mac.attach_essential(bar)
        mac.show_initial_mode()

        mac.toggle_mode()
        self.assertEqual(self.cfg["ui"]["mode"], "essential")
        self.assertGreaterEqual(len(self._saved_ui), 1)
        self.assertEqual(self._saved_ui[-1]["ui"]["mode"], "essential")

    def test_view_root_helper(self):
        from ui.app import MacWindow
        mac = MacWindow(self.root, self.cfg, self.actions)

        class FakeView:
            frame = tk.Frame(self.root)

        view = FakeView()
        self.assertIs(MacWindow._view_root(view), view.frame)


class TestEssentialBarWidget(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
        cls.root = tk.Tk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.root.destroy()
        except Exception:
            pass

    def test_create_empty(self):
        from ui.essential_bar import EssentialBar
        from ui.fonts import fonts
        state = _MockState()
        bar = EssentialBar(tk.Frame(self.root), state, {}, fonts(self.root),
                           on_expand=lambda: None)
        self.assertEqual(str(bar.frame.cget("width")), "240")
        self.assertEqual(str(bar.frame.cget("height")), "56")

    def test_click_calls_on_expand(self):
        from ui.essential_bar import EssentialBar
        from ui.fonts import fonts
        state = _MockState()
        called = []
        bar = EssentialBar(tk.Frame(self.root), state, {}, fonts(self.root),
                           on_expand=lambda: called.append(1))
        bar._on_click()
        self.assertEqual(len(called), 1)

    def test_destroy_is_safe(self):
        from ui.essential_bar import EssentialBar
        from ui.fonts import fonts
        state = _MockState()
        bar = EssentialBar(tk.Frame(self.root), state, {}, fonts(self.root),
                           on_expand=lambda: None)
        bar.destroy()
        bar.destroy()


if __name__ == "__main__":
    unittest.main()
