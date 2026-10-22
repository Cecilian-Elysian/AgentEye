# 发布契约(自动更新用)

应用的"检查更新"走 GitHub Releases。本文件规定发布时必须满足的格式,
否则应用会提示"release 里没有 setup.exe 安装包"或拒绝安装。

- 仓库:`github.com/Cecilian-Elysian/AgentEye`(公开,应用用匿名 API 读取)
- 应用侧实现:`src/AgentEye.Core/Update/`(检查/下载/校验)与
  `src/AgentEye.WinUI/Services/UpdateService.cs`(编排/拉起安装器)
- 一键构建:`build.ps1`(项目根)→ `dist\`(便携目录)+ `installer\AgentEye_Setup.exe`

## 一、版本号

版本号写在 `src/AgentEye.WinUI/AgentEye.WinUI.csproj`:

```xml
<Version>1.0.0</Version>
<FileVersion>1.0.0.0</FileVersion>
```

`build.ps1` 从 csproj 读版本注入安装器(**csproj 是唯一真源**)。

应用启动时读程序集的 `AssemblyInformationalVersion`(自动去掉 `+<sha>` 后缀),
与 release 的 `tag_name`(去 `v` 前缀)比较。三段式语义化版本,支持
`v2.1`、`2.1.0`、`2.1.0-beta`(预发布版视为低于同号正式版)。

**tag 必须与 csproj 里的 Version 一致**,否则应用会认为"已是最新"。

## 二、资产命名

release 至少要有一个资产,名字必须匹配:

```
AgentEye_Setup.exe             ← 精确名,优先选用
AgentEye-<任意版本>-Setup.exe   ← 也接受
```

- 必须是 `.exe`(Inno Setup 安装器),且名字里含 `setup.exe`(不区分大小写)
- `.zip`、`.msix`、`.msi`、`.txt` 都会被忽略

## 三、安装包内容

`AgentEye_Setup.exe` 由 Inno Setup 6 打包(`AgentEye_Setup.iss`),里面是
**完整的框架依赖发布目录**(运行时用系统装的 .NET 8 Desktop Runtime +
Windows App Runtime 1.7)。lzma2/max 压缩后约 **7.6 MB**。

打包方式(两种等价,推荐第一种):

```powershell
# 一键:publish → 剪 pdb → dist\ → 体积报告 → installer\AgentEye_Setup.exe
powershell -NoProfile -ExecutionPolicy Bypass -File build.ps1

# 只重编安装器(源目录默认 dist,可用 /DSrcDir 换)
& "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" /DAppVer=1.0.0 /DSrcDir=dist AgentEye_Setup.iss
```

安装器行为(见 `AgentEye_Setup.iss`):

- `PrivilegesRequired=lowest`,默认装 `E:\AgentEye`,首装显示目录页、升级沿用旧目录
- 桌面快捷方式(默认勾)、开机自启 HKCU Run(默认不勾)
- `CloseApplications=yes` + `RestartApplications=yes`:升级时经 Restart Manager
  关掉运行中的应用,装完自动重启——**应用内静默更新靠的就是这一对**
- 卸载入口:开始菜单 + 系统设置"应用"(HKCU Uninstall 注册表)

**用户端前置依赖**(框架依赖发布的代价):目标机器需已安装
.NET 8 Desktop Runtime 与 Windows App Runtime 1.7。WinAppSDK 自带
`WindowsAppRuntime.Bootstrap.dll`,缺 WinApp Runtime 时它能自动补装,
但缺 .NET 8 需要用户手动装。

## 四、校验(可选但建议)

应用按以下顺序取 sha256:

1. release 资产的 `digest` 字段(形如 `sha256:abc...`,GitHub 会给新上传的资产带上)
2. 都没有 → 跳过校验(仍可安装,但不校验完整性)

## 五、更新行为(用户侧会发生什么)

1. 应用下载 `AgentEye_Setup.exe` 到 `%TEMP%\AgentEye\update\<版本>\`
2. 校验 sha256(有 `digest` 时)
3. 拉起安装器:`AgentEye_Setup.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART
   /CLOSEAPPLICATIONS /RESTARTAPPLICATIONS`
4. 安装器经 Restart Manager 关掉运行中的应用 → 覆盖安装 → 自动重启新版

约束:

- **安装目录必须可写**。不可写时应用会在下载前就拒绝,提示手动修复。
- 本进程不主动退出——安装器万一失败,应用还活着,可以重试或手装。
- 排障:Inno 安装器自身的日志在 `%TEMP%`(Setup Log.*)。

## 六、发布步骤

```powershell
# 1. 改版本号
#    src\AgentEye.WinUI\AgentEye.WinUI.csproj → <Version>1.1.0</Version>
# 2. 一键构建(产物:dist\ + installer\AgentEye_Setup.exe)
dotnet test tests\AgentEye.Core.Tests
powershell -NoProfile -ExecutionPolicy Bypass -File build.ps1
# 3. 提交 + 打 tag + 推送
git add -A; git commit -m "release: v1.1.0"
git tag -a v1.1.0 -m "v1.1.0"
git push origin main --tags
# 4. 建 release(网页或 gh CLI),资产传 installer\AgentEye_Setup.exe
gh release create v1.1.0 installer\AgentEye_Setup.exe --title "AgentEye 1.1.0" --notes "更新说明"
```

注意:`gh` 需要先 `gh auth login`;release 建好后应用才能查到这个版本。

## 七、已验证的更新链路

- 静默安装:`AgentEye_Setup.exe /VERYSILENT …` 装进 E:\AgentEye,
  版本/卸载注册表/桌面入口全部就位,冒烟通过。
- 检查→下载→校验→拉起安装器的链路与旧 zip 方案共用同一套
  CheckAsync/DownloadAsync,检查与下载部分沿用既有端到端验证。
