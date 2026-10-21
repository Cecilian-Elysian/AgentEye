using AgentEye.Core.Config;
using Xunit;

namespace AgentEye.Core.Tests;

/// <summary>
/// ConfigStore 契约测试(对齐 Python 版 test_secure/test_config 的关键场景)。
/// 每个测试用独立临时目录,xUnit 并行安全;DPAPI 走真实当前用户。
/// </summary>
public sealed class ConfigStoreTests : IDisposable
{
    private readonly string _dir;
    private readonly string _path;
    private readonly ConfigStore _store;

    public ConfigStoreTests()
    {
        _dir = Path.Combine(Path.GetTempPath(), "agenteye-tests",
            Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(_dir);
        _path = Path.Combine(_dir, "config.json");
        _store = new ConfigStore(_path);
    }

    public void Dispose()
    {
        try { Directory.Delete(_dir, recursive: true); }
        catch (IOException) { }
    }

    private static Dictionary<string, object?> V2WithKey(string key = "sk-in-memory") => new()
    {
        ["schema_version"] = 2,
        ["refresh_interval_sec"] = 60,
        ["alert"] = new Dictionary<string, object?>
            { ["enable"] = true, ["warn_pct"] = 30, ["critical_amount_yuan"] = 5.0 },
        ["ui"] = new Dictionary<string, object?>
            { ["x"] = null, ["y"] = null, ["width"] = 900, ["height"] = 640,
              ["order"] = new List<object?>(), ["pinned"] = true,
              ["widget"] = false, ["widget_pos"] = null,
              ["page"] = "overview", ["theme"] = "dark" },
        ["providers"] = new List<object?>
        {
            new Dictionary<string, object?>
            {
                ["id"] = "p1", ["kind"] = "deepseek", ["name"] = "DS",
                ["key"] = key, ["base_url"] = "https://x", ["extra"] = new Dictionary<string, object?>(),
            },
        },
    };

    private static string ReadText(string p) => File.ReadAllText(p);

    [Fact]
    public void FreshInstall_CreatesTemplateFile()
    {
        var outcome = _store.LoadV2();
        Assert.True(outcome.FreshInstall);
        Assert.Empty(ConfigStore.GetList(outcome.Config, "providers"));
        Assert.Equal(2, outcome.Config["schema_version"]);
        Assert.True(File.Exists(_path));
        // 模板写盘后必须能再读回来
        var second = _store.LoadV2();
        Assert.False(second.FreshInstall);
    }

    [Fact]
    public void SaveV2_EncryptsOnDisk_KeepsPlaintextInMemory()
    {
        var cfg = V2WithKey();
        _store.SaveV2(cfg);
        var disk = JsonUtil.ParseObject(ReadText(_path))!;
        var p = (Dictionary<string, object?>)((List<object?>)disk["providers"]!)[0]!;
        Assert.False(p.ContainsKey("key"), "磁盘态绝不能有明文 key");
        Assert.True(p.ContainsKey("key_enc"));
        // 调用方内存态保持明文
        var memP = (Dictionary<string, object?>)((List<object?>)cfg["providers"]!)[0]!;
        Assert.Equal("sk-in-memory", memP["key"]);
        Assert.False(memP.ContainsKey("key_enc"));
    }

    [Fact]
    public void LoadV2_DecryptsBackToPlaintext()
    {
        _store.SaveV2(V2WithKey());
        var outcome = _store.LoadV2();
        var p = (Dictionary<string, object?>)ConfigStore.GetList(outcome.Config, "providers")[0]!;
        Assert.Equal("sk-in-memory", p["key"]);
        Assert.False(p.ContainsKey("key_enc"));
    }

    [Fact]
    public void PlainKey_PrefersEnc_FallsBackToKey()
    {
        var encOnly = new Dictionary<string, object?>
            { ["key_enc"] = AgentEye.Core.Security.DpapiCrypt.Protect("from-enc")! };
        Assert.Equal("from-enc", ConfigStore.PlainKey(encOnly));
        Assert.Equal("from-key", ConfigStore.PlainKey(
            new Dictionary<string, object?> { ["key"] = "from-key" }));
        Assert.Equal("", ConfigStore.PlainKey(new Dictionary<string, object?>()));
        Assert.Equal("", ConfigStore.PlainKey(null));
        // key_enc 损坏 → 回退 key
        Assert.Equal("fallback", ConfigStore.PlainKey(new Dictionary<string, object?>
            { ["key_enc"] = "not-a-blob", ["key"] = "fallback" }));
    }

    [Fact]
    public void VersionTooHigh_ThrowsAndLeavesFileUntouched()
    {
        var cfg = V2WithKey();
        cfg["schema_version"] = 3;
        _store.SaveV2(cfg);
        var before = ReadText(_path);
        Assert.Throws<ConfigVersionError>(() => _store.LoadV2());
        Assert.Equal(before, ReadText(_path));
    }

    [Fact]
    public void CorruptJson_Quarantined_NotOverwritten()
    {
        File.WriteAllText(_path, "{ not json");
        var outcome = _store.LoadV2();
        Assert.NotNull(outcome.CorruptMovedTo);
        Assert.True(File.Exists(outcome.CorruptMovedTo!), "损坏原文必须留证");
        Assert.False(File.Exists(_path), "空模板绝不能覆盖原路径");
        Assert.Empty(ConfigStore.GetList(outcome.Config, "providers"));
    }

    [Fact]
    public void RootNotObject_Quarantined()
    {
        File.WriteAllText(_path, "[1, 2, 3]");
        Assert.NotNull(_store.LoadV2().CorruptMovedTo);
    }

    [Fact]
    public void VersionTypeAnomaly_Quarantined_NotMigrated()
    {
        // 手滑写成字符串 "2":绝不能落进 v1 迁移把 providers 清空
        var cfg = V2WithKey();
        cfg["schema_version"] = "2";
        _store.SaveV2(cfg);
        var outcome = _store.LoadV2();
        Assert.NotNull(outcome.CorruptMovedTo);
        Assert.False(File.Exists(_path));
    }

    [Fact]
    public void MergeDefaults_FillsMissingSections_AndRepairsNonDict()
    {
        File.WriteAllText(_path, """{"schema_version": 2, "ui": null}""");
        var outcome = _store.LoadV2();
        var ui = Assert.IsType<Dictionary<string, object?>>(outcome.Config["ui"]);
        Assert.Equal(360, ui["width"]);
        Assert.True((bool)ui["pinned"]!);
        var alert = Assert.IsType<Dictionary<string, object?>>(outcome.Config["alert"]);
        Assert.Equal(30, alert["warn_pct"]);
    }

    [Fact]
    public void NormalizeProviders_DropsNonObjects_WithWarning()
    {
        File.WriteAllText(_path,
            """{"schema_version": 2, "providers": [null, "x", {"id": "p1", "kind": "deepseek", "name": "DS", "key": "sk-1"}]}""");
        var outcome = _store.LoadV2();
        Assert.Equal(1, ConfigStore.GetList(outcome.Config, "providers").Count);
        Assert.Contains(outcome.Warnings, w => w.Contains("2 个非对象条目"));
    }

    [Fact]
    public void NormalizeProviders_WrapsSingleDict()
    {
        File.WriteAllText(_path,
            """{"schema_version": 2, "providers": {"id": "p1", "kind": "relay", "name": "r", "key": "sk-2", "base_url": "https://x"}}""");
        var outcome = _store.LoadV2();
        Assert.Equal(1, ConfigStore.GetList(outcome.Config, "providers").Count);
    }

    [Fact]
    public void V1Migration_MapsAllArrays_AndWritesEncryptedBackup()
    {
        var v1 = """
        {
          "refresh_interval_sec": 45,
          "alert": {"warn_pct": 25},
          "ui": {"theme": "light"},
          "relay_sites": [{"name": "某中转站", "api_key": "sk-relay", "base_url": "https://r.example",
                           "quota_per_usd": 500000, "email": "a@b.c", "password": "pw"}],
          "minimax": [{"name": "MiniMax", "token": "eyJ-mini"}],
          "opencode_go": [{"key": "sk-og"}],
          "deepseek": [{"api_key": "sk-ds", "token": "should-not-win"}],
          "zhipu": []
        }
        """;
        File.WriteAllText(_path, v1);
        var outcome = _store.LoadV2();

        Assert.False(outcome.FreshInstall);
        Assert.Equal(2, outcome.Config["schema_version"]);
        Assert.Equal(45, outcome.Config["refresh_interval_sec"]);
        Assert.Equal("light", Assert.IsType<Dictionary<string, object?>>(outcome.Config["ui"])["theme"]);

        var providers = ConfigStore.GetList(outcome.Config, "providers");
        Assert.Equal(4, providers.Count);
        var byKind = providers.OfType<Dictionary<string, object?>>()
            .ToDictionary(p => p["kind"], p => p);
        var relay = byKind["relay"];
        Assert.Equal("某中转站", relay["name"]);
        Assert.Equal("sk-relay", relay["key"]);
        Assert.Equal("https://r.example", relay["base_url"]);
        Assert.Equal(500000, relay["quota_per_usd"]);
        var extra = Assert.IsType<Dictionary<string, object?>>(relay["extra"]);
        Assert.Equal("a@b.c", extra["email"]);
        Assert.Equal("pw", extra["password"]);
        Assert.Equal("eyJ-mini", byKind["minimax"]["key"]);
        Assert.Equal("sk-og", byKind["opencode_go"]["key"]);
        // key 字段优先级:api_key 先于 token
        Assert.Equal("sk-ds", byKind["deepseek"]["key"]);
        // 缺 name 的按 kind-序号 兜底
        Assert.Equal("opencode_go-3", byKind["opencode_go"]["name"]);

        // 备份存在且是加密的;磁盘上找不到任何明文 sk-
        var backup = Path.ChangeExtension(_path, ".v1.bak");
        Assert.True(File.Exists(backup));
        var raw = ReadText(backup);
        Assert.Contains("agenteye.v1.bak", raw);
        Assert.DoesNotContain("sk-relay", raw);
        Assert.DoesNotContain("eyJ-mini", raw);
        // 迁移结果已写回 config.json
        Assert.True(File.Exists(_path));
        Assert.Equal(2, JsonUtil.ParseObject(ReadText(_path))!["schema_version"]);

        // 备份可解回原文
        var restored = _store.RestoreV1Backup();
        var relaySites = Assert.IsType<List<object?>>(restored["relay_sites"]);
        var relayEntry = Assert.IsType<Dictionary<string, object?>>(relaySites[0]);
        Assert.Equal("sk-relay", relayEntry["api_key"]);
    }

    [Fact]
    public void V1Migration_WithoutVersionNumber_AlsoMigrates()
    {
        File.WriteAllText(_path, """{"minimax": [{"name": "m", "token": "t"}]}""");
        var outcome = _store.LoadV2();
        Assert.Equal(1, ConfigStore.GetList(outcome.Config, "providers").Count);
        Assert.True(File.Exists(Path.ChangeExtension(_path, ".v1.bak")));
    }

    [Fact]
    public void ApplyEnv_OverridesDecryptedKey_AndDoesNotPersist()
    {
        var envName = "AGENTEYE_TEST_KEY_" + Guid.NewGuid().ToString("N")[..8];
        Environment.SetEnvironmentVariable(envName, "sk-from-env");
        try
        {
            var cfg = V2WithKey("sk-on-disk");
            ((Dictionary<string, object?>)((List<object?>)cfg["providers"]!)[0]!)["api_key_env"] = envName;
            _store.SaveV2(cfg);
            ConfigStore.ApplyEnvV2(cfg);
            var p = (Dictionary<string, object?>)((List<object?>)cfg["providers"]!)[0]!;
            Assert.Equal("sk-from-env", p["key"]);
            Assert.Equal(envName, p["_key_from_env"]);
            // env key 不落盘
            _store.SaveV2(cfg);
            var disk = JsonUtil.ParseObject(ReadText(_path))!;
            var dp = (Dictionary<string, object?>)((List<object?>)disk["providers"]!)[0]!;
            Assert.False(dp.ContainsKey("key"));
            Assert.False(dp.ContainsKey("key_enc"));
            Assert.False(dp.ContainsKey("_key_from_env"));
        }
        finally
        {
            Environment.SetEnvironmentVariable(envName, null);
        }
    }

    [Fact]
    public void LockedFile_ThrowsConfigError_KeepsFileIntact()
    {
        File.WriteAllText(_path, ReadTextOrCreate());
        static string ReadTextOrCreate() => """{"schema_version": 2}""";
        using (new FileStream(_path, FileMode.Open, FileAccess.Read, FileShare.None))
        {
            Assert.Throws<ConfigError>(() => _store.LoadV2());
        }
        // 文件原封未动(绝不能被隔离或覆盖)
        Assert.True(File.Exists(_path));
        Assert.Equal("""{"schema_version": 2}""", ReadText(_path));
    }

    [Fact]
    public void InvalidUtf8_Quarantined()
    {
        File.WriteAllBytes(_path, [0x7b, 0xff, 0xfe, 0x7d]); // {0xFF0xFE} 非法 UTF-8
        Assert.NotNull(_store.LoadV2().CorruptMovedTo);
    }

    [Fact]
    public void ClampInterval_BoundsTo15To3600()
    {
        Assert.Equal(30, ConfigStore.ClampIntervalV2(new Dictionary<string, object?> { ["refresh_interval_sec"] = 30 }));
        Assert.Equal(15, ConfigStore.ClampIntervalV2(new Dictionary<string, object?> { ["refresh_interval_sec"] = 1 }));
        Assert.Equal(3600, ConfigStore.ClampIntervalV2(new Dictionary<string, object?> { ["refresh_interval_sec"] = 99999 }));
        Assert.Equal(30, ConfigStore.ClampIntervalV2(new Dictionary<string, object?> { ["refresh_interval_sec"] = "bad" }));
        Assert.Equal(30, ConfigStore.ClampIntervalV2(new Dictionary<string, object?>()));
    }

    [Fact]
    public void DeepClone_DoesNotShareNestedState()
    {
        var cfg = V2WithKey();
        var clone = JsonUtil.DeepClone(cfg);
        ((Dictionary<string, object?>)((List<object?>)clone["providers"]!)[0]!)["key"] = "mutated";
        var orig = (Dictionary<string, object?>)((List<object?>)cfg["providers"]!)[0]!;
        Assert.Equal("sk-in-memory", orig["key"]);
    }
}
