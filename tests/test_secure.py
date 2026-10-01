"""secure.py (DPAPI) 与 config 明文/密文契约测试。

覆盖:
- protect / unprotect 往返、base64 形态、脏数据与空输入降级
- save_v2 不改写调用方的内存 cfg(加密只发生在副本上)
- load_v2 把磁盘上的 key_enc 还原成内存态明文 key
- providers 轮询路径能解析只有 key_enc 的 provider
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import base64

import config as config_mod
import secure


class TestSecureBasics(unittest.TestCase):
    """DPAPI 基础能力。"""

    def setUp(self):
        self.win = secure.is_available()

    def test_is_available_matches_platform(self):
        self.assertEqual(self.win, sys.platform == "win32")

    def test_protect_rejects_empty(self):
        self.assertIsNone(secure.protect(""))
        self.assertIsNone(secure.protect(None))

    def test_unprotect_rejects_empty(self):
        self.assertIsNone(secure.unprotect(""))
        self.assertIsNone(secure.unprotect(None))

    def test_unprotect_rejects_non_base64(self):
        self.assertIsNone(secure.unprotect("这不是 base64 !!!"))

    def test_unprotect_rejects_valid_base64_garbage(self):
        junk = base64.b64encode(b"\x00\x01\x02not-a-dpapi-blob").decode()
        self.assertIsNone(secure.unprotect(junk))

    @unittest.skipUnless(sys.platform == "win32", "需要 Windows DPAPI")
    def test_roundtrip_ascii(self):
        enc = secure.protect("sk-test-123456")
        self.assertIsNotNone(enc)
        self.assertNotEqual(enc, "sk-test-123456")
        self.assertEqual(secure.unprotect(enc), "sk-test-123456")

    @unittest.skipUnless(sys.platform == "win32", "需要 Windows DPAPI")
    def test_roundtrip_unicode(self):
        enc = secure.protect("密钥-Ünïcødé-🔑")
        self.assertEqual(secure.unprotect(enc), "密钥-Ünïcødé-🔑")

    @unittest.skipUnless(sys.platform == "win32", "需要 Windows DPAPI")
    def test_protected_payload_is_base64_ascii(self):
        enc = secure.protect("sk-abc")
        self.assertTrue(all(c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                                  "abcdefghijklmnopqrstuvwxyz0123456789+/="
                            for c in enc))
        self.assertGreater(len(base64.b64decode(enc)), len("sk-abc"))

    @unittest.skipUnless(sys.platform == "win32", "需要 Windows DPAPI")
    def test_encrypt_same_key_twice_differs_but_both_decode(self):
        # DPAPI 带随机盐,两次密文不同,但都能解回原文
        a = secure.protect("sk-same")
        b = secure.protect("sk-same")
        self.assertNotEqual(a, b)
        self.assertEqual(secure.unprotect(a), "sk-same")
        self.assertEqual(secure.unprotect(b), "sk-same")

    def test_protect_returns_none_when_unavailable(self):
        if not self.win:
            self.assertIsNone(secure.protect("sk-abc"))


class ConfigPathMixin(unittest.TestCase):
    """把 config.CONFIG_PATH 指到临时目录,避免污染真实配置。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._orig = config_mod.CONFIG_PATH
        config_mod.CONFIG_PATH = Path(self.tmp.name) / "config.json"

    def tearDown(self):
        config_mod.CONFIG_PATH = self._orig
        self.tmp.cleanup()

    def _read_disk(self):
        import json
        return json.loads(config_mod.CONFIG_PATH.read_text(encoding="utf-8"))


