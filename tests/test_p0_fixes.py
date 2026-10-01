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
import re
import sys
import tempfile
import threading
import tkinter as tk
import time
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


class TestReadFailureIsNotCorruption(ConfigPathMixin):
    """读不到 ≠ 文件损坏。OSError 绝不能触发隔离留证。"""

    def test_transient_oserror_retries_then_succeeds(self):
        v2 = {"schema_version": 2, "providers": [
            {"id": "p1", "kind": "deepseek", "name": "DS",
             "key": "sk-real", "base_url": "https://x"}]}
        self._write(json.dumps(v2))
        real = config_mod.CONFIG_PATH.read_text(encoding="utf-8")
        calls = {"n": 0}

        def flaky(*a, **kw):
            calls["n"] += 1
            if calls["n"] < 3:
                raise PermissionError(5, "被另一个进程占用")
            return real

        with mock.patch.object(config_mod.Path, "read_text", side_effect=flaky):
            cfg = config_mod.load_v2()
        self.assertEqual(cfg["providers"][0]["name"], "DS")
        # 关键:一个损坏备份都不该产生
        self.assertEqual(
            list(Path(self.tmp.name).glob("config.json.corrupt-*")), [])

    def test_persistent_oserror_raises_and_writes_nothing(self):
        v2 = {"schema_version": 2, "providers": [
            {"id": "p1", "kind": "deepseek", "name": "DS", "key": "sk-x"}]}
        self._write(json.dumps(v2))
        before = config_mod.CONFIG_PATH.read_text(encoding="utf-8")
        with mock.patch.object(config_mod.Path, "read_text",
                               side_effect=PermissionError(32, "文件被占用")):
            with self.assertRaises(config_mod.ConfigError):
                config_mod.load_v2()
        # 原文件原地保留,没有被改名,也没有被覆盖
        self.assertTrue(config_mod.CONFIG_PATH.exists())
        self.assertEqual(config_mod.CONFIG_PATH.read_text(encoding="utf-8"),
                         before)
        self.assertEqual(
            list(Path(self.tmp.name).glob("config.json.corrupt-*")), [])

    def test_undecodable_bytes_still_quarantined(self):
        """字节流真的坏了仍走隔离留证(那是真损坏)。"""
        config_mod.CONFIG_PATH.write_bytes(b"\xff\xfe\x00garbage")
        cfg = config_mod.load_v2()
        self.assertEqual(cfg.get("providers"), [])
        quarantined = list(Path(self.tmp.name).glob("config.json.corrupt-*"))
        self.assertEqual(len(quarantined), 1)


class TestProvidersShapeNormalization(ConfigPathMixin):
    """手改配置可能塞进非对象条目,必须归一而不是每次启动崩掉。"""

    def _load(self, providers_value):
        self._write(json.dumps({"schema_version": 2,
                                "providers": providers_value}))
        return config_mod.load_v2()

    def test_null_member_is_dropped(self):
        cfg = self._load([None, {"id": "p1", "kind": "deepseek", "name": "DS"}])
        self.assertEqual(len(cfg["providers"]), 1)
        self.assertEqual(cfg["providers"][0]["name"], "DS")

    def test_all_non_dict_members(self):
        cfg = self._load(["a", 3, None])
        self.assertEqual(cfg["providers"], [])

    def test_providers_as_single_dict(self):
        cfg = self._load({"id": "p1", "kind": "deepseek", "name": "DS"})
        self.assertEqual(len(cfg["providers"]), 1)
        self.assertEqual(cfg["providers"][0]["name"], "DS")

    def test_providers_wrong_type_becomes_empty_list(self):
        cfg = self._load("nope")
        self.assertEqual(cfg["providers"], [])


class TestExitCodes(unittest.TestCase):
    """AGENTS.md 退出码契约:2 必须真的可达。"""

    def test_config_version_error_returns_2(self):
        import main as main_mod
        with mock.patch.object(
                main_mod, "main",
                side_effect=config_mod.ConfigVersionError("版本 3 太高")):
            self.assertEqual(main_mod._run(), 2)

    def test_config_error_returns_2(self):
        import main as main_mod
        with mock.patch.object(
                main_mod, "main",
                side_effect=config_mod.ConfigError("文件被占用")):
            self.assertEqual(main_mod._run(), 2)

    def test_generic_error_returns_1(self):
        import main as main_mod
        with mock.patch.object(main_mod, "main", side_effect=RuntimeError("x")):
            self.assertEqual(main_mod._run(), 1)

    def test_plaintext_key_error_is_also_config_error(self):
        import main as main_mod
        self.assertTrue(issubclass(config_mod.PlaintextKeyError,
                                   config_mod.ConfigError))
        with mock.patch.object(
                main_mod, "main",
                side_effect=config_mod.PlaintextKeyError("拒绝写盘")):
            self.assertEqual(main_mod._run(), 2)


