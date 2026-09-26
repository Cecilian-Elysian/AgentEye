"""测试 ModelPanel 的过滤计数 + 价格 trace + 试调 inline 设置。"""
import unittest
from unittest import mock

import tkinter as tk

import ui.model_panel as mp


class EstimateCost(unittest.TestCase):
    def test_basic(self):
        result = mp._estimate_cost("gpt-4o", "100")
        self.assertIn("$", result)

    def test_zero_calls(self):
        self.assertEqual(mp._estimate_cost("gpt-4o", "0"), "—")

    def test_invalid_calls(self):
        self.assertEqual(mp._estimate_cost("gpt-4o", "abc"), "次数无效")

    def test_unknown_model(self):
        result = mp._estimate_cost("unknown-xyz", "10")
        self.assertIn("无价表", result)


class Grouping(unittest.TestCase):
    def setUp(self):
        self.panel = mp.ModelPanel.__new__(mp.ModelPanel)

    def test_claude(self):
        self.assertEqual(self.panel._group("claude-3-5-sonnet"), "Claude")

    def test_gpt(self):
        self.assertEqual(self.panel._group("gpt-4o"), "GPT")
        self.assertEqual(self.panel._group("o1-preview"), "GPT")

    def test_gemini(self):
        self.assertEqual(self.panel._group("gemini-1.5-pro"), "Gemini")

    def test_embedding(self):
        self.assertEqual(self.panel._group("text-embedding-3-small"), "Embedding")

    def test_other(self):
        self.assertEqual(self.panel._group("some-random-model"), "其他")


class AfterReorderCallback(unittest.TestCase):
    """拖动重排后必须触发 on_after_reorder,触发 poller 刷新额度。"""

    @classmethod
    def setUpClass(cls):
        cls._root = tk.Tk()
        cls._root.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls._root.destroy()

    def test_callback_invoked(self):
        from unittest import mock
        called = []
        on_after = lambda: called.append(1)
        p = mp.ModelPanel(self._root, "Test", ["m1", "m2", "m3"],
                          on_reorder=lambda o: None,
                          on_after_reorder=on_after)
        p._commit_model_drag("m1", 2)
        self.assertEqual(called, [1])

    def test_callback_not_invoked_if_model_missing(self):
        from unittest import mock
        called = []
        on_after = lambda: called.append(1)
        p = mp.ModelPanel(self._root, "Test", ["m1", "m2", "m3"],
                          on_reorder=lambda o: None,
                          on_after_reorder=on_after)
        p._commit_model_drag("ghost", 0)
        self.assertEqual(called, [])

    def test_no_callback_no_error(self):
        p = mp.ModelPanel(self._root, "Test", ["m1", "m2"],
                          on_reorder=lambda o: None)
        p._commit_model_drag("m1", 1)


class EmptyFilterRender(unittest.TestCase):
    """搜索无匹配时 _render 不得崩溃(回归:BG/DIM 未定义先使用)。"""

    @classmethod
    def setUpClass(cls):
        cls._root = tk.Tk()
        cls._root.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls._root.destroy()

    def test_no_match_renders_placeholder(self):
        p = mp.ModelPanel(self._root, "Test", ["m1", "m2"])
        p.search_var.set("zzz-no-match")
        labels = [w for w in p.inner.winfo_children()
                  if isinstance(w, tk.Label)]
        self.assertEqual(len(labels), 1)
        self.assertEqual(labels[0].cget("text"), "(无匹配)")

    def test_probe_result_targeted_per_model(self):
        p = mp.ModelPanel(self._root, "Test", ["m1", "m2"], on_probe=lambda m: (True, 5, ""))
        p._probe_done("m1", True, 5.0, "")
        var = p.probe_result_vars["m1"]
        self.assertEqual(var.get(), "✓ 5ms")
        self.assertEqual(p.probe_result_vars["m2"].get(), "")


if __name__ == "__main__":
    unittest.main()
