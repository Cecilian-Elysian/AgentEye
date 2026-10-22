using System.IO.Compression;
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

    private string MakeZip(string name, params (string Path, string Content)[] files)
    {
        var zip = Path.Combine(_dir, name);
        using var fs = File.Create(zip);
        using var archive = new ZipArchive(fs, ZipArchiveMode.Create);
        foreach (var (path, content) in files)
        {
            var entry = archive.CreateEntry(path);
            using var w = new StreamWriter(entry.Open());
            w.Write(content);
        }
        return zip;
    }

    [Fact]
    public void ExtractZip_Then_Detect_Root_With_Exe()
    {
        var zip = MakeZip("a.zip",
            ("AgentEye.exe", "binary"),
            ("AgentEye.dll", "dll"));
        var dest = Path.Combine(_dir, "out");
        UpdateDownloader.ExtractZip(zip, dest);
        var root = UpdateDownloader.DetectPayloadRoot(dest);
        Assert.NotNull(root);
        Assert.Equal(dest, root);
        Assert.True(File.Exists(Path.Combine(root!, "AgentEye.exe")));
    }

    [Fact]
    public void DetectPayloadRoot_Descends_Single_Top_Folder()
    {
        var zip = MakeZip("b.zip", ("AgentEye-win-x64/AgentEye.exe", "binary"));
        var dest = Path.Combine(_dir, "out2");
        UpdateDownloader.ExtractZip(zip, dest);
        var root = UpdateDownloader.DetectPayloadRoot(dest);
        Assert.NotNull(root);
        Assert.Equal(Path.Combine(dest, "AgentEye-win-x64"), root);
    }

    [Fact]
    public void DetectPayloadRoot_Null_When_No_Exe()
    {
        var zip = MakeZip("c.zip", ("readme.txt", "hi"));
        var dest = Path.Combine(_dir, "out3");
        UpdateDownloader.ExtractZip(zip, dest);
        Assert.Null(UpdateDownloader.DetectPayloadRoot(dest));
    }

    [Fact]
    public void DetectPayloadRoot_Null_When_Ambiguous()
    {
        var zip = MakeZip("d.zip",
            ("dir1/AgentEye.exe", "x"),
            ("dir2/other.txt", "y"));
        var dest = Path.Combine(_dir, "out4");
        UpdateDownloader.ExtractZip(zip, dest);
        Assert.Null(UpdateDownloader.DetectPayloadRoot(dest));
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
}
