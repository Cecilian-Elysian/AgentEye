"""Poller._fire_alerts 全局 1h 闸门 + 现有 per-provider 冷却 + 重启持久化。

覆盖:
- 跨 provider 合并到一次 toast
- 同一 provider warn -> critical 等级升级也被闸门拦住
- 全局时间未到不弹
- 全局时间到了再弹
- max_per_hour=0 等同关闭
- alert.enable=False 直接不弹
- cooldown_min=0 时不受影响(全局闸门独立)
- 重启后从磁盘恢复时间戳,1h 闸门不归零
"""
import threading
import time
import unittest
from unittest import mock

import main as main_mod
import cache as cache_mod


def _r(name, level):
    return {"name": name, "level": level}


class FireAlertsBase(unittest.TestCase):
    """base:对 cache 持久化做隔离,所有子类的 _fire_alerts 调用都不会落盘。"""

    def setUp(self):
        self._load_patch = mock.patch.object(cache_mod, "load_alert_state",
                                             return_value=0.0)
        self._save_patch = mock.patch.object(cache_mod, "save_alert_state")
        self.load_mock = self._load_patch.start()
        self.save_mock = self._save_patch.start()

    def tearDown(self):
        self._load_patch.stop()
        self._save_patch.stop()

    def _poller(self, initial_ts=0.0, **alert):
        cfg = {"alert": {"enable": True, "cooldown_min": 60, **alert}}
        self.load_mock.return_value = initial_ts
        self.save_mock.reset_mock()
        state = main_mod.State()
        stop = threading.Event()
        wake = threading.Event()
        p = main_mod.Poller(cfg, state, stop, wake)
        return p, state


class FireAlertsGlobalGate(FireAlertsBase):
    @mock.patch("notify.alert_many")
    def test_first_alert_emits(self, alert_many):
        p, _ = self._poller(max_per_hour=60)
        before = time.time()
        p._fire_alerts([_r("A", "warn")])
        alert_many.assert_called_once()
        self.assertGreater(p._last_global_alert_ts, 0.0)
        self.assertGreaterEqual(p._last_global_alert_ts, before)

    @mock.patch("notify.alert_many")
    def test_second_alert_within_window_blocked(self, alert_many):
        p, _ = self._poller(max_per_hour=60)
        p._fire_alerts([_r("A", "warn")])
        p._fire_alerts([_r("A", "warn")])
        alert_many.assert_called_once()

    @mock.patch("notify.alert_many")
    def test_level_upgrade_within_window_blocked(self, alert_many):
        """warn -> critical 升级也不绕过全局闸门。"""
        p, _ = self._poller(max_per_hour=60)
        p._fire_alerts([_r("A", "warn")])
        p._fire_alerts([_r("A", "critical")])
        alert_many.assert_called_once()

    @mock.patch("notify.alert_many")
    def test_new_provider_within_window_blocked(self, alert_many):
        p, _ = self._poller(max_per_hour=60)
        p._fire_alerts([_r("A", "warn")])
        p._fire_alerts([_r("B", "critical")])
        alert_many.assert_called_once()

    @mock.patch("notify.alert_many")
    def test_alert_after_window_elapses(self, alert_many):
        p, _ = self._poller(cooldown_min=0, max_per_hour=1)
        p._fire_alerts([_r("A", "warn")])
        p._last_global_alert_ts = time.time() - 61
        p._fire_alerts([_r("A", "warn")])
        self.assertEqual(alert_many.call_count, 2)

    @mock.patch("notify.alert_many")
    def test_merges_multiple_providers_in_one_window(self, alert_many):
        """首次触发把多个 provider 合并到一条 toast。"""
        p, _ = self._poller(max_per_hour=60)
        p._fire_alerts([_r("A", "warn"), _r("B", "critical"), _r("C", "warn")])
        alert_many.assert_called_once()
        items = alert_many.call_args[0][0]
        names = [n for n, _ in items]
        self.assertEqual(sorted(names), ["A", "B", "C"])

    @mock.patch("notify.alert_many")
    def test_disabled_does_not_emit(self, alert_many):
        p, _ = self._poller(enable=False, max_per_hour=60)
        p._fire_alerts([_r("A", "warn"), _r("B", "critical")])
        alert_many.assert_not_called()
        self.assertEqual(p._last_global_alert_ts, 0.0)

    @mock.patch("notify.alert_many")
    def test_max_per_hour_zero_never_emits(self, alert_many):
        """max_per_hour=0 时全局闸门永远不通过。"""
        p, _ = self._poller(max_per_hour=0)
        p._fire_alerts([_r("A", "warn")])
        p._last_global_alert_ts = 0.0
        p._fire_alerts([_r("A", "warn")])
        alert_many.assert_not_called()

    @mock.patch("notify.alert_many")
    def test_ok_level_ignored(self, alert_many):
        p, _ = self._poller(max_per_hour=60)
        p._fire_alerts([_r("A", "ok"), _r("B", "ok")])
        alert_many.assert_not_called()

    @mock.patch("notify.alert_many")
    def test_cooldown_min_zero_does_not_affect_global_gate(self, alert_many):
        """cooldown_min=0 不应让全局闸门也失效。"""
        p, _ = self._poller(cooldown_min=0, max_per_hour=60)
        p._fire_alerts([_r("A", "warn")])
        p._fire_alerts([_r("A", "warn")])
        alert_many.assert_called_once()

    @mock.patch("notify.alert_many")
    def test_per_provider_cooldown_still_works(self, alert_many):
        p, _ = self._poller(cooldown_min=60, max_per_hour=60)
        p._fire_alerts([_r("A", "warn")])
        p._last_global_alert_ts = time.time() - 3700
        p._fire_alerts([_r("A", "warn")])
        alert_many.assert_called_once()

    @mock.patch("notify.alert_many")
    def test_default_max_per_hour_is_60(self, alert_many):
        """配置缺失 max_per_hour 时,默认 60 分钟。"""
        cfg = {"alert": {"enable": True, "cooldown_min": 60}}
        self.load_mock.return_value = 0.0
        state = main_mod.State()
        p = main_mod.Poller(cfg, state, threading.Event(), threading.Event())
        p._fire_alerts([_r("A", "warn")])
        alert_many.assert_called_once()
        p._fire_alerts([_r("A", "warn")])
        alert_many.assert_called_once()


