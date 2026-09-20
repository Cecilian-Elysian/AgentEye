# AgentEye v2

常驻桌面的多 Key 额度观察工具。粘贴 key 即用,自动识别 provider 类型,
自动拉取可用模型列表,实时显示总额度与各 provider 明细。

## v2 新特性

- **粘贴 key 即用**:Add Key 对话框自动识别 provider(OpenAI 兼容 / 元序等中转 / MiniMax / OpenCode Go / DeepSeek / 智谱)
- **5 个一键预设**:Add Key 顶部 5 个按钮(MiniMax / DeepSeek / 智谱 / OpenCode / 中转站),点一下自动填默认 URL 和名称
- **金额/额度双视图**:金额行($ ¥ 额度)无进度条 + 💰 前缀 + 暖色底;百分比行带渐变进度条
- **消耗渐变色**:绿→黄→红三色插值,基于 used_today/total 计算消耗比,detail 中所有金额/百分比同步上色
- **窗口可拖拽 resize**:右下角 grip 调整面板大小(280×180 ~ 800×900),实时自适应 wraplength
- **主面板 + 模型面板 拖拽重排**:长按 >5px 触发,红线指示器,顺序持久化到 cfg 和 cache
- **窗口固定按钮**:Header 📌/📍 切换 topmost,状态持久化
- **设置界面**:Header ⚙ 打开,改刷新间隔、告警/临界阈值(双币种独立)、月度预算、汇率
- **模型列表自动拉取**:每个 provider 显示 `/v1/models` 列表,按能力分组(Claude/GPT/Gemini/...),支持搜索
- **1-token 试调**:点击"试调"发送 1 token 请求,显示延迟,记录到 `~/.agenteye/cache/probe.jsonl`
- **金额今日已用/总额**:中转站显示 `今日 $X.XX / $Y.YY`,百分比行继续显示 5h%/周%/倒计时
- **价格计算器**:模型详情面板估算 N 次调用的花费(常见模型公开价表)
- **交互优化**:行 hover 高亮、点击数值复制(无移动)、边缘磁吸、F5/Ctrl+Q/Esc 快捷键、首启欢迎 toast
- **通知合并**:同一 tick 内多条告警合并为一条 toast(避免刷屏)
- **v1 自动迁移**:旧的 5 分立数组配置自动升级为统一 `providers[]`,备份为 `config.json.v1.bak`

## 配置 schema (v2)

`~/.agenteye/config.json`:

```json
{
  "schema_version": 2,
  "refresh_interval_sec": 30,
  "alert": {
    "enable": true,
    "warn_pct": 30, "critical_pct": 10,
    "warn_amount": 10, "critical_amount": 3,
    "cooldown_min": 60
  },
  "aggregate": {
    "enabled": true,
    "monthly_budget_usd": 100.0,
    "currency_rate_cny_per_usd": 7.2
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

## 支持的 provider

| kind | 接口 | 显示 |
|---|---|---|
| `relay` | 自动探测 6 种中转站端点 | 余额/已用 |
| `minimax` | 按 key 前缀选 coding_plan/token_plan | 5h% + 周% + 倒计时 |
| `opencode_go` | `opencode.ai/zen/go/v1/usage` | 5h/周/月估算金额 |
| `deepseek` | `api.deepseek.com/user/balance` | 总余额 + 赠金/充值拆分 |
| `zhipu` | `open.bigmodel.cn/api/monitor/usage/quota/limit` | 5h/周% + 倒计时 + 套餐档位 |
| `generic_openai` | 探测 `/v1/models` + 4 种 quota endpoint | 模型列表 + 余额 |

## 启动

```
run.bat          双击(后台 pythonw,无控制台)
python main.py   前台运行便于看报错
```

依赖: `requests`、`tkinter`(标准库)。

## 窗口操作

- **拖动**:按住任意位置拖,自动边缘磁吸(< 20px 贴边)
- **拖拽重排行**:按住行任何位置超过 5px 进入拖拽模式,出现红色指示线,松开释放
- **调整大小**:右下角 grip(`size_nw_se` 光标)拖动改变面板大小,内部自适应
- **光标**:拖动时 `fleur`,行 hover `hand2`,× 按钮 hover 变红,+ 按钮 hover 变绿
- **点击数值**:无移动 → 复制到剪贴板;有移动 → 拖拽重排
- **右键行**:刷新此行 / 查看模型 / 试调 / 编辑 / 暂停 / 复制 key / 复制 URL / 删除
- **点击 + 按钮**:打开 Add Key 对话框
- **点击 📌 按钮**:切换窗口固定(topmost),📌 = 固定,📍 = 不固定
- **点击 ⚙ 按钮**:打开设置界面(刷新间隔 / 告警阈值 / 月度预算 / 汇率)
- **右键菜单**:立即刷新 / 通知测试 / 添加 Key / 暂停 / 打开配置 / 退出
- **键盘**: F5 刷新, Ctrl+Q 退出, Esc 关闭弹窗, 窗口聚焦时自动刷新

## 行颜色

- 绿 = 正常(ok)
- 黄 = 低于预警(warn)
- 红 = 低于告急或查询失败(critical / error)
- 灰 = 未配置(unconfigured)

**渐变插值**:`_usage_ratio` 返回 0..1,绿(#53d77a) → 黄(#f0c24b) → 红(#ff5d5d)
三段线性插值;金额行主值和 detail 中所有 `$X`/`¥X`/`X%` 段统一上色。

**行类型**:
- 金额行(unit ∈ {$, ¥, 额度, 元, ￥}): 无底部进度条,💰 前缀,微调暖色底 #1d1b25
- 百分比行: 保留 5px 渐变 canvas 进度条,normal card 底

## 缓存与日志

- 模型列表: `~/.agenteye/cache/models.json` (TTL 6h,按 base_url+key hash)
- 试调日志: `~/.agenteye/cache/probe.jsonl` (append-only)
- 配置文件: `~/.agenteye/config.json` (原子写,.tmp + os.replace)
- v1 备份: `~/.agenteye/config.json.v1.bak`(自动迁移时生成)

## 测试

```
python -m unittest discover tests
```

当前 111 测试用例覆盖 detect / generic / cache / migration / aggregate / panel 渐变 / 金额行模式 / 拖拽重排 / 设置校验 / AddKey placeholder。

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
notify.py           PS 路径锁定 + alert_many 合并
providers/
  __init__.py       注册表,collect_entries / fetch_all / _level
  aggregate.py      USD 归一化 + 聚合 level
  detect.py         key 前缀 + URL 提示识别 kind
  generic.py        OpenAI 兼容探测 + 4 种 quota parser
  relay.py / minimax.py / opencode_go.py / deepseek.py / zhipu.py   5 内置 provider
ui/
  panel.py          主面板:provider 行 + 拖拽/拖动/resize
  row_menu.py       行右键菜单
  model_panel.py    模型列表 + 拖拽重排 + 搜索 + 分组 + 试调 + 价格计算
  aggregate_detail.py   聚合明细弹窗
  add_key.py        Add Key 对话框:5 预设 + placeholder + 预览
  settings_dialog.py   设置界面:刷新/告警/预算/汇率
```
