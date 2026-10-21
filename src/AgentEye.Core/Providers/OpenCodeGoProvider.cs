namespace AgentEye.Core.Providers;

/// <summary>
/// OpenCode Go(zen/go)订阅额度(端口自 opencode_go.py)。
///
/// percent 字段按"剩余"解读——与 remaining 字段名、_level 的 pct&lt;=warn
/// 告警方向、面板主值"已用 100-pct"保持一致。WINDOWS 里的 $12/$30/$60
/// 是硬编码的订阅档位额度:换档后金额会不准,is_estimate=True 就是
/// 为此留下的免责标记。
/// </summary>
public static class OpenCodeGoProvider
{
    // 候选端点:按顺序尝试,404/405/501 才换下一个。UI 预设里填的
    // base_url 不带 /zen/go,拼出来的是 https://opencode.ai/v1/usage(404),
    // 所以必须留一条回退到正确路径。
    private static readonly string[] UrlVariants = ["https://opencode.ai/zen/go/v1/usage"];

    private static readonly (string Key, string Label, double Limit)[] Windows =
    [
        ("rolling", "5h", 12.0),
        ("weekly", "周", 30.0),
        ("monthly", "月", 60.0),
    ];

    /// <summary>percent 视为 0-100 的剩余百分比,钳到 [0,100]。</summary>
    private static double? NormPct(double? v) => v is null
        ? null : Math.Clamp(v.Value, 0.0, 100.0);

    private static List<string> UsageUrls(string? bas)
    {
        bas = bas?.TrimEnd('/');
        var urls = new List<string>();
        if (!string.IsNullOrEmpty(bas))
            urls.Add(bas.EndsWith("/usage") ? bas : bas + "/v1/usage");
        foreach (var u in UrlVariants)
            if (!urls.Contains(u))
                urls.Add(u);
        return urls;
    }

    public static async Task<FetchPayload> FetchAsync(
        GenericOpenAi.LegacyEntry e, CancellationToken ct = default)
    {
        var key = e.ApiKey ?? "";
        if (key.Length == 0)
            return FetchPayload.Err("未配置 api_key", unconfigured: true);

        var headers = new Dictionary<string, string>
        {
            ["Authorization"] = $"Bearer {key}",
            ["Accept"] = "application/json",
        };
        System.Text.Json.JsonElement body = default;
        var haveBody = false;
        var lastStatus = 0;
        var urls = UsageUrls(e.BaseUrl);
        for (var i = 0; i < urls.Count; i++)
        {
            var (ok, status, respBody) = await Http.GetJsonAsync(
                urls[i], headers, Http.DefaultTimeoutSec, ct);
            if (!ok) return FetchPayload.Err("网络错误: 网络异常");
            if (status == 401)
                // 鉴权层拒绝与路径无关,不需要回退
                return FetchPayload.Err("key 无效 (HTTP 401)");
            if (status == 200)
            {
                body = respBody;
                haveBody = true;
                break;
            }
            lastStatus = status;
            var isLast = i + 1 >= urls.Count;
            // 404/405/501 = 端点不存在,换下一个候选。403 只在末位(已知
            // 正确的)端点上判 key 无效:WAF 对猜测路径返回 403 很常见
            var retryable = lastStatus is 404 or 405 or 501 or 403 && !isLast;
            if (isLast || !retryable) break;
        }
        if (!haveBody)
        {
            if (lastStatus == 403) return FetchPayload.Err("key 无效 (HTTP 403)");
            return FetchPayload.Err($"HTTP {lastStatus}");
        }
        if (!Http.IsObj(body)) return FetchPayload.Err("响应非 JSON");

        var usageEl = Http.Obj(body, "usage");
        var usage = usageEl is { } u && u.ValueKind == System.Text.Json.JsonValueKind.Object
            ? u : body;
        var parts = new List<string>();
        var pcts = new List<double>();
        var resets = new List<string>();
        foreach (var (wkey, label, limit) in Windows)
        {
            var wEl = Http.Obj(usage, wkey);
            if (wEl is not { } w || w.ValueKind != System.Text.Json.JsonValueKind.Object)
                continue;
            var p = NormPct(Http.Num(w, "percent"));
            if (p is null) continue;
            var amt = p.Value / 100.0 * limit;
            parts.Add($"{label} 剩≈${Http.F2(amt)}/${limit:F0}");
            pcts.Add(p.Value);
            var resetsAt = Http.Str(w, "resetsAt");
            if (resetsAt is not null) resets.Add(resetsAt);
        }

        if (pcts.Count == 0) return FetchPayload.Err("响应无窗口数据");

        double? monthlyAmt = null;
        var mEl = Http.Obj(usage, "monthly");
        if (mEl is { } m && m.ValueKind == System.Text.Json.JsonValueKind.Object &&
            NormPct(Http.Num(m, "percent")) is { } mp)
            monthlyAmt = mp / 100.0 * 60.0;

        var resetNote = "";
        if (resets.Count > 0) resetNote = $" · 重置 {IsoIn(resets[0])}";

        // used 必须回填:面板胶囊的长度/颜色吃 used/total。percent 按
        // "剩余"解读,monthly_amt 是"月窗口剩余换算",已用就是 60 - 月剩余。
        double? usedMonthly = monthlyAmt is null ? null : Math.Max(0.0, 60.0 - monthlyAmt.Value);

        return new FetchPayload
        {
            Remaining = monthlyAmt,
            Used = usedMonthly,
            Total = 60.0,
            Unit = "$",
            Pct = pcts.Min(),
            Detail = string.Join(" · ", parts) + resetNote,
            IsEstimate = true,
        };
    }

    private static string IsoIn(string isoStr)
    {
        if (!DateTimeOffset.TryParse(
                isoStr.Replace("Z", "+00:00"),
                System.Globalization.CultureInfo.InvariantCulture,
                System.Globalization.DateTimeStyles.None,
                out var dt))
            return "?";
        var sec = (long)(dt - DateTimeOffset.UtcNow).TotalSeconds;
        if (sec <= 0) return "已重置";
        var h = sec / 3600;
        var m = sec % 3600 / 60;
        return h > 0 ? $"{h}h{m:D2}m" : $"{m}m";
    }
}
