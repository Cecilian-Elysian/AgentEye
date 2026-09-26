"""测试 AddKeyForm 的 placeholder 行为 + preset 填充逻辑(无 GUI 启动)。

回归:添加 Key 曾经是独立 AddKeyDialog 窗口,现已内嵌为 AddKeyForm,
由 SettingsDialog 同窗口切换视图承载。
"""
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

    def _make_form(self):
        f = mock.MagicMock()
        f.url_var = tk.StringVar()
        f.key_var = tk.StringVar()
        f.name_var = tk.StringVar()
        f._url_placeholder = True
        f._key_placeholder = True
        f._probe_thread = None
        return f

    def test_apply_preset_minimax(self):
        f = self._make_form()
        ak.AddKeyForm._apply_preset(f, "minimax",
                                    "https://api.minimaxi.com", "MiniMax")
        self.assertEqual(f.url_var.get(), "https://api.minimaxi.com")
        self.assertEqual(f.name_var.get(), "MiniMax")
        self.assertFalse(f._url_placeholder)

    def test_apply_preset_relay_empty_url(self):
        f = self._make_form()
        ak.AddKeyForm._apply_preset(f, "relay", "", "中转站")
        self.assertEqual(f.url_var.get(), "")
        self.assertEqual(f.name_var.get(), "中转站")

    def test_apply_preset_keeps_existing_name(self):
        f = self._make_form()
        f.name_var.set("我的小号")
        ak.AddKeyForm._apply_preset(f, "deepseek",
                                    "https://api.deepseek.com", "DeepSeek")
        self.assertEqual(f.name_var.get(), "我的小号")  # 已有名称不被覆盖

    def test_save_blocks_when_placeholder_active(self):
        f = self._make_form()
        f._key_placeholder = True
        called = []
        f.on_save = lambda e: called.append(e)
        ak.AddKeyForm._save(f)
        self.assertEqual(called, [])  # placeholder 时 save 被忽略

    def test_save_uses_empty_url_when_placeholder(self):
        f = self._make_form()
        f._key_placeholder = False
        f._url_placeholder = True
        f.key_var.set("sk-test123")
        f.name_var.set("测试")
        called = []
        f.on_save = lambda e: called.append(e)
        ak.AddKeyForm._save(f)
        self.assertEqual(len(called), 1)
        self.assertEqual(called[0]["base_url"], "")
        self.assertEqual(called[0]["key"], "sk-test123")

    def test_save_fires_done_callback(self):
        f = self._make_form()
        f._key_placeholder = False
        f._url_placeholder = False
        f.key_var.set("sk-x")
        f.name_var.set("n")
        saved, done = [], []
        f.on_save = lambda e: saved.append(e)
        f.on_done = lambda: done.append(1)
        ak.AddKeyForm._save(f)
        self.assertEqual(len(saved), 1)
        self.assertEqual(done, [1])


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
