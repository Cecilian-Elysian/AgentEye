# 执行计划:WinUI 紧凑毛玻璃面板(AgentEye 仓库新分支)

> 状态:已执行完毕(2026-10-21,feat/winui-acrylic 分支)
> 目标仓库:本仓库(仓库根)
> 源目录(移植前的可运行版):仓库外工作目录 `AgentEyeWinUI`——**已于 2026-10-22 删除**
> (内容已全部并入本仓库,基线提交 `c333855` 收录了移植时的原始版本,bin/obj 为构建垃圾)
> 参考视觉:Win11 Acrylic 小面板(标题 + 刷新/关闭图标 + 图标/名称/副标题/大百分比/
> 细进度条 + 底部"更新于 / N 台")

---

## 0. 当前状态快照(开工前核对)

- `AgentEyeWinUI`:可编译、56/56 Core 测试通过、冒烟通过。
  - 构建:`dotnet build src\AgentEye.WinUI -c Debug`
  - 测试:`dotnet test tests\AgentEye.Core.Tests`
  - 产物:`src\AgentEye.WinUI\bin\Debug\net8.0-windows10.0.19041.0\win-x64\AgentEye.exe`
  - 结构:`src\AgentEye.Core`(net8.0 逻辑)/ `src\AgentEye.WinUI`(WinUI 3 壳)/ `tests\AgentEye.Core.Tests`
- `AgentEye` 仓库:
  - 当前分支 `feat/glass-redesign`,有 **32 个未提交改动**(Python 改皮 WIP)
  - 关键提交:`a7ee9a9 feat(ui): 对话框换皮 + provider 品牌色点;新增玻璃层回归测试` 等
  - 本地分支:`main`、`feat/glass-redesign`;远端 `origin/main`、`origin/feature/v2`
  - 根目录有个人文件 `2026.10.1 7 reverse.txt` —— **不要删除/提交**
  - `.gitignore` 目前是 Python 版

## 1. 仓库操作(保护现场 → Python 只留历史)

按顺序执行(在 AgentEye 仓库内):

```powershell
# 1) WIP 进历史(不丢任何改动)
git add -A
git commit -m "wip: python glass redesign 保存现场"

# 2) 从 main 起新分支,新分支历史干净(Python 只存在于 main 的历史)
git checkout main
git checkout -b feat/winui-acrylic

# 3) 删除 Python 树(只删 git 跟踪的;个人 txt 不动)
git rm -r providers ui tests
git rm main.py config.py cache.py secure.py notify.py run.bat
git rm requirements.txt requirements-dev.txt config.example.json CHANGELOG.md AGENTS.md
# .pytest_cache/__pycache__ 若被跟踪一并删除,否则留着(已被忽略)

# 4) 从 AgentEyeWinUI 拷入(排除 bin/obj)
#    AgentEye.sln、src\AgentEye.Core、src\AgentEye.WinUI、tests\AgentEye.Core.Tests、README.md
#    用文件工具复制,不要用 shell 拼接中文内容

# 5) .gitignore 换 C# 版:
#    bin/  obj/  .vs/  *.user  TestResults/  .idea/  *.swp
#    (保留原 Python 段可删;不要忽略 .sln/.csproj)

# 6) AGENTS.md 重写为 WinUI 工程契约(见 §6)
# 7) 提交基线
git add -A
git commit -m "feat(winui): 引入 WinUI 3 三层工程,移除 Python 实现"
```

注意:

- `AgentEyeWinUI` 目录**暂不删除**,作为对照;本轮验收通过后再由用户决定删。
- 若拷贝后首次编译报 exe 被占用:先 `Stop-Process -Name AgentEye -Force`。

## 2. 毛玻璃基础设施

1. 两个窗口的背板:`MicaBackdrop` → `DesktopAcrylicBackdrop`
   - `MainWindow.xaml`:`<Window.SystemBackdrop><DesktopAcrylicBackdrop /></Window.SystemBackdrop>`
   - `WidgetWindow.cs`:`_window.SystemBackdrop = new DesktopAcrylicBackdrop();`(try/catch 静默降级)
2. 新增主题跟随着色罩 `AeGlassTintBrush`(App.xaml ThemeDictionaries):
   - Light:`#8CF2F2F2`
   - Dark:`#8C000000`
   - 用法:Root 最底层铺一个 `Border Background="{ThemeResource AeGlassTintBrush}"` 且
     `IsHitTestVisible="False"`,内容叠在其上。Acrylic 底层跟系统主题,着色罩保证
     手选浅/深时观感一致、文字有对比度。
