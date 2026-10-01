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


class TestDuplicateNameRejected(unittest.TestCase):
    """重名 provider 不允许保存。

    背景:面板用 name 做 self._rows 的键,重名会让其中一行不再被刷新,
    且行右键的编辑/删除/暂停按 name 查第一个命中,会作用到错误的条目。
    """

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

    def _cfg(self):
        return {"providers": [
            {"id": "p1", "name": "DeepSeek", "kind": "deepseek",
             "key": "k1", "base_url": "https://api.deepseek.com"},
            {"id": "p2", "name": "中转站", "kind": "relay",
             "key": "k2", "base_url": ""},
        ]}

    def _form(self, cfg, **kwargs):
        from ui.add_key import AddKeyForm
        form = AddKeyForm(self.root, **kwargs)
        self.addCleanup(self._destroy, form)
        return form

    @staticmethod
    def _destroy(form):
        try:
            form.destroy()
        except tk.TclError:
            pass

    def _form_in_dialog(self, cfg, **kwargs):
        from ui.settings_dialog import SettingsDialog
        dlg = SettingsDialog(self.root, cfg, **kwargs)
        self.addCleanup(self._destroy, dlg)
        return dlg

    # ---------- 纯逻辑:SettingsDialog._taken_names ----------

    def test_taken_names_lists_existing(self):
        dlg = self._form_in_dialog(self._cfg())
        self.assertEqual(dlg._taken_names(None), {"DeepSeek", "中转站"})

    def test_taken_names_excludes_the_one_being_edited(self):
        dlg = self._form_in_dialog(self._cfg())
        self.assertEqual(dlg._taken_names("p1"), {"中转站"})

    def test_taken_names_skips_blank_names(self):
        dlg = self._form_in_dialog({"providers": [
            {"id": "p1", "name": "  ", "key": "k"},
            {"id": "p2", "name": "", "key": "k"},
            {"id": "p3", "name": "OK", "key": "k"},
        ]})
        self.assertEqual(dlg._taken_names(None), {"OK"})

    def test_taken_names_ignores_non_dict_entries(self):
        dlg = self._form_in_dialog({"providers": ["垃圾", {"id": "p1",
                                                          "name": "OK"}]})
        self.assertEqual(dlg._taken_names(None), {"OK"})

    # ---------- 行为:表单保存被拦下 ----------

    def _fill(self, form, name, key="sk-new"):
        form.name_var.set(name)
        form.key_var.set(key)
        form._key_placeholder = False

    def test_duplicate_name_blocks_save(self):
        saved = []
        form = self._form(self._cfg(), on_save=saved.append,
                          taken_names={"DeepSeek", "中转站"})
        self._fill(form, "DeepSeek")
        with _no_messagebox():
            form._save()
        self.assertEqual(saved, [], "重名不应触发 on_save")

    def test_duplicate_name_does_not_close_form(self):
        done = []
        form = self._form(self._cfg(), on_save=lambda e: None,
                          on_done=lambda: done.append(True),
                          taken_names={"DeepSeek"})
        self._fill(form, "DeepSeek")
        with _no_messagebox():
            form._save()
        self.assertEqual(done, [], "重名不应触发 on_done")

    def test_fresh_name_is_accepted(self):
        saved = []
        form = self._form(self._cfg(), on_save=saved.append,
                          taken_names={"DeepSeek"})
        self._fill(form, "新的名字")
        form._save()
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0]["name"], "新的名字")

    def test_empty_name_falls_back_and_is_still_checked(self):
        saved = []
        form = self._form(self._cfg(), on_save=saved.append,
                          taken_names={"未命名"})
        self._fill(form, "")
        with _no_messagebox():
            form._save()
        self.assertEqual(saved, [], "空名回退成'未命名'后也要查重名")

    def test_taken_names_default_is_empty(self):
        saved = []
        form = self._form(self._cfg(), on_save=saved.append)
        self._fill(form, "DeepSeek")
        form._save()
        self.assertEqual(len(saved), 1, "不传 taken_names 时不做重名拦截")

    # ---------- 接线:对话框真的把名单传进表单 ----------

    def test_add_view_passes_taken_names_to_form(self):
        dlg = self._form_in_dialog(self._cfg(), initial_view="add_key")
        self.assertEqual(dlg._form._taken_names,
                         frozenset({"DeepSeek", "中转站"}))

    def test_edit_view_excludes_own_name(self):
        dlg = self._form_in_dialog(self._cfg(), initial_view=("edit", "p1"))
        self.assertEqual(dlg._form._taken_names, frozenset({"中转站"}))
        # 自己原来的名字可以保留,不算冲突
        saved = []
        dlg._form.on_save = saved.append
        dlg._form._key_placeholder = False
        dlg._form._save()
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0]["name"], "DeepSeek")

    def test_edit_view_cannot_rename_onto_sibling(self):
        dlg = self._form_in_dialog(self._cfg(), initial_view=("edit", "p1"))
        saved = []
        dlg._form.on_save = saved.append
        dlg._form.name_var.set("中转站")
        dlg._form._key_placeholder = False
        with _no_messagebox():
            dlg._form._save()
        self.assertEqual(saved, [], "改名撞上兄弟条目应被拦下")


class _no_messagebox:
    """把 messagebox 弹窗换成 no-op,避免测试阻塞在模态框上。"""

    def __enter__(self):
        import ui.add_key as ak
        self._orig_warn = ak.messagebox.showwarning
        self._orig_error = ak.messagebox.showerror
        ak.messagebox.showwarning = lambda *a, **k: None
        ak.messagebox.showerror = lambda *a, **k: None
        return self

    def __exit__(self, *exc):
        import ui.add_key as ak
        ak.messagebox.showwarning = self._orig_warn
        ak.messagebox.showerror = self._orig_error
        return False


