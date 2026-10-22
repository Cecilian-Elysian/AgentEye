using AgentEye.WinUI.Pages;
using AgentEye.WinUI.Services;
using AgentEye.WinUI.Tray;
using AgentEye.WinUI.Widget;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using System.Runtime.InteropServices;
using WinRT.Interop;
using Windows.Graphics;

namespace AgentEye;

/// <summary>
/// 主窗口:Acrylic 背板 + 紧凑单窗(图标头部,无导航栏;总览/设置靠可见性切换)。
/// 装配面:配置加载、轮询启动、托盘与小组件挂载、几何持久化。
/// </summary>
public sealed partial class MainWindow : Window
{
    /// <summary>
    /// 窗口尺寸契约(物理像素,与 config 存的 ui.width/height 同源):
    /// 420×560 是主尺寸(用户确认的紧凑面板),其余尺寸靠自适应布局兜住,
    /// 最小/最大用来防止拖到布局撑不住的极端尺寸。
    /// </summary>
    private const int DefaultWidth = 420, DefaultHeight = 560;
    private const int MinWidth = 320, MinHeight = 400;
    private const int MaxWidth = 800, MaxHeight = 1200;

    private const uint WM_GETMINMAXINFO = 0x0024;

    [StructLayout(LayoutKind.Sequential)]
    private struct POINT { public int X, Y; }

    [StructLayout(LayoutKind.Sequential)]
    private struct MINMAXINFO
    {
        public POINT ptReserved;
        public POINT ptMaxSize;
        public POINT ptMaxPosition;
        public POINT ptMinTrackSize;
        public POINT ptMaxTrackSize;
    }

    [UnmanagedFunctionPointer(CallingConvention.Winapi)]
    private delegate nint SUBCLASSPROC(
        nint hWnd, uint uMsg, nint wParam, nint lParam, nuint uIdSubclass, nint dwSubclassParam);

    [DllImport("comctl32.dll")]
    private static extern bool SetWindowSubclass(
        nint hWnd, SUBCLASSPROC pfnSubclass, nuint uIdSubclass, nuint dwSubclassParam);

    [DllImport("comctl32.dll")]
    private static extern bool RemoveWindowSubclass(
        nint hWnd, SUBCLASSPROC pfnSubclass, nuint uIdSubclass);

    [DllImport("comctl32.dll")]
    private static extern nint DefSubclassProc(
        nint hWnd, uint uMsg, nint wParam, nint lParam);

    // 委托必须一直存活,否则被 GC 回收后子类化失效
    private static readonly SUBCLASSPROC SizeConstraintCallback = SizeConstraintProc;
    private bool _subclassed;

    private static nint SizeConstraintProc(
        nint hWnd, uint msg, nint wParam, nint lParam, nuint id, nint param)
    {
        if (msg == WM_GETMINMAXINFO && lParam != nint.Zero)
        {
            try
            {
                var mmi = Marshal.PtrToStructure<MINMAXINFO>(lParam);
                mmi.ptMinTrackSize = new POINT { X = MinWidth, Y = MinHeight };
                mmi.ptMaxTrackSize = new POINT { X = MaxWidth, Y = MaxHeight };
                Marshal.StructureToPtr(mmi, lParam, false);
            }
            catch { /* 结构写失败:保持系统默认限制 */ }
        }
        return DefSubclassProc(hWnd, msg, wParam, lParam);
    }

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

        // 限制拖拽范围(最小/最大),避免拖到布局撑不住的极端尺寸
        ApplySizeConstraints();

        // 几何恢复(ui.x/y/width/height)
        RestoreGeometry();

