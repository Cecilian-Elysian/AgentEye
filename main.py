import os
import sys
import threading
import time
import uuid

import config as config_mod
import notify
import cache as cache_mod
from providers import fetch_all
from ui import Panel
from ui.app import MacWindow
from ui.essential_bar import EssentialBar


class State:
    def __init__(self):
        self.results = []
        self.last_fetch = 0.0
        self.next_fetch = 0.0
        self.paused = False
        self.paused_providers = set()
        self.fetching = False
        self.poll_error = None
        self.save_error = None


class Poller(threading.Thread):
    def __init__(self, cfg, state, stop_event, wake_event):
        super().__init__(daemon=True)
        self.cfg = cfg
        self.state = state
        self.stop = stop_event
        self.wake = wake_event
        self.notified = {}
        try:
            self.notified = cache_mod.load_alert_state()
        except Exception:
            self.notified = {}

    def run(self):
        while not self.stop.is_set():
            if self.state.paused:
                # 暂停期间不 fetch,但 refresh_now() 会把 fetching 置 True
                # (用来转圈提示),这里必须复位,否则条带会一直显示"刷新中…"
                self.state.fetching = False
                if self.wake.wait(0.5):
                    self.wake.clear()
                continue
            self._safe_fetch_once()
            interval = config_mod.clamp_interval_v2(self.cfg)
            end = time.time() + interval
            self.state.next_fetch = end
            while time.time() < end and not self.stop.is_set():
                if self.wake.wait(0.5):
                    self.wake.clear()
                    break
                if self.state.paused:
                    break

    def _safe_fetch_once(self):
        """轮询兜底:异常绝不能让本线程退出。

        线程一旦死掉,面板会永远停在旧数据上,而界面上没有任何提示。
        这里吞掉异常记到 state.poll_error,下一轮继续。
        """
        try:
            self.fetch_once()
        except Exception as e:
            self.state.poll_error = f"{e.__class__.__name__}: {e}"
            self.state.last_fetch = time.time()
        else:
            self.state.poll_error = None

    def fetch_once(self):
        self.state.fetching = True
        try:
            # 传 stop:退出时 fetch_all 不再等在途请求(那些是 daemon 线程,
            # 解释器退出不 join 它们),关窗后进程立刻消失
            results = fetch_all(self.cfg,
                                skip_names=tuple(self.state.paused_providers),
                                stop=self.stop)
        finally:
            self.state.fetching = False
        self.state.results = results
        self.state.last_fetch = time.time()
        self._fire_alerts(results)

    def forget_alert_state(self, *names):
        """丢弃指定 provider 的告警冷却(删除/改名时调用)。

        不清理的话,"key 填错了,删掉重加"这种最常见的工作流会让新条目
        继承被删账号的 60 分钟冷却:真告急被静默,界面上看不出任何原因。
        """
        changed = False
        for n in names:
            if self.notified.pop(n, None) is not None:
                changed = True
        if changed:
            try:
                cache_mod.save_alert_state(self.notified)
            except Exception:
                pass

    def _fire_alerts(self, results):
        alert_cfg = self.cfg.get("alert") or {}
        if not alert_cfg.get("enable", True):
            return
        # 简化版:硬编码 60min per-provider cooldown;无全局节流。
        COOLDOWN_SEC = 60 * 60
        now = time.time()
        items = []
        for r in results:
            level = r.get("level")
            if level not in ("warn", "critical"):
                continue
            key = r["name"]
            last = self.notified.get(key)
            if last and last[0] == level and now - last[1] < COOLDOWN_SEC:
                continue
            self.notified[key] = (level, now)
            verb = "额度告急" if level == "critical" else "额度偏低"
            items.append((r["name"], verb))
        if items:
            try:
                cache_mod.save_alert_state(self.notified)
            except Exception:
                pass
            notify.alert_many(items)


def _infer_kind_from_dialog(entry):
    """Add Key 对话框提交后,根据 URL/key 推断 kind。"""
    from providers import detect as detect_mod
    r = detect_mod.detect(entry.get("key", ""), entry.get("base_url", ""))
    return r["kind"]


