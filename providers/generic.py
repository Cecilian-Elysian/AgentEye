"""通用 OpenAI 兼容 provider 适配器 + 模型探测。"""

import requests

TIMEOUT = 12

QUOTA_PROBES = (
    ("openai_billing", "/dashboard/billing/credit_grants", "_parse_openai_billing"),
    ("openai_subscription", "/dashboard/billing/subscription", "_parse_openai_subscription"),
    ("deepseek_balance", "/user/balance", "_parse_deepseek_balance"),
    ("new_api_self", "/api/user/self", "_parse_new_api_self"),
)

_PARSERS = {}


def _parser(name):
    def deco(fn):
        _PARSERS[name] = fn
        return fn
    return deco


def fetch_models(entry):
    """拉取 provider 的模型列表。"""
    base = (entry.get("base_url") or "").rstrip("/")
    key = entry.get("api_key") or entry.get("key") or ""
    if not base:
        return {"models": [], "error": "缺少 base_url"}
    if not key:
        return {"models": [], "error": "缺少 key"}

    models_url = base + "/models" if base.endswith("/v1") else base + "/v1/models"
    try:
        r = requests.get(
            models_url,
            headers={"Authorization": f"Bearer {key}", "Accept": "application/json"},
            timeout=TIMEOUT,
        )
    except requests.RequestException as e:
        return {"models": [], "error": f"网络错误: {e.__class__.__name__}"}
    if r.status_code in (401, 403):
        return {"models": [], "error": f"key 无效 (HTTP {r.status_code})"}
    if r.status_code == 404:
        return {"models": [], "error": "该 provider 无 /v1/models 端点"}
    if r.status_code != 200:
        return {"models": [], "error": f"HTTP {r.status_code}"}
    try:
        body = r.json()
    except ValueError:
        return {"models": [], "error": "响应非 JSON"}

    raw = body.get("data") if isinstance(body, dict) else body
    if not isinstance(raw, list):
        return {"models": [], "error": "响应结构未识别"}

    models = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        mid = item.get("id") or item.get("name") or item.get("model")
        if not mid:
            continue
        models.append({
            "id": mid,
            "owned_by": item.get("owned_by"),
            "context": item.get("context_length"),
        })
    return {"models": models, "error": None}


def fetch(entry):
    """主入口:探测 quota endpoint,返回标准 result dict。"""
    base = (entry.get("base_url") or "").rstrip("/")
    key = entry.get("api_key") or entry.get("key") or ""
    if not base:
        return {"error": "缺少 base_url", "unconfigured": True}
    if not key:
        return {"error": "缺少 key", "unconfigured": True}

    headers = {"Authorization": f"Bearer {key}", "Accept": "application/json"}
    errors = []
    parsed = None

    for label, path, parser_name in QUOTA_PROBES:
        try:
            r = requests.get(base + path, headers=headers, timeout=TIMEOUT)
        except requests.RequestException as e:
            errors.append(f"{label}: {e.__class__.__name__}")
            continue
        if r.status_code in (401, 403):
            return {"error": f"key 无效 (HTTP {r.status_code})"}
        if r.status_code != 200:
            errors.append(f"{label}: HTTP {r.status_code}")
            continue
        try:
            body = r.json()
        except ValueError:
            errors.append(f"{label}: 非JSON")
            continue
        result = _PARSERS[parser_name](body)
        if result:
            result["quota_endpoint"] = path
            parsed = result
            break
        errors.append(f"{label}: 结构未识别")

    if not parsed:
        return {"error": "; ".join(errors[:3])}

    models_result = fetch_models(entry)
    if not models_result.get("error"):
        parsed["models"] = [m["id"] for m in models_result["models"]]
        parsed["models_count"] = len(parsed["models"])

    parsed.setdefault("detail", "")
    parsed["detail"] = f"[{parsed['quota_endpoint']}] {parsed['detail']}".strip()
    return parsed


@_parser("_parse_openai_billing")
def _parse_openai_billing(body):
    if not isinstance(body, dict):
        return None
    try:
        granted = float(body.get("total_granted") or body.get("granted_amount") or 0)
        used = float(body.get("total_used_amount") or 0)
        available = float(body.get("total_available") or 0)
    except (TypeError, ValueError):
        return None
    if granted <= 0 and available <= 0:
        return None
    return {
        "remaining": available,
        "used": used,
        "total": granted,
        "unit": "$",
        "pct": available / granted * 100 if granted > 0 else None,
        "detail": f"已用 ${used:.2f} · 总额 ${granted:.2f}",
        "is_estimate": False,
    }


@_parser("_parse_openai_subscription")
def _parse_openai_subscription(body):
    if not isinstance(body, dict) or "data" not in body:
        return None
    data = body["data"]
    if not isinstance(data, dict):
        return None
    try:
        limit = float(data.get("hard_limit_usd") or 0)
    except (TypeError, ValueError):
        return None
    if limit <= 0:
        return None
    try:
        used = float(data.get("usage") or 0)
    except (TypeError, ValueError):
        used = 0
    remaining = max(0.0, limit - used)
    return {
        "remaining": remaining,
        "used": used,
        "total": limit,
        "unit": "$",
        "pct": remaining / limit * 100,
        "detail": f"已用 ${used:.2f} · 额度 ${limit:.2f}",
        "is_estimate": False,
    }


@_parser("_parse_deepseek_balance")
def _parse_deepseek_balance(body):
    if not isinstance(body, dict):
        return None
    infos = body.get("balance_infos")
    if not isinstance(infos, list) or not infos:
        return None
    info = infos[0]
    if not isinstance(info, dict):
        return None
    currency = info.get("currency", "CNY")
    sym = "$" if currency == "USD" else ("¥" if currency == "CNY" else currency + " ")
    try:
        total = float(info.get("total_balance") or 0)
        granted = float(info.get("granted_balance") or 0)
        topped = float(info.get("topped_up_balance") or 0)
    except (TypeError, ValueError):
        return None
    return {
        "remaining": total,
        "used": None,
        "total": None,
        "unit": sym,
        "pct": None,
        "detail": f"赠金 {sym}{granted:.2f} · 充值 {sym}{topped:.2f}",
        "is_estimate": False,
    }


@_parser("_parse_new_api_self")
def _parse_new_api_self(body):
    if not isinstance(body, dict):
        return None
    data = body.get("data") if isinstance(body.get("data"), dict) else body
    quota = data.get("quota")
    if quota is None:
        return None
    try:
        quota = float(quota)
        used = float(data.get("used_quota") or 0)
        per_usd = float(data.get("quota_per_usd") or 500000)
    except (TypeError, ValueError):
        return None
    remaining = quota / per_usd
    used_usd = used / per_usd
    total = remaining + used_usd
    return {
        "remaining": remaining,
        "used": used_usd,
        "total": total,
        "unit": "$",
        "pct": remaining / total * 100 if total > 0 else None,
        "detail": f"剩余 ${remaining:.2f} · 已用 ${used_usd:.2f}",
        "is_estimate": False,
    }
