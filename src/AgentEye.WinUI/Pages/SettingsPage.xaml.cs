using AgentEye.Core.Config;
using AgentEye.Core.Providers;
using AgentEye.WinUI.Services;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Controls.Primitives;
using Microsoft.UI.Xaml.Input;

namespace AgentEye.WinUI.Pages;

/// <summary>
/// 设置页:外观 / 告警 / API 管理(列表 ↔ 表单同窗切换)。
/// 表单只暴露 url / key / model;名称自动取 URL 域名,kind 由 key/URL 形态
/// 推断(新增时),其余高级字段走 config 文件。契约:provider 名称唯一;
/// 删除要输入名称确认;key 留空则沿用已存。
/// </summary>
public sealed partial class SettingsPage : UserControl
{
    private readonly AppServices _app;
    private readonly MainWindow _main;
    private Dictionary<string, object?>? _editing; // 非 null = 编辑模式
    private bool _loading;                          // 回显期间不触发保存

    public SettingsPage(AppServices app, MainWindow main)
    {
        InitializeComponent();
        _app = app;
        _main = main;
        LoadGeneral();
        ReloadList();
        app.ConfigSaved += ReloadList;
        Unloaded += (_, _) => app.ConfigSaved -= ReloadList;
    }

    /// <summary>每次切到设置页:表单收回列表态,通用区回显最新 cfg。</summary>
    public void OnShown()
    {
        ShowListPane();
        LoadGeneral();
        ReloadList();
    }

    // ------------------------------------------------------------------
    // 外观 / 告警(轮询周期走 config,不在 UI 暴露)
    // ------------------------------------------------------------------

    private void LoadGeneral()
    {
        _loading = true;
        try
        {
            ThemeChoice.SelectedIndex = _app.ThemeChoice switch
            {
                "dark" => 0, "light" => 1, _ => 2,
            };
            var alert = _app.AlertDict();
            AlertEnable.IsOn = alert.TryGetValue("enable", out var en) && en is true;
            WarnPctBox.Value = alert.TryGetValue("warn_pct", out var w) ? Convert.ToDouble(w) : 30;
            CriticalYuanBox.Value = alert.TryGetValue("critical_amount_yuan", out var c)
                ? Convert.ToDouble(c) : 5.0;
        }
        finally
        {
            _loading = false;
        }
    }

    private void Theme_Changed(object sender, SelectionChangedEventArgs e)
    {
        if (_loading) return;
        var choice = ThemeChoice.SelectedIndex switch { 0 => "dark", 1 => "light", _ => "auto" };
        _app.SetThemeChoice(choice);
        _main.ApplyTheme(choice);
        _app.TrySaveCfg();
        _main.RefreshOverviewPalette();
    }

    private void AlertToggle_Changed(object sender, RoutedEventArgs e)
    {
        if (_loading) return;
        ApplyAlert();
    }

    private void AlertNum_Changed(NumberBox sender, NumberBoxValueChangedEventArgs args)
    {
        if (_loading) return;
        ApplyAlert();
    }

    private void ApplyAlert()
    {
        var alert = _app.AlertDict();
        alert["enable"] = AlertEnable.IsOn;
        alert["warn_pct"] = (int)Math.Clamp(WarnPctBox.Value, 0, 100);
        alert["critical_amount_yuan"] = Math.Max(0, CriticalYuanBox.Value);
        _app.TrySaveCfg();
    }

    // ------------------------------------------------------------------
    // API 管理:列表
    // ------------------------------------------------------------------

    private void ReloadList()
    {
        var list = new List<string>();
        foreach (var p in _app.Providers().OfType<Dictionary<string, object?>>())
        {
            var name = p.TryGetValue("name", out var n) ? n : "?";
            var kind = p.TryGetValue("kind", out var k) ? k : "?";
            list.Add($"{name}    [{kind}]");
        }
        var selected = ProviderList.SelectedIndex;
        ProviderList.ItemsSource = list;
        if (selected >= 0 && selected < list.Count)
            ProviderList.SelectedIndex = selected;
    }

