using AgentEye.Core.Providers;
using AgentEye.WinUI.Services;
using Microsoft.UI;
using Microsoft.UI.Windowing;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Shapes;
using Windows.Graphics;

namespace AgentEye.WinUI.Widget;

/// <summary>
/// 桌面小组件:无边框、置顶、不抢焦点(WS_EX_NOACTIVATE + WS_EX_TOOLWINDOW),
/// Acrylic 背板 + 行内 2px 等级细条,高度按行数自适应(空态 260×64)。
/// 交互契约(端口自 Python ui/widget.py):
/// - "点击 vs 拖动"在松手时判定,位移 < 4 px 视为点击唤起主面板
/// - 松手落盘位置取事件请求坐标(AppWindow.Position 回显滞后一轮,不可信)
/// - 任何 Win32 步骤失败静默降级,不把主流程带崩
/// </summary>
public sealed class WidgetWindow : IDisposable
{
    private const double Width = 260, HeightEmpty = 64;
    private const double RowHeight = 18;   // 行 15 + 细条 2 + 间隙 1

    private readonly AppServices _app;
    private readonly MainWindow _main;
    private readonly Window _window = new();
    private readonly Grid _root = new();
    private nint _hwnd;
    private bool _visible;
    private bool _disposed;
    private bool _solidFallback;   // Acrylic 建不起来(老系统)时用实底色

    // 拖动状态
    private bool _dragging;
    private PointInt32 _pressCursor;   // 按下时光标屏幕坐标
    private PointInt32 _pressWindow;   // 按下时窗口位置
    private PointInt32 _lastPos;       // 最近一次请求的窗口位置(落盘用)
    private bool _movedFar;

    [System.Runtime.InteropServices.DllImport("user32.dll")]
    private static extern nint GetWindowLongPtrW(nint hWnd, int idx);
    [System.Runtime.InteropServices.DllImport("user32.dll")]
    private static extern nint SetWindowLongPtrW(nint hWnd, int idx, nint value);
    [System.Runtime.InteropServices.DllImport("user32.dll")]
    private static extern bool GetCursorPos(out POINT pt);
    [System.Runtime.InteropServices.DllImport("user32.dll")]
    private static extern bool SetForegroundWindow(nint hWnd);

    [System.Runtime.InteropServices.StructLayout(
        System.Runtime.InteropServices.LayoutKind.Sequential)]
    private struct POINT { public int X, Y; }

    private const int GWL_EXSTYLE = -20;
    private const long WS_EX_TOOLWINDOW = 0x80;
    private const long WS_EX_NOACTIVATE = 0x08000000;

    public bool IsVisible => _visible;

    public WidgetWindow(AppServices app, MainWindow main)
    {
        _app = app;
        _main = main;

        var presenter = (OverlappedPresenter)_window.AppWindow.Presenter;
        presenter.SetBorderAndTitleBar(false, false);
        presenter.IsAlwaysOnTop = true;
        presenter.IsResizable = false;
        presenter.IsMinimizable = false;
        presenter.IsMaximizable = false;
        _window.AppWindow.Resize(new SizeInt32((int)Width, (int)HeightEmpty));
        _window.AppWindow.IsShownInSwitchers = false;

        // Acrylic 背板:老系统可能抛异常 → 实底降级(增强面契约)
        try
        {
            _window.SystemBackdrop = new DesktopAcrylicBackdrop();
        }
        catch { _solidFallback = true; }

        _hwnd = WinRT.Interop.WindowNative.GetWindowHandle(_window);
        if (_hwnd != nint.Zero)
        {
            var ex = GetWindowLongPtrW(_hwnd, GWL_EXSTYLE).ToInt64();
            SetWindowLongPtrW(_hwnd, GWL_EXSTYLE,
                new nint(ex | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE));
        }

        BuildContent();

        // 拖动/点击(松手判定,对齐 Python 契约)
        _root.PointerPressed += (_, e) =>
        {
            _dragging = true;
            _movedFar = false;
            _pressWindow = _window.AppWindow.Position;
            if (GetCursorPos(out var pt))
                _pressCursor = new PointInt32(pt.X, pt.Y);
            _root.CapturePointer(e.Pointer);
        };
        _root.PointerMoved += (_, _) =>
        {
            if (!_dragging) return;
            if (!GetCursorPos(out var pt)) return;
            var dx = pt.X - _pressCursor.X;
            var dy = pt.Y - _pressCursor.Y;
            if (Math.Abs(dx) * Math.Abs(dx) + Math.Abs(dy) * Math.Abs(dy) >= 16)
                _movedFar = true;
            var next = new PointInt32(_pressWindow.X + dx, _pressWindow.Y + dy);
            _lastPos = next;
            try { _window.AppWindow.Move(next); } catch { }
        };
        _root.PointerReleased += (_, e) =>
        {
            if (!_dragging) return;
            _dragging = false;
            _root.ReleasePointerCapture(e.Pointer);
            if (_movedFar)
            {
                PersistPos();
            }
            else
            {
                try { _main.RestoreFromTray(); } catch { }
            }
        };

        _window.Closed += (_, _) =>
        {
            // 用户没有关闭入口,这里只兜异常路径;位置照常落盘
            PersistPos();
            _visible = false;
        };

        _app.ResultsChanged += RenderRows;
        RestorePos();
    }

