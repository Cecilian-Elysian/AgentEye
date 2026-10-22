using AgentEye.Core.Update;
using Xunit;

namespace AgentEye.Core.Tests;

public class UpdateDownloaderTests : IDisposable
{
    private readonly string _dir = Path.Combine(
        Path.GetTempPath(), "agenteye_test_" + Guid.NewGuid().ToString("N"));

    public UpdateDownloaderTests() => Directory.CreateDirectory(_dir);

    public void Dispose()
    {
        try { if (Directory.Exists(_dir)) Directory.Delete(_dir, true); } catch (IOException) { }
    }

    [Fact]
    public void Sha256_Verify_Match_And_Mismatch()
    {
        var file = Path.Combine(_dir, "f.bin");
        File.WriteAllText(file, "hello");
        var hash = UpdateDownloader.ComputeSha256(file);
        Assert.Equal(64, hash.Length);
        Assert.True(UpdateDownloader.VerifySha256(file, hash));
        Assert.True(UpdateDownloader.VerifySha256(file, hash.ToUpperInvariant()));
        Assert.False(UpdateDownloader.VerifySha256(file, new string('0', 64)));
        // 没有期望值时跳过校验
        Assert.True(UpdateDownloader.VerifySha256(file, null));
        Assert.True(UpdateDownloader.VerifySha256(file, "  "));
    }

    [Fact]
    public void Sha256_Ignore_Case_And_Whitespace_In_Expected()
    {
        var file = Path.Combine(_dir, "g.bin");
        File.WriteAllText(file, "world");
        var hash = UpdateDownloader.ComputeSha256(file);
        Assert.True(UpdateDownloader.VerifySha256(file, "  " + hash + "\n"));
    }
}
