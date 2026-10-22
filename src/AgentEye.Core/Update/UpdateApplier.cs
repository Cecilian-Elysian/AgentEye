namespace AgentEye.Core.Update;

/// <summary>
/// 更新落地:下载好 AgentEye_Setup.exe(Inno Setup 打包)后拉起静默安装,
/// 由安装器负责关掉运行中的应用(Restart Manager)、替换文件并自动重启。
/// 旧的「robocopy 替换脚本」方案已废弃——安装器自己会处理文件锁。
/// </summary>
public static class UpdateApplier
{
    /// <summary>安装目录是否可写(不可写时静默安装必然失败,提前给出可读文案)。</summary>
    public static bool IsDirectoryWritable(string dir)
    {
        try
        {
            if (!Directory.Exists(dir)) return false;
            var probe = Path.Combine(dir, $".ae_write_{Guid.NewGuid():N}.tmp");
            File.WriteAllText(probe, "x");
            File.Delete(probe);
            return true;
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException
                                      or NotSupportedException)
        {
            return false;
        }
    }

    /// <summary>
    /// Inno 静默安装参数:不弹向导/不弹消息框;CLOSEAPPLICATIONS 让安装器用
    /// Restart Manager 关掉运行中的 AgentEye,RESTARTAPPLICATIONS 让它装完自动重启。
    /// </summary>
    public const string SilentInstallArgs =
        "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS /RESTARTAPPLICATIONS";

    /// <summary>拉起安装器的完整命令行(纯函数,可单测)。</summary>
    public static string BuildSilentInstallCommand(string setupExe)
        => $"\"{setupExe}\" {SilentInstallArgs}";

    /// <summary>更新临时目录:每次更新一个独立子目录,失败可原样重试。</summary>
    public static string WorkDir(string tempRoot, string version)
    {
        var safe = string.Join("_", version.Split(Path.GetInvalidFileNameChars()));
        return Path.Combine(tempRoot, "AgentEye", "update", safe);
    }
}
