using System.Globalization;
using System.Text.Json;

namespace AgentEye.Core.Providers;

/// <summary>共享 HttpClient + 适配器用的 JSON/格式化小工具。</summary>
public static class Http
{
    public static readonly HttpClient Client = new(
        new SocketsHttpHandler { PooledConnectionLifetime = TimeSpan.FromMinutes(10) })
    {
        Timeout = Timeout.InfiniteTimeSpan, // 超时按请求用 CTS 控制
    };

    public const int DefaultTimeoutSec = 12;

    /// <summary>GET 并解析 JSON。网络层异常返回 (ok:false, 0, default)。</summary>
    public static async Task<(bool Ok, int Status, JsonElement Body)> GetJsonAsync(
        string url, IReadOnlyDictionary<string, string>? headers, int timeoutSec,
        CancellationToken ct = default)
    {
        try
        {
            using var cts = CancellationTokenSource.CreateLinkedTokenSource(ct);
            cts.CancelAfter(TimeSpan.FromSeconds(timeoutSec));
            using var req = new HttpRequestMessage(HttpMethod.Get, url);
            if (headers is not null)
                foreach (var (k, v) in headers)
                    req.Headers.TryAddWithoutValidation(k, v);
            using var resp = await Client.SendAsync(req,
                HttpCompletionOption.ResponseContentRead, cts.Token);
            if (!resp.IsSuccessStatusCode)
                return (true, (int)resp.StatusCode, default);
            var text = await resp.Content.ReadAsStringAsync(cts.Token);
            try
            {
                var doc = JsonDocument.Parse(text);
                return (true, 200, doc.RootElement.Clone());
            }
            catch (JsonException)
            {
                // 200 但响应非 JSON:让调用方按"非JSON"分支处理
                return (true, 200, JsonDocument.Parse("\"<not-json>\"").RootElement);
            }
        }
        catch (Exception e) when (
            e is HttpRequestException or TaskCanceledException
                or InvalidOperationException or SocketExceptionPlaceholder)
        {
            return (false, 0, default);
        }
    }

    /// <summary>内部占位:SocketException 在不同 TFM 上类型不同,统一按网络错。</summary>
    public sealed class SocketExceptionPlaceholder : Exception { }

    /// <summary>POST JSON 并解析(中转站登录)。</summary>
    public static Task<(bool Ok, int Status, JsonElement? Body)> PostJsonAsync(
        string url, object payload, int timeoutSec, CancellationToken ct = default) =>
        PostJsonAsync(url, null, payload, timeoutSec, ct);

    /// <summary>POST JSON 并解析,可带额外 headers(模型探测)。</summary>
    public static async Task<(bool Ok, int Status, JsonElement? Body)> PostJsonAsync(
        string url, Dictionary<string, string>? headers, object payload,
        int timeoutSec, CancellationToken ct = default)
    {
        try
        {
            using var cts = CancellationTokenSource.CreateLinkedTokenSource(ct);
            cts.CancelAfter(TimeSpan.FromSeconds(timeoutSec));
            using var req = new HttpRequestMessage(HttpMethod.Post, url);
            if (headers is not null)
                foreach (var (k, v) in headers)
                    req.Headers.TryAddWithoutValidation(k, v);
            req.Content = new StringContent(
                System.Text.Json.JsonSerializer.Serialize(payload),
                System.Text.Encoding.UTF8, "application/json");
            using var resp = await Client.SendAsync(req,
                HttpCompletionOption.ResponseContentRead, cts.Token);
            if (resp.StatusCode != System.Net.HttpStatusCode.OK)
                return (true, (int)resp.StatusCode, null);
            var text = await resp.Content.ReadAsStringAsync(cts.Token);
            try
            {
                return (true, 200, JsonDocument.Parse(text).RootElement.Clone());
            }
            catch (JsonException)
            {
                return (true, 200, null);
            }
        }
        catch (Exception e) when (
            e is HttpRequestException or TaskCanceledException or InvalidOperationException)
        {
            return (false, 0, null);
        }
    }

    // ------------------------------------------------------------------
    // JsonElement 取值小工具(带形状防御:手改响应/网关错误页都可能怪)
    // ------------------------------------------------------------------

    public static bool IsObj(JsonElement el) =>
        el.ValueKind == JsonValueKind.Object;

    public static JsonElement? Obj(JsonElement el, string key)
    {
        if (el.ValueKind != JsonValueKind.Object) return null;
        return el.TryGetProperty(key, out var v) ? v : null;
    }

    public static string? Str(JsonElement el, string key)
    {
        var v = Obj(el, key);
        return v is { ValueKind: JsonValueKind.String } s ? s.GetString() : null;
    }

    public static double? Num(JsonElement el, string key)
    {
        var v = Obj(el, key);
        if (v is null) return null;
        return v.Value.ValueKind switch
        {
            JsonValueKind.Number => v.Value.GetDouble(),
            JsonValueKind.String when double.TryParse(
                v.Value.GetString(), NumberStyles.Float, CultureInfo.InvariantCulture, out var d) => d,
            _ => null,
        };
    }

    public static List<JsonElement>? Arr(JsonElement el, string key)
    {
        var v = Obj(el, key);
        if (v is null || v.Value.ValueKind != JsonValueKind.Array) return null;
        return v.Value.EnumerateArray().ToList();
    }

    // ------------------------------------------------------------------
    // 数字格式化(不变文化,对齐 Python f-string 的 locale 无关语义)
    // ------------------------------------------------------------------

    public static string F2(double v) => v.ToString("F2", CultureInfo.InvariantCulture);
    public static string F0(double v) => v.ToString("F0", CultureInfo.InvariantCulture);
    public static string N2(double v) => v.ToString("N2", CultureInfo.InvariantCulture);

    public static double Now() => DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() / 1000.0;
}