3. `WidgetWindow.RepaintChrome` 同步改用 `AeGlassTintBrush` + `AeCardStrokeBrush`(保持现状 API)。

## 3. 主窗口(去导航 + 紧凑单窗)

文件:`src/AgentEye.WinUI/MainWindow.xaml` + `.xaml.cs`

- 删除整个 `NavigationView`;Root 布局:
  - Row0:48px 头部(`x:Name="AppTitleBar"`,`SetTitleBar(AppTitleBar)`)
    - 左:12px 圆点(Ellipse,AccentFillColorDefaultBrush)+ 标题 `AgentEye` / `设置`(`AppTitle`)
    - 右:`BtnPause`(暂停/恢复,图标)、`BtnRefresh`(立即刷新)、`BtnSettings`(齿轮)/`BtnBack`(返回,设置态显示)
    - 右侧留白 = `AppWindow.TitleBar.RightInset / XamlRoot.RasterizationScale`(物理像素换算 DIP)
  - Row1:`PageHost`(Grid),挂 `OverviewPage` 与 `SettingsPage`,显隐切换
- `GoSettings()` 改成 `ShowPage("settings")`;新增 `GoOverview()`;
  `ShowPage` 负责:标题文本、`BtnSettings`/`BtnBack` 可见性、调用 `SettingsPage.OnShown()`
- 默认几何 420×560(已存 `ui.width/height` 仍优先;最小宽 360)
- `ApplyTheme` / `SyncCaptionButtons` 保持;`WidgetWindow.ApplyTheme(choice)` 保持
- 头部图标按钮:32×32、透明底、圆角 6、`FontIcon` 字形(暂停 E769 / 播放 E768 /
  刷新 E72C / 设置 E713 / 返回 E72B)
- 旧 `Nav_SelectionChanged`、`Nav` 引用全部删除;`BtnTogglePause_Click` 逻辑移到
  MainWindow(按钮在窗口头部),`OverviewPage.BtnTogglePause/BtnRefresh` 移除

## 4. 总览页(对齐截图行样式)

文件:`src/AgentEye.WinUI/Pages/OverviewPage.xaml` + `.xaml.cs`

- XAML:根为 `Grid`(Row0 列表 `ScrollViewer>StackPanel x:Name="RowsHost"`,
  Row1 页脚)。去掉标题行(标题在窗口头部)。
- 页脚:`Grid` 两列,左 `FooterUpdated`(「更新于 HH:mm」/「尚未刷新」),
  右 `FooterCount`(「N 个」);12px,`AeTextSecondaryBrush`;上方 1px `AeDividerBrush`
- 行(代码构建,`BuildRow` 重写):
  - 容器 `Grid` 三列:`Auto`(36 圆图标)/ `*`(名称+副标题+细条)/ `Auto`(大数字)
  - 图标:36×36 `Border CornerRadius=18`,背景 = 等级色 20% 透明度(或主题色),
    内嵌 `FontIcon` 15px,前景 = 等级色;kind→字形:
    - `deepseek` → `E99A`(机器人)
    - `zhipu` → `E943`(代码)
    - `minimax` → `E945`(闪电)
    - `opencode_go` → `E756`(终端)
    - `relay` → `E968`(网络)
    - `generic_openai` / 其它 → `E774`(地球)
  - 名称:14px SemiBold,`AeTextPrimaryBrush`;暂停时 Opacity 0.5 且后缀「· 已暂停」
  - 副标题:11px,`AeTextSecondaryBrush`,单行省略 = `kind · detail`(Error 时显示 Error)
  - 细进度条:`ProgressBar` Height=3,CornerRadius=1.5,值 = Pct;前景按等级色
    (通过 `ProgressBar.Foreground = LevelBrush`)
  - 大数字:22px SemiBold + 小号单位(用 `TextBlock` 拼 `75%` / `$12.34` / `未配置` / `!`)
  - 行底:1px `Border Background="{ThemeResource AeDividerBrush}"`(不占宽度时用 Margin)
  - 行间距 10、上下 Padding 8
- 保留:右键菜单(暂停/编辑/删除)、`ConfirmDeleteAsync`、`TogglePause`
- `OnResultsChanged`:更新 `FooterUpdated`/`FooterCount`,重建行
- `ActualThemeChanged` 重渲染保持;所有颜色走 `AeRes`(禁止 `Application.Current.Resources.TryGetValue`)

