using System.Diagnostics;
using AgentEye.Core.Security;

namespace AgentEye.Core.Config;

/// <summary>一次加载的结果:配置本体 + 面向用户的告警 + 隔离文件路径。</summary>
public sealed record LoadOutcome(
    Dictionary<string, object?> Config,
    IReadOnlyList<string> Warnings,
    string? CorruptMovedTo,
    bool FreshInstall);

/// <summary>
/// v2 配置仓库:加载、保存、v1 迁移、损坏隔离。路径由构造注入,
/// 便于测试隔离(对齐 Python 版 config.py 的全部硬性要求):
///
/// - 文件损坏 ≠ 首次运行:损坏时改名留证且**不写盘**,绝不让空模板
///   盖掉用户仅有的 provider 与 key。
/// - 读不到(锁/权限)≠ 损坏:重试后仍读不到就报错,不碰磁盘。
/// - schema_version 高于 2 时抛 ConfigVersionError,不能当 v1 迁移。
/// - 迁移前必须先成功备份 v1 原文,且备份本身经 DPAPI 加密。
/// - save 只在深拷贝上加密,调用方内存态始终保持明文。
/// </summary>
public sealed class ConfigStore
{
    public const int SchemaVersion = 2;
    public const string V1BackupMark = "agenteye.v1.bak";

    public static readonly IReadOnlyDictionary<string, string> EnvDefaults =
        new Dictionary<string, string>
        {
            ["minimax"] = "MINIMAX_API_KEY",
            ["opencode_go"] = "OPENCODE_GO_API_KEY",
            ["deepseek"] = "DEEPSEEK_API_KEY",
            ["zhipu"] = "ZHIPU_API_KEY",
        };

    private static readonly IReadOnlyDictionary<string, string> KindFromV1Key =
        new Dictionary<string, string>
        {
            ["relay_sites"] = "relay",
            ["minimax"] = "minimax",
            ["opencode_go"] = "opencode_go",
            ["deepseek"] = "deepseek",
            ["zhipu"] = "zhipu",
        };

    private static readonly IReadOnlyDictionary<string, string> DefaultBaseUrls =
        new Dictionary<string, string>
        {
            ["relay"] = "",
            ["minimax"] = "https://api.minimaxi.com",
            ["opencode_go"] = "https://opencode.ai",
            ["deepseek"] = "https://api.deepseek.com",
            ["zhipu"] = "https://open.bigmodel.cn",
            ["generic_openai"] = "",
        };

    // 顺序即优先级:api_key → token → key(与 Python 元组一致)
    private static readonly string[] V1EntryKeyFields = ["api_key", "token", "key"];
    private static readonly string[] V1LiftedFields = ["name", "base_url"];
    private static readonly string[] V1ProviderKeepFields =
        ["quota_per_usd", "new_api_user_id", "headers"];

    private const int ReadRetries = 3;
    private static readonly TimeSpan ReadRetryDelay = TimeSpan.FromMilliseconds(150);
    private const int SaveRetries = 3;

    public string ConfigPath { get; }

    public ConfigStore(string? configPath = null)
    {
        ConfigPath = configPath ?? DefaultConfigPath;
    }

    public static string DefaultConfigPath
    {
        get
        {
            var profile = Environment.GetEnvironmentVariable("USERPROFILE");
            if (string.IsNullOrEmpty(profile))
                profile = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
            return Path.Combine(profile, ".agenteye", "config.json");
        }
    }

    // ------------------------------------------------------------------
    // 模板
    // ------------------------------------------------------------------

    /// <summary>空模板。每次新造,避免共享可变状态。</summary>
    public static Dictionary<string, object?> Template() => new()
    {
        ["schema_version"] = SchemaVersion,
        ["refresh_interval_sec"] = 30,
        ["alert"] = new Dictionary<string, object?>
        {
            ["enable"] = true,
            ["warn_pct"] = 30,
            ["critical_amount_yuan"] = 5.0,
        },
        ["ui"] = new Dictionary<string, object?>
        {
            ["x"] = null, ["y"] = null, ["width"] = 420, ["height"] = 560,
            ["order"] = new List<object?>(), ["pinned"] = true,
            ["widget"] = false, ["theme"] = "auto",
        },
        ["providers"] = new List<object?>(),
    };

    // ------------------------------------------------------------------
    // 密钥解析
    // ------------------------------------------------------------------

