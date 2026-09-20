import unittest

from providers.aggregate import compute, _normalize_to_usd


class TestNormalizeUSD(unittest.TestCase):
    def test_dollar(self):
        r = {'unit': '$', 'remaining': 10.0, 'used': 5.0, 'total': 15.0}
        self.assertEqual(_normalize_to_usd(r), (10.0, 5.0, 15.0))

    def test_dollar_none_remaining(self):
        r = {'unit': '$', 'remaining': None, 'used': 5.0}
        self.assertIsNone(_normalize_to_usd(r))

    def test_yuan_conversion(self):
        r = {'unit': '¥', 'remaining': 72.0, 'used': 0, 'total': 0}
        rem, used, tot = _normalize_to_usd(r, rate_cny_per_usd=7.2)
        self.assertAlmostEqual(rem, 10.0)
        self.assertAlmostEqual(used, 0.0)

    def test_percent_subscription(self):
        r = {'type': 'minimax', 'unit': '%', 'pct': 50}
        rem, used, tot = _normalize_to_usd(r)
        self.assertAlmostEqual(rem, 25.0)
        self.assertAlmostEqual(used, 25.0)
        self.assertAlmostEqual(tot, 50.0)

    def test_percent_no_type_uses_default(self):
        r = {'unit': '%', 'pct': 80}
        rem, _, tot = _normalize_to_usd(r)
        self.assertEqual(tot, 30.0)

    def test_credit_unit(self):
        r = {'unit': '额度', 'remaining': 100.0, 'used': 50.0}
        self.assertEqual(_normalize_to_usd(r), (100.0, 50.0, 0.0))

    def test_unknown_unit_returns_none(self):
        self.assertIsNone(_normalize_to_usd({'unit': 'BTC', 'remaining': 1}))


class TestCompute(unittest.TestCase):
    def test_empty_results(self):
        agg = compute([])
        self.assertEqual(agg['total_usd'], 0.0)
        self.assertEqual(agg['providers_with_data'], 0)
        self.assertEqual(agg['level'], 'ok')

    def test_none_cfg(self):
        agg = compute([{'unit': '$', 'remaining': 10}], None)
        self.assertEqual(agg['total_usd'], 10.0)

    def test_worst_level_critical(self):
        results = [
            {'name': 'A', 'type': 'relay', 'unit': '$', 'remaining': 10, 'level': 'ok'},
            {'name': 'B', 'type': 'minimax', 'unit': '%', 'pct': 50, 'level': 'critical'},
        ]
        agg = compute(results)
        self.assertEqual(agg['level'], 'critical')

    def test_worst_level_warn(self):
        results = [
            {'name': 'A', 'type': 'relay', 'unit': '$', 'remaining': 10, 'level': 'ok'},
            {'name': 'B', 'type': 'minimax', 'unit': '%', 'pct': 50, 'level': 'warn'},
        ]
        agg = compute(results)
        self.assertEqual(agg['level'], 'warn')

    def test_budget_critical_when_low(self):
        cfg = {'aggregate': {'monthly_budget_usd': 100}}
        results = [{'unit': '$', 'remaining': 4.0, 'level': 'ok'}]
        agg = compute(results, cfg)
        self.assertEqual(agg['pct'], 4.0)
        self.assertEqual(agg['level'], 'critical')

    def test_budget_warn(self):
        cfg = {'aggregate': {'monthly_budget_usd': 100}}
        results = [{'unit': '$', 'remaining': 15.0, 'level': 'ok'}]
        agg = compute(results, cfg)
        self.assertEqual(agg['pct'], 15.0)
        self.assertEqual(agg['level'], 'warn')

    def test_budget_does_not_demote_critical(self):
        """即使 budget 配置合理,critical provider 仍应是 critical。"""
        cfg = {'aggregate': {'monthly_budget_usd': 100}}
        results = [
            {'unit': '$', 'remaining': 80.0, 'level': 'ok'},
            {'unit': '$', 'remaining': 2.0, 'level': 'critical'},
        ]
        agg = compute(results, cfg)
        self.assertEqual(agg['level'], 'critical')

    def test_budget_over_means_ok(self):
        """剩余超过 budget 不触发告警(还有钱)。"""
        cfg = {'aggregate': {'monthly_budget_usd': 50}}
        results = [{'unit': '$', 'remaining': 80.0, 'level': 'ok'}]
        agg = compute(results, cfg)
        self.assertEqual(agg['pct'], 160.0)
        self.assertEqual(agg['level'], 'ok')

    def test_breakdown_sorted_desc(self):
        results = [
            {'name': 'A', 'type': 'relay', 'unit': '$', 'remaining': 5, 'level': 'ok'},
            {'name': 'B', 'type': 'minimax', 'unit': '%', 'pct': 80, 'level': 'ok'},
            {'name': 'C', 'type': 'relay', 'unit': '$', 'remaining': 50, 'level': 'ok'},
        ]
        agg = compute(results)
        names = [b['name'] for b in agg['breakdown']]
        self.assertEqual(names[0], 'C')
        self.assertEqual(names[-1], 'A')

    def test_currency_conversion(self):
        cfg = {'aggregate': {'currency_rate_cny_per_usd': 7.0}}
        results = [{'name': 'DS', 'unit': '¥', 'remaining': 70.0, 'level': 'ok'}]
        agg = compute(results, cfg)
        self.assertAlmostEqual(agg['total_usd'], 10.0)


if __name__ == "__main__":
    unittest.main()