class TestV1MigrationBacksUpFirst(ConfigPathMixin):
    def test_migration_creates_encrypted_backup(self):
        v1 = {"deepseek_keys": ["sk-old"], "refresh_interval_sec": 45}
        self._write(json.dumps(v1))
        cfg = config_mod.load_v2()
        backup = config_mod.CONFIG_PATH.with_suffix(".v1.bak")
        self.assertTrue(backup.exists(), "迁移前必须先落一份 v1 备份")
        raw = backup.read_text(encoding="utf-8")
        # 备份里绝不能出现明文密钥
        self.assertNotIn("sk-old", raw)
        data = json.loads(raw)
        self.assertIn(config_mod.V1_BACKUP_MARK, data)
        # 且备份内容确实可还原
        self.assertEqual(config_mod.restore_v1_backup(), v1)

    def test_backup_is_restorable_after_migration(self):
        v1 = {"deepseek_keys": ["sk-a", "sk-b"], "refresh_interval_sec": 45}
        self._write(json.dumps(v1))
        config_mod.load_v2()
        self.assertEqual(config_mod.restore_v1_backup()["deepseek_keys"],
                         ["sk-a", "sk-b"])

    def test_no_backup_when_dpapi_unavailable(self):
        """DPAPI 不可用时宁可中止迁移,也不能写出明文备份。"""
        v1 = {"deepseek_keys": ["sk-old"]}
        self._write(json.dumps(v1))
        with mock.patch("secure.is_available", return_value=False):
            with self.assertRaises(config_mod.ConfigError):
                config_mod.load_v2()
        backup = config_mod.CONFIG_PATH.with_suffix(".v1.bak")
        self.assertFalse(backup.exists(), "中止时不应留下备份")
        # 原配置原封不动
        self.assertEqual(json.loads(
            config_mod.CONFIG_PATH.read_text(encoding="utf-8")), v1)



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


class TestGenericCachesModels(unittest.TestCase):
    """generic.fetch 必须把模型列表写进 cache。

    这里必须用 assert_called:generic.py 里那段是 try/except 包着的,
    只断言返回值的话,写缓存的代码整段坏掉测试照样绿(历史上就因为
    一个 NameError 被吞掉,导致模型缓存从来没被写过)。
    """

    def _billing(self):
        m = mock.Mock()
        m.status_code = 200
        m.json.return_value = {"total_granted": 100.0, "total_used": 30.0,
                               "total_available": 70.0}
        return m

    def _models(self):
        m = mock.Mock()
        m.status_code = 200
        m.json.return_value = {"data": [{"id": "gpt-4o"}, {"id": "claude"}]}
        return m

    def test_set_models_is_called_with_real_base_and_key(self):
        import cache as cache_mod
        with mock.patch.object(generic_mod.requests, "get",
                               side_effect=[self._billing(), self._models()]), \
             mock.patch.object(cache_mod, "set_models") as sm:
            res = generic_mod.fetch({"base_url": "https://h", "key": "sk-x"})
        self.assertEqual(res["models"], ["gpt-4o", "claude"])
        sm.assert_called_once_with("https://h", "sk-x", ["gpt-4o", "claude"])

    def test_models_land_in_real_cache_file(self):
        """不打桩 cache,验证真的落到 models.json 里。"""
        import cache as cache_mod
        with mock.patch.object(generic_mod.requests, "get",
                               side_effect=[self._billing(), self._models()]):
            generic_mod.fetch({"base_url": "https://h", "key": "sk-x"})
        got = cache_mod.get_models("https://h", "sk-x")
        self.assertEqual(sorted(got), ["claude", "gpt-4o"])


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


