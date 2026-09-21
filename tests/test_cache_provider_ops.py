"""测试 cache.remove_provider_entries 和 cache.log_provider_deleted。"""
import json
import tempfile
import time
import unittest

import cache


class RemoveProviderEntries(unittest.TestCase):
    def _setup_tmp(self):
        d = tempfile.mkdtemp()
        cache.CACHE_DIR = type(cache.CACHE_DIR)(d)
        cache.MODELS_CACHE = cache.CACHE_DIR / "models.json"
        cache.PROBE_LOG = cache.CACHE_DIR / "probe.jsonl"

    def test_remove_existing(self):
        self._setup_tmp()
        cache.set_models("https://a", "k1", ["m1", "m2"])
        cache.set_models("https://b", "k2", ["m3"])
        self.assertTrue(cache.remove_provider_entries("https://a", "k1"))
        self.assertIsNone(cache.get_models("https://a", "k1"))
        self.assertEqual(cache.get_models("https://b", "k2"), ["m3"])

    def test_remove_missing(self):
        self._setup_tmp()
        cache.set_models("https://a", "k1", ["m1"])
        self.assertFalse(cache.remove_provider_entries("https://z", "kz"))

    def test_remove_empty_inputs(self):
        self._setup_tmp()
        cache.set_models("https://a", "k1", ["m1"])
        self.assertFalse(cache.remove_provider_entries("", ""))


class LogProviderDeleted(unittest.TestCase):
    def _setup_tmp(self):
        d = tempfile.mkdtemp()
        cache.CACHE_DIR = type(cache.CACHE_DIR)(d)
        cache.PROBE_LOG = cache.CACHE_DIR / "probe.jsonl"

    def test_appends_marker(self):
        self._setup_tmp()
        cache.log_provider_deleted("元序", base_url="https://a")
        lines = cache.PROBE_LOG.read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(lines), 1)
        entry = json.loads(lines[0])
        self.assertEqual(entry["event"], "provider_deleted")
        self.assertEqual(entry["provider"], "元序")
        self.assertEqual(entry["base_url"], "https://a")
        self.assertIn("ts", entry)

    def test_marker_coexists_with_probe(self):
        self._setup_tmp()
        cache.log_probe("A", "m1", True, 12.0)
        cache.log_provider_deleted("A")
        cache.log_probe("A", "m1", True, 8.0)
        lines = cache.PROBE_LOG.read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(lines), 3)
        self.assertEqual(json.loads(lines[1])["event"], "provider_deleted")


if __name__ == "__main__":
    unittest.main()
