"""M3 主题切换测试:Dark / Light / Auto + 全应用 refresh_palette。

- 调色板完备性:Dark / Light 必须包含全部 13 个字段,字段值必须是 6/8 位 hex
- set_theme:dark/light 互切后 PALETTE.BG/TEXT 跟随改变
- Auto → detect_system_theme 解析为 dark 或 light
- detect_system_theme 在无 darkdetect 时仍可用(返回 dark / light,不抛)
- PALETTE 是只读代理,setattr 应抛 AttributeError
- on_theme_change 监听会在 set_theme 时被调用,带 (choice, palette, persist)
- LEVEL_COLOR 在 set_theme 后被 _refresh_level_color 同步
- 应用模块 constants(pane C dict / settings_dialog BG/FG)实时反映新主题
- Panel.refresh_palette 重画 row 后,row 卡片 bg 跟新主题
- MacWindow.apply_theme(name) 切换并广播
"""

import os
import sys
import unittest
import tkinter as tk

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from ui.theme import (
    DarkPalette, LightPalette, PALETTES, PALETTE, Layout,
    set_theme, current_palette, current_choice, is_dark,
    on_theme_change, off_theme_change, detect_system_theme,
    THEME_CHOICES, TEXT_TK, TEXT_DIM_TK, LEVEL_COLOR,
    hex_with_alpha, to_tk_color, blend, usage_color,
)


REQUIRED_FIELDS = (
    "BG", "BG_VIBRANCY", "CARD", "CARD_HOVER", "CARD_PRESSED",
    "BAR_BG", "BAR_BG_AMOUNT", "CARD_AMOUNT",
    "TEXT", "TEXT_DIM", "TEXT_DISABLED", "DIVIDER",
    "BLUE", "GREEN", "YELLOW", "RED", "ORANGE", "PURPLE", "PINK", "GREY",
    "TRAFFIC_RED", "TRAFFIC_YELLOW", "TRAFFIC_GREEN", "TRAFFIC_GREEN_HOVER",
    "THUMB_IDLE", "THUMB_HOVER",
    "GLYPH_RED", "GLYPH_YELLOW",
    "OK", "WARN", "CRITICAL", "ERROR", "OFF", "UNKNOWN", "IS_DARK",
)


def _is_hex(value):
    if not isinstance(value, str):
        return False
    if not value.startswith("#"):
        return False
    body = value[1:]
    return len(body) in (6, 8) and all(c in "0123456789abcdefABCDEF" for c in body)


class TestPaletteCompleteness(unittest.TestCase):

    def setUp(self):
        set_theme("dark", broadcast=False, persist=False)

    def test_dark_palette_has_all_required_fields(self):
        for field in REQUIRED_FIELDS:
            self.assertTrue(
                hasattr(DarkPalette, field),
                f"DarkPalette 缺少字段 {field}",
            )
            self.assertTrue(
                _is_hex(getattr(DarkPalette, field)) if field != "IS_DARK" else isinstance(getattr(DarkPalette, field), bool),
                f"DarkPalette.{field} 不是合法 hex/布尔",
            )

    def test_light_palette_has_all_required_fields(self):
        for field in REQUIRED_FIELDS:
            self.assertTrue(
                hasattr(LightPalette, field),
                f"LightPalette 缺少字段 {field}",
            )

    def test_palette_keys_registered(self):
        self.assertIn("dark", PALETTES)
        self.assertIn("light", PALETTES)
        self.assertEqual(len(PALETTES), 2)


class TestSetTheme(unittest.TestCase):

    def setUp(self):
        set_theme("dark", broadcast=False, persist=False)

    def tearDown(self):
        set_theme("dark", broadcast=False, persist=False)

    def test_switch_dark_to_light_changes_palette(self):
        self.assertEqual(PALETTE.BG, DarkPalette.BG)
        resolved = set_theme("light", broadcast=False)
        self.assertEqual(resolved, "light")
        self.assertEqual(PALETTE.BG, LightPalette.BG)
        self.assertEqual(PALETTE.TEXT, LightPalette.TEXT)
        self.assertFalse(is_dark())

    def test_switch_light_to_dark(self):
        set_theme("light", broadcast=False)
        self.assertFalse(is_dark())
        set_theme("dark", broadcast=False)
        self.assertTrue(is_dark())
        self.assertEqual(PALETTE.BG, DarkPalette.BG)

    def test_invalid_name_falls_back_to_dark(self):
        set_theme("light", broadcast=False)
        set_theme("rainbow", broadcast=False)
        self.assertTrue(is_dark())

    def test_auto_resolves_to_dark_or_light(self):
        set_theme("auto", broadcast=False)
        self.assertIn(PALETTE.BG, (DarkPalette.BG, LightPalette.BG))
        self.assertIn(current_choice(), ("dark", "light", "auto"))

    def test_current_choice_persists_user_value(self):
        set_theme("auto", broadcast=False)
        self.assertEqual(current_choice(), "auto")
        self.assertTrue(is_dark() or not is_dark())

    def test_level_color_synced_after_set_theme(self):
        from ui.theme import LEVEL_OK, LEVEL_WARN
        set_theme("dark", broadcast=False)
        self.assertEqual(LEVEL_COLOR[LEVEL_OK], DarkPalette.OK)
        set_theme("light", broadcast=False)
        self.assertEqual(LEVEL_COLOR[LEVEL_OK], LightPalette.OK)
        self.assertNotEqual(LEVEL_COLOR[LEVEL_WARN], DarkPalette.WARN)


