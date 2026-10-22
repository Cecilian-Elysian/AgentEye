using System.Diagnostics;
using AgentEye.Core.Cache;
using AgentEye.Core.Providers;
using AgentEye.Core.Update;
using Microsoft.UI.Xaml;

namespace AgentEye.WinUI.Services;

/// <summary>更新流程的对外状态(UI 只读)。</summary>
public sealed class UpdateState
{
    /// <summary>是否有新版本可装。</summary>
    public bool HasUpdate { get; init; }
    /// <summary>新版本号(如 2.1.0)。</summary>
    public string? LatestVersion { get; init; }
    /// <summary>release 页面地址(没有则空)。</summary>
    public string? ReleaseUrl { get; init; }
    /// <summary>给用户看的状态文案。</summary>
    public string Message { get; init; } = "";
    /// <summary>正在检查/下载。</summary>
    public bool Busy { get; init; }
    /// <summary>下载进度 0-100(仅下载阶段)。</summary>
    public int Progress { get; init; }
    /// <summary>是否处于"已是最新"状态。</summary>
    public bool UpToDate { get; init; }
}

/// <summary>
/// 更新编排:检查(静默/手动)→ 下载 → 校验 → 解包 → 生成替换脚本 → 退出应用。
/// 任何一步失败都只落到状态文案里,绝不把主流程带崩(增强面契约)。
/// </summary>
public sealed class UpdateService
{
    /// <summary>静默检查的节流间隔(同一天不重复查)。</summary>
    public static readonly TimeSpan CheckInterval = TimeSpan.FromDays(1);

    private readonly AppServices _app;
    private readonly CacheStore _cache;
    private UpdateCheckResult? _result;

    public UpdateService(AppServices app)
    {
        _app = app;
        _cache = app.Cache;
    }

    /// <summary>状态变化通知(UI 线程)。</summary>
    public event Action<UpdateState>? StateChanged;

    /// <summary>当前应用版本(取程序集版本,剥掉 +sha 后缀)。</summary>
    public static string CurrentVersion
    {
        get
        {
            var asm = typeof(UpdateService).Assembly;
            var info = asm.GetCustomAttributes(
                typeof(System.Reflection.AssemblyInformationalVersionAttribute), false);
            var raw = info.Length > 0
                ? ((System.Reflection.AssemblyInformationalVersionAttribute)info[0])
                    .InformationalVersion
                : asm.GetName().Version?.ToString() ?? "0.0.0";
            var plus = raw.IndexOf('+');
            return plus > 0 ? raw[..plus] : raw;
        }
    }

    /// <summary>是否到了该检查更新的时间(静默检查用)。</summary>
    public bool ShouldCheckNow()
    {
        try
        {
            var last = _cache.LoadUpdateLastCheck();
            if (last is null) return true;
            var elapsed = DateTimeOffset.UtcNow - DateTimeOffset.FromUnixTimeSeconds((long)last.Value);
            return elapsed >= CheckInterval;
        }
        catch (Exception)
        {
            return true;
        }
    }

    /// <summary>检查更新。silent=true 时不弹 toast。</summary>
    public async Task<UpdateState> CheckAsync(bool silent = false)
    {
        Publish(new UpdateState { Busy = true, Message = "正在检查更新…" });
        UpdateCheckResult result;
        try
        {
            result = await UpdateChecker.CheckAsync(CurrentVersion);
        }
        catch (Exception e)
        {
            result = new UpdateCheckResult(UpdateCheckStatus.NetworkError, null,
                $"检查更新失败:{e.Message}");
        }
        _result = result;
        try { _cache.SaveUpdateLastCheck(Http.Now()); } catch (Exception) { }

        var state = ToState(result);
        // 被用户忽略过的版本不再提示,但状态仍如实显示
        if (state.HasUpdate && IsIgnored(result))
            state = new UpdateState
            {
                HasUpdate = false,
                LatestVersion = state.LatestVersion,
                ReleaseUrl = state.ReleaseUrl,
                UpToDate = false,
                Message = $"{state.Message}(已忽略此版本)",
            };
        Publish(state);
        if (state.HasUpdate && !silent)
            await _app.Notify.ShowAsync("发现新版本", state.Message);
        return state;
    }

    private bool IsIgnored(UpdateCheckResult result)
    {
        try
        {
            var ignored = _cache.LoadUpdateIgnoredVersion();
            return ignored is not null && result.Release is not null &&
                   ignored == result.Release.Tag;
        }
        catch (Exception)
        {
            return false;
        }
    }

    /// <summary>忽略当前提示的版本。</summary>
    public void IgnoreCurrentVersion()
    {
        if (_result?.Release is null) return;
        try { _cache.SaveUpdateIgnoredVersion(_result.Release.Tag); } catch (Exception) { }
    }

