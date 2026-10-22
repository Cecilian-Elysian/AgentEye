using System.Text.Json;
using AgentEye.Core.Providers;

namespace AgentEye.Core.Update;

/// <summary>release 里的一个可下载资产。</summary>
public sealed record UpdateAsset(string Name, string Url, long Size, string? Sha256);

/// <summary>一条 release 的摘要信息。</summary>
public sealed record ReleaseInfo(
    string Tag,
    string Name,
    string HtmlUrl,
    string Notes,
    bool PreRelease,
    DateTimeOffset? PublishedAt,
    IReadOnlyList<UpdateAsset> Assets)
{
    /// <summary>tag 去掉 v 前缀后的版本串。</summary>
    public string VersionText => Tag.TrimStart('v', 'V');
}

/// <summary>检查结果分类——UI 要分别给不同文案,不能一律"失败"。</summary>
public enum UpdateCheckStatus
{
    /// <summary>已是最新。</summary>
    UpToDate,
    /// <summary>有新版本。</summary>
    NewVersion,
    /// <summary>仓库还没有任何 release(首次使用常见)。</summary>
    NoRelease,
    /// <summary>被 GitHub 限流(未认证 60 次/小时)。</summary>
    RateLimited,
    /// <summary>网络不可达。</summary>
    NetworkError,
    /// <summary>响应不是预期的 JSON。</summary>
    InvalidResponse,
    /// <summary>release 里没有可用的 win-x64 安装包。</summary>
    NoAsset,
}

/// <summary>一次检查的完整结果。</summary>
public sealed record UpdateCheckResult(
    UpdateCheckStatus Status, ReleaseInfo? Release, string Message)
{
    public bool HasUpdate => Status == UpdateCheckStatus.NewVersion;
}

/// <summary>
/// GitHub Release 检查器:查 latest release、挑 win-x64 安装包、比对版本。
/// 纯逻辑 + 一个薄的网络壳;解析/选择/判定都拆成可单测的静态方法。
/// </summary>
public static class UpdateChecker
{
    /// <summary>更新源仓库(公开仓库,匿名 API 即可)。</summary>
    public const string Owner = "Cecilian-Elysian";
    public const string Repo = "AgentEye";

    /// <summary>安装包资产名匹配模式:AgentEye_Setup.exe(Inno Setup 安装器)。</summary>
    public const string AssetNameHint = "setup.exe";

    /// <summary>
    /// API 基址:默认官方 GitHub;环境变量 AGENTEYE_UPDATE_API 可指向
    /// 镜像/自建实例(也用于本地联调)。
    /// </summary>
    public static string DefaultApiBase
    {
        get
        {
            var env = Environment.GetEnvironmentVariable("AGENTEYE_UPDATE_API");
            return string.IsNullOrWhiteSpace(env) ? "https://api.github.com" : env.Trim();
        }
    }

    private const int TimeoutSec = 15;

    /// <summary>检查是否有新版本。owner/repo/apiBase 可覆盖(测试用)。</summary>
    public static async Task<UpdateCheckResult> CheckAsync(
        string currentVersion,
        string? owner = null, string? repo = null, string? apiBase = null,
        CancellationToken ct = default)
    {
        owner ??= Owner;
        repo ??= Repo;
        apiBase ??= DefaultApiBase;
        var url = $"{apiBase.TrimEnd('/')}/repos/{owner}/{repo}/releases/latest";
        var headers = new Dictionary<string, string>
        {
            ["User-Agent"] = "AgentEye",
            ["Accept"] = "application/vnd.github+json",
            ["X-GitHub-Api-Version"] = "2022-11-28",
        };

        var (ok, status, body) = await Http.GetJsonAsync(url, headers, TimeoutSec, ct);
        if (!ok)
            return new UpdateCheckResult(UpdateCheckStatus.NetworkError, null,
                "连不上 GitHub,检查更新失败(网络问题)");
        if (status == 404)
            return new UpdateCheckResult(UpdateCheckStatus.NoRelease, null,
                "仓库还没有发布版本,暂时无法检查更新");
        if (status == 403 || status == 429)
            return new UpdateCheckResult(UpdateCheckStatus.RateLimited, null,
                "GitHub 接口限流(未登录每小时 60 次),稍后再试");
        if (status != 200)
            return new UpdateCheckResult(UpdateCheckStatus.InvalidResponse, null,
                $"GitHub 返回 HTTP {status}");

        var release = ParseRelease(body);
        if (release is null)
            return new UpdateCheckResult(UpdateCheckStatus.InvalidResponse, null,
                "GitHub 返回的内容不是预期的 release 格式");

        return Decide(currentVersion, release);
    }

