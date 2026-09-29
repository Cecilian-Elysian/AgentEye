"""源码风格守卫:见 AGENTS.md「不使用 emoji」与「中文 docstring」。

只扫描运行时源码(ui / providers / 顶层模块),不扫 README、测试与配置,
测试里允许出现 emoji 作为 Unicode 测试样本。
"""
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# U+1F000..U+1FAFF 表情符号区,加常见杂项符号 ⚙ ✅ ❌
EMOJI = re.compile("[\U0001F000-\U0001FAFF⚙✅❌]")

# 允许作为测试样本出现的位置文件名后缀
SAMPLE_SUFFIXES = ("test_secure.py",)

SCANNED = [
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


class TestNoEmojiInSource(unittest.TestCase):

    def test_scanned_files_exist(self):
        for rel in SCANNED:
            self.assertTrue(os.path.isfile(os.path.join(ROOT, rel)),
                            f"{rel} 不存在,SCANNED 列表需同步维护")

    def test_no_emoji_in_runtime_source(self):
        offenders = []
        for rel in SCANNED:
            if rel.endswith(SAMPLE_SUFFIXES):
                continue
            path = os.path.join(ROOT, rel)
            with open(path, encoding="utf-8") as fh:
                for i, line in enumerate(fh, 1):
                    found = EMOJI.findall(line)
                    if found:
                        offenders.append(f"{rel}:{i} {''.join(found)}")
        self.assertEqual(offenders, [], "运行时源码不应含 emoji")

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


if __name__ == "__main__":
    unittest.main()
