"""Windows toast 通知。

- 锁死 C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe
  (避免 PATH 中 pwsh/PowerShell Core 加载 WinRT 类型失败)
- 失败回退到 winsound.MessageBeep
- alert_many 合并同一 tick 内的多条告警
"""

import os
import subprocess
import sys
import threading
import time

CREATE_NO_WINDOW = 0x08000000

PS_EXE = os.path.join(
    os.environ.get("SystemRoot", r"C:\Windows"),
    "System32", "WindowsPowerShell", "v1.0", "powershell.exe")

PS_TEMPLATE = """
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
$t=[Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
$t.GetElementsByTagName('text').Item(0).AppendChild($t.CreateTextNode('{title}'))|Out-Null
$t.GetElementsByTagName('text').Item(1).AppendChild($t.CreateTextNode('{message}'))|Out-Null
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('AgentEye').Show([Windows.UI.Notifications.ToastNotification]::new($t))
"""

_last_beep = 0.0
_beep_lock = threading.Lock()
_proc_counter = 0
_proc_lock = threading.Lock()


def _ps_escape(text):
    return str(text).replace("'", "''")


def _too_many_procs():
    global _proc_counter
    with _proc_lock:
        if _proc_counter >= 5:
            return True
        _proc_counter += 1
    return False


def _decrement_proc():
    global _proc_counter
    with _proc_lock:
        _proc_counter = max(0, _proc_counter - 1)


def send_toast(title, message):
    if sys.platform != "win32":
        return False
    if not os.path.exists(PS_EXE):
        return False
    if _too_many_procs():
        return False
    ps = PS_TEMPLATE.format(title=_ps_escape(title), message=_ps_escape(message))
    try:
        subprocess.Popen(
            [PS_EXE, "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps],
            creationflags=CREATE_NO_WINDOW,
        )
        def _release():
            time.sleep(5)
            _decrement_proc()
        threading.Thread(target=_release, daemon=True).start()
        return True
    except Exception:
        _decrement_proc()
        return False


def beep():
    global _last_beep
    if sys.platform != "win32":
        return False
    with _beep_lock:
        if time.time() - _last_beep < 1.0:
            return False
        _last_beep = time.time()
    try:
        import winsound
        winsound.MessageBeep(winsound.MB_ICONWARNING)
        return True
    except Exception:
        return False


def alert(title, message):
    if not send_toast(title, message):
        beep()


def alert_many(items, group_title="AgentEye"):
    """合并多条告警为一条 toast。items: [(name, verb), ...]"""
    if not items:
        return
    if len(items) == 1:
        name, verb = items[0]
        alert(f"{group_title} · {name}", verb)
        return
    critical_count = sum(1 for _, v in items if "告急" in v)
    warn_count = len(items) - critical_count
    parts = []
    if critical_count:
        parts.append(f"{critical_count} 项额度告急")
    if warn_count:
        parts.append(f"{warn_count} 项额度偏低")
    summary = " · ".join(parts)
    detail = "、".join(name for name, _ in items[:5])
    if len(items) > 5:
        detail += f" 等 {len(items)} 项"
    alert(f"{group_title} · {summary}", detail)
