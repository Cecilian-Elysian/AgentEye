"""退出码契约:_run() 对缺依赖必须返回 3/4,而不是让 ModuleNotFoundError 逃逸成 1。

背景:providers / ui 的顶层 import 曾放在 main 模块头部,缺 requests 或
tkinter 时解释器在 _run() 守卫生效之前就崩,退出码契约的 3/4 不可达。
修复后这些 import 全部下沉到 Poller.fetch_once / main() 内部。
"""
import os
import sys
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import main as main_mod


class TestExitCodes(unittest.TestCase):

    def test_missing_requests_returns_3(self):
        # sys.modules 里塞 None 会让 `import requests` 抛
        # "import of requests halted; None in sys.modules"
        with mock.patch.dict(sys.modules, {"requests": None}):
            rc = main_mod._run()
        self.assertEqual(rc, main_mod.EXIT_NO_REQUESTS)

    def test_missing_tkinter_returns_4(self):
        with mock.patch.dict(sys.modules, {"tkinter": None}):
            rc = main_mod._run()
        self.assertEqual(rc, main_mod.EXIT_NO_TK)

    def test_run_does_not_import_providers_at_module_scope(self):
        """防回归:main 模块顶层不允许再出现 providers/ui 的 import。"""
        import main as fresh
        src = open(fresh.__file__, encoding="utf-8").read()
        head = src.split("class State")[0]
        code_lines = [ln for ln in head.splitlines()
                      if ln.strip() and not ln.strip().startswith("#")]
        for banned in ("from providers", "from ui", "import tkinter",
                       "import requests"):
            hits = [ln for ln in code_lines if banned in ln]
            self.assertFalse(
                hits, f"模块顶层不允许 {banned}(会抢在守卫前炸): {hits}")


if __name__ == "__main__":
    unittest.main()