def build_actions(root, cfg, state, stop, wake, poller=None):
    actions = {}

    def refresh_now():
        state.fetching = True
        wake.set()
        flash = actions.get("flash_refresh")
        if flash:
            try:
                flash()
            except Exception:
                pass

    def toggle_pause():
        state.paused = not state.paused
        if not state.paused:
            wake.set()

    def test_notify():
        if not notify.send_toast("AgentEye", "通知测试 OK"):
            notify.beep()

    def open_config():
        # os.startfile 只存在于 Windows;其他平台抛 AttributeError,故捕 Exception
        try:
            os.startfile(str(config_mod.CONFIG_PATH))
        except Exception:
            pass

    _settings_win = {"dlg": None}

    def open_settings(view=None):
        """打开设置窗口。已打开则复用同一实例并切到目标视图,不再叠窗口。"""
        from ui.settings_dialog import SettingsDialog

        dlg = _settings_win.get("dlg")
        if dlg is not None:
            try:
                alive = bool(dlg.winfo_exists())
            except Exception:
                alive = False
            if alive:
                dlg.goto(view)
                dlg.raise_()
                return
            _settings_win["dlg"] = None

        def _on_save(new_cfg):
            # 绝不能 cfg.clear() 后再 update(new_cfg):SettingsDialog 持有的
            # 就是宿主这个 cfg 对象本身,它把同一个对象原样传回来,
            # clear() 会把整份配置清空、update() 变成自更新空操作,
            # 随后落盘成 {} —— 所有 provider 与密钥一次性丢失且无任何报错。
            # 传进来的可能是宿主已就地改过的同一对象,也可能是对话框的
            # 副本,两种都要能安全合并。
            if new_cfg is not cfg:
                cfg.clear()
                cfg.update(new_cfg)
            if _save():
                _apply_settings_live()

        _settings_win["dlg"] = SettingsDialog(
            root, cfg, on_save=_on_save,
            on_add_key=add_key_entry,
            on_update_provider=update_provider,
            on_delete_provider=delete_provider_by_id,
            initial_view=view)

    def _apply_settings_live():
        """设置保存后即时生效:立即唤醒 poller,新配置下次 fetch 生效。"""
        wake.set()

    def _save():
        """统一的配置落盘出口。

        save_v2 现在会抛 ConfigError(明文 key 拒写 / 文件被占用 / 版本过高),
        绝不能让调用方以为"界面已变所以一定存下来了"。失败时弹一次 toast,
        并把最近一次错误放进 state 供 footer 展示。
        """
        try:
            config_mod.save_v2(cfg)
            state.save_error = None
            return True
        except config_mod.ConfigError as e:
            state.save_error = str(e)
            try:
                notify.alert("AgentEye", f"配置未保存:{e}")
            except Exception:
                pass
            return False

    def save_position(x, y):
        ui = cfg.setdefault("ui", {})
        ui["x"], ui["y"] = int(x), int(y)
        _save()

    def save_size(w, h):
        ui = cfg.setdefault("ui", {})
        ui["width"], ui["height"] = int(w), int(h)
        _save()

    def save_order(order):
        ui = cfg.setdefault("ui", {})
        ui["order"] = list(order)
        _save()

    def save_pin(pinned):
        ui = cfg.setdefault("ui", {})
        ui["pinned"] = bool(pinned)
        _save()

    def save_ui(new_cfg=None):
        # MacWindow._persist_mode 会带一个 cfg 快照进来;真正的 cfg 已被
        # 它就地改过(同一个对象),所以这里只落盘,不合并。
        _save()

    def save_theme(theme):
        ui = cfg.setdefault("ui", {})
        if theme in ("dark", "light", "auto"):
            ui["theme"] = theme
            _save()

    def get_order():
        return list((cfg.get("ui") or {}).get("order") or [])

    def save_model_order(provider_name, base_url, key, order):
        if not base_url or not key:
            return
        try:
            import cache as cache_mod
            cache_mod.save_model_order(base_url, key, order)
        except Exception:
            pass

    def quit_app():
        stop.set()
        wake.set()
        try:
            root.destroy()
        except Exception:
            pass

    def add_key():
        """添加 Key 入口(右键菜单)→ 设置对话框内嵌表单模式,不开独立窗口。"""
        open_settings("add_key")

    def add_key_entry(entry):
        kind = _infer_kind_from_dialog(entry)
        new_provider = {
            "id": uuid.uuid4().hex[:12],
            "kind": kind,
            "name": entry.get("name", "未命名"),
            "key": entry.get("key", ""),
            "base_url": entry.get("base_url", ""),
            "extra": {},
        }
        cfg.setdefault("providers", []).append(new_provider)
        _save()
        try:
            import notify as notify_mod
            notify_mod.alert("AgentEye", f"已添加:{new_provider['name']}")
        except Exception:
            pass
        wake.set()

    def update_provider(pid, entry):
        """按 id 更新 provider 的 name/key/base_url(kind 不变)。"""
        for p in cfg.get("providers") or []:
            if p.get("id") == pid:
                old_name = p.get("name")
                p["name"] = (entry.get("name") or "").strip() \
                    or p.get("name") or "未命名"
                p["key"] = entry.get("key") or ""
                p["base_url"] = entry.get("base_url") or ""
                if _save():
                    # 改名后旧名字的冷却条目是孤儿,会一直留在内存和
                    # alert_state.json 里(每次改名 +1 键,单调增长)
                    if poller is not None and p["name"] != old_name:
                        poller.forget_alert_state(old_name)
                    wake.set()
                return

    def delete_provider_by_id(pid):
        providers = cfg.get("providers") or []
        target = next((p for p in providers if p.get("id") == pid), None)
        if not target:
            return
        base_url = target.get("base_url") or ""
        key = config_mod.plain_key(target)
        name = target.get("name") or pid
        cfg["providers"] = [p for p in providers if p.get("id") != pid]
        if not _save():
            # 配置没存上,下次启动这个 provider 还在。此时若清掉模型缓存
            # 并写 provider_deleted 日志,用户会看到"已删除"提示,但数据
            # 还在、缓存却没了,还得不到任何解释。回滚内存改动并停手。
            cfg["providers"] = providers
            notify.alert("AgentEye",
                         f"删除 {name} 失败:配置未保存,{name} 仍保留")
            return
        try:
            import cache as cache_mod
            if base_url and key:
                cache_mod.remove_provider_entries(base_url, key)
            cache_mod.log_provider_deleted(name, base_url=base_url)
        except Exception:
            pass
        if poller is not None:
            poller.forget_alert_state(name)
        try:
            import notify as notify_mod
            notify_mod.alert("AgentEye", f"已删除:{name}")
        except Exception:
            pass
        wake.set()

    def delete_provider(name):
        """行菜单入口:按名字找到 provider,复用按 id 删除。"""
        target = next((p for p in cfg.get("providers") or []
                       if p.get("name") == name), None)
        if not target:
            return
        delete_provider_by_id(target.get("id"))

    def edit_provider(name):
        """行菜单入口:打开设置对话框并直达该 provider 的编辑表单。"""
        target = next((p for p in cfg.get("providers") or []
                       if p.get("name") == name), None)
        if not target:
            return
        open_settings(("edit", target.get("id")))

    def pause_provider(name):
        """行菜单入口:单独暂停/恢复某个 provider 的轮询。"""
        if not name:
            return
        if name in state.paused_providers:
            state.paused_providers.discard(name)
            verb = "已恢复"
        else:
            state.paused_providers.add(name)
            verb = "已暂停"
        wake.set()
        try:
            notify.alert("AgentEye", f"{verb}:{name}")
        except Exception:
            pass

    def probe_models(name):
        """行菜单入口:对缓存模型列表的首个模型发 1-token 试调并弹结果。

        真正的 HTTP 放在子线程里:这个函数是 tk.Menu 的 command 回调,
        跑在 Tk 主线程上,同步发请求会把事件循环堵死最多 10s
        (请求超时),表现为窗口停止重绘、倒计时停住、Windows 弹"未响应"。
        """
        target = next((p for p in cfg.get("providers") or []
                       if p.get("name") == name), None)
        if not target:
            return
        base_url = target.get("base_url") or ""
        key = config_mod.plain_key(target)
        if not base_url or not key:
            notify.alert("AgentEye", f"{name} 缺少 base_url 或 key,无法试调")
            return
        models = cache_mod.get_models(base_url, key) or []
        if not models:
            notify.alert("AgentEye", f"{name} 没有模型缓存,先查看模型列表")
            return
        model_id = models[0]

        def worker():
            try:
                ok, latency, err = probe_model(model_id, base_url, key,
                                               provider_name=name)
                detail = f"{latency:.0f}ms" if ok else (err or "试调失败")
                notify.alert("AgentEye", f"{name} · {model_id} · {detail}")
            except Exception as e:
                try:
                    notify.alert("AgentEye", f"{name} 试调失败:"
                                           f"{e.__class__.__name__}")
                except Exception:
                    pass

        threading.Thread(target=worker, name=f"probe-{name}",
                         daemon=True).start()

    def probe_model(model_id, base_url, key, timeout=10.0, provider_name=""):
        """1-token 试调:返回 (ok, latency_ms, error) 三元组。"""
        import requests
        if not base_url or not key:
            return False, 0.0, "缺少 base_url 或 key"
        url = base_url.rstrip("/")
        url = url + "/chat/completions" if url.endswith("/v1") else url + "/v1/chat/completions"
        try:
            t0 = time.time()
            r = requests.post(
                url,
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={"model": model_id, "messages": [{"role": "user", "content": "hi"}],
                      "max_tokens": 1},
                timeout=timeout,
            )
            latency = (time.time() - t0) * 1000
        except requests.RequestException as e:
            return False, 0.0, str(e.__class__.__name__)
        if r.status_code in (401, 403):
            return False, latency, f"key 无效 (HTTP {r.status_code})"
        if r.status_code != 200:
            return False, latency, f"HTTP {r.status_code}"
        import cache
        try:
            cache.log_probe(provider_name=provider_name, model_id=model_id,
                            success=True, latency_ms=latency)
        except Exception:
            pass
        return True, latency, ""

    return {
        "refresh_now": refresh_now,
        "toggle_pause": toggle_pause,
        "test_notify": test_notify,
        "open_config": open_config,
        "open_settings": open_settings,
        "save_position": save_position,
        "save_size": save_size,
        "save_order": save_order,
        "save_pin": save_pin,
        "save_ui": save_ui,
        "save_theme": save_theme,
        "get_order": get_order,
        "save_model_order": save_model_order,
        "quit": quit_app,
        "add_key": add_key,
        "edit_provider": edit_provider,
        "update_provider": update_provider,
        "pause_provider": pause_provider,
        "probe_models": probe_models,
        "delete_provider": delete_provider,
        "delete_provider_by_id": delete_provider_by_id,
        "probe_model": probe_model,
    }


