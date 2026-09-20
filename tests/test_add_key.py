"""测试 AddKeyDialog 的 placeholder 行为 + preset 填充逻辑(无 GUI 启动)。"""
import unittest
from unittest import mock

import tkinter as tk

import ui.add_key as ak


class PlaceholderLogic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._root = tk.Tk()
        cls._root.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls._root.destroy()

    def _make_dialog(self):
        d = mock.MagicMock()
        d.url_var = tk.StringVar()
        d.key_var = tk.StringVar()
        d.name_var = tk.StringVar()
        d._url_placeholder = True
        d._key_placeholder = True
        d._probe_thread = None
        return d

    def test_apply_preset_minimax(self):
        d = self._make_dialog()
        ak.AddKeyDialog._apply_preset(d, "minimax",
                                      "https://api.minimaxi.com", "MiniMax")
        self.assertEqual(d.url_var.get(), "https://api.minimaxi.com")
        self.assertEqual(d.name_var.get(), "MiniMax")
        self.assertFalse(d._url_placeholder)

    def test_apply_preset_relay_empty_url(self):
        d = self._make_dialog()
        ak.AddKeyDialog._apply_preset(d, "relay", "", "中转站")
        self.assertEqual(d.url_var.get(), "")
        self.assertEqual(d.name_var.get(), "中转站")

    def test_apply_preset_keeps_existing_name(self):
        d = self._make_dialog()
        d.name_var.set("我的小号")
        ak.AddKeyDialog._apply_preset(d, "deepseek",
                                      "https://api.deepseek.com", "DeepSeek")
        self.assertEqual(d.name_var.get(), "我的小号")  # 已有名称不被覆盖

    def test_save_blocks_when_placeholder_active(self):
        d = self._make_dialog()
        d._key_placeholder = True
        called = []
        d.on_save = lambda e: called.append(e)
        ak.AddKeyDialog._save(d)
        self.assertEqual(called, [])  # placeholder 时 save 被忽略

    def test_save_uses_empty_url_when_placeholder(self):
        d = self._make_dialog()
        d._key_placeholder = False
        d._url_placeholder = True
        d.key_var.set("sk-test123")
        d.name_var.set("测试")
        called = []
        d.on_save = lambda e: called.append(e)
        ak.AddKeyDialog._save(d)
        self.assertEqual(len(called), 1)
        self.assertEqual(called[0]["base_url"], "")
        self.assertEqual(called[0]["key"], "sk-test123")


class PresetList(unittest.TestCase):
    def test_presets_count(self):
        self.assertEqual(len(ak.PRESETS), 5)

    def test_presets_have_required_fields(self):
        for label, kind, url in ak.PRESETS:
            self.assertTrue(label)
            self.assertIn(kind, {"minimax", "deepseek", "zhipu",
                                 "opencode_go", "relay"})


if __name__ == "__main__":
    unittest.main()