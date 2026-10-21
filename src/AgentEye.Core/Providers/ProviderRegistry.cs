using AgentEye.Core.Cache;
using AgentEye.Core.Config;

namespace AgentEye.Core.Providers;

/// <summary>
/// 适配器注册表 + 并发拉取编排 + 等级判定(端口自 providers/__init__.py)。
///
/// 硬性要求(与 Python 版一致):
/// - FetchAll 返回顺序必须与 cfg["providers"] 一致(UI 按 (name, type)
///   序列当重建签名,顺序一变就整面板重建)。
/// - 单个 provider 抛异常只影响它自己那一行。
/// - skipNames 里的条目不发请求,直接返回 paused 行。
/// </summary>
public static class ProviderRegistry
{
    public const int MaxConcurrent = 8;

    private static readonly IReadOnlyDictionary<string,
            Func<GenericOpenAi.LegacyEntry, CancellationToken, Task<FetchPayload>>>
        Adapters = new Dictionary<string,
            Func<GenericOpenAi.LegacyEntry, CancellationToken, Task<FetchPayload>>>
        {
            ["relay"] = RelayProvider.FetchAsync,
            ["minimax"] = MiniMaxProvider.FetchAsync,
            ["opencode_go"] = OpenCodeGoProvider.FetchAsync,
            ["deepseek"] = DeepSeekProvider.FetchAsync,
            ["zhipu"] = ZhipuProvider.FetchAsync,
            ["generic_openai"] = GenericOpenAi.FetchAsync,
        };

    /// <summary>占位 key 文本等同于没填。</summary>
    private static readonly HashSet<string> PlaceholderKeys = new()
    {
        "在这里粘贴中转站的key",
        "在这里粘贴订阅Key",
        "在这里粘贴Go的key",
        "在这里粘贴DeepSeek的key",
        "在这里粘贴智谱的key",
    };

    private static List<(string Kind, Dictionary<string, object?> Entry)> CollectEntries(
        Dictionary<string, object?> cfg) =>
        ConfigStore.GetList(cfg, "providers")
            .OfType<Dictionary<string, object?>>()
            .Select(p => (p.TryGetValue("kind", out var k) && k is string ks ? ks : "", p))
            .ToList();

    private static ProviderResult BlankResult(string kind, Dictionary<string, object?> entry)
    {
        var name = entry.TryGetValue("name", out var n) && n is string ns && ns.Length > 0
            ? ns : $"{kind}-provider";
        return new ProviderResult
        {
            Id = entry.TryGetValue("id", out var i) && i is string ids ? ids : null,
            Name = name,
            Type = kind,
            Kind = kind,
            UpdatedAt = Http.Now(),
        };
    }

    private static ProviderResult Failed(string kind, Dictionary<string, object?> entry, Exception e)
    {
        var res = BlankResult(kind, entry);
        res.Error = $"{e.GetType().Name}: {e.Message}";
        res.Level = Levels.Error;
        return res;
    }

    private static ProviderResult Paused(string kind, Dictionary<string, object?> entry)
    {
        var res = BlankResult(kind, entry);
        res.Detail = "已暂停轮询";
        res.Paused = true;
        res.Level = Levels.Paused;
        return res;
    }

    private static ProviderResult Cancelled(string kind, Dictionary<string, object?> entry)
    {
        var res = BlankResult(kind, entry);
        res.Detail = "已退出,本轮未拉取";
        res.Level = Levels.Paused;
        return res;
    }

    /// <summary>
    /// 取明文 key:优先内存态 key,否则解 key_enc(磁盘态兜底)。
    /// key_enc 存在但解密失败时抛 KeyDecryptError,与"未配置"区分开。
    /// </summary>
    public static string ResolveKey(Dictionary<string, object?> entry)
    {
        var key = entry.TryGetValue("key", out var k) && k is string ks ? ks : "";
        if (key.Length > 0 || !entry.TryGetValue("key_enc", out var enc) ||
            enc is not string encS || encS.Length == 0)
            return key;
        var resolved = ConfigStore.PlainKey(entry);
        if (resolved.Length == 0)
            throw new KeyDecryptError("key_enc 解密失败,请在设置里重新填写 key");
        return resolved;
    }

    /// <summary>v2 entry → 适配器期望的 legacy 形态,key 由调用方解好。</summary>
    private static GenericOpenAi.LegacyEntry ToLegacyEntry(
        Dictionary<string, object?> p, string key)
    {
        var extra = p.TryGetValue("extra", out var ex) && ex is Dictionary<string, object?> exd
            ? exd.Where(kv => kv.Key is not ("api_key" or "token" or "key"))
                 .ToDictionary(kv => kv.Key, kv => kv.Value)
            : [];
        var raw = new Dictionary<string, object?>(extra);
        foreach (var f in new[] { "quota_per_usd", "new_api_user_id", "headers" })
            if (p.TryGetValue(f, out var v))
                raw[f] = v;

        var baseUrl = p.TryGetValue("base_url", out var bu) && bu is string bus ? bus : null;
        var name = p.TryGetValue("name", out var nm) && nm is string nms ? nms : null;
        return new GenericOpenAi.LegacyEntry(name, key, baseUrl ?? "", raw);
    }

    private static double Num(object? value, double fallback)
    {
        if (value is null) return fallback;
        try { return Convert.ToDouble(value); }
        catch { return fallback; }
    }

