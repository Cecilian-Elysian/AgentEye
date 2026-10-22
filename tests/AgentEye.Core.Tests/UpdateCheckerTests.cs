using System.Text.Json;
using AgentEye.Core.Update;
using Xunit;

namespace AgentEye.Core.Tests;

public class UpdateCheckerTests
{
    private static JsonElement Json(string s) => JsonDocument.Parse(s).RootElement;

    [Fact]
    public void ParseRelease_Reads_Tag_Url_Assets()
    {
        var body = Json("""
        {
          "tag_name": "v2.1.0",
          "name": "AgentEye 2.1.0",
          "html_url": "https://github.com/Cecilian-Elysian/AgentEye/releases/tag/v2.1.0",
          "body": "修复若干问题",
          "prerelease": false,
          "published_at": "2026-10-22T10:00:00Z",
          "assets": [
            {"name": "AgentEye_Setup.exe", "browser_download_url": "https://x/AgentEye_Setup.exe",
             "size": 123, "digest": "sha256:AAAA"},
            {"name": "sha256sums.txt", "browser_download_url": "https://x/s.txt", "size": 10}
          ]
        }
        """);
        var rel = UpdateChecker.ParseRelease(body)!;
        Assert.Equal("v2.1.0", rel.Tag);
        Assert.Equal("2.1.0", rel.VersionText);
        Assert.Equal("AgentEye 2.1.0", rel.Name);
        Assert.False(rel.PreRelease);
        Assert.Equal(2, rel.Assets.Count);
        Assert.NotNull(rel.PublishedAt);
    }

    [Fact]
    public void ParseRelease_NonObject_Is_Null()
        => Assert.Null(UpdateChecker.ParseRelease(Json("[1,2,3]")));

    [Fact]
    public void ParseRelease_Missing_Tag_Is_Null()
        => Assert.Null(UpdateChecker.ParseRelease(Json("""{"name":"x"}""")));

    [Theory]
    [InlineData("sha256:abcdef", "abcdef")]
    [InlineData("SHA256:ABCDEF", "abcdef")]
    public void ParseDigest_Reads_Hex(string digest, string expected)
        => Assert.Equal(expected, UpdateChecker.ParseDigest(digest));

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("sha1:abc")]
    [InlineData("sha256:tooshort")]
    [InlineData("deadbeef")]
    public void ParseDigest_Rejects_Bad(string? digest)
        => Assert.Null(UpdateChecker.ParseDigest(digest));

    [Fact]
    public void SelectAsset_Prefers_Exact_Name()
    {
        var assets = new List<UpdateAsset>
        {
            new("AgentEye-2.1.0-Setup.exe", "https://x/a.exe", 1, null),
            new("AgentEye_Setup.exe", "https://x/b.exe", 1, null),
        };
        Assert.Equal("https://x/b.exe", UpdateChecker.SelectAsset(assets)!.Url);
    }

    [Fact]
    public void SelectAsset_Accepts_Variant_Name()
    {
        var assets = new List<UpdateAsset>
        {
            new("AgentEye-2.1.0-Setup.exe", "https://x/a.exe", 1, null),
        };
        Assert.Equal("https://x/a.exe", UpdateChecker.SelectAsset(assets)!.Url);
    }

    [Fact]
    public void SelectAsset_Skips_NonExe_And_Other_Arch()
    {
        var assets = new List<UpdateAsset>
        {
            new("AgentEye-win-x64.zip", "https://x/a.zip", 1, null),
            new("AgentEye_Setup.msi", "https://x/b.msi", 1, null),
            new("notes.txt", "https://x/c.txt", 1, null),
        };
        Assert.Null(UpdateChecker.SelectAsset(assets));
    }

    [Fact]
    public void Decide_Newer_Version_Reports_NewVersion()
    {
        var rel = MakeRelease("v2.1.0", withAsset: true);
        var r = UpdateChecker.Decide("2.0.0", rel);
        Assert.Equal(UpdateCheckStatus.NewVersion, r.Status);
        Assert.True(r.HasUpdate);
    }

    [Fact]
    public void Decide_Same_Version_Reports_UpToDate()
    {
        var r = UpdateChecker.Decide("2.1.0", MakeRelease("v2.1.0", withAsset: true));
        Assert.Equal(UpdateCheckStatus.UpToDate, r.Status);
        Assert.False(r.HasUpdate);
    }

    [Fact]
    public void Decide_Older_Remote_Reports_UpToDate()
    {
        var r = UpdateChecker.Decide("2.2.0", MakeRelease("v2.1.0", withAsset: true));
        Assert.Equal(UpdateCheckStatus.UpToDate, r.Status);
    }

    [Fact]
    public void Decide_Newer_But_No_Asset_Reports_NoAsset()
    {
        var r = UpdateChecker.Decide("2.0.0", MakeRelease("v2.1.0", withAsset: false));
        Assert.Equal(UpdateCheckStatus.NoAsset, r.Status);
    }

    [Fact]
    public void Decide_Bad_Version_Reports_InvalidResponse()
    {
        var r = UpdateChecker.Decide("not-a-version", MakeRelease("v2.1.0", withAsset: true));
        Assert.Equal(UpdateCheckStatus.InvalidResponse, r.Status);
    }

    private static ReleaseInfo MakeRelease(string tag, bool withAsset) => new(
        tag, tag, "https://x", "", false, null,
        withAsset
            ? new List<UpdateAsset> { new("AgentEye_Setup.exe", "https://x/a.exe", 1, null) }
            : new List<UpdateAsset>());
}