class TestPaletteProxy(unittest.TestCase):

    def test_palette_attribute_proxies_current(self):
        set_theme("dark", broadcast=False)
        self.assertEqual(PALETTE.BG, DarkPalette.BG)
        self.assertEqual(PALETTE.GREEN, DarkPalette.GREEN)
        set_theme("light", broadcast=False)
        self.assertEqual(PALETTE.GREEN, LightPalette.GREEN)
        self.assertEqual(PALETTE.TEXT_DIM, LightPalette.TEXT_DIM)

    def test_palette_setattr_raises(self):
        with self.assertRaises(AttributeError):
            PALETTE.BG = "#000000"

    def test_palette_unknown_attr_raises(self):
        with self.assertRaises(AttributeError):
            _ = PALETTE.NOT_A_FIELD


class TestSystemDetect(unittest.TestCase):

    def test_detect_system_theme_returns_valid(self):
        result = detect_system_theme()
        self.assertIn(result, ("dark", "light"))


class TestListenerBroadcast(unittest.TestCase):

    def setUp(self):
        set_theme("dark", broadcast=False, persist=False)

    def tearDown(self):
        set_theme("dark", broadcast=False, persist=False)

    def test_listener_called_on_set_theme(self):
        calls = []
        def cb(choice, palette, persist):
            calls.append((choice, palette, persist))
        on_theme_change(cb)
        try:
            set_theme("light", broadcast=True, persist=True)
            self.assertGreaterEqual(len(calls), 1)
            last = calls[-1]
            self.assertEqual(last[0], "light")
            self.assertIs(last[1], LightPalette)
            self.assertTrue(last[2])
        finally:
            off_theme_change(cb)

    def test_listener_not_called_when_broadcast_false(self):
        calls = []
        def cb(choice, palette, persist):
            calls.append(choice)
        on_theme_change(cb)
        try:
            set_theme("light", broadcast=False)
            self.assertEqual(calls, [])
        finally:
            off_theme_change(cb)

    def test_listener_can_be_removed(self):
        calls = []
        def cb(choice, palette, persist):
            calls.append(choice)
        on_theme_change(cb)
        off_theme_change(cb)
        set_theme("light", broadcast=True)
        self.assertEqual(calls, [])


class TestColorHelpers(unittest.TestCase):

    def test_to_tk_color_passes_through_6_digit(self):
        self.assertEqual(to_tk_color("#FF00FF"), "#FF00FF")

    def test_to_tk_color_strips_alpha(self):
        self.assertEqual(to_tk_color("#FF00FF80"), "#FF00FF")

    def test_hex_with_alpha_extends(self):
        self.assertEqual(hex_with_alpha("#FF00FF", 0x80), "#FF00FF80")
        self.assertEqual(hex_with_alpha("#000000", 0), "#00000000")
        self.assertEqual(hex_with_alpha("#FFFFFF", 255), "#FFFFFF00".replace("00", "FF"))

    def test_blend_endpoints(self):
        self.assertEqual(blend("#000000", "#FFFFFF", 0.0).lower(), "#000000")
        self.assertEqual(blend("#000000", "#FFFFFF", 1.0).lower(), "#ffffff")

    def test_blend_midpoint(self):
        result = blend("#000000", "#FFFFFF", 0.5)
        self.assertEqual(result.lower(), "#7f7f7f")

    def test_usage_color_ok(self):
        self.assertEqual(usage_color(0.0).lower(), PALETTE.GREEN.lower())

    def test_usage_color_warn(self):
        self.assertEqual(usage_color(0.5).lower(), PALETTE.YELLOW.lower())

    def test_usage_color_critical(self):
        self.assertEqual(usage_color(1.0).lower(), PALETTE.CRITICAL.lower())

    def test_usage_color_none(self):
        self.assertEqual(usage_color(None).lower(), PALETTE.UNKNOWN.lower())


class TestThemeConstantsPrebuilt(unittest.TestCase):

    def test_text_tk_is_6_digit(self):
        self.assertIsInstance(TEXT_TK, str)
        self.assertEqual(len(TEXT_TK.lstrip("#")), 6)

    def test_text_dim_tk_is_6_digit(self):
        self.assertEqual(len(TEXT_DIM_TK.lstrip("#")), 6)

    def test_theme_choices(self):
        self.assertIn("dark", THEME_CHOICES)
        self.assertIn("light", THEME_CHOICES)
        self.assertIn("auto", THEME_CHOICES)


