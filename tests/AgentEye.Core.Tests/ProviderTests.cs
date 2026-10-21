using AgentEye.Core.Cache;
using AgentEye.Core.Config;
using AgentEye.Core.Providers;
using Xunit;

namespace AgentEye.Core.Tests;

public class DetectTests
{
    [Theory]
    [InlineData("https://api.deepseek.com", "deepseek", "https://api.deepseek.com", "high")]
    [InlineData("https://open.bigmodel.cn/api", "zhipu", "https://open.bigmodel.cn", "high")]
    [InlineData("https://api.minimaxi.com", "minimax", "https://api.minimaxi.com", "high")]
    [InlineData("https://api.minimax.cn/", "minimax", "https://api.minimaxi.com", "high")]
    [InlineData("https://opencode.ai", "opencode_go", "https://opencode.ai", "high")]
    public void UrlHostHints_Win(string url, string kind, string baseUrl, string conf)
    {
        var o = Detect.Run(hintUrl: url);
        Assert.Equal(kind, o.Kind);
        Assert.Equal(baseUrl, o.BaseUrl);
        Assert.Equal(conf, o.Confidence);
    }

    [Fact]
    public void UrlV1_MediumGeneric()
    {
        var o = Detect.Run(hintUrl: "https://relay.example.com/v1");
        Assert.Equal("generic_openai", o.Kind);
        Assert.Equal("https://relay.example.com/v1", o.BaseUrl);
        Assert.Equal("medium", o.Confidence);
    }

    [Fact]
    public void UrlUnknown_LowGeneric()
    {
        var o = Detect.Run(hintUrl: "https://weird.example.com");
        Assert.Equal("generic_openai", o.Kind);
        Assert.Equal("https://weird.example.com", o.BaseUrl);
        Assert.Equal("low", o.Confidence);
    }

    [Fact]
    public void SkCpPrefix_HighMinimax()
    {
        var o = Detect.Run(key: "sk-cp-abc123");
        Assert.Equal("minimax", o.Kind);
        Assert.Equal("https://api.minimaxi.com", o.BaseUrl);
        Assert.Equal("high", o.Confidence);
    }

    [Fact]
    public void JwtShape_LowOpenCodeGo()
    {
        var o = Detect.Run(key: "eyJhbGciOi.somepayload.signature");
        Assert.Equal("opencode_go", o.Kind);
        Assert.Equal("low", o.Confidence);
    }

    [Fact]
    public void SkPrefix_LowGeneric()
    {
        var o = Detect.Run(key: "sk-plain");
        Assert.Equal("generic_openai", o.Kind);
        Assert.Equal("low", o.Confidence);
    }

    [Fact]
    public void Empty_LowGeneric()
    {
        Assert.Equal("generic_openai", Detect.Run().Kind);
    }
}

public class LevelTests
{
    private static Dictionary<string, object?> Cfg(double crit = 5.0, double warn = 30.0) => new()
    {
        ["alert"] = new Dictionary<string, object?>
            { ["critical_amount_yuan"] = crit, ["warn_pct"] = warn },
    };

    private static ProviderResult Res(string unit = "", double? remaining = null,
        double? pct = null, string? error = null, bool unconfigured = false) =>
        new() { Unit = unit, Remaining = remaining, Pct = pct, Error = error, Unconfigured = unconfigured };

    [Fact]
    public void Yuan_RemainingBelowCritical_IsCritical()
    {
        Assert.Equal(Levels.Critical,
            ProviderRegistry.ComputeLevel(Res("¥", remaining: 3.0), new(), Cfg()));
        Assert.Equal(Levels.Critical,
            ProviderRegistry.ComputeLevel(Res("¥", remaining: 5.0), new(), Cfg()));
        Assert.Equal(Levels.Ok,
            ProviderRegistry.ComputeLevel(Res("¥", remaining: 5.01), new(), Cfg()));
    }

    [Fact]
    public void Yuan_NoRemaining_IsOk()
    {
        Assert.Equal(Levels.Ok, ProviderRegistry.ComputeLevel(Res("¥"), new(), Cfg()));
    }

    [Theory]
    [InlineData(30.0, Levels.Warn)]
    [InlineData(29.9, Levels.Warn)]
    [InlineData(30.1, Levels.Ok)]
    public void Pct_WarnThresholdBoundary(double pct, string expected)
    {
        Assert.Equal(expected, ProviderRegistry.ComputeLevel(Res(pct: pct), new(), Cfg()));
    }

    [Fact]
    public void Pct_AppliesToNonPercentUnitsToo()
    {
        // 关键回归:美元计额 provider 不按 unit 白名单过滤
        Assert.Equal(Levels.Warn,
            ProviderRegistry.ComputeLevel(Res("$", pct: 10), new(), Cfg()));
    }

    [Fact]
    public void NoPct_IsOk()
    {
        Assert.Equal(Levels.Ok, ProviderRegistry.ComputeLevel(Res("$", remaining: 1), new(), Cfg()));
    }