class TestPanelColorDictConsistency(unittest.TestCase):
    """C 字典与 _refresh_C 必须覆盖 panel.py 里所有 C["..."] 读取。

    历史上有 C["card_pressed"] 这么一条:读取点存在、palette 也有
    CARD_PRESSED,但中间那层投影漏了,拖拽一按就 KeyError。这里把
    "读取点 ⊆ 字典" 和 "字典 == 字面量 == _refresh_C" 两条都钉死。
    """

    def test_every_read_key_exists_in_c(self):
        from ui import panel as panel_mod
        src = (Path(panel_mod.__file__).read_text(encoding="utf-8"))
        used = set(re.findall(r'\bC\["(\w+)"\]', src))
        missing = sorted(used - set(panel_mod.C))
        self.assertEqual(missing, [],
                         f"panel.py 读取了 C 里不存在的键:{missing}")

    def test_c_dict_has_no_hardcoded_hex(self):
        """C 的每个值都必须来自 PALETTE,不许写死 hex(AGENTS.md 规则 3)。

        只做"键存在"检查不够:把某一项改成硬编码色值仍然能通过,
        但那一项从此不随主题变化,浅色主题下会残留深色框。
        """
        from ui import panel as panel_mod
        src = (Path(panel_mod.__file__).read_text(encoding="utf-8"))
        m = re.search(r"^C = \{(.*?)^\}", src, re.S | re.M)
        self.assertIsNotNone(m, "找不到 C 字典字面量")
        body = m.group(1)
        # 注意值的引号:"key": "#RRGGBB",冒号与 # 之间还隔一个 "
        bad = re.findall(r'"(\w+)":\s*"(#[0-9A-Fa-f]{6})"', body)
        self.assertEqual(bad, [], f"C 里有硬编码颜色:{bad}")

        keys = set(re.findall(r'"(\w+)":', body))
        from_src = set(re.findall(r'C\["(\w+)"\]\s*=\s*to_tk', src))
        self.assertEqual(sorted(keys - from_src), [],
                         "C 里的键必须在 _refresh_C 里也有 to_tk_color 赋值")

    def test_refresh_c_writes_every_key(self):
        from ui import panel as panel_mod
        src = (Path(panel_mod.__file__).read_text(encoding="utf-8"))
        m = re.search(r"def _refresh_C\(\):.*?(?=\ndef |\nclass )", src, re.S)
        self.assertIsNotNone(m, "找不到 _refresh_C")
        assigned = set(re.findall(r'C\["(\w+)"\]\s*=', m.group(0)))
        self.assertEqual(
            sorted(set(panel_mod.C) - assigned), [],
            "C 的每个键都必须在 _refresh_C 里被重新赋值,否则切主题后残留旧色")


    def test_palette_has_every_field_c_uses(self):
        from ui import panel as panel_mod
        from ui.theme import DarkPalette
        src = (Path(panel_mod.__file__).read_text(encoding="utf-8"))
        # 取右值真正引用的 palette 字段:C["dim"] = to_tk_color_blended(
        # PALETTE.TEXT_DIM) 用的是 TEXT_DIM 而不是 DIM,所以不能拿左键名去比
        used = set(re.findall(
            r'C\["\w+"\]\s*=\s*to_tk_color(?:_blended)?\(\s*PALETTE\.(\w+)',
            src))
        # PALETTE 是 _PaletteProxy 代理,dir() 看不到动态属性;
        # DarkPalette 是普通类(非 dataclass),字段都在 __dict__ 里
        have = {n for n in vars(DarkPalette) if n.isupper()}
        absent = sorted(used - have)
        self.assertEqual(absent, [], f"PALETTE 缺少 C 需要的字段:{absent}")
        self.assertGreaterEqual(len(used), 10,
                                "正则没匹配够,测试本身可能失效")


class TestActionWiringCompleteness(unittest.TestCase):
    """ui/panel.py 里所有 actions.get("X", lambda: ...) 的 X 必须真的被接线。

    AGENTS.md 规则 4 要求维护 action 清单来防 .get(..., lambda: None)
    静默吞掉未接线入口,但历史清单自己漏了 toggle_mode,导致右键菜单里
    「切换为单行模式」在生产环境是个恒 no-op。这里改成从源码里把兜底
    键抓出来,和 build_actions() 的真实返回值对撞。
    """

    # 已知未接线项(本轮只改文档不改代码,见 README 已知问题)。
    KNOWN_MISSING = {"toggle_mode"}

    def test_fallback_keys_are_wired(self):
        import threading
        import tkinter as tk
        import main as main_mod
        from ui import panel as panel_mod
        src = (Path(panel_mod.__file__).read_text(encoding="utf-8"))
        used = set(re.findall(r'actions\.get\("(\w+)",\s*lambda', src))
        self.assertTrue(used, "正则没匹配到任何兜底 action,测试本身失效")

        root = tk.Tk()
        self.addCleanup(root.destroy)
        # 不给 skip 兜底:Tk 建不起来时整个套件本来就跑不了,
        # 在这里 skip 只会把"守卫没生效"伪装成"通过"
        actions = main_mod.build_actions(root, {}, main_mod.State(),
                                         threading.Event(),
                                         threading.Event())
        wired = set(actions)
        self.assertTrue(wired, "build_actions 返回空字典,测试本身失效")

        missing = sorted(used - wired - self.KNOWN_MISSING)
        self.assertEqual(
            missing, [],
            f"panel.py 里这些 action 永远拿到兜底 no-op:{missing}")


class TestNoUnresolvedNames(unittest.TestCase):
    """静态检查:函数里读的每个全局名都必须真的存在。

    P0-3 就是这么溜过去的:generic.fetch 写缓存时用了 base_url(实际
    变量叫 base),NameError 被同行的 `except Exception` 吞掉,代码
    永远不执行却全绿。测试再完善也挡不住这种,只能靠名字解析。
    """

    RUNTIME_SOURCES = [
        "main.py", "config.py", "cache.py", "notify.py", "secure.py",
        "providers/__init__.py", "providers/generic.py",
        "providers/relay.py", "providers/minimax.py",
        "providers/opencode_go.py", "providers/detect.py",
        "providers/zhipu.py", "providers/deepseek.py",
        "ui/panel.py", "ui/theme.py", "ui/app.py",
    ]

    def _resolve(self, path):
        import builtins
        import symtable
        src = path.read_text(encoding="utf-8")
        st = symtable.symtable(src, str(path), "exec")
        module_names = set()
        for s in st.get_symbols():
            if s.is_assigned() or s.is_imported() or s.is_namespace():
                module_names.add(s.get_name())
        problems = []

        def walk(table):
            for sym in table.get_symbols():
                name = sym.get_name()
                if not sym.is_global() or sym.is_assigned():
                    continue
                if (name in module_names or hasattr(builtins, name)
                        or name in ("__file__", "__name__", "__doc__",
                                    "__package__", "__builtins__")):
                    continue
                problems.append(f"{path.name}:{table.get_name()}() 里的 {name}")
            for child in table.get_children():
                walk(child)

        walk(st)
        return problems

    def test_no_unresolved_global_names(self):
        root = Path(__file__).resolve().parent.parent
        problems = []
        for rel in self.RUNTIME_SOURCES:
            p = root / rel
            if not p.exists():
                problems.append(f"源文件不存在:{rel}")
                continue
            problems.extend(self._resolve(p))
        self.assertEqual(problems, [],
                         "这些全局名在本模块里查不到定义(多半是拼写错误):"
                         + "; ".join(problems))