    /// <summary>解析 release JSON(纯函数,可单测)。</summary>
    public static ReleaseInfo? ParseRelease(JsonElement body)
    {
        if (!Http.IsObj(body)) return null;
        var tag = Http.Str(body, "tag_name");
        if (string.IsNullOrWhiteSpace(tag)) return null;
        var assets = new List<UpdateAsset>();
        foreach (var a in Http.Arr(body, "assets") ?? [])
        {
            var name = Http.Str(a, "name");
            var url = Http.Str(a, "browser_download_url");
            if (string.IsNullOrEmpty(name) || string.IsNullOrEmpty(url)) continue;
            var size = (long)(Http.Num(a, "size") ?? 0);
            var digest = Http.Str(a, "digest");
            assets.Add(new UpdateAsset(name, url, size, ParseDigest(digest)));
        }
        DateTimeOffset? published = null;
        var pub = Http.Str(body, "published_at");
        if (!string.IsNullOrEmpty(pub) &&
            DateTimeOffset.TryParse(pub, out var parsed))
            published = parsed;
        return new ReleaseInfo(
            tag.Trim(),
            Http.Str(body, "name") ?? tag.Trim(),
            Http.Str(body, "html_url") ?? "",
            Http.Str(body, "body") ?? "",
            Http.Obj(body, "prerelease")?.ValueKind == System.Text.Json.JsonValueKind.True,
            published,
            assets);
    }

    /// <summary>解析 GitHub 的 digest 字段:"sha256:abcdef" → "abcdef"。</summary>
    public static string? ParseDigest(string? digest)
    {
        if (string.IsNullOrWhiteSpace(digest)) return null;
        var s = digest.Trim();
        var colon = s.IndexOf(':');
        if (colon < 0) return null;
        var algo = s[..colon].Trim();
        var hex = s[(colon + 1)..].Trim();
        if (!algo.Equals("sha256", StringComparison.OrdinalIgnoreCase)) return null;
        if (hex.Length == 0) return null;
        foreach (var c in hex)
            if (!Uri.IsHexDigit(c)) return null;
        return hex.ToLowerInvariant();
    }

    /// <summary>从资产里挑安装器(纯函数,可单测)。</summary>
    public static UpdateAsset? SelectAsset(IReadOnlyList<UpdateAsset> assets)
    {
        UpdateAsset? best = null;
        foreach (var a in assets)
        {
            var name = a.Name.ToLowerInvariant();
            if (!name.EndsWith(".exe", StringComparison.Ordinal)) continue;
            if (!name.Contains(AssetNameHint, StringComparison.Ordinal)) continue;
            // 优先精确名 AgentEye_Setup.exe
            if (name == "agenteye_setup.exe") return a;
            best ??= a;
        }
        return best;
    }

    /// <summary>版本判定 + 资产挑选(纯函数,可单测)。</summary>
    public static UpdateCheckResult Decide(string currentVersion, ReleaseInfo release)
    {
        var current = AppVersionInfo.Parse(currentVersion);
        var latest = AppVersionInfo.Parse(release.VersionText);
        if (current is null || latest is null)
            return new UpdateCheckResult(UpdateCheckStatus.InvalidResponse, release,
                $"版本号无法比较(当前 {currentVersion},远端 {release.Tag})");
        if (!latest.IsNewerThan(current))
            return new UpdateCheckResult(UpdateCheckStatus.UpToDate, release,
                $"已是最新版本 v{current}");
        var asset = SelectAsset(release.Assets);
        if (asset is null)
            return new UpdateCheckResult(UpdateCheckStatus.NoAsset, release,
                $"发现新版本 v{latest},但 release 里没有 {AssetNameHint} 安装包");
        return new UpdateCheckResult(UpdateCheckStatus.NewVersion, release,
            $"发现新版本 v{latest}(当前 v{current})");
    }
}