class TestSaveDoesNotMutateCaller(ConfigPathMixin):
    """save_v2 只在副本上加密,调用方的 cfg 保持明文。"""

    def _cfg(self):
        return {
            "schema_version": 2,
            "refresh_interval_sec": 60,
            "alert": {"enable": True, "warn_pct": 30,
                      "critical_amount_yuan": 5.0},
            "ui": {"x": None, "y": None, "width": 360, "height": 360,
                   "order": [], "pinned": True, "mode": "standard",
                   "theme": "dark"},
            "providers": [
                {"id": "p1", "kind": "deepseek", "name": "DS",
                 "key": "sk-in-memory", "base_url": "https://x", "extra": {}}
            ],
        }

    def test_caller_cfg_keeps_plaintext_key(self):
        cfg = self._cfg()
        config_mod.save_v2(cfg)
        self.assertEqual(cfg["providers"][0]["key"], "sk-in-memory")
        self.assertNotIn("key_enc", cfg["providers"][0])

    def test_caller_cfg_is_a_separate_object(self):
        cfg = self._cfg()
        config_mod.save_v2(cfg)
        disk = self._read_disk()
        self.assertIsNot(disk, cfg)
        self.assertIsNot(disk["providers"][0], cfg["providers"][0])

    @unittest.skipUnless(sys.platform == "win32", "需要 Windows DPAPI")
    def test_disk_holds_key_enc_and_drops_key(self):
        config_mod.save_v2(self._cfg())
        p = self._read_disk()["providers"][0]
        self.assertNotIn("key", p)
        self.assertIn("key_enc", p)
        self.assertEqual(secure.unprotect(p["key_enc"]), "sk-in-memory")

    @unittest.skipUnless(sys.platform == "win32", "需要 Windows DPAPI")
    def test_roundtrip_save_then_load(self):
        config_mod.save_v2(self._cfg())
        loaded = config_mod.load_v2()
        p = loaded["providers"][0]
        self.assertEqual(p["key"], "sk-in-memory")
        self.assertNotIn("key_enc", p)
        self.assertEqual(config_mod.plain_key(p), "sk-in-memory")

    def test_plain_key_reads_plain_field(self):
        self.assertEqual(
            config_mod.plain_key({"key": "sk-plain"}), "sk-plain")

    def test_plain_key_on_non_dict(self):
        self.assertEqual(config_mod.plain_key(None), "")
        self.assertEqual(config_mod.plain_key("x"), "")

    def test_decrypt_providers_noop_without_key_enc(self):
        providers = [{"id": "a", "key": "sk-x"}]
        self.assertFalse(config_mod._decrypt_providers(providers))
        self.assertEqual(providers[0]["key"], "sk-x")

    def test_decrypt_providers_keeps_undecryptable_key_enc(self):
        providers = [{"id": "a", "key_enc": "###bad###"}]
        self.assertFalse(config_mod._decrypt_providers(providers))
        self.assertNotIn("key", providers[0])
        self.assertIn("key_enc", providers[0])


class TestPollingResolvesEncryptedKey(ConfigPathMixin):
    """轮询路径必须能解析只有 key_enc 的 provider。"""

    def test_load_hydrates_key_from_key_enc(self):
        import json
        payload = {
            "schema_version": 2,
            "refresh_interval_sec": 60,
            "alert": {},
            "ui": {},
            "providers": [{"id": "p1", "kind": "deepseek", "name": "DS",
                           "base_url": "https://x", "extra": {}}],
        }
        if secure.is_available():
            enc = secure.protect("sk-encrypted")
            self.assertIsNotNone(enc)
            payload["providers"][0]["key_enc"] = enc
            expect = "sk-encrypted"
        else:
            payload["providers"][0]["key"] = "sk-encrypted"
            expect = "sk-encrypted"
        config_mod.atomic_save(config_mod.CONFIG_PATH, payload)

        loaded = config_mod.load_v2()
        self.assertEqual(loaded["providers"][0]["key"], expect)

    def test_resolve_key_prefers_plain_field(self):
        from providers import KeyDecryptError, _resolve_key
        self.assertEqual(_resolve_key({"key": "sk-plain"}), "sk-plain")
        self.assertEqual(_resolve_key({}), "")
        # key_enc 解不开不再是静默空串:必须可区分地报出来
        with self.assertRaises(KeyDecryptError):
            _resolve_key({"key_enc": "###bad###"})

    def test_one_marks_unconfigured_without_any_key(self):
        from providers import _one
        res = _one("deepseek", {"id": "p", "name": "DS", "base_url": ""}, {})
        self.assertTrue(res["unconfigured"])
        self.assertEqual(res["level"], "unconfigured")

    def test_one_ignores_placeholder_key(self):
        from providers import _one
        entry = {"id": "p", "name": "DS", "key": "在这里粘贴DeepSeek的key"}
        res = _one("deepseek", entry, {})
        self.assertTrue(res["unconfigured"])

    def test_to_legacy_entry_uses_resolved_key(self):
        from providers import _to_legacy_entry
        p = {"name": "DS", "base_url": "https://x", "extra": {"a": 1},
             "headers": {"X": "1"}}
        legacy = _to_legacy_entry(p, "sk-resolved")
        self.assertEqual(legacy["api_key"], "sk-resolved")
        self.assertEqual(legacy["token"], "sk-resolved")
        self.assertEqual(legacy["key"], "sk-resolved")
        self.assertEqual(legacy["a"], 1)
        self.assertEqual(legacy["headers"], {"X": "1"})


if __name__ == "__main__":
    unittest.main()
