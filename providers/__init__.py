import time
from concurrent.futures import ThreadPoolExecutor

from . import deepseek, minimax, opencode_go, relay, zhipu

ADAPTERS = {
    "relay": relay.fetch,
    "minimax": minimax.fetch,
    "opencode_go": opencode_go.fetch,
    "deepseek": deepseek.fetch,
    "zhipu": zhipu.fetch,
}

KIND_CONFIG_KEY = {
    "relay": "relay_sites",
    "minimax": "minimax",
    "opencode_go": "opencode_go",
    "deepseek": "deepseek",
    "zhipu": "zhipu",
}

DEFAULT_NAMES = {
    "relay": "中转站",
    "minimax": "MiniMax",
    "opencode_go": "OpenCode Go",
    "deepseek": "DeepSeek",
    "zhipu": "智谱 GLM",
}

AMOUNT_UNITS = ("$", "¥")

PLACEHOLDER_KEYS = {
    "在这里粘贴中转站的key",
    "在这里粘贴订阅Key",
    "在这里粘贴Go的key",
    "在这里粘贴DeepSeek的key",
    "在这里粘贴智谱的key",
}


def collect_entries(cfg):
    entries = []
    for kind, cfg_key in KIND_CONFIG_KEY.items():
        for entry in cfg.get(cfg_key) or []:
            if isinstance(entry, dict):
                entries.append((kind, entry))
    return entries


def fetch_all(cfg):
    entries = collect_entries(cfg)
    if not entries:
        return []
    with ThreadPoolExecutor(max_workers=max(4, len(entries))) as ex:
        futures = [ex.submit(_one, kind, entry, cfg) for kind, entry in entries]
        return [f.result() for f in futures]


def _one(kind, entry, cfg):
    result = {
        "name": entry.get("name") or DEFAULT_NAMES[kind],
        "type": kind,
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
    key = entry.get("api_key") or entry.get("token") or ""
    login_creds = bool(entry.get("email") and entry.get("password"))
    if (not key and not login_creds) or key in PLACEHOLDER_KEYS:
        result.update({"error": "未配置 key", "unconfigured": True, "level": "unconfigured"})
        return result
    try:
        result.update(ADAPTERS[kind](entry))
    except Exception as e:
        result["error"] = f"{e.__class__.__name__}: {e}"
    result["updated_at"] = time.time()
    result["level"] = _level(result, entry, cfg)
    return result


def _level(res, entry, cfg):
    if res.get("error"):
        return "unconfigured" if res.get("unconfigured") else "error"
    alert = cfg.get("alert") or {}
    unit = res.get("unit")
    if unit in AMOUNT_UNITS or unit == "额度" or entry.get("warn_amount") is not None:
        if unit == "¥":
            d_warn, d_crit = 10.0, 5.0
        else:
            d_warn, d_crit = 10.0, 3.0
        warn = float(entry.get("warn_amount", alert.get("warn_amount", d_warn)))
        crit = float(entry.get("critical_amount", alert.get("critical_amount", d_crit)))
        remaining = res.get("remaining")
        if remaining is None:
            return "ok"
        if remaining <= crit:
            return "critical"
        if remaining <= warn:
            return "warn"
        return "ok"
    warn = float(entry.get("warn_pct", alert.get("warn_pct", 30)))
    crit = float(entry.get("critical_pct", alert.get("critical_pct", 10)))
    pct = res.get("pct")
    if pct is None:
        return "ok"
    if pct <= crit:
        return "critical"
    if pct <= warn:
        return "warn"
    return "ok"


def fmt_main(res):
    if res.get("unconfigured"):
        return "未配置"
    if res.get("error"):
        return "查询失败"
    unit = res.get("unit", "")
    prefix = "≈" if res.get("is_estimate") else ""
    if unit in AMOUNT_UNITS:
        remaining = res.get("remaining")
        if remaining is None:
            return "-"
        text = f"{prefix}{unit}{remaining:,.2f}"
        if res.get("total"):
            text += f" / {unit}{res['total']:,.2f}"
        return text
    if unit == "%":
        pct = res.get("pct")
        return f"{pct:.0f}%" if pct is not None else "-"
    remaining = res.get("remaining")
    return f"{prefix}{remaining:,.2f}{unit}" if remaining is not None else "-"


def fmt_countdown(sec):
    sec = max(0, int(sec))
    h, m, s = sec // 3600, (sec % 3600) // 60, sec % 60
    if h:
        return f"{h}h{m:02d}m{s:02d}s"
    return f"{m:02d}:{s:02d}"