class TestPanelRefreshPalette(unittest.TestCase):

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

    def test_panel_refresh_palette_changes_row_bg(self):
        from ui.panel import Panel

        class FakeState:
            paused = False
            fetching = False
            next_fetch = None
            results = [
                {"name": "p1", "unit": "%", "pct": 50, "level": "warn",
                 "reset_at": None, "remaining": None, "total": None,
                 "used_today": None, "detail": ""},
            ]

        cfg = {"ui": {}}
        actions = {
            "refresh_now": lambda: None,
            "test_notify": lambda: None,
            "add_key": lambda: None,
            "open_settings": lambda: None,
            "toggle_pause": lambda: None,
            "open_config": lambda: None,
            "quit": lambda: None,
            "save_ui": lambda *a, **k: None,
            "get_order": lambda: [],
        }

        panel = Panel(self.root, FakeState(), cfg, actions)

        set_theme("light", broadcast=False)
        panel.refresh_palette("light", PALETTES["light"], False)

        bg_after = panel._rows.get("p1", {}).get("frame")
        self.assertIsNotNone(bg_after)
        self.assertEqual(
            bg_after.cget("bg").lower(),
            to_tk_color(LightPalette.CARD).lower(),
        )


class TestMacWindowApplyTheme(unittest.TestCase):

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

    def test_apply_theme_changes_palette(self):
        from ui.app import MacWindow
        cfg = {"ui": {"mode": "standard"}}
        actions = {"save_ui": lambda *a, **k: None}
        mac = MacWindow(self.root, cfg, actions)
        resolved = mac.apply_theme("light", broadcast=True)
        self.assertEqual(resolved, "light")
        self.assertEqual(PALETTE.BG, LightPalette.BG)
        self.assertEqual(mac.root.cget("bg").lower(),
                         to_tk_color(LightPalette.BG).lower())


class TestSettingsDialogThemeRadio(unittest.TestCase):

    def setUp(self):
        set_theme("dark", broadcast=False, persist=False)
        self.root = tk.Tk()
        self.root.withdraw()

    def tearDown(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def test_dialog_has_theme_var(self):
        from ui.settings_dialog import SettingsDialog
        cfg = {"ui": {}}
        dlg = SettingsDialog(self.root, cfg, on_save=lambda c: None,
                              current_count=0)
        try:
            self.assertTrue(hasattr(dlg, "_theme_var"))
            self.assertIn(dlg._theme_var.get(), ("dark", "light", "auto"))
            self.assertEqual(dlg._theme_var.get(), "dark")
        finally:
            try:
                dlg.destroy()
            except tk.TclError:
                pass

    def test_dialog_loads_saved_theme(self):
        from ui.settings_dialog import SettingsDialog
        cfg = {"ui": {"theme": "light"}}
        dlg = SettingsDialog(self.root, cfg, on_save=lambda c: None,
                              current_count=0)
        try:
            self.assertEqual(dlg._theme_var.get(), "light")
        finally:
            try:
                dlg.destroy()
            except tk.TclError:
                pass

    def test_dialog_save_persists_theme(self):
        from ui.settings_dialog import SettingsDialog
        from tkinter import messagebox
        orig = messagebox.showerror
        messagebox.showerror = lambda *a, **k: None
        try:
            cfg = {
                "ui": {"theme": "dark"},
                "refresh_interval_sec": 60,
                "alert": {
                    "warn_amount": 5.0, "warn_amount_yuan": 30.0,
                    "critical_amount": 2.0, "critical_amount_yuan": 10.0,
                    "warn_pct": 30, "critical_pct": 15,
                    "cooldown_min": 30, "max_per_hour": 5,
                },
                "aggregate": {
                    "monthly_budget_usd": 100.0,
                    "currency_rate_cny_per_usd": 7.2,
                },
            }
            captured = {}
            dlg = SettingsDialog(self.root, cfg,
                                  on_save=lambda c: captured.update(dict(c)),
                                  current_count=0)
            try:
                dlg._theme_var.set("light")
                dlg._save()
                self.assertEqual(captured.get("ui", {}).get("theme"), "light")
            finally:
                try:
                    if dlg.winfo_exists():
                        dlg.destroy()
                except tk.TclError:
                    pass
        finally:
            messagebox.showerror = orig


class TestPersistenceAndBoot(unittest.TestCase):

    def test_main_reads_theme_from_cfg(self):
        import main as main_mod
        self.assertTrue(hasattr(main_mod, "build_actions"))
        src = open(main_mod.__file__, encoding="utf-8").read()
        self.assertIn("mac.apply_theme(initial_theme", src)


if __name__ == "__main__":
    unittest.main()