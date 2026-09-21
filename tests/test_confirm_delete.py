"""测试 ConfirmDeleteDialog 的确认按钮启用逻辑(纯逻辑,不依赖 Tk 弹窗)。"""
import unittest
from unittest import mock

import tkinter as tk

import ui.confirm_delete as cd


class RefreshState(unittest.TestCase):
    """直接调 _refresh_state,断言 confirm_btn.config 被调用的最终 state。"""

    @classmethod
    def setUpClass(cls):
        cls._root = tk.Tk()
        cls._root.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls._root.destroy()

    def _build_dialog(self, name):
        d = mock.MagicMock(spec=["_expected", "_var", "confirm_btn"])
        d._expected = name
        d._var = tk.StringVar()
        d.confirm_btn = mock.MagicMock()
        return d

    def test_initially_disabled(self):
        d = self._build_dialog("元序")
        cd.ConfirmDeleteDialog._refresh_state(d)
        last_call = d.confirm_btn.config.call_args
        self.assertEqual(last_call.kwargs.get("state"), "disabled")

    def test_wrong_input_disabled(self):
        d = self._build_dialog("元序")
        d._var.set("其它")
        cd.ConfirmDeleteDialog._refresh_state(d)
        last_call = d.confirm_btn.config.call_args
        self.assertEqual(last_call.kwargs.get("state"), "disabled")

    def test_correct_input_enabled(self):
        d = self._build_dialog("元序")
        d._var.set("元序")
        cd.ConfirmDeleteDialog._refresh_state(d)
        last_call = d.confirm_btn.config.call_args
        self.assertEqual(last_call.kwargs.get("state"), "normal")

    def test_empty_input_disabled(self):
        d = self._build_dialog("元序")
        d._var.set("")
        cd.ConfirmDeleteDialog._refresh_state(d)
        last_call = d.confirm_btn.config.call_args
        self.assertEqual(last_call.kwargs.get("state"), "disabled")


if __name__ == "__main__":
    unittest.main()
