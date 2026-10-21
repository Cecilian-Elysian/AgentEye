using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Media;

namespace AgentEye.WinUI.Services;

/// <summary>
/// 主题感知的资源查找:普通 Resources.TryGetValue 不会下钻
/// ThemeDictionaries,代码画的部位必须走这里(按元素 ActualTheme 取)。
/// 顺序:主题子字典 → 根字典(等级色等主题无关刷子)→ 兜底。
/// </summary>
public static class AeRes
{
    public static Brush Brush(FrameworkElement el, string key, Brush? fallback = null)
    {
        var root = Application.Current.Resources;
        // x:Key="Light"/"Dark" 装箱形态可能是枚举也可能是字符串,两种都试
        if (root.ThemeDictionaries.TryGetValue(el.ActualTheme, out var themed) &&
            themed is ResourceDictionary td &&
            td.TryGetValue(key, out var tv) && tv is Brush themeBrush)
            return themeBrush;
        if (root.TryGetValue(key, out var v) && v is Brush b)
            return b;
        return fallback ?? new SolidColorBrush(Microsoft.UI.Colors.Gray);
    }

    /// <summary>拿不到返回 null(用于"没有描边"这类合法缺省)。</summary>
    public static Brush? BrushOrNull(FrameworkElement el, string key)
    {
        var root = Application.Current.Resources;
        if (root.ThemeDictionaries.TryGetValue(el.ActualTheme, out var themed) &&
            themed is ResourceDictionary td &&
            td.TryGetValue(key, out var tv) && tv is Brush themeBrush)
            return themeBrush;
        return root.TryGetValue(key, out var v) && v is Brush b ? b : null;
    }
}
