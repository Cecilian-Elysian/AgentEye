# AgentEye

> 常驻桌面的多 Key 额度观察工具。粘贴 key 即用,自动识别 provider 类型,
> 自动拉取可用模型列表,实时显示总额度与各 provider 明细。

## 特性

### 监控与告警

- **粘贴 key 即用**:Add Key 对话框自动识别 provider(OpenAI 兼容 / 中转站 / MiniMax / OpenCode Go / DeepSeek / 智谱)
- **5 个一键预设**:Add Key 顶部 5 个按钮(MiniMax / DeepSeek / 智谱 / OpenCode / 中转站),点一下自动填默认 URL 和名称
- **金额/额度双视图**:金额行(`$ ¥ 额度`)无进度条 + 💰 前缀 + 暖色底;百分比行带渐变进度条
- **今日已用 / 总额**:中转站显示 `今日 $X.XX / $Y.YY`,百分比行继续显示 `5h% · 周% · 倒计时`
- **消耗渐变色**:绿→黄→红三色插值,基于 `used_today/total` 计算消耗比,主值与 detail 中所有 `$X` / `¥X` / `X%` 同步上色
- **per-provider 告警冷却**:同一 provider 同等级告警 60 分钟内不重复弹;等级切换(warn → critical)算新告警

### 窗口与交互

- **窗口可拖拽 resize**:右下角 grip 调整面板大小(280×180 ~ 800×900),实时自适应 wraplength
- **主面板 + 模型面板 拖拽重排**:长按 > 8 px 触发,红线指示器,顺序持久化;模型面板拖完自动触发一次额度刷新
- **窗口固定按钮**:Header `⊙` / `○` 切换 topmost,状态持久化
- **最小化按钮**:Header `–` 最小化到任务栏,点击任务栏还原(自动恢复无边框 + 置顶)
- **Header 风格统一**:`≡ ⊙ – ×` 全部为 flat 深色按钮,hover 高亮
- **主面板滚动条**:窗口缩小或 provider 多时,右侧滚动条 + 滚轮滚动查看
- **边缘磁吸 + 快捷键**:F5 刷新,Ctrl+Q 退出,Esc 关闭弹窗,聚焦时自动刷新

### 模型与试调

- **模型列表自动拉取**:每个 provider 显示 `/v1/models`,按能力分组(Claude / GPT / Gemini / ...),支持搜索(计数实时更新,拖动不跳滚动位)
- **1-token 试调**:点击"试调"发送 1 token 请求,显示延迟,记录到 `~/.agenteye/cache/probe.jsonl`
- **价格计算器**:模型详情面板估算 N 次调用的花费(常见模型公开价表)

### 配置与管理

- **设置界面**:Header `≡` 打开,改刷新间隔、¥ 临界阈值、% 告警阈值 + 主题切换;链接 "添加 API Key" 跳转独立 AddKeyDialog(5 预设 + 自动探测 + 连续添加)
- **删除确认**:右键删除 provider 需输入名字确认,同时清理 models 缓存并追加 probe 日志标记
- **首启欢迎 toast**:首次启动给出操作提示
- **v1 自动迁移**:旧的 5 个分立数组配置自动升级为统一 `providers[]`,备份为 `config.json.v1.bak`

## 快速开始

```
git clone ...
双击 run.bat
```

依赖: `requests`、`tkinter`(标准库)。

```
run.bat          双击(后台 pythonw,无控制台)
python main.py   前台运行便于看报错
```

## 配置 schema (v2)

`~/.agenteye/config.json`:

```json
{
  "schema_version": 2,
  "refresh_interval_sec": 30,
  "alert": {
    "enable": true,
    "warn_pct": 30,
    "critical_amount_yuan": 5.0
  },
  "ui": {"x": null, "y": null, "width": 360, "height": 360, "order": [], "pinned": true},
  "providers": [
    {"id": "abc123", "kind": "minimax", "name": "MiniMax M3",
     "key": "sk-cp-...", "base_url": "https://api.minimaxi.com",
     "extra": {}},
    {"id": "def456", "kind": "generic_openai", "name": "某中转",
     "key": "sk-...", "base_url": "https://api.example.com/v1",
     "extra": {}}
  ]
}
```

环境变量覆盖: `MINIMAX_API_KEY` / `OPENCODE_GO_API_KEY` / `DEEPSEEK_API_KEY`,
或在条目里写 `"api_key_env": "自定义环境变量名"`。

