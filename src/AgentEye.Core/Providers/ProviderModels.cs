namespace AgentEye.Core.Providers;

/// <summary>result 的等级常量(与 Python 版 providers/__init__.py 对齐)。</summary>
public static class Levels
{
    public const string Error = "error";
    public const string Unknown = "unknown";
    public const string Paused = "paused";
    public const string Ok = "ok";
    public const string Warn = "warn";
    public const string Critical = "critical";
    public const string Unconfigured = "unconfigured";
}

/// <summary>
/// key_enc 存在但 DPAPI 解不出明文(密文损坏或换了 Windows 用户)。
/// 与"没配 key"(unconfigured)区分开:前者提示密文坏了需要重填,
/// 后者只是提醒还没填。
/// </summary>
public sealed class KeyDecryptError : Exception
{
    public KeyDecryptError(string message) : base(message) { }
}

/// <summary>
/// 适配器的部分返回(等价于 Python 适配器返回的 dict,经 result.update
/// 合并进空白行)。未赋值的字段 = 不覆盖空白行的对应值。
/// </summary>
public sealed class FetchPayload
{
    public string? Error { get; set; }
    public bool Unconfigured { get; set; }
    public double? Remaining { get; set; }
    public double? Used { get; set; }
    public double? Total { get; set; }
    public double? UsedToday { get; set; }
    public string? Unit { get; set; }
    public double? Pct { get; set; }
    public string? Detail { get; set; }
    public bool? IsEstimate { get; set; }
    public string? QuotaEndpoint { get; set; }
    public List<string>? Models { get; set; }
    public int? ModelsCount { get; set; }

    public static FetchPayload Err(string message, bool unconfigured = false) =>
        new() { Error = message, Unconfigured = unconfigured };
}

/// <summary>UI 行模型:ProviderRegistry.FetchAll 的产出,字段清单唯一来源。</summary>
public sealed class ProviderResult
{
    public string? Id { get; set; }
    public string Name { get; set; } = "";
    public string Type { get; set; } = "";
    public string Kind { get; set; } = "";
    public double? Remaining { get; set; }
    public double? Used { get; set; }
    public double? Total { get; set; }
    public double? UsedToday { get; set; }
    public string Unit { get; set; } = "";
    public double? Pct { get; set; }
    public string Detail { get; set; } = "";
    public bool IsEstimate { get; set; }
    public double UpdatedAt { get; set; }
    public string? Error { get; set; }
    public bool Unconfigured { get; set; }
    public bool Paused { get; set; }
    public string Level { get; set; } = Levels.Unknown;
    public string? QuotaEndpoint { get; set; }
    public List<string>? Models { get; set; }
    public int? ModelsCount { get; set; }

    /// <summary>合并适配器部分返回:非 null 字段覆盖(等价 dict.update)。</summary>
    public void Merge(FetchPayload p)
    {
        Error = p.Error ?? Error;
        if (p.Error is not null) Unconfigured = p.Unconfigured;
        Remaining = p.Remaining ?? Remaining;
        Used = p.Used ?? Used;
        Total = p.Total ?? Total;
        UsedToday = p.UsedToday ?? UsedToday;
        Unit = p.Unit ?? Unit;
        Pct = p.Pct ?? Pct;
        Detail = p.Detail ?? Detail;
        IsEstimate = p.IsEstimate ?? IsEstimate;
        QuotaEndpoint = p.QuotaEndpoint ?? QuotaEndpoint;
        Models = p.Models ?? Models;
        ModelsCount = p.ModelsCount ?? ModelsCount;
    }
}
