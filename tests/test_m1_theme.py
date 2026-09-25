"""M1 主题与字体单元测试。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ui.theme import (
    PALETTE, LEVEL_COLOR, Layout, Typography,
    hex_with_alpha, blend, usage_color,
    LEVEL_OK, LEVEL_WARN, LEVEL_CRITICAL, LEVEL_ERROR,
    LEVEL_UNCONFIGURED, LEVEL_UNKNOWN,
)


class TestPalette(unittest.TestCase):
    def test_palette_colors_are_hex(self):
        for name in ("BG", "CARD", "BLUE", "GREEN", "YELLOW", "RED"):
            color = getattr(PALETTE, name)
            self.assertTrue(color.startswith("#"))
            self.assertEqual(len(color), 7, f"{name} 不是 6 位 hex: {color}")

    def test_traffic_lights_are_mac_colors(self):
        self.assertEqual(PALETTE.TRAFFIC_RED, "#FF5F57")
        self.assertEqual(PALETTE.TRAFFIC_YELLOW, "#FEBC2E")
        self.assertEqual(PALETTE.TRAFFIC_GREEN, "#28C840")

    def test_level_color_mapping(self):
        self.assertEqual(LEVEL_COLOR[LEVEL_OK], PALETTE.GREEN)
        self.assertEqual(LEVEL_COLOR[LEVEL_WARN], PALETTE.YELLOW)
        self.assertEqual(LEVEL_COLOR[LEVEL_CRITICAL], PALETTE.RED)
        self.assertEqual(LEVEL_COLOR[LEVEL_ERROR], PALETTE.ORANGE)
        self.assertEqual(LEVEL_COLOR[LEVEL_UNCONFIGURED], PALETTE.GREY)


class TestLayout(unittest.TestCase):
    def test_radius_hierarchy(self):
        self.assertLessEqual(Layout.RADIUS_BAR, Layout.RADIUS_BTN)
        self.assertLessEqual(Layout.RADIUS_BTN, Layout.RADIUS_CARD)
        self.assertLessEqual(Layout.RADIUS_CARD, Layout.RADIUS_WIN)

    def test_dimensions_positive(self):
        self.assertGreater(Layout.MIN_W, 0)
        self.assertGreater(Layout.MIN_H, 0)
        self.assertGreater(Layout.MAX_W, Layout.MIN_W)
        self.assertGreater(Layout.MAX_H, Layout.MIN_H)

    def test_essential_size_compact(self):
        self.assertLessEqual(Layout.ESSENTIAL_W, 280)
        self.assertLessEqual(Layout.ESSENTIAL_H, 80)


class TestTypography(unittest.TestCase):
    def test_num_size_larger_than_body(self):
        self.assertGreater(Typography.NUM_SIZE, Typography.BODY_SIZE)

    def test_all_sizes_positive(self):
        for name in dir(Typography):
            if name.endswith("_SIZE"):
                v = getattr(Typography, name)
                self.assertGreater(v, 0, f"{name} 不是正数")


class TestHexWithAlpha(unittest.TestCase):
    def test_appends_alpha(self):
        self.assertEqual(hex_with_alpha("#1E1E1E", 200), "#1E1E1EC8")

    def test_clamps_alpha(self):
        self.assertEqual(hex_with_alpha("#1E1E1E", -10), "#1E1E1E00")
        self.assertEqual(hex_with_alpha("#1E1E1E", 999), "#1E1E1EFF")

    def test_strips_hash(self):
        self.assertEqual(hex_with_alpha("FF5F57", 128), "#FF5F5780")


class TestBlend(unittest.TestCase):
    def test_endpoints(self):
        self.assertEqual(blend("#000000", "#FFFFFF", 0.0).upper(), "#000000")
        self.assertEqual(blend("#000000", "#FFFFFF", 1.0).upper(), "#FFFFFF")

    def test_midpoint(self):
        mid = blend("#000000", "#FFFFFF", 0.5).upper()
        self.assertEqual(mid, "#7F7F7F")

    def test_clamps_t(self):
        self.assertEqual(blend("#000000", "#FFFFFF", -1).upper(), "#000000")
        self.assertEqual(blend("#000000", "#FFFFFF", 2).upper(), "#FFFFFF")


class TestUsageColor(unittest.TestCase):
    def _eq(self, a, b):
        return a.lower() == b.lower()

    def test_none_returns_grey(self):
        self.assertTrue(self._eq(usage_color(None), PALETTE.GREY))

    def test_zero_is_green(self):
        self.assertTrue(self._eq(usage_color(0.0), PALETTE.GREEN))

    def test_one_is_critical_red(self):
        self.assertTrue(self._eq(usage_color(1.0), PALETTE.CRITICAL))

    def test_half_is_yellow(self):
        self.assertTrue(self._eq(usage_color(0.5), PALETTE.YELLOW))

    def test_clamps(self):
        self.assertTrue(self._eq(usage_color(-0.5), PALETTE.GREEN))
        self.assertTrue(self._eq(usage_color(2.0), PALETTE.CRITICAL))


class TestVibrancyPlatformBranch(unittest.TestCase):
    def test_module_imports(self):
        from ui import vibrancy
        self.assertTrue(hasattr(vibrancy, "apply_windows_rounded_corners"))
        self.assertTrue(hasattr(vibrancy, "apply_windows_system_backdrop"))
        self.assertTrue(hasattr(vibrancy, "apply_windows_layered_alpha"))
        self.assertTrue(hasattr(vibrancy, "apply_window_chrome"))
        self.assertTrue(hasattr(vibrancy, "get_hwnd"))

    def test_is_windows_11_or_later_returns_bool(self):
        from ui.vibrancy import is_windows_11_or_later
        result = is_windows_11_or_later()
        self.assertIsInstance(result, bool)


class TestMacWindowModule(unittest.TestCase):
    def test_imports(self):
        from ui.app import MacWindow, MacHeader, TrafficLight, build_mac_window
        self.assertTrue(callable(MacWindow))
        self.assertTrue(callable(build_mac_window))


if __name__ == "__main__":
    unittest.main()
