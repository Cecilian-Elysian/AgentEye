"""源码风格守卫:见 AGENTS.md「不使用 emoji」与「依赖最小化」。

- 运行时源码(ui / providers / 顶层模块)不得含 emoji
- 测试源码同样扫描,只对 Unicode 测试样本开白名单
- 箭头(→ ←)、≈、✓ ✗ 等排版与文本符号不算 emoji
"""
import os
import re
import sys
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# 扫描区间一律用码点构造,本文件自身才能通过下面这条 emoji 扫描。
EMOJI_RANGES = (
    (0x1F000, 0x1FAFF),   # 表情符号区
    (0x2699, 0x2699),     # 齿轮
    (0x2705, 0x2705),     # 白色勾
    (0x274C, 0x274C),     # 白色叉
)
EMOJI = re.compile("[" + "".join(
    chr(lo) if lo == hi else f"{chr(lo)}-{chr(hi)}"
    for lo, hi in EMOJI_RANGES) + "]")

# 允许含 emoji 的文件:DPAPI 测试需要拿 emoji 当 Unicode 往返样本
EMOJI_SAMPLE_FILES = frozenset({"tests/test_secure.py"})

RUNTIME_SOURCES = [
    "main.py", "config.py", "cache.py", "notify.py", "secure.py",
    "providers/__init__.py", "providers/detect.py", "providers/generic.py",
    "providers/relay.py", "providers/minimax.py",
    "providers/opencode_go.py", "providers/deepseek.py",
    "providers/zhipu.py",
    "ui/__init__.py", "ui/app.py", "ui/panel.py", "ui/essential_bar.py",
    "ui/model_panel.py", "ui/row_menu.py", "ui/settings_dialog.py",
    "ui/add_key.py", "ui/confirm_delete.py", "ui/mac_toplevel.py",
    "ui/theme.py", "ui/fonts.py", "ui/scrollbar_style.py",
    "ui/vibrancy.py",
]

FORBIDDEN_IMPORTS = ("pywin32", "win32api", "win32gui", "pyautogui",
                     "darkdetect")


def _scan(rel_paths, exempt=frozenset()):
    """返回 [(rel, lineno, emoji), ...] 形式的违规清单。"""
    offenders = []
    for rel in rel_paths:
        if rel in exempt:
            continue
        path = os.path.join(ROOT, rel)
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8") as fh:
            for i, line in enumerate(fh, 1):
                found = EMOJI.findall(line)
                if found:
                    offenders.append((rel, i, "".join(found)))
    return offenders


class TestNoEmoji(unittest.TestCase):

    def test_scanned_runtime_files_exist(self):
        missing = [r for r in RUNTIME_SOURCES
                   if not os.path.isfile(os.path.join(ROOT, r))]
        self.assertEqual(missing, [], "RUNTIME_SOURCES 需同步维护")

    def test_no_emoji_in_runtime_source(self):
        offenders = _scan(RUNTIME_SOURCES)
        self.assertEqual(
            [f"{r}:{i} {e}" for r, i, e in offenders], [],
            "运行时源码不应含 emoji")

    def test_no_emoji_in_test_source_except_samples(self):
        tests_dir = os.path.join(ROOT, "tests")
        rels = []
        for name in sorted(os.listdir(tests_dir)):
            if name.startswith("test_") and name.endswith(".py"):
                rels.append(f"tests/{name}")
        self.assertTrue(rels, "tests/ 下应有测试文件")
        offenders = _scan(rels, exempt=EMOJI_SAMPLE_FILES)
        self.assertEqual(
            [f"{r}:{i} {e}" for r, i, e in offenders], [],
            "测试源码也不应含 emoji(Unicode 样本文件除外)")

    def test_exempt_list_actually_contains_emoji(self):
        """白名单不能变成万能豁免:被豁免的文件必须真的需要它。"""
        self.assertIn("tests/test_secure.py", EMOJI_SAMPLE_FILES)
        offenders = _scan(["tests/test_secure.py"], exempt=frozenset())
        self.assertTrue(offenders, "白名单文件里应确实有 emoji 样本")

    def test_panel_row_name_has_no_prefix(self):
        """金额行前缀已移除,行标题直接用 provider 名。"""
        path = os.path.join(ROOT, "ui", "panel.py")
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        self.assertIn('name_lbl = tk.Label(top, text=name,', src)
        self.assertNotIn('text=prefix + name', src)
        self.assertIsNone(EMOJI.search(src))

    def test_estimate_marker_kept(self):
        """_fmt_main 的 ≈ 估算前缀是排版符号,不属于 emoji,必须保留。"""
        path = os.path.join(ROOT, "ui", "panel.py")
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        self.assertIn('prefix = "≈" if result.get("is_estimate")', src)