    private Dictionary<string, object?>? SelectedProvider()
    {
        var idx = ProviderList.SelectedIndex;
        if (idx < 0) return null;
        var arr = _app.Providers().OfType<Dictionary<string, object?>>().ToList();
        return idx < arr.Count ? arr[idx] : null;
    }

    private async void ProviderList_DoubleTapped(object sender, DoubleTappedRoutedEventArgs e)
    {
        var p = SelectedProvider();
        if (p is not null) EditProvider(TryGetName(p));
    }

    private async void BtnEdit_Click(object sender, RoutedEventArgs e)
    {
        var p = SelectedProvider();
        if (p is null) return;
        EditProvider(TryGetName(p));
    }

    private async void BtnDelete_Click(object sender, RoutedEventArgs e)
    {
        var p = SelectedProvider();
        if (p is null) return;
        await ConfirmDeleteAsync(_app, this, TryGetName(p));
    }

    private static string TryGetName(Dictionary<string, object?> p) =>
        p.TryGetValue("name", out var n) && n is string ns ? ns : "";

    /// <summary>危险删除:输入 provider 名称确认(对齐 Python confirm_delete)。</summary>
    public static async Task ConfirmDeleteAsync(
        AppServices app, FrameworkElement host, string name)
    {
        var input = new TextBox { PlaceholderText = $"输入 {name} 以确认" };
        var dialog = new ContentDialog
        {
            XamlRoot = host.XamlRoot,
            Title = $"删除 {name}",
            Content = new StackPanel
            {
                Spacing = 8,
                Children =
                {
                    new TextBlock
                    {
                        Text = "此操作会从配置里移除该 provider 与其 key。",
                        TextWrapping = TextWrapping.Wrap,
                    },
                    input,
                },
            },
            PrimaryButtonText = "删除",
            CloseButtonText = "取消",
            DefaultButton = ContentDialogButton.Close,
        };
        var result = await dialog.ShowAsync();
        if (result != ContentDialogResult.Primary) return;
        if (input.Text.Trim() != name) return;
        var providers = ConfigStore.GetList(app.Cfg, "providers");
        var target = providers.OfType<Dictionary<string, object?>>()
            .FirstOrDefault(p => TryGetName(p) == name);
        if (target is null) return;
        providers.Remove(target);
        app.Paused.Remove(name);
        if (!app.TrySaveCfg())
            return; // 写盘失败:列表不动,让用户看到配置没存下来
        try
        {
            var baseUrl = target.TryGetValue("base_url", out var b) && b is string bs ? bs : "";
            app.Cache.RemoveProviderEntries(baseUrl, PlainKeyOf(target));
            app.Cache.LogProviderDeleted(name, baseUrl);
        }
        catch { /* 缓存清理失败不拦删除主流程 */ }
        app.SetResults(app.Results.Where(r => r.Name != name).ToList());
        _ = app.Poller.RefreshNowAsync();
    }

    private static string PlainKeyOf(Dictionary<string, object?> p) => ConfigStore.PlainKey(p);

    // ------------------------------------------------------------------
    // API 管理:表单(添加 / 编辑)
    // ------------------------------------------------------------------

    public void OpenAddForm()
    {
        _editing = null;
        ClearForm();
        ShowFormPane();
    }

    public void EditProvider(string name)
    {
        var p = _app.FindProviderByName(name);
        if (p is null) return;
        _editing = p;
        LoadForm(p);
        ShowFormPane();
    }

    private void BtnAdd_Click(object sender, RoutedEventArgs e) => OpenAddForm();

    private void BtnCancel_Click(object sender, RoutedEventArgs e) => ShowListPane();

    private void ShowFormPane()
    {
        ListPane.Visibility = Visibility.Collapsed;
        FormPane.Visibility = Visibility.Visible;
        FormError.Visibility = Visibility.Collapsed;
    }

    private void ShowListPane()
    {
        _editing = null;
        FormPane.Visibility = Visibility.Collapsed;
        ListPane.Visibility = Visibility.Visible;
        ReloadList();
    }

