using System.Security.Cryptography;
using System.Text;
using AgentEye.Core.Config;
using AgentEye.Core.Providers;

namespace AgentEye.Core.Cache;

/// <summary>
/// 缓存层:模型列表(TTL 6h)+ 试调日志(append-only JSONL)+ 告警冷却。
/// 端口自 cache.py;目录默认 ~/.agenteye/cache/,与 config.json 平级。
/// 读-改-写必须串行(set_models 跑在轮询线程、排序/删除跑在 UI 线程,
/// 无锁会互相截断丢更新)。
/// </summary>
public sealed class CacheStore
{
    public const int ProbeLogMaxLines = 2000;
    public static readonly TimeSpan ModelsTtl = TimeSpan.FromHours(6);

    private static readonly Lazy<CacheStore> LazyDefault =
        new(() => new CacheStore(DefaultDir()), LazyThreadSafetyMode.ExecutionAndPublication);

    /// <summary>进程级默认实例(~/.agenteye/cache)。</summary>
    public static CacheStore Default => LazyDefault.Value;

    public static string DefaultDir()
    {
        var profile = Environment.GetEnvironmentVariable("USERPROFILE");
        if (string.IsNullOrEmpty(profile))
            profile = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
        return Path.Combine(profile, ".agenteye", "cache");
    }

    private readonly string _dir;
    private readonly object _lock = new();

    public CacheStore(string? dir = null)
    {
        _dir = dir ?? DefaultDir();
    }

    private string ModelsPath => Path.Combine(_dir, "models.json");
    private string ProbeLogPath => Path.Combine(_dir, "probe.jsonl");
    private string AlertStatePath => Path.Combine(_dir, "alert_state.json");

    private void Ensure()
    {
        Directory.CreateDirectory(_dir);
    }

    private static string Hash(string baseUrl, string apiKey)
    {
        var raw = Encoding.UTF8.GetBytes(baseUrl.TrimEnd('/') + "|" + (apiKey ?? ""));
        return Convert.ToHexString(SHA256.HashData(raw)).ToLowerInvariant()[..16];
    }

    private static Dictionary<string, object?>? LoadJson(string path)
    {
        if (!File.Exists(path)) return null;
        try
        {
            var parsed = JsonUtil.ParseObject(File.ReadAllText(path));
            return parsed;
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException)
        {
            return null;
        }
    }