    [Fact]
    public void ErrorRows_KeepTheirLevel()
    {
        Assert.Equal(Levels.Error,
            ProviderRegistry.ComputeLevel(Res(error: "x"), new(), Cfg()));
        Assert.Equal(Levels.Unconfigured,
            ProviderRegistry.ComputeLevel(Res(error: "x", unconfigured: true), new(), Cfg()));
    }
}

public class FetchAllTests
{
    private static Dictionary<string, object?> Cfg(params (string Name, string Kind)[] ps)
    {
        var providers = ps.Select(p => (object?)new Dictionary<string, object?>
        {
            ["id"] = p.Name, ["kind"] = p.Kind, ["name"] = p.Name,
            ["key"] = "sk-test",
            ["base_url"] = "https://example.invalid", ["extra"] = new Dictionary<string, object?>(),
        }).ToList();
        return new Dictionary<string, object?> { ["providers"] = providers };
    }

    [Fact]
    public async Task OrderMatchesProvidersList()
    {
        var cfg = Cfg(("a", "unknown_kind"), ("b", "unknown_kind"), ("c", "unknown_kind"));
        var rows = await ProviderRegistry.FetchAllAsync(cfg);
        Assert.Equal(3, rows.Count);
        Assert.Equal(new[] { "a", "b", "c" }, rows.Select(r => r.Name));
        // 未知 kind:单行报错,不影响其它行
        Assert.All(rows, r => Assert.Contains("未知 provider kind", r.Error));
        Assert.All(rows, r => Assert.Equal(Levels.Error, r.Level));
    }

    [Fact]
    public async Task SkipNames_PausedRow_NoRequest()
    {
        var cfg = Cfg(("a", "generic_openai"), ("b", "unknown_kind"));
        var rows = await ProviderRegistry.FetchAllAsync(cfg, skipNames: ["a"]);
        Assert.Equal(Levels.Paused, rows[0].Level);
        Assert.True(rows[0].Paused);
        Assert.Equal("已暂停轮询", rows[0].Detail);
        Assert.Equal(Levels.Error, rows[1].Level);
    }

    [Fact]
    public async Task NoKey_Unconfigured()
    {
        var cfg = new Dictionary<string, object?>
        {
            ["providers"] = new List<object?>
            {
                new Dictionary<string, object?>
                {
                    ["id"] = "p", ["kind"] = "deepseek", ["name"] = "a",
                    ["base_url"] = "https://example.invalid",
                    ["extra"] = new Dictionary<string, object?>(),
                },
            },
        };
        var rows = await ProviderRegistry.FetchAllAsync(cfg);
        Assert.True(rows[0].Unconfigured);
        Assert.Equal("未配置 key", rows[0].Error);
        Assert.Equal(Levels.Unconfigured, rows[0].Level);
    }

    [Fact]
    public async Task PlaceholderKey_EqualsUnconfigured()
    {
        var cfg = new Dictionary<string, object?>
        {
            ["providers"] = new List<object?>
            {
                new Dictionary<string, object?>
                {
                    ["id"] = "p", ["kind"] = "deepseek", ["name"] = "a",
                    ["key"] = "在这里粘贴DeepSeek的key",
                    ["extra"] = new Dictionary<string, object?>(),
                },
            },
        };
        var rows = await ProviderRegistry.FetchAllAsync(cfg);
        Assert.True(rows[0].Unconfigured);
    }

    [Fact]
    public async Task CorruptKeyEnc_IsKeyDecryptError_NotUnconfigured()
    {
        var cfg = new Dictionary<string, object?>
        {
            ["providers"] = new List<object?>
            {
                new Dictionary<string, object?>
                {
                    ["id"] = "p", ["kind"] = "deepseek", ["name"] = "a",
                    ["key_enc"] = "not-a-valid-blob",
                    ["extra"] = new Dictionary<string, object?>(),
                },
            },
        };
        var rows = await ProviderRegistry.FetchAllAsync(cfg);
        Assert.Equal(Levels.Error, rows[0].Level);
        Assert.False(rows[0].Unconfigured);
        Assert.Contains("key_enc 解密失败", rows[0].Error);
    }

    [Fact]
    public async Task EmptyConfig_ReturnsEmptyList()
    {
        Assert.Empty(await ProviderRegistry.FetchAllAsync(new Dictionary<string, object?>()));
    }
}

public class CacheStoreTests : IDisposable
{
    private readonly string _dir = Path.Combine(Path.GetTempPath(),
        "agenteye-cache-tests", Guid.NewGuid().ToString("N"));
    private readonly CacheStore _cache;

    public CacheStoreTests()
    {
        _cache = new CacheStore(_dir);
    }

    public void Dispose()
    {
        try { Directory.Delete(_dir, recursive: true); }
        catch (IOException) { }
    }

