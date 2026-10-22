# 发布契约(自动更新用)

应用的"检查更新"走 GitHub Releases。本文件规定发布时必须满足的格式,
否则应用会提示"release 里没有 win-x64 安装包"或拒绝安装。

- 仓库:`github.com/Cecilian-Elysian/AgentEye`(公开,应用用匿名 API 读取)
- 应用侧实现:`src/AgentEye.Core/Update/`(检查/下载/校验)与
  `src/AgentEye.WinUI/Services/UpdateService.cs`(编排/替换/重启)

## 一、版本号

版本号写在 `src/AgentEye.WinUI/AgentEye.WinUI.csproj`:

```xml
<Version>2.0.0</Version>
<FileVersion>2.0.0.0</FileVersion>
```

应用启动时读程序集的 `AssemblyInformationalVersion`(自动去掉 `+<sha>` 后缀),
与 release 的 `tag_name`(去 `v` 前缀)比较。三段式语义化版本,支持
`v2.1`、`2.1.0`、`2.1.0-beta`(预发布版视为低于同号正式版)。

**tag 必须与 csproj 里的 Version 一致**,否则应用会认为"已是最新"。

## 二、资产命名

release 至少要有一个资产,名字必须匹配:

```
AgentEye-win-x64.zip          ← 精确名,优先选用
AgentEye-<任意版本>-win-x64.zip   ← 也接受
```

- 必须是 `.zip`,且名字里含 `win-x64.zip`
- 其它架构(`win-arm64.zip`)、`.msix`、`.txt` 都会被忽略

## 三、zip 内容(关键)

zip 里装的是**完整的自包含发布目录**,不是单个 exe。当前产物是
496 个文件 / 约 166 MB(含 .NET 运行时、WindowsAppRuntime、WinUI)。

打包方式:

```powershell
dotnet publish src\AgentEye.WinUI -c Release -r win-x64 --self-contained true -o publish\AgentEye-win-x64
Compress-Archive -Path publish\AgentEye-win-x64\* -DestinationPath AgentEye-win-x64.zip
```

zip 的根目录里必须能找到 `AgentEye.exe`:
- 根目录直接放(推荐):`zip:AgentEye.exe` ✓
- 套一层目录也可以:`zip:AgentEye-win-x64/AgentEye.exe` ✓(应用会自动下钻一层)
- 套多层/找不到 exe:应用判定"安装包结构不符合预期",拒绝更新

## 四、校验(可选但建议)

应用按以下顺序取 sha256:

1. release 资产的 `digest` 字段(形如 `sha256:abc...`,GitHub 会给新上传的资产带上)
2. 都没有 → 跳过校验(仍可安装,但不校验完整性)

若两者都没有,想要校验,可以在 release 里再传一个同名 `.sha256` 边车文件
(内容是 64 位十六进制);**当前版本不读边车文件**,只有 `digest` 生效。

## 五、替换行为(用户侧会发生什么)

1. 应用下载 zip 到 `%TEMP%\AgentEye\update\<版本>\`
2. 校验 sha256(有 `digest` 时)
3. 解包并定位 payload 根
4. 生成 `%TEMP%\AgentEye\update\<版本>\apply.ps1`,启动它(隐藏窗口)
5. 应用退出 → 脚本 `robocopy /MIR` 整目录覆盖安装目录(顺带清掉旧版本残留文件)
6. 脚本拉起新版本

约束:

- **安装目录必须可写**。装在 `Program Files` 下不可写 → 应用会明确提示
  "安装目录不可写",请改用浏览器下载后手动替换(不做 UAC 提权)。
- 替换的是**整个目录**,所以 zip 必须是完整发布目录,否则会把旧文件清掉。
- 失败可查:脚本把每一步写进同目录的 `apply.ps1.log`。

## 六、发布步骤

```powershell
# 1. 改版本号
#    src\AgentEye.WinUI\AgentEye.WinUI.csproj → <Version>2.1.0</Version>
# 2. 跑测试与构建
dotnet test tests\AgentEye.Core.Tests
dotnet build src\AgentEye.WinUI -c Release
# 3. 打包(见第三节)
# 4. 提交 + 打 tag + 推送
git add -A; git commit -m "release: v2.1.0"
git tag -a v2.1.0 -m "v2.1.0"
git push origin main --tags
# 5. 建 release(网页或 gh CLI)
gh release create v2.1.0 AgentEye-win-x64.zip --title "AgentEye 2.1.0" --notes "更新说明"
```

注意:`gh` 需要先 `gh auth login`;release 建好后应用才能查到这个版本。

## 七、已验证的更新链路

本地用假 GitHub API(返回 `releases/latest` + zip)端到端验证过:
检查 → 提示新版本 → 下载 → sha256 校验 → 解包 → 定位 payload →
生成脚本 → 应用退出 → robocopy 整目录替换 → 拉起新版本。
替换用的是整目录镜像(`/MIR`),旧版本残留文件会被清掉。
