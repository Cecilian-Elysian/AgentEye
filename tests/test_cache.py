import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import cache


class TestModelsCache(unittest.TestCase):
    def setUp(self):
        cache._ensure()

    def test_set_and_get(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(cache, "MODELS_CACHE", Path(tmp) / "models.json"):
                cache.set_models("https://api.example.com/v1", "sk-abc", ["gpt-4o", "gpt-4o-mini"])
                got = cache.get_models("https://api.example.com/v1", "sk-abc")
                self.assertEqual(got, ["gpt-4o", "gpt-4o-mini"])

    def test_ttl_expiry(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(cache, "MODELS_CACHE", Path(tmp) / "models.json"):
                cache.set_models("https://api.example.com", "k", ["x"])
                got = cache.get_models("https://api.example.com", "k", ttl=0)
                self.assertIsNone(got)

    def test_missing_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(cache, "MODELS_CACHE", Path(tmp) / "models.json"):
                self.assertIsNone(cache.get_models("nope", "nada"))

    def test_different_keys_isolated(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(cache, "MODELS_CACHE", Path(tmp) / "models.json"):
                cache.set_models("https://a.com", "k1", ["m1"])
                cache.set_models("https://b.com", "k2", ["m2"])
                self.assertEqual(cache.get_models("https://a.com", "k1"), ["m1"])
                self.assertEqual(cache.get_models("https://b.com", "k2"), ["m2"])

    def test_invalidate_specific(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(cache, "MODELS_CACHE", Path(tmp) / "models.json"):
                cache.set_models("https://a.com", "k1", ["m1"])
                cache.set_models("https://b.com", "k2", ["m2"])
                cache.invalidate_models("https://a.com", "k1")
                self.assertIsNone(cache.get_models("https://a.com", "k1"))
                self.assertEqual(cache.get_models("https://b.com", "k2"), ["m2"])

    def test_invalidate_all(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(cache, "MODELS_CACHE", Path(tmp) / "models.json"):
                cache.set_models("https://a.com", "k1", ["m1"])
                cache.invalidate_models()
                self.assertIsNone(cache.get_models("https://a.com", "k1"))


class TestProbeLog(unittest.TestCase):
    def setUp(self):
        cache._ensure()

    def test_log_and_recent(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(cache, "PROBE_LOG", Path(tmp) / "probe.jsonl"):
                cache.log_probe("p1", "gpt-4o", True, 123.4)
                cache.log_probe("p1", "claude", False, 5000.0, error="timeout")
                recents = cache.recent_probes(limit=10)
                self.assertEqual(len(recents), 2)
                self.assertEqual(recents[0]["model"], "claude")
                self.assertFalse(recents[0]["success"])
                self.assertEqual(recents[1]["model"], "gpt-4o")
                self.assertTrue(recents[1]["success"])

    def test_filter_by_provider(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(cache, "PROBE_LOG", Path(tmp) / "probe.jsonl"):
                cache.log_probe("p1", "m", True, 100)
                cache.log_probe("p2", "m", True, 200)
                cache.log_probe("p1", "m2", True, 150)
                recents = cache.recent_probes(provider_name="p1")
                self.assertEqual(len(recents), 2)
                self.assertTrue(all(r["provider"] == "p1" for r in recents))

    def test_last_probe(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(cache, "PROBE_LOG", Path(tmp) / "probe.jsonl"):
                cache.log_probe("p1", "gpt-4o", True, 100)
                cache.log_probe("p1", "gpt-4o", True, 200)
                cache.log_probe("p1", "claude", True, 300)
                last = cache.last_probe("p1", "gpt-4o")
                self.assertEqual(last["latency_ms"], 200)
                self.assertIsNone(cache.last_probe("p1", "missing"))

    def test_empty_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(cache, "PROBE_LOG", Path(tmp) / "probe.jsonl"):
                self.assertEqual(cache.recent_probes(), [])


if __name__ == "__main__":
    unittest.main()