class TestLevelAlerting(unittest.TestCase):
    """等级判定:任何能算出 pct 的 provider 都应该能告警。"""

    CFG = {"alert": {"warn_pct": 30, "critical_amount_yuan": 5.0}}

    def _lv(self, **res):
        return providers._level(res, {}, self.CFG)

    def test_dollar_provider_with_pct_can_warn(self):
        # OpenCode Go:unit="$",pct=12(只剩 12%)。此前恒返回 ok。
        self.assertEqual(self._lv(unit="$", pct=12.0, remaining=3.0), "warn")

    def test_dollar_provider_healthy_stays_ok(self):
        self.assertEqual(self._lv(unit="$", pct=80.0, remaining=60.0), "ok")

    def test_opencode_go_style_result_warns(self):
        res = {"unit": "$", "pct": 5.0, "remaining": 1.0, "used": None,
               "total": None, "detail": "5h ≈$0.60/$12"}
        self.assertEqual(providers._level(res, {}, self.CFG), "warn")

    def test_yuan_uses_absolute_threshold(self):
        self.assertEqual(self._lv(unit="¥", remaining=3.0), "critical")
        self.assertEqual(self._lv(unit="¥", remaining=50.0), "ok")

    def test_no_pct_stays_ok(self):
        # 只报绝对金额的美元 provider:没有百分比就无从判断
        self.assertEqual(self._lv(unit="$", remaining=3.0, pct=None), "ok")

    def test_error_wins_over_thresholds(self):
        self.assertEqual(self._lv(unit="$", pct=1.0, error="HTTP 500"),
                         LEVEL_ERR)
        self.assertEqual(self._lv(unit="$", pct=1.0, error="缺 key",
                                  unconfigured=True), "unconfigured")


LEVEL_ERR = providers.LEVEL_ERROR


class TestOpencodeGoUrlFallback(unittest.TestCase):
    """预设里的 base_url 不带 /zen/go,拼出来的 URL 会 404,必须回退。"""

    def _resp(self, status, payload=None):
        m = mock.Mock()
        m.status_code = status
        m.json.return_value = payload or {}
        return m

    def test_404_falls_back_to_module_constant(self):
        from providers import opencode_go as oc
        calls = []

        def fake_get(url, headers=None, timeout=None):
            calls.append(url)
            if url == "https://opencode.ai/v1/usage":
                return self._resp(404)
            return self._resp(200, {"usage": {"rolling": {"percent": 40}}})

        with mock.patch.object(oc.requests, "get", side_effect=fake_get):
            res = oc.fetch({"base_url": "https://opencode.ai", "api_key": "ey-x"})
        self.assertEqual(calls[0], "https://opencode.ai/v1/usage")
        self.assertIn("zen/go", calls[-1])
        self.assertNotIn("error", res)

    def test_first_url_success_needs_no_fallback(self):
        from providers import opencode_go as oc
        calls = []

        def fake_get(url, headers=None, timeout=None):
            calls.append(url)
            return self._resp(200, {"usage": {"rolling": {"percent": 40}}})

        with mock.patch.object(oc.requests, "get", side_effect=fake_get):
            oc.fetch({"base_url": "https://opencode.ai", "api_key": "ey-x"})
        self.assertEqual(len(calls), 1)

    def test_auth_error_does_not_retry_other_url(self):
        from providers import opencode_go as oc
        calls = []

        def fake_get(url, headers=None, timeout=None):
            calls.append(url)
            return self._resp(401)

        with mock.patch.object(oc.requests, "get", side_effect=fake_get):
            res = oc.fetch({"base_url": "https://opencode.ai", "api_key": "ey-x"})
        self.assertEqual(len(calls), 1, "401 不该去试别的端点")
        self.assertIn("key 无效", res["error"])


