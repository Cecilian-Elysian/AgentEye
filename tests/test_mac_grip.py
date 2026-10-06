"""MacWindow 右下角缩放热区与黄点最小化恢复。

背景:mac 模式下 Panel 跳过自建 grip(注释声称"由 MacWindow 接管"),
但 MacWindow 从未实现,overrideredirect 窗口又没有原生边框——生产里
窗口尺寸永远改不了。黄点最小化同理:还原后永久带原生标题栏。
"""
import os
import sys
import types
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from ui.app import MacWindow, MODE_STANDARD, MODE_ESSENTIAL
from ui.theme import Layout


def _make_mac(root, recorded=None):
    actions = {
        "save_size": lambda w, h: recorded.append((int(w), int(h))) if recorded
        is not None else None,
        "save_position": lambda *a: None,
        "save_ui": lambda *a: None,
        "quit": lambda: None,
        "open_settings": lambda: None,
    }
    return MacWindow(root, {"ui": {}}, actions)


def _event(x_root=0.0, y_root=0.0, widget=None):
    return types.SimpleNamespace(x_root=x_root, y_root=y_root, widget=widget)


class TestResizeGrip(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import tkinter as tk
        cls.root = tk.Tk()
        # 不能 withdraw:withdrawn 窗口的 geometry 不被布局系统处理,
        # winfo_width 恒为 1。测试期间窗口会在桌面上一闪而过,
        # 与 test_m6 等既有 MacWindow 测试行为一致。

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def test_grip_exists_and_follows_mode(self):
        recorded = []
        mac = _make_mac(self.root, recorded)
        self.addCleanup(mac.stop, ) if hasattr(mac, "stop") else None
        self.assertEqual(mac._grip.winfo_manager(), "place",
                         "standard 模式必须有缩放热区,否则窗口不可调尺寸")
        mac._apply_mode(MODE_ESSENTIAL)
        self.assertEqual(mac._grip.winfo_manager(), "",
                         "essential 尺寸固定,热区应隐藏")
        mac._apply_mode(MODE_STANDARD)
        self.assertEqual(mac._grip.winfo_manager(), "place")

    def test_grip_move_clamps_and_end_saves(self):
        recorded = []
        mac = _make_mac(self.root, recorded)
        self.root.geometry("360x360+40+40")
        self.root.update_idletasks()

        mac._grip_start(_event(x_root=100.0, y_root=100.0))
        # 拖大:必须被 MAX 钳住,不受真实屏幕之外的坐标影响
        mac._grip_move(_event(x_root=100.0 + 5000.0, y_root=100.0))
        self.root.update_idletasks()
        w = self.root.winfo_width()
        self.assertLessEqual(w, Layout.MAX_W)
        self.assertGreater(w, 360)
        self.assertEqual(recorded, [], "拖拽进行中不应落盘")

        mac._grip_end()
        self.assertEqual(len(recorded), 1, "释放时必须经 save_size 持久化")
        self.assertGreaterEqual(recorded[0][0], Layout.MIN_W)
        self.assertGreaterEqual(recorded[0][1], Layout.MIN_H)

    def test_grip_move_shrinks_to_min(self):
        mac = _make_mac(self.root, [])
        self.root.geometry("360x360+40+40")
        self.root.update_idletasks()
        mac._grip_start(_event(x_root=100.0, y_root=100.0))
        mac._grip_move(_event(x_root=100.0 - 5000.0, y_root=100.0 - 5000.0))
        self.root.update_idletasks()
        self.assertGreaterEqual(self.root.winfo_width(), Layout.MIN_W)
        self.assertGreaterEqual(self.root.winfo_height(), Layout.MIN_H)
        mac._grip_end()


class TestMinimizeRestore(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import tkinter as tk
        cls.root = tk.Tk()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def test_stub_minimize_sets_flag_and_restore_reapplies_borderless(self):
        mac = _make_mac(self.root, [])
        # 不真的 iconify(测试环境 WM 行为抖动),只验证状态机
        with mock.patch.object(mac.root, "overrideredirect") as orod, \
                mock.patch.object(mac.root, "iconify"):
            mac._stub_minimize()
            self.assertTrue(mac._minimized)
            orod.assert_called_with(False)
            # 任务栏还原图标 → root 收到 <Map>
            mac._on_map_restore(_event(widget=mac.root))
            self.assertFalse(mac._minimized)
            orod.assert_called_with(True)

    def test_map_event_from_other_widget_is_ignored(self):
        mac = _make_mac(self.root, [])
        mac._minimized = True
        mac._on_map_restore(_event(widget=mac.header))
        self.assertTrue(mac._minimized, "非 root 的 Map 不应触发恢复")


if __name__ == "__main__":
    unittest.main()
