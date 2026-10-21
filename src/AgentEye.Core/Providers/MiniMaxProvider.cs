using System.Text.RegularExpressions;

namespace AgentEye.Core.Providers;

/// <summary>MiniMax 套餐额度(coding_plan / token_plan,端口自 minimax.py)。</summary>
public static partial class MiniMaxProvider
{
    private const string DefaultHost = "https://api.minimaxi.com";
    private const string CodingPath = "/v1/api/openplatform/coding_plan/remains";
    private const string TokenPath = "/v1/token_plan/remains";

    private static readonly string[] IntervalKeys =
    [
        "current_interval_remaining_percent", "interval_remaining_percent",
        "remaining_percent", "remains_percent",
    ];
    private static readonly string[] WeeklyKeys =
        ["current_weekly_remaining_percent", "weekly_remaining_percent"];
    private static readonly string[] TimeKeys = ["remains_time", "weekly_remains_time", "reset_time"];
    private static readonly string[] NameKeys = ["model_name", "model", "name"];
    private static readonly string[] ItemListKeys = ["model_remains", "remains", "models", "sub_remains"];

    [GeneratedRegex(@"^(https?://[^/]+)")]
    private static partial Regex HostRegex();

    private static string Host(GenericOpenAi.LegacyEntry e)
    {
        var bas = e.BaseUrl is { Length: > 0 } ? e.BaseUrl : DefaultHost;
        var m = HostRegex().Match(bas);
        return (m.Success ? m.Groups[1].Value : DefaultHost).TrimEnd('/');
    }

    private static double? NormPct(object? v) => v is null ? null
        : Math.Clamp(Convert.ToDouble(v), 0.0, 100.0);

    private static object? First(System.Text.Json.JsonElement item, string[] keys)
    {
        foreach (var k in keys)
        {
            var v = Http.Obj(item, k);
            if (v is { ValueKind: not System.Text.Json.JsonValueKind.Null })
                return v.Value.ValueKind switch
                {
                    System.Text.Json.JsonValueKind.String => v.Value.GetString(),
                    System.Text.Json.JsonValueKind.Number => v.Value.GetDouble(),
                    System.Text.Json.JsonValueKind.True => true,
                    System.Text.Json.JsonValueKind.False => false,
                    _ => null,
                };
        }
        return null;
    }

    private static List<System.Text.Json.JsonElement>? ExtractItems(System.Text.Json.JsonElement body)
    {
        var candidates = new List<System.Text.Json.JsonElement> { body };
        var dEl = Http.Obj(body, "data");
        if (dEl is { } d && d.ValueKind == System.Text.Json.JsonValueKind.Object)
            candidates.Add(d);
        foreach (var src in candidates)
            foreach (var k in ItemListKeys)
            {
                var v = Http.Arr(src, k);
                if (v is { Count: > 0 } && Http.IsObj(v[0])) return v;
            }
        return null;
    }

    private sealed record Item(string Name, double? Interval, double? Weekly,
        string? Reset, double? TotalN, double? UsedN);

    /// <summary>重置时间格式化:字段语义不统一(剩余毫秒 vs 绝对时间戳),按量级判别。</summary>
    private static string? FmtReset(object? value)
    {
        double v;
        try { v = Convert.ToDouble(value); }
        catch { return null; }
        if (v <= 0) return null;
        if (v >= 1e11) return FmtRemaining(v - Http.Now() * 1000.0);
        if (v is >= 1e9 and < 1e11)
            return FmtRemaining(v * 1000.0 - Http.Now() * 1000.0);
        return FmtRemaining(v);
    }

    private static string? FmtRemaining(double ms)
    {
        var sec = (long)(ms / 1000);
        if (sec <= 0) return null;
        var d = sec / 86400;
        var rest = sec % 86400;
        var h = rest / 3600;
        var m = rest % 3600 / 60;
        if (d > 0) return $"{d}d{h:D2}h";
        return h > 0 ? $"{h}h{m:D2}m" : $"{m}m";
    }