class TestSettingsWindowIsSingleton(unittest.TestCase):
    """设置窗口单例:重复点击复用同一实例,不叠出一串对话框。

    背景:open_settings 此前每次都 new 一个 SettingsDialog,连点绿点或
    反复用右键「设置…」会叠出一串各自为政的窗口(一个在列表一个在表单),
    编辑会互相覆盖 cfg。
    """

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

    @staticmethod
    def _destroy(w):
        try:
            w.destroy()
        except tk.TclError:
            pass

    def _actions(self, cfg):
        import threading
        import main as main_mod
        state = main_mod.State()
        return main_mod.build_actions(self.root, cfg, state,
                                      threading.Event(), threading.Event())

    def _cfg(self):
        return {"providers": [
            {"id": "p1", "name": "DeepSeek", "kind": "deepseek",
             "key": "k1", "base_url": "https://api.deepseek.com"},
        ]}

    def _open(self, actions, view=None):
        from ui.settings_dialog import SettingsDialog
        actions["open_settings"](view)
        dialogs = [w for w in self.root.winfo_children()
                   if isinstance(w, SettingsDialog) and w.winfo_exists()]
        self.assertEqual(len(dialogs), 1, f"应只有 1 个设置窗口,实得 {len(dialogs)}")
        self.addCleanup(self._destroy, dialogs[0])
        return dialogs[0]

    def test_second_open_reuses_same_window(self):
        actions = self._actions(self._cfg())
        first = self._open(actions)
        second = self._open(actions)
        self.assertIs(first, second)

    def test_reopen_navigates_to_add_view(self):
        actions = self._actions(self._cfg())
        dlg = self._open(actions)
        self.assertIsNone(dlg._form)
        self._open(actions, "add_key")
        self.assertIsNotNone(dlg._form, "应切到添加表单")
        self.assertIsNone(dlg._editing_id)

    def test_reopen_navigates_to_edit_view(self):
        actions = self._actions(self._cfg())
        dlg = self._open(actions)
        self._open(actions, ("edit", "p1"))
        self.assertEqual(dlg._editing_id, "p1")
        self.assertIsNotNone(dlg._form)

    def test_reopen_back_to_list(self):
        actions = self._actions(self._cfg())
        dlg = self._open(actions, "add_key")
        self._open(actions)
        self.assertIsNone(dlg._form)
        self.assertIsNone(dlg._editing_id)

    def test_recreated_after_destroy(self):
        """窗口被关掉后引用要失效,下次点击要能重新开。"""
        actions = self._actions(self._cfg())
        first = self._open(actions)
        self._destroy(first)
        self.root.update_idletasks()
        second = self._open(actions)
        self.assertIsNot(first, second)
        self.assertTrue(second.winfo_exists())

    def test_unknown_edit_target_falls_back_to_list(self):
        actions = self._actions(self._cfg())
        dlg = self._open(actions)
        self._open(actions, ("edit", "不存在"))
        self.assertIsNone(dlg._form)

    def test_main_holds_a_single_slot(self):
        """源码断言:宿主必须持有一个可复用的引用。"""
        src = open(os.path.join(ROOT, "main.py"), encoding="utf-8").read()
        self.assertIn('_settings_win = {"dlg": None}', src)
        self.assertIn("dlg.goto(view)", src)
        self.assertIn("dlg.raise_()", src)

    def test_dialog_exposes_goto_and_raise(self):
        from ui.settings_dialog import SettingsDialog
        self.assertTrue(callable(getattr(SettingsDialog, "goto", None)))
        self.assertTrue(callable(getattr(SettingsDialog, "raise_", None)))

    def test_goto_on_destroyed_dialog_is_noop(self):
        actions = self._actions(self._cfg())
        dlg = self._open(actions)
        self._destroy(dlg)
        dlg.goto("add_key")  # 不应抛异常
        dlg.raise_()

    def test_save_does_not_wipe_config(self):
        """点「保存设置」不得清空 cfg(回归:P0 整份配置被写盘成 {})。

        SettingsDialog 持有的是宿主那个 cfg 对象本身,它的 _save() 会把
        on_save(cfg) 原样传回;宿主若照着做 cfg.clear() + update(同一个
        对象) 就会把配置清空并落盘。历史上这个路径零测试。
        """
        cfg = self._cfg()
        cfg["refresh_interval_sec"] = 60
        cfg["alert"] = {"warn_pct": 30, "critical_amount_yuan": 5.0}
        actions = self._actions(cfg)
        dlg = self._open(actions)
        dlg._save()
        self.assertEqual(len(cfg.get("providers") or []), 1,
                         "保存设置后 providers 不得被清空")
        self.assertEqual(cfg["providers"][0]["name"], "DeepSeek")
        self.assertEqual(cfg["providers"][0]["key"], "k1")
        self.assertEqual(cfg["refresh_interval_sec"], 60)
        self.assertIn("ui", cfg)

    def test_save_writes_config_to_disk(self):
        """保存设置后磁盘上仍有 providers,而不是被空模板覆盖。"""
        import config as config_mod
        import json
        cfg = self._cfg()
        actions = self._actions(cfg)
        dlg = self._open(actions)
        dlg._save()
        self.assertTrue(config_mod.CONFIG_PATH.exists())
        disk = json.loads(config_mod.CONFIG_PATH.read_text(encoding="utf-8"))
        self.assertEqual(len(disk.get("providers") or []), 1)
        # 磁盘态只有 key_enc,没有明文 key
        self.assertNotIn("key", disk["providers"][0])


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