## 5. 设置页 + 小组件

设置页(`SettingsPage.xaml`):

- 三张 `Border Style="{StaticResource AeCardStyle}"` → 改为透明分组:
  段标题(`AeSectionTitleStyle`)+ 1px `AeDividerBrush` 分割线,组间 16px
- 保留:外观 RadioButtons、告警开关/两条阈值、API 管理列表↔表单、删除确认、错误提示
- 删掉不再使用的 `AeKpi*` 样式与 `AeCardStyle` 的卡片底(如仍被引用则保留样式名、改透明)

小组件(`Widget/WidgetWindow.cs`):

- 尺寸 260×64;Acrylic 背板 + `AeGlassTintBrush` 罩
- 行样式同总览迷你版:7px 色点/图标 + 名称 11px + 右侧数值 11px + 2px 细条
- 保留:WS_EX_NOACTIVATE|WS_EX_TOOLWINDOW、拖动/点击(松手 <4px 判点击)、
  `ui.widget_pos` 落盘、`Show(false)` 不激活

## 6. AGENTS.md(WinUI 版)要点

- 项目定位:Windows 桌面多 Key 额度观察,WinUI 3 紧凑毛玻璃面板 + 托盘 + 小组件
- 三层结构:`src/AgentEye.Core`(纯逻辑,net8.0)/ `src/AgentEye.WinUI`(壳)/ `tests/AgentEye.Core.Tests`
- 构建:`dotnet build src\AgentEye.WinUI -c Debug`;测试:`dotnet test tests\AgentEye.Core.Tests`
- 主题契约:代码取主题资源必须走 `Services/AeRes.Brush(el, key)`,
  不许对 `Application.Current.Resources` 直接 `TryGetValue`(不会下钻 ThemeDictionaries);
  新增主题色必须同时给 Light/Dark 两个子字典
- XAML 属性值若以 `{` 开头必须转义(如 `{}{"a":1}`),否则 XamlCompiler pass1 静默崩溃
- 中文内容文件只用编辑器工具(Read/Write/Edit);PS 5.1 的 Get/Set-Content 会按 GBK 解码 UTF-8
- config 契约不变:`~/.agenteye/config.json` v2 schema、DPAPI `key_enc`、损坏隔离;
  UI 只暴露 url/key/model,其余字段改 config
- 退出码约定(如保留):0 正常 / 1 未预期 / 2 配置无效 / 3 / 4 视实现

## 7. 验证清单

```powershell
dotnet build src\AgentEye.WinUI -c Debug -v q --nologo   # 0 error
dotnet test tests\AgentEye.Core.Tests -v q --nologo      # 56 passed
# 冒烟:启动 7 秒未退出
$p = Start-Process "bin\Debug\...\AgentEye.exe" -PassThru; Start-Sleep 7; $p.HasExited
```

人工核对:

1. 浅色/深色:Acrylic 模糊可见、文字对比度够、标题栏 caption 按钮可见
2. 头部:暂停/刷新/设置/返回按钮可点;标题随页面切换
3. 总览:行样式(图标/名称/副标题/大数字/细条/分割线)、页脚更新时间与数量
4. 设置:段标题+分割线布局、表单保存、删除确认、告警设置生效
5. 小组件:毛玻璃底、迷你行、拖动与点击、位置记忆
6. 托盘:数字图标与菜单正常

## 8. 已知风险/注意

- `DesktopAcrylicBackdrop` 在 Win10/老 Win11 自动降级;仍要 try/catch 兜底
- 头部按钮位于 SetTitleBar 区域内,WinUI 3 下可接收点击;若实测不可点,
  改用 `InputNonClientPointerSource` 或把按钮下移到内容区第一行
- 旧配置可能存了 900×640 几何 → 首次打开不是紧凑尺寸;可接受,或加载时
  把 width 夹到 [360, 520](二选一,执行时决定并在 README 记录)
- 设置页 `FormError` 用 `StaticResource AeErrorBrush`(根字典主题无关色)是安全的
- 托盘 GDI 配色硬编码是设计决定(图标不随主题变),勿改
- 任何 XAML 新增中文属性值保持原文;提交前跑一次构建确认 pass1 未崩

## 9. 完成定义

- 新分支 `feat/winui-acrylic` 上:Python 已移除(历史保留)、WinUI 工程可构建可测试
- 冒烟 + 人工核对通过
- 提交信息:`feat(winui): 紧凑毛玻璃面板(去除导航栏/图标头部/行样式/小组件统一)`
