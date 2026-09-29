"""Poller 容错:轮询线程不允许静默死掉。

背景:_safe_fetch_once 之前不存在,Poller.run 里的 fetch_once 一旦抛异常,
线程就退出,而界面继续显示旧数据、倒计时照走,用户完全无感。
"""
import os
import sys
import threading
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import main as main_mod


def _poller(cfg=None):
    return main_mod.Poller(cfg or {"alert": {"enable": True}},
                           main_mod.State(),
                           threading.Event(), threading.Event())


class TestSafeFetchOnce(unittest.TestCase):

    def setUp(self):
        cache = __import__("cache")
        self._save = mock.patch.object(cache, "save_alert_state")
        self._load = mock.patch.object(cache, "load_alert_state",
                                       return_value={})
        self._save.start()
        self._load.start()

    def tearDown(self):
        self._save.stop()
        self._load.stop()

    def test_records_error_and_keeps_state(self):
        p = _poller()
        with mock.patch.object(main_mod, "fetch_all",
                               side_effect=RuntimeError("炸了")):
            p._safe_fetch_once()
        self.assertEqual(p.state.poll_error, "RuntimeError: 炸了")
        self.assertFalse(p.state.fetching)

    def test_error_cleared_on_next_success(self):
        p = _poller()
        with mock.patch.object(main_mod, "fetch_all",
                               side_effect=RuntimeError("炸了")):
            p._safe_fetch_once()
        self.assertIsNotNone(p.state.poll_error)
        results = [{"name": "A", "level": "ok"}]
        with mock.patch.object(main_mod, "fetch_all", return_value=results):
            p._safe_fetch_once()
        self.assertIsNone(p.state.poll_error)
        self.assertEqual(p.state.results, results)

    def test_results_survive_a_failed_round(self):
        """失败一轮不应把上一轮的结果清空,否则界面直接空掉。"""
        p = _poller()
        results = [{"name": "A", "level": "ok"}]
        with mock.patch.object(main_mod, "fetch_all", return_value=results):
            p._safe_fetch_once()
        with mock.patch.object(main_mod, "fetch_all",
                               side_effect=RuntimeError("炸了")):
            p._safe_fetch_once()
        self.assertEqual(p.state.results, results)

    def test_last_fetch_advances_on_failure(self):
        p = _poller()
        p.state.last_fetch = 0.0
        with mock.patch.object(main_mod, "fetch_all",
                               side_effect=RuntimeError("炸了")):
            p._safe_fetch_once()
        self.assertGreater(p.state.last_fetch, 0.0)

    def test_fetching_flag_always_cleared(self):
        p = _poller()
        with mock.patch.object(main_mod, "fetch_all",
                               side_effect=RuntimeError("炸了")):
            p._safe_fetch_once()
        self.assertFalse(p.state.fetching)


class TestPollerRunSurvivesErrors(unittest.TestCase):
    """run() 循环:一轮 fetch 抛错后,线程仍会进入下一轮。"""

    def setUp(self):
        cache = __import__("cache")
        self._save = mock.patch.object(cache, "save_alert_state")
        self._load = mock.patch.object(cache, "load_alert_state",
                                       return_value={})
        self._save.start()
        self._load.start()

    def tearDown(self):
        self._save.stop()
        self._load.stop()

    def test_thread_stays_alive_after_error(self):
        state = main_mod.State()
        stop = threading.Event()
        wake = threading.Event()
        p = main_mod.Poller({"alert": {"enable": True}}, state, stop, wake)

        calls = []

        def fake_fetch():
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("第一轮炸了")
            stop.set()

        # 间隔压到 0,run() 里的等待循环立即跳过,测试不必真等 15 秒
        with mock.patch.object(p, "fetch_once", side_effect=fake_fetch), \
                mock.patch.object(__import__("config"),
                                  "clamp_interval_v2", return_value=0):
            p.run()

        self.assertEqual(len(calls), 2, "出错后应继续下一轮,而不是退出")

    def test_run_uses_the_guarded_entrypoint(self):
        """run() 必须调 _safe_fetch_once,否则兜底形同虚设。"""
        p = _poller()
        stop = threading.Event()
        p.stop = stop

        def fake_safe():
            stop.set()

        with mock.patch.object(p, "_safe_fetch_once", side_effect=fake_safe) as m, \
                mock.patch.object(p, "fetch_once") as raw:
            p.run()
        m.assert_called()
        raw.assert_not_called()


class TestPanelShowsPollError(unittest.TestCase):
    """footer 与状态点必须把轮询错误显示出来,否则等于没兜底。"""

    def _src(self):
        return open(os.path.join(ROOT, "ui", "panel.py"),
                    encoding="utf-8").read()

    def test_footer_renders_poll_error(self):
        src = self._src()
        self.assertIn("poll_error", src)
        self.assertIn("轮询出错", src)

    def test_state_has_poll_error_slot(self):
        self.assertIsNone(main_mod.State().poll_error)

    def test_paused_takes_second_place_to_error(self):
        """已经暂停时若残留旧错误,仍应优先显示错误(错误更严重)。"""
        src = self._src()
        err_idx = src.index("if poll_error:")
        paused_idx = src.index("if self.state.paused:", err_idx)
        self.assertLess(err_idx, paused_idx)


if __name__ == "__main__":
    unittest.main()
