"""行级右键菜单。

供 ui/panel.py 在每行右键时弹出。
Actions 通过 callbacks 注入,保持解耦。
删除操作要求输入名字确认,见 ui/confirm_delete.ConfirmDeleteDialog。
"""

import tkinter as tk


class RowMenu:
    def __init__(self, parent, on_refresh, on_pause, on_edit, on_delete,
                 on_copy_key, on_copy_url, on_show_models, on_probe):
        self.parent = parent
        self._on_delete_raw = on_delete
        self._delete_target = None
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
        self._delete_idx = self.menu.index("end")
        self.menu.add_command(label="删除此 provider", command=self._ask_delete)

    def set_target(self, name):
        self._delete_target = name

    def _ask_delete(self):
        from ui.confirm_delete import ConfirmDeleteDialog
        name = self._delete_target
        if not name:
            return
        ConfirmDeleteDialog(
            self.parent,
            name=name,
            message=f"删除 provider {name} 不可恢复。其模型列表缓存会被清空,试调日志保留。",
            on_confirm=self._on_delete_raw,
        )

    def popup(self, x, y):
        try:
            self.menu.tk_popup(x, y)
        finally:
            self.menu.grab_release()