    /// <summary>
    /// 单条拉取:解 key → 未配置/占位判定 → 适配器 → 等级判定。
    /// 异常只影响本行,不外抛。
    /// </summary>
    public static async Task<ProviderResult> FetchOneAsync(
        string kind, Dictionary<string, object?> entry,
        Dictionary<string, object?> cfg, CancellationToken ct = default)
    {
        var result = BlankResult(kind, entry);
        string key;
        try
        {
            key = ResolveKey(entry);
        }
        catch (KeyDecryptError e)
        {
            result.Error = e.Message;
            result.Level = Levels.Error;
            return result;
        }
        var extra = entry.TryGetValue("extra", out var ex) && ex is Dictionary<string, object?> exd
            ? exd : [];
        var loginCreds = extra.TryGetValue("email", out var em) && em is string ems && ems.Length > 0 &&
                         extra.TryGetValue("password", out var pw) && pw is string pws && pws.Length > 0;
        if (PlaceholderKeys.Contains(key)) key = "";
        if (key.Length == 0 && !loginCreds)
        {
            result.Error = "未配置 key";
            result.Unconfigured = true;
            result.Level = Levels.Unconfigured;
            return result;
        }
        if (!Adapters.TryGetValue(kind, out var adapter))
        {
            result.Error = $"未知 provider kind: {kind}";
            result.Level = Levels.Error;
            return result;
        }
        try
        {
            var legacy = ToLegacyEntry(entry, key);
            var payload = await adapter(legacy, ct);
            result.Merge(payload);
            result.UpdatedAt = Http.Now();
            result.Level = ComputeLevel(result, entry, cfg);
        }
        catch (OperationCanceledException)
        {
            return Cancelled(kind, entry);
        }
        catch (Exception e)
        {
            result.Error = $"{e.GetType().Name}: {e.Message}";
            result.Level = Levels.Error;
        }
        return result;
    }

    /// <summary>
    /// 并发拉取所有 provider(等价 Python fetch_all)。
    /// 返回顺序与 cfg["providers"] 一致;skipNames 里的行返回 paused。
    /// </summary>
    public static async Task<List<ProviderResult>> FetchAllAsync(
        Dictionary<string, object?> cfg,
        IEnumerable<string>? skipNames = null,
        CancellationToken ct = default)
    {
        var entries = CollectEntries(cfg);
        if (entries.Count == 0) return [];
        var skip = skipNames?.ToHashSet() ?? new HashSet<string>();
        var todo = entries.Where(e =>
            !(e.Entry.TryGetValue("name", out var n) && n is string ns && skip.Contains(ns)))
            .ToList();

        var byName = new Dictionary<string, ProviderResult>();
        if (todo.Count > 0)
        {
            using var sem = new SemaphoreSlim(MaxConcurrent);
            var tasks = todo.Select(async t =>
            {
                await sem.WaitAsync(ct);
                try
                {
                    ct.ThrowIfCancellationRequested();
                    return (t.Entry, await FetchOneAsync(t.Kind, t.Entry, cfg, ct));
                }
                catch (OperationCanceledException)
                {
                    return (t.Entry, Cancelled(t.Kind, t.Entry));
                }
                catch (Exception e)
                {
                    return (t.Entry, Failed(t.Kind, t.Entry, e));
                }
                finally
                {
                    sem.Release();
                }
            }).ToList();
            var results = await Task.WhenAll(tasks);
            foreach (var (entry, res) in results)
            {
                var name = entry.TryGetValue("name", out var n) && n is string ns ? ns : "";
                byName[name] = res;
            }
        }
        foreach (var (kind, entry) in entries)
        {
            var name = entry.TryGetValue("name", out var n) && n is string ns ? ns : "";
            if (skip.Contains(name))
                byName[name] = Paused(kind, entry);
        }
        return entries.Select(e =>
        {
            var name = e.Entry.TryGetValue("name", out var n) && n is string ns ? ns : "";
            return byName.TryGetValue(name, out var r) ? r : Failed(e.Kind, e.Entry,
                new InvalidOperationException("拉取任务未返回结果"));
        }).ToList();
    }

    /// <summary>
    /// 阈值判定(端口自 _level):
    /// - ¥ 绝对额:alert.critical_amount_yuan(默认 5.0),剩余低于它 = critical
    /// - 有 pct 的(不论 unit):按 alert.warn_pct(默认 30)判定,低于 = warn。
    ///   不按 unit 白名单过滤——美元计额的 provider 才是主要监控对象。
    /// - 拿不到 pct 的(只报绝对金额的 $ provider):保持 ok
    /// </summary>
    public static string ComputeLevel(
        ProviderResult res, Dictionary<string, object?> entry,
        Dictionary<string, object?> cfg)
    {
        if (res.Error is not null)
            return res.Unconfigured ? Levels.Unconfigured : Levels.Error;
        var alert = cfg.TryGetValue("alert", out var a) && a is Dictionary<string, object?> ad
            ? ad : [];
        if (res.Unit == "¥")
        {
            var crit = Num(alert.TryGetValue("critical_amount_yuan", out var c) ? c : null, 5.0);
            if (res.Remaining is null) return Levels.Ok;
            return res.Remaining <= crit ? Levels.Critical : Levels.Ok;
        }
        if (res.Pct is not null)
        {
            var warn = Num(alert.TryGetValue("warn_pct", out var w) ? w : null, 30.0);
            return res.Pct <= warn ? Levels.Warn : Levels.Ok;
        }
        return Levels.Ok;
    }
}
