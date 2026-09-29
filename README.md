# AgentEye

Windows 桌面常驻的多 Key AI 额度观察工具，粘贴 key 即用


## 使用

方法一（普通用户）：

双击 `run.bat` 启动（后台 `pythonw`，无控制台窗口）

方法二（项目测试）：

进入项目根目录

```
安装依赖
pip install -r requirements.txt

前台运行，报错直接打在控制台
python main.py
```

方法三（项目测试）：

只想验证界面不打算接任何 provider：

```
.venv\Scripts\python.exe main.py
```

> 启动后会在屏幕右侧出现一个无边框小面板，默认 360×360，可拖到屏幕任意位置并在拖动时自动吸附到 20 px 内的屏幕边缘，右下角 grip 可在 280×180 ~ 800×900 之间拉伸；标题栏三个交通灯从左到右分别是黄（最小化到任务栏）、绿（打开设置）、红（退出），面板右上角的小圆点实时反映全局最差等级（绿=全部正常、橙=有偏低、红=有告急或查询失败、灰=轮询已暂停）；点标题栏空白处或行与行之间的空隙可拖动窗口，按住某一 provider 行拖动超过 8 px 则进入重排模式并显示一条蓝色指示线，松手后顺序写入配置并在下次启动时保持；单击某一行的数值是复制剩余值到剪贴板；右键行会弹出「立即刷新此行 / 查看模型列表 / 试调模型… / 编辑此 provider / 暂停或恢复此 provider / 复制 key / 复制 base URL / 删除此 provider」，删除必须输入 provider 名字二次确认，并会一并清掉它的模型列表缓存、在试调日志里追加一条 `provider_deleted` 标记；模型列表面板会拉取该 provider 的 `/v1/models` 并按能力分组，支持搜索（命中数实时更新）和拖拽重排（顺序持久化，点「试调」发一个 `max_tokens=1` 的请求测延迟并把结果记进 `probe.jsonl`，模型详情里还能按内置价表估算 N 次调用的花费）；设置窗口在同一位置切换「列表 ↔ 表单」两个视图，列表里可以逐条编辑或删除 provider，点「添加 API Key」进入表单，顶部五个预设按钮（MiniMax / DeepSeek / 智谱 GLM / OpenCode / 中转站）一点就自动填好默认 base URL 和名称，填入 key 后会自动探测并预览识别出的 provider 类型；面板有折叠与展开两态，折叠态收成 240 px 宽的单行条带（条带本身 56 px 高，另加标题栏，宽度锁定不可拉伸），只显示最差的那个 provider 的主值与次值，点条带任一处或右键菜单「切换为单行模式」可来回切换，两态选择会记住；
主题有深色 / 浅色 / 跟随系统三档，切换即时生效；告警只在低于阈值时弹，同一 provider 同一等级 60 分钟内不重复弹，等级从 warn 升到 critical 视为新告警会再弹一次，剩余人民币 ≤ 临界值弹「额度告急」，剩余百分比 ≤ 阈值弹「额度偏低」，一次轮询内多个 provider 同时告警会合并成一条 toast；快捷键为 F5 立即刷新、Ctrl+Q 退出、Esc 关闭当前弹窗，窗口获得焦点时自动触发一次刷新；首次启动会弹一条欢迎提示，右键面板空白处有「立即刷新 / 通知测试 / 添加 Key… / 暂停轮询 / 切换为单行模式 / 打开配置文件 / 设置… / 退出」。

配置项（均可通过设置窗口修改，配置文件是 `~/.agenteye/config.json`）：

| 配置 | 默认值 | 作用 |
|---|---|---|
| `refresh_interval_sec` | `30` | 轮询各 provider 的周期，15–3600 秒 |
| `alert.enable` | `true` | 总开关，关掉后不再弹任何告警 |
| `alert.critical_amount_yuan` | `5.0` | 人民币剩余 ≤ 此值判为 critical（红） |
| `alert.warn_pct` | `30` | 剩余百分比 ≤ 此值判为 warn（橙） |
| `ui.theme` | `auto` | `dark` / `light` / `auto`（跟随系统） |
| `ui.pinned` | `true` | 是否置顶 |
| `ui.mode` | `standard` | `standard` 展开面板 / `essential` 单行条带 |
| `ui.x` / `ui.y` | `null` | 窗口位置，`null` 时首次运行放在屏幕右侧 |
| `ui.width` / `ui.height` | `360` | 窗口尺寸 |
| `ui.order` | `[]` | provider 行顺序 |

`config.json` 缺失时会自动创建一份空模板并落盘；内容非法（JSON 错误或字段类型不对）时按空配置处理，v1 旧 schema（`relay_sites` / `minimax` / `opencode_go` / `deepseek` / `zhipu` 五个分立数组）会被自动迁移成统一的 `providers[]`，原文件备份为 `config.json.v1.bak`。API Key 优先读环境变量 `MINIMAX_API_KEY` / `OPENCODE_GO_API_KEY` / `DEEPSEEK_API_KEY` / `ZHIPU_API_KEY`，也可在条目里写 `"api_key_env": "自定义变量名"` 指定其他变量；写盘时 key 经 Windows DPAPI 加密成 `key_enc`，内存里始终保持明文。


