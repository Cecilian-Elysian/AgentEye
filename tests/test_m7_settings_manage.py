"""设置面板内嵌 provider 管理测试。

- AddKeyForm 编辑模式(initial 预填 + show_presets 开关)
- SettingsDialog 中间区「列表 ↔ 表单」切换
- 列表行渲染 / 空列表提示 / 删除回调 / 编辑保存回调
- main.py 接线(edit_provider / update_provider / delete_provider_by_id)
"""
import os
import sys
import unittest
import tkinter as tk

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from ui.theme import set_theme


def _collect_texts(w):
    """递归收集子树里所有 Label 的 text,用于断言列表渲染。"""
    texts = []
    for c in w.winfo_children():
        if isinstance(c, tk.Label):
            texts.append(str(c.cget("text")))
        texts.extend(_collect_texts(c))
    return texts


class TestAddKeyFormInitial(unittest.TestCase):
    """AddKeyForm 编辑模式:initial 预填,不自动探测,可直接保存。"""

    @classmethod
    def setUpClass(cls):
        set_theme("dark", broadcast=False, persist=False)
        cls.root = tk.Tk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.root.destroy()
        except tk.TclError:
            pass

    def test_initial_prefills_all_fields(self):
        from ui.add_key import AddKeyForm
        form = AddKeyForm(self.root, initial={
            "name": "我的 DeepSeek",
            "key": "sk-test123",
            "base_url": "https://api.deepseek.com",
        })
        try:
            self.assertEqual(form.name_var.get(), "我的 DeepSeek")
            self.assertEqual(form.key_var.get(), "sk-test123")
            self.assertEqual(form.url_var.get(), "https://api.deepseek.com")
            self.assertFalse(form._key_placeholder)
            self.assertFalse(form._url_placeholder)
            # key 已预填 → 保存按钮直接可用,无需先探测
            self.assertEqual(str(form.save_btn["state"]), "normal")
        finally:
            try:
                form.destroy()
            except tk.TclError:
                pass

    def test_initial_empty_key_keeps_placeholder(self):
        from ui.add_key import AddKeyForm
        form = AddKeyForm(self.root, initial={"name": "x", "key": ""})
        try:
            self.assertTrue(form._key_placeholder)
            self.assertEqual(str(form.save_btn["state"]), "disabled")
        finally:
            try:
                form.destroy()
            except tk.TclError:
                pass

    def test_show_presets_false_hides_preset_row(self):
        from ui.add_key import AddKeyForm
        form = AddKeyForm(self.root, show_presets=False)
        try:
            texts = [str(w.cget("text")) for w in form.winfo_children()
                     if isinstance(w, tk.Label)]
            self.assertNotIn("快速选择", texts)
        finally:
            try:
                form.destroy()
            except tk.TclError:
                pass

    def test_default_shows_preset_row(self):
        from ui.add_key import AddKeyForm
        form = AddKeyForm(self.root)
        try:
            texts = [str(w.cget("text")) for w in form.winfo_children()
                     if isinstance(w, tk.Label)]
            self.assertIn("快速选择", texts)
        finally:
            try:
                form.destroy()
            except tk.TclError:
                pass


