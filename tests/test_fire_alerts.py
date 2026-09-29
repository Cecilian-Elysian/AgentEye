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
    """base:对 cache 持久化做隔离,所有子类的 _fire_alerts 调用都不会落盘,
    Poller 构造时也不会读到磁盘上真实的告警状态。"""

    def setUp(self):
        cache = __import__("cache")
        self._save_patch = mock.patch.object(cache, "save_alert_state")
        self.save_mock = self._save_patch.start()
        self._load_patch = mock.patch.object(
            cache, "load_alert_state", return_value={})
        self.load_mock = self._load_patch.start()

    def tearDown(self):
        self._save_patch.stop()
        self._load_patch.stop()

    def _poller(self, **alert):
        cfg = {"alert": {"enable": True, **alert}}
        state = main_mod.State()
        stop = threading.Event()
        wake = threading.Event()
        p = main_mod.Poller(cfg, state, stop, wake)
        return p, state

    def _poller_with_state(self, notified, **alert):
        """构造一个带既有冷却状态的 Poller(模拟重启后恢复)。"""
        cfg = {"alert": {"enable": True, **alert}}
        state = main_mod.State()
        p = main_mod.Poller(cfg, state, threading.Event(), threading.Event())
        p.notified = dict(notified)
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
    """告警冷却落盘:save_alert_state 收 per-provider 表,启动时读回。"""

    @mock.patch("notify.alert_many")
    def test_fire_saves_notified_table(self, alert_many):
        p, _ = self._poller()
        before = time.time()
        p._fire_alerts([_r("A", "warn")])
        alert_many.assert_called_once()
        self.save_mock.assert_called_once()
        saved = self.save_mock.call_args[0][0]
        self.assertIsInstance(saved, dict)
        self.assertEqual(list(saved), ["A"])
        level, ts = saved["A"]
        self.assertEqual(level, "warn")
        self.assertGreaterEqual(ts, before)

    @mock.patch("notify.alert_many")
    def test_no_alert_no_save(self, alert_many):
        p, _ = self._poller()
        p._fire_alerts([_r("A", "ok")])
        alert_many.assert_not_called()
        self.save_mock.assert_not_called()

    @mock.patch("notify.alert_many")
    def test_persisted_state_survives_restart(self, alert_many):
        """重启后从磁盘恢复的冷却仍然有效,60 分钟内不重复弹。"""
        p, _ = self._poller()
        p._fire_alerts([_r("A", "warn")])
        self.assertEqual(len(alert_many.call_args_list), 1)

        # 模拟重启:新 Poller 从持久化状态恢复
        restored = {"A": ["warn", time.time()]}
        p2, _ = self._poller_with_state(restored)
        p2._fire_alerts([_r("A", "warn")])
        self.assertEqual(len(alert_many.call_args_list), 1,
                         "冷却应跨重启生效,不重复弹")

    @mock.patch("notify.alert_many")
    def test_persisted_still_allows_level_upgrade(self, alert_many):
        """恢复的冷却不该挡住 warn -> critical 的升级告警。"""
        restored = {"A": ["warn", time.time()]}
        p, _ = self._poller_with_state(restored)
        p._fire_alerts([_r("A", "critical")])
        alert_many.assert_called_once()

    def test_poller_loads_state_at_construction(self):
        with mock.patch.object(
                __import__("cache"), "load_alert_state",
                return_value={"A": ["critical", 123.0]}) as load:
            self._poller()
        load.assert_called_once()


class AlertStateCacheRoundtrip(unittest.TestCase):
    """cache.save_alert_state / load_alert_state 的落盘格式。"""

    def setUp(self):
        import tempfile
        from pathlib import Path
        cache = __import__("cache")
        self._tmp = tempfile.TemporaryDirectory()
        self._orig = cache.ALERT_STATE
        cache.ALERT_STATE = Path(self._tmp.name) / "alert_state.json"

    def tearDown(self):
        __import__("cache").ALERT_STATE = self._orig
        self._tmp.cleanup()

    def test_roundtrip(self):
        cache = __import__("cache")
        cache.save_alert_state({"A": ["warn", 1.5], "B": ["critical", 2.5]})
        self.assertEqual(cache.load_alert_state(),
                         {"A": ["warn", 1.5], "B": ["critical", 2.5]})

    def test_load_missing_file(self):
        cache = __import__("cache")
        self.assertEqual(cache.load_alert_state(), {})

    def test_save_sanitises_bad_entries(self):
        cache = __import__("cache")
        cache.save_alert_state({
            "ok": ["warn", 1.0],          # 合法
            "bad_level": ["nonsense", 1.0],  # 等级非法
            "bad_len": ["warn"],            # 长度不对
            "bad_ts": ["warn", "abc"],      # 时间戳非法
            123: ["warn", 1.0],             # 键不是字符串
            "bad_type": "warn",             # 值不是序列
        })
        self.assertEqual(list(cache.load_alert_state()), ["ok"])

    def test_load_ignores_legacy_single_ts_shape(self):
        """旧版只存 last_alert_ts,读不出 provider 表时按空表处理。"""
        cache = __import__("cache")
        cache.ALERT_STATE.write_text('{"last_alert_ts": 123.0}',
                                     encoding="utf-8")
        self.assertEqual(cache.load_alert_state(), {})

    def test_load_tolerates_corrupt_json(self):
        cache = __import__("cache")
        cache.ALERT_STATE.write_text("{ 坏掉的 json", encoding="utf-8")
        self.assertEqual(cache.load_alert_state(), {})

    def test_save_non_dict_writes_empty_table(self):
        cache = __import__("cache")
        cache.save_alert_state("垃圾")
        self.assertEqual(cache.load_alert_state(), {})


if __name__ == "__main__":
    unittest.main()