# AGENTS.md

AgentEye 的工程契约。

## 项目定位

Windows 桌面常驻的多 Key AI 额度观察工具。UI 采用 macOS 视觉取向(交通灯、
essential 单行条带),但**只支持 Windows**,依赖 DPAPI、WinRT toast 与
`ctypes.windll` DPI 感知,不承诺跨平台。

## 编码风格

1. 不使用 emoji。箭头(`→ ←`)、`≈`、`✓` `✗` 等排版与文本符号不在此列。
   `tests/test_style.py` 会扫描运行时源码并拦截。
2. 公开 API 使用中文 docstring。
3. Tk 主题色一律走 `ui.theme.PALETTE` + `to_tk_color()`,不要硬编码 hex。
   模块级颜色字典在主题切换时必须同步刷新,否则浅色主题会残留深色框。
4. 进度条宽度由 `<Configure>` 事件驱动,读 `event.width`,不要用
   `winfo_width() or 300` 兜底(首帧布局未完成时拿到 1 px)。
5. UI 不直接 import `providers` 适配器模块,只经 `providers/__init__.py` 的注册表。
6. 配置读写只走 v2 schema(`providers[]`),不要重新引入 v1 的分立数组。
7. 保持依赖最小化:运行时仅依赖 `requests`;密钥加密用 `secure.py` 里的
   ctypes 调 DPAPI,通知用 `notify.py` 里的 WinRT + `winsound`。

## 密钥契约

| 形态 | 字段 |
|---|---|
| 内存 | `provider["key"]` 明文 |
| 磁盘 | `provider["key_enc"]` base64(DPAPI),**没有** `key` |

`config.save_v2` 在 `deepcopy` 上加密后写盘,绝不改写调用方的 `cfg`;
`config.load_v2` 负责把 `key_enc` 还原成明文。任何新增的读 key 路径都要走
`config.plain_key()` 或 `providers._resolve_key()`,直接 `entry["key"]` 会在
加密生效后拿到空串。

## 测试

1. 默认运行 `python -m pytest tests -q`。
2. 必须用 pytest,不要用 `unittest discover`:`tests/conftest.py` 给
   `tk.Tk.__init__` 打了有限次重试,消掉 Windows 上反复建销 Tk root 时的
   `TclError` 抖动,`unittest` 下不生效。
3. 测试不得读写用户真实配置:用 `config.CONFIG_PATH` 指向临时目录
   (`tests/test_secure.py`、`tests/test_smoke.py` 里的 mixin 已有现成写法)。
4. 新增 UI 入口时同步补 `tests/test_pause_and_actions.py` 里的 action 清单,
   避免 `.get(..., lambda: None)` 把未接线入口静默吞掉。

## 退出码

`main._run()` 抛出,`python main.py` 的返回值:

| 码 | 含义 |
|---|---|
| 0 | 正常退出(含用户点关闭) |
| 1 | 未预期异常 |
| 2 | 配置无效(保留位) |
| 3 | `requests` 依赖缺失 |
| 4 | 当前 Python 未包含 `tkinter` |
