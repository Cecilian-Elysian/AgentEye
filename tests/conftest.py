"""pytest 共享配置。

Windows 上同一进程里反复创建/销毁多个 Tk root 时,tk.Tk() 偶发
TclError("tk wasn't installed properly")。这里给 Tk.__init__ 加
有限次重试,消掉这种环境级抖动;不改变任何测试语义。
"""

import time
import tkinter as tk

_orig_tk_init = tk.Tk.__init__


def _retrying_tk_init(self, *args, **kwargs):
    last_err = None
    for _ in range(5):
        try:
            _orig_tk_init(self, *args, **kwargs)
            return
        except tk.TclError as e:
            last_err = e
            time.sleep(0.2)
    raise last_err


tk.Tk.__init__ = _retrying_tk_init
