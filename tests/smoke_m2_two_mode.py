"""M2 集成 smoke test:MacWindow + Panel + EssentialBar 两态切换。"""
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
from ui import Panel
from ui.app import MacWindow
from ui.essential_bar import EssentialBar


class State:
    def __init__(self):
        self.results = [
            {"name": "DeepSeek", "level": "ok", "unit": "$",
             "remaining": 8.20, "total": 10.0, "used_today": 1.80,
             "detail": "总余额", "pct": 18},
            {"name": "MiniMax", "level": "warn", "unit": "%",
             "remaining": None, "total": None, "pct": 62, "reset_at": time.time() + 3600,
             "detail": "5h 62% · 周 44%"},
        ]
        self.last_fetch = time.time()
        self.next_fetch = time.time() + 30
        self.paused = False
        self.fetching = False


def build_actions(root, cfg):
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
        "save_ui": lambda: None,
        "get_order": lambda: [],
        "save_model_order": lambda *a, **k: None,
        "quit": lambda: root.destroy(),
        "add_key": lambda: None,
        "delete_provider": lambda *a, **k: None,
        "probe_model": lambda *a, **k: (False, 0.0, ""),
    }


def smoke():
    cfg = config_mod.load_v2()
    state = State()

    root = tk.Tk()
    root.withdraw()
    actions = build_actions(root, cfg)
    mac = MacWindow(root, cfg, actions)

    panel = Panel(mac.standard_slot, state, cfg, actions, root_window=root)
    bar = EssentialBar(mac.essential_slot, state, cfg, mac.fonts_dict,
                       on_expand=mac.toggle_mode)
    mac.attach_standard(panel)
    mac.attach_essential(bar)

    print(f"[ok] initial mode = {mac.mode}")
    mac.show_initial_mode()
    root.update_idletasks()
    root.update()
    print(f"[ok] after init mode = {mac.mode}")
    print(f"[ok] root geom = {root.winfo_geometry()}")

    mac.toggle_mode()
    root.update_idletasks()
    root.update()
    print(f"[ok] after toggle mode = {mac.mode}")
    print(f"[ok] root geom essential = {root.winfo_geometry()}")

    mac.toggle_mode()
    root.update_idletasks()
    root.update()
    print(f"[ok] after second toggle mode = {mac.mode}")

    root.destroy()
    print("[ok] M2 smoke test passed")


if __name__ == "__main__":
    smoke()
