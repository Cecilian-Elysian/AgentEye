# 更新日志

记录 AgentEye 的每一次功能修改。格式:按批次分节,每节内按条目列出改动点与涉及文件。

## 背景(本次日志起点前的最近一次改造)

行内进度条重做为 12px 全圆角胶囊,数值/条长/条色三者统一为"已消耗"口径:

- `ui/theme.py`:Layout 新增 `ROW_BAR_HEIGHT = 12`
- `ui/panel.py`:新增 `_rounded_points` / `_draw_capsule`;`_row_skeleton` 的 5px
  直条改为双 `create_polygon(smooth=True)` 胶囊;`_on_bar_configure` 修掉
  `frac=None` 时画满格的 bug;`refresh_palette` 改为按图元重刷轨道色,浅色主题
  不再残留深色轨道;主值 `%` 行改为「已用 X%」;新增 `_row_color` 统一数值
  颜色判定(有占比走渐变,无占比但 level 为 warn/critical 沿用等级色)
- `ui/essential_bar.py`:`_row_ratio` 改为委托 `panel._usage_ratio`,两视图口径一致
- `providers/zhipu.py`:detail 段按剩余升序,最紧张窗口排第一
- `providers/minimax.py`:headline 模型提到 detail 首位
- `providers/opencode_go.py`:回填 `used = 60 - monthly_amt`,金额行占比与显示同源
- `ui/panel.py`:`_update` 重建签名加 `unit`,金额行首帧失败后拿到 `"$"` 能正确
  撤掉胶囊,不再残留空条
- 测试:新增 `tests/test_row_capsule.py`;更新 test_panel_bar / test_panel_color /
  test_pause_and_actions / test_m2_two_mode / test_p0_fixes

## 批次 1(P0 修复 + 缓存锁)

- **退出码 3/4 不可达**(`main.py`):providers/ui 的顶层 import 下沉到
  `Poller.fetch_once` / `main()` 内部——原先缺 requests/tkinter 时
  ModuleNotFoundError 抢在 `_run()` 守卫前炸,退出码契约的 3/4 永远不可达;
  `_run` 与 `config.py` 的 `sys.stderr.write` 全部加 None 守卫(pythonw 下
  stderr 是 None,会把"隔离损坏配置后空配置启动"这类路径整个炸掉)
- **生产窗口不可调尺寸**(`ui/app.py`):MacWindow 实现右下角 resize grip
  (mac 模式 Panel 跳过自建 grip 但 MacWindow 从未实现,overrideredirect
  窗口又无原生边框);essential 模式尺寸固定,热区隐藏;释放走 `save_size`
  持久化;grip 配色随主题刷新
- **schema_version 类型宽容致数据丢失**(`config.py`):分派改三分支——
  整型 2 走 v2、缺版本/整型 1 走 v1 迁移、其余(`"2"` 字符串/`2.0`/`true`)
  按损坏隔离;原先 `"2"` 会落进迁移,拿空 providers 模板覆盖 config.json
  且 `.v1.bak` 已存在时连备份都不做;隔离名加 uuid 后缀,防同秒覆盖证据
- **点击数值复制不可达**(`ui/panel.py`):`value_lbl` 补进 drag_widgets,
  `is_value_click` 生效;`_copy_value` 改复制 `_fmt_main` 所见即所得主值
  (原先 % 行复制裸 remaining=None 静默无反应)
- **黄点最小化永久破坏边框**(`ui/app.py`):`_stub_minimize` 置位 +
  root `<Map>` 恢复 overrideredirect/topmost(原先恢复路径只在 Panel 的
  非 mac 分支存在,mac 模式最小化一次就永久带原生标题栏)
- **缓存锁缺失**(`cache.py`):`remove_provider_entries` 补 `with _lock:`,
  与文件头"读-改-写必须串行"的自声明不变式对齐
- 测试:新增 `tests/test_exit_codes.py`(sys.modules 塞 None 验证 3/4 +
  模块顶层 import 防回归扫描)、`tests/test_mac_grip.py`(grip 随模式显隐/
  钳制/落盘、最小化状态机);`test_migration.py` 增版本分派 5 例;
  `test_row_capsule.py` 增复制 2 例 + 滚动保持 1 例;
  `test_poller_resilience.py` 补丁目标改指 providers

## 批次 2(P1 功能缺陷)

- **opencode_go percent 语义统一为"剩余"**(`providers/opencode_go.py`):
  detail 改「5h 剩≈$X/$Y」与主值/胶囊同向;`_norm_pct` 删掉 `0<v<1 ×100`
  猜测(0.9% 剩余会被放大成 90%,恰在尾部区间反转告警方向);模块头写死
  语义决定,并注明 WINDOWS 档位额度是硬编码估算
- **generic except 收窄**(`providers/generic.py`):模型缓存写失败只捕
  `OSError`——原先 `except Exception` 把 NameError 类真 bug 静默吞掉;
  写 stderr 前判空(pythonw 兜底)
