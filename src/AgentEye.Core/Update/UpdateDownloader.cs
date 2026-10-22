using System.IO.Compression;
using System.Security.Cryptography;
using AgentEye.Core.Providers;

namespace AgentEye.Core.Update;

/// <summary>
/// 安装包下载与落地:流式下载(带进度)→ sha256 校验 → 解压 →
/// 定位 payload 根目录(zip 内可能只有一层顶层目录)。
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

    /// <summary>解压到目标目录(先清空)。</summary>
    public static void ExtractZip(string zipFile, string destDir)
    {
        if (Directory.Exists(destDir))
        {
            foreach (var f in Directory.EnumerateFiles(destDir, "*", SearchOption.AllDirectories))
                try { File.Delete(f); } catch (IOException) { }
            foreach (var d in Directory.EnumerateDirectories(destDir))
                try { Directory.Delete(d, true); } catch (IOException) { }
        }
        Directory.CreateDirectory(destDir);
        ZipFile.ExtractToDirectory(zipFile, destDir, overwriteFiles: true);
    }

    /// <summary>
    /// 定位 payload 根:根下有 exe 就用根;否则若只有唯一一层目录则下钻。
    /// 找不到返回 null(资产不合法)。
    /// </summary>
    public static string? DetectPayloadRoot(string extractedDir, string requiredFile = "AgentEye.exe")
    {
        if (File.Exists(Path.Combine(extractedDir, requiredFile)))
            return extractedDir;
        var dirs = Directory.GetDirectories(extractedDir);
        if (dirs.Length == 1)
        {
            var inner = dirs[0];
            if (File.Exists(Path.Combine(inner, requiredFile)))
                return inner;
        }
        return null;
    }
}
