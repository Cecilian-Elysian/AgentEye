"""按 provider 暂停 / 恢复轮询的测试。

- providers.fetch_all(skip_names=...) 对被跳过的条目不发请求,返回 paused 行
- paused 行 level=paused、不产生告警、fmt_main 显示"已暂停"
- main.build_actions 导出 pause_provider / probe_models(此前两者缺失,
  行右键菜单是静默空操作)
- main.build_actions 导出完整 action 集合,避免再出现 .get(...) 兜底为空
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import providers


def _cfg(*names):
    return {
        "schema_version": 2,
        "providers": [
            {"id": f"id-{n}", "kind": "deepseek", "name": n,
             "key": "sk-" + n, "base_url": "https://api.deepseek.com",
             "extra": {}}
            for n in names
        ],
    }


class TestFetchAllSkip(unittest.TestCase):
    def setUp(self):
        self._orig_one = providers._one
        self.calls = []

        def _spy(kind, entry, cfg):
            # 只记账,不调真实适配器:调了就会向 api.deepseek.com 发真实
            # HTTPS 请求(带一个假 Bearer),断网时每个用例拖 12s。
            # 这几个用例断言的是"哪些条目被调过"和 paused 标记,不需要
            # 真的网络往返;字段清单用生产代码的 _blank_result 保证一致。
            self.calls.append(entry.get("name"))
            res = providers._blank_result(kind, entry)
            res.update({"level": "ok", "remaining": 1.0})
            return res

        providers._one = _spy

    def tearDown(self):
        providers._one = self._orig_one

    def test_no_skip_calls_everything(self):
        res = providers.fetch_all(_cfg("A", "B"))
        self.assertEqual(sorted(self.calls), ["A", "B"])
        self.assertEqual(len(res), 2)

    def test_skipped_entry_is_not_fetched(self):
        res = providers.fetch_all(_cfg("A", "B"), skip_names={"A"})
        self.assertNotIn("A", self.calls)
        self.assertIn("B", self.calls)

    def test_skipped_entry_returns_paused_row(self):
        res = {r["name"]: r for r in
               providers.fetch_all(_cfg("A", "B"), skip_names={"A"})}
        self.assertEqual(res["A"]["level"], providers.LEVEL_PAUSED)
        self.assertTrue(res["A"]["paused"])
        self.assertIsNone(res["A"]["error"])
        self.assertIsNone(res["A"]["remaining"])
        self.assertFalse(res["A"]["unconfigured"])

    def test_paused_row_keeps_id_and_kind(self):
        res = {r["name"]: r for r in
               providers.fetch_all(_cfg("A"), skip_names={"A"})}
        self.assertEqual(res["A"]["id"], "id-A")
        self.assertEqual(res["A"]["kind"], "deepseek")

    def test_all_skipped_returns_all_paused(self):
        res = providers.fetch_all(_cfg("A", "B"), skip_names={"A", "B"})
        self.assertEqual(self.calls, [])
        self.assertEqual(len(res), 2)
        self.assertTrue(all(r["paused"] for r in res))

    def test_empty_cfg_returns_empty(self):
        self.assertEqual(providers.fetch_all({"providers": []}), [])
        self.assertEqual(providers.fetch_all({}), [])

    def test_paused_row_does_not_alert(self):
        import threading

        from main import Poller, State
        import notify

        state = State()
        poller = Poller({}, state, threading.Event(), threading.Event())
        fired = []
        orig = notify.alert_many
        notify.alert_many = lambda items: fired.extend(items)
        try:
            poller._fire_alerts([{"name": "A", "level": providers.LEVEL_PAUSED}])
        finally:
            notify.alert_many = orig
        self.assertEqual(fired, [])


class TestFmtPaused(unittest.TestCase):
    """暂停行在真正使用的格式化函数里要显示"已暂停",不是 "-"。

    历史上 providers.fmt_main 是个没人调用的死函数,断言都打在它身上;
    真正跑的是 ui.panel._fmt_main 与 ui.essential_bar._main_value。
    """

    def test_dead_formatters_are_gone(self):
        for name in ("fmt_main", "fmt_countdown"):
            self.assertFalse(hasattr(providers, name),
                             f"providers.{name} 是死函数,应已删除")

    def test_panel_fmt_main_paused(self):
        from ui.panel import _fmt_main
        self.assertEqual(_fmt_main({"paused": True}), "已暂停")

    def test_panel_fmt_main_paused_beats_error(self):
        from ui.panel import _fmt_main
        self.assertEqual(_fmt_main({"paused": True, "error": "boom"}),
                         "已暂停")

    def test_panel_fmt_main_normal_unaffected(self):
        from ui.panel import _fmt_main
        self.assertEqual(_fmt_main({"unit": "%", "pct": 42}), "已用 58%")
        self.assertEqual(_fmt_main({"unconfigured": True}), "未配置")
        self.assertEqual(_fmt_main({"error": "boom"}), "查询失败")

    def test_essential_bar_main_value_paused(self):
        from ui.essential_bar import _main_value
        self.assertEqual(_main_value({"paused": True}), ("已暂停", ""))

    def test_essential_bar_main_value_none_unchanged(self):
        from ui.essential_bar import _main_value
        self.assertEqual(_main_value(None), ("—", "—"))

    def test_paused_row_without_branch_would_render_dash(self):
        """反证:没有 paused 分支时结果确实是 "-",说明断言有效。"""
        from ui.panel import _fmt_main
        self.assertEqual(_fmt_main({"unit": "", "remaining": None}), "-")


class TestThemePausedLevel(unittest.TestCase):
    def test_theme_exposes_paused_constant(self):
        from ui import theme
        self.assertEqual(theme.LEVEL_PAUSED, "paused")

    def test_paused_maps_to_off_color(self):
        from ui import theme
        self.assertEqual(theme.level_color(theme.LEVEL_PAUSED),
                         theme.PALETTE.OFF)


class TestActionsSurface(unittest.TestCase):
    """build_actions 必须导出所有菜单/行菜单引用的 action。"""

    def _actions(self, state=None):
        import threading
        import main as main_mod

        state = state or main_mod.State()
        return main_mod.build_actions(None, {}, state,
                                      threading.Event(), threading.Event())

    def test_pause_provider_is_exported(self):
        self.assertIn("pause_provider", self._actions())

    def test_probe_models_is_exported(self):
        self.assertIn("probe_models", self._actions())

    def test_all_panel_and_row_menu_actions_exported(self):
        keys = self._actions()
        required = [
            "refresh_now", "toggle_pause", "test_notify", "open_config",
            "open_settings", "save_position", "save_size", "save_order",
            "save_pin", "save_ui", "save_theme", "get_order",
            "save_model_order", "quit", "add_key", "edit_provider",
            "update_provider", "delete_provider", "delete_provider_by_id",
            "probe_model", "pause_provider", "probe_models",
        ]
        missing = [k for k in required if k not in keys]
        self.assertEqual(missing, [])

    def test_toggle_pause_flips_state(self):
        import main as main_mod
        state = main_mod.State()
        actions = self._actions(state)
        self.assertFalse(state.paused)
        actions["toggle_pause"]()
        self.assertTrue(state.paused)
        actions["toggle_pause"]()
        self.assertFalse(state.paused)

    def test_pause_provider_toggles_membership(self):
        import main as main_mod
        state = main_mod.State()
        actions = self._actions(state)
        actions["pause_provider"]("DeepSeek")
        self.assertIn("DeepSeek", state.paused_providers)
        actions["pause_provider"]("DeepSeek")
        self.assertNotIn("DeepSeek", state.paused_providers)

    def test_pause_provider_ignores_empty_name(self):
        import main as main_mod
        state = main_mod.State()
        actions = self._actions(state)
        actions["pause_provider"]("")
        self.assertEqual(state.paused_providers, set())


class TestPanelRowMenuWiring(unittest.TestCase):
    """源码级断言:行菜单两个入口不再靠 .get(...) 静默兜底。"""

    def test_row_menu_callbacks_are_wired_in_panel(self):
        src = open(os.path.join(ROOT, "ui", "panel.py"),
                   encoding="utf-8").read()
        self.assertIn('actions.get("pause_provider"', src)
        self.assertIn('actions.get("probe_models"', src)

    def test_probe_cb_passes_provider_name(self):
        src = open(os.path.join(ROOT, "ui", "panel.py"),
                   encoding="utf-8").read()
        self.assertIn("provider_name=name", src)


class TestConfigDeadCodeRemoved(unittest.TestCase):
    """v1 死路径已删除,配置只有 v2 一套。"""

    def test_v1_api_is_gone(self):
        import config
        for name in ("load", "save", "_merge", "_apply_env",
                     "clamp_interval", "TEMPLATE"):
            self.assertFalse(hasattr(config, name),
                             f"config.{name} 应已删除")

    def test_env_defaults_kept(self):
        import config
        self.assertEqual(config.ENV_DEFAULTS["minimax"], "MINIMAX_API_KEY")

    def test_example_config_is_v2(self):
        import json
        path = os.path.join(ROOT, "config.example.json")
        data = json.loads(open(path, encoding="utf-8").read())
        self.assertEqual(data["schema_version"], 2)
        self.assertIn("providers", data)
        self.assertNotIn("relay_sites", data)
        for p in data["providers"]:
            self.assertIn("kind", p)
            self.assertIn("id", p)

    def test_fresh_install_seeds_no_placeholder_providers(self):
        import json
        import tempfile
        from pathlib import Path
        import config as config_mod

        orig = config_mod.CONFIG_PATH
        tmp = tempfile.TemporaryDirectory()
        try:
            config_mod.CONFIG_PATH = Path(tmp.name) / "config.json"
            cfg = config_mod.load_v2()
        finally:
            config_mod.CONFIG_PATH = orig
            tmp.cleanup()
        self.assertEqual(cfg["schema_version"], 2)
        self.assertEqual(cfg["providers"], [])


if __name__ == "__main__":
    unittest.main()
