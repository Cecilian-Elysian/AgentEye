import requests

TIMEOUT = 12
URL = "https://opencode.ai/zen/go/v1/usage"

WINDOWS = (
    ("rolling", "5h", 12.0),
    ("weekly", "周", 30.0),
    ("monthly", "月", 60.0),
)


def _norm_pct(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    if v <= 1:
        v *= 100
    return max(0.0, min(100.0, v))


def fetch(entry):
    base = (entry.get("base_url") or URL).rstrip("/")
    url = base if base.endswith("/usage") else base + "/v1/usage"
    key = entry.get("api_key") or ""
    if not key:
        return {"error": "未配置 api_key", "unconfigured": True}

    try:
        r = requests.get(
            url,
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

    usage = body.get("usage") or body
    parts = []
    pcts = []
    resets = []
    for wkey, label, limit in WINDOWS:
        w = usage.get(wkey)
        if not isinstance(w, dict):
            continue
        p = _norm_pct(w.get("percent"))
        if p is None:
            continue
        amt = p / 100.0 * limit
        parts.append(f"{label} ≈${amt:.2f}/${limit:.0f}")
        pcts.append(p)
        if w.get("resetsAt"):
            resets.append(w["resetsAt"])

    if not pcts:
        return {"error": "响应无窗口数据"}

    monthly_amt = None
    w = usage.get("monthly")
    if isinstance(w, dict) and _norm_pct(w.get("percent")) is not None:
        monthly_amt = _norm_pct(w["percent"]) / 100.0 * 60.0

    reset_note = ""
    if resets:
        reset_note = f" · 重置 {_iso_in(resets[0])}"

    return {
        "remaining": monthly_amt,
        "used": None,
        "total": 60.0,
        "unit": "$",
        "pct": min(pcts),
        "detail": " · ".join(parts) + reset_note,
        "is_estimate": True,
    }


def _iso_in(iso_str):
    from datetime import datetime, timezone

    try:
        dt = datetime.fromisoformat(str(iso_str).replace("Z", "+00:00"))
        delta = dt - datetime.now(timezone.utc)
        sec = int(delta.total_seconds())
    except (ValueError, TypeError):
        return "?"
    if sec <= 0:
        return "已重置"
    h, m = sec // 3600, (sec % 3600) // 60
    return f"{h}h{m:02d}m" if h else f"{m}m"
