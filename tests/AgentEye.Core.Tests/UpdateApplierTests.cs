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
    public void QuotePs_Escapes_Single_Quote()
    {
        Assert.Equal("'abc'", UpdateApplier.QuotePs("abc"));
        Assert.Equal("'a''b'", UpdateApplier.QuotePs("a'b"));
    }

    [Fact]
    public void BuildApplyScript_Contains_Key_Steps()
    {
        var script = UpdateApplier.BuildApplyScript(
            1234, @"C:\tmp\src", @"C:\Program Files\AgentEye",
            @"C:\Program Files\AgentEye\AgentEye.exe", @"C:\tmp\apply.ps1");
        Assert.Contains("param(", script);
        Assert.Contains("Wait-Process -Id $TargetPid", script);
        Assert.Contains("robocopy.exe $Src $Dst /MIR", script);
        Assert.Contains("Start-Process -FilePath $Exe", script);
        // 失败要能查:脚本写日志 + 记 robocopy 退出码 + 失败重试
        Assert.Contains("Log ", script);
        Assert.Contains("robocopy try=$i exit=$rc", script);
        Assert.Contains("robocopy.exe not found", script);
    }

    [Fact]
    public void BuildLaunchCommand_Passes_All_Args()
    {
        var cmd = UpdateApplier.BuildLaunchCommand(
            @"C:\tmp\apply.ps1", 4321, @"C:\tmp\src", @"C:\dst", @"C:\dst\AgentEye.exe");
        Assert.Contains("-NoProfile", cmd);
        Assert.Contains("-ExecutionPolicy Bypass", cmd);
        Assert.Contains("-WindowStyle Hidden", cmd);
        Assert.Contains("-File \"C:\\tmp\\apply.ps1\"", cmd);
        Assert.Contains("-TargetPid 4321", cmd);
        Assert.Contains("-Src \"C:\\tmp\\src\"", cmd);
        Assert.Contains("-Dst \"C:\\dst\"", cmd);
        Assert.Contains("-Exe \"C:\\dst\\AgentEye.exe\"", cmd);
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
