using System.Collections.Concurrent;

namespace AgentEye.Core.Providers;

/// <summary>
/// 中转站适配器(端口自 relay.py):按候选端点逐个探测,支持
/// 静态 token 或 email/password 登录(带 token 缓存与 401 重登)。
/// </summary>
public static class RelayProvider
{
    private const double QuotaPerUsdDefault = 500000.0;
    private const string LoginPath = "/api/v1/auth/login";

    private static readonly (string Kind, string Path)[] Candidates =
    [
        ("new_api", "/api/user/self"),
        ("key_usage", "/v1/usage"),
        ("v1_usage", "/api/v1/usage"),
        ("v1_keys", "/api/v1/keys"),
        ("v1_subs", "/api/v1/subscriptions/summary"),
        ("v1_me", "/api/v1/auth/me"),
    ];

    private static readonly string[] RemainingKeys =
        ["balance", "remaining", "remain", "total_balance", "credit", "credits", "left", "quota"];
    private static readonly string[] UsedKeys =
        ["used_quota", "used", "usage_count", "consumed", "total_used", "usage"];
    private static readonly string[] TotalKeys =
        ["total", "limit", "total_quota", "monthly_limit", "max"];

    private static readonly ConcurrentDictionary<(string Base, string Email), (string Token, double Expiry)>
        TokenCache = new();
    private static readonly object TokenLock = new();

    private static (string Base, string Email) CacheKey(string bas, string email) => (bas, email);

    // 同一站点可以挂多个账号;只按 base 缓存会让两个账号共用同一 token
    private static async Task<(string? Token, string? Err)> GetAccessToken(
        string bas, string email, string password, CancellationToken ct)
    {
        var key = CacheKey(bas, email);
        lock (TokenLock)
        {
            if (TokenCache.TryGetValue(key, out var cached) && cached.Expiry > Http.Now())
                return (cached.Token, null);
        }
        var (ok, status, body) = await Http.PostJsonAsync(bas + LoginPath,
            new Dictionary<string, object?> { ["email"] = email, ["password"] = password },
            Http.DefaultTimeoutSec, ct);
        if (!ok) return (null, "网络异常");
        if (status != 200) return (null, $"HTTP {status}");
        if (body is not { ValueKind: System.Text.Json.JsonValueKind.Object } b)
            return (null, "响应非JSON");
        var token = Http.Str(b, "access_token");
        if (string.IsNullOrEmpty(token)) return (null, "响应无 access_token");
        var ttl = Http.Num(b, "expires_in") ?? 3600;
        lock (TokenLock)
        {
            TokenCache[key] = (token, Http.Now() + Math.Max(60.0, ttl - 60.0));
        }
        return (token, null);
    }

