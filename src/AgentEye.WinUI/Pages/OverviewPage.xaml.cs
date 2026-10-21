using AgentEye.Core.Providers;
using AgentEye.WinUI.Services;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Shapes;

namespace AgentEye.WinUI.Pages;

/// <summary>
/// 总览页:KPI 卡 + provider 行卡片(代码渲染,行随刷新整批重建,
/// 对齐 Python 版 Panel 的重建语义)。
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
        StatusText.Text = _app.Poller.LastRefresh is { } t
            ? $"上次刷新 {t:HH:mm:ss}"
            : "尚未刷新";

        RowsHost.Children.Clear();
        foreach (var row in rows)
            RowsHost.Children.Add(BuildRow(row));
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

    private Border BuildRow(ProviderResult row)
    {
        var card = new Border { Style = (Style)Application.Current.Resources["AeCardStyle"] };

        var grid = new Grid { ColumnSpacing = 12 };
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });

        // 左列:名称行 + 胶囊 + detail
        var left = new StackPanel { Spacing = 6 };

        var nameRow = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 8 };
        nameRow.Children.Add(new Ellipse
        {
            Width = 8, Height = 8,
            Fill = LevelBrush(row.Level),
            VerticalAlignment = VerticalAlignment.Center,
        });
        nameRow.Children.Add(new TextBlock
        {
            Text = row.Name,
            FontSize = 15,
            FontWeight = Microsoft.UI.Text.FontWeights.SemiBold,
            Foreground = TextBrush(),
            VerticalAlignment = VerticalAlignment.Center,
        });
        nameRow.Children.Add(new Border
        {
            Background = DimBrush(),
            Opacity = 0.25,
            CornerRadius = new CornerRadius(4),
            Padding = new Thickness(6, 1, 6, 2),
            Child = new TextBlock
            {
                Text = row.Kind,
                FontSize = 11,
                Foreground = TextBrush(),
            },
            VerticalAlignment = VerticalAlignment.Center,
        });
        if (row.Paused)
            nameRow.Children.Add(new TextBlock
            {
                Text = "已暂停",
                FontSize = 11,
                Foreground = DimBrush(),
                VerticalAlignment = VerticalAlignment.Center,
            });
        left.Children.Add(nameRow);

        var bar = new ProgressBar
        {
            Minimum = 0,
            Maximum = 100,
            Height = 6,
            CornerRadius = new CornerRadius(3),
        };
        if (row.Pct is not null) bar.Value = Math.Clamp(row.Pct.Value, 0, 100);
        left.Children.Add(bar);

        var detail = row.Detail;
        if (row.Error is not null) detail = row.Error;
        left.Children.Add(new TextBlock
        {
            Text = detail,
            FontSize = 12,
            TextTrimming = TextTrimming.CharacterEllipsis,
            Foreground = DimBrush(),
        });
        Grid.SetColumn(left, 0);
        grid.Children.Add(left);

        // 右列:主值(剩余/已用)
        var mainValue = new TextBlock
        {
            FontSize = 20,
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
            mainValue.Text = "!";
        Grid.SetColumn(mainValue, 1);
        grid.Children.Add(mainValue);

        card.Child = grid;

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
        card.ContextFlyout = menu;

        return card;
    }

    private void TogglePause(string name)
    {
        if (!_app.Paused.Remove(name)) _app.Paused.Add(name);
        _ = _app.Poller.RefreshNowAsync();
    }

    private void BtnRefresh_Click(object sender, RoutedEventArgs e) =>
        _ = _app.Poller.RefreshNowAsync();

    private void BtnTogglePause_Click(object sender, RoutedEventArgs e)
    {
        var paused = _app.Poller.ToggleGlobalPause();
        BtnTogglePause.Content = paused ? "恢复轮询" : "暂停轮询";
    }
}
