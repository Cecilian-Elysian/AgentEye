import requests

TIMEOUT = 12
DEFAULT_BASE = "https://open.bigmodel.cn"
PATH = "/api/monitor/usage/quota/limit"

WINDOW_LABELS = {
    (3, 5): "5h",
    (6, 1): "周",
}


def _fmt_reset_abs(ms):
    try:
        sec = int(float(ms) / 1000) - _now()
    except (TypeError, ValueError):
        return None
    if sec <= 0:
        return None
    d, rest = sec // 86400, sec % 86400
    h, m = rest // 3600, (rest % 3600) // 60
    if d:
        return f"{d}d{h:02d}h"
    if h:
        return f"{h}h{m:02d}m"
    return f"{m}m"


def _now():
    import time

    return int(time.time())


def fetch(entry):
    key = entry.get("api_key") or ""
    if not key:
        return {"error": "未配置 api_key", "unconfigured": True}

    base = (entry.get("base_url") or DEFAULT_BASE).rstrip("/")
    try:
        r = requests.get(
            base + PATH,
            headers={"Authorization": key, "Accept": "application/json"},
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

    if body.get("code") not in (None, 200) or body.get("success") is False:
        return {"error": f"接口报错: {body.get('msg') or body.get('code')}"}

    data = body.get("data") or {}
    limits = data.get("limits") or []
    token_limits = [
        l
        for l in limits
        if l.get("type") == "TOKENS_LIMIT" and l.get("percentage") is not None
    ]
    if not token_limits:
        return {"error": "无 token 额度窗口"}

    parts = []
    remaining = []
    for l in token_limits:
        label = WINDOW_LABELS.get(
            (l.get("unit"), l.get("number")), f"{l.get('number')}·u{l.get('unit')}"
        )
        used = float(l["percentage"])
        rem = max(0.0, 100.0 - used)
        remaining.append(rem)
        seg = f"{label} 剩{rem:.0f}%"
        reset = _fmt_reset_abs(l.get("nextResetTime"))
        if reset:
            seg += f"(重置{reset})"
        parts.append(seg)

    level = data.get("level")
    detail = " · ".join(parts)
    if level:
        detail += f" · {level}套餐"

    return {
        "remaining": None,
        "used": None,
        "total": None,
        "unit": "%",
        "pct": min(remaining),
        "detail": detail,
        "is_estimate": False,
    }