    private static UpdateState ToState(UpdateCheckResult r) => new()
    {
        HasUpdate = r.HasUpdate,
        UpToDate = r.Status == UpdateCheckStatus.UpToDate,
        LatestVersion = r.Release?.VersionText,
        ReleaseUrl = r.Release?.HtmlUrl,
        Message = r.Message,
        Busy = false,
    };

    /// <summary>打开 release 页面(浏览器)。</summary>
    public static async Task OpenReleasePageAsync(string url)
    {
        try
        {
            await Windows.System.Launcher.LaunchUriAsync(new Uri(url));
        }
        catch (Exception)
        {
            // 兜底:用默认浏览器
            try
            {
                Process.Start(new ProcessStartInfo(url) { UseShellExecute = true });
            }
            catch (Exception) { }
        }
    }

    /// <summary>
    /// 下载并安装更新:下载 → 校验 → 解包 → 生成替换脚本 → 启动脚本 → 退出应用。
    /// 返回 null 表示成功(应用即将退出),否则是错误文案。
    /// </summary>
    public async Task<string?> DownloadAndApplyAsync(
        IProgress<int>? progress = null, CancellationToken ct = default)
    {
        var release = _result?.Release;
        if (release is null) return "尚未检查到新版本";
        var asset = UpdateChecker.SelectAsset(release.Assets);
        if (asset is null) return "release 里没有可用的 win-x64 安装包";

        var installDir = AppContext.BaseDirectory.TrimEnd('\\');
        var exePath = Path.Combine(installDir, "AgentEye.exe");
        if (!UpdateApplier.IsDirectoryWritable(installDir))
            return $"安装目录不可写({installDir}),请改用浏览器下载后手动替换";

        var workDir = UpdateApplier.WorkDir(Path.GetTempPath(), release.VersionText);
        var zipPath = Path.Combine(workDir, asset.Name);
        var extractDir = Path.Combine(workDir, "payload");

        try
        {
            Publish(new UpdateState
            {
                HasUpdate = true,
                LatestVersion = release.VersionText,
                ReleaseUrl = release.HtmlUrl,
                Busy = true,
                Message = $"正在下载 {asset.Name}…",
            });

            await UpdateDownloader.DownloadAsync(asset.Url, zipPath, new Progress<long>(n =>
            {
                if (asset.Size > 0)
                    progress?.Report((int)Math.Clamp(n * 100 / asset.Size, 0, 99));
            }), ct);

            if (!UpdateDownloader.VerifySha256(zipPath, asset.Sha256))
                return "安装包校验失败(sha256 不匹配),已放弃更新";

            Publish(new UpdateState
            {
                HasUpdate = true,
                LatestVersion = release.VersionText,
                ReleaseUrl = release.HtmlUrl,
                Busy = true,
                Progress = 99,
                Message = "正在解包…",
            });
            UpdateDownloader.ExtractZip(zipPath, extractDir);
            var payloadRoot = UpdateDownloader.DetectPayloadRoot(extractDir);
            if (payloadRoot is null)
                return "安装包结构不符合预期(找不到 AgentEye.exe)";

            var scriptPath = Path.Combine(workDir, "apply.ps1");
            File.WriteAllText(scriptPath, UpdateApplier.BuildApplyScript(
                Environment.ProcessId, payloadRoot, installDir, exePath, scriptPath),
                new System.Text.UTF8Encoding(false));

            var cmd = UpdateApplier.BuildLaunchCommand(
                scriptPath, Environment.ProcessId, payloadRoot, installDir, exePath);
            var psi = new ProcessStartInfo("powershell.exe", cmd)
            {
                UseShellExecute = false,
                CreateNoWindow = true,
            };
            Process.Start(psi);

            // 脚本在等本进程退出,这里主动退出,让它接手替换
            Publish(new UpdateState
            {
                HasUpdate = true,
                LatestVersion = release.VersionText,
                ReleaseUrl = release.HtmlUrl,
                Busy = true,
                Progress = 100,
                Message = "正在更新,应用将自动重启…",
            });
            await Task.Delay(400);
            Application.Current.Exit();
            return null;
        }
        catch (OperationCanceledException)
        {
            Publish(new UpdateState { Message = "已取消更新" });
            return "已取消更新";
        }
        catch (Exception e)
        {
            Publish(new UpdateState { Message = $"更新失败:{e.Message}" });
            return $"更新失败:{e.Message}";
        }
    }

    private void Publish(UpdateState state)
    {
        try { StateChanged?.Invoke(state); } catch (Exception) { }
    }
}
