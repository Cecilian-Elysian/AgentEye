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
    to_tk_color,
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
        # 不能把断言包在 try/except tk.TclError 里:_on_close 抛 TclError
        # 时 assertFalse 会被跳过,测试照样绿。销毁后再取 widget 状态本身
        # 就会 TclError,所以用 winfo_exists() 的返回值来判定。
        dlg._on_close()
        self.assertFalse(dlg.winfo_exists())

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
        # 真正有意义的行为断言:先在浅色主题下构造,再切到深色并要求
        # refresh_palette 把控件底色改过来。之前这里是 assertTrue(True),
        # 刷新彻底坏掉(内部提前 return)也不会红。
        set_theme("light", broadcast=False, persist=False)
        dlg = SettingsDialog(self.root, cfg)
        try:
            def _norm(c):
                return str(c).lstrip("#").upper()

            self.assertEqual(_norm(dlg._holder.cget("bg")),
                             _norm(to_tk_color(PALETTE.BG)))
            set_theme("dark", broadcast=False, persist=False)
            dlg.refresh_palette()
            self.assertEqual(_norm(dlg._holder.cget("bg")),
                             _norm(to_tk_color(PALETTE.BG)))
        finally:
            try:
                dlg.destroy()
            except tk.TclError:
                pass


class TestAddKeyFormEmbedded(unittest.TestCase):
    """添加 Key 已内嵌为 AddKeyForm(tk.Frame),不再是独立窗口。

    SettingsDialog 单视图,中间区在「列表 ↔ 表单」间切换。
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

    def test_settings_dialog_swaps_to_form_and_back(self):
        from ui.settings_dialog import SettingsDialog
        from ui.add_key import AddKeyForm
        cfg = {"providers": [{"id": "a1", "name": "a", "key": "k"}]}
        dlg = SettingsDialog(self.root, cfg, initial_view="add_key")
        try:
            # 单视图:标题始终是"设置",中间区切到表单
            self.assertIn("设置", dlg.title())
            self.assertIsInstance(dlg._form, AddKeyForm)
            self.assertIsNone(dlg._editing_id)
            # 返回列表模式
            dlg._swap_center_list()
            self.assertIn("设置", dlg.title())
            self.assertIsNone(dlg._form)
            self.assertIsNone(dlg._editing_id)
        finally:
            try:
                dlg.destroy()
            except tk.TclError:
                pass

    def test_settings_dialog_add_entry_saved_returns_to_list(self):
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
            # 不再关闭对话框,回到列表模式
            self.assertTrue(bool(dlg.winfo_exists()))
            self.assertIsNone(dlg._form)
            self.assertIsNone(dlg._editing_id)
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
    """拖拽指示线必须真的画得出来。

    之前这里是 grep 源码字符串("PALETTE.BLUE" / "_show_drag_indicator"),
    而 ui/panel.py:764 读 C["card_pressed"] 抛 KeyError —— 那几行字符串
    正好住在会崩的函数体里,grep 断言是"因为有 bug 才绿"。现在真调一次。
    """

    @classmethod
    def setUpClass(cls):
        from ui.panel import Panel
        cls.root = tk.Tk()
        cls.root.withdraw()

        class _State:
            results = []
            paused = False
            paused_providers = set()
            fetching = False
            poll_error = None
            save_error = None
            next_fetch = 0.0

        cls.saved = []
        cls.cfg = {"ui": {"width": 360, "height": 360}, "providers": [],
                   "alert": {"warn_pct": 30, "critical_amount_yuan": 5.0}}
        actions = {
            "refresh_now": lambda: None,
            "toggle_pause": lambda: None,
            "test_notify": lambda: None,
            "open_config": lambda: None,
            "open_settings": lambda *a: None,
            "quit": lambda: None,
            "save_position": lambda *a: None,
            "save_size": lambda *a: None,
            "save_order": lambda o: cls.saved.append(list(o)),
            "save_pin": lambda v: None,
            "get_order": lambda: [],
            "get": None,
        }
        cls.state = _State()
        cls.panel = Panel(cls.root, cls.state, cls.cfg, actions)

    @classmethod
    def tearDownClass(cls):
        try:
            cls.root.destroy()
        except tk.TclError:
            pass

    def _rows(self, *names):
        self.state.results = [
            {"name": n, "kind": "deepseek", "level": "ok", "unit": "$",
             "remaining": 5.0, "used": 1.0, "total": 6.0, "pct": None,
             "detail": "d", "error": None, "unconfigured": False,
             "paused": False, "updated_at": 1.0, "is_estimate": False}
            for n in names
        ]
        self.panel._sig = None
        self.panel._update()

    class _Ev:
        def __init__(self, y_root, widget=None):
            self.y_root = y_root
            self.x_root = 0
            self.widget = widget

    def test_drag_shows_indicator_without_raising(self):
        """按下 → 垂直拖动超过阈值,指示线与按压高亮都要能画出来。"""
        from ui import panel as panel_mod
        self._rows("A", "B")
        name = "A"
        self.panel._drag_press(self._Ev(100), name)
        # 超过 8px 阈值,会走到 _show_drag_indicator
        self.panel._drag_motion(self._Ev(400), name)
        d = self.panel._drag
        self.assertTrue(d["active"], "超过阈值应激活拖拽")
        self.assertIsNotNone(d.get("indicator"), "应画出指示线")
        # 关键回归:C["card_pressed"] 必须存在
        self.assertIn("card_pressed", panel_mod.C)
        self.panel._drag_release(self._Ev(400), name)

    def test_drag_release_commits_new_order(self):
        self._rows("A", "B")
        del self.saved[:]
        name = "A"
        self.panel._drag_press(self._Ev(100), name)
        self.panel._drag_motion(self._Ev(10000), name)
        self.panel._drag_release(self._Ev(10000), name)
        self.assertTrue(self.saved, "_commit_drag 应调用 save_order")
        self.assertEqual(sorted(self.saved[-1]), ["A", "B"])


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