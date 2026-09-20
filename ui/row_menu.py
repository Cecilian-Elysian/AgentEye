"""行级右键菜单。

供 ui/panel.py 在每行右键时弹出。
Actions 通过 callbacks 注入,保持解耦。
"""

import tkinter as tk


class RowMenu:
    def __init__(self, parent, on_refresh, on_pause, on_edit, on_delete,
                 on_copy_key, on_copy_url, on_show_models, on_probe):
        self.parent = parent
        self.menu = tk.Menu(parent, tearoff=0)
        self.menu.add_command(label="立即刷新此行", command=on_refresh)
        self.menu.add_command(label="查看模型列表", command=on_show_models)
        self.menu.add_command(label="试调模型…", command=on_probe)
        self.menu.add_separator()
        self.menu.add_command(label="编辑此 provider", command=on_edit)
        self.menu.add_command(label="暂停此 provider", command=on_pause)
        self.menu.add_separator()
        self.menu.add_command(label="复制 key", command=on_copy_key)
        self.menu.add_command(label="复制 base URL", command=on_copy_url)
        self.menu.add_separator()
        self.menu.add_command(label="删除此 provider", command=on_delete)

    def popup(self, x, y):
        try:
            self.menu.tk_popup(x, y)
        finally:
            self.menu.grab_release()
