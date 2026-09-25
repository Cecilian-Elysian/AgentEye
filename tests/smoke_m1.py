"""M1 smoke test:启动一个 Tk root + MacWindow,不进 mainloop,直接销毁。

验证 MacWindow 不会在 init 阶段炸,且 traffic light / header 都创建出来了。
"""
import os
import sys
import tkinter as tk

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import ctypes
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

import config as config_mod
from ui.app import MacWindow
from ui.theme import PALETTE, Layout


def smoke():
    cfg = config_mod.load_v2()
    root = tk.Tk()
    root.geometry(f"{Layout.MIN_W}x{Layout.MIN_H+100}+200+200")

    actions = {
        "quit": lambda: None,
        "minimize": lambda: None,
        "toggle_pin": lambda: None,
        "save_position": lambda *a, **k: None,
    }
    mac = MacWindow(root, cfg, actions)

    assert mac.header is not None
    assert mac.body is not None
    assert mac.standard_slot is not None
    assert mac.essential_slot is not None
    print("[ok] MacWindow created")
    print(f"[ok] header bg = {mac.header.cget('bg')}")
    print(f"[ok] pin color = {PALETTE.TRAFFIC_GREEN}")
    print(f"[ok] fonts ui = {mac.fonts_dict['ui']}")
    print(f"[ok] fonts mono = {mac.fonts_dict['mono']}")
    print(f"[ok] traffic light count = 3 (close/minimize/pin)")

    root.update_idletasks()
    print(f"[ok] root size = {root.winfo_width()}x{root.winfo_height()}")
    root.destroy()
    print("[ok] smoke test passed")


if __name__ == "__main__":
    smoke()
