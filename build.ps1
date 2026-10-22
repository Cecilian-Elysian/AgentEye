# AgentEye 一键构建:dist(便携目录) + installer(AgentEye_Setup.exe)
# 模式对齐 key_note:csproj 版本当唯一真源,中间产物进 build\,绝不打包用户数据
# (config 在 ~\.agenteye,与安装目录无关,无需备份还原)
$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

$DistDir   = Join-Path $ProjectRoot "dist"
$PublishDir = Join-Path $ProjectRoot "build\publish"
$StageDir   = Join-Path $ProjectRoot "build\setup_stage"

# 版本以 csproj 为唯一真源(安装包版本由其派生)
$CsprojPath = Join-Path $ProjectRoot "src\AgentEye.WinUI\AgentEye.WinUI.csproj"
[xml]$CsprojXml = Get-Content -LiteralPath $CsprojPath
$AppVer = @($CsprojXml.Project.PropertyGroup | ForEach-Object { $_.Version } | Where-Object { $_ })[0]
if (-not $AppVer) { $AppVer = "1.0.0" }
Write-Host "VERSION: $AppVer" -ForegroundColor Cyan

# 杀运行中的实例(托盘/小组件同进程),释放文件锁
$Running = Get-Process -Name "AgentEye" -ErrorAction SilentlyContinue
if ($Running) {
    Write-Host "正在关闭运行中的 AgentEye ..." -ForegroundColor Yellow
    $Running | Stop-Process -Force
    Start-Sleep -Milliseconds 500
}

if (Test-Path $DistDir)    { Remove-Item -Recurse -Force $DistDir }
if (Test-Path $PublishDir) { Remove-Item -Recurse -Force $PublishDir }
if (Test-Path $StageDir)   { Remove-Item -Recurse -Force $StageDir }

Write-Host "=== dotnet publish (Release, 框架依赖) ===" -ForegroundColor Cyan
dotnet publish "src\AgentEye.WinUI\AgentEye.WinUI.csproj" -c Release -o $PublishDir --nologo
if ($LASTEXITCODE -ne 0) { Write-Host "dotnet publish 失败" -ForegroundColor Red; exit 1 }

# 剪掉 pdb(符号服务器场景才需要,本地分发无用)
Get-ChildItem $PublishDir -File -Filter *.pdb -Recurse | Remove-Item -Force

New-Item -ItemType Directory -Path $DistDir -Force | Out-Null
Copy-Item -Path (Join-Path $PublishDir "*") -Destination $DistDir -Recurse -Force

# ──── 体积构成报告 ────
$distFiles = Get-ChildItem $DistDir -File -Recurse
$totalMb = [math]::Round(($distFiles | Measure-Object Length -Sum).Sum / 1MB, 1)
Write-Host "=== 分类汇总 ===" -ForegroundColor Cyan
$groups = [ordered]@{
    "WindowsAppSDK 运行时" = '^Microsoft\.(Windows|UI|WinUI|Web)|^WinUI|^WinRT|^WindowsApp|^Microsoft\.Windows\.SDK|^DWrite|^dwm|^Dwm|^dcompi|^CoreMessaging|^marshal|^wuceffectsi|^MRM|^RestartAgent|^workloads|^NpuDetect|\.winmd$|^resources\.pri$'
    ".NET 运行时"          = '^System\.|^Microsoft\.CSharp|^Microsoft\.NETCore|^mscorlib|^netstandard|^coreclr|^clrjit|^hostfxr|^hostpolicy|^windowsdesktop|^Hostfxr|^hostfxr|^nethost|^jsii|^api-ms|^utf8|^e_sqlite'
    "本应用"               = '^AgentEye\.'
    "其他"                 = '.*'
}
$classified = @{}
foreach ($g in $groups.Keys) { $classified[$g] = 0 }
foreach ($f in $distFiles) {
    $hit = "其他"
    foreach ($g in $groups.Keys) {
        if ($f.Name -match $groups[$g]) { $hit = $g; break }
    }
    $classified[$hit] += $f.Length
}
foreach ($g in $groups.Keys) {
    Write-Host ("  {0,-22} {1,8} MB" -f $g, [math]::Round($classified[$g] / 1MB, 1))
}
Write-Host "DIST: $DistDir ($totalMb MB, $($distFiles.Count) 文件)" -ForegroundColor Green
Write-Host "EXE:  $DistDir\AgentEye.exe"

# ──── 安装包:从干净 staging 打包(绝不含用户数据) ────
$Isscc = Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"
if (-not (Test-Path $Isscc)) {
    Write-Host "未找到 Inno Setup 6($Isscc),已跳过安装包" -ForegroundColor Red
    Write-Host "请安装 Inno Setup 6 后重跑 build.ps1" -ForegroundColor Red
    exit 2
}

New-Item -ItemType Directory -Path $StageDir -Force | Out-Null
Copy-Item -Path (Join-Path $PublishDir "*") -Destination $StageDir -Recurse -Force
Copy-Item -Path (Join-Path $ProjectRoot "README.md") -Destination $StageDir -Force
Write-Host "=== Inno Setup 安装包 ===" -ForegroundColor Cyan
& $Isscc "/DAppVer=$AppVer" "/DSrcDir=build\setup_stage" (Join-Path $ProjectRoot "AgentEye_Setup.iss")
if ($LASTEXITCODE -ne 0) { Write-Host "ISCC 失败;未产出安装包" -ForegroundColor Red; exit 2 }
$setupExe = Join-Path $ProjectRoot "installer\AgentEye_Setup.exe"
$setupMb = [math]::Round((Get-Item $setupExe).Length / 1MB, 1)
Write-Host "SETUP: $setupExe ($setupMb MB)" -ForegroundColor Green
Write-Host "=== Build complete ===" -ForegroundColor Green
