"""测试 SettingsDialog 的设置读写 + 校验逻辑(简化版:仅 3 项设置)。"""
import unittest
from unittest import mock

import tkinter as tk

import ui.settings_dialog as sd


ROWS_PATHS = [
    "refresh_interval_sec",
    "alert.critical_amount_yuan",
    "alert.warn_pct",
]


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
            "alert": {"warn_pct": 30, "critical_amount_yuan": 5.0},
        }
        d._theme_var = tk.StringVar(value="dark")
        for path, (lo, hi, vtype) in [
            ("refresh_interval_sec", (15, 3600, "int")),
            ("alert.critical_amount_yuan", (0.0, 100000.0, "float")),
            ("alert.warn_pct", (1, 99, "int")),
        ]:
            d._vars[path] = (tk.StringVar(value="0"), vtype, lo, hi)
        return d

    def test_only_three_settings(self):
        """SettingsDialog 只保留 3 项设置(全部都在 ROWS 里)。"""
        self.assertEqual(len(sd.ROWS), 3)
        paths = [r[1] for r in sd.ROWS]
        self.assertEqual(paths, ROWS_PATHS)

    def test_signature_matches_main_call(self):
        """main.py open_settings 的调用形状必须与 __init__ 签名一致。

        回归:main.py 曾传 current_count=,签名精简后未同步导致设置打不开。
        """
        import inspect
        sig = inspect.signature(sd.SettingsDialog.__init__)
        self.assertEqual(list(sig.parameters),
                         ["self", "parent", "cfg", "on_save", "on_add_key"])

    def test_save_failed_validation_does_not_mutate_cfg(self):
        """校验失败时,合法项也不能写进 cfg(全量校验通过才写入)。"""
        d = self._make_dialog()
        sd.SettingsDialog._load(d)
        d._vars["refresh_interval_sec"][0].set("60")       # 合法
        d._vars["alert.warn_pct"][0].set("999")            # 非法
        with mock.patch.object(sd, "messagebox"):
            sd.SettingsDialog._save(d)
        self.assertEqual(d._cfg["refresh_interval_sec"], 30,
                         "有非法项时,合法项的新值也不应写入")
        self.assertNotIn("theme", d._cfg.get("ui", {}),
                         "有非法项时,主题不应持久化")

    def test_load_populates_vars(self):
        d = self._make_dialog()
        sd.SettingsDialog._load(d)
        self.assertEqual(d._vars["refresh_interval_sec"][0].get(), "30")
        self.assertEqual(d._vars["alert.critical_amount_yuan"][0].get(), "5")
        self.assertEqual(d._vars["alert.warn_pct"][0].get(), "30")
        # 浮点数 5.0 被 f"{v:g}" 格式化为 "5"
        self.assertEqual(float(d._vars["alert.critical_amount_yuan"][0].get()), 5.0)

    def test_save_writes_to_cfg(self):
        d = self._make_dialog()
        sd.SettingsDialog._load(d)
        d._vars["refresh_interval_sec"][0].set("60")
        d._vars["alert.critical_amount_yuan"][0].set("10")
        d._vars["alert.warn_pct"][0].set("25")
        with mock.patch.object(sd, "messagebox"):
            sd.SettingsDialog._save(d)
        self.assertEqual(d._cfg["refresh_interval_sec"], 60)
        self.assertEqual(d._cfg["alert"]["critical_amount_yuan"], 10.0)
        self.assertEqual(d._cfg["alert"]["warn_pct"], 25)

    def test_load_uses_defaults_when_missing(self):
        """cfg 里没有对应 key 时,_load 走 DEFAULTS(不是 0)。"""
        d = self._make_dialog()
        d._cfg = {"alert": {}}
        sd.SettingsDialog._load(d)
        self.assertEqual(d._vars["refresh_interval_sec"][0].get(), "30")
        # 浮点数 5.0 经 f"{v:g}" 格式化为 "5"
        self.assertEqual(d._vars["alert.critical_amount_yuan"][0].get(), "5")
        self.assertEqual(d._vars["alert.warn_pct"][0].get(), "30")

    def test_save_rejects_out_of_range(self):
        d = self._make_dialog()
        sd.SettingsDialog._load(d)
        d._vars["refresh_interval_sec"][0].set("5")  # < 15
        with mock.patch.object(sd, "messagebox") as mb:
            sd.SettingsDialog._save(d)
        # 5 是 < 15 范围,弹错误
        mb.showerror.assert_called()

    def test_save_rejects_non_numeric(self):
        d = self._make_dialog()
        sd.SettingsDialog._load(d)
        d._vars["alert.critical_amount_yuan"][0].set("not a number")
        with mock.patch.object(sd, "messagebox") as mb:
            sd.SettingsDialog._save(d)
        mb.showerror.assert_called()


if __name__ == "__main__":
    unittest.main()