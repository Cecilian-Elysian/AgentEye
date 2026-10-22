using AgentEye.Core.Update;
using Xunit;

namespace AgentEye.Core.Tests;

public class UpdateApplierTests : IDisposable
{
    private readonly string _dir = Path.Combine(
        Path.GetTempPath(), "agenteye_apply_" + Guid.NewGuid().ToString("N"));

    public UpdateApplierTests() => Directory.CreateDirectory(_dir);

    public void Dispose()
    {
        try { if (Directory.Exists(_dir)) Directory.Delete(_dir, true); } catch (IOException) { }
    }

    [Fact]
    public void IsDirectoryWritable_True_For_Writable()
    {
        Assert.True(UpdateApplier.IsDirectoryWritable(_dir));
    }

    [Fact]
    public void IsDirectoryWritable_False_For_Missing()
    {
        Assert.False(UpdateApplier.IsDirectoryWritable(Path.Combine(_dir, "nope")));
    }

    [Fact]
    public void SilentInstallArgs_Has_Quiet_And_Restart_Flags()
    {
        // 静默 + 不弹框;关掉运行中的应用并自动重启是整条链的关键
        Assert.Contains("/VERYSILENT", UpdateApplier.SilentInstallArgs);
        Assert.Contains("/SUPPRESSMSGBOXES", UpdateApplier.SilentInstallArgs);
        Assert.Contains("/CLOSEAPPLICATIONS", UpdateApplier.SilentInstallArgs);
        Assert.Contains("/RESTARTAPPLICATIONS", UpdateApplier.SilentInstallArgs);
    }

    [Fact]
    public void BuildSilentInstallCommand_Quotes_Path_And_Appends_Args()
    {
        var cmd = UpdateApplier.BuildSilentInstallCommand(
            @"C:\Users\me\AppData\Local\Temp\AgentEye\update\1.1.0\AgentEye_Setup.exe");
        Assert.StartsWith("\"", cmd);
        Assert.Contains("\" ", cmd);
        Assert.EndsWith(UpdateApplier.SilentInstallArgs, cmd);
        // 路径带空格也必须整体被引号包住
        var spaced = UpdateApplier.BuildSilentInstallCommand(@"C:\Prog Files\AgentEye_Setup.exe");
        Assert.Contains("\"C:\\Prog Files\\AgentEye_Setup.exe\"", spaced);
    }

    [Fact]
    public void WorkDir_Isolates_By_Version()
    {
        var a = UpdateApplier.WorkDir(@"C:\Temp", "2.1.0");
        var b = UpdateApplier.WorkDir(@"C:\Temp", "2.2.0");
        Assert.NotEqual(a, b);
        Assert.Contains("2.1.0", a);
        Assert.StartsWith(Path.Combine(@"C:\Temp", "AgentEye", "update"), a);
    }
}