    private void ClearForm()
    {
        FBaseUrl.Text = "";
        FKey.Text = "";
        FModel.Text = "";
    }

    private void LoadForm(Dictionary<string, object?> p)
    {
        _loading = true;
        try
        {
            ClearForm();
            FBaseUrl.Text = p.TryGetValue("base_url", out var b) && b is string bs ? bs : "";
            // key 留空 = 沿用已存(明文/密文都行,保存时解好放内存)
            FKey.Text = AppServices.PlainKey(p);
            FModel.Text = p.TryGetValue("model", out var m) && m is string ms ? ms : "";
        }
        finally
        {
            _loading = false;
        }
    }

    private void ShowFormError(string? msg)
    {
        if (msg is null)
        {
            FormError.Visibility = Visibility.Collapsed;
            return;
        }
        FormError.Text = msg;
        FormError.Visibility = Visibility.Visible;
    }

    private async void BtnSave_Click(object sender, RoutedEventArgs e)
    {
        var baseUrl = FBaseUrl.Text.Trim();
        var key = FKey.Text.Trim();
        var model = FModel.Text.Trim();

        if (baseUrl.Length == 0)
        {
            ShowFormError("Base URL 不能为空");
            return;
        }

        // 名称自动取 URL 域名,重名追加 -2/-3;编辑时保持原名不变
        // (改名会让暂停集合与托盘最紧张行的索引错位)
        var name = _editing is not null ? TryGetName(_editing)
            : UniqueName(NameFromUrl(baseUrl));

        Dictionary<string, object?> entry;
        if (_editing is not null)
        {
            entry = _editing;
        }
        else
        {
            entry = new Dictionary<string, object?>
            {
                ["id"] = Guid.NewGuid().ToString("N")[..12],
                ["extra"] = new Dictionary<string, object?>(),
            };
            ConfigStore.GetList(_app.Cfg, "providers").Add(entry);
        }

        // key 处理:留空则沿用内存里已有的;env 覆盖在 ApplyEnvV2。
        var existingKey = AppServices.PlainKey(entry);
        var newKey = key.Length > 0 ? key
            : existingKey.Length > 0 ? existingKey
            : "";
        if (_editing is null)
        {
            // kind 只在新增时推断;已有条目改 kind 会破坏 extra 语义,走 config
            entry["kind"] = Detect.Run(key: key, hintUrl: baseUrl).Kind;
        }
        entry["name"] = name;
        entry["base_url"] = baseUrl;
        if (newKey.Length > 0)
            entry["key"] = newKey;
        SetOrRemove(entry, "model", model);
        entry.Remove("_key_from_env");

        var err = _app.SaveCfgError();
        if (err is not null)
        {
            // 写盘失败:把刚加的新条目回滚,别让内存态和磁盘态分叉
            if (_editing is null) ConfigStore.GetList(_app.Cfg, "providers").Remove(entry);
            ShowFormError($"保存失败:{err}");
            return;
        }
        ShowListPane();
        _ = _app.Poller.RefreshNowAsync();
        await Task.CompletedTask;
    }

    /// <summary>URL → 展示名:优先域名,畸形输入退化为最后一段。</summary>
    private static string NameFromUrl(string baseUrl)
    {
        if (Uri.TryCreate(baseUrl, UriKind.Absolute, out var u) && u.Host.Length > 0)
            return u.Host;
        var tail = baseUrl.Trim().TrimEnd('/').Split('/').LastOrDefault() ?? "";
        return tail.Length > 0 ? tail : "provider";
    }

    /// <summary>域名撞车时追加 -2/-3,保证 provider 名称唯一。</summary>
    private string UniqueName(string baseName)
    {
        var candidate = baseName;
        for (var n = 2; _app.FindProviderByName(candidate) is not null; n++)
            candidate = $"{baseName}-{n}";
        return candidate;
    }

    private static void SetOrRemove(Dictionary<string, object?> d, string key, string value)
    {
        if (value.Length > 0) d[key] = value;
        else d.Remove(key);
    }
}
