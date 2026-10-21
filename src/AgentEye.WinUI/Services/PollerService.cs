using Microsoft.UI.Dispatching;
using AgentEye.Core.Config;
using AgentEye.Core.Providers;

namespace AgentEye.WinUI.Services;

/// <summary>
/// 轮询引擎:PeriodicTimer 后台循环 + 单飞(进行中的轮询不叠加)。
/// 完成后回 UI 线程发 ResultsChanged;退出用 CancellationToken,进程关
/// 窗即取消,在途请求直接掐(对齐 Python daemon 线程语义)。
/// </summary>
public sealed class PollerService : IDisposable
{
    private readonly AppServices _app;
    private readonly DispatcherQueue _dq;
    private CancellationTokenSource? _cts;
    private Task? _loop;
    private int _inFlight;
    public DateTimeOffset? LastRefresh { get; private set; }

    public PollerService(AppServices app)
    {
        _app = app;
        _dq = DispatcherQueue.GetForCurrentThread();
    }

    /// <summary>启动周期轮询(15-3600 秒,读 cfg)。</summary>
    public void Start()
    {
        if (_loop is not null) return;
        _cts = new CancellationTokenSource();
        _loop = Task.Run(() => LoopAsync(_cts.Token));
    }

    public async void Reschedule()
    {
        // 重建循环让新周期生效
        Stop();
        await Task.CompletedTask;
        Start();
    }

    public void Stop()
    {
        _cts?.Cancel();
        _cts = null;
        _loop = null;
    }

    private bool _globalPaused;

    /// <summary>托盘菜单文案用:当前是否处于全局暂停。</summary>
    public bool IsGloballyPaused => _globalPaused;

    /// <summary>全局暂停/恢复(行不重建,只是不再发请求)。返回暂停后的状态。</summary>
    public bool ToggleGlobalPause()
    {
        if (_globalPaused)
        {
            _globalPaused = false;
            Start();
        }
        else
        {
            _globalPaused = true;
            Stop();
        }
        return _globalPaused;
    }

    private async Task LoopAsync(CancellationToken ct)
    {
        while (!ct.IsCancellationRequested)
        {
            var sec = ConfigStore.ClampIntervalV2(_app.Cfg);
            try
            {
                await RefreshNowAsync(ct);
                using var timer = new PeriodicTimer(TimeSpan.FromSeconds(sec));
                await timer.WaitForNextTickAsync(ct);
            }
            catch (OperationCanceledException)
            {
                return;
            }
            catch (Exception)
            {
                // 单轮失败不终止循环;退避 5 秒再进下一轮
                try { await Task.Delay(5000, ct); }
                catch (OperationCanceledException) { return; }
            }
        }
    }

    /// <summary>立即刷一轮(供按钮/托盘调用)。进行中则忽略,不叠加。</summary>
    public async Task RefreshNowAsync(CancellationToken ct = default)
    {
        if (Interlocked.CompareExchange(ref _inFlight, 1, 0) != 0) return;
        try
        {
            var results = await ProviderRegistry.FetchAllAsync(
                _app.Cfg, _app.Paused, ct);
            await AlertService.EvaluateAsync(_app, results, ct);
            LastRefresh = DateTimeOffset.Now;
            _dq.TryEnqueue(() => _app.SetResults(results));
        }
        finally
        {
            Interlocked.Exchange(ref _inFlight, 0);
        }
    }

    public void Dispose() => Stop();
}