    [Fact]
    public void Models_RoundTrip_WithOrderPreserved()
    {
        _cache.SetModels("https://x/v1", "sk-1", ["m1", "m2", "m3"]);
        Assert.Equal(["m1", "m2", "m3"], _cache.GetModels("https://x/v1", "sk-1"));
        // 用户手动排序后,新一轮 fetch 不能冲掉顺序
        _cache.SaveModelOrder("https://x/v1", "sk-1", ["m3", "m1"]);
        _cache.SetModels("https://x/v1", "sk-1", ["m1", "m2", "m3"]);
        Assert.Equal(["m3", "m1", "m2"], _cache.GetModels("https://x/v1", "sk-1"));
    }

    [Fact]
    public void Models_TtlExpiry_ReturnsNull()
    {
        _cache.SetModels("https://x/v1", "sk-1", ["m1"]);
        Assert.NotNull(_cache.GetModels("https://x/v1", "sk-1"));
        Assert.Null(_cache.GetModels("https://x/v1", "sk-1", TimeSpan.Zero));
        // 键不匹配(base 或 key 变了)也取不到
        Assert.Null(_cache.GetModels("https://x/v1", "sk-other"));
    }

    [Fact]
    public void Models_CorruptFile_ReturnsNull()
    {
        Directory.CreateDirectory(_dir);
        File.WriteAllText(Path.Combine(_dir, "models.json"), "{ truncated");
        Assert.Null(_cache.GetModels("https://x", "k"));
    }

    [Fact]
    public void RemoveProviderEntries_RemovesOnlyThatKey()
    {
        _cache.SetModels("https://a/v1", "k1", ["m"]);
        _cache.SetModels("https://b/v1", "k2", ["m"]);
        Assert.True(_cache.RemoveProviderEntries("https://a/v1", "k1"));
        Assert.False(_cache.RemoveProviderEntries("https://a/v1", "k1"));
        Assert.Null(_cache.GetModels("https://a/v1", "k1"));
        Assert.NotNull(_cache.GetModels("https://b/v1", "k2"));
    }

    [Fact]
    public void ProbeLog_AppendTrimRecent()
    {
        _cache.LogProbe("DS", "m1", success: true, latencyMs: 123.4);
        _cache.LogProbe("DS", "m2", success: false, latencyMs: 9, error: "boom");
        _cache.LogProviderDeleted("DS");
        var recent = _cache.RecentProbes("DS");
        Assert.Equal(3, recent.Count);
        Assert.Equal("provider_deleted", recent[0]["event"]);
        Assert.Equal("m2", recent[1]["model"]);
        Assert.False((bool)recent[1]["success"]!);
        Assert.Equal("m1", _cache.LastProbe("DS", "m1")!["model"]);
        Assert.Null(_cache.LastProbe("DS", "m-none"));
    }

    [Fact]
    public void AlertState_RoundTrip_FiltersBadRows()
    {
        _cache.SaveAlertState(new Dictionary<string, (string, double)>
        {
            ["DS"] = ("critical", Http.Now() - 60),
            ["Future"] = ("warn", Http.Now() + 3600),   // 未来时间戳:丢弃
            ["BadLevel"] = ("ok", Http.Now()),           // 非法等级:丢弃
        });
        var state = _cache.LoadAlertState();
        Assert.Single(state);
        Assert.True(state.ContainsKey("DS"));
        Assert.Equal("critical", state["DS"].Level);
    }

    [Fact]
    public void AlertState_CorruptFile_ReturnsEmpty()
    {
        Directory.CreateDirectory(_dir);
        File.WriteAllText(Path.Combine(_dir, "alert_state.json"), "not json");
        Assert.Empty(_cache.LoadAlertState());
    }
}

public class ModelProbeTests
{
    [Fact]
    public void Ok200_Usable()
    {
        var o = GenericOpenAi.ClassifyModelProbe(netOk: true, status: 200);
        Assert.True(o.Ok);
        Assert.Contains("key+model", o.Message);
    }

    [Theory]
    [InlineData(401)]
    [InlineData(403)]
    public void AuthReject_KeyInvalid(int status)
    {
        var o = GenericOpenAi.ClassifyModelProbe(netOk: true, status);
        Assert.False(o.Ok);
        Assert.Contains("key", o.Message);
    }

    [Fact]
    public void NotFound_ModelOrEndpoint()
    {
        var o = GenericOpenAi.ClassifyModelProbe(netOk: true, status: 404);
        Assert.False(o.Ok);
        Assert.Contains("404", o.Message);
    }

    [Fact]
    public void NetFail_NetworkError()
    {
        var o = GenericOpenAi.ClassifyModelProbe(netOk: false, status: 0);
        Assert.False(o.Ok);
        Assert.Contains("网络", o.Message);
    }

    [Fact]
    public void OtherStatus_ReportsHttp()
    {
        var o = GenericOpenAi.ClassifyModelProbe(netOk: true, status: 502);
        Assert.False(o.Ok);
        Assert.Contains("502", o.Message);
    }
}