    public static async Task<FetchPayload> FetchAsync(
        GenericOpenAi.LegacyEntry e, CancellationToken ct = default)
    {
        var bas = (e.BaseUrl ?? "").TrimEnd('/');
        var token = e.Raw.TryGetValue("token", out var t) && t is string ts ? ts : "";
        var email = e.Raw.TryGetValue("email", out var em) && em is string ems ? ems : "";
        var password = e.Raw.TryGetValue("password", out var pw) && pw is string pws ? pws : "";
        if (bas.Length == 0 || (token.Length == 0 && (email.Length == 0 || password.Length == 0)))
            return FetchPayload.Err("未配置 base_url/token", unconfigured: true);

        var extraHeaders = new Dictionary<string, string>();
        if (e.Raw.TryGetValue("headers", out var h) && h is Dictionary<string, object?> hd)
            foreach (var (k, v) in hd)
                if (v is not null)
                    extraHeaders[k] = v.ToString() ?? "";
        if (e.Raw.TryGetValue("new_api_user_id", out var uid) && uid is not null)
            extraHeaders["New-Api-User"] = uid.ToString() ?? "";

        var errors = new List<string>();
        var useAccessToken = email.Length > 0 && password.Length > 0;
        var relogged = false;

        while (true)
        {
            var authToken = token;
            if (useAccessToken)
            {
                var (tok, err) = await GetAccessToken(bas, email, password, ct);
                if (tok is null)
                {
                    if (token.Length > 0)
                    {
                        // 登录接口挂了/改版了,但静态 token 还在:降级用它
                        useAccessToken = false;
                        authToken = token;
                    }
                    else
                    {
                        return FetchPayload.Err($"登录失败: {err}");
                    }
                }
                else
                {
                    authToken = tok;
                }
            }

            var headers = new Dictionary<string, string>
            {
                ["Authorization"] = $"Bearer {authToken}",
                ["Accept"] = "application/json",
            };
            foreach (var (k, v) in extraHeaders) headers[k] = v;

            var saw401 = false;
            var loopBroken = false;
            foreach (var (kind, path) in Candidates)
            {
                if (useAccessToken && kind == "new_api") continue;
                var (ok, status, body) = await Http.GetJsonAsync(
                    bas + path, headers, Http.DefaultTimeoutSec, ct);
                if (!ok)
                {
                    errors.Add($"{path}: 网络异常");
                    continue;
                }
                if (status == 401 && useAccessToken && !relogged)
                {
                    lock (TokenLock)
                    {
                        TokenCache.TryRemove(CacheKey(bas, email), out _);
                    }
                    relogged = true;
                    loopBroken = true;
                    break;
                }
                if (status == 401)
                {
                    // 静态 token / 重登后仍 401:记住,最后统一给"key 无效"
                    saw401 = true;
                    errors.Add($"{path}: HTTP 401");
                    continue;
                }
                if (status != 200)
                {
                    errors.Add($"{path}: HTTP {status}");
                    continue;
                }
                if (!Http.IsObj(body))
                {
                    errors.Add($"{path}: 非JSON");
                    continue;
                }
                var parsed = Parse(kind, body, e);
                if (parsed is not null)
                {
                    if (parsed.Error is not null)
                        // _parse 主动给出的结论(如 key 无效)直接透传
                        return parsed;
                    parsed.Detail = $"[{path}] {parsed.Detail ?? ""}".Trim();
                    return parsed;
                }
                errors.Add($"{path}: 结构未识别");
            }
            if (!loopBroken)
            {
                if (saw401) return FetchPayload.Err("key 无效 (HTTP 401)");
                return FetchPayload.Err(string.Join("; ", errors.Take(3)));
            }
            // relogged → continue 外层 while
        }
    }

    private static FetchPayload? Parse(string kind, System.Text.Json.JsonElement body,
        GenericOpenAi.LegacyEntry e) =>
        kind switch
        {
            "new_api" => ParseNewApi(body, e),
            "key_usage" => ParseKeyUsage(body, e),
            _ => ParseGeneric(body, e),
        };

    private static FetchPayload? ParseKeyUsage(System.Text.Json.JsonElement body,
        GenericOpenAi.LegacyEntry e)
    {
        if (!Http.IsObj(body)) return null;
        if (Http.Obj(body, "isValid") is { ValueKind: System.Text.Json.JsonValueKind.False })
            // 端点明确说 key 无效:直接给结论
            return FetchPayload.Err("key 无效 (isValid=false)");
        var remainingRaw = Http.Num(body, "balance") ?? Http.Num(body, "remaining");
        if (remainingRaw is null) return null;
        var remaining = remainingRaw.Value;
        var unitField = (Http.Str(body, "unit") ?? "USD").ToUpperInvariant();
        var sym = unitField.Contains("USD") ? "$" : unitField.Contains("CNY") ? "¥" : "额度";
        var usage = Http.Obj(body, "usage") is { ValueKind: System.Text.Json.JsonValueKind.Object }
            ? Http.Obj(body, "usage")!.Value : default;
        var today = Http.Obj(usage, "today") is { ValueKind: System.Text.Json.JsonValueKind.Object }
            ? Http.Obj(usage, "today")!.Value : default;
        var total = Http.Obj(usage, "total") is { ValueKind: System.Text.Json.JsonValueKind.Object }
            ? Http.Obj(usage, "total")!.Value : default;
        var parts = new List<string>();
        var hasToday = Http.IsObj(today);
        if (hasToday)
        {
            var cost = Http.Num(today, "actual_cost") ?? Http.Num(today, "cost");
            if (cost is not null) parts.Add($"今日 {sym}{Http.F2(cost.Value)}");
            if (Http.Num(today, "requests") is { } reqs)
                parts.Add($"{(long)reqs} 次");
        }
        double? used = null;
        if (Http.IsObj(total))
        {
            used = Http.Num(total, "actual_cost") ?? Http.Num(total, "cost");
            if (used is not null) parts.Add($"累计实付 {sym}{Http.F2(used.Value)}");
        }
        double? usedToday = null;
        if (hasToday)
        {
            var tcost = Http.Num(today, "actual_cost") ?? Http.Num(today, "cost");
            if (tcost is not null) usedToday = tcost;
        }
        var plan = Http.Str(body, "planName");
        if (plan is not null) parts.Add(plan);
        return new FetchPayload
        {
            Remaining = remaining,
            Used = used,
            UsedToday = usedToday,
            Total = null,
            Unit = sym,
            Pct = null,
            Detail = string.Join(" · ", parts),
            IsEstimate = false,
        };
    }