    // ------------------------------------------------------------------
    // 内容:标题 + 最多 3 行 provider(色点 + 名称 + 已用/剩余)
    // ------------------------------------------------------------------

    private void BuildContent()
    {
        _root.Padding = new Thickness(10, 6, 10, 6);
        _root.CornerRadius = new CornerRadius(8);
        _root.BorderThickness = new Thickness(1);
        RepaintChrome();

        var stack = new StackPanel { Spacing = 3 };
        var title = new TextBlock
        {
            Text = "AgentEye",
            FontSize = 10,
            Opacity = 0.6,
        };
        stack.Children.Add(title);
        _rowsHost = new StackPanel { Spacing = 2 };
        stack.Children.Add(_rowsHost);
        _root.Children.Add(stack);
        _window.Content = _root;

        // 系统深浅切换(auto 模式)时重涂底色 + 重渲染行
        _root.ActualThemeChanged += (_, _) =>
        {
            RepaintChrome();
            RenderRows();
        };
    }

    /// <summary>重涂底色/描边(代码画,主题切换后必须手动来)。</summary>
    private void RepaintChrome()
    {
        _root.Background = AeRes.Brush(_root, _solidFallback ? "AeCardBrush" : "AeGlassTintBrush");
        _root.BorderBrush = AeRes.BrushOrNull(_root, "AeCardStrokeBrush");
    }

    /// <summary>跟随主面板的主题选择(dark/light/auto)。</summary>
    public void ApplyTheme(string choice)
    {
        _root.RequestedTheme = choice switch
        {
            "dark" => ElementTheme.Dark,
            "light" => ElementTheme.Light,
            _ => ElementTheme.Default,
        };
        RepaintChrome();
        RenderRows();
    }

    private StackPanel _rowsHost = null!;

    private void RenderRows()
    {
        if (_disposed) return;
        var host = _rowsHost;
        if (host is null) return;
        host.Children.Clear();

        var rows = _app.Results;
        // 紧张优先(和托盘同一排序),最多 3 行
        var shown = rows
            .OrderBy(r => r.Level switch
            {
                var l when l == Levels.Critical => 0,
                var l when l == Levels.Warn => 1,
                var l when l == Levels.Ok => 2,
                var l when l == Levels.Error => 3,
                var l when l == Levels.Unconfigured => 4,
                _ => 5,
            })
            .ThenBy(r => r.Pct ?? 999)
            .Take(3)
            .ToList();
        foreach (var r in shown)
            host.Children.Add(BuildRow(r));
        if (shown.Count == 0)
        {
            host.Children.Add(new TextBlock
            {
                Text = "未接入 provider",
                FontSize = 11,
                Opacity = 0.6,
            });
        }

        // 高度随行数自适应(空态 = HeightEmpty),修旧版 3 行必裁切
        try
        {
            var h = shown.Count == 0
                ? HeightEmpty
                : 12 /*padding*/ + 13 /*title*/ + 4 /*gap*/ + shown.Count * RowHeight;
            _window.AppWindow.Resize(new SizeInt32((int)Width, (int)Math.Ceiling(h)));
        }
        catch { /* 增强面 */ }
    }