class TestAlertCooldownNotInherited(unittest.TestCase):
    """删除/改名后,新条目不该继承旧条目的 60 分钟告警冷却。"""

    def _poller(self):
        import main as main_mod
        p = main_mod.Poller({}, main_mod.State(),
                            threading.Event(), threading.Event())
        p.notified = {"DeepSeek": ("critical", time.time() - 5),
                      "别的": ("warn", time.time() - 5)}
        return p

    def test_forget_drops_only_named(self):
        p = self._poller()
        p.forget_alert_state("DeepSeek")
        self.assertNotIn("DeepSeek", p.notified)
        self.assertIn("别的", p.notified, "不该误伤别的 provider")

    def test_deleted_provider_alerts_immediately_after_recreate(self):
        """真实场景:key 填错了 → 删掉 → 同名重加 → 立刻 critical。"""
        import threading as th
        import main as main_mod
        poller = self._poller()
        cfg = {"schema_version": 2, "refresh_interval_sec": 30,
               "alert": {"enable": True, "warn_pct": 30,
                         "critical_amount_yuan": 5.0},
               "ui": {}, "providers": [
                   {"id": "p1", "kind": "deepseek", "name": "DeepSeek",
                    "key": "sk-x", "base_url": "https://h", "extra": {}}]}
        root = tk_root()
        try:
            actions = main_mod.build_actions(root, cfg, main_mod.State(),
                                             th.Event(), th.Event(),
                                             poller=poller)
            actions["delete_provider_by_id"]("p1")
            self.assertNotIn("DeepSeek", poller.notified,
                             "删除后必须清掉冷却,否则同名重建会继承它")

            # 同名重建,轮询一轮报 critical
            cfg["providers"].append(
                {"id": "p2", "kind": "deepseek", "name": "DeepSeek",
                 "key": "sk-y", "base_url": "https://h", "extra": {}})
            poller.cfg = cfg
            poller.state.results = []
            with mock.patch.object(main_mod, "notify") as notify_mod:
                poller._fire_alerts([{"name": "DeepSeek", "level": "critical"}])
            called = getattr(notify_mod, "alert_many", None)
            self.assertIsNotNone(called, "notify 被 mock 了才算验证到弹窗路径")
            called.assert_called()
        finally:
            root.destroy()

    def test_rename_forgets_old_name(self):
        import threading as th
        import main as main_mod
        poller = self._poller()
        cfg = {"schema_version": 2, "refresh_interval_sec": 30,
               "alert": {"enable": True, "warn_pct": 30,
                         "critical_amount_yuan": 5.0},
               "ui": {}, "providers": [
                   {"id": "p1", "kind": "deepseek", "name": "DeepSeek",
                    "key": "sk-x", "base_url": "https://h", "extra": {}}]}
        root = tk_root()
        try:
            actions = main_mod.build_actions(root, cfg, main_mod.State(),
                                             th.Event(), th.Event(),
                                             poller=poller)
            actions["update_provider"]("p1", {"name": "改名后", "key": "sk-y",
                                              "base_url": "https://h"})
            self.assertNotIn("DeepSeek", poller.notified)
        finally:
            root.destroy()


def tk_root():
    """建一个隐形 Tk root,顺手清掉上一个遗留的 grab。

    ModelPanel/SettingsDialog 构造时会 grab_set()。同一进程里连续建多个
    Tk root 时,上一个的 grab 可能还挂着,新窗口 grab_set() 抛
    "grab failed: another application has grab",会把整个测试进程带崩。
    """
    import tkinter as tk
    r = tk.Tk()
    r.withdraw()
    r.attributes("-alpha", 0.0)
    try:
        for child in r.winfo_children():
            if child.grab_current():
                child.grab_release()
    except tk.TclError:
        pass
    return r


