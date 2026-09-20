import os
import sys
import threading
import time

import config as config_mod
import notify
from providers import fetch_all
from ui import Panel


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
            interval = config_mod.clamp_interval(self.cfg)
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
            notify.alert(f"AgentEye · {r['name']}", verb)


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

    def save_position(x, y):
        ui = cfg.setdefault("ui", {})
        ui["x"], ui["y"] = int(x), int(y)
        config_mod.save(cfg)

    def quit_app():
        stop.set()
        wake.set()
        try:
            root.destroy()
        except Exception:
            pass

    return {
        "refresh_now": refresh_now,
        "toggle_pause": toggle_pause,
        "test_notify": test_notify,
        "open_config": open_config,
        "save_position": save_position,
        "quit": quit_app,
    }


def main():
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    cfg = config_mod.load()
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
