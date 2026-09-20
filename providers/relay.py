import re
import time

import requests

TIMEOUT = 12
QUOTA_PER_USD_DEFAULT = 500000.0

LOGIN_PATH = "/api/v1/auth/login"

_TOKEN_CACHE = {}

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
                return {"error": f"登录失败: {err}"}

        headers = {"Authorization": f"Bearer {auth_token}", "Accept": "application/json"}
        headers.update(extra_headers)

        for kind, path in CANDIDATES:
            if use_access_token and kind == "new_api":
                continue
            try:
                r = requests.get(base + path, headers=headers, timeout=TIMEOUT)
            except requests.RequestException as e:
                errors.append(f"{path}: {e.__class__.__name__}")
                continue
            if r.status_code == 401 and use_access_token and not relogged:
                _TOKEN_CACHE.pop(base, None)
                relogged = True
                break
            if r.status_code != 200:
                errors.append(f"{path}: HTTP {r.status_code}")
                continue
            try:
                body = r.json()
            except ValueError:
                errors.append(f"{path}: 非JSON")
                continue
            parsed = _parse(kind, body, entry)
            if parsed:
                parsed["detail"] = f"[{path}] {parsed.get('detail', '')}".strip()
                return parsed
            errors.append(f"{path}: 结构未识别")
        else:
            return {"error": "; ".join(errors[:3])}

        if relogged:
            continue


def _get_access_token(base, email, password):
    cached = _TOKEN_CACHE.get(base)
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
    token = data.get("access_token")
    if not token:
        return None, "响应无 access_token"
    try:
        ttl = float(data.get("expires_in") or 3600)
    except (TypeError, ValueError):
        ttl = 3600.0
    _TOKEN_CACHE[base] = {
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
    if body.get("isValid") is False:
        return None
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
    plan = body.get("planName")
    if plan:
        parts.append(str(plan))
    return {
        "remaining": remaining,
        "used": used,
        "total": None,
        "unit": sym,
        "pct": None,
        "detail": " · ".join(parts),
        "is_estimate": False,
    }


def _parse_new_api(body, entry):
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
        "total": total,
        "unit": "$",
        "pct": pct,
        "detail": f"剩余 ${remaining:.2f} · 已用 ${used_usd:.2f}",
        "is_estimate": False,
    }


def _parse_generic(body, entry):
    items = body if isinstance(body, list) else [body]
    sum_remaining = 0.0
    sum_used = 0.0
    sum_total = 0.0
    found = False
    key_count = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        key_count += 1
        rem = _deep_find(item, REMAINING_KEYS)
        if rem is None:
            continue
        found = True
        sum_remaining += rem
        sum_used += _deep_find(item, USED_KEYS) or 0
        sum_total += _deep_find(item, TOTAL_KEYS) or 0
    if not found:
        return None
    unit = entry.get("unit") or "额度"
    detail = f"剩余 {sum_remaining:,.2f}{unit}"
    if key_count > 1:
        detail += f" · {key_count} 个 key"
    if sum_total > 0:
        pct = sum_remaining / sum_total * 100
        detail += f" · 总量 {sum_total:,.2f}"
        return {
            "remaining": sum_remaining,
            "used": sum_used or None,
            "total": sum_total,
            "unit": unit,
            "pct": pct,
            "detail": detail,
            "is_estimate": True,
        }
    return {
        "remaining": sum_remaining,
        "used": sum_used or None,
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
