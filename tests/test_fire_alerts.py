"""Poller._fire_alerts 全局 1h 闸门 + 现有 per-provider 冷却。

覆盖:
- 跨 provider 合并到一次 toast
- 同一 provider warn -> critical 等级升级也被闸门拦住
- 全局时间未到不弹
- 全局时间到了再弹
- max_per_hour=0 等同关闭
- alert.enable=False 直接不弹
- cooldown_min=0 时不受影响(全局闸门独立)
"""
import threading
import time
import unittest
from unittest import mock

import main as main_mod


def _make_poller(cfg):
    state = main_mod.State()
    stop = threading.Event()
    wake = threading.Event()
    return main_mod.Poller(cfg, state, stop, wake), state


def _r(name, level):
    return {"name": name, "level": level}


class FireAlertsGlobalGate(unittest.TestCase):
    def _poller(self, **alert):
        cfg = {"alert": {"enable": True, "cooldown_min": 60, **alert}}
        return _make_poller(cfg)

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
        p._last_global_alert_ts = 0.0  # 假装过了一小时
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
        """全局时间未到,也不应重复同一个 provider 同样等级。"""
        p, _ = self._poller(cooldown_min=60, max_per_hour=60)
        p._fire_alerts([_r("A", "warn")])
        # 第二轮,即便全局闸门允许(假设),per-provider cooldown 也拦
        p._last_global_alert_ts = time.time() - 3700  # 全局过了
        p._fire_alerts([_r("A", "warn")])
        # 第二次应是全局闸门放过、per-provider 冷却拦截;调用仍是 1
        alert_many.assert_called_once()

    @mock.patch("notify.alert_many")
    def test_default_max_per_hour_is_60(self, alert_many):
        """配置缺失 max_per_hour 时,默认 60 分钟。"""
        cfg = {"alert": {"enable": True, "cooldown_min": 60}}
        p, _ = _make_poller(cfg)
        p._fire_alerts([_r("A", "warn")])
        # 第一次弹
        alert_many.assert_called_once()
        # 立刻第二次 -- 默认 60min 闸门拦截
        p._fire_alerts([_r("A", "warn")])
        alert_many.assert_called_once()


if __name__ == "__main__":
    unittest.main()