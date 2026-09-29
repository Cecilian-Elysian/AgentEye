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

LEVEL_ERROR = "error"
LEVEL_UNKNOWN = "unknown"
LEVEL_PAUSED = "paused"

PLACEHOLDER_KEYS = {
    "在这里粘贴中转站的key",
    "在这里粘贴订阅Key",
    "在这里粘贴Go的key",
    "在这里粘贴DeepSeek的key",
    "在这里粘贴智谱的key",
}


def collect_entries(cfg):
    """v2 schema:从 cfg['providers'] 收集所有条目。"""
    out = []
    for p in cfg.get("providers") or []:
        if isinstance(p, dict):
            out.append((p.get("kind", ""), p))
    return out


def fetch_all(cfg, skip_names=None):
    """并发拉取所有 provider。skip_names 里的条目不发请求,直接返回 paused 行。

    两个硬性要求:
    - 返回顺序必须与 cfg['providers'] 一致。panel 用 (name, type) 序列当
      重建签名,顺序一变就整面板 destroy 重建,滚动位置也会丢。
    - 单个 provider 抛异常只影响它自己那一行,不能连累其它条目。
    """
    entries = collect_entries(cfg)
    if not entries:
        return []
    skip = set(skip_names or ())
    todo = [(k, e) for k, e in entries if e.get("name") not in skip]

    by_name = {}
    if todo:
        with ThreadPoolExecutor(max_workers=max(4, len(todo))) as ex:
            futures = {}
            for kind, entry in todo:
                fut = ex.submit(_one, kind, entry, cfg)
                futures[fut] = (kind, entry)
            for fut in futures:
                kind, entry = futures[fut]
                try:
                    by_name[entry.get("name")] = fut.result()
                except Exception as e:
                    by_name[entry.get("name")] = _failed(kind, entry, e)
    for kind, entry in entries:
        if entry.get("name") in skip:
            by_name[entry.get("name")] = _paused(kind, entry)
    return [by_name[e.get("name")] for _k, e in entries]


def _blank_result(kind, entry):
    """result 的唯一字段清单来源。UI 依赖这些键,缺一个就是隐性 bug。"""
    return {
        "id": entry.get("id"),
        "name": entry.get("name") or f"{kind}-provider",
        "type": kind,
        "kind": kind,
        "remaining": None,
        "used": None,
        "total": None,
        "used_today": None,
        "unit": "",
        "pct": None,
        "detail": "",
        "is_estimate": False,
        "updated_at": time.time(),
        "error": None,
        "unconfigured": False,
        "paused": False,
        "level": LEVEL_UNKNOWN,
    }


def _failed(kind, entry, exc):
    """某个 provider 连 result 都构造不出来时的兜底行。"""
    res = _blank_result(kind, entry)
    res.update({"error": f"{exc.__class__.__name__}: {exc}",
                "level": LEVEL_ERROR})
    return res


def _paused(kind, entry):
    """被用户手动暂停的 provider:不发请求,也不产生告警。"""
    res = _blank_result(kind, entry)
    res.update({"detail": "已暂停轮询", "paused": True,
                "level": LEVEL_PAUSED})
    return res


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
    extra = {k: v for k, v in (p.get("extra") or {}).items()
             if k not in ("api_key", "token", "key")}
    entry.update(extra)
    for f in ("quota_per_usd", "new_api_user_id", "headers"):
        if f in p:
            entry[f] = p[f]
    # key 相关字段最终以解密结果为准,不能让 extra 旁路覆盖
    entry["api_key"] = entry["token"] = entry["key"] = key
    return entry


def _num(value, default):
    """从配置里取数字。JSON 里显式的 null、非数字字符串都要能兜住。

    阈��解析失败若抛到上层,fetch_all 整个不返回,面板会冻在上一次数据上。
    """
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _one(kind, entry, cfg):
    result = _blank_result(kind, entry)
    key = _resolve_key(entry)
    login_creds = bool((entry.get("extra") or {}).get("email")
                       and (entry.get("extra") or {}).get("password"))
    if key in PLACEHOLDER_KEYS:
        key = ""  # 占位文本等同于没填
    if not key and not login_creds:
        result.update({"error": "未配置 key", "unconfigured": True,
                       "level": "unconfigured"})
        return result
    legacy = _to_legacy_entry(entry, key)
    adapter = ADAPTERS.get(kind)
    if not adapter:
        result["error"] = f"未知 provider kind: {kind}"
        result["level"] = LEVEL_ERROR
        return result
    try:
        result.update(adapter(legacy))
        result["updated_at"] = time.time()
        result["level"] = _level(result, entry, cfg)
    except Exception as e:
        result["error"] = f"{e.__class__.__name__}: {e}"
        result["level"] = LEVEL_ERROR
    return result


def _level(res, entry, cfg):
    """阈值简化版:只有 ¥ 临界和 % 警告会触发 warn/critical,其余保持 OK。

    - ¥ 临界:cfg.alert.critical_amount_yuan(默认 5.0),低于 = critical
    - % 警告:cfg.alert.warn_pct(默认 30),低于 = warn
    - $ / 额度 / 其他:不再做阈值判断,保持 ok
    """
    if res.get("error"):
        return "unconfigured" if res.get("unconfigured") else LEVEL_ERROR
    alert = cfg.get("alert") or {}
    unit = res.get("unit")
    if unit == "¥":
        crit = _num(alert.get("critical_amount_yuan"), 5.0)
        remaining = res.get("remaining")
        if remaining is None:
            return "ok"
        return "critical" if remaining <= crit else "ok"
    if unit == "%":
        warn = _num(alert.get("warn_pct"), 30.0)
        pct = res.get("pct")
        if pct is None:
            return "ok"
        return "warn" if pct <= warn else "ok"
    return "ok"