    private static FetchPayload? ParseNewApi(System.Text.Json.JsonElement body,
        GenericOpenAi.LegacyEntry e)
    {
        if (!Http.IsObj(body)) return null;
        if (Http.Obj(body, "success") is { ValueKind: System.Text.Json.JsonValueKind.False })
            return null;
        var data = Http.Obj(body, "data") is { ValueKind: System.Text.Json.JsonValueKind.Object }
            ? Http.Obj(body, "data")!.Value : body;
        if (Http.Num(data, "quota") is not { } quota) return null;
        var used = Http.Num(data, "used_quota") ?? 0;
        var perUsd = e.Raw.TryGetValue("quota_per_usd", out var qpu) && qpu is not null
            ? Convert.ToDouble(qpu) : QuotaPerUsdDefault;
        var remaining = quota / perUsd;
        var usedUsd = used / perUsd;
        var total = remaining + usedUsd;
        return new FetchPayload
        {
            Remaining = remaining,
            Used = usedUsd,
            UsedToday = null,
            Total = total,
            Unit = "$",
            Pct = total > 0 ? remaining / total * 100 : null,
            Detail = $"剩余 ${Http.F2(remaining)} · 已用 ${Http.F2(usedUsd)}",
            IsEstimate = false,
        };
    }

    private static FetchPayload? ParseGeneric(System.Text.Json.JsonElement body,
        GenericOpenAi.LegacyEntry e)
    {
        if (body.ValueKind is not (System.Text.Json.JsonValueKind.Object
                or System.Text.Json.JsonValueKind.Array))
            return null;
        // 多 key 站点的 {"success":true,"data":[...]} 包装在这里是
        // "单元素 items 套 list":用 DeepCount 聚合全部命中
        var keyCount = DeepCount(body, RemainingKeys, 0);
        if (keyCount <= 0) return null;
        var sumRemaining = DeepSum(body, RemainingKeys, 0);
        var sumUsed = DeepSum(body, UsedKeys, 0);
        var sumTotal = DeepSum(body, TotalKeys, 0);
        double? perUsd = null;
        try
        {
            perUsd = e.Raw.TryGetValue("quota_per_usd", out var qpu) && qpu is not null
                ? Convert.ToDouble(qpu) : 0;
        }
        catch { perUsd = null; }
        if (perUsd is > 0)
        {
            sumRemaining /= perUsd.Value;
            sumUsed /= perUsd.Value;
            sumTotal /= perUsd.Value;
            const string unit = "$";
            string detail;
            if (sumTotal > 0)
                detail = $"剩余 ${Http.N2(sumRemaining)}"
                         + (keyCount > 1 ? $" · {keyCount} 个 key" : "")
                         + $" · 总量 ${Http.N2(sumTotal)}";
            else
                detail = $"剩余 ${Http.N2(sumRemaining)}"
                         + (keyCount > 1 ? $" · {keyCount} 个 key" : "");
            if (sumTotal > 0)
                return new FetchPayload
                {
                    Remaining = sumRemaining, Used = sumUsed > 0 ? sumUsed : null,
                    UsedToday = null, Total = sumTotal, Unit = unit,
                    Pct = sumRemaining / sumTotal * 100, Detail = detail, IsEstimate = true,
                };
            return new FetchPayload
            {
                Remaining = sumRemaining, Used = sumUsed > 0 ? sumUsed : null,
                UsedToday = null, Total = null, Unit = unit,
                Pct = null, Detail = detail, IsEstimate = true,
            };
        }
        var unitRaw = e.Raw.TryGetValue("unit", out var u) && u is string us && us.Length > 0
            ? us : "额度";
        var detailPlain = $"剩余 {Http.N2(sumRemaining)}{unitRaw}";
        if (keyCount > 1) detailPlain += $" · {keyCount} 个 key";
        if (sumTotal > 0) detailPlain += $" · 总量 {Http.N2(sumTotal)}";
        if (sumTotal > 0)
            return new FetchPayload
            {
                Remaining = sumRemaining, Used = sumUsed > 0 ? sumUsed : null,
                UsedToday = null, Total = sumTotal, Unit = unitRaw,
                Pct = sumRemaining / sumTotal * 100, Detail = detailPlain, IsEstimate = true,
            };
        return new FetchPayload
        {
            Remaining = sumRemaining, Used = sumUsed > 0 ? sumUsed : null,
            UsedToday = null, Total = null, Unit = unitRaw,
            Pct = null, Detail = detailPlain, IsEstimate = true,
        };
    }

