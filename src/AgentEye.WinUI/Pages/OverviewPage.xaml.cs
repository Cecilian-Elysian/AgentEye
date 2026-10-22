using AgentEye.Core.Providers;
using AgentEye.WinUI.Services;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Shapes;

namespace AgentEye.WinUI.Pages;

/// <summary>
/// 总览页:provider 行扁平化直排在玻璃上(36px kind 图标 + 名称/主值 +
/// 3px 等级色细条 + 1px 分割线),行随刷新整批重建,
/// 对齐 Python 版 Panel 的重建语义。
/// </summary>
public sealed partial class OverviewPage : UserControl
{
    private readonly AppServices _app;
    private readonly MainWindow _main;

    public OverviewPage(AppServices app, MainWindow main)
    {
        InitializeComponent();
        _app = app;
        _main = main;
        Loaded += (_, _) =>
        {
            _app.ResultsChanged += OnResultsChanged;
            OnResultsChanged();
        };
        Unloaded += (_, _) => _app.ResultsChanged -= OnResultsChanged;
        // 系统深浅切换(auto 模式)时重渲染代码画的行
        ActualThemeChanged += (_, _) => OnResultsChanged();
    }

    /// <summary>主题切换后的调色刷新(XAML ThemeResource 自动,这里刷代码画的行)。</summary>
    public void RefreshPalette() => OnResultsChanged();

    private void OnResultsChanged()
    {
        var rows = _app.Results;
        FooterUpdated.Text = _app.Poller.LastRefresh is { } t
            ? $"上次刷新 {t:HH:mm:ss}"
            : "尚未刷新";
        FooterCount.Text = rows.Count == 0 ? "" : $"{rows.Count} 个 provider";
        EmptyState.Visibility = rows.Count == 0 ? Visibility.Visible : Visibility.Collapsed;

        RowsHost.Children.Clear();
        for (var i = 0; i < rows.Count; i++)
        {
            RowsHost.Children.Add(BuildRow(rows[i]));
            if (i < rows.Count - 1)
                RowsHost.Children.Add(new Rectangle
                {
                    Height = 1,
                    Fill = AeRes.Brush(this, "AeDividerBrush"),
                });
        }
    }

    private Brush LevelBrush(string level) => AeRes.Brush(this, level switch
    {
        Levels.Ok => "AeOkBrush",
        Levels.Warn => "AeWarnBrush",
        Levels.Critical => "AeCriticalBrush",
        Levels.Error => "AeErrorBrush",
        Levels.Unconfigured => "AePausedBrush",
        Levels.Paused => "AePausedBrush",
        _ => "AePausedBrush",
    });

    private Brush TextBrush() => AeRes.Brush(this, "AeTextPrimaryBrush");
    private Brush DimBrush() => AeRes.Brush(this, "AeTextSecondaryBrush");

    /// <summary>等级色的淡版,当进度条轨道用(0% 剩余时也能看出等级)。</summary>
    private static Brush LevelTrack(Brush level) => level is SolidColorBrush s
        ? new SolidColorBrush(Windows.UI.Color.FromArgb(48, s.Color.R, s.Color.G, s.Color.B))
        : level;

    /// <summary>kind → Segoe Fluent Icons 字形,未知 kind 落其它。</summary>
    private static string KindGlyph(string kind) => kind switch
    {
        "deepseek" => "\uE99A",
        "zhipu" => "\uE943",
        "minimax" => "\uE945",
        "opencode_go" => "\uE756",
        "relay" => "\uE968",
        _ => "\uE774",
    };

