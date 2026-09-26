"""M4+M5 测试:MacToplevel 基类 + 4 个对话框 macOS 化 + EssentialBar 行点击打开。

- MacToplevel 子类继承时能创建,带交通灯 + body
- MacToplevel 主题切换会触发 refresh_palette
- SettingsDialog / ConfirmDeleteDialog / ModelPanel 继承 MacToplevel;
  AddKeyForm 内嵌于 SettingsDialog(不再有独立添加窗口)
- 关闭按钮 → destroy
- EssentialBar › 点击 → on_open_models 触发
- Panel 行拖拽指示器颜色为蓝色
"""

import os
import sys
import unittest
import tkinter as tk

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from ui.theme import (
    PALETTE, set_theme, on_theme_change, off_theme_change, PALETTES,
)


class TestMacToplevelBase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.root = tk.Tk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.root.destroy()
        except tk.TclError:
            pass

    def setUp(self):
        set_theme("dark", broadcast=False, persist=False)

    def test_create_with_subclass(self):
        from ui.mac_toplevel import MacToplevel

        class DemoDialog(MacToplevel):
            def __init__(self, parent):
                super().__init__(parent, title="demo", width=300, height=200)
                tk.Label(self.body, text="hello").pack()
            def refresh_palette(self):
                pass

        dlg = DemoDialog(self.root)
        try:
            self.assertTrue(dlg.winfo_exists())
            self.assertTrue(hasattr(dlg, "body"))
            self.assertTrue(hasattr(dlg, "header"))
            self.assertTrue(hasattr(dlg, "outer"))
            self.assertEqual(str(dlg.title()), "demo")
        finally:
            try:
                dlg.destroy()
            except tk.TclError:
                pass

    def test_close_button_destroys(self):
        from ui.mac_toplevel import MacToplevel

        class DemoDialog(MacToplevel):
            def __init__(self, parent):
                super().__init__(parent, title="x", width=200, height=150)

        dlg = DemoDialog(self.root)
        self.assertTrue(dlg.winfo_exists())
        try:
            dlg._on_close()
            self.assertFalse(dlg.winfo_exists())
        except tk.TclError:
            pass

    def test_traffic_lights_have_three_kinds(self):
        from ui.mac_toplevel import MacToplevel

        class DemoDialog(MacToplevel):
            def __init__(self, parent):
                super().__init__(parent, title="t",
                                 show_minimize=True, show_expand=True,
                                 width=240, height=160)

        dlg = DemoDialog(self.root)
        try:
            self.assertIsNotNone(dlg._close_dot)
            self.assertIsNotNone(dlg._minimize_dot)
            self.assertIsNotNone(dlg._expand_dot)
        finally:
            try:
                dlg.destroy()
            except tk.TclError:
                pass

    def test_no_minimize_when_disabled(self):
        from ui.mac_toplevel import MacToplevel

        class DemoDialog(MacToplevel):
            def __init__(self, parent):
                super().__init__(parent, title="x",
                                 show_minimize=False, show_expand=False,
                                 width=240, height=160)

        dlg = DemoDialog(self.root)
        try:
            self.assertIsNotNone(dlg._close_dot)
            self.assertIsNone(dlg._minimize_dot)
            self.assertIsNone(dlg._expand_dot)
        finally:
            try:
                dlg.destroy()
            except tk.TclError:
                pass

    def test_on_theme_change_triggers_refresh_palette(self):
        from ui.mac_toplevel import MacToplevel

        refresh_calls = []

        class DemoDialog(MacToplevel):
            def __init__(self, parent):
                super().__init__(parent, title="r",
                                 width=200, height=150)
            def refresh_palette(self):
                refresh_calls.append(True)

        dlg = DemoDialog(self.root)
        try:
            self.assertEqual(refresh_calls, [])
            set_theme("light", broadcast=True, persist=False)
            self.assertGreaterEqual(len(refresh_calls), 1)
        finally:
            try:
                dlg.destroy()
            except tk.TclError:
                pass

    def test_drag_data_initially_none(self):
        from ui.mac_toplevel import MacToplevel

        class DemoDialog(MacToplevel):
            def __init__(self, parent):
                super().__init__(parent, title="d",
                                 width=200, height=150)

        dlg = DemoDialog(self.root)
        try:
            self.assertIsNone(dlg._drag_data)
        finally:
            try:
                dlg.destroy()
            except tk.TclError:
                pass


