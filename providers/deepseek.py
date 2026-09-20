import requests

TIMEOUT = 12
URL = "https://api.deepseek.com/user/balance"

SYMBOLS = {"CNY": "¥", "USD": "$"}
DEFAULT_THRESHOLDS = {"CNY": (10.0, 5.0), "USD": (2.0, 1.0)}


def fetch(entry):
    base = (entry.get("base_url") or "https://api.deepseek.com").rstrip("/")
    key = entry.get("api_key") or ""
    if not key:
        return {"error": "未配置 api_key", "unconfigured": True}

    try:
        r = requests.get(
            base + "/user/balance",
            headers={"Authorization": f"Bearer {key}", "Accept": "application/json"},
            timeout=TIMEOUT,
        )
    except requests.RequestException as e:
        return {"error": f"网络错误: {e.__class__.__name__}"}

    if r.status_code in (401, 403):
        return {"error": f"key 无效 (HTTP {r.status_code})"}
    if r.status_code != 200:
        return {"error": f"HTTP {r.status_code}"}

    try:
        body = r.json()
    except ValueError:
        return {"error": "响应非 JSON"}

    infos = body.get("balance_infos") or []
    if not infos:
        return {"error": "响应无 balance_infos"}

    info = infos[0]
    currency = info.get("currency", "CNY")
    sym = SYMBOLS.get(currency, currency + " ")
    try:
        total = float(info.get("total_balance") or 0)
        granted = float(info.get("granted_balance") or 0)
        topped = float(info.get("topped_up_balance") or 0)
    except (TypeError, ValueError):
        return {"error": "余额字段解析失败"}

    available = body.get("is_available", True)
    detail = f"赠金 {sym}{granted:.2f} · 充值 {sym}{topped:.2f}"
    if not available:
        detail += " · 余额不可用"

    warn, crit = DEFAULT_THRESHOLDS.get(currency, (10.0, 5.0))
    if entry.get("warn_amount") is not None:
        warn = float(entry["warn_amount"])
    if entry.get("critical_amount") is not None:
        crit = float(entry["critical_amount"])

    return {
        "remaining": total,
        "used": None,
        "total": None,
        "unit": sym,
        "pct": None,
        "detail": detail,
        "is_estimate": False,
        "warn": warn,
        "critical": crit,
    }