class TestSettingsManageList(unittest.TestCase):
    """SettingsDialog 中间区列表模式渲染。"""

    def setUp(self):
        set_theme("dark", broadcast=False, persist=False)
        self.root = tk.Tk()
        self.root.withdraw()

    def tearDown(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def _make_dialog(self, cfg, **kwargs):
        from ui.settings_dialog import SettingsDialog
        dlg = SettingsDialog(self.root, cfg, **kwargs)
        self.addCleanup(self._safe_destroy, dlg)
        return dlg

    @staticmethod
    def _safe_destroy(dlg):
        try:
            dlg.destroy()
        except tk.TclError:
            pass

    def test_default_opens_list_mode(self):
        cfg = {"providers": [
            {"id": "p1", "name": "MiniMax", "kind": "minimax",
             "key": "k1", "base_url": "https://api.minimaxi.com"},
            {"id": "p2", "name": "中转站", "kind": "relay",
             "key": "k2", "base_url": ""},
        ]}
        dlg = self._make_dialog(cfg)
        self.assertIsNone(dlg._form)
        texts = _collect_texts(dlg._center)
        self.assertIn("API 管理", texts)
        self.assertIn("共 2 个", texts)
        self.assertIn("MiniMax", texts)
        self.assertIn("中转站", texts)
        self.assertIn("(未填 base_url)", texts)
        self.assertIn("→ 添加 API Key", texts)

    def test_empty_list_shows_hint(self):
        dlg = self._make_dialog({"providers": []})
        self.assertIsNone(dlg._form)
        texts = _collect_texts(dlg._center)
        self.assertIn("共 0 个", texts)
        self.assertTrue(any("暂无 provider" in t for t in texts))

    def test_initial_view_add_key(self):
        from ui.add_key import AddKeyForm
        dlg = self._make_dialog({"providers": []}, initial_view="add_key")
        self.assertIsInstance(dlg._form, AddKeyForm)
        self.assertIsNone(dlg._editing_id)

    def test_initial_view_edit_prefills(self):
        from ui.add_key import AddKeyForm
        cfg = {"providers": [
            {"id": "p1", "name": "智谱", "kind": "zhipu",
             "key": "zk-1", "base_url": "https://open.bigmodel.cn"},
        ]}
        dlg = self._make_dialog(cfg, initial_view=("edit", "p1"))
        self.assertIsInstance(dlg._form, AddKeyForm)
        self.assertEqual(dlg._editing_id, "p1")
        self.assertEqual(dlg._form.name_var.get(), "智谱")
        self.assertEqual(dlg._form.key_var.get(), "zk-1")
        # 编辑模式不显示预设
        texts = [str(w.cget("text")) for w in dlg._form.winfo_children()
                 if isinstance(w, tk.Label)]
        self.assertNotIn("快速选择", texts)

    def test_initial_view_edit_missing_id_falls_back_to_list(self):
        dlg = self._make_dialog({"providers": []},
                                initial_view=("edit", "ghost"))
        self.assertIsNone(dlg._form)
        self.assertIsNone(dlg._editing_id)


class TestSettingsManageActions(unittest.TestCase):
    """删除 / 编辑保存回调链路。"""

    def setUp(self):
        set_theme("dark", broadcast=False, persist=False)
        self.root = tk.Tk()
        self.root.withdraw()

    def tearDown(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def _make_cfg(self):
        return {"providers": [
            {"id": "p1", "name": "A", "kind": "minimax", "key": "k1",
             "base_url": "u1"},
            {"id": "p2", "name": "B", "kind": "relay", "key": "k2",
             "base_url": ""},
        ]}

    def test_delete_confirmed_calls_host_and_refreshes(self):
        from ui.settings_dialog import SettingsDialog
        cfg = self._make_cfg()
        deleted = []
        dlg = SettingsDialog(self.root, cfg,
                             on_delete_provider=lambda pid: (
                                 deleted.append(pid),
                                 cfg.__setitem__(
                                     "providers",
                                     [p for p in cfg["providers"]
                                      if p.get("id") != pid]))[0])
        try:
            dlg._delete_confirmed("p1")
            self.assertEqual(deleted, ["p1"])
            texts = _collect_texts(dlg._center)
            self.assertIn("共 1 个", texts)
            self.assertNotIn("A", texts)
            self.assertIn("B", texts)
        finally:
            try:
                dlg.destroy()
            except tk.TclError:
                pass

    def test_confirm_delete_spawns_dialog(self):
        from ui.confirm_delete import ConfirmDeleteDialog
        from ui.settings_dialog import SettingsDialog
        cfg = self._make_cfg()
        dlg = SettingsDialog(self.root, cfg)
        try:
            dlg._confirm_delete("p1")
            # ConfirmDeleteDialog 的 parent 是设置对话框本身
            confirms = [w for w in dlg.winfo_children()
                        if isinstance(w, ConfirmDeleteDialog)]
            self.assertEqual(len(confirms), 1)
            self.assertEqual(confirms[0]._expected, "A")
            confirms[0].destroy()
        finally:
            try:
                dlg.destroy()
            except tk.TclError:
                pass

    def test_save_with_editing_id_calls_update(self):
        from ui.settings_dialog import SettingsDialog
        cfg = self._make_cfg()
        updates = []
        dlg = SettingsDialog(
            self.root, cfg,
            on_update_provider=lambda pid, e: updates.append((pid, e)))
        try:
            self.assertIsNone(dlg._editing_id)  # 列表模式
            dlg._editing_id = "p2"
            dlg._handle_entry_saved(
                {"name": "B2", "key": "k2x", "base_url": "u2"})
            self.assertEqual(updates, [("p2", {"name": "B2", "key": "k2x",
                                               "base_url": "u2"})])
            # 保存后回到列表模式
            self.assertIsNone(dlg._form)
            self.assertIsNone(dlg._editing_id)
        finally:
            try:
                dlg.destroy()
            except tk.TclError:
                pass

    def test_save_without_editing_id_calls_add(self):
        from ui.settings_dialog import SettingsDialog
        cfg = self._make_cfg()
        added, updated = [], []
        dlg = SettingsDialog(self.root, cfg,
                             on_add_key=lambda e: added.append(e),
                             on_update_provider=lambda pid, e: updated.append((pid, e)))
        try:
            dlg._handle_entry_saved({"name": "C", "key": "k3", "base_url": ""})
            self.assertEqual(len(added), 1)
            self.assertEqual(updated, [])
        finally:
            try:
                dlg.destroy()
            except tk.TclError:
                pass


class TestMainWiring(unittest.TestCase):
    """main.py 接线源码断言(仿 TestM45Integration 模式)。"""

    def _main_src(self):
        return open(os.path.join(ROOT, "main.py"), encoding="utf-8").read()

    def test_edit_provider_action_registered(self):
        src = self._main_src()
        self.assertIn('"edit_provider": edit_provider', src)

    def test_edit_provider_opens_settings_with_edit_view(self):
        src = self._main_src()
        self.assertIn('open_settings(("edit", target.get("id")))', src)

    def test_settings_dialog_receives_manage_callbacks(self):
        src = self._main_src()
        self.assertIn("on_update_provider=update_provider", src)
        self.assertIn("on_delete_provider=delete_provider_by_id", src)

    def test_panel_row_menu_uses_edit_provider(self):
        src = open(os.path.join(ROOT, "ui", "panel.py"), encoding="utf-8").read()
        self.assertIn('"edit_provider"', src)


if __name__ == "__main__":
    unittest.main()
