"""多 provider 总额度聚合。

将不同 unit 的 provider 归一化到 USD,计算总额度 / 已用 / 进度。
"""

# 各 provider kind 的"月度上限 USD 估值"(用于订阅类 % 转换为金额)
MONTHLY_CAP_USD = {
    "minimax": 50.0,
    "opencode_go": 60.0,
    "zhipu": 30.0,
}

LEVEL_RANK = {"ok": 0, "warn": 1, "critical": 2, "error": 3, "unconfigured": 0, "unknown": 0}


def _normalize_to_usd(result, rate_cny_per_usd=7.2):
    """将单个 result 归一化到 USD。返回 (remaining_usd, used_usd, total_usd) 或 None。"""
    unit = result.get("unit") or ""
    rem = result.get("remaining")
    used = result.get("used")
    total = result.get("total")

    if unit == "$":
        return (rem or 0, used or 0, total or 0) if rem is not None else None
    if unit == "¥":
        if rem is None:
            return None
        return (rem / rate_cny_per_usd, (used or 0) / rate_cny_per_usd,
                (total or 0) / rate_cny_per_usd)
    if unit == "%":
        pct = result.get("pct")
        if pct is None:
            return None
        kind = result.get("type") or result.get("kind") or ""
        cap = MONTHLY_CAP_USD.get(kind, 30.0)
        remaining_usd = cap * pct / 100.0
        used_usd = cap - remaining_usd
        return (remaining_usd, used_usd, cap)
    if unit == "额度":
        if rem is None:
            return None
        return (rem, used or 0, total or 0)
    return None


def compute(results, cfg=None):
    """聚合计算。

    Returns:
        dict: {
            total_usd, used_usd, total_budget_usd, pct,
            level, breakdown: [...], providers_with_data: int
        }
    """
    cfg = cfg or {}
    agg_cfg = cfg.get("aggregate") or {}
    rate = float(agg_cfg.get("currency_rate_cny_per_usd", 7.2))
    budget = float(agg_cfg.get("monthly_budget_usd", 0) or 0)

    total_usd = 0.0
    used_usd = 0.0
    worst_level = "ok"
    breakdown = []
    with_data = 0

    for r in results or []:
        norm = _normalize_to_usd(r, rate)
        if norm is None:
            continue
        r_usd, u_usd, t_usd = norm
        total_usd += r_usd
        used_usd += u_usd
        with_data += 1
        breakdown.append({
            "name": r.get("name", "?"),
            "kind": r.get("type") or r.get("kind") or "",
            "remaining_usd": r_usd,
            "used_usd": u_usd,
            "total_usd": t_usd,
            "level": r.get("level", "unknown"),
            "unit": r.get("unit", ""),
        })
        rank = LEVEL_RANK.get(r.get("level", "ok"), 0)
        if rank > LEVEL_RANK.get(worst_level, 0):
            worst_level = r.get("level", "ok")

    breakdown.sort(key=lambda b: b["remaining_usd"], reverse=True)

    pct = None
    level = worst_level
    if budget > 0:
        pct = total_usd / budget * 100
        if pct <= 5:
            budget_level = "critical"
        elif pct <= 20:
            budget_level = "warn"
        else:
            budget_level = "ok"
        if LEVEL_RANK.get(budget_level, 0) > LEVEL_RANK.get(level, 0):
            level = budget_level

    return {
        "total_usd": total_usd,
        "used_usd": used_usd,
        "total_budget_usd": budget,
        "pct": pct,
        "level": level,
        "breakdown": breakdown,
        "providers_with_data": with_data,
        "enabled": agg_cfg.get("enabled", True),
    }