class TestSettingsDialogMacMode(unittest.TestCase):

    def setUp(self):
        set_theme("dark", broadcast=False, persist=False)
        self.root = tk.Tk()
        self.root.withdraw()

    def tearDown(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def test_inherits_mactoplevel(self):
        from ui.settings_dialog import SettingsDialog
        from ui.mac_toplevel import MacToplevel
        self.assertTrue(issubclass(SettingsDialog, MacToplevel))

    def test_has_body_header(self):
        from ui.settings_dialog import SettingsDialog
        cfg = {"ui": {"theme": "dark"},
               "refresh_interval_sec": 60,
               "alert": {"warn_pct": 30, "critical_amount_yuan": 10.0}}
        dlg = SettingsDialog(self.root, cfg)
        try:
            self.assertTrue(hasattr(dlg, "body"))
            self.assertTrue(hasattr(dlg, "header"))
        finally:
            try:
                dlg.destroy()
            except tk.TclError:
                pass

    def test_refresh_palette_works(self):
        from ui.settings_dialog import SettingsDialog
        cfg = {"ui": {"theme": "dark"},
               "refresh_interval_sec": 60,
               "alert": {"warn_pct": 30, "critical_amount_yuan": 10.0}}
        dlg = SettingsDialog(self.root, cfg)
        try:
            dlg.refresh_palette()
            self.assertTrue(True)
        finally:
            try:
                dlg.destroy()
            except tk.TclError:
                pass


class TestAddKeyFormEmbedded(unittest.TestCase):
    """添加 Key 已内嵌为 AddKeyForm(tk.Frame),不再是独立窗口。

    SettingsDialog 同窗口切换「设置 ↔ 添加 Key」两个视图。
    """

    def setUp(self):
        set_theme("dark", broadcast=False, persist=False)
        self.root = tk.Tk()
        self.root.withdraw()

    def tearDown(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def test_form_is_frame_not_toplevel(self):
        from ui.add_key import AddKeyForm
        self.assertTrue(issubclass(AddKeyForm, tk.Frame))

    def test_form_creates_with_presets(self):
        from ui.add_key import AddKeyForm
        form = AddKeyForm(self.root, current_count=3)
        try:
            labels = [w for w in form.winfo_children()
                      if isinstance(w, tk.Frame)]
            self.assertTrue(labels)  # 至少有 top_row / preset_frame 等子帧
            self.assertTrue(hasattr(form, "key_var"))
            self.assertTrue(hasattr(form, "save_btn"))
        finally:
            try:
                form.destroy()
            except tk.TclError:
                pass

    def test_settings_dialog_swaps_to_add_view(self):
        from ui.settings_dialog import SettingsDialog
        from ui.add_key import AddKeyForm
        cfg = {"providers": [{"name": "a", "key": "k"}]}
        dlg = SettingsDialog(self.root, cfg, initial_view="add_key")
        try:
            self.assertIn("添加", dlg.title())
            self.assertIsInstance(dlg._form, AddKeyForm)
            # 原地返回设置视图
            dlg._show_settings_view()
            self.assertIn("设置", dlg.title())
            self.assertIsNone(dlg._form)
        finally:
            try:
                dlg.destroy()
            except tk.TclError:
                pass

    def test_settings_dialog_add_entry_saved_closes(self):
        from ui.settings_dialog import SettingsDialog
        from ui.add_key import AddKeyForm
        cfg = {"providers": []}
        received = []
        dlg = SettingsDialog(self.root, cfg,
                             on_add_key=lambda e: received.append(e),
                             initial_view="add_key")
        try:
            self.assertIsInstance(dlg._form, AddKeyForm)
            dlg._handle_entry_saved({"name": "n", "key": "sk-x", "base_url": ""})
            self.assertEqual(len(received), 1)
            self.assertFalse(bool(dlg.winfo_exists()))
        finally:
            try:
                dlg.destroy()
            except tk.TclError:
                pass


class TestConfirmDeleteMacMode(unittest.TestCase):

    def setUp(self):
        set_theme("dark", broadcast=False, persist=False)
        self.root = tk.Tk()
        self.root.withdraw()

    def tearDown(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def test_inherits_mactoplevel(self):
        from ui.confirm_delete import ConfirmDeleteDialog
        from ui.mac_toplevel import MacToplevel
        self.assertTrue(issubclass(ConfirmDeleteDialog, MacToplevel))

    def test_create_and_refresh(self):
        from ui.confirm_delete import ConfirmDeleteDialog
        dlg = ConfirmDeleteDialog(self.root, name="元序",
                                   on_confirm=lambda: None)
        try:
            self.assertEqual(dlg._expected, "元序")
            dlg.refresh_palette()
            self.assertTrue(True)
        finally:
            try:
                dlg.destroy()
            except tk.TclError:
                pass


class TestModelPanelMacMode(unittest.TestCase):

    def setUp(self):
        set_theme("dark", broadcast=False, persist=False)
        self.root = tk.Tk()
        self.root.withdraw()

    def tearDown(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def test_inherits_mactoplevel(self):
        from ui.model_panel import ModelPanel
        from ui.mac_toplevel import MacToplevel
        self.assertTrue(issubclass(ModelPanel, MacToplevel))

    def test_create_with_models(self):
        from ui.model_panel import ModelPanel
        dlg = ModelPanel(self.root, "TestProvider",
                          ["gpt-4o", "claude-sonnet-4-6"])
        try:
            self.assertIn("TestProvider", dlg.title())
            self.assertEqual(len(dlg.models), 2)
        finally:
            try:
                dlg._on_close()
            except tk.TclError:
                pass


class TestEssentialBarChevron(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.root = tk.Tk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.root.destroy()
        except tk.TclError:
            pass

    def setUp(self):
        set_theme("dark", broadcast=False, persist=False)

    def _make_fonts(self):
        return {"ui": ("Segoe UI", 10),
                "mono": ("Consolas", 11),
                "title": ("Segoe UI", 11, "bold")}

    def test_chevron_click_calls_on_open_models(self):
        from ui.essential_bar import EssentialBar

        class FakeState:
            paused = False
            fetching = False
            next_fetch = None
            results = [
                {"name": "p1", "unit": "%", "pct": 80, "level": "warn",
                 "reset_at": None, "remaining": None, "total": None,
                 "used_today": None, "detail": ""},
            ]

        opened = []
        bar = EssentialBar(self.root, FakeState(), {}, self._make_fonts(),
                           on_open_models=lambda n: opened.append(n))
        try:
            bar._update()
            self.assertEqual(bar._current_worst_name, "p1")
            bar._on_chevron_click()
            self.assertEqual(opened, ["p1"])
        finally:
            try:
                bar.destroy()
            except tk.TclError:
                pass

    def test_chevron_click_no_callback(self):
        from ui.essential_bar import EssentialBar

        class FakeState:
            paused = False
            fetching = False
            next_fetch = None
            results = []

        bar = EssentialBar(self.root, FakeState(), {}, self._make_fonts())
        try:
            bar._on_chevron_click()
            self.assertIsNone(bar._current_worst_name)
        finally:
            try:
                bar.destroy()
            except tk.TclError:
                pass

    def test_chevron_widget_present(self):
        from ui.essential_bar import EssentialBar

        class FakeState:
            paused = False
            fetching = False
            next_fetch = None
            results = []

        bar = EssentialBar(self.root, FakeState(), {}, self._make_fonts())
        try:
            self.assertTrue(hasattr(bar, "_chevron"))
            self.assertEqual(bar._chevron.cget("text"), "›")
        finally:
            try:
                bar.destroy()
            except tk.TclError:
                pass


class TestPanelDragIndicatorColor(unittest.TestCase):

    def test_drag_indicator_uses_blue(self):
        src = open(os.path.join(ROOT, "ui", "panel.py"), encoding="utf-8").read()
        self.assertIn("PALETTE.BLUE", src)
        self.assertIn("_show_drag_indicator", src)
        self.assertIn("_drag_active", src)


class TestM45Integration(unittest.TestCase):

    def test_main_wires_essential_chevron(self):
        src = open(os.path.join(ROOT, "main.py"), encoding="utf-8").read()
        self.assertIn("on_open_models=open_model_panel", src)
        self.assertIn("open_model_panel(provider_name)", src)

    def test_panel_open_model_panel_method(self):
        from ui.panel import Panel
        self.assertTrue(hasattr(Panel, "_show_models"))


if __name__ == "__main__":
    unittest.main()