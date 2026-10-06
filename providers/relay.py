import re
import threading
import time

import requests

TIMEOUT = 12
QUOTA_PER_USD_DEFAULT = 500000.0

LOGIN_PATH = "/api/v1/auth/login"

_TOKEN_CACHE = {}
_TOKEN_LOCK = threading.Lock()

CANDIDATES = (
    ("new_api", "/api/user/self"),
    ("key_usage", "/v1/usage"),
    ("v1_usage", "/api/v1/usage"),
    ("v1_keys", "/api/v1/keys"),
    ("v1_subs", "/api/v1/subscriptions/summary"),
    ("v1_me", "/api/v1/auth/me"),
)

REMAINING_KEYS = ("balance", "remaining", "remain", "total_balance", "credit", "credits", "left", "quota")
USED_KEYS = ("used_quota", "used", "usage_count", "consumed", "total_used", "usage")
TOTAL_KEYS = ("total", "limit", "total_quota", "monthly_limit", "max")


def _cache_key(base, email):
    # 同一站点可以挂多个账号;只按 base 缓存会让两个账号共用同一 token,
    # 第二个账号拿到的是第一个账号的额度。
    return (base, email)


def fetch(entry):
    base = (entry.get("base_url") or "").rstrip("/")
    token = entry.get("token") or ""
    email = entry.get("email") or ""
    password = entry.get("password") or ""
    if not base or not (token or (email and password)):
        return {"error": "未配置 base_url/token", "unconfigured": True}

    extra_headers = dict(entry.get("headers") or {})
    if entry.get("new_api_user_id") is not None:
        extra_headers["New-Api-User"] = str(entry["new_api_user_id"])

    errors = []
    use_access_token = bool(email and password)
    relogged = False

    while True:
        auth_token = token
        if use_access_token:
            auth_token, err = _get_access_token(base, email, password)
            if not auth_token:
                if token:
                    # 登录接口挂了/改版了,但静态 token 还在:降级用它,
                    # 别把整轮额度查询直接判死
                    use_access_token = False
                    auth_token = token
                else:
                    return {"error": f"登录失败: {err}"}

        headers = {"Authorization": f"Bearer {auth_token}", "Accept": "application/json"}
        headers.update(extra_headers)

        saw_401 = False
        for kind, path in CANDIDATES:
            if use_access_token and kind == "new_api":
                continue
            try:
                r = requests.get(base + path, headers=headers, timeout=TIMEOUT)
            except requests.RequestException as e:
                errors.append(f"{path}: {e.__class__.__name__}")
                continue
            if r.status_code == 401 and use_access_token and not relogged:
                with _TOKEN_LOCK:
                    _TOKEN_CACHE.pop(_cache_key(base, email), None)
                relogged = True
                break
            if r.status_code == 401:
                # 静态 token / 重登后仍 401:记住,最后统一给"key 无效",
                # 别让用户面对一串 "HTTP 401" 不知道该换 token
                saw_401 = True
                errors.append(f"{path}: HTTP 401")
                continue
            if r.status_code != 200:
                errors.append(f"{path}: HTTP {r.status_code}")
                continue
            try:
                body = r.json()
            except ValueError:
                errors.append(f"{path}: 非JSON")
                continue
            parsed = _parse(kind, body, entry)
            if parsed is not None:
                if parsed.get("error"):
                    # _parse 主动给出的结论(如 key 无效)直接透传,
                    # 不加 detail 前缀、不再试后续端点
                    return parsed
                parsed["detail"] = f"[{path}] {parsed.get('detail', '')}".strip()
                return parsed
            errors.append(f"{path}: 结构未识别")
        else:
            if saw_401:
                return {"error": "key 无效 (HTTP 401)"}
            return {"error": "; ".join(errors[:3])}

        if relogged:
            continue


