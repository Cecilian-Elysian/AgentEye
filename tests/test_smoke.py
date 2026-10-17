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


def _walk(widget):
    """深度遍历一棵 widget 树。"""
    out = [widget]
    for c in widget.winfo_children():
        out.extend(_walk(c))
    return out


def _collect_label_texts(widget):
    """收集子树里所有 Label / Button 上的文本。"""
    texts = []
    for w in _walk(widget):
        if w.winfo_class() in ("Label", "Button"):
            try:
                t = str(w.cget("text"))
            except tk.TclError:
                continue
            if t:
                texts.append(t)
    return texts


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

    def test_empty_providers_shows_dedicated_empty_state(self):
        """空列表渲染专用空态,不再伪造一条 provider 行。

        旧实现拿 _row_skeleton 造一条名叫「未配置任何 provider」、值是
        "-"、下面还挂一根空胶囊的行,看着就是一条真实 provider。
        """
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
        self.assertEqual(panel._rows, {}, "空列表不该留下任何 provider 行")
        names = [getattr(w, "_provider_name", None)
                 for w in panel.rows_frame.winfo_children()]
        self.assertNotIn("未配置任何 provider", names,
                         "空态不该伪装成一条 provider 行")
        texts = _collect_label_texts(panel.rows_frame)
        self.assertTrue(any("还没有添加任何 API Key" in t for t in texts),
                        f"空态主文案缺失,实际渲染: {texts}")
        # 空态必须给出下一步,而不是只说一句"空空如也"
        self.assertTrue(
            any(w.winfo_class() == "Button" for w in _walk(panel.rows_frame)),
            "空态应有一个可点的「添加 API Key」入口")

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
        """标准模式:standard_slot 在树上,essential_slot 不在。

        条带 bar.frame 一直 pack 在 essential_slot 里(由构造期完成),
        显隐由 slot 决定——所以判据看 slot,不看视图根。
        """
        mac, panel, bar = self._wire()
        mac.show_initial_mode()
        self.root.update_idletasks()
        self.assertEqual(mac.essential_slot.winfo_manager(), "")
        self.assertEqual(mac.standard_slot.winfo_manager(), "pack")
        self.assertEqual(mac._view_root(panel).winfo_manager(), "pack")
        self.assertEqual(bar.frame.winfo_height(), 1,
                         "essential_slot 不在树上时条带不参与布局")

    def test_essential_slot_shown_in_essential_mode(self):
        mac, panel, bar = self._wire()
        mac.show_initial_mode()
        self.root.update_idletasks()
        mac.toggle_mode()
        self.root.update_idletasks()
        self.root.update()
        self.assertEqual(mac.essential_slot.winfo_manager(), "pack")
        self.assertEqual(mac.standard_slot.winfo_manager(), "")

    def test_essential_bar_is_actually_visible(self):
        """折叠模式必须真的把条带显示出来。

        历史 bug:切模式时 pack 的是 EssentialBar.frame,而它的父容器
        essential_slot 没被 pack —— bar 有 winfo_manager == "pack" 却
        永远不 mapped,折叠模式是个纯空白窗口。原来那条测试只查
        winfo_manager,把"packed 到不可见"当成了可见。

        判据是结构性的「slot 在树上 + 条带 pack 在这个 slot 里」;
        这里不断言 winfo_width —— 测试的 root 是 withdraw 的,
        整棵树都不会参与几何计算,winfo_width 恒为 1。
        """
        mac, panel, bar = self._wire()
        mac.show_initial_mode()
        self.root.update_idletasks()
        mac.toggle_mode()
        self.root.update_idletasks()

        self.assertEqual(mac.essential_slot.winfo_manager(), "pack",
                         "essential_slot 必须被 pack,否则子控件全是死区")
        self.assertIs(bar.frame.master, mac.essential_slot)
        self.assertEqual(bar.frame.winfo_manager(), "pack",
                         "条带必须 pack 在 essential_slot 里")
        self.assertEqual(mac.standard_slot.winfo_manager(), "")
        # 尺寸配置没被覆盖,且与 Layout 一致
        from ui.theme import Layout
        self.assertEqual(str(bar.frame.cget("width")),
                         str(Layout.ESSENTIAL_W))
        self.assertEqual(str(bar.frame.cget("height")),
                         str(Layout.ESSENTIAL_H))


if __name__ == "__main__":
    unittest.main()