    public static async Task<FetchPayload> FetchAsync(
        GenericOpenAi.LegacyEntry e, CancellationToken ct = default)
    {
        var key = e.ApiKey ?? "";
        if (key.Length == 0)
            return FetchPayload.Err("未配置 api_key", unconfigured: true);

        var plan = e.Raw.TryGetValue("plan", out var p) && p is string ps &&
                   (ps == "coding_plan" || ps == "token_plan")
            ? ps
            : key.StartsWith("sk-cp-") ? "coding_plan" : "token_plan";
        var path = plan == "coding_plan" ? CodingPath : TokenPath;
        var url = Host(e) + path;

        var (ok, status, body) = await Http.GetJsonAsync(url,
            new Dictionary<string, string>
            {
                ["Authorization"] = $"Bearer {key}",
                ["Accept"] = "application/json",
            }, Http.DefaultTimeoutSec, ct);
        if (!ok) return FetchPayload.Err("网络错误: 网络异常");
        if (status is 401 or 403) return FetchPayload.Err($"key 无效 (HTTP {status})");
        if (status != 200) return FetchPayload.Err($"HTTP {status}");
        if (!Http.IsObj(body)) return FetchPayload.Err("响应非 JSON");

        // 接口级报错必须在解析 items 之前判:错误体里的残留字段会被当成
        // 正常数据。base_resp 偶尔回成非 dict(网关错误页),先收型再取。
        var baseResp = Http.Obj(body, "base_resp");
        var baseObj = baseResp is { } br && br.ValueKind == System.Text.Json.JsonValueKind.Object
            ? br : default;
        var statusCode = Http.IsObj(baseObj) ? Http.Num(baseObj, "status_code") : null;
        if (statusCode is not null && statusCode != 0)
        {
            var msg = Http.Str(baseObj, "status_msg") ?? statusCode.ToString();
            return FetchPayload.Err($"接口报错: {msg}");
        }

        var items = ExtractItems(body);
        if (items is null) return FetchPayload.Err("响应结构未识别");

        var parsed = new List<Item>();
        var skipped = 0;
        foreach (var it in items)
        {
            if (Http.Num(it, "current_interval_status") == 3 &&
                Http.Num(it, "current_weekly_status") == 3)
            {
                skipped++;
                continue;
            }
            var name = First(it, NameKeys)?.ToString() ?? "?";
            var interval = NormPct(First(it, IntervalKeys));
            var weekly = NormPct(First(it, WeeklyKeys));
            var reset = FmtReset(First(it, TimeKeys));
            parsed.Add(new Item(name, interval, weekly, reset,
                Http.Num(it, "current_interval_total_count"),
                Http.Num(it, "current_interval_usage_count")));
        }

        if (parsed.Count == 0)
            return FetchPayload.Err("套餐未启用或无可用额度项");

        var headline = parsed.FirstOrDefault(p => p.Name.Contains("general", StringComparison.OrdinalIgnoreCase))
                       ?? parsed[0];
        if (headline.Interval is null)
        {
            // general 项没有 5h 百分比时,退而取第一个有百分比的项
            var withPct = parsed.FirstOrDefault(p => p.Interval is not null);
            if (withPct is not null) headline = withPct;
        }
        var pct = headline.Interval;
        if (pct is null)
        {
            var percents = parsed.Where(p => p.Interval is not null)
                .Select(p => p.Interval!.Value).ToList();
            if (percents.Count == 0) return FetchPayload.Err("无百分比字段");
            pct = percents[0];
        }

        // headline 决定主值 pct 与重置时间,detail 首段必须就是它
        var ordered = new List<Item> { headline };
        ordered.AddRange(parsed.Where(p => !ReferenceEquals(p, headline)));
        var parts = new List<string>();
        foreach (var it in ordered.Take(3))
        {
            var seg = it.Name;
            if (it.TotalN is > 0)
            {
                try
                {
                    seg += $" {(long)it.TotalN - (long)(it.UsedN ?? 0)}/{(long)it.TotalN} 次";
                }
                catch
                {
                    seg += it.Interval is not null ? $" 5h {Http.F0(it.Interval.Value)}%" : "";
                }
            }
            else if (it.Interval is not null)
            {
                seg += $" 5h {Http.F0(it.Interval.Value)}%";
            }
            if (it.Weekly is not null) seg += $" · 周 {Http.F0(it.Weekly.Value)}%";
            parts.Add(seg);
        }
        if (parsed.Count > 3) parts.Add($"…共{parsed.Count}个模型");
        if (skipped > 0) parts.Add($"({skipped}项未启用)");
        var detail = string.Join(" | ", parts);
        if (headline.Reset is not null) detail += $" · 重置 {headline.Reset}";
        detail = $"[{plan}] " + detail;

        return new FetchPayload
        {
            Remaining = null, Used = null, Total = null,
            Unit = "%", Pct = pct, Detail = detail, IsEstimate = false,
        };
    }
}
