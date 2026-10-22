using AgentEye.Core.Cache;
using Xunit;

namespace AgentEye.Core.Tests;

/// <summary>
/// CacheStore 的更新状态契约:节流时间戳 + 忽略版本,跨重启有效。
/// </summary>
public sealed class CacheUpdateStateTests : IDisposable
{
    private readonly string _dir;
    private readonly CacheStore _cache;

    public CacheUpdateStateTests()
    {
        _dir = Path.Combine(Path.GetTempPath(), "agenteye-tests",
            Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(_dir);
        _cache = new CacheStore(_dir);
    }

    public void Dispose()
    {
        try { Directory.Delete(_dir, recursive: true); } catch (IOException) { }
    }

    [Fact]
    public void LastCheck_RoundTrips()
    {
        Assert.Null(_cache.LoadUpdateLastCheck());
        _cache.SaveUpdateLastCheck(1758000000.5);
        Assert.Equal(1758000000.5, _cache.LoadUpdateLastCheck());
    }

    [Fact]
    public void LastCheck_Survives_New_Instance()
    {
        _cache.SaveUpdateLastCheck(123.25);
        var other = new CacheStore(_dir);
        Assert.Equal(123.25, other.LoadUpdateLastCheck());
    }

    [Fact]
    public void IgnoredVersion_RoundTrips_And_Clears()
    {
        Assert.Null(_cache.LoadUpdateIgnoredVersion());
        _cache.SaveUpdateIgnoredVersion("v2.1.0");
        Assert.Equal("v2.1.0", _cache.LoadUpdateIgnoredVersion());
        _cache.SaveUpdateIgnoredVersion(null);
        Assert.Null(_cache.LoadUpdateIgnoredVersion());
    }

    [Fact]
    public void State_File_Lives_Under_Cache_Dir()
    {
        _cache.SaveUpdateLastCheck(1.0);
        Assert.True(File.Exists(Path.Combine(_dir, "update_state.json")));
    }
}