    private static double? DeepFind(System.Text.Json.JsonElement obj, string[] keys, int depth)
    {
        if (depth > 6) return null;
        if (obj.ValueKind == System.Text.Json.JsonValueKind.Object)
        {
            if (Http.Obj(obj, "data") is { } d &&
                d.ValueKind is System.Text.Json.JsonValueKind.Object
                    or System.Text.Json.JsonValueKind.Array)
            {
                var hit = DeepFind(d, keys, depth + 1);
                if (hit is not null) return hit;
            }
            foreach (var k in keys)
            {
                if (Http.Num(obj, k) is { } v) return v;
            }
            foreach (var prop in obj.EnumerateObject())
            {
                if (prop.Value.ValueKind == System.Text.Json.JsonValueKind.Object)
                {
                    var hit = DeepFind(prop.Value, keys, depth + 1);
                    if (hit is not null) return hit;
                }
            }
        }
        else if (obj.ValueKind == System.Text.Json.JsonValueKind.Array)
        {
            foreach (var item in obj.EnumerateArray().Take(20))
            {
                var hit = DeepFind(item, keys, depth + 1);
                if (hit is not null) return hit;
            }
        }
        return null;
    }

    private static double DeepSum(System.Text.Json.JsonElement obj, string[] keys, int depth)
    {
        if (depth > 6) return 0.0;
        var total = 0.0;
        if (obj.ValueKind == System.Text.Json.JsonValueKind.Object)
        {
            if (Http.Obj(obj, "data") is { } d &&
                d.ValueKind is System.Text.Json.JsonValueKind.Object
                    or System.Text.Json.JsonValueKind.Array)
                total += DeepSum(d, keys, depth + 1);
            foreach (var k in keys)
            {
                if (Http.Num(obj, k) is { } v)
                {
                    total += v;
                    break;
                }
            }
            foreach (var prop in obj.EnumerateObject())
            {
                if (prop.Value.ValueKind == System.Text.Json.JsonValueKind.Object)
                    total += DeepSum(prop.Value, keys, depth + 1);
            }
        }
        else if (obj.ValueKind == System.Text.Json.JsonValueKind.Array)
        {
            foreach (var item in obj.EnumerateArray().Take(50))
                total += DeepSum(item, keys, depth + 1);
        }
        return total;
    }

    private static int DeepCount(System.Text.Json.JsonElement obj, string[] keys, int depth)
    {
        if (depth > 6) return 0;
        if (obj.ValueKind == System.Text.Json.JsonValueKind.Array)
            return obj.EnumerateArray().Take(50)
                .Count(el => DeepFind(el, keys, 0) is not null);
        if (obj.ValueKind == System.Text.Json.JsonValueKind.Object)
        {
            if (Http.Obj(obj, "data") is { } d &&
                d.ValueKind is System.Text.Json.JsonValueKind.Object
                    or System.Text.Json.JsonValueKind.Array)
            {
                var n = DeepCount(d, keys, depth + 1);
                if (n > 0) return n;
            }
            return DeepFind(obj, keys, 0) is not null ? 1 : 0;
        }
        return 0;
    }
}
