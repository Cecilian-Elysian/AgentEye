namespace AgentEye.Core.Providers;

/// <summary>智谱 GLM 额度窗口(端口自 zhipu.py)。</summary>
public static class ZhipuProvider
{
    private const string DefaultBase = "https://open.bigmodel.cn";
    private const string Path = "/api/monitor/usage/quota/limit";

    private static readonly Dictionary<(int Unit, int Number), string> WindowLabels = new()
    {
        [(3, 5)] = "5h",
        [(6, 1)] = "周",
    };

    private static string? FmtResetAbs(double? ms)
    {
        if (ms is null) return null;
        var sec = (long)(ms.Value / 1000) - (long)Http.Now();
        if (sec <= 0) return null;
        var d = sec / 86400;
        var rest = sec % 86400;
        var h = rest / 3600;
        var m = rest % 3600 / 60;
        if (d > 0) return $"{d}d{h:D2}h";
        if (h > 0) return $"{h}h{m:D2}m";
        return $"{m}m";
    }

    public static async Task<FetchPayload> FetchAsync(
        GenericOpenAi.LegacyEntry e, CancellationToken ct = default)
    {
        var key = e.ApiKey ?? "";
        if (key.Length == 0)
            return FetchPayload.Err("未配置 api_key", unconfigured: true);

        var bas = string.IsNullOrEmpty(e.BaseUrl) ? DefaultBase : e.BaseUrl.TrimEnd('/');
        var (ok, status, body) = await Http.GetJsonAsync(bas + Path,
            new Dictionary<string, string>
            {
                // 智谱这一端点用裸 key,不带 Bearer 前缀
                ["Authorization"] = key,
                ["Accept"] = "application/json",
            }, Http.DefaultTimeoutSec, ct);
        if (!ok) return FetchPayload.Err("网络错误: 网络异常");
        if (status is 401 or 403) return FetchPayload.Err($"key 无效 (HTTP {status})");
        if (status != 200) return FetchPayload.Err($"HTTP {status}");
        if (!Http.IsObj(body)) return FetchPayload.Err("响应非 JSON");

        // 智谱个别网关把 code 回成字符串 "200",不能直接按数字比
        var code = Http.Obj(body, "code");
        var codeStr = code?.ValueKind switch
        {
            System.Text.Json.JsonValueKind.String => code.Value.GetString(),
            System.Text.Json.JsonValueKind.Number => code.Value.GetRawText(),
            _ => null,
        };
        var success = Http.Obj(body, "success") is { ValueKind: System.Text.Json.JsonValueKind.False };
        if ((codeStr is not null && codeStr != "200") || success)
            return FetchPayload.Err($"接口报错: {Http.Str(body, "msg") ?? codeStr ?? "?"}");

        var data = Http.Obj(body, "data") is { ValueKind: System.Text.Json.JsonValueKind.Object }
            ? Http.Obj(body, "data")!.Value : default;
        var limits = Http.Arr(data, "limits") ?? [];
        var tokenLimits = limits
            .Where(l => Http.IsObj(l)
                        && Http.Str(l, "type") == "TOKENS_LIMIT"
                        && Http.Num(l, "percentage") is not null)
            .ToList();
        if (tokenLimits.Count == 0) return FetchPayload.Err("无 token 额度窗口");

        var segs = new List<(double Rem, string Seg)>();
        foreach (var l in tokenLimits)
        {
            var unit = (int?)Http.Num(l, "unit") ?? 0;
            var number = (int?)Http.Num(l, "number") ?? 0;
            var label = WindowLabels.GetValueOrDefault((unit, number), $"{number}·u{unit}");
            var used = Http.Num(l, "percentage")!.Value;
            var rem = Math.Max(0.0, 100.0 - used);
            var seg = $"{label} 剩{Http.F0(rem)}%";
            var reset = FmtResetAbs(Http.Num(l, "nextResetTime"));
            if (reset is not null) seg += $"(重置{reset})";
            segs.Add((rem, seg));
        }

        // 主值 pct 取的是 min(各窗口剩余),detail 首段必须指向同一个窗口
        segs.Sort((a, b) => a.Rem.CompareTo(b.Rem));
        var remaining = segs.Select(t => t.Rem).ToList();
        var parts = segs.Select(t => t.Seg).ToList();

        var level = Http.Str(data, "level");
        var detail = string.Join(" · ", parts);
        if (level is not null) detail += $" · {level}套餐";

        return new FetchPayload
        {
            Remaining = null, Used = null, Total = null,
            Unit = "%", Pct = remaining.Min(), Detail = detail, IsEstimate = false,
        };
    }
}
