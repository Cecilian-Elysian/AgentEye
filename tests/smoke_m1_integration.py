"""M1 完整集成测试:MacWindow + Panel 一起跑,空 providers 状态。

验证整条 init 链路不抛异常,header 与 panel header 都不冲突。
"""
import os
import sys
import threading
import time
import tkinter as tk

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import ctypes
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

import config as config_mod
import notify
import cache as cache_mod
from providers import fetch_all
from ui import Panel
from ui.app import MacWindow


class State:
    def __init__(self):
        self.results = []
        self.last_fetch = 0.0
        self.next_fetch = 0.0
        self.paused = False
        self.fetching = False


def build_actions(root, cfg, state, stop, wake):
    return {
        "refresh_now": lambda: None,
        "toggle_pause": lambda: None,
        "test_notify": lambda: None,
        "open_config": lambda: None,
        "open_settings": lambda: None,
        "save_position": lambda *a, **k: None,
        "save_size": lambda *a, **k: None,
        "save_order": lambda *a, **k: None,
        "save_pin": lambda *a, **k: None,
        "get_order": lambda: [],
        "save_model_order": lambda *a, **k: None,
        "quit": lambda: root.destroy(),
        "add_key": lambda: None,
        "delete_provider": lambda *a, **k: None,
        "probe_model": lambda *a, **k: (False, 0.0, ""),
    }


def integration():
    cfg = config_mod.load_v2()
    state = State()
    stop = threading.Event()
    wake = threading.Event()

    root = tk.Tk()
    root.withdraw()
    actions = build_actions(root, cfg, state, stop, wake)
    mac = MacWindow(root, cfg, actions)
    panel = Panel(mac.standard_slot, state, cfg, actions, root_window=root)
    mac.attach_standard(panel)
    mac.show_initial_mode()

    root.update_idletasks()
    print(f"[ok] MacWindow + Panel integrated")
    print(f"[ok] root overrideredirect = {root.overrideredirect()}")
    print(f"[ok] topmost = {root.attributes('-topmost')}")
    print(f"[ok] bg = {root.cget('bg')}")

    root.update()
    time.sleep(0.05)
    root.update()
    root.destroy()
    print("[ok] integration test passed")


if __name__ == "__main__":
    integration()
