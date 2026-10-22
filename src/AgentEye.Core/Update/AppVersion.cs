namespace AgentEye.Core.Update;

/// <summary>
/// 应用版本(语义化):去 v 前缀、缺位补 0、+构建元数据忽略、
/// -预发布后缀视为低于同号正式版。
/// </summary>
public sealed record AppVersionInfo(int Major, int Minor, int Patch, string PreRelease)
{
    /// <summary>解析版本串;不是版本格式返回 null。</summary>
    public static AppVersionInfo? Parse(string? raw)
    {
        if (string.IsNullOrWhiteSpace(raw)) return null;
        var s = raw.Trim();
        if (s.Length > 0 && (s[0] == 'v' || s[0] == 'V')) s = s[1..];
        // 构建元数据(2.0.0+abc123)不影响比较
        var plus = s.IndexOf('+');
        if (plus >= 0) s = s[..plus];
        // 预发布后缀
        string pre = "";
        var dash = s.IndexOf('-');
        if (dash >= 0)
        {
            pre = s[(dash + 1)..];
            s = s[..dash];
        }
        var parts = s.Split('.');
        if (parts.Length == 0) return null;
        var nums = new int[3];
        for (var i = 0; i < 3; i++)
        {
            if (i >= parts.Length) break;
            if (!int.TryParse(parts[i], out nums[i])) return null;
            if (nums[i] < 0) return null;
        }
        return new AppVersionInfo(nums[0], nums[1], nums[2], pre);
    }

    /// <summary>与另一版本比较:负=小于,零=相等,正=大于。</summary>
    public int CompareTo(AppVersionInfo other)
    {
        var c = Major.CompareTo(other.Major);
        if (c != 0) return c;
        c = Minor.CompareTo(other.Minor);
        if (c != 0) return c;
        c = Patch.CompareTo(other.Patch);
        if (c != 0) return c;
        // 同号:有预发布后缀的更低(1.2.0-beta < 1.2.0)
        if (PreRelease.Length == 0 && other.PreRelease.Length == 0) return 0;
        if (PreRelease.Length == 0) return 1;
        if (other.PreRelease.Length == 0) return -1;
        return string.CompareOrdinal(PreRelease, other.PreRelease);
    }

    public bool IsNewerThan(AppVersionInfo other) => CompareTo(other) > 0;

    public override string ToString() =>
        PreRelease.Length == 0
            ? $"{Major}.{Minor}.{Patch}"
            : $"{Major}.{Minor}.{Patch}-{PreRelease}";
}
