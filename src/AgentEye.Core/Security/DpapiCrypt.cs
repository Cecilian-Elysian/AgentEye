using System.Security.Cryptography;

namespace AgentEye.Core.Security;

/// <summary>
/// Windows DPAPI 密钥加解密(ProtectedData,CurrentUser 域)。
///
/// 契约(Python 版 secure.py 对齐):
/// - 内存态:provider["key"] 存明文
/// - 磁盘态:provider 只有 base64(DPAPI) 的 key_enc,没有 key
///
/// DPAPI 加密的数据绑定当前 Windows 用户 + 本机,换机器或换账户无法解密,
/// 这是设计使然。加密失败返回 null,调用方按"不可用"降级,绝不写明文。
/// </summary>
public static class DpapiCrypt
{
    /// <summary>DPAPI 是否可用(仅 Windows)。</summary>
    public static bool IsAvailable => OperatingSystem.IsWindows();

    /// <summary>明文 → base64(DPAPI blob)。失败或输入为空返回 null。</summary>
    public static string? Protect(string? plain)
    {
        if (!IsAvailable || string.IsNullOrEmpty(plain)) return null;
        try
        {
            var raw = System.Text.Encoding.UTF8.GetBytes(plain);
            var blob = ProtectedData.Protect(raw, optionalEntropy: null,
                DataProtectionScope.CurrentUser);
            return blob.Length == 0 ? null : Convert.ToBase64String(blob);
        }
        catch (Exception)
        {
            return null;
        }
    }

    /// <summary>base64(DPAPI blob) → 明文。输入非法或解密失败返回 null。</summary>
    public static string? Unprotect(string? encoded)
    {
        if (!IsAvailable || string.IsNullOrEmpty(encoded)) return null;
        try
        {
            var buf = new byte[encoded.Length * 3 / 4 + 3];
            if (!Convert.TryFromBase64String(encoded, buf, out var written))
                return null;
            var raw = new byte[written];
            Convert.TryFromBase64String(encoded, raw, out _);
            var plain = ProtectedData.Unprotect(raw, optionalEntropy: null,
                DataProtectionScope.CurrentUser);
            var text = System.Text.Encoding.UTF8.GetString(plain);
            return text.Length == 0 ? null : text;
        }
        catch (Exception)
        {
            return null;
        }
    }
}
