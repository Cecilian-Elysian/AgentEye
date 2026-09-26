"""Poller._fire_alerts 简化版:只保留 per-provider 60min 冷却(硬编码)。

覆盖:
- warn/critical 收集到 items
- 同 provider 同 level 在 60min 内不重复弹
- 跨 level 升级不被拦住(level 切换算新告警)
- 跨 provider 不合并(各自独立计数)
- alert.enable=False 直接不弹
- 多 provider 同时告警各自弹一次
"""
import threading
import time
import unittest
from unittest import mock

import main as main_mod


def _r(name, level):
    return {"name": name, "level": level}


class FireAlertsBase(unittest.TestCase):
    """base:对 cache 持久化做隔离,所有子类的 _fire_alerts 调用都不会落盘。"""

    def setUp(self):
        self._save_patch = mock.patch.object(
            __import__("cache"), "save_alert_state")
        self.save_mock = self._save_patch.start()

    def tearDown(self):
        self._save_patch.stop()

    def _poller(self, **alert):
        cfg = {"alert": {"enable": True, **alert}}
        state = main_mod.State()
        stop = threading.Event()
        wake = threading.Event()
        p = main_mod.Poller(cfg, state, stop, wake)
        return p, state


class FireAlertsBasic(FireAlertsBase):
    @mock.patch("notify.alert_many")
    def test_first_alert_emits(self, alert_many):
        p, _ = self._poller()
        p._fire_alerts([_r("A", "warn")])
        alert_many.assert_called_once()
        items = alert_many.call_args[0][0]
        self.assertEqual(items, [("A", "额度偏低")])

    @mock.patch("notify.alert_many")
    def test_critical_uses_critical_verb(self, alert_many):
        p, _ = self._poller()
        p._fire_alerts([_r("A", "critical")])
        items = alert_many.call_args[0][0]
        self.assertEqual(items, [("A", "额度告急")])

    @mock.patch("notify.alert_many")
    def test_ok_level_ignored(self, alert_many):
        p, _ = self._poller()
        p._fire_alerts([_r("A", "ok"), _r("B", "ok")])
        alert_many.assert_not_called()

    @mock.patch("notify.alert_many")
    def test_disabled_does_not_emit(self, alert_many):
        p, _ = self._poller(enable=False)
        p._fire_alerts([_r("A", "warn"), _r("B", "critical")])
        alert_many.assert_not_called()


class FireAlertsPerProviderCooldown(FireAlertsBase):
    """同一 provider 同 level 在 60min 内不重复弹。"""

    @mock.patch("notify.alert_many")
    def test_same_provider_same_level_within_cooldown_blocked(self, alert_many):
        p, _ = self._poller()
        p._fire_alerts([_r("A", "warn")])
        p._fire_alerts([_r("A", "warn")])
        alert_many.assert_called_once()

    @mock.patch("notify.alert_many")
    def test_level_upgrade_resets_cooldown(self, alert_many):
        """warn -> critical 算新告警,应再弹一次。"""
        p, _ = self._poller()
        p._fire_alerts([_r("A", "warn")])
        p._fire_alerts([_r("A", "critical")])
        self.assertEqual(alert_many.call_count, 2)

    @mock.patch("notify.alert_many")
    def test_new_provider_independent(self, alert_many):
        """不同 provider 不共享 cooldown。"""
        p, _ = self._poller()
        p._fire_alerts([_r("A", "warn")])
        p._fire_alerts([_r("B", "critical")])
        self.assertEqual(alert_many.call_count, 2)

    @mock.patch("notify.alert_many")
    def test_cooldown_elapses_emits_again(self, alert_many):
        p, _ = self._poller()
        p._fire_alerts([_r("A", "warn")])
        # 篡改 notified 的时间戳到 1h 之前,模拟冷却过期
        for k, v in p.notified.items():
            p.notified[k] = (v[0], time.time() - 3700)
        p._fire_alerts([_r("A", "warn")])
        self.assertEqual(alert_many.call_count, 2)

    @mock.patch("notify.alert_many")
    def test_different_level_in_cooldown_still_emits(self, alert_many):
        """60min 内从 ok->warn,首次进入应弹。"""
        p, _ = self._poller()
        p._fire_alerts([_r("A", "ok")])
        p._fire_alerts([_r("A", "warn")])
        alert_many.assert_called_once()

    @mock.patch("notify.alert_many")
    def test_multiple_providers_each_emit(self, alert_many):
        """多个 provider 同时告警,各自弹一次。"""
        p, _ = self._poller()
        p._fire_alerts([_r("A", "warn"), _r("B", "critical"), _r("C", "warn")])
        alert_many.assert_called_once()
        # alert_many 接收 [(name, verb), ...] 列表
        items = alert_many.call_args[0][0]
        names = sorted([n for n, _ in items])
        self.assertEqual(names, ["A", "B", "C"])


class FireAlertsPersistence(FireAlertsBase):
    """每次 fire 都保存时间戳(简化版;只用于埋点,不再控制节流)。"""

    @mock.patch("notify.alert_many")
    def test_fire_saves_timestamp(self, alert_many):
        p, _ = self._poller()
        before = time.time()
        p._fire_alerts([_r("A", "warn")])
        alert_many.assert_called_once()
        self.save_mock.assert_called_once()
        saved_ts = self.save_mock.call_args[0][0]
        self.assertGreaterEqual(saved_ts, before)


if __name__ == "__main__":
    unittest.main()