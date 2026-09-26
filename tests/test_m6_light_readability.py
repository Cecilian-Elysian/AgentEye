"""Light theme readability + 标题栏布局 (黄绿红 + 标题加权补偿) 回归测试。"""
import unittest
import tkinter as tk

from ui.theme import (
    set_theme, current_palette, PALETTE, to_tk_color, to_tk_color_blended,
)
from ui.app import MacWindow, TrafficLight
from ui.essential_bar import EssentialBar
import config as config_mod


def _make_root():
    root = tk.Tk()
    root.geometry("360x400+200+200")
    return root


def _hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


class TestLightThemeReadability(unittest.TestCase):

    def setUp(self):
        self.root = _make_root()

    def tearDown(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def _build_mac(self, actions=None):
        cfg = config_mod.load_v2()
        return MacWindow(self.root, cfg, actions or {})

    def test_text_tk_module_globals_refresh_on_set_theme(self):
        """TEXT_TK / TEXT_DIM_TK 模块常量必须在 set_theme 之后立即更新。"""
        import ui.theme as t
        t.set_theme("dark", broadcast=False)
        self.assertEqual(t.TEXT_TK, "#FFFFFF")
        t.set_theme("light", broadcast=False)
        self.assertEqual(t.TEXT_TK, "#000000")

    def test_to_tk_color_blended_dim_has_visible_contrast(self):
        """to_tk_color_blended 把 alpha 预混合到 BG 上,产出 6 位色仍
        与 BG 形成足够对比度 (差值 > 60)。"""
        for theme in ("dark", "light"):
            with self.subTest(theme=theme):
                set_theme(theme, broadcast=False)
                dim = to_tk_color_blended(PALETTE.TEXT_DIM)
                bg = to_tk_color(PALETTE.BG)
                dr, dg, db = _hex_to_rgb(dim)
                br, bg_, bb = _hex_to_rgb(bg)
                max_diff = max(abs(dr - br), abs(dg - bg_), abs(db - bb))
                self.assertGreater(max_diff, 60,
                                   f"theme={theme} DIM={dim} BG={bg} 对比度太低")

    def test_mac_header_title_visible_in_light_theme(self):
        set_theme("dark", broadcast=False)
        mac = self._build_mac()
        mac.apply_theme("light", broadcast=True)
        title = mac.header.title_lbl
        self.assertEqual(title.cget("fg").lower(), "#000000")
        self.assertEqual(title.cget("bg").lower(), "#f5f5f7")

    def test_essential_bar_sub_label_contrasts_in_light(self):
        set_theme("dark", broadcast=False)
        bar = EssentialBar(
            self.root, type("S", (), {"paused": False, "fetching": False,
                                       "next_fetch": None, "results": []})(),
            {}, {"ui": ("Segoe UI", 10), "mono": ("Consolas", 11),
                  "title": ("Segoe UI", 11, "bold")},
        )
        set_theme("light", broadcast=True)
        fg = bar.sub_lbl.cget("fg").lower()
        bg = bar.frame.cget("bg").lower()
        self.assertNotEqual(fg, bg, f"sub_lbl fg={fg} 与 bg={bg} 相同 → 不可见")
        self.assertNotEqual(fg, "#ffffff", "sub_lbl 浅色下不应是纯白")

    def test_essential_bar_chevron_contrasts_in_light(self):
        bar = EssentialBar(
            self.root, type("S", (), {"paused": False, "fetching": False,
                                       "next_fetch": None, "results": []})(),
            {}, {"ui": ("Segoe UI", 10), "mono": ("Consolas", 11),
                  "title": ("Segoe UI", 11, "bold")},
        )
        set_theme("light", broadcast=True)
        fg = bar._chevron.cget("fg").lower()
        self.assertNotEqual(fg, "#ffffff", "chevron 浅色下应是 DIM 不是 TEXT")

    def test_apply_theme_dark_then_light_then_dark_returns_to_original(self):
        set_theme("dark", broadcast=False)
        mac = self._build_mac()
        original_fg = mac.header.title_lbl.cget("fg").lower()
        original_bg = mac.header.title_lbl.cget("bg").lower()
        mac.apply_theme("light", broadcast=True)
        self.assertEqual(mac.header.title_lbl.cget("fg").lower(), "#000000")
        mac.apply_theme("dark", broadcast=True)
        self.assertEqual(mac.header.title_lbl.cget("fg").lower(), original_fg)
        self.assertEqual(mac.header.title_lbl.cget("bg").lower(), original_bg)


class TestTrafficLightThemeRefresh(unittest.TestCase):
    """TrafficLight 画布 bg 必须跟主题,修复浅色残留深色方框。"""

    def setUp(self):
        self.root = _make_root()

    def tearDown(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def _mac(self):
        cfg = config_mod.load_v2()
        return MacWindow(self.root, cfg, {})

    def test_traffic_light_canvas_bg_updates_on_theme_switch(self):
        """dark→light 后 3 个 dot 的 Canvas bg 必须变成 palette.BG,
        而不是停留在构造时 frozen 的 dark 值。"""
        set_theme("dark", broadcast=False)
        mac = self._mac()
        mac.apply_theme("light", broadcast=True)
        for dot in (mac.header.yellow_dot, mac.header.settings_dot,
                    mac.header.red_dot):
            bg = dot.cget("bg").lower()
            self.assertEqual(bg, "#f5f5f7",
                             f"{dot._kind} 浅色下 Canvas bg 应 = #f5f5f7,实为 {bg}")

    def test_traffic_light_canvas_bg_round_trip(self):
        """dark→light→dark 来回切换,bg 必须正确回到 dark 值。"""
        set_theme("dark", broadcast=False)
        mac = self._mac()
        for dot in (mac.header.yellow_dot, mac.header.settings_dot,
                    mac.header.red_dot):
            self.assertEqual(dot.cget("bg").lower(), "#1e1e1e")
        mac.apply_theme("light", broadcast=True)
        for dot in (mac.header.yellow_dot, mac.header.settings_dot,
                    mac.header.red_dot):
            self.assertEqual(dot.cget("bg").lower(), "#f5f5f7")
        mac.apply_theme("dark", broadcast=True)
        for dot in (mac.header.yellow_dot, mac.header.settings_dot,
                    mac.header.red_dot):
            self.assertEqual(dot.cget("bg").lower(), "#1e1e1e")

    def test_traffic_light_constructs_with_header_dot_flag(self):
        """新 TrafficLight 必须设 _is_header_dot = True,防止点击触发 drag。"""
        set_theme("dark", broadcast=False)
        mac = self._mac()
        for dot in (mac.header.yellow_dot, mac.header.settings_dot,
                    mac.header.red_dot):
            self.assertTrue(getattr(dot, "_is_header_dot", False),
                            f"{dot._kind} 缺少 _is_header_dot 标志")

    def test_traffic_light_no_glyph_item(self):
        """TrafficLight 不再创建 text canvas item,只有 oval 圆点。"""
        set_theme("dark", broadcast=False)
        mac = self._mac()
        for dot in (mac.header.yellow_dot, mac.header.settings_dot,
                    mac.header.red_dot):
            types = [dot.type(i) for i in dot.find_all()]
            self.assertNotIn("text", types,
                             f"{dot._kind} 不应有 text item,实有 {types}")
            self.assertIn("oval", types,
                          f"{dot._kind} 应保留 oval 圆点")
        # 也没有 _glyph 属性了
        for dot in (mac.header.yellow_dot, mac.header.settings_dot,
                    mac.header.red_dot):
            self.assertFalse(hasattr(dot, "_glyph"),
                             f"{dot._kind} 不应再有 _glyph 属性")

    def test_traffic_light_hover_event_does_nothing_visible(self):
        """Enter/Leave 事件触发后,canvas item 列表不变(无 glyph 出现/消失)。"""
        set_theme("dark", broadcast=False)
        mac = self._mac()
        for dot in (mac.header.yellow_dot, mac.header.settings_dot,
                    mac.header.red_dot):
            before = dot.find_all()
            dot.event_generate("<Enter>")
            self.root.update()
            after_enter = dot.find_all()
            dot.event_generate("<Leave>")
            self.root.update()
            after_leave = dot.find_all()
            self.assertEqual(len(before), len(after_enter),
                             f"{dot._kind} hover 不应新增 item")
            self.assertEqual(len(before), len(after_leave),
                             f"{dot._kind} leave 不应改变 item 数")


class TestMacHeaderLayout(unittest.TestCase):
    """MacHeader 标题栏新布局:无 left,右集群 [黄绿红],标题加权补偿。"""

    def setUp(self):
        self.root = _make_root()

    def tearDown(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def _mac(self, actions=None):
        cfg = config_mod.load_v2()
        return MacWindow(self.root, cfg, actions or {})

    def test_no_left_frame_only_right_cluster(self):
        """MacHeader 不再有 'left' Frame,右集群里正好 3 个 TrafficLight。"""
        set_theme("dark", broadcast=False)
        mac = self._mac()
        children = mac.header.winfo_children()
        # children = [right Frame, title_lbl Label] — 没有 left
        frames = [c for c in children if c.winfo_class() == "Frame"]
        self.assertEqual(len(frames), 1, f"应只有 1 个 Frame,实为 {len(frames)}")
        right = frames[0]
        # 验证右集群里正好有 3 个 TrafficLight
        dots = [c for c in right.winfo_children() if isinstance(c, TrafficLight)]
        self.assertEqual(len(dots), 3, f"右集群应有 3 个 dot,实为 {len(dots)}")

    def test_right_cluster_order_yellow_green_red(self):
        """右集群从左到右是黄(最小化) → 绿(设置) → 红(退出)。"""
        set_theme("dark", broadcast=False)
        mac = self._mac()
        self.root.update_idletasks()
        frames = [c for c in mac.header.winfo_children() if c.winfo_class() == "Frame"]
        right = frames[0]
        dots = [c for c in right.winfo_children() if isinstance(c, TrafficLight)]
        # 按 winfo_x 升序排 → 视觉从左到右
        dots.sort(key=lambda d: d.winfo_x())
        kinds = [d._kind for d in dots]
        self.assertEqual(kinds, ["minimize", "settings", "close"],
                         f"右集群从左到右应为 [minimize, settings, close],实为 {kinds}")

    def test_no_standalone_settings_text_button(self):
        """不再有独立 ⚙ 文本按钮,只有 3 个 traffic light dot。"""
        set_theme("dark", broadcast=False)
        mac = self._mac()
        self.assertFalse(hasattr(mac.header, "settings_btn"),
                         "MacHeader 已不应再有 settings_btn 文本按钮")
        self.assertTrue(hasattr(mac.header, "settings_dot"),
                        "MacHeader 应该有 settings_dot 交通灯")
        self.assertTrue(hasattr(mac.header, "yellow_dot"))
        self.assertTrue(hasattr(mac.header, "red_dot"))

    def test_yellow_dot_triggers_minimize(self):
        set_theme("dark", broadcast=False)
        fired = []
        mac = self._mac(actions={"minimize": lambda: fired.append("min")})
        # 验证 bind 确实指向 minimize 命令 + 直接调 _on_click
        self.assertIs(mac.header.yellow_dot._command, mac.actions["minimize"])
        mac.header.yellow_dot._on_click()
        self.assertEqual(fired, ["min"])

    def test_settings_dot_triggers_open_settings(self):
        set_theme("dark", broadcast=False)
        fired = []
        mac = self._mac(actions={"open_settings": lambda: fired.append("set")})
        self.assertIs(mac.header.settings_dot._command,
                      mac.actions["open_settings"])
        mac.header.settings_dot._on_click()
        self.assertEqual(fired, ["set"])

    def test_red_dot_triggers_quit(self):
        set_theme("dark", broadcast=False)
        fired = []
        mac = self._mac(actions={"quit": lambda: fired.append("quit")})
        self.assertIs(mac.header.red_dot._command, mac.actions["quit"])
        mac.header.red_dot._on_click()
        self.assertEqual(fired, ["quit"])

    def test_title_position_compensated_for_right_cluster(self):
        """标题 relx 必须偏向左侧,以补偿右集群占用的右侧空间。"""
        set_theme("dark", broadcast=False)
        mac = self._mac()
        self.root.update_idletasks()
        mac.header.update_idletasks()
        right_x = mac.header.winfo_children()[0].winfo_x()
        header_w = mac.header.winfo_width()
        place_info = mac.header.title_lbl.place_info()
        relx = float(place_info.get("relx", "0"))
        # 期望:标题放在"左半区"中点 = right_x/2 / header_w
        expected_relx = (right_x / 2) / max(header_w, 1)
        self.assertAlmostEqual(relx, expected_relx, places=2,
                               msg=f"title relx={relx} 应 ≈ {expected_relx}")

    def test_clicking_traffic_light_does_not_start_drag(self):
        """点交通灯不应启动 drag(_is_header_dot 标记被 drag 检查识别)。"""
        set_theme("dark", broadcast=False)
        mac = self._mac()
        # 模拟 drag_start 触发的判定
        dot = mac.header.settings_dot
        self.assertFalse(mac._is_window_drag_target(dot))


class TestPanelRightClickMenu(unittest.TestCase):
    """Panel 右击菜单必须有 '切换为单行模式' 入口(补偿失去的绿点 toggle)。"""

    def test_panel_menu_has_toggle_mode_entry(self):
        import ui.panel as panel_mod
        src = open(panel_mod.__file__, encoding="utf-8").read()
        self.assertIn("切换为单行模式", src,
                      "panel._build_menu 必须有 '切换为单行模式' 项")
        self.assertIn("toggle_mode", src,
                      "panel._build_menu 必须引用 actions['toggle_mode']")


class TestSettingsDialogNonModal(unittest.TestCase):
    """SettingsDialog 必须非模态,不能 grab_set,主窗口拖动才不会被吞。"""

    def setUp(self):
        self.root = tk.Tk()
        self.root.geometry("360x400+200+200")

    def tearDown(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def test_settings_dialog_does_not_grab(self):
        """打开设置后,主窗口不应被 dialog grab,grab_current() 应为 None。"""
        set_theme("dark", broadcast=False)
        cfg = config_mod.load_v2()
        MacWindow(self.root, cfg, {})
        from ui.settings_dialog import SettingsDialog
        dlg = SettingsDialog(self.root, cfg)
        try:
            # grab_current() 返回当前持有 grab 的 widget;None = 没有 grab
            self.assertIsNone(self.root.grab_current(),
                              "SettingsDialog 不应 grab_set,会阻塞主面板拖动")
        finally:
            try:
                dlg.destroy()
            except tk.TclError:
                pass

    def test_settings_dialog_does_not_block_main_header_click(self):
        """打开设置后,主窗口 header 的 <Button-1> 仍能触发 drag_start 回调。"""
        set_theme("dark", broadcast=False)
        cfg = config_mod.load_v2()
        mac = MacWindow(self.root, cfg, {})
        # 在 MacHeader 创建后追加一个观察者 bind,这样不依赖 mac._drag_start
        # 的具体引用;只要 event 触发就说明没被 grab 阻塞
        drag_called = []
        mac.header.bind("<Button-1>",
                        lambda e: drag_called.append(e.widget), add="+")
        from ui.settings_dialog import SettingsDialog
        dlg = SettingsDialog(self.root, cfg)
        try:
            mac.header.event_generate("<Button-1>", x=180, y=18)
            self.root.update()
            self.assertGreater(len(drag_called), 0,
                               "设置打开时主窗口 header click 应仍能触发")
            self.assertIs(drag_called[0], mac.header,
                          "event.widget 应是主窗口 header")
        finally:
            try:
                dlg.destroy()
            except tk.TclError:
                pass


if __name__ == "__main__":
    unittest.main()