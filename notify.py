import subprocess
import sys

CREATE_NO_WINDOW = 0x08000000

PS_TEMPLATE = """
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
$t=[Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
$t.GetElementsByTagName('text').Item(0).AppendChild($t.CreateTextNode('{title}'))|Out-Null
$t.GetElementsByTagName('text').Item(1).AppendChild($t.CreateTextNode('{message}'))|Out-Null
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('AgentEye').Show([Windows.UI.Notifications.ToastNotification]::new($t))
"""


def _ps_escape(text):
    return str(text).replace("'", "''")


def send_toast(title, message):
    if sys.platform != "win32":
        return False
    ps = PS_TEMPLATE.format(title=_ps_escape(title), message=_ps_escape(message))
    try:
        subprocess.Popen(
            ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps],
            creationflags=CREATE_NO_WINDOW,
        )
        return True
    except Exception:
        return False


def beep():
    if sys.platform != "win32":
        return False
    try:
        import winsound

        winsound.MessageBeep(winsound.MB_ICONWARNING)
        return True
    except Exception:
        return False


def alert(title, message):
    if not send_toast(title, message):
        beep()
