using AgentEye.Core.Update;
using Xunit;

namespace AgentEye.Core.Tests;

public class UpdateVersionTests
{
    [Theory]
    [InlineData("1.0.0", "1.0.0", 0)]
    [InlineData("v1.0.0", "1.0.0", 0)]
    [InlineData("1.0.1", "1.0.0", 1)]
    [InlineData("1.0.0", "1.0.1", -1)]
    [InlineData("1.1", "1.1.0", 0)]
    [InlineData("1.1", "1.1.1", -1)]
    [InlineData("2.0.0", "1.9.9", 1)]
    [InlineData("1.10.0", "1.9.0", 1)]
    [InlineData("1.2.0-beta", "1.2.0", -1)]
    [InlineData("1.2.0", "1.2.0-beta", 1)]
    [InlineData("2.0.0+9b3195e", "2.0.0", 0)]
    [InlineData("v2.0.0", "1.0.0", 1)]
    public void Compare_Works(string left, string right, int expected)
    {
        var a = AppVersionInfo.Parse(left)!;
        var b = AppVersionInfo.Parse(right)!;
        Assert.Equal(expected, Math.Sign(a.CompareTo(b)));
    }

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("   ")]
    [InlineData("latest")]
    [InlineData("abc")]
    [InlineData("1.x.0")]
    public void Parse_Rejects_NonVersion(string? raw)
        => Assert.Null(AppVersionInfo.Parse(raw));

    [Fact]
    public void Parse_Normalizes_Fields()
    {
        var v = AppVersionInfo.Parse("v2.1.3-rc1+abc")!;
        Assert.Equal(2, v.Major);
        Assert.Equal(1, v.Minor);
        Assert.Equal(3, v.Patch);
        Assert.Equal("rc1", v.PreRelease);
        Assert.Equal("2.1.3-rc1", v.ToString());
    }

    [Fact]
    public void IsNewerThan_Matches_Compare()
    {
        var cur = AppVersionInfo.Parse("2.0.0")!;
        Assert.False(cur.IsNewerThan(AppVersionInfo.Parse("2.0.0")!));
        Assert.True(cur.IsNewerThan(AppVersionInfo.Parse("1.9.9")!));
        Assert.False(cur.IsNewerThan(AppVersionInfo.Parse("2.0.1")!));
    }
}