def _get_access_token(base, email, password):
    key = _cache_key(base, email)
    with _TOKEN_LOCK:
        cached = _TOKEN_CACHE.get(key)
        if cached and cached["expiry"] > time.time():
            return cached["token"], None
    try:
        r = requests.post(
            base + LOGIN_PATH,
            json={"email": email, "password": password},
            timeout=TIMEOUT,
        )
    except requests.RequestException as e:
        return None, f"{e.__class__.__name__}"
    if r.status_code != 200:
        return None, f"HTTP {r.status_code}"
    try:
        data = r.json()
    except ValueError:
        return None, "响应非JSON"
    if not isinstance(data, dict):
        return None, "响应结构非对象"
    token = data.get("access_token")
    if not token:
        return None, "响应无 access_token"
    try:
        ttl = float(data.get("expires_in") or 3600)
    except (TypeError, ValueError):
        ttl = 3600.0
    with _TOKEN_LOCK:
        _TOKEN_CACHE[key] = {
            "token": token,
            "expiry": time.time() + max(60.0, ttl - 60.0),
        }
    return token, None


def _parse(kind, body, entry):
    if kind == "new_api":
        return _parse_new_api(body, entry)
    if kind == "key_usage":
        return _parse_key_usage(body, entry)
    return _parse_generic(body, entry)


def _parse_key_usage(body, entry):
    if not isinstance(body, dict):
        # 200 但返回 list/标量的异常站点:别让 .get 抛 AttributeError
        return None
    if body.get("isValid") is False:
        # 端点明确说 key 无效:直接给结论,别让用户面对一串
        # "结构未识别"去猜是不是该换 key
        return {"error": "key 无效 (isValid=false)"}
    remaining = body.get("balance", body.get("remaining"))
    if remaining is None:
        return None
    try:
        remaining = float(remaining)
    except (TypeError, ValueError):
        return None
    unit_field = str(body.get("unit") or "USD").upper()
    sym = "$" if "USD" in unit_field else ("¥" if "CNY" in unit_field else "额度")
    usage = body.get("usage") or {}
    today = usage.get("today") or {}
    total = usage.get("total") or {}
    parts = []
    if today:
        cost = today.get("actual_cost")
        if cost is None:
            cost = today.get("cost")
        if cost is not None:
            parts.append(f"今日 {sym}{float(cost):.2f}")
        if today.get("requests") is not None:
            parts.append(f"{int(today['requests'])} 次")
    used = None
    if total:
        used = total.get("actual_cost")
        if used is None:
            used = total.get("cost")
        if used is not None:
            used = float(used)
            parts.append(f"累计实付 {sym}{used:.2f}")
    used_today = None
    if today:
        tcost = today.get("actual_cost")
        if tcost is None:
            tcost = today.get("cost")
        if tcost is not None:
            used_today = float(tcost)
    plan = body.get("planName")
    if plan:
        parts.append(str(plan))
    return {
        "remaining": remaining,
        "used": used,
        "used_today": used_today,
        "total": None,
        "unit": sym,
        "pct": None,
        "detail": " · ".join(parts),
        "is_estimate": False,
    }


def _parse_new_api(body, entry):
    if not isinstance(body, dict):
        # 200 但返回 list/标量的异常站点:别让 .get 抛 AttributeError
        return None
    if body.get("success") is False:
        return None
    data = body.get("data") if isinstance(body.get("data"), dict) else body
    quota = data.get("quota")
    if quota is None:
        return None
    try:
        quota = float(quota)
        used = float(data.get("used_quota") or 0)
    except (TypeError, ValueError):
        return None
    per_usd = float(entry.get("quota_per_usd") or QUOTA_PER_USD_DEFAULT)
    remaining = quota / per_usd
    used_usd = used / per_usd
    total = remaining + used_usd
    pct = remaining / total * 100 if total > 0 else None
    return {
        "remaining": remaining,
        "used": used_usd,
        "used_today": None,
        "total": total,
        "unit": "$",
        "pct": pct,
        "detail": f"剩余 ${remaining:.2f} · 已用 ${used_usd:.2f}",
        "is_estimate": False,
    }


