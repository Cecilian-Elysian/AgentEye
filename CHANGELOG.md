# Changelog

## 2026-10-22 — 多尺寸自适应 + 安装到 E 盘(feat/winui-acrylic)

### 新增

- 安装到 `E:\AgentEye\`(Release 自包含发布,491 文件 / 166 MB),
  桌面与开始菜单各建一个快捷方式;配置仍在 `~\.agenteye\`,重装不丢
- 窗口尺寸约束:`WM_GETMINMAXINFO` 子类(`SetWindowSubclass`),
  允许范围 320×400 ~ 800×1200,主尺寸仍是 420×560
- 设置页、标题栏、页脚改为自适应栅格(标签列 `*`、控件列 `Auto`),
  窄窗口不再出现控件被挤没/文字被裁

### 变更

- 更新区按钮策略:发现新版时隐藏「检查更新」,只留「下载并更新 /
  忽略此版本」,窄窗口也放得下
- 几何恢复的宽度夹取放宽到 [320, 800](原 [360, 520]),其它尺寸可持久化

## 2026-10-22 — GitHub 自动更新(feat/winui-acrylic)

### 新增

- 自动更新通道:更新源为 GitHub Releases(`Cecilian-Elysian/AgentEye`)。
  - 启动时静默检查一次(同一自然日只查一次,状态存 `cache/update_state.json`)
  - 设置页「关于」区:当前版本 / 检查更新 / 下载并更新 / 忽略此版本
  - 下载 → sha256 校验(GitHub 资产 `digest`)→ 解包 → 退出应用 →
    PowerShell 辅助脚本 `robocopy /MIR` 整目录替换 → 自动拉起新版本
  - 安装目录不可写时降级为提示手动替换(不做 UAC 提权)
- Core 新增 `Update/`(版本比较、release 解析、下载解包、替换脚本生成),
  配套 53 个 xUnit 用例,测试总数 56 → 109
- `docs/RELEASE.md`:发布契约(tag 命名、资产名、zip 内容、校验、发布步骤)

### 变更

- 应用版本号写入 csproj(`<Version>2.0.0</Version>`),与 release tag 比对
- `AGENTEYE_UPDATE_API` 环境变量可覆盖 API 基址(镜像/自建实例/本地联调)

## 2026-10-21 — WinUI 3 紧凑毛玻璃面板(feat/winui-acrylic)

本分支起 AgentEye 转为 WinUI 3 实现,Python/Tkinter 原版只保留在
`main` 与 `feat/glass-redesign` 的历史里。

### 新增

- 三层工程:`src/AgentEye.Core`(纯逻辑,零 UI 依赖)、
  `src/AgentEye.WinUI`(壳)、`tests/AgentEye.Core.Tests`(xUnit,56 例)。
- 主面板:Win11 Acrylic(`DesktopAcrylicBackdrop`)+ `AeGlassTintBrush`
  着色罩(浅 `#8CF2F2F2` / 深 `#8C000000`),紧凑单窗 420×560、
  宽度夹 [360,520]。
- 头部图标按钮组(32×32 圆角 6):返回 E72B / 暂停 E769↔E768 /
  立即刷新 E72C / 设置 E713;右侧留白按
  `TitleBar.RightInset / RasterizationScale` 动态换算。
- 总览行扁平化直排玻璃:36px kind 图标 chip(deepseek E99A / zhipu E943 /
  minimax E945 / opencode_go E756 / relay E968 / 其它 E774)+
  3px 等级色细条 + 1px 分割线 + 页脚(上次刷新 / provider 数)。
- 小组件:260×64 起步、高度随行数自适应(修旧版 3 行必裁切),
  Acrylic 背板(老系统实底降级),行内 2px 等级细条。
- config 模板默认几何 420×560(原 360×360)。

### 变更

- 主窗口去 `NavigationView`:总览/设置靠可见性切换;`GoSettings()`
  保留公开入口(托盘在用),托盘来的调用统一封送 UI 线程。
- 设置页去卡片:分组透明直排,适配紧凑窗宽。
- `AeStyles.xaml` 删除零引用的 AeKpi*/AeCardStyle/AeCardCornerRadius。

### 修复

- 托盘暂停态与主面板暂停按钮字形联动(`SyncPauseGlyph` 封送)。

### 兼容性

- `~/.agenteye/config.json` v2 schema、DPAPI `key_enc`、损坏隔离、
  v1 自动迁移与 Python 版完全同源,可直接替换使用。