class PersistenceAcrossRestart(FireAlertsBase):
    """重启不归零:1h 闸门靠磁盘持久化跨进程。"""

    def test_first_run_loads_zero_from_disk(self):
        """冷启动时磁盘为空 → load_alert_state 被调用,得到 0.0。"""
        cfg = {"alert": {"enable": True, "cooldown_min": 60, "max_per_hour": 60}}
        state = main_mod.State()
        p = main_mod.Poller(cfg, state, threading.Event(), threading.Event())
        self.load_mock.assert_called_once()
        self.assertEqual(p._last_global_alert_ts, 0.0)

    @mock.patch("notify.alert_many")
    def test_first_run_saves_timestamp_on_fire(self, alert_many):
        cfg = {"alert": {"enable": True, "cooldown_min": 60, "max_per_hour": 60}}
        p, _ = self._poller(max_per_hour=60)
        before = time.time()
        p._fire_alerts([_r("A", "warn")])
        alert_many.assert_called_once()
        self.save_mock.assert_called_once()
        saved_ts = self.save_mock.call_args[0][0]
        self.assertGreaterEqual(saved_ts, before)

    def test_restart_loads_recent_ts_and_blocks(self):
        """模拟重启:上次 60s 前刚弹过 → 重启后立刻不弹。"""
        recent = time.time() - 60
        cfg = {"alert": {"enable": True, "cooldown_min": 60, "max_per_hour": 60}}
        self.load_mock.return_value = recent
        state = main_mod.State()
        p = main_mod.Poller(cfg, state, threading.Event(), threading.Event())
        self.assertEqual(p._last_global_alert_ts, recent)

        with mock.patch("notify.alert_many") as am:
            p._fire_alerts([_r("A", "warn")])
            am.assert_not_called()

    @mock.patch("notify.alert_many")
    def test_restart_after_window_fires_again(self, alert_many):
        """重启时磁盘上的时间戳已经超过窗口 → 立即弹。"""
        long_ago = time.time() - 3700
        cfg = {"alert": {"enable": True, "cooldown_min": 0, "max_per_hour": 60}}
        self.load_mock.return_value = long_ago
        state = main_mod.State()
        p = main_mod.Poller(cfg, state, threading.Event(), threading.Event())
        self.assertEqual(p._last_global_alert_ts, long_ago)
        with mock.patch.object(cache_mod, "save_alert_state") as sv:
            p._fire_alerts([_r("A", "warn")])
            alert_many.assert_called_once()
            sv.assert_called_once()


if __name__ == "__main__":
    unittest.main()