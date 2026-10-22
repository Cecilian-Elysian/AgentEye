using System.Security.Cryptography;
using AgentEye.Core.Providers;

namespace AgentEye.Core.Update;

/// <summary>
/// 安装包下载与落地:流式下载(带进度)→ sha256 校验。
/// 下载产物是 Inno Setup 安装器(AgentEye_Setup.exe),装与重启由它负责,
/// 这里不再解包(zip 相关逻辑随 robocopy 方案一起废弃)。
/// </summary>
public static class UpdateDownloader
{
    /// <summary>下载文件到本地,返回落盘路径;失败抛异常(调用方负责降级)。</summary>
    public static async Task<string> DownloadAsync(
        string url, string destFile, IProgress<long>? progress = null,
        CancellationToken ct = default)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(destFile)!);
        using var cts = CancellationTokenSource.CreateLinkedTokenSource(ct);
        cts.CancelAfter(TimeSpan.FromMinutes(10));
        using var resp = await Http.Client.GetAsync(url, HttpCompletionOption.ResponseHeadersRead, cts.Token);
        if (!resp.IsSuccessStatusCode)
            throw new IOException($"下载失败 HTTP {(int)resp.StatusCode}");
        var total = resp.Content.Headers.ContentLength ?? 0;
        await using var src = await resp.Content.ReadAsStreamAsync(cts.Token);
        await using var dst = new FileStream(destFile, FileMode.Create, FileAccess.Write, FileShare.None);
        var buf = new byte[81920];
        long done = 0;
        int read;
        while ((read = await src.ReadAsync(buf, cts.Token)) > 0)
        {
            await dst.WriteAsync(buf.AsMemory(0, read), cts.Token);
            done += read;
            progress?.Report(done);
        }
        await dst.FlushAsync(cts.Token);
        dst.Flush(flushToDisk: true);
        if (total > 0 && done != total)
            throw new IOException($"下载不完整({done}/{total} 字节)");
        return destFile;
    }

    /// <summary>文件 sha256(小写十六进制)。</summary>
    public static string ComputeSha256(string file)
    {
        using var fs = File.OpenRead(file);
        using var sha = SHA256.Create();
        return Convert.ToHexString(sha.ComputeHash(fs)).ToLowerInvariant();
    }

    /// <summary>校验 sha256;期望值缺失时返回 true(跳过校验)。</summary>
    public static bool VerifySha256(string file, string? expectedHex)
    {
        if (string.IsNullOrWhiteSpace(expectedHex)) return true;
        var actual = ComputeSha256(file);
        return string.Equals(actual, expectedHex.Trim().ToLowerInvariant(),
            StringComparison.Ordinal);
    }
}