        Closed += (_, _) => OnClosed();
    }

    /// <summary>给窗口挂 WM_GETMINMAXINFO 子类,限制最小/最大尺寸。</summary>
    private void ApplySizeConstraints()
    {
        try
        {
            var hwnd = WinRT.Interop.WindowNative.GetWindowHandle(this);
            if (hwnd == nint.Zero) return;
            _subclassed = SetWindowSubclass(hwnd, SizeConstraintCallback, 1, 0);
        }
        catch { /* comctl32 不可用:退化成无限制,布局本身已自适应 */ }
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

        // 标题栏右侧留白 = 物理像素换算 DIP,别硬编码
        try
        {
            HeaderButtons.Margin = new Thickness(
                0, 0, AppWindow.TitleBar.RightInset / Root.XamlRoot.RasterizationScale, 0);
        }
        catch { /* XamlRoot 未就绪等:忽略,按钮区右侧留白稍宽无碍 */ }

        // 启动静默检查更新(同一自然日只查一次);发现新版弹一次 toast
        _ = Task.Run(async () =>
        {
            try
            {
                if (!_app.Update.ShouldCheckNow()) return;
                await _app.Update.CheckAsync(silent: true);
            }
            catch { /* 增强面:静默失败 */ }
        });
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
        BtnBack.Visibility = tag == "settings" ? Visibility.Visible : Visibility.Collapsed;
        AppTitle.Text = tag == "overview" ? "AgentEye" : "AgentEye — 设置";
    }

    // ---------------- 头部图标按钮 ----------------

    private void BtnPause_Click(object sender, RoutedEventArgs e)
    {
        var paused = _app.Poller.ToggleGlobalPause();
        if (!paused) _ = _app.Poller.RefreshNowAsync();
        SyncPauseGlyph();
    }

    private void BtnRefresh_Click(object sender, RoutedEventArgs e)
        => _ = _app.Poller.RefreshNowAsync();

    private void BtnSettings_Click(object sender, RoutedEventArgs e)
        => ShowPage("settings");

    private void BtnBack_Click(object sender, RoutedEventArgs e)
        => ShowPage("overview");

    /// <summary>暂停按钮字形/提示随全局暂停态切换(托盘切了也要跟上)。</summary>
    public void SyncPauseGlyph() => DispatcherQueue.TryEnqueue(() =>
    {
        var paused = _app.Poller.IsGloballyPaused;
        PauseIcon.Glyph = paused ? "\uE768" : "\uE769";
        ToolTipService.SetToolTip(BtnPause, paused ? "恢复轮询" : "暂停轮询");
    });

    /// <summary>托盘/外部入口:封送 UI 线程后进设置页。</summary>
    public void GoSettings() => DispatcherQueue.TryEnqueue(() => ShowPage("settings"));

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

    public void RestoreFromTray() => DispatcherQueue.TryEnqueue(() =>
    {
        Activate();
        AppWindow.Show();
        SetForegroundWindow(WindowNative.GetWindowHandle(this));
    });

    public void ToggleWidget() => DispatcherQueue.TryEnqueue(() =>
    {
        if (WidgetVisible) HideWidget();
        else ShowWidget();
    });

    /// <summary>数值容错:JSON 里 int/double 都收(Python 版写的是 int,老配置不能被丢弃)。</summary>
    private static double? AsNum(object? v)
    {
        if (v is null) return null;
        try
        {
            var d = Convert.ToDouble(v, System.Globalization.CultureInfo.InvariantCulture);
            return double.IsNaN(d) || double.IsInfinity(d) ? null : d;
        }
        catch { return null; }
    }

    private void RestoreGeometry()
    {
        var ui = _app.UiDict();
        // 主尺寸 420×560;恢复时夹到允许范围(其它尺寸都自适应)
        var wv = AsNum(ui.TryGetValue("width", out var wRaw) ? wRaw : null);
        var w = wv is double dw && dw >= MinWidth
            ? (int)Math.Clamp(dw, MinWidth, MaxWidth) : DefaultWidth;
        var hv = AsNum(ui.TryGetValue("height", out var hRaw) ? hRaw : null);
        var h = hv is double dh && dh >= MinHeight
            ? (int)Math.Clamp(dh, MinHeight, MaxHeight) : DefaultHeight;
        AppWindow.Resize(new SizeInt32(w, h));
        var xv = AsNum(ui.TryGetValue("x", out var xRaw) ? xRaw : null);
        var yv = AsNum(ui.TryGetValue("y", out var yRaw) ? yRaw : null);
        if (xv is double dx && yv is double dy &&
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
        // 卸掉窗口子类(句柄即将失效)
        try
        {
            if (_subclassed)
            {
                var hwnd = WinRT.Interop.WindowNative.GetWindowHandle(this);
                if (hwnd != nint.Zero)
                    RemoveWindowSubclass(hwnd, SizeConstraintCallback, 1);
                _subclassed = false;
            }
        }
        catch { /* 静默 */ }
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
