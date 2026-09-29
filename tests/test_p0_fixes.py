"""P0/P1 修复的回归测试。

覆盖:
- config:损坏文件留证不覆盖、schema_version>2 报错、v1 迁移先备份、
  env key 不落盘、明文拒写盘
- providers:fetch_all 保序、单行失败不连累、extra 不旁路覆盖 key
- relay:token 缓存按 (base, email) 隔离
- minimax:接口级报错优先于结构解析、headline 兜底
- generic:billing total_used 字段名兼容
- theme:监听器随 widget 销毁自动反注册
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config as config_mod
import providers
from providers import relay
from providers import generic as generic_mod
from providers import minimax as minimax_mod


class ConfigPathMixin(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._orig = config_mod.CONFIG_PATH
        config_mod.CONFIG_PATH = Path(self.tmp.name) / "config.json"

    def tearDown(self):
        config_mod.CONFIG_PATH = self._orig
        self.tmp.cleanup()

    def _write(self, text):
        config_mod.CONFIG_PATH.write_text(text, encoding="utf-8")


class TestCorruptConfigQuarantine(ConfigPathMixin):
    """损坏的 config.json 必须改名留证,绝不能被空模板覆盖。"""

    def test_corrupt_file_is_preserved(self):
        garbage = '{"schema_version": 2, "providers": [ {"key": "sk-'
        self._write(garbage)
        cfg = config_mod.load_v2()
        self.assertEqual(cfg.get("providers"), [])
        # 原文被挪到 corrupt-* 文件里,内容原样
        quarantined = list(Path(self.tmp.name).glob("config.json.corrupt-*"))
        self.assertEqual(len(quarantined), 1, "应恰好留下一份损坏原文")
        self.assertEqual(
            quarantined[0].read_text(encoding="utf-8"), garbage)
        # 本次启动不写盘,不产生新的 config.json
        self.assertFalse(config_mod.CONFIG_PATH.exists())

    def test_non_dict_root_is_quarantined(self):
        self._write('[1, 2, 3]')
        cfg = config_mod.load_v2()
        self.assertEqual(cfg.get("providers"), [])
        quarantined = list(Path(self.tmp.name).glob("config.json.corrupt-*"))
        self.assertEqual(len(quarantined), 1)

    def test_future_version_raises_not_migrates(self):
        future = {"schema_version": 3, "providers": [
            {"id": "p1", "kind": "deepseek", "name": "DS",
             "key_enc": "AAAA", "base_url": "https://x"}]}
        self._write(json.dumps(future))
        with self.assertRaises(config_mod.ConfigVersionError):
            config_mod.load_v2()
        # 原文件原地保留,程序没动它
        self.assertEqual(json.loads(config_mod.CONFIG_PATH.read_text(
            encoding="utf-8")), future)


class TestV1MigrationBacksUpFirst(ConfigPathMixin):
    def test_migration_creates_backup(self):
        v1 = {"deepseek_keys": ["sk-old"], "refresh_interval_sec": 45}
        self._write(json.dumps(v1))
        cfg = config_mod.load_v2()
        backup = config_mod.CONFIG_PATH.with_suffix(".v1.bak")
        self.assertTrue(backup.exists(), "迁移前必须先落一份 v1 备份")
        self.assertEqual(json.loads(backup.read_text(encoding="utf-8")), v1)
        self.assertEqual(cfg.get("schema_version"), 2)


class TestEnvKeyNeverHitsDisk(ConfigPathMixin):
    def test_env_key_not_written_back(self):
        env = {"DEEPSEEK_API_KEY": "sk-from-env"}
        cfg = {
            "schema_version": 2,
            "providers": [
                {"id": "p1", "kind": "deepseek", "name": "DS",
                 "base_url": "https://x", "extra": {}}
            ],
        }
        config_mod.atomic_save(config_mod.CONFIG_PATH, cfg)
        with mock.patch.dict(os.environ, env):
            loaded = config_mod.load_v2()
            self.assertEqual(loaded["providers"][0]["key"], "sk-from-env")
            # 用户改任何东西触发保存:env key 不允许进配置文件
            config_mod.save_v2(loaded)
            disk = json.loads(config_mod.CONFIG_PATH.read_text(
                encoding="utf-8"))
        p = disk["providers"][0]
        self.assertNotIn("key", p, "env 来的明文 key 不能落盘")
        self.assertNotIn("key_enc", p, "env key 也不该被加密后落盘")
        self.assertNotIn("_key_from_env", p)


class TestPlaintextRefusedOnDisk(ConfigPathMixin):
    def test_save_raises_when_encryption_unavailable(self):
        cfg = {
            "schema_version": 2,
            "providers": [
                {"id": "p1", "kind": "deepseek", "name": "DS",
                 "key": "sk-plain", "base_url": "https://x", "extra": {}}
            ],
        }
        with mock.patch("secure.is_available", return_value=False):
            with self.assertRaises(config_mod.PlaintextKeyError):
                config_mod.save_v2(cfg)
        self.assertFalse(config_mod.CONFIG_PATH.exists(),
                         "拒写盘时不该留下任何文件")


class TestFetchAllOrderAndIsolation(unittest.TestCase):
    def _cfg(self, names):
        return {"schema_version": 2, "providers": [
            {"id": f"p{i}", "kind": "generic", "name": n,
             "key": "sk-x", "base_url": "https://h", "extra": {}}
            for i, n in enumerate(names)
        ]}

    def test_results_follow_cfg_order_with_skip(self):
        cfg = self._cfg(["a", "b", "c"])
        with mock.patch.object(providers, "_one",
                               side_effect=lambda k, e, c: {
                                   "name": e["name"], "level": "ok",
                                   "paused": False}):
            results = providers.fetch_all(cfg, skip_names={"b"})
        self.assertEqual([r["name"] for r in results], ["a", "b", "c"])
        self.assertTrue(results[1]["paused"])
        self.assertFalse(results[0]["paused"])

    def test_one_row_failure_does_not_sink_others(self):
        cfg = self._cfg(["a", "b"])
        calls = {"n": 0}

        def boom(kind, entry, cfg):
            calls["n"] += 1
            if entry["name"] == "b":
                raise RuntimeError("adapter exploded")
            return {"name": entry["name"], "level": "ok"}

        with mock.patch.object(providers, "_one", side_effect=boom):
            results = providers.fetch_all(cfg)
        self.assertEqual([r["name"] for r in results], ["a", "b"])
        self.assertEqual(results[0]["level"], "ok")
        self.assertEqual(results[1]["level"], providers.LEVEL_ERROR)
        self.assertIn("RuntimeError", results[1]["error"])

    def test_extra_cannot_bypass_resolved_key(self):
        p = {"id": "p1", "kind": "generic", "name": "n",
             "key": "real-key", "base_url": "https://x",
             "extra": {"key": "fake-from-extra",
                       "token": "fake-token-from-extra"}}
        entry = providers._to_legacy_entry(p, "real-key")
        self.assertEqual(entry["key"], "real-key")
        self.assertEqual(entry["api_key"], "real-key")
        self.assertEqual(entry["token"], "real-key")


class TestRelayTokenCacheIsolation(unittest.TestCase):
    def test_same_base_different_accounts_get_own_tokens(self):
        relay._TOKEN_CACHE.clear()
        responses = {
            "a@x.com": {"access_token": "tok-a", "expires_in": 3600},
            "b@x.com": {"access_token": "tok-b", "expires_in": 3600},
        }

        def fake_post(url, json=None, timeout=None):
            resp = mock.Mock()
            resp.status_code = 200
            resp.json.return_value = responses[json["email"]]
            return resp

        with mock.patch.object(relay.requests, "post", side_effect=fake_post):
            ta, _ = relay._get_access_token("https://h", "a@x.com", "pw")
            tb, _ = relay._get_access_token("https://h", "b@x.com", "pw")
        self.assertEqual(ta, "tok-a")
        self.assertEqual(tb, "tok-b")
        self.assertEqual(len(relay._TOKEN_CACHE), 2,
                         "同域双账号必须各持一份 token")
        relay._TOKEN_CACHE.clear()


class TestMinimaxOrdering(unittest.TestCase):
    def test_api_error_wins_over_structure(self):
        with mock.patch.object(minimax_mod.requests, "get") as g:
            g.return_value.status_code = 200
            g.return_value.json.return_value = {
                "base_resp": {"status_code": 1004, "status_msg": "bad key"}}
            res = minimax_mod.fetch({"api_key": "ey-", "plan": "token_plan"})
        self.assertIn("接口报错", res["error"])

    def test_headline_falls_back_to_model_with_pct(self):
        body = {"base_resp": {"status_code": 0}, "data": {
            "model_remains": [
                {"model_name": "abab5", "interval_remaining_percent": None},
                {"model_name": "mini", "interval_remaining_percent": 42.0,
                 "remains_time": 5400000},
            ]}}
        with mock.patch.object(minimax_mod.requests, "get") as g:
            g.return_value.status_code = 200
            g.return_value.json.return_value = body
            res = minimax_mod.fetch({"api_key": "ey-", "plan": "token_plan"})
        self.assertEqual(res["pct"], 42.0)
        self.assertIn("重置 1h30m", res["detail"],
                      "headline 应跟着有百分比的模型走")


class TestGenericBillingField(unittest.TestCase):
    def test_total_used_legacy_name(self):
        res = generic_mod._parse_openai_billing(
            {"total_granted": 100.0, "total_used": 30.0,
             "total_available": 70.0})
        self.assertEqual(res["used"], 30.0)

    def test_total_used_amount_wrapper_name(self):
        res = generic_mod._parse_openai_billing(
            {"total_granted": 100.0, "total_used_amount": 30.0,
             "total_available": 70.0})
        self.assertEqual(res["used"], 30.0)


class TestThemeListenerTeardown(unittest.TestCase):
    """widget 销毁后主题监听器必须自动反注册,不能残留。"""

    def test_destroyed_widget_unregisters(self):
        import tkinter as tk
        import ui.theme as theme_mod

        root = tk.Tk()
        self.addCleanup(root.destroy)
        frame = tk.Frame(root)
        frame.pack()
        frame.update_idletasks()

        calls = []
        orig_choice = theme_mod.current_choice()
        self.addCleanup(
            lambda: theme_mod.set_theme(orig_choice, broadcast=False,
                                        persist=False))
        unbind = theme_mod.bind_theme_listener(
            frame, lambda *a: calls.append(a))
        self.assertTrue(callable(unbind))

        # 销毁 frame:<Destroy> 事件同步触发,监听器应被摘除
        frame.destroy()
        theme_mod.set_theme("light", broadcast=True, persist=False)
        theme_mod.set_theme("dark", broadcast=True, persist=False)
        self.assertEqual(calls, [], "销毁后的 widget 不应再收到主题广播")


if __name__ == "__main__":
    unittest.main()
