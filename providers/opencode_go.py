import requests

TIMEOUT = 12
URL = "https://opencode.ai/zen/go/v1/usage"

# 候选端点:按顺序尝试,404/405/501 才换下一个。
# 用户在 UI 预设里填的 base_url 不带 /zen/go,拼出来的是
# https://opencode.ai/v1/usage(404),所以必须留一条回退到正确路径。
URL_VARIANTS = (
    "https://opencode.ai/zen/go/v1/usage",
)

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
    # 兼容 0-1 比例语义(0.35 → 35%)。严格小于 1 才翻倍:
    # 恰好 1.0 有歧义(1% 还是 100%),按 1% 处理,和 v<=1 旧写法的
    # 差别是 v==1 不再被误放大 100 倍。
    if 0 < v < 1:
        v *= 100
    return max(0.0, min(100.0, v))


def _usage_urls(base):
    """按顺序给出候选 usage URL。

    预设/自动识别填的 base_url 是 https://opencode.ai,而真实端点在
    /zen/go 下,直接拼 base + "/v1/usage" 会 404。这里把"按 base_url
    拼的"和"模块常量"都列出来,由 fetch 按序重试,两种填法都能用。
    """
    base = (base or "").rstrip("/")
    urls = []
    if base:
        urls.append(base if base.endswith("/usage") else base + "/v1/usage")
    for u in URL_VARIANTS:
        if u not in urls:
            urls.append(u)
    return urls


def fetch(entry):
    key = entry.get("api_key") or ""
    if not key:
        return {"error": "未配置 api_key", "unconfigured": True}

    r = None
    last_status = None
    for url in _usage_urls(entry.get("base_url")):
        try:
            r = requests.get(
                url,
                headers={"Authorization": f"Bearer {key}",
                         "Accept": "application/json"},
                timeout=TIMEOUT,
            )
        except requests.RequestException as e:
            return {"error": f"网络错误: {e.__class__.__name__}"}
        if r.status_code in (401, 403):
            return {"error": f"key 无效 (HTTP {r.status_code})"}
        if r.status_code == 200:
            break
        last_status = r.status_code
        r = None
        if r is None and last_status not in (404, 405, 501):
            # 只在"端点不存在"时才换下一个候选,其它状态码重试无意义
            break
    if r is None:
        return {"error": f"HTTP {last_status}"}

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
