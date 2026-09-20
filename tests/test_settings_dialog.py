"""测试 SettingsDialog 的设置读写 + 校验逻辑。"""
import unittest
from unittest import mock

import tkinter as tk

import ui.settings_dialog as sd


class SettingsValidation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._root = tk.Tk()
        cls._root.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls._root.destroy()

    def _make_dialog(self):
        d = mock.MagicMock()
        d._vars = {}
        d._cfg = {
            "refresh_interval_sec": 30,
            "alert": {"warn_amount": 10, "warn_pct": 30},
            "aggregate": {"monthly_budget_usd": 100, "currency_rate_cny_per_usd": 7.2},
        }
        for path, (lo, hi, vtype) in [
            ("refresh_interval_sec", (15, 3600, "int")),
            ("alert.warn_amount", (0.0, 100000.0, "float")),
            ("alert.warn_pct", (1, 99, "int")),
            ("aggregate.monthly_budget_usd", (0.0, 100000.0, "float")),
            ("aggregate.currency_rate_cny_per_usd", (0.1, 20.0, "float")),
        ]:
            d._vars[path] = (tk.StringVar(value="0"), vtype, lo, hi)
        return d

    def test_load_populates_vars(self):
        d = self._make_dialog()
        sd.SettingsDialog._load(d, d._cfg)
        self.assertEqual(d._vars["refresh_interval_sec"][0].get(), "30")
        self.assertEqual(d._vars["alert.warn_amount"][0].get(), "10")
        self.assertEqual(d._vars["alert.warn_pct"][0].get(), "30")
        self.assertEqual(d._vars["aggregate.monthly_budget_usd"][0].get(), "100")
        self.assertEqual(d._vars["aggregate.currency_rate_cny_per_usd"][0].get(), "7.2")

    def test_save_writes_to_cfg(self):
        d = self._make_dialog()
        sd.SettingsDialog._load(d, d._cfg)
        d._vars["refresh_interval_sec"][0].set("60")
        d._vars["alert.warn_amount"][0].set("20")
        d._vars["alert.warn_pct"][0].set("25")
        d._vars["aggregate.currency_rate_cny_per_usd"][0].set("7.5")
        with mock.patch.object(sd, "messagebox"):
            sd.SettingsDialog._save(d)
        self.assertEqual(d._cfg["refresh_interval_sec"], 60)
        self.assertEqual(d._cfg["alert"]["warn_amount"], 20.0)
        self.assertEqual(d._cfg["alert"]["warn_pct"], 25)
        self.assertEqual(d._cfg["aggregate"]["currency_rate_cny_per_usd"], 7.5)

    def test_save_rejects_out_of_range(self):
        d = self._make_dialog()
        sd.SettingsDialog._load(d, d._cfg)
        d._vars["refresh_interval_sec"][0].set("5")  # < 15
        with mock.patch.object(sd, "messagebox") as mb:
            sd.SettingsDialog._save(d)
        # 5 是 < 15 范围,弹错误
        mb.showerror.assert_called()

    def test_save_rejects_non_numeric(self):
        d = self._make_dialog()
        sd.SettingsDialog._load(d, d._cfg)
        d._vars["alert.warn_amount"][0].set("not a number")
        with mock.patch.object(sd, "messagebox") as mb:
            sd.SettingsDialog._save(d)
        mb.showerror.assert_called()


if __name__ == "__main__":
    unittest.main()