# AgentEye

常驻桌面的模型额度观察小工具。统一轮询四类额度源,置顶小窗显示金额/额度,低额度弹 Windows 通知。

## 支持的额度源

| 类型 | 接口 | 显示 | 预警方式 |
|---|---|---|---|
| 中转站(new-api / 元序等,探测式自动适配) | 依次探测 `/api/user/self` → `/api/v1/usage` → `/api/v1/keys` → `/api/v1/subscriptions/summary` → `/api/v1/auth/me`;自研网关可配登录凭据走 `/api/v1/auth/login` | 剩余/已用金额(new-api 系 quota÷500000=美元) | 按金额(默认 $10 预警 / $3 告急) |
| MiniMax Coding/Token Plan | 按 key 前缀自动选 `sk-cp-`→coding_plan 或 token_plan 端点 | 各模型 5小时窗口% + 周% + 重置倒计时 | 按百分比 |
| OpenCode Go 订阅 | `GET opencode.ai/zen/go/v1/usage` | 5h/周/月三窗口金额(×$12/$30/$60 限额估算,标 ≈) | 按百分比(取最差窗口) |
| DeepSeek 官方充值 | `GET api.deepseek.com/user/balance` | 总余额 + 赠金/充值拆分 | 按金额(默认 ¥10 / ¥5) |
| 智谱 GLM Coding Plan | `GET open.bigmodel.cn/api/monitor/usage/quota/limit`(key 不加 Bearer) | 5h/周窗口剩余% + 重置倒计时 + 套餐档位 | 按百分比 |

所有查询均为只读接口,不消耗被查询的额度。

## 配置

首次运行自动生成 `~\.agenteye\config.json`(也可从 `config.example.json` 复制修改),把各家 key 粘进对应字段后重启程序即可:

```json
{
  "refresh_interval_sec": 300,
  "alert": { "enable": true, "warn_pct": 30, "critical_pct": 10, "cooldown_min": 60 },
  "relay_sites": [
    { "name": "元序", "base_url": "https://token.yuanxuai.xyz", "token": "sk-..." }
  ],
  "minimax": [{ "name": "MiniMax", "api_key": "sk-cp-...或订阅Key" }],
  "opencode_go": [{ "name": "OpenCode Go", "api_key": "ey..." }],
  "deepseek": [{ "name": "DeepSeek", "api_key": "sk-...", "warn_amount": 10, "critical_amount": 5 }],
  "zhipu": [{ "name": "智谱 GLM", "api_key": "..." }]
}
```

字段说明:

- `refresh_interval_sec`:轮询间隔,限制在 30–3600 秒,默认 300
- `alert`:全局预警阈值。百分比型(warn_pct/critical_pct)用于 MiniMax/OpenCode;金额型(warn_amount/critical_amount)用于中转站/DeepSeek,可在单个条目里覆盖
- `cooldown_min`:同一来源同一级别通知的冷却时间,避免刷屏
- `relay_sites[].token`:中转站 API key(通常就是你在 opencode 里配的那把)
- `relay_sites[].email` / `relay_sites[].password`:站点登录凭据。部分自研网关(如元序)的 sk- key 只有对话权限,查余额接口需要账号登录换 access_token;填上后自动登录并缓存 token,401 时自动重登
- `relay_sites[].new_api_user_id`:个别 new-api 站需要此头,填站点用户中心显示的数字 ID
- `relay_sites[].quota_per_usd`:new-api 系额度换算比,默认 500000
- `relay_sites[].headers`:需要额外请求头时兜底用
- `deepseek[].warn_amount/critical_amount`:人民币金额阈值
- 环境变量覆盖:`MINIMAX_API_KEY`、`OPENCODE_GO_API_KEY`、`DEEPSEEK_API_KEY`,或条目里写 `"api_key_env": "自定义环境变量名"`(relay 条目则覆盖 `token`)
- `ui.x/y`:窗口位置,拖动后自动保存

## 启动

```
run.bat          双击(后台 pythonw,无控制台)
python main.py   前台运行便于看报错
```

依赖:`requests`(本机已装)。

## 窗口操作

- 拖动:按住标题区/空白处拖
- 右键菜单:立即刷新 / 通知测试 / 暂停轮询 / 打开配置文件 / 退出
- 行颜色:绿=正常,黄=低于预警,红=低于告急或查询失败,灰=未配置
- `×` 退出

## 已知边界

- OpenCode Zen 按量余额:官方无 API,无法接入(本工具只做 Go 订阅)
- MiniMax 按量付费余额:无稳定公开接口,只做套餐类查询
- SiliconFlow(硅基流动):官方已下线 `/v1/user/info` 余额接口(410),暂无替代,只能网页控制台查看
- 元序等自研网关:sk- key 只有对话权限时需在配置里填站点 `email`/`password`,查询用登录态 access_token
