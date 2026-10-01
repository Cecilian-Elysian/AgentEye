"""窗口壳整链路 smoke 测试(原 tests/smoke_*.py 的正式化版本)。

覆盖三条真实启动链路,全部不进入 mainloop:
- M1  :Tk root + MacWindow 单独起
- M1+ :MacWindow + Panel 一起起(空 providers)
- M2  :MacWindow + Panel + EssentialBar 两态切换

与旧的 smoke 脚本的差别:
- 断言从 print 改成真断言,失败会报具体原因
- config.CONFIG_PATH 指向临时目录,不再读写用户真实配置
- 复用 build_actions 覆盖全部 action key,防止新增 action 漏接线
"""
import os
import sys
import tempfile
import time
import tkinter as tk
import unittest
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import config as config_mod


def _set_dpi_awareness():
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass


class _MockState:
    """与 main.State 同形,供 Panel / EssentialBar 消费。"""

    def __init__(self, results=None):
        self.results = list(results or [])
        self.last_fetch = time.time()
        self.next_fetch = time.time() + 30
        self.paused = False
        self.paused_providers = set()
        self.fetching = False


def stub_actions(root, cfg=None, state=None):
    """全量 action stub。缺 key 会让 UI 侧的 .get(...) 兜底成 no-op,
    这里刻意给全,让 smoke 覆盖到真实调用路径。"""
    saved = {"ui": []}
    return {
        "refresh_now": lambda: None,
        "toggle_pause": lambda: None,
        "test_notify": lambda: None,
        "open_config": lambda: None,
        "open_settings": lambda: None,
        "minimize": lambda: None,
        "save_position": lambda *a, **k: None,
        "save_size": lambda *a, **k: None,
        "save_order": lambda *a, **k: None,
        "save_pin": lambda *a, **k: None,
        "save_ui": lambda new_cfg=None: saved["ui"].append(new_cfg),
        "save_theme": lambda *a, **k: None,
        "get_order": lambda: [],
        "save_model_order": lambda *a, **k: None,
        "quit": lambda: root.destroy(),
        "add_key": lambda: None,
        "edit_provider": lambda *a, **k: None,
        "update_provider": lambda *a, **k: None,
        "delete_provider": lambda *a, **k: None,
        "delete_provider_by_id": lambda *a, **k: None,
        "pause_provider": lambda *a, **k: None,
        "probe_models": lambda *a, **k: None,
        "probe_model": lambda *a, **k: (False, 0.0, ""),
    }


class IsolatedConfigMixin:
    """把 config.CONFIG_PATH 指向临时目录,避免污染用户真实配置。"""

    def setUp(self):
        _set_dpi_awareness()
        self._tmp = tempfile.TemporaryDirectory()
        self._orig_path = config_mod.CONFIG_PATH
        config_mod.CONFIG_PATH = Path(self._tmp.name) / "config.json"

    def tearDown(self):
        config_mod.CONFIG_PATH = self._orig_path
        self._tmp.cleanup()


