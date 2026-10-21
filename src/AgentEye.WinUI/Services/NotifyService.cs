using AgentEye.Core.Cache;
using AgentEye.Core.Providers;

namespace AgentEye.WinUI.Services;

/// <summary>
/// 告警评估:跨过阈值弹一次、同 provider 同等级 60 分钟冷却(跨重启)、
/// warn→critical 升级视为新告警、一轮多 provider 合并成一条 toast。
/// </summary>
public static class AlertService
{
    private static readonly TimeSpan Cooldown = TimeSpan.FromHours(1);

    public static async Task EvaluateAsync(
        AppServices app, IReadOnlyList<ProviderResult> results, CancellationToken ct)
    {
        var notified = app.Cache.LoadAlertState();
        var now = Http.Now();
        var fired = new List<ProviderResult>();
        var changed = false;
        var seen = new HashSet<string>();

        foreach (var row in results)
        {
            if (row.Level is not (Levels.Warn or Levels.Critical)) continue;
            seen.Add(row.Name);
            if (notified.TryGetValue(row.Name, out var prev))
            {
                // 同等级且还在冷却窗内:不重复
                if (prev.Level == row.Level && now - prev.Ts < Cooldown.TotalSeconds)
                    continue;
            }
            notified[row.Name] = (row.Level, now);
            changed = true;
            fired.Add(row);
        }
        // 回落到阈值以上的行:清掉冷却记录,下次再跌破可以立刻告警
        foreach (var name in notified.Keys.Where(n => !seen.Contains(n)).ToList())
        {
            notified.Remove(name);
            changed = true;
        }
        if (changed)
            app.Cache.SaveAlertState(notified);

        if (fired.Count > 0)
            await app.Notify.ShowAlertAsync(fired, ct);
    }
}

/// <summary>
/// 通知:WinRT/AppSDK toast 优先,失败回退 MessageBeep。
/// 任何一步失败都静默降级,不把轮询主流程带崩。
/// </summary>
public sealed class NotifyService
{
    private bool _registered;
    private bool _registerFailed;

    [System.Runtime.InteropServices.DllImport("user32.dll")]
    private static extern bool MessageBeep(uint type);

    /// <summary>合并告警 toast(标题 + 每行一段明细)。</summary>
    public async Task ShowAlertAsync(IReadOnlyList<ProviderResult> rows, CancellationToken ct)
    {
        var title = rows.Count == 1
            ? $"{rows[0].Name} 额度告警"
            : $"{rows.Count} 个 provider 额度告警";
        var body = string.Join("\n", rows.Select(r =>
            $"{r.Name}: {(r.Pct is null ? r.Detail : $"剩 {Http.F0(r.Pct.Value)}% · {r.Detail}")}"));
        await ShowAsync(title, body);
        await Task.CompletedTask;
    }

    public async Task ShowAsync(string title, string body)
    {
        var shown = false;
        try
        {
            if (!_registerFailed)
            {
                var manager = Microsoft.Windows.AppNotifications.AppNotificationManager.Default;
                if (!_registered)
                {
                    manager.NotificationInvoked += (_, _) => { };
                    manager.Register();
                    _registered = true;
                }
                var builder = new Microsoft.Windows.AppNotifications.Builder.AppNotificationBuilder()
                    .AddText(title)
                    .AddText(body);
                manager.Show(builder.BuildNotification());
                shown = true;
            }
        }
        catch (Exception)
        {
            _registerFailed = true;
        }
        if (!shown)
        {
            try { MessageBeep(0x00000030); } catch { /* 静默 */ }
        }
        await Task.CompletedTask;
    }
}