告警级别判定:

| 单位 | 触发条件 |
|---|---|
| `¥` | 剩余金额 ≤ `alert.critical_amount_yuan`(默认 5)→ 红 |
| `%` | 剩余百分比 ≤ `alert.warn_pct`(默认 30)→ 黄 |
| `$` / 其他 | 不做阈值判断,一直 `ok` |

per-provider 60 min 硬编码冷却:同一 provider 同等级不重复弹,跨等级 / 跨 provider 不合并。

## 支持的 provider

| kind | 接口 | 显示 |
|---|---|---|
| `relay` | 自动探测 6 种中转站端点 | 余额 / 已用 |
| `minimax` | 按 key 前缀选 `coding_plan` / `token_plan` | 5h% + 周% + 倒计时 |
| `opencode_go` | `opencode.ai/zen/go/v1/usage` | 5h / 周 / 月估算金额 |
| `deepseek` | `api.deepseek.com/user/balance` | 总余额 + 赠金/充值拆分 |
| `zhipu` | `open.bigmodel.cn/api/monitor/usage/quota/limit` | 5h / 周% + 倒计时 + 套餐档位 |
| `generic_openai` | 探测 `/v1/models` + 4 种 quota endpoint | 模型列表 + 余额 |

## 窗口操作

- **拖动**:按住空白处(标题/底部/行间空隙)拖,自动边缘磁吸(< 20 px 贴边);行内按下拖动是重排,不会移动窗口
- **拖拽重排行**:按住行任何位置超过 8 px 进入拖拽模式,出现红色指示线,松开释放
- **调整大小**:右下角 grip(`size_nw_se` 光标)拖动改变面板大小,内部自适应
- **光标**:拖动时 `fleur`,行 hover `hand2`,× 按钮 hover 变红
- **点击数值**:无移动 → 复制到剪贴板;有移动 → 拖拽重排
- **右键行**:刷新此行 / 查看模型 / 试调 / 编辑 / 暂停 / 复制 key / 复制 URL / 删除(删除需输入名字确认)
- **点击 ≡ 按钮**:打开设置界面(刷新间隔 / ¥ 临界阈值 / % 告警阈值 / 主题)
- **点击 ⊙ / ○ 按钮**:切换窗口固定(topmost)
- **点击 – 按钮**:最小化到任务栏,点击任务栏图标还原
- **右键菜单**:立即刷新 / 通知测试 / 添加 Key / 暂停 / 打开配置 / 退出
- **键盘**: F5 刷新, Ctrl+Q 退出, Esc 关闭弹窗, 窗口聚焦时自动刷新

## 行颜色

- 绿 = 正常(`ok`)
- 黄 = 低于预警(`warn`)
- 红 = 低于告急或查询失败(`critical` / `error`)
- 灰 = 未配置(`unconfigured`)

**渐变插值**:`_usage_ratio` 返回 0..1,绿(`#53d77a`) → 黄(`#f0c24b`) → 红(`#ff5d5d`)
三段线性插值;金额行主值和 detail 中所有 `$X` / `¥X` / `X%` 段统一上色。

**行类型**:
- 金额行(`unit ∈ {$ ¥ ￥ 额度 元}`):无底部进度条,💰 前缀,微调暖色底 `#1d1b25`
- 百分比行:保留 5 px 渐变 canvas 进度条,normal card 底

> 进度条绘制由 `<Configure>` 事件驱动,首帧布局完成 / 窗口 resize 时 Tk 自动用真实 `event.width` 重画,不存在"刚打开看不见"或"resize 后宽度错位"问题。

## 缓存与日志

| 文件 | 用途 |
|---|---|
| `~/.agenteye/config.json` | 主配置(原子写,`.tmp` + `os.replace`) |
| `~/.agenteye/config.json.v1.bak` | v1 → v2 迁移时自动备份 |
| `~/.agenteye/cache/models.json` | 模型列表缓存(TTL 6 h,按 base_url + key hash) |
| `~/.agenteye/cache/probe.jsonl` | 试调日志(append-only) |
| `~/.agenteye/cache/alert_state.json` | 告警时间戳(per-provider 冷却持久化) |

## 测试

```
python -m unittest discover tests
```

当前 **266 个测试用例** 覆盖:

