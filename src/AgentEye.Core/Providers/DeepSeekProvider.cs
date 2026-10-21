namespace AgentEye.Core.Providers;

/// <summary>DeepSeek 官方余额(端口自 deepseek.py)。</summary>
public static class DeepSeekProvider
{
    private static readonly Dictionary<string, string> Symbols = new()
    { ["CNY"] = "¥", ["USD"] = "$" };

    public static async Task<FetchPayload> FetchAsync(
        GenericOpenAi.LegacyEntry e, CancellationToken ct = default)
    {
        var bas = string.IsNullOrEmpty(e.BaseUrl)
            ? "https://api.deepseek.com" : e.BaseUrl.TrimEnd('/');
        // OpenAI 兼容客户端习惯填 https://api.deepseek.com/v1,而余额端点
        // 挂在根路径下,带 /v1 会 404
        if (bas.EndsWith("/v1")) bas = bas[..^3];
        var key = e.ApiKey ?? "";
        if (key.Length == 0)
            return FetchPayload.Err("未配置 api_key", unconfigured: true);

        var (ok, status, body) = await Http.GetJsonAsync(bas + "/user/balance",
            new Dictionary<string, string>
            {
                ["Authorization"] = $"Bearer {key}",
                ["Accept"] = "application/json",
            }, Http.DefaultTimeoutSec, ct);
        if (!ok) return FetchPayload.Err("网络错误: 网络异常");
        if (status is 401 or 403) return FetchPayload.Err($"key 无效 (HTTP {status})");
        if (status != 200) return FetchPayload.Err($"HTTP {status}");
        if (!Http.IsObj(body)) return FetchPayload.Err("响应非 JSON");

        var infos = Http.Arr(body, "balance_infos");
        if (infos is not { Count: > 0 }) return FetchPayload.Err("响应无 balance_infos");
        if (!Http.IsObj(infos[0])) return FetchPayload.Err("响应无 balance_infos");
        var info = infos[0];
        var currency = Http.Str(info, "currency") ?? "CNY";
        var sym = Symbols.GetValueOrDefault(currency, currency + " ");
        var total = Http.Num(info, "total_balance") ?? 0;
        var granted = Http.Num(info, "granted_balance") ?? 0;
        var topped = Http.Num(info, "topped_up_balance") ?? 0;

        // is_available:缺省视为可用;显式 false/0 视为不可用
        var available = !body.TryGetProperty("is_available", out var av) || av.ValueKind switch
        {
            System.Text.Json.JsonValueKind.False => false,
            System.Text.Json.JsonValueKind.True => true,
            System.Text.Json.JsonValueKind.Number => av.GetDouble() != 0,
            System.Text.Json.JsonValueKind.String => (av.GetString()?.Length ?? 0) > 0,
            _ => true,
        };
        var detail = $"赠金 {sym}{Http.F2(granted)} · 充值 {sym}{Http.F2(topped)}";
        if (!available) detail += " · 余额不可用";

        return new FetchPayload
        {
            Remaining = total,
            Used = null,
            Total = null,
            Unit = sym,
            Pct = null,
            Detail = detail,
            IsEstimate = false,
        };
    }
}
