"""测试 _usage_ratio / _usage_color 渐变色彩函数。"""
import unittest

import ui.panel as panel


class UsageColor(unittest.TestCase):
    def test_ratio_amount_with_total(self):
        r = {"unit": "$", "used": 13.28, "total": 30.0, "level": "warn"}
        ratio = panel._usage_ratio(r)
        self.assertAlmostEqual(ratio, 13.28 / 30.0, places=4)

    def test_ratio_amount_no_total_falls_back_to_level(self):
        r = {"unit": "$", "remaining": 16.72, "level": "warn"}
        ratio = panel._usage_ratio(r)
        self.assertEqual(ratio, 0.55)

    def test_ratio_percent_inverts(self):
        r = {"unit": "%", "pct": 73, "level": "warn"}
        self.assertAlmostEqual(panel._usage_ratio(r), 0.27, places=4)
        r = {"unit": "%", "pct": 30, "level": "critical"}
        self.assertAlmostEqual(panel._usage_ratio(r), 0.70, places=4)

    def test_ratio_unconfigured_is_none(self):
        self.assertIsNone(panel._usage_ratio({"unconfigured": True}))
        self.assertIsNone(panel._usage_ratio({"error": "boom"}))

    def test_ratio_clamps(self):
        r = {"unit": "$", "used": 50, "total": 30, "level": "ok"}
        self.assertEqual(panel._usage_ratio(r), 1.0)
        r = {"unit": "$", "used": -5, "total": 30, "level": "ok"}
        self.assertEqual(panel._usage_ratio(r), 0.0)

    def test_color_endpoints(self):
        c0 = panel._usage_color(0.0)
        c1 = panel._usage_color(1.0)
        self.assertEqual(c0, "#53d77a")
        self.assertEqual(c1, "#ff5d5d")

    def test_color_midpoint_is_yellow_ish(self):
        c = panel._usage_color(0.5)
        r, g, b = int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)
        self.assertGreater(r, g)
        self.assertGreater(g, b)

    def test_color_moves_toward_red(self):
        green = panel._usage_color(0.0)
        yellow = panel._usage_color(0.5)
        red = panel._usage_color(1.0)

        def dist_to_red(c):
            r, g, b = int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)
            return (255 - r) ** 2 + g ** 2 + b ** 2

        d_green = dist_to_red(green)
        d_yellow = dist_to_red(yellow)
        d_red = dist_to_red(red)
        self.assertGreater(d_green, d_yellow)
        self.assertGreater(d_yellow, d_red)

    def test_color_clamp(self):
        self.assertEqual(panel._usage_color(-0.5), panel._usage_color(0.0))
        self.assertEqual(panel._usage_color(1.5), panel._usage_color(1.0))

    def test_color_none(self):
        self.assertEqual(panel._usage_color(None), panel.C["dim"])


class UsageRatioToday(unittest.TestCase):
    def test_used_today_preferred_over_cumulative(self):
        r = {"unit": "$", "used_today": 5.0, "used": 20.0, "total": 30.0}
        self.assertAlmostEqual(panel._usage_ratio(r), 5.0 / 30.0, places=4)

    def test_used_today_none_falls_back_to_cumulative(self):
        r = {"unit": "$", "used_today": None, "used": 20.0, "total": 30.0}
        self.assertAlmostEqual(panel._usage_ratio(r), 20.0 / 30.0, places=4)

    def test_used_today_zero(self):
        r = {"unit": "$", "used_today": 0.0, "used": 20.0, "total": 30.0}
        self.assertEqual(panel._usage_ratio(r), 0.0)


class FmtMain(unittest.TestCase):
    def test_amount_with_used_today_and_total(self):
        r = {"unit": "$", "used_today": 0.0, "total": 30.0, "remaining": 16.72}
        self.assertEqual(panel._fmt_main(r), "今日 $0.00 / $30.00")

    def test_amount_used_today_none_falls_back_to_remaining(self):
        r = {"unit": "$", "used_today": None, "total": 30.0, "remaining": 16.72}
        self.assertEqual(panel._fmt_main(r), "$16.72 / $30.00")

    def test_amount_no_total_uses_remaining(self):
        r = {"unit": "$", "used_today": None, "total": None, "remaining": 16.72}
        self.assertEqual(panel._fmt_main(r), "$16.72")

    def test_amount_used_today_no_total(self):
        r = {"unit": "$", "used_today": 0.0, "total": None, "remaining": 16.72}
        self.assertEqual(panel._fmt_main(r), "今日 $0.00")

    def test_amount_yuan(self):
        r = {"unit": "¥", "used_today": 1.5, "total": 100.0, "remaining": 23.75}
        self.assertEqual(panel._fmt_main(r), "今日 ¥1.50 / ¥100.00")

    def test_percent_unchanged(self):
        self.assertEqual(panel._fmt_main({"unit": "%", "pct": 73}), "73%")

    def test_unconfigured(self):
        self.assertEqual(panel._fmt_main({"unconfigured": True}), "未配置")

    def test_error(self):
        self.assertEqual(panel._fmt_main({"error": "boom"}), "查询失败")


class DetailRegex(unittest.TestCase):
    def test_currency_matches(self):
        text = "[/v1/usage] 今日 $0.00 · 0 次 · 累计实付 $13.28"
        ms = list(panel._DETAIL_NUMBER_RE.finditer(text))
        self.assertEqual([m.group(0) for m in ms], ["$0.00", "$13.28"])

    def test_yuan_matches(self):
        text = "赠金 ¥0.00 · 充值 ¥23.75"
        ms = list(panel._DETAIL_NUMBER_RE.finditer(text))
        self.assertEqual([m.group(0) for m in ms], ["¥0.00", "¥23.75"])

    def test_percent_matches(self):
        text = "[coding_plan] general 5h 73% · 周 87% | 重置 3h59m"
        ms = list(panel._DETAIL_NUMBER_RE.finditer(text))
        self.assertEqual([m.group(0) for m in ms], ["73%", "87%"])

    def test_reset_time_not_matched(self):
        self.assertEqual(panel._DETAIL_NUMBER_RE.findall("重置 3h59m"), [])
        self.assertEqual(panel._DETAIL_NUMBER_RE.findall("0 次"), [])


class IsAmountMode(unittest.TestCase):
    def test_dollar(self):
        self.assertTrue(panel._is_amount_mode({"unit": "$"}))

    def test_yuan(self):
        self.assertTrue(panel._is_amount_mode({"unit": "¥"}))

    def test_credit(self):
        self.assertTrue(panel._is_amount_mode({"unit": "额度"}))

    def test_percent(self):
        self.assertFalse(panel._is_amount_mode({"unit": "%"}))

    def test_empty(self):
        self.assertFalse(panel._is_amount_mode({"unit": ""}))

    def test_tokens(self):
        self.assertFalse(panel._is_amount_mode({"unit": "tokens"}))

    def test_full_yen(self):
        self.assertTrue(panel._is_amount_mode({"unit": "￥"}))


class RowBg(unittest.TestCase):
    def test_amount_warm_bg(self):
        self.assertNotEqual(panel._row_bg({"unit": "$"}), panel._row_bg({"unit": "%"}))


if __name__ == "__main__":
    unittest.main()