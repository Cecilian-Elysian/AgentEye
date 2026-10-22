# AgentEye 的工程契约(WinUI 3 版)。

## 项目定位

Windows 桌面多 Key AI 额度观察工具。UI 采用 Win11 Acrylic 紧凑毛玻璃面板
(单窗、无导航栏、图标头部),另有两个常驻面:无边框桌面小组件(不抢焦点)
与托盘图标(图标上 GDI 渲染最紧张 provider 的数字)。
**只支持 Windows 10 1809+ / Win11**,依赖 DPAPI、WinRT toast 与 WinAppSDK,
不承诺跨平台。Python/Tkinter 原版只存在于 `main` 与 `feat/glass-redesign`
的历史里,不再维护。

## 三层结构

- `src/AgentEye.Core`:net8.0 纯逻辑,**零 UI 依赖**——config v2 读写、
  DPAPI 加解密、6 种 provider 适配器、缓存、阈值判定、更新检查
  (`Update/`:版本比较、release 解析、下载校验、安装器拉起)。只引
  `System.Security.Cryptography.ProtectedData`。
- `src/AgentEye.WinUI`:WinUI 3 壳——MainWindow(去导航紧凑单窗)、
  Pages(总览/设置)、Widget(小组件)、Tray(托盘)、Services(AeRes /
  Poller / Notify / AppServices)、Styles(AeStyles.xaml)。
- `tests/AgentEye.Core.Tests`:xUnit,只测 Core(契约层),WinUI 层靠
  人工核对。

## 构建与测试

```text
dotnet build src\AgentEye.WinUI -c Debug -v q --nologo   # 0 error 才算过
dotnet test tests\AgentEye.Core.Tests -v q --nologo      # 56 passed
```

冒烟:启动 exe 7 秒未退出。改 XAML 后必须重构建确认 pass1 没有静默崩。

## 发布形态

- **框架依赖**(csproj 里 `SelfContained=false` + `WindowsAppSDKSelfContained=false`):
  产物 41 文件 / 36 MB,运行时用系统装的 .NET 8 Desktop Runtime +
  Windows App Runtime 1.7。`SatelliteResourceLanguages=zh-Hans;en`
  砍掉 83 种语言卫星资源。`RuntimeIdentifier` 必须无条件设 win-x64,
  否则框架依赖发布直接失败。
