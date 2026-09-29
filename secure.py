"""Windows DPAPI 密钥加解密(ctypes,零第三方依赖)。

用途:把 provider 的 API Key 以 `key_enc` 形式落盘,避免明文躺在
`~/.agenteye/config.json` 里。

契约:
- 内存态:provider["key"] 存明文(见 config._decrypt_providers)
- 磁盘态:provider 只有 `key_enc`,没有 `key`(见 config._encrypt_providers)

非 Windows 或任何一次 API 失败都静默降级:protect/unprotect 返回 None,
调用方回退到明文字段。DPAPI 加密的数据绑定当前 Windows 用户 + 本机,
换机器或换账户无法解密,这是设计使然,不是缺陷。
"""

import base64
import sys

IS_WIN = sys.platform == "win32"

CRYPTPROTECT_UI_FORBIDDEN = 0x1

if IS_WIN:
    import ctypes
    from ctypes import wintypes

    class _DATA_BLOB(ctypes.Structure):
        """DATA_BLOB:长度前缀 + 字节指针。"""
        _fields_ = [("cbData", wintypes.DWORD),
                    ("pbData", ctypes.POINTER(ctypes.c_ubyte))]
else:  # pragma: no cover - 非 Windows 平台
    ctypes = None
    wintypes = None
    _DATA_BLOB = None


def is_available():
    """DPAPI 是否可用(仅 Windows)。"""
    return bool(IS_WIN)


def _load_dlls():
    """返回 (crypt32, kernel32);任一加载失败返回 (None, None)。"""
    if not IS_WIN:
        return None, None
    try:
        crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    except (OSError, AttributeError):
        return None, None

    crypt32.CryptProtectData.argtypes = [
        ctypes.POINTER(_DATA_BLOB),   # pDataIn
        wintypes.LPCWSTR,             # szDataDescr
        ctypes.POINTER(_DATA_BLOB),   # pOptionalEntropy
        ctypes.c_void_p,              # pvReserved
        ctypes.c_void_p,              # pPromptStruct
        wintypes.DWORD,               # dwFlags
        ctypes.POINTER(_DATA_BLOB),   # pDataOut
    ]
    crypt32.CryptProtectData.restype = wintypes.BOOL

    crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(_DATA_BLOB),   # pDataIn
        ctypes.POINTER(wintypes.LPWSTR),  # ppszDataDescr
        ctypes.POINTER(_DATA_BLOB),   # pOptionalEntropy
        ctypes.c_void_p,              # pvReserved
        ctypes.c_void_p,              # pPromptStruct
        wintypes.DWORD,               # dwFlags
        ctypes.POINTER(_DATA_BLOB),   # pDataOut
    ]
    crypt32.CryptUnprotectData.restype = wintypes.BOOL

    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    return crypt32, kernel32


def _to_blob(raw):
    """bytes → (_DATA_BLOB, 持有内存的 buffer)。buffer 必须活到调用结束。"""
    buf = ctypes.create_string_buffer(raw, len(raw))
    blob = _DATA_BLOB()
    blob.cbData = len(raw)
    blob.pbData = ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte))
    return blob, buf


def _from_blob(blob):
    """_DATA_BLOB → bytes,拷贝一份出来。"""
    if not blob.pbData:
        return b""
    return ctypes.string_at(blob.pbData, blob.cbData)


def protect(plain):
    """明文 → base64(DPAPI blob)。失败或输入为空返回 None。"""
    if not IS_WIN or not plain:
        return None
    crypt32, kernel32 = _load_dlls()
    if crypt32 is None:
        return None
    try:
        raw = str(plain).encode("utf-8")
        src, _keep = _to_blob(raw)
        dst = _DATA_BLOB()
        if not crypt32.CryptProtectData(
            ctypes.byref(src), "AgentEye", None, None, None,
            CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(dst),
        ):
            return None
        out = _from_blob(dst)
        kernel32.LocalFree(dst.pbData)
        if not out:
            return None
        return base64.b64encode(out).decode("ascii")
    except Exception:
        return None


def unprotect(encoded):
    """base64(DPAPI blob) → 明文。输入非法或解密失败返回 None。"""
    if not IS_WIN or not encoded:
        return None
    crypt32, kernel32 = _load_dlls()
    if crypt32 is None:
        return None
    try:
        raw = base64.b64decode(str(encoded), validate=True)
    except (ValueError, TypeError):
        return None
    if not raw:
        return None
    try:
        src, _keep = _to_blob(raw)
        dst = _DATA_BLOB()
        descr = wintypes.LPWSTR()
        if not crypt32.CryptUnprotectData(
            ctypes.byref(src), ctypes.byref(descr), None, None, None,
            CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(dst),
        ):
            return None
        out = _from_blob(dst)
        if descr:
            kernel32.LocalFree(descr)
        kernel32.LocalFree(dst.pbData)
        if not out:
            return None
        return out.decode("utf-8")
    except Exception:
        return None