## 开发检查

```text
pip install -r requirements-dev.txt
python -m pytest tests -q
```


## 文件结构

开发板
```
AgentEye/
├─ .gitignore                  # 忽略 __pycache__、.venv、截图与调试产物
├─ AGENTS.md                   # 工程契约：定位、编码风格、密钥契约、测试、退出码
├─ README.md                   # 使用、配置、文件结构、注意事项
├─ requirements.txt            # 运行依赖：requests
├─ requirements-dev.txt        # 开发依赖：pytest
├─ config.example.json         # config.json 的 v2 schema 示例
├─ run.bat                     # 双击启动（pythonw，无控制台）
├─ main.py                     # 入口、Poller 线程、actions 装配、退出码
├─ config.py                   # v2 schema、load/save_v2、v1 迁移、原子写
├─ secure.py                   # Windows DPAPI 加解密（ctypes，无第三方依赖）
├─ cache.py                    # models.json(TTL) / probe.jsonl / alert_state.json
├─ notify.py                   # WinRT toast，失败回退 winsound
├─ providers/
│  ├─ __init__.py              # kind 注册表、fetch_all、_level 阈值、_resolve_key
│  ├─ detect.py                # key 前缀 + base URL 推断 kind
│  ├─ generic.py               # OpenAI 兼容探测 + 多种 quota 端点解析
│  ├─ relay.py                 # 中转站余额
│  ├─ minimax.py               # 套餐 5h / 周用量
│  ├─ opencode_go.py           # OpenCode Go 订阅用量
│  ├─ deepseek.py              # 余额 + 赠金/充值拆分
│  └─ zhipu.py                 # 智谱 5h / 周额度
├─ ui/
│  ├─ app.py                   # MacWindow 窗口壳、essential/standard 两态、交通灯
│  ├─ panel.py                 # 主面板：provider 行、滚动条、拖拽重排、拖动、resize
│  ├─ essential_bar.py         # 折叠态单行条带
│  ├─ model_panel.py           # 模型列表、分组、搜索、拖拽重排、试调、价格估算
│  ├─ row_menu.py              # 行级右键菜单（删除走输入名字确认）
│  ├─ settings_dialog.py       # 设置 + provider 列表管理（列表 ↔ 表单切换）
│  ├─ add_key.py               # Add Key 表单：5 预设 + 自动探测（内嵌组件）
│  ├─ confirm_delete.py        # 危险操作确认：输入名字才能确认
│  ├─ mac_toplevel.py          # macOS 风对话框基类：标题栏 + 交通灯 + 拖拽
│  ├─ theme.py                 # 深/浅色 palette、等级色、渐变插值、主题订阅
│  ├─ fonts.py                 # 跨平台字体挑选
│  ├─ scrollbar_style.py       # 自绘滚动条样式
│  └─ vibrancy.py              # Win11 圆角/DWM 背景/暗标题栏，macOS 与 Linux 为占位
└─ tests/
   ├─ conftest.py              # Tk root 创建重试补丁，消 Windows TclError 抖动
   ├─ test_secure.py           # DPAPI 往返与明文/密文契约
   ├─ test_pause_and_actions.py # 按 provider 暂停、action 接线完整性、死代码守卫
   ├─ test_style.py            # 运行时源码无 emoji 守卫
   ├─ test_smoke.py            # 三条启动链路集成测试
   ├─ test_m1..m7_*.py         # 窗口壳 / 两态 / 主题 / 对话框 / 设置管理
   └─ test_*.py                # detect、cache、迁移、面板、告警、拖拽等
```


## 注意事项

- Windows 10/11，64 位；macOS / Linux 风格代码（vibrancy 圆角、圆点）只是视觉取向，不承诺可用
- 依赖 `requests` 与 Python 标准库的 `tkinter`；`tkinter` 缺失时需换带 Tcl/Tk 的 Python 官方安装包
- 必须运行在有交互桌面的登录会话中，不支持 Windows 服务、纯后台 Session
- 通知依赖 WinRT toast，锁死系统自带的 Windows PowerShell 5.1 路径；失败时回退为 `winsound` 蜂鸣，不会弹窗
- API Key 用 DPAPI 加密，绑定当前 Windows 账户与本机；把 `config.json` 拷到别的机器或别的账户下无法解密，此时会回退成读明文 `key` 字段
- 中转站若管理接口需要登录，条目 `extra` 里要同时填 `email` 和 `password`
- SiliconFlow 官方已下线余额接口，无法接入；OpenCode Zen 与 MiniMax 的按量付费余额没有稳定的公开接口，只做套餐类查询
- 价格表只内置了少量常见模型，未收录的模型在价格估算里显示为 0，需要自行在 `ui/model_panel.py` 的 `PRICE_TABLE` 里补
- 轮询会按 `providers[]` 条目数开线程并发请求各家接口，条目多时留意各家的频率限制
- 测试会创建并销毁多个 Tk 根窗口，在无图形环境的机器上无法运行

最后修改日期: 2026.9.29
