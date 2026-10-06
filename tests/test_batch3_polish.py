"""批次 3 打磨项的行为测试。

覆盖:
- deepseek base_url 带 /v1 后缀时自动剥掉(余额端点在根路径)
- generic 订阅解析接受无 data 包装的裸体响应
- minimax base_resp 回非 dict(网关错误页)不再 AttributeError
- zhipu 网关把 code 回成字符串 "200" 不再误判接口报错
- add_key_entry 写盘失败回滚内存条目并抛错(设置对话框留表单)
- refresh_now 在 fetching 中直接短路
- essential 条带 % 行主值与 Panel 同口径(已用)
- save_model_order 只动排序,不续命 TTL
- ModelPanel 同一模型试调在途去重
"""
import json
import threading
import time
import tkinter as tk

import pytest

import cache as cache_mod
import config as config_mod
import main as main_mod
import providers.deepseek as deepseek_mod
import providers.generic as generic_mod
import providers.minimax as minimax_mod
import providers.zhipu as zhipu_mod
from ui import essential_bar as eb_mod
from ui import model_panel as mp_mod


class _FakeResp:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


def test_deepseek_strips_v1_suffix(monkeypatch):
    seen = {}

    def fake_get(url, **kw):
        seen["url"] = url
        return _FakeResp({"balance_infos": [{
            "currency": "CNY", "total_balance": "1.0",
            "granted_balance": "0", "topped_up_balance": "0"}]})

    monkeypatch.setattr(deepseek_mod.requests, "get", fake_get)
    r = deepseek_mod.fetch({"api_key": "sk-x",
                            "base_url": "https://api.deepseek.com/v1/"})
    assert seen["url"] == "https://api.deepseek.com/user/balance"
    assert "error" not in r


def test_generic_subscription_accepts_bare_body():
    out = generic_mod._parse_openai_subscription(
        {"hard_limit_usd": 100, "usage": 30}, {})
    assert out is not None
    assert out["total"] == 100
    assert out["remaining"] == 70


def test_minimax_base_resp_non_dict_does_not_crash(monkeypatch):
    monkeypatch.setattr(
        minimax_mod.requests, "get",
        lambda *a, **k: _FakeResp({"base_resp": "gateway error",
                                   "data": {"items": []}}))
    r = minimax_mod.fetch({"api_key": "k", "plan": "token_plan"})
    assert isinstance(r, dict) and r.get("error")


def test_zhipu_string_code_200_is_success(monkeypatch):
    monkeypatch.setattr(
        zhipu_mod.requests, "get",
        lambda *a, **k: _FakeResp({
            "code": "200", "success": True,
            "data": {"limits": [{"type": "TOKENS_LIMIT",
                                 "percentage": 40.0,
                                 "unit": "hour", "number": 5}]}}))
    r = zhipu_mod.fetch({"api_key": "k"})
    assert "error" not in r, r
    assert r["pct"] == pytest.approx(60.0)


def test_add_key_entry_rolls_back_on_save_failure(monkeypatch):
    monkeypatch.setattr(main_mod.notify, "alert", lambda *a, **k: None)

    def boom(c):
        raise config_mod.ConfigError("磁盘满")

    monkeypatch.setattr(config_mod, "save_v2", boom)
    root = tk.Tk()
    try:
        cfg = {"version": 2, "providers": [], "ui": {}, "alert": {}}
        state = main_mod.State()
        actions = main_mod.build_actions(root, cfg, state,
                                         threading.Event(),
                                         threading.Event())
        with pytest.raises(config_mod.ConfigError):
            actions["add_key_entry"]({"name": "X", "key": "sk-1"})
        assert cfg["providers"] == []
        assert state.save_error
    finally:
        root.destroy()


def test_add_key_entry_success_keeps_provider(monkeypatch):
    monkeypatch.setattr(main_mod.notify, "alert", lambda *a, **k: None)
    monkeypatch.setattr(config_mod, "save_v2", lambda c: True)
    root = tk.Tk()
    try:
        cfg = {"version": 2, "providers": [], "ui": {}, "alert": {}}
        actions = main_mod.build_actions(root, cfg, main_mod.State(),
                                         threading.Event(),
                                         threading.Event())
        actions["add_key_entry"]({"name": "X", "key": "sk-1"})
        assert [p["name"] for p in cfg["providers"]] == ["X"]
    finally:
        root.destroy()


def test_refresh_now_ignores_while_fetching():
    root = tk.Tk()
    try:
        state = main_mod.State()
        wake = threading.Event()
        actions = main_mod.build_actions(root, {}, state, threading.Event(),
                                         wake)
        state.fetching = True
        wake.clear()
        actions["refresh_now"]()
        assert not wake.is_set()

        state.fetching = False
        actions["refresh_now"]()
        assert wake.is_set()
        assert state.fetching
    finally:
        root.destroy()


def test_essential_main_value_percent_is_used():
    """与 Panel._fmt_main 同口径:pct 存剩余,主值写已用。"""
    assert eb_mod._main_value({"unit": "%", "pct": 73}) == ("已用 27%", "")
    assert eb_mod._main_value({"unit": "%", "pct": 0}) == ("已用 100%", "")
    assert eb_mod._main_value({"unit": "%", "pct": 150}) == ("已用 0%", "")
    assert eb_mod._main_value({"unit": "%", "pct": None}) == ("-", "")


def test_save_model_order_does_not_refresh_ttl():
    cache_mod.set_models("https://x", "k", ["a", "b"])
    key = cache_mod._hash("https://x", "k")
    data = json.loads(cache_mod.MODELS_CACHE.read_text(encoding="utf-8"))
    data[key]["fetched_at"] = 12345.0
    cache_mod._save_json(cache_mod.MODELS_CACHE, data)

    cache_mod.save_model_order("https://x", "k", ["b", "a"])

    data = json.loads(cache_mod.MODELS_CACHE.read_text(encoding="utf-8"))
    assert data[key]["fetched_at"] == 12345.0
    assert data[key]["order"] == ["b", "a"]


def test_model_panel_probe_dedup_inflight():
    root = tk.Tk()
    try:
        calls = []
        release = threading.Event()

        def slow_probe(model):
            calls.append(model)
            release.wait(2.0)
            return True, 5.0, ""

        p = mp_mod.ModelPanel(root, "P", ["m1"], on_probe=slow_probe)
        try:
            p._probe("m1")
            deadline = time.time() + 2
            while not calls and time.time() < deadline:
                root.update()
                time.sleep(0.01)
            p._probe("m1")  # 在途:必须被忽略
            assert calls == ["m1"]
            release.set()
            deadline = time.time() + 2
            while "m1" in p._probing and time.time() < deadline:
                root.update()
                time.sleep(0.01)
            assert "m1" not in p._probing
            btn = p.probe_btns.get("m1")
            assert btn is not None and str(btn.cget("state")) == "normal"
        finally:
            p.destroy()
    finally:
        root.destroy()