    /// <summary>provider dict → 明文 key;优先用 key_enc,失败回退 key。</summary>
    public static string PlainKey(Dictionary<string, object?>? provider)
    {
        if (provider is null) return "";
        if (provider.TryGetValue("key_enc", out var encObj) &&
            encObj is string enc && enc.Length > 0)
        {
            var decoded = DpapiCrypt.Unprotect(enc);
            if (decoded is not null) return decoded;
        }
        return provider.TryGetValue("key", out var keyObj) && keyObj is string k ? k : "";
    }

    /// <summary>
    /// 就地加密副本上的 providers:key → key_enc(移除明文)。
    /// 明文优先于 key_enc:用户在 DPAPI 解密失败后重输的 key 必须能落盘。
    /// </summary>
    private static void EncryptProviders(List<object?> providers)
    {
        if (!DpapiCrypt.IsAvailable) return;
        foreach (var item in providers)
        {
            if (item is not Dictionary<string, object?> p) continue;
            if (p.ContainsKey("_key_from_env"))
            {
                // 来自环境变量的密钥不落盘,配置文件里不留副本
                p.Remove("key");
                p.Remove("_key_from_env");
                continue;
            }
            if (!p.TryGetValue("key", out var plainObj) ||
                plainObj is not string plain || plain.Length == 0) continue;
            var enc = DpapiCrypt.Protect(plain);
            if (enc is null) continue; // 加密失败:保留明文,由写盘断言拦下
            p["key_enc"] = enc;
            p.Remove("key");
        }
    }

    /// <summary>就地解密内存态 providers:key_enc → 明文 key。失败保留 key_enc。</summary>
    private static void DecryptProviders(List<object?> providers)
    {
        foreach (var item in providers)
        {
            if (item is not Dictionary<string, object?> p) continue;
            if (!p.TryGetValue("key_enc", out var encObj) ||
                encObj is not string enc || enc.Length == 0) continue;
            var plain = PlainKey(p);
            if (plain.Length == 0) continue;
            p["key"] = plain;
            p.Remove("key_enc");
        }
    }

    /// <summary>深拷贝 cfg 并加密其中的 key,得到可直接写盘的形态。</summary>
    private static Dictionary<string, object?> PrepareForDisk(Dictionary<string, object?> cfg)
    {
        var data = JsonUtil.DeepClone(cfg);
        var providers = GetList(data, "providers");
        EncryptProviders(providers);
        var leaked = providers
            .OfType<Dictionary<string, object?>>()
            .Where(p => p.TryGetValue("key", out var k) && k is string s && s.Length > 0)
            .Select(p => p.TryGetValue("name", out var n) && n is string ns && ns.Length > 0 ? ns
                       : p.TryGetValue("id", out var i) && i is string ids && ids.Length > 0 ? ids : "?")
            .ToList();
        if (leaked.Count > 0)
            throw new PlaintextKeyError(
                "拒绝写盘:以下 provider 的 key 未能加密(DPAPI 不可用?)——" +
                string.Join(", ", leaked));
        return data;
    }

    // ------------------------------------------------------------------
    // 环境变量覆盖 / 默认值合并 / 归一化
    // ------------------------------------------------------------------

    /// <summary>
    /// 环境变量覆盖。必须在解密**之后**调用,否则磁盘里解出来的 key
    /// 会把 env 覆盖回去,环境变量形同虚设。
    /// </summary>
    public static void ApplyEnvV2(Dictionary<string, object?> cfg)
    {
        foreach (var item in GetList(cfg, "providers"))
        {
            if (item is not Dictionary<string, object?> p) continue;
            var kind = p.TryGetValue("kind", out var k) && k is string ks ? ks : null;
            var envName = p.TryGetValue("api_key_env", out var e) && e is string es && es.Length > 0
                ? es
                : kind is not null && EnvDefaults.TryGetValue(kind, out var d) ? d : null;
            if (envName is null) continue;
            var fromEnv = Environment.GetEnvironmentVariable(envName);
            if (!string.IsNullOrEmpty(fromEnv))
            {
                p["key"] = fromEnv;
                // 标记来源:env 里的密钥不落盘
                p["_key_from_env"] = envName;
            }
        }
    }

    /// <summary>递归合并 user 到 base(深 merge dict)。</summary>
    public static Dictionary<string, object?> MergeV2Defaults(
        Dictionary<string, object?> @base, Dictionary<string, object?>? user)
    {
        if (user is null) return @base;
        foreach (var (key, value) in user)
        {
            if (value is Dictionary<string, object?> vd &&
                @base.TryGetValue(key, out var existing) &&
                existing is Dictionary<string, object?> bd)
            {
                MergeV2Defaults(bd, vd);
            }
            else
            {
                @base[key] = value;
            }
        }
        return @base;
    }