    private FrameworkElement BuildRow(ProviderResult r)
    {
        var levelKey = r.Level switch
        {
            var l when l == Levels.Critical => "AeCriticalBrush",
            var l when l == Levels.Warn => "AeWarnBrush",
            var l when l == Levels.Ok => "AeOkBrush",
            var l when l == Levels.Paused => "AePausedBrush",
            _ => "AePausedBrush",
        };
        var levelBrush = AeRes.Brush(_root, levelKey);

        var dot = new Ellipse
        {
            Width = 7,
            Height = 7,
            VerticalAlignment = VerticalAlignment.Center,
            Fill = levelBrush,
        };
        var name = new TextBlock
        {
            Text = r.Name,
            FontSize = 11,
            VerticalAlignment = VerticalAlignment.Center,
            MaxWidth = 140,
            TextTrimming = TextTrimming.CharacterEllipsis,
        };
        var value = new TextBlock
        {
            FontSize = 11,
            VerticalAlignment = VerticalAlignment.Center,
            Text = r.Level is Levels.Unconfigured ? "未配置"
                : r.Pct is not null ? $"{r.Pct:F0}%"
                : r.Remaining is not null ? $"{r.Remaining:F2} {r.Unit}"
                : "-",
        };
        var line = new Grid { ColumnSpacing = 6 };
        line.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        line.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        line.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        Grid.SetColumn(dot, 0);
        Grid.SetColumn(name, 1);
        Grid.SetColumn(value, 2);
        line.Children.Add(dot);
        line.Children.Add(name);
        line.Children.Add(value);

        // 行内 2px 等级细条(无 pct 时空轨,等级色仍由点承担)
        var bar = new ProgressBar
        {
            Height = 2,
            Minimum = 0,
            Maximum = 100,
            CornerRadius = new CornerRadius(1),
            Foreground = levelBrush,
            Background = AeRes.BrushOrNull(_root, "AeDividerBrush"),
        };
        if (r.Pct is not null) bar.Value = Math.Clamp(r.Pct.Value, 0, 100);

        return new StackPanel { Spacing = 1, Children = { line, bar } };
    }

    // ------------------------------------------------------------------
    // 显隐 + 位置
    // ------------------------------------------------------------------

    public void ShowBar()
    {
        if (_disposed) return;
        RenderRows();
        if (!_visible)
        {
            // Show(false):显示但不激活,配合 WS_EX_NOACTIVATE 做到不抢焦点
            _window.AppWindow.Show(false);
            _visible = true;
        }
    }

    public void HideBar()
    {
        if (!_visible) return;
        PersistPos();
        try { _window.AppWindow.Hide(); } catch { }
        _visible = false;
    }

    private void RestorePos()
    {
        var ui = _app.UiDict();
        if (ui.TryGetValue("widget_pos", out var p) && p is List<object?> arr &&
            arr.Count >= 2 && arr[0] is double x && arr[1] is double y)
        {
            _lastPos = new PointInt32((int)x, (int)y);
            try { _window.AppWindow.Move(_lastPos); }
            catch { /* 副屏已拔:留默认位 */ }
        }
    }

    private void PersistPos()
    {
        try
        {
            _app.UiDict()["widget_pos"] = new List<object?> { (double)_lastPos.X, (double)_lastPos.Y };
            _app.TrySaveCfg();
        }
        catch { /* 增强面 */ }
    }

    public void Dispose()
    {
        if (_disposed) return;
        _disposed = true;
        _app.ResultsChanged -= RenderRows;
        PersistPos();
        try { _window.Close(); } catch { }
    }
}
