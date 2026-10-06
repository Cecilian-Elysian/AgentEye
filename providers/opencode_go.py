"""OpenCode Go(zen/go)订阅额度。

percent 字段的语义决定:按"剩余"解读——与 remaining 字段名、
providers._level 的 pct<=warn 告警方向、面板主值"已用 100-pct"
保持一致。detail 文案与主值/胶囊必须同向,统一写"剩≈$X/$Y"。

WINDOWS 里的 $12/$30/$60 是硬编码的订阅档位额度:换档后金额会不准,
is_estimate=True(以及 detail 的"≈")就是为此留下的免责标记。
"""
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
    """percent 视为 0-100 的剩余百分比,钳到 [0, 100]。

    不做 0-1 比例的猜测换算:真实分数百分比如 0.9(剩 0.9%,最该
    告警的时刻)会被 x100 放大成 90,恰好在最关键的尾部区间把方向
    反转掉。zhipu 的 percentage 与 relay 的比值口径也都是 0-100。
    """
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
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
    urls = _usage_urls(entry.get("base_url"))
    for i, url in enumerate(urls):
        try:
            r = requests.get(
                url,
                headers={"Authorization": f"Bearer {key}",
                         "Accept": "application/json"},
                timeout=TIMEOUT,
            )
        except requests.RequestException as e:
            return {"error": f"网络错误: {e.__class__.__name__}"}
        if r.status_code == 401:
            # 鉴权层拒绝与路径无关,不需要回退
            return {"error": "key 无效 (HTTP 401)"}
        if r.status_code == 200:
            break
        last_status = r.status_code
        r = None
        is_last = i + 1 >= len(urls)
        # 404/405/501 = 端点不存在,换下一个候选。403 只在末位(已知
        # 正确的)端点上判 key 无效:WAF 对猜测路径返回 403 很常见,
        # 提前判死会把有效 key 误报成无效
        retryable = last_status in (404, 405, 501, 403) and not is_last
        if is_last or not retryable:
            break
    if r is None:
        if last_status == 403:
            return {"error": "key 无效 (HTTP 403)"}
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
        parts.append(f"{label} 剩≈${amt:.2f}/${limit:.0f}")
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

    # used 必须回填:面板胶囊的长度/颜色吃 used/total。percent 按
    # "剩余"解读(见模块头),monthly_amt 是"月窗口剩余换算",胶囊
    # 要的已用就是 60 - monthly_amt,与 detail 的"剩≈$X/$60"同源。
    used_monthly = None
    if monthly_amt is not None:
        used_monthly = max(0.0, 60.0 - monthly_amt)

    return {
        "remaining": monthly_amt,
        "used": used_monthly,
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
