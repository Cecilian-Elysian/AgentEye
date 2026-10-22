namespace AgentEye.Core.Update;

/// <summary>
/// 替换执行:运行中的 exe 被锁,没法直接覆盖。做法是生成一个 PowerShell
/// 辅助脚本(放 %TEMP%,不进安装目录),它先等应用退出,再整目录镜像替换,
/// 最后拉起新版本并自删。
/// </summary>
public static class UpdateApplier
{
    /// <summary>安装目录是否可写(装到 Program Files 时为 false)。</summary>
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

    /// <summary>PowerShell 单引号字符串转义(内部单引号要双写)。</summary>
    public static string QuotePs(string value) => "'" + value.Replace("'", "''") + "'";

    /// <summary>生成替换脚本内容(纯函数,可单测)。</summary>
    public static string BuildApplyScript(
        int targetPid, string srcDir, string destDir, string exePath, string selfPath)
    {
        return $$"""
            param(
              [int]$TargetPid,
              [string]$Src,
              [string]$Dst,
              [string]$Exe,
              [string]$Self
            )
            $ErrorActionPreference = 'SilentlyContinue'
            $Log = "$Self.log"
            function Log([string]$m) {
              Add-Content -LiteralPath $Log -Value ("[{0}] {1}" -f (Get-Date -Format "HH:mm:ss"), $m)
            }
            Log "start src=$Src dst=$Dst pid=$TargetPid"
            # wait for the app to exit, otherwise exe/assemblies are locked
            try { Wait-Process -Id $TargetPid -ErrorAction SilentlyContinue } catch { }
            Log "app exited"
            if (-not (Get-Command robocopy.exe -ErrorAction SilentlyContinue)) {
              Log "FATAL: robocopy.exe not found"
              exit 2
            }
            # /MIR overwrites same-name files and purges leftovers from the old version
            # retry: right after exit the file handles may still be held for a moment
            for ($i = 1; $i -le 3; $i++) {
              $out = & robocopy.exe $Src $Dst /MIR /R:2 /W:1 /NFL /NDL /NJH /NJS /NP 2>&1
              $rc = $LASTEXITCODE
              Log "robocopy try=$i exit=$rc"
              if ($rc -ne $null -and $rc -lt 8) { break }
              Log ("robocopy out=" + (($out | Out-String).Trim()))
              Start-Sleep -Milliseconds 1500
            }
            Start-Process -FilePath $Exe -WorkingDirectory $Dst
            Log "relaunched $Exe"
            """;
    }

    /// <summary>启动辅助脚本的完整命令行(纯函数,可单测)。</summary>
    public static string BuildLaunchCommand(
        string scriptPath, int targetPid, string srcDir, string destDir, string exePath)
    {
        return "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden " +
               $"-File \"{scriptPath}\" -TargetPid {targetPid} " +
               $"-Src \"{srcDir}\" -Dst \"{destDir}\" -Exe \"{exePath}\" " +
               $"-Self \"{scriptPath}\"";
    }

    /// <summary>更新临时目录:每次更新一个独立子目录,失败可原样重试。</summary>
    public static string WorkDir(string tempRoot, string version)
    {
        var safe = string.Join("_", version.Split(Path.GetInvalidFileNameChars()));
        return Path.Combine(tempRoot, "AgentEye", "update", safe);
    }
}
