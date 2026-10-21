using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Media;

namespace AgentEye.WinUI.Services;

/// <summary>
/// 主题感知的资源查找:普通 Resources.TryGetValue 不会下钻
/// ThemeDictionaries,代码画的部位必须走这里(按元素 ActualTheme 取)。
/// 顺序:主题子字典 → 根字典(等级色等主题无关刷子)→ 兜底。
///
/// 坑:App.xaml 里写的是 x:Key="Light"/"Dark"(字符串键),而
/// el.ActualTheme 是 ElementTheme 枚举装箱值——两者互不相等,
/// 只用枚举查会永远查不到、退化成灰色兜底。两种键形都要试。
/// </summary>
public static class AeRes
{
    public static Brush Brush(FrameworkElement el, string key, Brush? fallback = null)
    {
        if (TryTheme(el, key, out var themeBrush)) return themeBrush;
        var root = Application.Current.Resources;
        if (root.TryGetValue(key, out var v) && v is Brush b)
            return b;
        return fallback ?? new SolidColorBrush(Microsoft.UI.Colors.Gray);
    }

    /// <summary>拿不到返回 null(用于"没有描边"这类合法缺省)。</summary>
    public static Brush? BrushOrNull(FrameworkElement el, string key)
    {
        if (TryTheme(el, key, out var themeBrush)) return themeBrush;
        var root = Application.Current.Resources;
        return root.TryGetValue(key, out var v) && v is Brush b ? b : null;
    }

    /// <summary>按元素实际主题下钻 ThemeDictionaries(字符串键 + 枚举键都试)。</summary>
    private static bool TryTheme(FrameworkElement el, string key, out Brush brush)
    {
        brush = null!;
        var root = Application.Current.Resources;
        foreach (var k in ThemeKeys(el))
        {
            if (!root.ThemeDictionaries.TryGetValue(k, out var themed)) continue;
            if (themed is not ResourceDictionary td) continue;
            if (!td.TryGetValue(key, out var tv)) continue;
            if (tv is Brush b) { brush = b; return true; }
        }
        return false;
    }

    /// <summary>候选键:先当前元素主题,再应用级请求主题,最后兜底两套。</summary>
    private static IEnumerable<object> ThemeKeys(FrameworkElement el)
    {
        var app = Application.Current.RequestedTheme;
        var appDark = app == ApplicationTheme.Dark;
        if (el.ActualTheme == ElementTheme.Light)
        {
            yield return "Light";
            yield return ElementTheme.Light;
        }
        else if (el.ActualTheme == ElementTheme.Dark)
        {
            yield return "Dark";
            yield return ElementTheme.Dark;
        }
        else
        {
            // 元素还没 realize:按应用级请求主题推
            yield return appDark ? "Dark" : "Light";
            yield return appDark ? ElementTheme.Dark : ElementTheme.Light;
            yield return "Default";
        }
    }
}