class TestBarMatchesColor(unittest.TestCase):
    """进度条长度与颜色必须同源,都表示"已消耗占比"。

    旧实现:长度 = pct/100(剩余),颜色 = _usage_ratio(已消耗)。
    剩 30% 的账号画成"30% 宽的橙条",而折叠条带又画 70% 宽,
    同一份数据在两处互相矛盾。
    """

    def test_length_equals_color_ratio(self):
        from ui import panel as panel_mod
        r = {"name": "Z", "unit": "%", "pct": 30.0, "level": "warn",
             "remaining": None, "used": None, "total": None}
        ratio = panel_mod._usage_ratio(r)
        self.assertAlmostEqual(ratio, 0.7, places=6,
                               msg="剩余 30% = 已消耗 70%")
        # _usage_color 与 bar 长度用的是同一个 ratio,所以同一条一定自洽
        color = panel_mod._usage_color(ratio)
        self.assertNotEqual(color, panel_mod.C["ok"],
                            "消耗 70% 不该是绿色")

    def test_paint_row_uses_ratio_for_frac(self):
        import tkinter as tk
        from ui import panel as panel_mod
        root = tk.Tk()
        self.addCleanup(root.destroy)
        root.withdraw()
        top = tk.Toplevel(root)

        class _S:
            results = []
            paused = False
            paused_providers = set()
            fetching = False
            poll_error = None
            save_error = None
            next_fetch = 0.0

        state = _S()
        state.results = [{"name": "Z", "type": "zhipu", "unit": "%",
                          "level": "ok", "remaining": None, "used": None,
                          "total": None, "pct": 80, "detail": "d",
                          "error": None, "updated_at": 1.0}]
        actions = {"refresh_now": lambda: None, "toggle_pause": lambda: None,
                   "test_notify": lambda: None, "quit": lambda: None,
                   "save_position": lambda *a: None,
                   "save_size": lambda *a: None,
                   "save_order": lambda *a: None,
                   "save_pin": lambda *a: None, "get_order": lambda: [],
                   "open_config": lambda: None,
                   "open_settings": lambda: None,
                   "add_key": lambda: None,
                   "delete_provider": lambda n: None,
                   "edit_provider": lambda n: None,
                   "pause_provider": lambda n: None,
                   "probe_models": lambda n: None,
                   "probe_model": lambda *a, **k: (False, 0.0, ""),
                   "save_model_order": lambda *a: None}
        p = panel_mod.Panel(top, state, {"ui": {}, "providers": [],
                                         "alert": {}}, actions)
        try:
            p.stop()
        except Exception:
            pass
        p._update()
        widgets = p._rows["Z"]
        p._paint_row(widgets, state.results[0])
        # pct=80 剩余 → 已消耗 0.2
        self.assertAlmostEqual(widgets["_bar_frac"], 0.2, places=6)
        self.assertEqual(widgets["_bar_frac"],
                         panel_mod._usage_ratio(state.results[0]))

    def test_unknown_ratio_draws_empty_bar_not_full(self):
        """出错/未配置的行不该画出误导性的满格条。"""
        import tkinter as tk
        from ui import panel as panel_mod
        root = tk.Tk()
        self.addCleanup(root.destroy)
        root.withdraw()
        top = tk.Toplevel(root)

        class _S:
            results = []
            paused = False
            paused_providers = set()
            fetching = False
            poll_error = None
            save_error = None
            next_fetch = 0.0

        state = _S()
        state.results = [{"name": "E", "type": "deepseek", "unit": "¥",
                          "level": "error", "remaining": None, "used": None,
                          "total": None, "pct": None, "detail": "boom",
                          "error": "HTTP 500", "updated_at": 1.0}]
        actions = {"refresh_now": lambda: None, "toggle_pause": lambda: None,
                   "test_notify": lambda: None, "quit": lambda: None,
                   "save_position": lambda *a: None,
                   "save_size": lambda *a: None,
                   "save_order": lambda *a: None,
                   "save_pin": lambda *a: None, "get_order": lambda: [],
                   "open_config": lambda: None,
                   "open_settings": lambda: None,
                   "add_key": lambda: None,
                   "delete_provider": lambda n: None,
                   "edit_provider": lambda n: None,
                   "pause_provider": lambda n: None,
                   "probe_models": lambda n: None,
                   "probe_model": lambda *a, **k: (False, 0.0, ""),
                   "save_model_order": lambda *a: None}
        p = panel_mod.Panel(top, state, {"ui": {}, "providers": [],
                                         "alert": {}}, actions)
        try:
            p.stop()
        except Exception:
            pass
        p._update()
        widgets = p._rows["E"]
        # 出错/未配置的行根本不给画进度条,更不会画出误导性的满格灰条
        self.assertIsNone(widgets["bar"])
        p._paint_row(widgets, state.results[0])   # 不应抛异常


class TestModelDragWithFilter(unittest.TestCase):
    """搜索过滤状态下拖拽,落盘的全量顺序不能被写坏。

    旧实现把"可见列表里的下标"直接拿去插全量列表,并 on_reorder 落盘,
    结果是错序持久化,用户只能自己重拖才能纠正。
    """

    @classmethod
    def setUpClass(cls):
        cls.root = tk_root()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.root.destroy()
        except tk.TclError:
            pass

    def _make(self, models):
        from ui import model_panel as mp_mod
        self.saved = []
        p = mp_mod.ModelPanel(self.root, "P", list(models),
                              on_reorder=lambda o: self.saved.append(list(o)))
        # ModelPanel 构造时 grab_set();不释放的话同一进程里下一个窗口
        # grab_set() 会抛 "grab failed",把测试进程带崩
        self.addCleanup(self._cleanup, p)
        return p

    def _cleanup(self, p):
        try:
            if p.grab_current():
                p.grab_release()
        except tk.TclError:
            pass
        try:
            p.destroy()
        except tk.TclError:
            pass

    def test_reorder_without_filter(self):
        p = self._make(["m1", "m2", "m3"])
        p._commit_model_drag("m1", 2)
        self.assertEqual(list(p.models), ["m2", "m3", "m1"])
        self.assertEqual(self.saved[-1], ["m2", "m3", "m1"])

    def test_reorder_while_filtered_keeps_hidden_items(self):
        p = self._make(["keep1", "drop1", "keep2", "drop2"])
        p.filtered = ["keep1", "keep2"]        # 模拟搜索过滤后只剩 keep*
        p._commit_model_drag("keep1", 1)
        self.assertEqual(sorted(p.models),
                         ["drop1", "drop2", "keep1", "keep2"],
                         "条目不能凭空丢失")
        vis = [m for m in p.models if m.startswith("keep")]
        self.assertEqual(vis, ["keep2", "keep1"], "可见顺序确实变了")
        self.assertEqual(len(self.saved[-1]), 4)

    def test_filtered_reorder_does_not_corrupt_persisted_order(self):
        """旧实现会把 keep1 插到全量下标 1,落盘成错序。"""
        p = self._make(["keep1", "drop1", "keep2", "drop2"])
        p.filtered = ["keep1", "keep2"]
        p._commit_model_drag("keep1", 1)
        out = self.saved[-1]
        self.assertEqual(sorted(out),
                         ["drop1", "drop2", "keep1", "keep2"],
                         "落盘列表必须仍是原来那 4 个")
        self.assertLess(out.index("keep2"), out.index("keep1"),
                        "可见顺序必须被尊重")
        # 隐藏项保持原相对位置:drop1 仍在最前
        self.assertEqual(out[0], "drop1")


