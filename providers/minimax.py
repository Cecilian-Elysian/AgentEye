import re
import time

import requests

TIMEOUT = 12
DEFAULT_HOST = "https://api.minimaxi.com"

CODING_PATH = "/v1/api/openplatform/coding_plan/remains"
TOKEN_PATH = "/v1/token_plan/remains"

INTERVAL_KEYS = (
    "current_interval_remaining_percent",
    "interval_remaining_percent",
    "remaining_percent",
    "remains_percent",
)
WEEKLY_KEYS = (
    "current_weekly_remaining_percent",
    "weekly_remaining_percent",
)
TIME_KEYS = ("remains_time", "weekly_remains_time", "reset_time")
NAME_KEYS = ("model_name", "model", "name")
ITEM_LIST_KEYS = ("model_remains", "remains", "models", "sub_remains")


def _host(entry):
    base = entry.get("base_url") or DEFAULT_HOST
    m = re.match(r"(https?://[^/]+)", base)
    return (m.group(1) if m else DEFAULT_HOST).rstrip("/")


def _norm_pct(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(100.0, v))


def _first(item, keys):
    for k in keys:
        if item.get(k) is not None:
            return item[k]
    return None


def _extract_items(body):
    candidates = [body]
    data = body.get("data")
    if isinstance(data, dict):
        candidates.append(data)
    for src in candidates:
        for k in ITEM_LIST_KEYS:
            v = src.get(k)
            if isinstance(v, list) and v and isinstance(v[0], dict):
                return v
    return None


def _fmt_reset(value):
    """把重置时间格式化成剩余时长。

    字段语义不统一:remains_time 是"还剩多少毫秒",而 reset_time 是
    "到点的绝对时间戳"(秒或毫秒)。按量级自动判别,否则绝对时间戳被
    当剩余时长,会算出"重置 19万小时"这种乱值。
    """
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v <= 0:
        return None
    if v >= 1e11:
        return _fmt_remaining(v - time.time() * 1000.0)
    if 1e9 <= v < 1e11:
        # 秒级时间戳:毫秒时长最大 ~6e8(一周),不会落到这个区间
        return _fmt_remaining(v * 1000.0 - time.time() * 1000.0)
    return _fmt_remaining(v)


def _fmt_remaining(ms):
    sec = int(ms / 1000)
    if sec <= 0:
        return None
    d, rest = sec // 86400, sec % 86400
    h, m = rest // 3600, (rest % 3600) // 60
    if d:
        return f"{d}d{h:02d}h"
    return f"{h}h{m:02d}m" if h else f"{m}m"


def fetch(entry):
    key = entry.get("api_key") or ""
    if not key:
        return {"error": "未配置 api_key", "unconfigured": True}

    plan = entry.get("plan")
    if plan not in ("coding_plan", "token_plan"):
        plan = "coding_plan" if key.startswith("sk-cp-") else "token_plan"
    path = CODING_PATH if plan == "coding_plan" else TOKEN_PATH
    url = _host(entry) + path

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

    # 接口级报错必须在解析 items 之前判:不然错误体里的残留字段会被
    # 当成正常数据,报出莫名的"结构未识别"或假额度。
    status_code = (body.get("base_resp") or {}).get("status_code")
    if status_code not in (None, 0):
        return {"error": f"接口报错: {(body.get('base_resp') or {}).get('status_msg', status_code)}"}

    items = _extract_items(body)
    if not items:
        return {"error": "响应结构未识别"}

    parsed = []
    skipped = 0
    for it in items:
        if it.get("current_interval_status") == 3 and it.get("current_weekly_status") == 3:
            skipped += 1
            continue
        name = _first(it, NAME_KEYS) or "?"
        interval = _norm_pct(_first(it, INTERVAL_KEYS))
        weekly = _norm_pct(_first(it, WEEKLY_KEYS))
        total_n = it.get("current_interval_total_count")
        used_n = it.get("current_interval_usage_count")
        reset = _fmt_reset(_first(it, TIME_KEYS))
        parsed.append(
            {
                "name": name,
                "interval": interval,
                "weekly": weekly,
                "reset": reset,
                "total_n": total_n,
                "used_n": used_n,
            }
        )

    if not parsed:
        return {"error": "套餐未启用或无可用额度项"}

    headline = next(
        (p for p in parsed if "general" in str(p["name"]).lower()), parsed[0]
    )
    if headline["interval"] is None:
        # general 项没有 5h 百分比时,退而取第一个有百分比的项,
        # 避免 headline 指向空值导致 reset 时间和实际 pct 张冠李戴。
        with_pct = next((p for p in parsed if p["interval"] is not None), None)
        if with_pct is not None:
            headline = with_pct
    pct = headline["interval"]
    if pct is None:
        percents = [p["interval"] for p in parsed if p["interval"] is not None]
        if not percents:
            return {"error": "无百分比字段"}
        pct = percents[0]

    parts = []
    for p in parsed[:3]:
        seg = str(p["name"])
        if p["total_n"]:
            try:
                seg += f" {int(p['total_n']) - int(p['used_n'] or 0)}/{int(p['total_n'])} 次"
            except (TypeError, ValueError):
                seg += f" 5h {p['interval']:.0f}%" if p["interval"] is not None else ""
        elif p["interval"] is not None:
            seg += f" 5h {p['interval']:.0f}%"
        if p["weekly"] is not None:
            seg += f" · 周 {p['weekly']:.0f}%"
        parts.append(seg)
    if len(parsed) > 3:
        parts.append(f"…共{len(parsed)}个模型")
    if skipped:
        parts.append(f"({skipped}项未启用)")
    detail = " | ".join(parts)
    if headline["reset"]:
        detail += f" · 重置 {headline['reset']}"
    detail = f"[{plan}] " + detail

    return {
        "remaining": None,
        "used": None,
        "total": None,
        "unit": "%",
        "pct": pct,
        "detail": detail,
        "is_estimate": False,
    }
