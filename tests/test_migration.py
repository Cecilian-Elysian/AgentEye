import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import config as config_mod
from config import (
    DEFAULT_BASE_URLS,
    KIND_FROM_V1_KEY,
    V2_TEMPLATE,
    migrate_v1_to_v2,
    atomic_save,
    clamp_interval_v2,
)


def _make_v1_minimal():
    return {
        "refresh_interval_sec": 600,
        "alert": {"warn_amount": 20},
        "ui": {"x": 100, "y": 200},
        "relay_sites": [],
        "minimax": [{"name": "我的 MiniMax", "api_key": "sk-cp-real-key-12345"}],
        "opencode_go": [{"api_key": "eyJ-real-jwt-key"}],
        "deepseek": [{"name": "DS", "api_key": "sk-ds-real", "warn_amount": 50}],
        "zhipu": [{"api_key": "zhipu-key"}],
    }


class TestMigrateV1ToV2(unittest.TestCase):
    def test_schema_version_set(self):
        v2 = migrate_v1_to_v2(_make_v1_minimal())
        self.assertEqual(v2["schema_version"], 2)

    def test_providers_list_populated(self):
        v2 = migrate_v1_to_v2(_make_v1_minimal())
        kinds = [p["kind"] for p in v2["providers"]]
        self.assertEqual(kinds, ["minimax", "opencode_go", "deepseek", "zhipu"])

    def test_provider_fields(self):
        v2 = migrate_v1_to_v2(_make_v1_minimal())
        m = next(p for p in v2["providers"] if p["kind"] == "minimax")
        self.assertEqual(m["key"], "sk-cp-real-key-12345")
        self.assertEqual(m["name"], "我的 MiniMax")
        self.assertEqual(m["base_url"], "https://api.minimaxi.com")
        self.assertEqual(len(m["id"]), 12)

    def test_deepseek_passthrough(self):
        v2 = migrate_v1_to_v2(_make_v1_minimal())
        d = next(p for p in v2["providers"] if p["kind"] == "deepseek")
        self.assertEqual(d.get("warn_amount"), 50)

    def test_opencode_default_url(self):
        v2 = migrate_v1_to_v2(_make_v1_minimal())
        o = next(p for p in v2["providers"] if p["kind"] == "opencode_go")
        self.assertEqual(o["base_url"], "https://opencode.ai")

    def test_zhipu_default_url(self):
        v2 = migrate_v1_to_v2(_make_v1_minimal())
        z = next(p for p in v2["providers"] if p["kind"] == "zhipu")
        self.assertEqual(z["base_url"], "https://open.bigmodel.cn")

    def test_relay_with_token_field(self):
        v1 = {"relay_sites": [{"name": "元序",
                               "base_url": "https://token.yuanxuai.xyz",
                               "token": "sk-relay-token-real"}]}
        v2 = migrate_v1_to_v2(v1)
        self.assertEqual(len(v2["providers"]), 1)
        r = v2["providers"][0]
        self.assertEqual(r["kind"], "relay")
        self.assertEqual(r["key"], "sk-relay-token-real")
        self.assertEqual(r["base_url"], "https://token.yuanxuai.xyz")

    def test_relay_email_password_preserved(self):
        v1 = {"relay_sites": [{"base_url": "https://x",
                               "email": "a@b.com",
                               "password": "pw"}]}
        v2 = migrate_v1_to_v2(v1)
        r = v2["providers"][0]
        self.assertEqual(r["extra"].get("email"), "a@b.com")
        self.assertEqual(r["extra"].get("password"), "pw")

    def test_global_config_preserved(self):
        v2 = migrate_v1_to_v2(_make_v1_minimal())
        self.assertEqual(v2["refresh_interval_sec"], 600)
        self.assertEqual(v2["ui"], {"x": 100, "y": 200})
        self.assertEqual(v2["alert"]["warn_amount"], 20)

    def test_aggregate_defaults_present(self):
        v2 = migrate_v1_to_v2(_make_v1_minimal())
        self.assertIn("aggregate", v2)
        self.assertTrue(v2["aggregate"]["enabled"])
        self.assertEqual(v2["aggregate"]["monthly_budget_usd"], 100.0)

    def test_empty_v1(self):
        v2 = migrate_v1_to_v2({})
        self.assertEqual(v2["providers"], [])
        self.assertEqual(v2["schema_version"], 2)

    def test_bad_v1(self):
        v2 = migrate_v1_to_v2(None)
        self.assertEqual(v2, V2_TEMPLATE)

    def test_each_kind_produces_unique_id(self):
        v2 = migrate_v1_to_v2(_make_v1_minimal())
        ids = [p["id"] for p in v2["providers"]]
        self.assertEqual(len(ids), len(set(ids)))


class TestAtomicSave(unittest.TestCase):
    def test_writes_file(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "test.json"
            atomic_save(p, {"a": 1, "b": ["x", "y"]})
            self.assertTrue(p.exists())
            data = json.loads(p.read_text(encoding="utf-8"))
            self.assertEqual(data["a"], 1)
            self.assertEqual(data["b"], ["x", "y"])

    def test_no_tmp_file_left(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "test.json"
            atomic_save(p, {"x": 1})
            self.assertFalse(p.with_suffix(p.suffix + ".tmp").exists())

    def test_overwrites_existing(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "test.json"
            atomic_save(p, {"v": 1})
            atomic_save(p, {"v": 2})
            data = json.loads(p.read_text(encoding="utf-8"))
            self.assertEqual(data["v"], 2)


class TestClampIntervalV2(unittest.TestCase):
    def test_default_30(self):
        self.assertEqual(clamp_interval_v2({}), 30)

    def test_clamp_min_15(self):
        self.assertEqual(clamp_interval_v2({"refresh_interval_sec": 5}), 15)

    def test_clamp_max_3600(self):
        self.assertEqual(clamp_interval_v2({"refresh_interval_sec": 99999}), 3600)

    def test_normal(self):
        self.assertEqual(clamp_interval_v2({"refresh_interval_sec": 120}), 120)


if __name__ == "__main__":
    unittest.main()