    /// <summary>providers 归一成 list,丢弃非法成员并记录告警。</summary>
    public static void NormalizeProviders(Dictionary<string, object?> cfg, List<string> warnings)
    {
        if (!cfg.TryGetValue("providers", out var raw) || raw is null)
        {
            cfg["providers"] = new List<object?>();
            return;
        }
        List<object?> list;
        if (raw is Dictionary<string, object?> single)
        {
            // 少写个中括号,当单条处理
            list = [single];
        }
        else if (raw is List<object?> l)
        {
            list = l;
        }
        else
        {
            warnings.Add($"配置里 providers 不是列表(实际 {raw.GetType().Name}),已置空");
            cfg["providers"] = new List<object?>();
            return;
        }
        var good = new List<object?>();
        var bad = 0;
        foreach (var p in list)
        {
            if (p is Dictionary<string, object?>) good.Add(p);
            else bad++;
        }
        if (bad > 0)
            warnings.Add($"配置里 providers 有 {bad} 个非对象条目,已丢弃(provider 必须是 {{...}} 对象)");
        cfg["providers"] = good;
    }

    public static int ClampIntervalV2(Dictionary<string, object?> cfg)
    {
        var sec = 30;
        if (cfg.TryGetValue("refresh_interval_sec", out var v))
        {
            try { sec = Convert.ToInt32(v); }
            catch { sec = 30; }
        }
        return Math.Clamp(sec, 15, 3600);
    }

    // ------------------------------------------------------------------
    // v1 迁移
    // ------------------------------------------------------------------

    private static string GenId() => Guid.NewGuid().ToString("N")[..12];

    /// <summary>将 v1 schema(5 个分立数组)转换为 v2(统一 providers[])。</summary>
    public static Dictionary<string, object?> MigrateV1ToV2(object? v1Raw)
    {
        if (v1Raw is not Dictionary<string, object?> v1)
            return Template();

        var v2 = Template();
        if (v1.TryGetValue("refresh_interval_sec", out var ri))
            v2["refresh_interval_sec"] = ri;
        if (v1.TryGetValue("alert", out var a) && a is Dictionary<string, object?> alert)
        {
            var target = (Dictionary<string, object?>)v2["alert"]!;
            foreach (var (k, v) in alert) target[k] = v;
        }
        if (v1.TryGetValue("ui", out var u) && u is Dictionary<string, object?> ui)
            v2["ui"] = JsonUtil.DeepClone(ui);

        var providers = new List<object?>();
        foreach (var (v1Key, kind) in KindFromV1Key)
        {
            if (!v1.TryGetValue(v1Key, out var entries) || entries is not List<object?> entryList)
                continue;
            foreach (var entryObj in entryList)
            {
                if (entryObj is not Dictionary<string, object?> entry) continue;
                var key = "";
                foreach (var f in V1EntryKeyFields)
                {
                    if (entry.TryGetValue(f, out var kv) && kv is string ks && ks.Length > 0)
                    {
                        key = ks;
                        break;
                    }
                }
                var baseUrl =
                    entry.TryGetValue("base_url", out var bu) && bu is string bus && bus.Length > 0
                        ? bus
                        : DefaultBaseUrls.GetValueOrDefault(kind, "");
                var extra = new Dictionary<string, object?>();
                foreach (var (k, v) in entry)
                {
                    if (!V1EntryKeyFields.Contains(k) &&
                        !V1LiftedFields.Contains(k) &&
                        !V1ProviderKeepFields.Contains(k))
                    {
                        extra[k] = v;
                    }
                }
                var provider = new Dictionary<string, object?>
                {
                    ["id"] = GenId(),
                    ["kind"] = kind,
                    ["name"] = entry.TryGetValue("name", out var n) && n is string ns && ns.Length > 0
                        ? ns
                        : $"{kind}-{providers.Count + 1}",
                    ["key"] = key,
                    ["base_url"] = baseUrl,
                    ["extra"] = extra,
                };
                foreach (var k in V1ProviderKeepFields)
                    if (entry.TryGetValue(k, out var keep))
                        provider[k] = keep;
                providers.Add(provider);
            }
        }
        v2["providers"] = providers;
        return v2;
    }

