"""Bug regression tests — light theme readability.

背景:之前 `TEXT_TK / TEXT_DIM_TK` 是模块级常量,在 import 时按 dark 调色
板预求值,之后 set_theme('light') 也不刷新,导致标题在白底上仍是白字
(不可见)。改用 `to_tk_color(PALETTE.X)` 内联求值后,fg/bg 必须实时跟随。
"""
import unittest
import tkinter as tk

from ui.theme import (
    set_theme, current_palette, PALETTE, to_tk_color, to_tk_color_blended,
)
from ui.app import MacWindow
from ui.essential_bar import EssentialBar
import config as config_mod


def _make_root():
    root = tk.Tk()
    root.geometry("360x400+200+200")
    return root


class TestLightThemeReadability(unittest.TestCase):

    def setUp(self):
        self.root = _make_root()

    def tearDown(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def _build_mac(self):
        cfg = config_mod.load_v2()
        return MacWindow(self.root, cfg, {})

    def test_text_tk_module_globals_refresh_on_set_theme(self):
        """TEXT_TK / TEXT_DIM_TK 模块常量必须在 set_theme 之后立即更新。"""
        import ui.theme as t
        t.set_theme("dark", broadcast=False)
        dark_text = t.TEXT_TK
        dark_dim = t.TEXT_DIM_TK
        self.assertEqual(dark_text, "#FFFFFF")
        t.set_theme("light", broadcast=False)
        light_text = t.TEXT_TK
        light_dim = t.TEXT_DIM_TK
        self.assertEqual(light_text, "#000000")
        self.assertNotEqual(dark_text, light_text)
        self.assertNotEqual(dark_dim, light_dim)

    def test_to_tk_color_blended_dim_has_visible_contrast(self):
        """to_tk_color_blended 把 alpha 预混合到 BG 上,产出的 6 位色应
        仍然与 BG 形成足够对比度 (差值 > 60)。"""
        for theme in ("dark", "light"):
            with self.subTest(theme=theme):
                set_theme(theme, broadcast=False)
                dim = to_tk_color_blended(PALETTE.TEXT_DIM)
                bg = to_tk_color(PALETTE.BG)
                # 把两个 hex 转成 RGB 求最大通道差
                def _hex_to_rgb(h):
                    h = h.lstrip("#")
                    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))
                dr, dg, db = _hex_to_rgb(dim)
                br, bg_, bb = _hex_to_rgb(bg)
                max_diff = max(abs(dr - br), abs(dg - bg_), abs(db - bb))
                self.assertGreater(max_diff, 60,
                                   f"theme={theme} DIM={dim} BG={bg} 对比度太低")

    def test_mac_header_title_visible_in_light_theme(self):
        """MacHeader.title_lbl 在浅色主题下应该是黑字配浅底,不能白字配白底。"""
        set_theme("dark", broadcast=False)
        mac = self._build_mac()
        mac.apply_theme("light", broadcast=True)
        title = mac.header.title_lbl
        fg = title.cget("fg").lower()
        bg = title.cget("bg").lower()
        self.assertEqual(fg, "#000000")
        self.assertEqual(bg, "#f5f5f7")

    def test_mac_header_settings_btn_idle_fg_contrasts_with_bg_in_light(self):
        """⚙ 按钮 idle fg 在浅色下必须是中等灰,不是纯白。"""
        set_theme("dark", broadcast=False)
        mac = self._build_mac()
        mac.apply_theme("light", broadcast=True)
        btn = mac.header.settings_btn
        idle_fg = btn._idle_fg.lower()
        idle_bg = btn._idle_bg.lower()
        self.assertNotEqual(idle_fg, idle_bg,
                            f"⚙ idle fg={idle_fg} 与 bg={idle_bg} 相同 → 不可见")
        # 必须是 6 位 hex,不是 8 位
        self.assertEqual(len(idle_fg), 7)
        # 不是纯白
        self.assertNotEqual(idle_fg, "#ffffff")
        # 不是纯黑 (应该是 DIM,不是 TEXT)
        self.assertNotEqual(idle_fg, "#000000")

    def test_essential_bar_sub_label_contrasts_in_light(self):
        """EssentialBar.sub_lbl 在浅色下必须可见(非白字)。"""
        set_theme("dark", broadcast=False)
        bar = EssentialBar(
            self.root, type("S", (), {"paused": False, "fetching": False,
                                       "next_fetch": None, "results": []})(),
            {}, {"ui": ("Segoe UI", 10), "mono": ("Consolas", 11),
                  "title": ("Segoe UI", 11, "bold")},
        )
        set_theme("light", broadcast=True)
        fg = bar.sub_lbl.cget("fg").lower()
        bg = bar.frame.cget("bg").lower()
        self.assertNotEqual(fg, bg,
                            f"sub_lbl fg={fg} 与 bg={bg} 相同 → 不可见")
        self.assertNotEqual(fg, "#ffffff",
                            "sub_lbl 浅色下不应是纯白")

    def test_essential_bar_chevron_contrasts_in_light(self):
        bar = EssentialBar(
            self.root, type("S", (), {"paused": False, "fetching": False,
                                       "next_fetch": None, "results": []})(),
            {}, {"ui": ("Segoe UI", 10), "mono": ("Consolas", 11),
                  "title": ("Segoe UI", 11, "bold")},
        )
        set_theme("light", broadcast=True)
        fg = bar._chevron.cget("fg").lower()
        self.assertNotEqual(fg, "#ffffff", "chevron 浅色下应是 DIM 不是 TEXT")

    def test_apply_theme_dark_then_light_then_dark_returns_to_original(self):
        """来回切换主题,标题颜色应能正确回到原始值。"""
        set_theme("dark", broadcast=False)
        mac = self._build_mac()
        original_fg = mac.header.title_lbl.cget("fg").lower()
        original_bg = mac.header.title_lbl.cget("bg").lower()
        mac.apply_theme("light", broadcast=True)
        self.assertEqual(mac.header.title_lbl.cget("fg").lower(), "#000000")
        mac.apply_theme("dark", broadcast=True)
        self.assertEqual(mac.header.title_lbl.cget("fg").lower(), original_fg)
        self.assertEqual(mac.header.title_lbl.cget("bg").lower(), original_bg)


if __name__ == "__main__":
    unittest.main()