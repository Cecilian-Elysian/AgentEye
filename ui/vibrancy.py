"""跨平台窗口修饰:Win11 DWM 圆角 + Acrylic 半透明 + macOS NSVisualEffectView 占位。

设计原则:
- 所有失败都是软失败:任何 ctypes 调用异常都返回 False,不阻塞主流程
- macOS / Linux 路径给真接口的占位,实际 macOS 用户再实现 NSVisualEffectView
- 仅 Windows 平台提供有效实现,默认用 DWM 系统级 Acrylic
"""

import sys


_DWM_WINDOW_CORNER_PREFERENCE = 33
_DWMWCP_DEFAULT = 0
_DWMWCP_DONOTROUND = 1
_DWMWCP_ROUND = 2
_DWMWCP_ROUNDSMALL = 3

_DWMWA_SYSTEMBACKDROP_TYPE = 38
_DWMSBT_AUTO = 0
_DWMSBT_NONE = 1
_DWMSBT_MAINWINDOW = 2
_DWMSBT_TRANSIENTWINDOW = 3
_DWMSBT_TABBEDWINDOW = 4


def is_windows_11_or_later():
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        version = sys.getwindowsversion()
        return version.major >= 10 and version.build >= 22000
    except Exception:
        return False


def apply_windows_rounded_corners(hwnd):
    """Win11:让 DWM 给窗口画圆角。对 overrideredirect 窗口也生效。"""
    if not is_windows_11_or_later():
        return False
    try:
        import ctypes
        from ctypes import wintypes
        dwmapi = ctypes.windll.dwmapi
        preference = ctypes.c_int(_DWMWCP_ROUND)
        dwmapi.DwmSetWindowAttribute(
            wintypes.HWND(hwnd),
            ctypes.c_int(_DWM_WINDOW_CORNER_PREFERENCE),
            ctypes.byref(preference),
            ctypes.sizeof(preference),
        )
        return True
    except Exception:
        return False


def apply_windows_system_backdrop(hwnd, kind="main"):
    """Win11 22H2+:系统级 mica/acrylic 背景。

    kind: 'main' (默认)、'transient' (薄)、'tabbed' (tab 风格)
    失败时返回 False,调用方回退到 wm_attributes('-alpha')。
    """
    if not is_windows_11_or_later():
        return False
    try:
        import ctypes
        from ctypes import wintypes
        dwmapi = ctypes.windll.dwmapi
        mapping = {
            "auto": _DWMSBT_AUTO,
            "none": _DWMSBT_NONE,
            "main": _DWMSBT_MAINWINDOW,
            "transient": _DWMSBT_TRANSIENTWINDOW,
            "tabbed": _DWMSBT_TABBEDWINDOW,
        }
        value = ctypes.c_int(mapping.get(kind, _DWMSBT_MAINWINDOW))
        dwmapi.DwmSetWindowAttribute(
            wintypes.HWND(hwnd),
            ctypes.c_int(_DWMWA_SYSTEMBACKDROP_TYPE),
            ctypes.byref(value),
            ctypes.sizeof(value),
        )
        return True
    except Exception:
        return False


def apply_windows_dark_titlebar(hwnd, dark=True):
    """Win10/11:让标题栏跟随深色。

    对 overrideredirect 窗口标题栏本来就不可见,但仍可调用以保完整。
    """
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        from ctypes import wintypes
        value = ctypes.c_int(1 if dark else 0)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            wintypes.HWND(hwnd),
            20,
            ctypes.byref(value),
            ctypes.sizeof(value),
        )
        return True
    except Exception:
        return False


def apply_windows_layered_alpha(hwnd, alpha_0_255):
    """老 Win10 fallback:用 layered window + alpha 实现半透明。"""
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        from ctypes import wintypes
        WS_EX_LAYERED = 0x00080000
        LWA_ALPHA = 0x00000002
        user32 = ctypes.windll.user32
        GWL_EXSTYLE = -20
        ex_style = user32.GetWindowLongW(wintypes.HWND(hwnd), GWL_EXSTYLE)
        user32.SetWindowLongW(
            wintypes.HWND(hwnd),
            GWL_EXSTYLE,
            ex_style | WS_EX_LAYERED,
        )
        user32.SetLayeredWindowAttributes(
            wintypes.HWND(hwnd),
            wintypes.COLORREF(0),
            ctypes.c_byte(alpha_0_255),
            LWA_ALPHA,
        )
        return True
    except Exception:
        return False


def apply_macos_vibrancy_stub(window):
    """macOS NSVisualEffectView 占位。M1 阶段先 stub,M5 再实现真接入。"""
    return False


def apply_linux_transparency_stub(window):
    """Linux compositor transparency 占位。"""
    return False


def apply_window_chrome(root, dark=True):
    """统一入口:按平台挑合适的窗口修饰。返回 True 表示至少做了一层处理。"""
    applied = False
    if sys.platform == "win32":
        try:
            root.update_idletasks()
            hwnd = int(root.wm_frame(), 16) if False else root.winfo_id()
            try:
                hwnd = int(root.frame(), 16)
            except Exception:
                hwnd = root.winfo_id()
            if is_windows_11_or_later():
                if apply_windows_rounded_corners(hwnd):
                    applied = True
                if apply_windows_system_backdrop(hwnd, kind="main"):
                    applied = True
                if apply_windows_dark_titlebar(hwnd, dark=dark):
                    applied = True
            else:
                alpha = 235 if dark else 245
                if apply_windows_layered_alpha(hwnd, alpha):
                    applied = True
        except Exception:
            pass
    elif sys.platform == "darwin":
        if apply_macos_vibrancy_stub(root):
            applied = True
    else:
        if apply_linux_transparency_stub(root):
            applied = True
    return applied


def get_hwnd(root):
    """获取 Tk 窗口的原生 HWND (Win32)。"""
    try:
        return int(root.frame(), 16)
    except Exception:
        return root.winfo_id()


__all__ = [
    "is_windows_11_or_later",
    "apply_windows_rounded_corners",
    "apply_windows_system_backdrop",
    "apply_windows_dark_titlebar",
    "apply_windows_layered_alpha",
    "apply_window_chrome",
    "get_hwnd",
]
