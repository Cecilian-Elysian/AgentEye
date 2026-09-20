import os
import sys
import threading
import time
import uuid

import config as config_mod
import notify
from providers import fetch_all
from ui import Panel
from ui.add_key import AddKeyDialog


class State:
    def __init__(self):
        self.results = []
        self.last_fetch = 0.0
        self.next_fetch = 0.0
        self.paused = False
        self.fetching = False


class Poller(threading.Thread):
    def __init__(self, cfg, state, stop_event, wake_event):
        super().__init__(daemon=True)
        self.cfg = cfg
        self.state = state
        self.stop = stop_event
        self.wake = wake_event
        self.notified = {}

    def run(self):
        while not self.stop.is_set():
            if self.state.paused:
                if self.wake.wait(0.5):
                    self.wake.clear()
                continue
            self.fetch_once()
            interval = config_mod.clamp_interval_v2(self.cfg)
            end = time.time() + interval
            self.state.next_fetch = end
            while time.time() < end and not self.stop.is_set():
                if self.wake.wait(0.5):
                    self.wake.clear()
                    break
                if self.state.paused:
                    break

    def fetch_once(self):
        self.state.fetching = True
        try:
            results = fetch_all(self.cfg)
        finally:
            self.state.fetching = False
        self.state.results = results
        self.state.last_fetch = time.time()
        self._fire_alerts(results)

    def _fire_alerts(self, results):
        alert_cfg = self.cfg.get("alert") or {}
        if not alert_cfg.get("enable", True):
            return
        cooldown = float(alert_cfg.get("cooldown_min", 60)) * 60
        now = time.time()
        items = []
        for r in results:
            level = r.get("level")
            if level not in ("warn", "critical"):
                continue
            key = r["name"]
            last = self.notified.get(key)
            if last and last[0] == level and now - last[1] < cooldown:
                continue
            self.notified[key] = (level, now)
            verb = "额度告急" if level == "critical" else "额度偏低"
            items.append((r["name"], verb))
        if items:
            notify.alert_many(items)


def _infer_kind_from_dialog(entry):
    """Add Key 对话框提交后,根据 URL/key 推断 kind。"""
    from providers import detect as detect_mod
    r = detect_mod.detect(entry.get("key", ""), entry.get("base_url", ""))
    return r["kind"]


def build_actions(root, cfg, state, stop, wake):
    def refresh_now():
        wake.set()

    def toggle_pause():
        state.paused = not state.paused
        if not state.paused:
            wake.set()

    def test_notify():
        if not notify.send_toast("AgentEye", "通知测试 OK"):
            notify.beep()

    def open_config():
        try:
            os.startfile(str(config_mod.CONFIG_PATH))
        except OSError:
            pass

    def open_settings():
        from ui.settings_dialog import SettingsDialog

        def _on_save(new_cfg):
            cfg.clear()
            cfg.update(new_cfg)
            config_mod.save_v2(cfg)
            _apply_settings_live()

        SettingsDialog(root, cfg, on_save=_on_save)

    def _apply_settings_live():
        """设置保存后即时生效:立即唤醒 poller,新配置下次 fetch 生效。"""
        wake.set()

    def save_position(x, y):
        ui = cfg.setdefault("ui", {})
        ui["x"], ui["y"] = int(x), int(y)
        config_mod.save_v2(cfg)

    def save_size(w, h):
        ui = cfg.setdefault("ui", {})
        ui["width"], ui["height"] = int(w), int(h)
        config_mod.save_v2(cfg)

    def save_order(order):
        ui = cfg.setdefault("ui", {})
        ui["order"] = list(order)
        config_mod.save_v2(cfg)

    def save_pin(pinned):
        ui = cfg.setdefault("ui", {})
        ui["pinned"] = bool(pinned)
        config_mod.save_v2(cfg)

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
        def _on_save(entry):
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
            config_mod.save_v2(cfg)
            try:
                import notify as notify_mod
                notify_mod.alert("AgentEye", f"已添加:{new_provider['name']}")
            except Exception:
                pass
            wake.set()
        count = len(cfg.get("providers") or [])
        AddKeyDialog(root, on_save=_on_save, current_count=count)

    def probe_model(model_id, base_url, key, timeout=10.0):
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
            cache.log_probe(provider_name="", model_id=model_id,
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
        "get_order": get_order,
        "save_model_order": save_model_order,
        "quit": quit_app,
        "add_key": add_key,
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
    actions = build_actions(root, cfg, state, stop, wake)
    Panel(root, state, cfg, actions)
    root.mainloop()

    stop.set()
    wake.set()


if __name__ == "__main__":
    sys.exit(main())