- 要自包含版(换机即用,166 MB)得临时改回这两个属性——别长期并存两套。
- 一键构建 `build.ps1`(项目根,模式对齐 key_note):publish → 剪 pdb →
  `dist\`(便携目录)→ 体积报告 → Inno Setup 出 `installer\AgentEye_Setup.exe`
  (lzma2 约 7.6 MB)。`build\`、`dist\`、`installer\` 全部 gitignore;
  staging 是干净的,config 在 `~\.agenteye` 与安装目录无关,无需备份还原。
- PS1 含中文**必须带 UTF-8 BOM**(PS5.1 无 BOM 按 GBK 读,中文全串烧)。

## 安装器契约(AgentEye_Setup.iss)

- `AppId=AgentEye` 显式写死——升级链依赖它稳定,改名即断链。
- `DefaultDirName=E:\AgentEye` + `DisableDirPage=auto`(升级沿用旧目录)。
- `PrivilegesRequired=lowest`,HKCU 注册表,无需管理员。
- `CloseApplications=yes` + `RestartApplications=yes`:静默升级时安装器经
  Restart Manager 关掉运行中的应用、装完自动重启——**应用内更新靠这一对**,
  所以 UpdateService 拉起安装器后**不自己退出**(安装失败应用还活着)。
- [Run] 项带 `skipifsilent`:静默安装(更新场景)不弹"启动应用",
  重启交给 RestartApplications。


## 窗口尺寸契约

- 主尺寸 **420×560**(用户确认的紧凑面板),写在 `MainWindow.xaml.cs`
  的 `DefaultWidth/DefaultHeight`;物理像素,与 config 的
  `ui.width/ui.height` 同源(存的是物理像素,恢复时同源)。
- 允许范围 320×400 ~ 800×1200,靠 `WM_GETMINMAXINFO` 子类
  (`SetWindowSubclass`)约束;越界拖拽会被系统夹回。
- **其它尺寸必须自适应**:横向排列容易撑破的地方一律用 Grid
  (标签列 `*` + 控件列 `Auto`),不要用固定宽度的横排 StackPanel;
  文字加 `TextTrimming`,页脚/标题用两列 Grid 防重叠。
- 窄窗口下头部按钮区优先(标题裁剪),设置页靠 ScrollViewer 滚动。

## 主题资源契约

- 代码里取主题画刷**必须走 `Services/AeRes.Brush(el, key)` /
  `BrushOrNull`**;普通 `Application.Current.Resources.TryGetValue`
  不会下钻 ThemeDictionaries,拿到的永远是默认主题——禁止直连。
- `AeRes` 查主题子字典时**字符串键("Light"/"Dark")与枚举键
  (ElementTheme.Light)都要试**:XAML 里写的是 `x:Key="Light"` 字符串,
  `el.ActualTheme` 是枚举装箱值,两者不相等——只试一种会静默退化成
  灰色兜底(行文字/分割线/小组件底色全变灰,很显眼)。
- 新增主题色必须同时给 `App.xaml` 的 Light/Dark 两个子字典;主题无关色
  (等级色、`AeErrorBrush`)放根字典,可用 `{StaticResource}` 直引。
- 样式集中在 `Styles/AeStyles.xaml`;删样式前先全工程搜引用。
- 代码画的行(总览/小组件)在 `ActualThemeChanged` 里整批重渲染。

## XAML 契约

- 属性值若以 `{` 开头(如字面 JSON)必须写成 `{}{...}` 转义,否则
  XamlCompiler pass1 静默崩溃、无报错行号。子元素排在属性元素
  (如 `<Grid.RowDefinitions>`)**之前**会确定性复现 pass1 静默崩
  (3/3)——属性元素一律写在最前。另:pass1 偶发无差别静默崩
  (同内容重试即过,疑似增量状态/并行节点竞态),遇 MSB3073 无
  诊断输出先原样重跑一次、再清 `obj` 重跑,别急着改代码。
- 头部图标按钮是 32×32、透明底、圆角 6 的 `Button` + `FontIcon`;
  按钮区右侧留白 = `AppWindow.TitleBar.RightInset / RasterizationScale`
  (物理像素换算 DIP),别硬编码。
- 图标字形统一用 Segoe Fluent Icons 码位(E769/E768/E72C/E713/E72B、
  行图标 E99A/E943/E945/E756/E968/E774),不许内嵌图片。

## 中文文件

含中文的文件一律用编辑器工具(Read/Write/Edit)读写;PowerShell 5.1 的
`Get-/Set-Content` 按 GBK 解码 UTF-8,会把整个文件写坏。字节级复制
(Copy-Item / robocopy)安全。

## config 契约(与 Python 版同源,不得破坏)

- `~/.agenteye/config.json`,v2 schema(`providers[]` + `ui.*` +
  `alert.*`),`schema_version` 非 2 即按版本异常处理。
- API Key 内存态明文、磁盘态 `key_enc`(DPAPI CurrentUser + 标准
  base64);写盘前深拷贝加密,发现明文残留直接抛 `PlaintextKeyError`。
- 损坏隔离:JSON/UTF-8/根类型坏 → 先把原文件改名
  `config.json.corrupt-<时间戳>-<随机>` 再按模板启动,**绝不覆盖原文**。
- v1(5 个分立数组)自动迁移,原文件 DPAPI 加密备份 `.v1.bak`。
- 写盘必须原子(临时文件 + `File.Move` + flush-to-disk)。
- 环境变量覆盖解密后的 key(`*_API_KEY`),且不落盘。
- UI 只暴露 url/key/model;其余字段让用户手改 config。
- 小组件几何:`ui.widget_pos` 落盘取松手时的 `_lastPos`(事件坐标),
  不读 `AppWindow.Position`(回显滞后);松手位移 <4px 判点击。

## 增强面降级

托盘(`TrayIconService`,Shell_NotifyIconW + GDI 数字图标,配色硬编码是
设计决定勿改)与小组件(`WidgetWindow`,WS_EX_NOACTIVATE|TOOLWINDOW)
都是增强面:任何 Win32/WinRT 步骤失败只能静默降级,不许把主流程带崩。
`DesktopAcrylicBackdrop` 在老系统上可能抛异常,赋值处必须 try/catch。
系统「透明效果」关闭时(注册表 `EnableTransparency=0`)Windows 一律不渲染
Acrylic/Mica,窗口退化为不透明底色——这是系统策略,别去代码里绕。

## 更新机制

- 更新源是 GitHub Releases;检查逻辑在 `Core/Update/`,编排在
  `WinUI/Services/UpdateService.cs`。
- 状态存 `cache/update_state.json`(上次检查时间、忽略的版本)——
  **不要往 config 里塞更新的键**(config 与 Python 版同源,别破坏)。
- 版本号只认 csproj 的 `<Version>`;发布格式约定见 `docs/RELEASE.md`。
- 更新资产是 **`AgentEye_Setup.exe`(Inno 安装器)**:下载 → sha256 校验 →
  `/VERYSILENT` 拉起安装器,关进程/替换/重启全归它。旧的
  zip→robocopy 替换脚本方案已删(`ExtractZip`/`DetectPayloadRoot` 不复存在)。
- 安装目录不可写时下载前就拒绝(提示手动修复);排障看 Inno 的
  `%TEMP%` Setup Log,不再有 apply.ps1.log。
- `AGENTEYE_UPDATE_API` 可覆盖 API 基址(镜像/自建实例/本地联调)。
- 更新是增强面:任何一步失败只落状态文案,不许把主流程带崩。

## 退出码

`dotnet run` 场景不承诺退出码;Core 抛 `ConfigError` 族在壳层兜住后
弹错误 UI。进程因未处理异常退出即为 bug。