class TestFocusInDebounce(unittest.TestCase):
    """点设置对话框里的输入框不该触发整轮轮询。"""

    @classmethod
    def setUpClass(cls):
        # 一个类共用一个 Tk root:进程里反复建/销毁多个完整解释器
        # (tk_root() 每次一个)在 Windows 的 Tk 上不稳定,会在后面的
        # 测试里随机崩掉整个 pytest 进程(fatal exception 0x80000003)。
        cls.root = tk_root()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.root.destroy()
        except tk.TclError:
            pass

    def _panel(self):
        from ui import panel as panel_mod

        class _S:
            results = []
            paused = False
            paused_providers = set()
            fetching = False
            poll_error = None
            save_error = None
            next_fetch = 0.0

        self.state = _S()
        self.hits = []
        actions = {"refresh_now": lambda: self.hits.append(1),
                   "toggle_pause": lambda: None, "test_notify": lambda: None,
                   "quit": lambda: None, "save_position": lambda *a: None,
                   "save_size": lambda *a: None, "save_order": lambda *a: None,
                   "save_pin": lambda *a: None, "get_order": lambda: [],
                   "open_config": lambda: None, "open_settings": lambda: None,
                   "add_key": lambda: None, "delete_provider": lambda n: None,
                   "edit_provider": lambda n: None,
                   "pause_provider": lambda n: None,
                   "probe_models": lambda n: None,
                   "probe_model": lambda *a, **k: (False, 0.0, ""),
                   "save_model_order": lambda *a: None}
        cfg = {"ui": {}, "providers": [], "alert": {}}
        top = tk.Toplevel(self.root)
        self.addCleanup(self._teardown, top)
        p = panel_mod.Panel(top, self.state, cfg, actions,
                            root_window=self.root)
        return p, top

    def _teardown(self, top):
        try:
            top.destroy()
        except tk.TclError:
            pass

    def test_child_focus_does_not_trigger(self):
        p, top = self._panel()
        entry = tk.Entry(top)
        entry.pack()
        p._on_focus_in(type("E", (), {"widget": entry})())
        self.assertEqual(self.hits, [],
                         "子控件获得焦点不该触发全量轮询")

    def test_toplevel_focus_triggers_once(self):
        p, top = self._panel()
        # 生产里 root_window 就是应用主窗口,FocusIn 的 widget 是它本身
        p._on_focus_in(type("E", (), {"widget": self.root})())
        self.assertEqual(len(self.hits), 1)
        # 紧接着再来一次应被去抖挡掉
        p._on_focus_in(type("E", (), {"widget": top})())
        self.assertEqual(len(self.hits), 1, "最小间隔内不该重复触发")

    def test_fetching_blocks(self):
        p, top = self._panel()
        self.state.fetching = True
        p._on_focus_in(type("E", (), {"widget": self.root})())
        self.assertEqual(self.hits, [])

    def test_stop_cancels_tick(self):
        """窗口销毁前必须停掉 1Hz 定时器,否则残留回调打到已销毁的
        解释器上,会让整个进程崩在 Tk 内部。"""
        p, top = self._panel()
        p._update()
        self.assertIsNotNone(p._tick_after_id, "tick 应该在跑")
        p.stop()
        self.assertIsNone(p._tick_after_id)
        p.stop()          # 幂等:重复调用不应抛异常


class TestCacheConcurrentWrites(unittest.TestCase):
    """models.json 的读-改-写必须串行,且临时名唯一。

    旧实现用固定的 <name>.tmp:两个写者(轮询 worker 的 set_models 与
    主线程的 save_model_order)先后 write_text("w") 会互相截断,
    os.replace 装上混合字节的 JSON,再被 _load_json 当损坏返回 {},
    于是**所有** provider 的模型缓存一起消失。
    """

    def _concurrent_set(self, n=12):
        import cache as cache_mod
        errs = []

        def w(i):
            try:
                cache_mod.set_models(f"https://h{i}", f"sk-{i}", [f"m{i}"])
            except Exception as e:      # noqa: BLE001
                errs.append(e)

        ts = [threading.Thread(target=w, args=(i,)) for i in range(n)]
        for t in ts:
            t.start()
        for t in ts:
            t.join(20)
        self.assertEqual(errs, [], f"并发写抛异常:{errs}")

    def test_all_concurrent_writers_survive(self):
        import cache as cache_mod
        self._concurrent_set()
        for i in range(12):
            got = cache_mod.get_models(f"https://h{i}", f"sk-{i}")
            self.assertEqual(got, [f"m{i}"],
                             f"第 {i} 条被写丢了(models.json 被打坏)")

    def test_file_stays_valid_json(self):
        import cache as cache_mod
        self._concurrent_set()
        raw = cache_mod.MODELS_CACHE.read_text(encoding="utf-8")
        data = json.loads(raw)      # 解析失败说明写坏了
        self.assertEqual(len(data), 12)

    def test_no_tmp_files_left_behind(self):
        import cache as cache_mod
        self._concurrent_set()
        leftovers = list(cache_mod.CACHE_DIR.glob("*.tmp"))
        self.assertEqual(leftovers, [], f"残留临时文件:{leftovers}")

    def test_set_models_preserves_user_order(self):
        """重新拉模型不能把用户排好的顺序冲掉(与并发写同时发生)。"""
        import cache as cache_mod
        cache_mod.set_models("https://h", "sk-1", ["a", "b", "c"])
        cache_mod.save_model_order("https://h", "sk-1", ["c", "a", "b"])
        cache_mod.set_models("https://h", "sk-1", ["a", "b", "c", "d"])
        self.assertEqual(cache_mod.get_models("https://h", "sk-1"),
                         ["c", "a", "b", "d"])

    def test_malformed_cache_is_ignored_not_raised(self):
        import cache as cache_mod
        cache_mod.set_models("https://h", "sk-1", ["a"])
        raw = json.loads(cache_mod.MODELS_CACHE.read_text(encoding="utf-8"))
        key = cache_mod._hash("https://h", "sk-1")
        raw[key] = {"models": "not-a-list", "fetched_at": "2026-01-01"}
        cache_mod._save_json(cache_mod.MODELS_CACHE, raw)
        self.assertIsNone(cache_mod.get_models("https://h", "sk-1"))