    /// <summary>迁移前把 v1 原文加密存成 config.json.v1.bak;失败中止迁移。</summary>
    private void BackupV1Encrypted(Dictionary<string, object?> userCfg)
    {
        var backup = BackupPath;
        if (File.Exists(backup)) return;
        if (!DpapiCrypt.IsAvailable)
            throw new ConfigError("DPAPI 不可用,已中止 v1 迁移:备份会写出明文密钥");
        var blob = JsonUtil.DumpCompact(userCfg);
        var enc = DpapiCrypt.Protect(blob);
        if (enc is null)
            throw new ConfigError("v1 备份加密失败,已中止迁移:不愿写出明文密钥");
        try
        {
            AtomicSave(backup, new Dictionary<string, object?> { [V1BackupMark] = enc });
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException)
        {
            throw new ConfigError($"无法写入 v1 备份({e.Message}),已中止迁移以免密钥丢失");
        }
    }

    /// <summary>读回并解密 config.json.v1.bak(解密失败时抛 ConfigError)。</summary>
    public Dictionary<string, object?> RestoreV1Backup()
    {
        var backup = BackupPath;
        if (!File.Exists(backup))
            throw new ConfigError($"没有备份文件:{backup}");
        var data = JsonUtil.ParseObject(File.ReadAllText(backup))
            ?? throw new ConfigError($"{backup} 不是本程序写的加密备份");
        if (data.TryGetValue(V1BackupMark, out var encObj) && encObj is string enc)
        {
            var raw = DpapiCrypt.Unprotect(enc)
                ?? throw new ConfigError(
                    $"{backup} 解密失败:DPAPI 绑定当前用户,换账户/换机器无法恢复");
            return JsonUtil.ParseObject(raw)
                ?? throw new ConfigError($"{backup} 解密后的内容不是合法 JSON");
        }
        throw new ConfigError($"{backup} 不是本程序写的加密备份");
    }

    private string BackupPath => Path.ChangeExtension(ConfigPath, ".v1.bak");

    // ------------------------------------------------------------------
    // 原子写
    // ------------------------------------------------------------------

    /// <summary>
    /// 原子写入:唯一临时文件 + File.Move(overwrite) + FlushToDisk。
    /// NTFS 上对读者是原子的,但不保证数据已落盘;显式 fsync 防断电后半
    /// 个文件被当成损坏配置。
    /// </summary>
    public void AtomicSave(string path, Dictionary<string, object?> data)
    {
        var fullPath = Path.GetFullPath(path);
        var dir = Path.GetDirectoryName(fullPath)!;
        Directory.CreateDirectory(dir);
        var payload = System.Text.Encoding.UTF8.GetBytes(JsonUtil.Dump(data));
        var tmp = Path.Combine(dir,
            $"{Path.GetFileName(fullPath)}.{Path.GetRandomFileName()}.tmp");
        try
        {
            using (var fs = new FileStream(tmp, FileMode.Create, FileAccess.Write,
                FileShare.None))
            {
                fs.Write(payload);
                fs.Flush(flushToDisk: true);
            }
            File.Move(tmp, fullPath, overwrite: true);
            tmp = "";
        }
        finally
        {
            if (tmp.Length > 0 && File.Exists(tmp))
            {
                try { File.Delete(tmp); } catch (IOException) { }
            }
        }
    }

    /// <summary>保存 v2 配置(原子写,占用重试)。只在深拷贝上加密。</summary>
    public void SaveV2(Dictionary<string, object?> cfg)
    {
        var data = PrepareForDisk(cfg); // PlaintextKeyError 直接冒出去
        Exception? last = null;
        for (var attempt = 0; attempt < SaveRetries; attempt++)
        {
            try
            {
                AtomicSave(ConfigPath, data);
                return;
            }
            catch (Exception e) when (
                e is IOException or UnauthorizedAccessException)
            {
                // ERROR_SHARING_VIOLATION / ACCESS_DENIED:记事本/杀软短暂占用
                last = e;
                if (attempt < SaveRetries - 1)
                    Thread.Sleep(150 * (attempt + 1));
            }
        }
        throw new ConfigError($"配置保存失败(文件被占用?):{last?.Message}");
    }

    // ------------------------------------------------------------------
    // 损坏隔离
    // ------------------------------------------------------------------

    /// <summary>把损坏的 config.json 改名留证,绝不原地覆盖。</summary>
    private string? QuarantineCorruptConfig(string reason)
    {
        _ = reason; // 证据进文件名不如进日志,保留参数以对齐 Python 调用形态
        var stamp = DateTime.Now.ToString("yyyyMMdd-HHmmss");
        var dest = Path.Combine(
            Path.GetDirectoryName(ConfigPath)!,
            $"{Path.GetFileName(ConfigPath)}.corrupt-{stamp}-{Guid.NewGuid().ToString("N")[..6]}");
        try
        {
            File.Move(ConfigPath, dest);
            return dest;
        }
        catch (IOException)
        {
            return null;
        }
        catch (UnauthorizedAccessException)
        {
            return null;
        }
    }

