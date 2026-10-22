# AgentEye (WinUI 3)

Windows 桌面多 Key AI 额度观察工具的 WinUI 3 重写版。与 Python/Tkinter 原版
(存在于 `main` 与 `feat/glass-redesign` 分支历史)共用同一份
`~/.agenteye/config.json` 与缓存目录,可直接替换使用。

## 功能

- 主面板:Win11 Acrylic 紧凑毛玻璃面板(单窗、无导航栏、图标头部),
  总览页(全部 provider 的余额/百分比行)与设置页(外观 / 告警 / API 管理)。
  玻璃效果依赖系统「设置 → 个性化 → 颜色 → 透明效果」开启;该开关关闭时
  Windows 不渲染 Acrylic,窗口自动退化为不透明底色(系统策略,非缺陷)。
- 托盘:Shell_NotifyIconW 常驻,图标上 GDI 渲染最紧张 provider 的已用百分比;
  左键唤起主面板,右键菜单(暂停轮询 / 立即刷新 / 切换小组件 / 退出)。
- 桌面小组件:无边框置顶 260x64(高度随行数自适应),Acrylic 背板,
  不抢焦点(WS_EX_NOACTIVATE),按住拖动、松手位移 < 4px 判定为点击并
  唤起主面板,位置随关窗落盘。
- 通知:WinRT AppNotification toast,同一 provider 同一等级 60 分钟冷却,
  升级(黄转红)会重新告警;toast 不可用时降级 MessageBeep。

## 构建

依赖 .NET SDK 8+(含 Windows 工作负载)与 Windows App SDK 1.7,无需 Visual Studio:

```powershell
dotnet build src\AgentEye.WinUI -c Debug
```

产物:`src\AgentEye.WinUI\bin\Debug\net8.0-windows10.0.19041.0\win-x64\AgentEye.exe`

## 测试

```powershell
dotnet test tests\AgentEye.Core.Tests
```

56 个测试覆盖配置层(v2 schema、DPAPI、v1 迁移、损坏隔离)与 provider 层
(探测、6 种适配器、中转站、缓存、告警状态)。

## 安装

已发布安装到 `E:\AgentEye\`(自包含整目录,约 166 MB / 491 个文件,含
.NET 运行时与 Windows App Runtime,不需要另装运行库),并建好快捷方式:

- 桌面:`AgentEye`
- 开始菜单:`AgentEye`

配置与缓存仍在 `~\.agenteye\`(与安装位置无关,重装不丢配置)。
自己重新发布:

```powershell
dotnet publish src\AgentEye.WinUI -c Release -r win-x64 --self-contained true -o E:\AgentEye
```

## 更新

- 更新源:GitHub Releases(`github.com/Cecilian-Elysian/AgentEye`)
- 启动时后台静默检查一次(同一自然日只查一次),有新版弹 toast 提示
- 设置页「关于」区可随时手动「检查更新」,发现新版可「下载并更新」:
  应用内下载 → sha256 校验 → 解包 → 退出 → 脚本整目录替换 → 自动重启
- 安装目录不可写(如装在 Program Files)时,会提示改用浏览器下载后手动替换
- 发布格式约定见 `docs\RELEASE.md`

## 文件结构

```
src\AgentEye.Core        逻辑层(net8.0,无 UI 依赖)
  Config\                v2 schema 读写、DPAPI 加密、迁移与损坏隔离
  Providers\             探测与 6 种 provider 适配器 + 中转站
  Cache\                 models/probe/alert 状态缓存
src\AgentEye.WinUI       壳层(WinUI 3)
  Pages\                 OverviewPage / SettingsPage
  Services\              AeRes / AppServices / PollerService / NotifyService
  Styles\                AeStyles.xaml(工程自有样式)
  Tray\                  托盘(纯 Win32 + GDI)
  Widget\                桌面小组件
tests\AgentEye.Core.Tests
```

工程契约(资源取用、XAML 坑、config 兼容)见 `AGENTS.md`;改造执行计划
收录于 `docs\PLAN-winui-acrylic.md`;发布格式约定见 `docs\RELEASE.md`;
变更记录见 `CHANGELOG.md`。

## 与 Python 版的已知差异

- 模型列表面板(原版 `Panel` 的 models 视图)暂未移植,models 缓存仍会写入。
- 设置页表单为同窗切换(列表 <-> 表单),交互对齐原版但视觉为 Fluent 控件。
- 托盘菜单"切换小组件"对应原版小组件显隐开关。
