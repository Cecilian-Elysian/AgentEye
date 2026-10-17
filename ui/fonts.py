"""字体选择。

项目只支持 Windows(AGENTS.md),所以只留 Windows 一条 fallback 链。
UI family 以 Microsoft YaHei UI 打头:它是 Windows 7 起系统自带的中文
UI 字体,中英混排的字宽与基线都比 Segoe UI 稳,而 Segoe UI 里的中文字形
靠 fallback 换字体,同一行里会串成两种字面。原来这条链从 Segoe UI
起头,于是窗口标题是 Segoe 而面板是硬编码的 YaHei,界面上同时存在四套字体。

mono family 保留给纯 ASCII 场景(倒计时、token 数)。
含中文的文本不要走 mono:CJK 字符在等宽字体里没有字形,Tk 会回退到
系统中文字体,中文字宽不等于等宽格宽,同一行右侧会参差。
"""

import platform
import tkinter as tk
import tkinter.font as tkfont


_YAHEI = "Microsoft YaHei UI"
_YAHEI_PLAIN = "Microsoft YaHei"
_SEGOE_VARIABLE = "Segoe UI Variable"
_SEGOE = "Segoe UI"
_NOTO_VARIABLE = "Noto Sans CJK SC Variable Font"
_NOTO = "Noto Sans CJK SC"
_CASCADIA_VARIABLE = "Cascadia Mono Variable"
_CASCADIA = "Cascadia Mono"
_CONSOLAS = "Consolas"


_CHAINS = {
    "Windows": {
        "ui": [_YAHEI, _YAHEI_PLAIN, _SEGOE_VARIABLE, _SEGOE,
               _NOTO_VARIABLE, _NOTO, "Arial"],
        "mono": [_CASCADIA_VARIABLE, _CASCADIA, _CONSOLAS],
    },
}
_DEFAULT = "Windows"


def _chain(kind):
    return _CHAINS.get(platform.system(), _CHAINS[_DEFAULT])[kind]


def _available_families():
    try:
        return set(tkfont.families())
    except Exception:
        return set()


def _pick(chain, available):
    for name in chain:
        if name in available:
            return name
    return None


def pick_ui_family(root=None):
    """返回当前系统可用的 UI 字体 family 字符串;找不到就回退 tk 默认。

    没有 Tk 解释器时(模块导入期调用本函数)字体枚举拿不到,返回链首——
    Microsoft YaHei UI 是 Windows 7 起系统自带字体,是唯一能安全凭空
    断言的名字。返回 nametofont 的 family 在无 root 时会 TclError,
    那个值当字体名传给 widget 是无效的。
    """
    chain = _chain("ui")
    families = _available_families() if root is None else _ensure_families(root)
    name = _pick(chain, families)
    if name:
        return name
    if not families:
        return chain[0]
    try:
        return tkfont.nametofont("TkDefaultFont").actual("family")
    except Exception:
        return chain[0]


def pick_mono_family(root=None):
    """返回等宽 family。同样在无 Tk 时回退链首。"""
    chain = _chain("mono")
    families = _available_families() if root is None else _ensure_families(root)
    name = _pick(chain, families)
    if name:
        return name
    if not families:
        return chain[0]
    try:
        return tkfont.nametofont("TkFixedFont").actual("family")
    except Exception:
        return chain[0]



_FAMILY_CACHE = {}


def _ensure_families(root):
    key = id(root)
    if key in _FAMILY_CACHE:
        return _FAMILY_CACHE[key]
    try:
        root.update_idletasks()
    except Exception:
        pass
    fams = _available_families()
    _FAMILY_CACHE[key] = fams
    return fams


def fonts(root):
    """返回一组 (family, size[, weight]) 元组,绑定到 root 上确保字体可用。

    num / num_small 用 ui family 而不是 mono:折叠条带的主值是「今日 ¥1.50」
    「已用 27%」这类中英混排文本,等宽字体里没有 CJK 字形,Tk 回退到系统中
    文体后中文字宽不等于等宽格宽,同一行右侧会参差。要用 mono 就自己挑
    全 ASCII 的位置(倒计时、token 数)。
    """
    _ensure_families(root)
    ui = pick_ui_family(root)
    mono = pick_mono_family(root)

    from ui.theme import Typography

    return {
        "ui": ui,
        "mono": mono,
        "title": (ui, Typography.TITLE_SIZE, Typography.TITLE_WEIGHT),
        "body": (ui, Typography.BODY_SIZE),
        "num": (ui, Typography.NUM_SIZE),
        "num_small": (ui, Typography.NUM_SMALL_SIZE),
        "detail": (ui, Typography.DETAIL_SIZE),
        "footer": (ui, Typography.FOOTER_SIZE),
        "badge": (ui, Typography.BADGE_SIZE),
    }


def apply_default_font(root, family=None, size=None):
    """把 Tk 的全局默认字体改成与面板一致。

    tk.Menu 与 messagebox 走的是 TkDefaultFont / TkMenuFont,不给 font
    就用 Tk 自带的 Segoe UI 9pt——同一屏里出现第四套字体,而且 9pt 中文
    明显比面板小一档。option_add 改的是 option database,对之后创建的
    控件生效;已存在的控件要自己刷 refresh_palette。
    """
    from ui.theme import Typography

    fam = family or pick_ui_family(root)
    size = size or Typography.BODY_SIZE
    try:
        root.option_add("*Font", (fam, size))
        root.option_add("*Menu*Font", (fam, size))
        root.option_add("*MessageBox*Font", (fam, size))
    except tk.TclError:
        return False
    return True


__all__ = [
    "pick_ui_family", "pick_mono_family", "fonts", "apply_default_font",
]