def _parse_generic(body, entry):
    if not isinstance(body, (dict, list)):
        # 200 但返回 list/标量的异常站点:别让 .get 抛 AttributeError
        return None
    # 多 key 站点的 {"success":true,"data":[...]} 包装在这里是
    # "单元素 items 套 list":用 _deep_sum 聚合全部命中,而不是
    # 首中即返只算第一个 key(额度被低估数倍且无"N 个 key"提示)
    key_count = _deep_count(body, REMAINING_KEYS)
    if key_count <= 0:
        return None
    sum_remaining = _deep_sum(body, REMAINING_KEYS)
    sum_used = _deep_sum(body, USED_KEYS)
    sum_total = _deep_sum(body, TOTAL_KEYS)
    found = True
    # one-api 系站点的 quota 是"内部点数";配置了 quota_per_usd 才知道
    # 多少点等于 1 美元,换算成 $ 展示。没配就按原样当"额度"数。
    per_usd = None
    try:
        per_usd = float(entry.get("quota_per_usd") or 0) or None
    except (TypeError, ValueError):
        per_usd = None
    if per_usd:
        sum_remaining /= per_usd
        sum_used /= per_usd
        sum_total /= per_usd
        unit = "$"
        if sum_total > 0:
            detail = (f"剩余 ${sum_remaining:,.2f}"
                      + (f" · {key_count} 个 key" if key_count > 1 else "")
                      + f" · 总量 ${sum_total:,.2f}")
        else:
            detail = (f"剩余 ${sum_remaining:,.2f}"
                      + (f" · {key_count} 个 key" if key_count > 1 else ""))
    else:
        unit = entry.get("unit") or "额度"
        detail = f"剩余 {sum_remaining:,.2f}{unit}"
        if key_count > 1:
            detail += f" · {key_count} 个 key"
        if sum_total > 0:
            detail += f" · 总量 {sum_total:,.2f}"
    if sum_total > 0:
        pct = sum_remaining / sum_total * 100
        return {
            "remaining": sum_remaining,
            "used": sum_used or None,
            "used_today": None,
            "total": sum_total,
            "unit": unit,
            "pct": pct,
            "detail": detail,
            "is_estimate": True,
        }
    return {
        "remaining": sum_remaining,
        "used": sum_used or None,
        "used_today": None,
        "total": None,
        "unit": unit,
        "pct": None,
        "detail": detail,
        "is_estimate": True,
    }


def _deep_find(obj, keys, depth=0):
    if depth > 6:
        return None
    if isinstance(obj, dict):
        data = obj.get("data")
        if isinstance(data, (dict, list)):
            hit = _deep_find(data, keys, depth + 1)
            if hit is not None:
                return hit
        for k in keys:
            v = obj.get(k)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                return float(v)
        for v in obj.values():
            if isinstance(v, dict):
                hit = _deep_find(v, keys, depth + 1)
                if hit is not None:
                    return hit
    elif isinstance(obj, list):
        for item in obj[:20]:
            hit = _deep_find(item, keys, depth + 1)
            if hit is not None:
                return hit
    return None


def _deep_sum(obj, keys, depth=0):
    """与 _deep_find 同样的遍历,但把**所有**命中求和。

    背景:{"success":true,"data":[{...},{...}]} 是 /api/v1/keys 类端点
    的标准包装,多 key 中转站的响应体在这里是"单元素 list 套 list"。
    _deep_find 首中即返,只统计到第一个 key 的剩余,额度被大幅低估,
    连"N 个 key"的提示都不会出现。
    """
    if depth > 6:
        return 0.0
    total = 0.0
    if isinstance(obj, dict):
        data = obj.get("data")
        if isinstance(data, (dict, list)):
            total += _deep_sum(data, keys, depth + 1)
        for k in keys:
            v = obj.get(k)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                total += float(v)
                break
        for v in obj.values():
            if isinstance(v, dict):
                total += _deep_sum(v, keys, depth + 1)
    elif isinstance(obj, list):
        for item in obj[:50]:
            total += _deep_sum(item, keys, depth + 1)
    return total


def _deep_count(obj, keys, depth=0):
    """统计列表容器里有几个条目命中 keys(用于"N 个 key"提示)。"""
    if depth > 6:
        return 0
    if isinstance(obj, list):
        return sum(1 for el in obj[:50]
                   if _deep_find(el, keys) is not None)
    if isinstance(obj, dict):
        data = obj.get("data")
        if isinstance(data, (dict, list)):
            n = _deep_count(data, keys, depth + 1)
            if n:
                return n
        return 1 if _deep_find(obj, keys) is not None else 0
    return 0
