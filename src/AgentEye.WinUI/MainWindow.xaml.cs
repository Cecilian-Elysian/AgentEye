using AgentEye.WinUI.Pages;
using AgentEye.WinUI.Services;
using AgentEye.WinUI.Tray;
using AgentEye.WinUI.Widget;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using WinRT.Interop;
using Windows.Graphics;

namespace AgentEye;

/// <summary>
/// 主窗口:Mica 背板 + NavigationView 导航壳(总览/设置)。
/// 装配面:配置加载、轮询启动、托盘与小组件挂载、几何持久化。
/// </summary>
public sealed partial class MainWindow : Window
{
    private readonly AppServices _app = new();
    private OverviewPage? _overview;
    private SettingsPage? _settings;
    private TrayIconService? _tray;
    private WidgetWindow? _widget;
    private bool _closed;

    public MainWindow()
    {
        InitializeComponent();
        ExtendsContentIntoTitleBar = true;
        SetTitleBar(AppTitleBar);

        // 主题:加载即应用(ui.theme)
        ApplyTheme(_app.ThemeChoice);

        // 几何恢复(ui.x/y/width/height)
        RestoreGeometry();

        Closed += (_, _) => OnClosed();
    }

    private void Root_Loaded(object sender, RoutedEventArgs e)
    {
        // 首次进总览页并启动轮询(放 Loaded:DispatcherQueue 就绪)
        _overview = new OverviewPage(_app, this);
        _settings = new SettingsPage(_app, this);
        PageHost.Children.Add(_overview);
        PageHost.Children.Add(_settings);
        ShowPage("overview");

        _app.Poller.Start();

        // 空配置首启也刷一轮:让"未配置"空态立刻可见
        _ = _app.Poller.RefreshNowAsync();

        // 托盘常驻;失败静默降级(不把主流程带崩)
        try
        {
            _tray = new TrayIconService(_app, this);
        }
        catch { _tray = null; }

        // 小组件按 ui.widget 恢复
        try
        {
            if (_app.UiDict().TryGetValue("widget", out var w) && w is true)
                ShowWidget();
        }
        catch { /* 增强面,失败静默 */ }

        // 主题跟随系统:auto 时系统切换会触发这里,同步按钮配色即可,
        // 页面/小组件各自监听 ActualThemeChanged 重渲染
        Root.ActualThemeChanged += (_, _) => SyncCaptionButtons();
    }

    public void ApplyTheme(string choice)
    {
        Root.RequestedTheme = choice switch
        {
            "dark" => ElementTheme.Dark,
            "light" => ElementTheme.Light,
            _ => ElementTheme.Default,
        };
        // caption 按钮字形颜色跟系统主题,不跟 Root.RequestedTheme,
        // 必须手动同步(否则系统深色+选浅色 → 浅底白按钮看不见)
        SyncCaptionButtons();
        _widget?.ApplyTheme(choice);
    }

    private void SyncCaptionButtons()
    {
        try
        {
            var light = Root.ActualTheme == ElementTheme.Light;
            var bar = AppWindow.TitleBar;
            var fg = light
                ? Windows.UI.Color.FromArgb(255, 0x1A, 0x1A, 0x1A)
                : Windows.UI.Color.FromArgb(255, 0xFF, 0xFF, 0xFF);
            var hoverBg = light
                ? Windows.UI.Color.FromArgb(0x14, 0x00, 0x00, 0x00)
                : Windows.UI.Color.FromArgb(0x14, 0xFF, 0xFF, 0xFF);
            bar.ButtonForegroundColor = fg;
            bar.ButtonHoverForegroundColor = fg;
            bar.ButtonPressedForegroundColor = fg;
            bar.ButtonInactiveForegroundColor = fg;
            bar.ButtonBackgroundColor = Microsoft.UI.Colors.Transparent;
            bar.ButtonInactiveBackgroundColor = Microsoft.UI.Colors.Transparent;
            bar.ButtonHoverBackgroundColor = hoverBg;
            bar.ButtonPressedBackgroundColor = hoverBg;
        }
        catch { /* 老系统上 TitleBar API 可能不全:静默降级 */ }
    }

    public void ShowPage(string tag)
    {
        if (_overview is null || _settings is null) return;
        _overview.Visibility = tag == "overview" ? Visibility.Visible : Visibility.Collapsed;
        _settings.Visibility = tag == "settings" ? Visibility.Visible : Visibility.Collapsed;
        _settings.OnShown();
        AppTitle.Text = tag == "overview" ? "AgentEye" : "AgentEye — 设置";
    }

    private void Nav_SelectionChanged(NavigationView sender, NavigationViewSelectionChangedEventArgs args)
    {
        if (sender.SelectedItem is NavigationViewItem item && item.Tag is string tag)
            ShowPage(tag);
    }

    public void GoSettings() => Nav.SelectedItem = Nav.MenuItems[1];

    public SettingsPage Settings => _settings!;

    public void RefreshOverviewPalette() => _overview?.RefreshPalette();

    public void ShowWidget()
    {
        if (_widget is null)
        {
            _widget = new WidgetWindow(_app, this);
            _widget.ApplyTheme(_app.ThemeChoice);
        }
        _widget.ShowBar();
    }

    public void HideWidget() => _widget?.HideBar();

    public bool WidgetVisible => _widget?.IsVisible ?? false;

    public void ToggleWidget()
    {
        if (WidgetVisible) HideWidget();
        else ShowWidget();
    }

    public void RestoreFromTray()
    {
        Activate();
        AppWindow.Show();
        SetForegroundWindow(WindowNative.GetWindowHandle(this));
    }

    private void RestoreGeometry()
    {
        var ui = _app.UiDict();
        var w = ui.TryGetValue("width", out var wd) && wd is double dw && dw >= 400 ? (int)dw : 900;
        var h = ui.TryGetValue("height", out var hd) && hd is double dh && dh >= 300 ? (int)dh : 640;
        AppWindow.Resize(new SizeInt32(w, h));
        if (ui.TryGetValue("x", out var x) && x is double dx &&
            ui.TryGetValue("y", out var y) && y is double dy &&
            dx > -10000 && dy > -10000)
        {
            try { AppWindow.Move(new PointInt32((int)dx, (int)dy)); }
            catch { /* 副屏已拔等情况:留系统默认位 */ }
        }
    }

    private void OnClosed()
    {
        if (_closed) return;
        _closed = true;
        // 几何持久化(AppWindow 物理像素直接存,恢复时同源)
        try
        {
            var ui = _app.UiDict();
            ui["x"] = (double)AppWindow.Position.X;
            ui["y"] = (double)AppWindow.Position.Y;
            ui["width"] = (double)AppWindow.Size.Width;
            ui["height"] = (double)AppWindow.Size.Height;
            _app.TrySaveCfg();
        }
        catch { /* 关窗路径绝不因写盘失败崩溃 */ }
        _widget?.Dispose();
        _tray?.Dispose();
        _app.Poller.Dispose();
    }

    [System.Runtime.InteropServices.DllImport("user32.dll")]
    private static extern bool SetForegroundWindow(nint hWnd);
}