- `detect` / `generic` / `cache`(含 provider 删除清理)/ `migration` / `panel` 渐变 / 金额行模式 / 拖拽重排
- 设置校验 / AddKey placeholder / 滚动条结构 / 删除确认 / 模型面板分组与重排回调 / 重建后重绘回归
- **告警 per-provider 冷却** (`test_fire_alerts.py`):基本弹发、禁用不弹、ok 忽略、同 provider 同 level 60min 冷却、warn→critical 算新告警、多 provider 各弹
- **首帧进度条** (`test_panel_bar.py`):不调 `update_idletasks` 时 Tk `<Configure>` 仍正确驱动 rect、resize 后 handler 用 `event.width` 重画

## 已知边界

- OpenCode Zen 按量余额:官方无 API,只做 Go 订阅
- MiniMax 按量付费余额:无稳定公开接口,只做套餐类查询
- SiliconFlow:官方已下线余额接口,无法接入
- 价格表:仅内置 gpt-4o / claude-3.5 / deepseek / glm-4 几个常见模型,其它需手填或在价表扩展

## 架构

```
main.py             入口,Poller 线程 + tk mainloop
config.py           v1 + v2 schema,load_v2 自动迁移,原子写
cache.py            models_cache (TTL, 含 order) + probe_log (JSONL)
                    + alert_state (per-provider 冷却时间戳)
notify.py           alert_many 合并 toast
providers/
  __init__.py       注册表,collect_entries / fetch_all / _level(¥ 临界 + % 警告)
  detect.py         key 前缀 + URL 提示识别 kind
  generic.py        OpenAI 兼容探测 + 4 种 quota parser
  relay.py / minimax.py / opencode_go.py / deepseek.py / zhipu.py   5 内置 provider
ui/
  panel.py          主面板:provider 行 + 滚动条 + 拖拽/拖动/resize
                    进度条由 <Configure> 事件驱动
  row_menu.py       行右键菜单(删除走输入名字确认)
  confirm_delete.py 危险操作确认:输入名字才能确认
  model_panel.py    模型列表 + 拖拽重排 + 搜索 + 分组 + 试调 + 价格计算
  add_key.py        Add Key 对话框:5 预设 + placeholder + 预览(独立窗口)
  settings_dialog.py   设置界面:刷新间隔 / ¥ 临界 / % 警告 / 主题(链接添加 Key)
  presets.py        内置 provider 预设占位(待设置对话框接线)
```

## 更新日志

### v2.2 (设置界面简化)

- `refactor(ui)`:SettingsDialog 砍到 3 项设置(刷新间隔 / ¥ 临界 / % 警告)+ 主题切换;"添加 API Key" 拆成链接跳转独立 AddKeyDialog
- `refactor(alert)`:删除 `warn_amount` / `warn_amount_yuan` / `critical_amount` / `critical_pct` / `cooldown_min` / `max_per_hour` 6 项 cfg key;_level 简化到 ¥ 临界 + % 警告
- `refactor(aggregate)`:删除 `monthly_budget_usd` / `currency_rate_cny_per_usd` 2 项 cfg key + 整模块 `providers/aggregate.py`(只被测试引用)
- `refactor(alert)`:全局节流 → per-provider 60min 冷却(硬编码)
- `fix(ui)`:SettingsDialog 去掉 grab_set() 改为非模态,允许设置打开时主面板仍可拖动
- `fix(ui)`:去掉交通灯 hover glyph(× − ⋯),只保留 cursor=hand2 表示可点击
- `fix(ui)`:交通灯右移到右集群,黄绿红顺序;⚙ 简化为绿点设键;浅色交通灯残留深色框修复

### v2.1 (最近 4 笔 commit)

- `fix(panel)`:进度条 bar 绑 `<Configure>`,Tk 布局驱动,修首帧不可见 + resize 后不跟随
- `chore(ui)`:引入 `ui/presets.py` 占位模块,为设置对话框重构做准备
- `fix(alert)`:全局告警时间戳持久化,重启后 1 h 闸门不归零
- `feat(alert)`:新增 `alert.max_per_hour` 全局告警间隔,跨 provider 一小时最多一次 toast

### v2.0

- 多 provider 统一面板 + 5 个一键预设
- 金额/额度双视图 + 渐变色
- 主面板 + 模型面板拖拽重排 + resize
- v1 → v2 schema 自动迁移