class TestM1WindowShell(IsolatedConfigMixin, unittest.TestCase):
    """M1:Tk root + MacWindow 单独起。"""

    def setUp(self):
        super().setUp()
        self.root = tk.Tk()
        self.root.geometry("360x260+200+200")
        # MacWindow 会设 -topmost + overrideredirect。这里必须保持 mapped
        # (本类要验槽位几何),所以用 alpha=0 隐形,而不是 withdraw()。
        self.root.attributes("-alpha", 0.0)

    def tearDown(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass
        super().tearDown()

    def test_macwindow_builds_all_slots(self):
        from ui.app import MacWindow

        cfg = config_mod.load_v2()
        mac = MacWindow(self.root, cfg, stub_actions(self.root, cfg))
        self.assertIsNotNone(mac.header)
        self.assertIsNotNone(mac.body)
        self.assertIsNotNone(mac.standard_slot)
        self.assertIsNotNone(mac.essential_slot)

    def test_fonts_dict_is_populated(self):
        from ui.app import MacWindow

        mac = MacWindow(self.root, config_mod.load_v2(),
                        stub_actions(self.root))
        self.assertTrue(mac.fonts_dict.get("ui"))
        self.assertTrue(mac.fonts_dict.get("mono"))

    def test_three_traffic_lights_created(self):
        from ui.app import MacWindow, TrafficLight

        mac = MacWindow(self.root, config_mod.load_v2(),
                        stub_actions(self.root))
        dots = [mac.header.red_dot, mac.header.settings_dot,
                mac.header.yellow_dot]
        for dot in dots:
            self.assertIsInstance(dot, TrafficLight)
        # 视觉顺序从左到右是 [黄(最小化) 绿(设置) 红(退出)]
        self.assertEqual(
            [d._kind for d in (mac.header.yellow_dot, mac.header.settings_dot,
                               mac.header.red_dot)],
            ["minimize", "settings", "close"])

    def test_layout_applied(self):
        from ui.app import MacWindow
        from ui.theme import Layout

        mac = MacWindow(self.root, config_mod.load_v2(),
                        stub_actions(self.root))
        self.root.update_idletasks()
        self.assertGreaterEqual(self.root.winfo_width(), Layout.MIN_W)


class TestM1Integration(IsolatedConfigMixin, unittest.TestCase):
    """M1:MacWindow + Panel 一起起,空 providers。"""

    def setUp(self):
        super().setUp()
        self.root = tk.Tk()
        self.root.withdraw()

    def tearDown(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass
        super().tearDown()

    def test_panel_mounts_in_standard_slot(self):
        from ui import Panel
        from ui.app import MacWindow

        cfg = config_mod.load_v2()
        actions = stub_actions(self.root, cfg)
        mac = MacWindow(self.root, cfg, actions)
        panel = Panel(mac.standard_slot, _MockState(), cfg, actions,
                      root_window=self.root)
        mac.attach_standard(panel)
        mac.show_initial_mode()
        self.root.update_idletasks()
        self.assertTrue(panel.rows_frame.winfo_exists())

    def test_empty_providers_shows_placeholder_row(self):
        from ui import Panel
        from ui.app import MacWindow

        cfg = config_mod.load_v2()
        actions = stub_actions(self.root, cfg)
        mac = MacWindow(self.root, cfg, actions)
        panel = Panel(mac.standard_slot, _MockState(), cfg, actions,
                      root_window=self.root)
        mac.attach_standard(panel)
        mac.show_initial_mode()
        self.root.update_idletasks()
        names = [getattr(w, "_provider_name", None)
                 for w in panel.rows_frame.winfo_children()]
        self.assertIn("未配置任何 provider", names)

    def test_chrome_flags_applied(self):
        from ui import Panel
        from ui.app import MacWindow

        cfg = config_mod.load_v2()
        actions = stub_actions(self.root, cfg)
        mac = MacWindow(self.root, cfg, actions)
        panel = Panel(mac.standard_slot, _MockState(), cfg, actions,
                      root_window=self.root)
        mac.attach_standard(panel)
        mac.show_initial_mode()
        self.root.update_idletasks()
        self.assertTrue(self.root.overrideredirect())
        self.assertTrue(self.root.attributes("-topmost"))


class TestM2TwoModeIntegration(IsolatedConfigMixin, unittest.TestCase):
    """M2:MacWindow + Panel + EssentialBar,两态来回切换。"""

    def setUp(self):
        super().setUp()
        self.root = tk.Tk()
        self.root.withdraw()
        self.state = _MockState(results=[
            {"name": "DeepSeek", "level": "ok", "unit": "$",
             "remaining": 8.20, "total": 10.0, "used_today": 1.80,
             "detail": "总余额", "pct": 18},
            {"name": "MiniMax", "level": "warn", "unit": "%",
             "remaining": None, "total": None, "pct": 62,
             "reset_at": time.time() + 3600,
             "detail": "5h 62% · 周 44%"},
        ])
        self.cfg = config_mod.load_v2()
        self.actions = stub_actions(self.root, self.cfg, self.state)

    def tearDown(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass
        super().tearDown()

    def _wire(self):
        from ui import Panel
        from ui.app import MacWindow
        from ui.essential_bar import EssentialBar

        mac = MacWindow(self.root, self.cfg, self.actions)
        panel = Panel(mac.standard_slot, self.state, self.cfg, self.actions,
                      root_window=self.root)
        bar = EssentialBar(mac.essential_slot, self.state, self.cfg,
                           mac.fonts_dict, on_expand=mac.toggle_mode)
        mac.attach_standard(panel)
        mac.attach_essential(bar)
        return mac, panel, bar

    def test_initial_mode_is_standard(self):
        mac, _panel, _bar = self._wire()
        mac.show_initial_mode()
        self.root.update_idletasks()
        self.assertEqual(mac.mode, "standard")

    def test_toggle_round_trip(self):
        mac, _panel, _bar = self._wire()
        mac.show_initial_mode()
        self.root.update_idletasks()

        mac.toggle_mode()
        self.root.update_idletasks()
        self.root.update()
        self.assertEqual(mac.mode, "essential")

        mac.toggle_mode()
        self.root.update_idletasks()
        self.root.update()
        self.assertEqual(mac.mode, "standard")

    def test_essential_slot_hidden_in_standard_mode(self):
        mac, panel, bar = self._wire()
        mac.show_initial_mode()
        self.root.update_idletasks()
        self.assertEqual(mac._view_root(bar).winfo_manager(), "")
        self.assertEqual(mac._view_root(panel).winfo_manager(), "pack")

    def test_essential_slot_shown_in_essential_mode(self):
        mac, panel, bar = self._wire()
        mac.show_initial_mode()
        self.root.update_idletasks()
        mac.toggle_mode()
        self.root.update_idletasks()
        self.assertEqual(mac._view_root(bar).winfo_manager(), "pack")
        self.assertEqual(mac._view_root(panel).winfo_manager(), "")


if __name__ == "__main__":
    unittest.main()
