import time
from concurrent.futures import ThreadPoolExecutor

from . import deepseek, generic, minimax, opencode_go, relay, zhipu

ADAPTERS = {
    "relay": relay.fetch,
    "minimax": minimax.fetch,
    "opencode_go": opencode_go.fetch,
    "deepseek": deepseek.fetch,
    "zhipu": zhipu.fetch,
    "generic_openai": generic.fetch,
}

AMOUNT_UNITS = ("$", "¥")

PLACEHOLDER_KEYS = {
    "在这里粘贴中转站的key",
    "在这里粘贴订阅Key",
    "在这里粘贴Go的key",
    "在这里粘贴DeepSeek的key",
    "在这里粘贴智谱的key",
}


LEVEL_PAUSED = "paused"


def collect_entries(cfg):
    """v2 schema:从 cfg['providers'] 收集所有条目。"""
    out = []
    for p in cfg.get("providers") or []:
        if isinstance(p, dict):
            out.append((p.get("kind", ""), p))
    return out


def fetch_all(cfg, skip_names=None):
    """并发拉取所有 provider。skip_names 里的条目不发请求,直接返回 paused 行。"""
    entries = collect_entries(cfg)
    if not entries:
        return []
    skip = set(skip_names or ())
    paused = [(k, e) for k, e in entries if e.get("name") in skip]
    todo = [(k, e) for k, e in entries if e.get("name") not in skip]
    results = []
    if todo:
        with ThreadPoolExecutor(max_workers=max(4, len(todo))) as ex:
            futures = [ex.submit(_one, kind, entry, cfg)
                       for kind, entry in todo]
            results = [f.result() for f in futures]
    results.extend(_paused(kind, entry) for kind, entry in paused)
    return results


def _paused(kind, entry):
    """被用户手动暂停的 provider:不发请求,也不产生告警。"""
    return {
        "id": entry.get("id"),
        "name": entry.get("name") or f"{kind}-provider",
        "type": kind,
        "kind": kind,
        "remaining": None,
        "used": None,
        "total": None,
        "unit": "",
        "pct": None,
        "detail": "已暂停轮询",
        "is_estimate": False,
        "updated_at": time.time(),
        "error": None,
        "unconfigured": False,
        "paused": True,
        "level": LEVEL_PAUSED,
    }


def _resolve_key(entry):
    """取明文 key:优先内存态 key,否则解 key_enc(磁盘态兜底)。"""
    key = entry.get("key") or ""
    if key or not entry.get("key_enc"):
        return key
    try:
        from config import plain_key
        return plain_key(entry) or ""
    except Exception:
        return ""


def _to_legacy_entry(p, key):
    """v2 entry → legacy 适配器期望的 dict 形状。key 由调用方解好。"""
    entry = {
        "name": p.get("name"),
        "api_key": key,
        "token": key,
        "key": key,
        "base_url": p.get("base_url"),
    }
    extra = p.get("extra") or {}
    entry.update(extra)
    for f in ("quota_per_usd", "new_api_user_id", "headers"):
        if f in p:
            entry[f] = p[f]
    return entry


def _one(kind, entry, cfg):
    name = entry.get("name") or f"{kind}-provider"
    result = {
        "id": entry.get("id"),
        "name": name,
        "type": kind,
        "kind": kind,
        "remaining": None,
        "used": None,
        "total": None,
        "unit": "",
        "pct": None,
        "detail": "",
        "is_estimate": False,
        "updated_at": time.time(),
        "error": None,
        "unconfigured": False,
        "level": "unknown",
    }
    key = _resolve_key(entry)
    login_creds = bool((entry.get("extra") or {}).get("email")
                       and (entry.get("extra") or {}).get("password"))
    if (not key and not login_creds) or key in PLACEHOLDER_KEYS:
        result.update({"error": "未配置 key", "unconfigured": True,
                       "level": "unconfigured"})
        return result
    legacy = _to_legacy_entry(entry, key)
    adapter = ADAPTERS.get(kind)
    if not adapter:
        result["error"] = f"未知 provider kind: {kind}"
        result["level"] = "error"
        return result
    try:
        result.update(adapter(legacy))
    except Exception as e:
        result["error"] = f"{e.__class__.__name__}: {e}"
    result["updated_at"] = time.time()
    result["level"] = _level(result, entry, cfg)
    return result


def _level(res, entry, cfg):
    """阈值简化版:只有 ¥ 临界和 % 警告会触发 warn/critical,其余保持 OK。

    - ¥ 临界:cfg.alert.critical_amount_yuan(默认 5.0),低于 = critical
    - % 警告:cfg.alert.warn_pct(默认 30),低于 = warn
    - $ / 额度 / 其他:不再做阈值判断,保持 ok
    """
    if res.get("error"):
        return "unconfigured" if res.get("unconfigured") else "error"
    alert = cfg.get("alert") or {}
    unit = res.get("unit")
    if unit == "¥":
        crit = float(alert.get("critical_amount_yuan", 5.0))
        remaining = res.get("remaining")
        if remaining is None:
            return "ok"
        return "critical" if remaining <= crit else "ok"
    if unit == "%":
        warn = float(alert.get("warn_pct", 30))
        pct = res.get("pct")
        if pct is None:
            return "ok"
        return "warn" if pct <= warn else "ok"
    return "ok"