    private FrameworkElement BuildRow(ProviderResult row)
    {
        var stack = new StackPanel { Spacing = 6 };

        // 上半:36px 图标 + (名称行 / detail) + 主值
        var top = new Grid { ColumnSpacing = 10 };
        top.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(36) });
        top.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        top.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });

        var pausedBrush = AeRes.Brush(this, "AePausedBrush");
        var iconChip = new Border
        {
            Width = 36,
            Height = 36,
            CornerRadius = new CornerRadius(8),
            BorderThickness = new Thickness(1),
            BorderBrush = AeRes.Brush(this, "AeCardStrokeBrush"),
            VerticalAlignment = VerticalAlignment.Top,
            Child = new FontIcon
            {
                FontFamily = new FontFamily("Segoe Fluent Icons"),
                FontSize = 16,
                Glyph = KindGlyph(row.Kind),
                Foreground = row.Paused ? pausedBrush : DimBrush(),
            },
        };
        Grid.SetColumn(iconChip, 0);
        top.Children.Add(iconChip);

        var mid = new StackPanel { Spacing = 3, VerticalAlignment = VerticalAlignment.Center };

        var nameRow = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 8 };
        nameRow.Children.Add(new TextBlock
        {
            Text = row.Name,
            FontSize = 14,
            FontWeight = Microsoft.UI.Text.FontWeights.SemiBold,
            Foreground = TextBrush(),
            VerticalAlignment = VerticalAlignment.Center,
            // 名字可能被挤窄,裁剪而不是撑破布局
            TextTrimming = TextTrimming.CharacterEllipsis,
            MaxWidth = 180,
        });
        if (row.Paused)
            nameRow.Children.Add(new TextBlock
            {
                Text = "已暂停",
                FontSize = 11,
                Foreground = DimBrush(),
                VerticalAlignment = VerticalAlignment.Center,
            });
        mid.Children.Add(nameRow);

        var detail = row.Detail;
        if (row.Error is not null) detail = row.Error;
        mid.Children.Add(new TextBlock
        {
            Text = detail,
            FontSize = 12,
            TextTrimming = TextTrimming.CharacterEllipsis,
            Foreground = DimBrush(),
        });
        Grid.SetColumn(mid, 1);
        top.Children.Add(mid);

        // 右列:主值(剩余/已用)
        var mainValue = new TextBlock
        {
            FontSize = 16,
            FontWeight = Microsoft.UI.Text.FontWeights.SemiBold,
            Foreground = TextBrush(),
            VerticalAlignment = VerticalAlignment.Center,
        };
        if (row.Level == Levels.Unconfigured)
            mainValue.Text = "未配置";
        else if (row.Pct is not null)
            mainValue.Text = $"{Http.F0(row.Pct.Value)}%";
        else if (row.Remaining is not null)
            mainValue.Text = $"{Http.F2(row.Remaining.Value)}{row.Unit}";
        else
            mainValue.Text = row.Level == Levels.Error ? "错误" : "-";
        if (row.Error is not null && row.Level != Levels.Unconfigured)
        {
            mainValue.Text = "!";
            mainValue.Foreground = LevelBrush(row.Level);
        }
        Grid.SetColumn(mainValue, 2);
        top.Children.Add(mainValue);

        stack.Children.Add(top);

        // 下半:3px 等级色细条(整行宽,无值时空轨)
        var level = LevelBrush(row.Level);
        var bar = new ProgressBar
        {
            Minimum = 0,
            Maximum = 100,
            Height = 3,
            CornerRadius = new CornerRadius(1.5),
            Foreground = level,
            // 轨道也带等级色:剩余 0% 时填充为空,不然等级完全看不出来
            Background = LevelTrack(level),
        };
        if (row.Pct is not null) bar.Value = Math.Clamp(row.Pct.Value, 0, 100);
        stack.Children.Add(bar);

        var host = new Grid { Children = { stack } };

        // 行右键菜单(对齐 Python row_menu:暂停/编辑/删除)
        var menu = new MenuFlyout();
        var miPause = new MenuFlyoutItem
        { Text = _app.Paused.Contains(row.Name) ? "恢复轮询" : "暂停此 provider" };
        miPause.Click += (_, _) => TogglePause(row.Name);
        menu.Items.Add(miPause);
        var miEdit = new MenuFlyoutItem { Text = "编辑" };
        miEdit.Click += (_, _) =>
        {
            _main.GoSettings();
            _main.Settings.EditProvider(row.Name);
        };
        menu.Items.Add(miEdit);
        var miDelete = new MenuFlyoutItem { Text = "删除" };
        miDelete.Click += async (_, _) => await SettingsPage.ConfirmDeleteAsync(
            _app, this, row.Name);
        menu.Items.Add(miDelete);
        host.ContextFlyout = menu;

        return host;
    }

    private void TogglePause(string name)
    {
        if (!_app.Paused.Remove(name)) _app.Paused.Add(name);
        _ = _app.Poller.RefreshNowAsync();
    }

    private void OpenSettings_Click(object sender, RoutedEventArgs e)
        => _main.GoSettings();
}