- **多显示器磁吸/恢复**(新增 `ui/screen.py`,接入 `ui/app.py` 与
  `ui/panel.py`):`work_area`(ctypes MonitorFromPoint+GetMonitorInfoW,
  DEFAULTTONULL 出界回退)+ 纯函数 `snap_clamp` / `restore_position`;
  两处拖拽磁吸共用,副屏不再被拽回主屏;启动恢复坐标钳进最近显示器
  (拔显示器窗口不失联);修掉 `ui.get("x") or 100` 把合法 0 坐标当缺失
- **relay 多 key 聚合**(`providers/relay.py`):新增 `_deep_sum`/`_deep_count`,
  `_parse_generic` 对 `{"data":[...]}` 包装聚合全部 key(原先首中即返只算
  第一个 key,额度低估数倍且无"N 个 key"提示);`isValid=false` 直接报
  「key 无效」,非 dict 响应体守卫;静态 token 401 汇总报
  「key 无效 (HTTP 401)」;`_parse` 主动给出的错误结论直接透传,
  不加 detail 前缀
- **detect JWT 误判**(`providers/detect.py`):裸前缀 `"ey"` 收紧为
  三段式 JWT 才判 opencode_go,置信度降 low 并提示可能是 MiniMax
  token_plan(原先 MiniMax JWT 必然打到 opencode 端点上失败)
- **403 提前判死**(`generic.py`/`opencode_go.py`):401 仍立即判
  key 无效;403 在非末位候选端点继续回退(WAF 对猜测路径返回 403
  很常见),末位端点才判 key 无效
- **试调失败落审计日志**(`main.py`):RequestException/401,403/非 200
  三分支补 `log_probe(success=False)`,probe.jsonl 不再只有成功记录
- **主题切换保滚动**(`ui/panel.py`):`refresh_palette` 的 `_rebuild`
  前存 `yview()[0]`、后恢复,列表不再跳回顶部
- **`"ui": null` 防御**(`config.py`):merge 后 `ui`/`alert` 非 dict 用
  模板补回(原先 `setdefault("ui", {})` 拿到 None,所有几何/主题
  持久化 TypeError 且无提示)
- **AddKeyForm 探测竞态**(`ui/add_key.py`):探测线程存活时记挂起标志;
  完成回调比对输入快照,变了自动重排,旧结果不再放行保存
- 测试:`test_p0_fixes.py` 增 relay 聚合 4 例、generic 403 回退 3 例、
  缓存写失败 2 例、`_norm_pct` 2 例、opencode 403 回退 2 例;
  `test_detect.py` 改 JWT 用例并增 1 例;新增 `tests/test_screen.py`
  (snap_clamp/restore_position/work_area 回退);`test_add_key.py` 增
  探测竞态 3 例;`test_row_capsule.py` 增主题滚动保持 1 例

## 批次 3(打磨 + 一处新发现的线程 bug)

- **试调结果在工作线程被静默丢弃**(新发现,`ui/model_panel.py` 与
  `ui/add_key.py`):两处在探测线程里调 `self.after(0, ...)`,而
  tkinter 的 after/createcommand 不允许非主线程调用(py3.12 起直接
  RuntimeError),原实现的兜底只捕 TclError——生产环境试调结果永远
  不更新、save_btn 永久 disabled。改成结果进 `queue.Queue`,主线程
  由 80ms 泵回调 `_drain_probe_results` 取走
- **ModelPanel 试调在途去重**(`ui/model_panel.py`):同一模型重复点
  试调不再并发两个请求(双倍计费、结果互相覆盖);按钮在途禁用,
  `_render` 重建行后恢复禁用态
- **PowerShell 通知进程挂死泄漏**(`notify.py`):`_watch` 超时分支
  kill 子进程——原先计数器照减但进程留着,隐藏窗口每个几十 MB,
  常驻数周后耗尽内存
- **对话框原生关闭绕过 on_close**(`ui/mac_toplevel.py`):注册
  `WM_DELETE_WINDOW` → `_on_close`;原先 Alt+F4/任务栏关闭直接
  destroy,跳过保存清理逻辑
- **行右键菜单热区**(`ui/panel.py`):右键绑定从 (卡片, 名称) 扩到
  detail 条、进度条、数值;金额行的 bar 为 None,循环跳过
- **detail 宽度随窗口缩放**(`ui/panel.py`):`_on_root_configure`
  原先 configure(wraplength=...) —— Text 没有该选项,每次 TclError
  被吞,整个回调是死代码;现按窗口宽估字符数放大 Text width
- **`_paint_row` 去重 key 补字段**(`ui/panel.py`):used_today/used/
  paused/unconfigured 进 key,暂停态翻转等不再因签名相同被跳刷;
  占位行("未配置任何 provider")不进拖拽落盘的 order
- **刷新在途短路**(`main.py`):`refresh_now` 在 fetching 中直接
  return;删除从不存在的 `flash_refresh` 死分支