def main():
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    cfg = config_mod.load_v2()
    state = State()
    stop = threading.Event()
    wake = threading.Event()

    poller = Poller(cfg, state, stop, wake)
    poller.start()

    import tkinter as tk

    root = tk.Tk()
    actions = build_actions(root, cfg, state, stop, wake, poller=poller)
    mac = MacWindow(root, cfg, actions)

    initial_theme = (cfg.get("ui") or {}).get("theme") or "auto"
    mac.apply_theme(initial_theme, broadcast=True, persist=False)

    panel = Panel(mac.standard_slot, state, cfg, actions, root_window=root)

    def open_model_panel(provider_name):
        try:
            panel._show_models(provider_name)
        except Exception:
            pass

    essential = EssentialBar(mac.essential_slot, state, cfg, mac.fonts_dict,
                             on_expand=mac.toggle_mode,
                             on_open_models=open_model_panel)

    mac.attach_standard(panel)
    mac.attach_essential(essential)
    mac.show_initial_mode()
    root.mainloop()

    stop.set()
    wake.set()


EXIT_OK = 0
EXIT_ERROR = 1
EXIT_CONFIG = 2
EXIT_NO_REQUESTS = 3
EXIT_NO_TK = 4


def _run():
    """进程入口:按 AGENTS.md 的退出码契约返回。"""
    try:
        import requests  # noqa: F401
    except ImportError:
        sys.stderr.write(
            "缺少依赖 requests,先执行 pip install -r requirements.txt\n")
        return EXIT_NO_REQUESTS
    try:
        main()
    except ImportError as e:
        if "tkinter" in str(e):
            sys.stderr.write(
                "当前 Python 未包含 tkinter,换官方安装包重装\n")
            return EXIT_NO_TK
        raise
    except config_mod.ConfigVersionError as e:
        # 配置来自更新版本,不是"崩溃"。走独立退出码,让 run.bat 之类的
        # 启动器能区分"该升级"和"程序坏了"。
        sys.stderr.write(f"{e}\n")
        return EXIT_CONFIG
    except config_mod.ConfigError as e:
        # 配置存在但读不了/不合规。为避免覆盖用户数据,这里直接退出,
        # 不做任何写入。
        sys.stderr.write(f"配置问题:{e}\n")
        return EXIT_CONFIG
    except Exception as e:
        sys.stderr.write(f"启动失败:{e.__class__.__name__}: {e}\n")
        return EXIT_ERROR
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(_run())
