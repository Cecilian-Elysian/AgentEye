"""M1.1 滚动条样式单元测试。"""
import os
import sys
import tkinter as tk
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestScrollbarStyle(unittest.TestCase):
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

    def test_module_imports(self):
        from ui.scrollbar_style import make_dark_scrollbar, _ensure_style
        self.assertTrue(callable(make_dark_scrollbar))
        self.assertTrue(callable(_ensure_style))

    def test_factory_creates_vertical_ttk_scrollbar(self):
        from ui.scrollbar_style import make_dark_scrollbar, _STYLE_NAME_V
        parent = tk.Frame(self.root)
        sb = make_dark_scrollbar(parent, orient="vertical")
        self.assertIsInstance(sb, tk.ttk.Scrollbar)
        self.assertEqual(str(sb.cget("orient")), "vertical")
        self.assertEqual(str(sb.cget("style")), _STYLE_NAME_V)
        parent.destroy()

    def test_factory_creates_horizontal_ttk_scrollbar(self):
        from ui.scrollbar_style import make_dark_scrollbar, _STYLE_NAME_H
        parent = tk.Frame(self.root)
        sb = make_dark_scrollbar(parent, orient="horizontal")
        self.assertEqual(str(sb.cget("orient")), "horizontal")
        self.assertEqual(str(sb.cget("style")), _STYLE_NAME_H)
        parent.destroy()

    def test_style_idempotent(self):
        from ui.scrollbar_style import _ensure_style, _STYLE_NAME_V, make_dark_scrollbar
        _ensure_style(self.root)
        _ensure_style(self.root)
        parent = tk.Frame(self.root)
        sb = make_dark_scrollbar(parent, orient="vertical")
        self.assertEqual(str(sb.cget("style")), _STYLE_NAME_V)
        parent.destroy()

    def test_panel_uses_dark_scrollbar(self):
        from ui import panel as panel_mod
        src = open(panel_mod.__file__, encoding="utf-8").read()
        self.assertIn("make_dark_scrollbar", src)
        self.assertNotIn("tk.Scrollbar(", src)

    def test_model_panel_uses_dark_scrollbar(self):
        from ui import model_panel as mp
        src = open(mp.__file__, encoding="utf-8").read()
        self.assertIn("make_dark_scrollbar", src)
        self.assertNotIn("tk.Scrollbar(", src)


if __name__ == "__main__":
    unittest.main()