    // ------------------------------------------------------------------
    // 加载
    // ------------------------------------------------------------------

    /// <summary>读配置原文:锁/权限类失败先重试;字节流坏立即按损坏处理。</summary>
    private string ReadConfigText()
    {
        Exception? last = null;
        var strictUtf8 = new System.Text.UTF8Encoding(encoderShouldEmitUTF8Identifier: false,
            throwOnInvalidBytes: true);
        for (var attempt = 0; attempt < ReadRetries; attempt++)
        {
            try
            {
                return File.ReadAllText(ConfigPath, strictUtf8);
            }
            catch (System.Text.DecoderFallbackException)
            {
                throw; // 内容真的坏了,重试无意义
            }
            catch (Exception e) when (e is IOException or UnauthorizedAccessException)
            {
                last = e;
                if (attempt < ReadRetries - 1)
                    Thread.Sleep(ReadRetryDelay * (attempt + 1));
            }
        }
        throw new ConfigError(
            $"无法读取配置文件 {ConfigPath}({last?.GetType().Name}: {last?.Message})。" +
            "请关闭正在占用它的程序(记事本/编辑器/另一个 AgentEye 实例)后重试;" +
            "为避免覆盖你的配置,本次不做任何写入。");
    }

    public LoadOutcome LoadV2()
    {
        var warnings = new List<string>();
        Directory.CreateDirectory(Path.GetDirectoryName(ConfigPath)!);
        if (!File.Exists(ConfigPath))
        {
            // 全新安装:空 providers,界面据此显示"添加 Key"空态
            var fresh = Template();
            SaveV2(fresh);
            return new LoadOutcome(fresh, warnings, null, FreshInstall: true);
        }

        string text;
        try
        {
            text = ReadConfigText();
        }
        catch (System.Text.DecoderFallbackException e)
        {
            return QuarantineAndReturnTemplate($"字节流不是合法 UTF-8({e.Message})");
        }

        var userCfg = JsonUtil.ParseObject(text);
        if (userCfg is null)
            return QuarantineAndReturnTemplate("根节点不是对象或 JSON 解析失败");

        var version = userCfg.TryGetValue("schema_version", out var v) ? v : null;
        if (version is int vi && vi == SchemaVersion)
        {
            var merged = MergeV2Defaults(Template(), userCfg);
            // 手改 "ui": null / "alert": [] 会把整套默认值顶掉:非 dict 的
            // 一律用模板补回(NormalizeProviders 只护 providers)。
            foreach (var sect in new[] { "ui", "alert" })
            {
                if (merged.TryGetValue(sect, out var s) && s is not Dictionary<string, object?>)
                    merged[sect] = Template()[sect] ?? new Dictionary<string, object?>();
            }
            NormalizeProviders(merged, warnings);
            // 顺序要紧:先解密成明文,再让环境变量覆盖,否则 env 永远不生效
            DecryptProviders(GetList(merged, "providers"));
            ApplyEnvV2(merged);
            return new LoadOutcome(merged, warnings, null, FreshInstall: false);
        }

        if (version is int high && high > SchemaVersion)
            throw new ConfigVersionError(
                $"配置版本 schema_version={high} 高于本程序支持的 {SchemaVersion}。" +
                "请升级 AgentEye,或手动改回 2。");

        // 只有缺版本号 / 整型 1 才走 v1 迁移;版本字段类型不对(字符串"2"、
        // true 等)按损坏隔离,绝不能落进迁移把 providers 清空。
        if (version is null || (version is int one && one == 1))
        {
            BackupV1Encrypted(userCfg);
            var migrated = MigrateV1ToV2(userCfg);
            NormalizeProviders(migrated, warnings);
            DecryptProviders(GetList(migrated, "providers"));
            ApplyEnvV2(migrated);
            SaveV2(migrated);
            return new LoadOutcome(migrated, warnings, null, FreshInstall: false);
        }

        return QuarantineAndReturnTemplate($"schema_version 类型异常: {JsonUtil.FromClr(version)}");
    }

    private LoadOutcome QuarantineAndReturnTemplate(string reason)
    {
        var moved = QuarantineCorruptConfig(reason);
        if (moved is null)
            reason += "(重命名失败,本次不会覆盖原文件)";
        return new LoadOutcome(Template(), [reason], moved, FreshInstall: false);
    }

    // ------------------------------------------------------------------
    // 小工具
    // ------------------------------------------------------------------

    public static List<object?> GetList(Dictionary<string, object?> cfg, string key) =>
        cfg.TryGetValue(key, out var v) && v is List<object?> l ? l : [];
}