class TestProbeLogTrimmed(unittest.TestCase):
    def test_log_is_capped(self):
        import cache as cache_mod
        for i in range(cache_mod.PROBE_LOG_MAX_LINES + 50):
            cache_mod.log_probe("P", f"m{i}", True, 1.0)
        lines = cache_mod.PROBE_LOG.read_text(encoding="utf-8").splitlines()
        self.assertLessEqual(len(lines), cache_mod.PROBE_LOG_MAX_LINES)
        # 保留的是最近的
        last = json.loads(lines[-1])
        self.assertEqual(last["model"],
                         f"m{cache_mod.PROBE_LOG_MAX_LINES + 49}")


class TestAlertStateClockSkew(unittest.TestCase):
    def test_future_timestamp_is_dropped(self):
        """未来时间戳会让冷却判定恒真,该 provider 被永久静默。"""
        import cache as cache_mod
        cache_mod.save_alert_state({"A": ["critical", time.time() + 86400]})
        self.assertEqual(cache_mod.load_alert_state(), {})
        cache_mod.save_alert_state({"A": ["critical", time.time() - 10]})
        self.assertIn("A", cache_mod.load_alert_state())


class TestShutdownDoesNotLinger(unittest.TestCase):
    """关窗后进程不该在后台 invisible 挂两分多钟。

    根因:3.9+ 的 ThreadPoolExecutor worker 是非守护线程,解释器退出时
    concurrent.futures 的 atexit 钩子会 join 它们;而每家请求 12s 超时,
    中转站 6 个端点串行、401 还要重登重跑一轮。改成 daemon 线程后
    解释器不 join,进程立即消失。
    """

    def _cfg(self, n=3):
        return {"schema_version": 2, "providers": [
            {"id": f"p{i}", "kind": "deepseek", "name": f"P{i}",
             "key": "sk-x", "base_url": "https://h", "extra": {}}
            for i in range(n)
        ]}

    def test_worker_threads_are_daemon(self):
        import threading
        seen = []

        def spy(kind, entry, cfg):
            seen.append(threading.current_thread().daemon)
            return dict(providers._blank_result(kind, entry),
                        name=entry["name"])

        with mock.patch.object(providers, "_one", side_effect=spy):
            providers.fetch_all(self._cfg())
        self.assertEqual(seen, [True] * 3,
                         "拉取线程必须 daemon,否则退出时会被 join 拖住")

    def test_stop_prevents_new_requests(self):
        stop = threading.Event()
        stop.set()
        calls = []

        def spy(kind, entry, cfg):
            calls.append(entry["name"])
            return dict(providers._blank_result(kind, entry),
                        name=entry["name"])

        with mock.patch.object(providers, "_one", side_effect=spy):
            res = providers.fetch_all(self._cfg(), stop=stop)
        self.assertEqual(calls, [], "stop 已置位时不该再发任何请求")
        self.assertEqual(len(res), 3, "仍须返回与 cfg 等长的行集")

    def test_cancelled_rows_are_marked(self):
        stop = threading.Event()
        stop.set()
        with mock.patch.object(providers, "_one",
                               side_effect=AssertionError("不该被调用")):
            res = providers.fetch_all(self._cfg(), stop=stop)
        self.assertTrue(all(r["level"] == providers.LEVEL_PAUSED
                            for r in res))

    def test_skip_names_accepts_live_set(self):
        """skip_names 传 set 时必须先拷快照,不能边迭代边被主线程改。"""
        live = {"P1"}

        def mutating_spy(kind, entry, cfg):
            live.add(entry["name"])      # 模拟主线程同时点了另一个行
            return dict(providers._blank_result(kind, entry),
                        name=entry["name"])

        with mock.patch.object(providers, "_one", side_effect=mutating_spy):
            res = providers.fetch_all(self._cfg(), skip_names=live)
        self.assertEqual(len(res), 3)
        by_name = {r["name"]: r for r in res}
        self.assertTrue(by_name["P1"]["paused"])
        self.assertFalse(by_name["P0"]["paused"])


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








