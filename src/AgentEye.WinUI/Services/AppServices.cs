using AgentEye.Core.Cache;
using AgentEye.Core.Config;
using AgentEye.Core.Providers;

namespace AgentEye.WinUI.Services;

/// <summary>
/// 应用级中心状态:配置仓库、轮询服务、暂停集合、主题。
/// 对齐 Python 版 main.build_actions 的装配面——UI 层只从这里拿能力,
/// 不直接摸 Core 细节。
/// </summary>
public sealed class AppServices
{
    public static AppServices Instance { get; private set; } = null!;

    public ConfigStore Store { get; }
    public CacheStore Cache { get; }
    public Dictionary<string, object?> Cfg { get; private set; }
    public HashSet<string> Paused { get; } = new();
    public List<ProviderResult> Results { get; private set; } = [];
    public LoadOutcome? LastOutcome { get; private set; }

    public PollerService Poller { get; }
    public NotifyService Notify { get; }
    public UpdateService Update { get; }

    /// <summary>每轮刷新完成后触发(UI 线程)。</summary>
    public event Action? ResultsChanged;
    /// <summary>配置保存成功后触发(设置页回显等)。</summary>
    public event Action? ConfigSaved;

    public AppServices()
    {
        Instance = this;
        Store = new ConfigStore();
        Cache = CacheStore.Default;
        try
        {
            LastOutcome = Store.LoadV2();
            Cfg = LastOutcome.Config;
        }
        catch (ConfigError)
        {
            // 配置不可用(读锁等):按空配置跑,禁止任何写盘,等用户处理
            Cfg = ConfigStore.Template();
        }
        Poller = new PollerService(this);
        Notify = new NotifyService();
        Update = new UpdateService(this);
    }

    public bool TrySaveCfg()
    {
        try
        {
            Store.SaveV2(Cfg);
            ConfigSaved?.Invoke();
            return true;
        }
        catch (ConfigError)
        {
            // 写盘失败转 UI 提示,不让调用方以为"界面变了就存下来了"
            return false;
        }
    }

    public string? SaveCfgError()
    {
        try
        {
            Store.SaveV2(Cfg);
            ConfigSaved?.Invoke();
            return null;
        }
        catch (ConfigError e)
        {
            return e.Message;
        }
    }

    public void SetResults(List<ProviderResult> results)
    {
        Results = results;
        ResultsChanged?.Invoke();
    }

    public string ThemeChoice =>
        Cfg.TryGetValue("ui", out var u) && u is Dictionary<string, object?> ui &&
        ui.TryGetValue("theme", out var t) && t is string ts ? ts : "auto";

    public void SetThemeChoice(string choice)
    {
        var ui = UiDict();
        ui["theme"] = choice;
    }

    public Dictionary<string, object?> UiDict()
    {
        if (Cfg.TryGetValue("ui", out var u) && u is Dictionary<string, object?> ui)
            return ui;
        var fresh = (Dictionary<string, object?>)ConfigStore.Template()["ui"]!;
        Cfg["ui"] = fresh;
        return fresh;
    }

    public Dictionary<string, object?> AlertDict()
    {
        if (Cfg.TryGetValue("alert", out var a) && a is Dictionary<string, object?> ad)
            return ad;
        var fresh = (Dictionary<string, object?>)ConfigStore.Template()["alert"]!;
        Cfg["alert"] = fresh;
        return fresh;
    }

    public List<object?> Providers() => ConfigStore.GetList(Cfg, "providers");

    /// <summary>provider 名称必须唯一:返回重名条目(用于添加/编辑校验)。</summary>
    public Dictionary<string, object?>? FindProviderByName(string? name)
    {
        if (string.IsNullOrEmpty(name)) return null;
        return Providers().OfType<Dictionary<string, object?>>()
            .FirstOrDefault(p => p.TryGetValue("name", out var n) && n as string == name);
    }

    public static string PlainKey(Dictionary<string, object?> p) => ConfigStore.PlainKey(p);
}