class TestMinimalDependencies(unittest.TestCase):
    """AGENTS.md:运行时仅依赖 requests,其余一律标准库或自研。"""

    def _runtime_files(self):
        return [r for r in RUNTIME_SOURCES]

    def test_no_undeclared_third_party_imports(self):
        """任何未在 requirements.txt 声明的第三方库都不得出现在运行时源码。"""
        offenders = []
        for rel in self._runtime_files():
            path = os.path.join(ROOT, rel)
            with open(path, encoding="utf-8") as fh:
                for i, line in enumerate(fh, 1):
                    stripped = line.strip()
                    if not stripped.startswith(("import ", "from ")):
                        continue
                    for bad in FORBIDDEN_IMPORTS:
                        if bad in stripped:
                            offenders.append(f"{rel}:{i} {stripped}")
        self.assertEqual(offenders, [], "这些库未在 requirements.txt 声明")

    def test_requirements_txt_declares_only_requests(self):
        path = os.path.join(ROOT, "requirements.txt")
        with open(path, encoding="utf-8") as fh:
            lines = [ln.strip() for ln in fh
                     if ln.strip() and not ln.strip().startswith("#")]
        self.assertEqual(len(lines), 1, f"运行时依赖应只有一条,实际 {lines}")
        self.assertTrue(lines[0].lower().startswith("requests"))


class TestSystemThemeDetection(unittest.TestCase):
    """auto 主题:只走标准库 winreg,任何机器上行为一致。"""

    def test_darkdetect_is_not_used(self):
        from ui import theme
        with open(theme.__file__, encoding="utf-8") as fh:
            src = fh.read()
        self.assertNotIn("darkdetect", src)

    def test_winreg_path_maps_light_theme_value(self):
        """AppsUseLightTheme=1 → light,0 → dark。"""
        import sys
        from ui import theme

        if sys.platform != "win32":
            self.skipTest("仅 Windows 有 winreg 路径")

        import winreg

        for value, expected in ((1, "light"), (0, "dark")):
            with mock.patch.object(winreg, "OpenKey",
                                   return_value=mock.MagicMock()), \
                    mock.patch.object(winreg, "QueryValueEx",
                                      return_value=(value, None)), \
                    mock.patch.object(winreg, "CloseKey"):
                self.assertEqual(theme.detect_system_theme(), expected)

    def test_winreg_key_is_closed(self):
        """OpenKey 之后必须 CloseKey,否则每次探测都漏一个注册表句柄。"""
        import sys
        from ui import theme

        if sys.platform != "win32":
            self.skipTest("仅 Windows 有 winreg 路径")

        import winreg

        handle = mock.MagicMock()
        with mock.patch.object(winreg, "OpenKey", return_value=handle) as op, \
                mock.patch.object(winreg, "QueryValueEx",
                                  return_value=(1, None)), \
                mock.patch.object(winreg, "CloseKey") as cl:
            theme.detect_system_theme()
        op.assert_called_once()
        cl.assert_called_once_with(handle)

    def test_winreg_failure_falls_back_to_dark(self):
        """winreg 不可用(无桌面会话等)时不应抛异常。"""
        from ui import theme
        with mock.patch.object(theme.sys, "platform", "win32"), \
                mock.patch.dict("sys.modules", {"winreg": None}):
            self.assertEqual(theme.detect_system_theme(), "dark")

    def test_non_windows_returns_dark(self):
        from ui import theme
        with mock.patch.object(theme.sys, "platform", "linux"):
            self.assertEqual(theme.detect_system_theme(), "dark")

    def test_returns_valid_choice(self):
        from ui import theme
        self.assertIn(theme.detect_system_theme(), ("dark", "light"))

    def test_set_theme_auto_resolves(self):
        from ui import theme
        try:
            self.assertIn(theme.set_theme("auto", broadcast=False,
                                          persist=False), ("dark", "light"))
        finally:
            theme.set_theme("dark", broadcast=False, persist=False)


if __name__ == "__main__":
    unittest.main()