    private void SaveJson(string path, Dictionary<string, object?> data)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        var payload = Encoding.UTF8.GetBytes(JsonUtil.Dump(data));
        var tmp = Path.Combine(Path.GetDirectoryName(path)!,
            $"{Path.GetFileName(path)}.{Path.GetRandomFileName()}.tmp");
        try
        {
            using (var fs = new FileStream(tmp, FileMode.Create, FileAccess.Write, FileShare.None))
            {
                fs.Write(payload);
                fs.Flush(flushToDisk: true);
            }
            File.Move(tmp, path, overwrite: true);
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

    // ------------------------------------------------------------------
    // 模型缓存
    // ------------------------------------------------------------------

    public List<string>? GetModels(string baseUrl, string apiKey, TimeSpan? ttl = null)
    {
        Ensure();
        var ttlSec = (ttl ?? ModelsTtl).TotalSeconds;
        Dictionary<string, object?>? cache;
        lock (_lock) { cache = LoadJson(ModelsPath); }
        if (cache is null) return null;
        if (!cache.TryGetValue(Hash(baseUrl, apiKey), out var entryObj) ||
            entryObj is not Dictionary<string, object?> entry)
            return null;
        if (entry.TryGetValue("fetched_at", out var fetchedObj) &&
            fetchedObj is double fetched)
        {
            if (Http.Now() - fetched > ttlSec) return null;
        }
        else return null;
        if (entry.TryGetValue("models", out var modelsObj) &&
            modelsObj is List<object?> rawModels)
        {
            var models = rawModels.OfType<string>().ToList();
            if (entry.TryGetValue("order", out var orderObj) &&
                orderObj is List<object?> orderRaw)
            {
                var order = orderRaw.OfType<string>().ToList();
                if (order.Count > 0)
                {
                    var present = models.Where(order.Contains).ToList();
                    var presentSet = present.ToHashSet();
                    var extras = models.Where(m => !presentSet.Contains(m)).ToList();
                    return order.Where(presentSet.Contains).Concat(extras).ToList();
                }
            }
            return models;
        }
        return null;
    }

    public void SetModels(string baseUrl, string apiKey, List<string> models)
    {
        Ensure();
        var key = Hash(baseUrl, apiKey);
        lock (_lock)
        {
            var cache = LoadJson(ModelsPath) ?? [];
            var prev = cache.TryGetValue(key, out var p) && p is Dictionary<string, object?> pd
                ? pd : [];
            var entry = new Dictionary<string, object?>
            {
                ["models"] = models.Cast<object?>().ToList(),
                ["fetched_at"] = Http.Now(),
            };
            // 别把用户排好的顺序冲掉
            if (prev.TryGetValue("order", out var o) && o is List<object?> order && order.Count > 0)
                entry["order"] = order;
            cache[key] = entry;
            SaveJson(ModelsPath, cache);
        }
    }

    /// <summary>仅持久化排序,不更新 models 列表、不碰 fetched_at。</summary>
    public void SaveModelOrder(string baseUrl, string apiKey, List<string> order)
    {
        Ensure();
        var key = Hash(baseUrl, apiKey);
        lock (_lock)
        {
            var cache = LoadJson(ModelsPath) ?? [];
            var entry = cache.TryGetValue(key, out var p) && p is Dictionary<string, object?> pd
                ? new Dictionary<string, object?>(pd)
                : new Dictionary<string, object?> { ["models"] = new List<object?>(), ["fetched_at"] = Http.Now() };
            var models = entry.TryGetValue("models", out var m) && m is List<object?> ml
                ? ml : [];
            var filtered = models.OfType<string>().Where(order.Contains).Cast<object?>().ToList();
            entry["order"] = order.Cast<object?>().ToList();
            entry.TryAdd("models", filtered);
            cache[key] = entry;
            SaveJson(ModelsPath, cache);
        }
    }

    public void InvalidateModels(string? baseUrl = null, string? apiKey = null)
    {
        Ensure();
        lock (_lock)
        {
            if (baseUrl is null && apiKey is null)
            {
                if (File.Exists(ModelsPath)) File.Delete(ModelsPath);
                return;
            }
            var cache = LoadJson(ModelsPath) ?? [];
            if (cache.Remove(Hash(baseUrl ?? "", apiKey ?? "")))
                SaveJson(ModelsPath, cache);
        }
    }

    /// <summary>从 models.json 删除该 (base_url, key) 的条目。</summary>
    public bool RemoveProviderEntries(string? baseUrl, string? apiKey)
    {
        lock (_lock)
        {
            Ensure();
            var cache = LoadJson(ModelsPath) ?? [];
            if (cache.Remove(Hash(baseUrl ?? "", apiKey ?? "")))
            {
                SaveJson(ModelsPath, cache);
                return true;
            }
            return false;
        }
    }

    // ------------------------------------------------------------------
    // 试调日志
    // ------------------------------------------------------------------

    private void SaveTextAtomic(string path, string text)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        var payload = Encoding.UTF8.GetBytes(text);
        var tmp = Path.Combine(Path.GetDirectoryName(path)!,
            $"{Path.GetFileName(path)}.{Path.GetRandomFileName()}.tmp");
        try
        {
            using (var fs = new FileStream(tmp, FileMode.Create, FileAccess.Write, FileShare.None))
            {
                fs.Write(payload);
                fs.Flush(flushToDisk: true);
            }
            File.Move(tmp, path, overwrite: true);
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

    private void TrimProbeLog()
    {
        try
        {
            lock (_lock)
            {
                if (!File.Exists(ProbeLogPath)) return;
                var lines = File.ReadAllLines(ProbeLogPath);
                if (lines.Length <= ProbeLogMaxLines) return;
                SaveTextAtomic(ProbeLogPath,
                    string.Join("\n", lines[^ProbeLogMaxLines..]) + "\n");
            }
        }
        catch (IOException) { }
        catch (UnauthorizedAccessException) { }
    }

    public void LogProbe(string providerName, string modelId, bool success,
        double latencyMs, string error = "")
    {
        Ensure();
        var line = new Dictionary<string, object?>
        {
            ["ts"] = Http.Now(),
            ["provider"] = providerName,
            ["model"] = modelId,
            ["success"] = success,
            ["latency_ms"] = latencyMs,
            ["error"] = error,
        };
        lock (_lock)
        {
            File.AppendAllText(ProbeLogPath,
                JsonUtil.DumpCompact(line) + "\n", Encoding.UTF8);
        }
        TrimProbeLog();
    }

    public void LogProviderDeleted(string providerName, string baseUrl = "")
    {
        Ensure();
        var line = new Dictionary<string, object?>
        {
            ["ts"] = Http.Now(),
            ["event"] = "provider_deleted",
            ["provider"] = providerName,
            ["base_url"] = baseUrl ?? "",
        };
        lock (_lock)
        {
            File.AppendAllText(ProbeLogPath,
                JsonUtil.DumpCompact(line) + "\n", Encoding.UTF8);
        }
    }

    public List<Dictionary<string, object?>> RecentProbes(
        string? providerName = null, int limit = 20)
    {
        Ensure();
        if (!File.Exists(ProbeLogPath)) return [];
        var lines = File.ReadAllLines(ProbeLogPath);
        var output = new List<Dictionary<string, object?>>();
        for (var i = lines.Length - 1; i >= 0 && output.Count < limit; i--)
        {
            if (lines[i].Length == 0) continue;
            var entry = JsonUtil.ParseObject(lines[i]);
            if (entry is null) continue;
            if (providerName is not null &&
                entry.TryGetValue("provider", out var p) && p is string ps &&
                ps != providerName)
                continue;
            output.Add(entry);
        }
        return output;
    }

    public Dictionary<string, object?>? LastProbe(string providerName, string modelId) =>
        RecentProbes(providerName, 200)
            .FirstOrDefault(e => e.TryGetValue("model", out var m) && m is string ms && ms == modelId);

    // ------------------------------------------------------------------
    // 告警冷却状态
    // ------------------------------------------------------------------

    /// <summary>
    /// 原子保存 per-provider 告警冷却状态,让 60 分钟冷却跨重启生效。
    /// notified 形如 {"DeepSeek": ["critical", 1758000000.0], ...}。
    /// </summary>
    public void SaveAlertState(IReadOnlyDictionary<string, (string Level, double Ts)> notified)
    {
        Ensure();
        var now = Http.Now();
        var clean = new Dictionary<string, object?>();
        foreach (var (name, (level, ts)) in notified)
        {
            if (level is not ("warn" or "critical")) continue;
            // NTP 回拨 / 手改文件都可能给出未来的时间戳:不夹取的话
            // 冷却判定会把这个 provider 静默到天荒地老
            if (ts > now + 60) continue;
            clean[name] = new List<object?> { level, ts };
        }
        lock (_lock)
        {
            SaveJson(AlertStatePath, new Dictionary<string, object?> { ["notified"] = clean });
        }
    }

    /// <summary>读取告警冷却状态。缺失、损坏或旧版单 ts 格式一律返回空表。</summary>
    public Dictionary<string, (string Level, double Ts)> LoadAlertState()
    {
        Ensure();
        var data = LoadJson(AlertStatePath);
        if (data is null ||
            !data.TryGetValue("notified", out var raw) ||
            raw is not Dictionary<string, object?> rawDict)
            return [];
        var output = new Dictionary<string, (string, double)>();
        var now = Http.Now();
        foreach (var (name, value) in rawDict)
        {
            if (value is not List<object?> pair || pair.Count != 2) continue;
            if (pair[0] is not string level || level is not ("warn" or "critical")) continue;
            if (pair[1] is not double ts) continue;
            if (ts > now + 60) continue;
            output[name] = (level, ts);
        }
        return output;
    }
}