- **add_key_entry 写盘失败回滚**(`main.py` + `ui/settings_dialog.py`):
  `_save()` 返回 False 时移除刚 append 的半截条目并抛 ConfigError;
  设置对话框宿主回调抛错时 `messagebox` 报错并留在表单——原先
  异常被吞还照样切回列表,用户以为存上了
- **providers 解析加固**:zhipu 接受字符串 `"200"` code(个别网关);
  minimax `base_resp` 非 dict(网关错误页)先收型再 `.get`;
  deepseek base_url 带 `/v1` 自动剥掉(余额端点在根路径,带 /v1 404);
  generic 订阅解析接受无 `data` 包装的裸体响应
- **缓存细节**(`cache.py`):`save_model_order` 不再刷新 `fetched_at`
  (重排不该给 TTL 续命);`log_probe`/`log_provider_deleted` 的
  append 收进 `_lock`(与裁剪的读改写互斥);`get_models` 过滤
  历史遗留的非字符串元素
- **渐变端点进 PALETTE**(`ui/panel.py`):`_usage_color` 的
  #53d77a/#f0c24b/#ff5d5d 写死在函数体,浅色主题下偏深且与
  等级色不同源;改为实时插值 PALETTE.OK/WARN/CRITICAL
- **essential 条带主值口径**(`ui/essential_bar.py`):% 行主值与
  Panel._fmt_main 同口径写「已用 X%」——原先裸显剩余 62%,挨着
  按"已消耗 38%"取色的条,方向读反
- **删除 vibrancy.get_hwnd**:零调用方死代码,删除以免引诱第二份
  hwnd 逻辑(test_m1_theme 改为断言不存在)
- **接线守卫扩展**(`tests/test_p0_fixes.py`):app.py 的 MacWindow
  用无兜底 `.get()` 读 actions,同样抓出来与 build_actions 对撞
  (allowlist:`minimize`)
- 测试:新增 `tests/test_batch3_polish.py`(12 例:/v1 剥除、裸体
  订阅、base_resp 收型、字符串 code、回滚、刷新短路、条带口径、
  TTL、试调去重);`test_m2_two_mode.py` 条带主值断言更新为新契约;
  `test_panel_color.py` 端点断言改为 PALETTE 派生
- 审计项核实后不修:README 的 v1 备份名 `.v1.bak` 本来就写对了;
  minimax `_fmt_reset` 的量级判别逻辑自洽(注释已说明一周上限);
  probe_model 的 401/403 文案批次 2 已覆盖

## 批次 4(GUI 优化:视觉 + 交互 + 流畅度)

- **essential 条带胶囊化**(`ui/essential_bar.py`):轨道/填充从直角
  `create_rectangle` 换成与展开面板行内条同款的 12 点圆角 polygon
  (复用 `panel._rounded_points`),不足圆头直径不画填充;主题切换
  同步刷轨道色。两种视图的条形语言终于一致
- **进度条缓动动画**(行内条 + essential 条带):数据跳变时条从当前
  显示值以 35%/帧滑向目标,不再瞬移;动画期间 tick 自动升到 33ms
  快档,收敛后回 1Hz(无动画空转)。渐变色不跟随缓动、每帧直接用
  目标色——渐变色差肉眼不可辨,位置跳变才扎眼。行重建时清空动画
  集合,死名不会把 tick 永久钉在快档
- **交通灯 hover**(`ui/app.py`):圆点悬停提亮 30%(theme.blend),
  移开恢复;`refresh_palette` 同步更新 `_color` 基准,主题切换后
  Leave 恢复的不再是以往主题的色
- **菜单配色**(`ui/row_menu.py` + `ui/panel.py`):右键行菜单与主
  菜单从系统默认灰改为 PALETTE 配色(卡片底/悬停高亮),瞬态菜单
  下次弹出自然跟随主题
- **按下态**(`ui/panel.py`):行卡按下时压暗一档(CARD_PRESSED),
  松开恢复——此前点行没有任何"按到了"的反馈
- **复制反馈**(`ui/panel.py`):复制主值/key/URL 成功后对应标签染
  ok 绿 450ms;只改前景色不动文本,与 `_paint_row` 的签名去重不打架
- **tooltip**(新增 `ui/tooltip.py`,接入 `ui/panel.py` 行卡):行卡
  悬停 600ms 显示估算值说明 + 完整 detail——detail Text 只有 1 行
  高,长文案平时是被裁掉的。getters 按次取值,轮询更新后悬浮内容
  跟着新;Leave/按下/销毁兜底收窗
- 测试:新增 `tests/test_gui_polish.py` 15 例(胶囊几何/宽度语义/
  行内与条带缓动收敛/颜色即时更新/hover 往返/主题后 _color 同步/
  两处菜单配色/tooltip 弹收与空文本/复制闪烁恢复)
- 备注:合成 Enter/Leave 事件只投递给已映射窗口,相关测试不能
  withdraw root(geometry + update 即可),测试文件内已注明
