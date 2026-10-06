"""多显示器工作区查询与窗口磁吸/恢复钳制。

背景:磁吸原先按主屏 winfo_screenwidth/height 钳制,窗口在副屏时
会被强行拽回主屏——左侧/上方副屏拖不进去,右侧/下方副屏跟用户
抢鼠标。启动恢复也不校验屏幕边界,拔掉显示器后窗口彻底失联。
"""
import ctypes
from ctypes import wintypes


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_ulong),
                ("rcMonitor", RECT), ("rcWork", RECT),
                ("dwFlags", ctypes.c_ulong)]


def work_area(x, y, fallback_wh):
    """(x, y) 所在显示器的工作区 (left, top, right, bottom)。

    查询失败(非 Windows / ctypes 异常 / 点落在所有显示器之外)时,
    回退 fallback_wh=(w, h) 描述的主屏矩形,与旧版主屏钳制行为一致。
    """
    fw, fh = fallback_wh
    fallback = (0, 0, int(fw), int(fh))
    try:
        user32 = ctypes.windll.user32
        pt = wintypes.POINT(int(x), int(y))
        # MONITOR_DEFAULTTONULL:点落在所有显示器之外时返回 NULL,
        # 走 fallback(用 NEAREST 的话永远有"最近"显示器,无法识别
        # 显示器被拔掉的场景)
        MONITOR_DEFAULTTONULL = 0
        hmon = user32.MonitorFromPoint(pt, MONITOR_DEFAULTTONULL)
        if not hmon:
            return fallback
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(MONITORINFO)
        if not user32.GetMonitorInfoW(hmon, ctypes.byref(info)):
            return fallback
        rc = info.rcWork
        return (rc.left, rc.top, rc.right, rc.bottom)
    except Exception:
        return fallback


def snap_clamp(x, y, w, h, area, snap):
    """拖动中的窗口吸附到工作区边缘。纯函数,便于单测。"""
    left, top, right, bottom = area
    if x - left < snap:
        x = left
    elif right - x < snap:
        x = right - w
    if y - top < snap:
        y = top
    elif bottom - y < snap:
        y = bottom - h
    return x, y


def restore_position(x, y, w, h, fallback_wh):
    """启动恢复:把保存坐标钳进最近的显示器,显示器拔掉不失联。"""
    area = work_area(int(x) + int(w) // 2, int(y) + int(h) // 2, fallback_wh)
    left, top, right, bottom = area
    nx = min(max(int(x), left), max(left, right - int(w)))
    ny = min(max(int(y), top), max(top, bottom - int(h)))
    return nx, ny
