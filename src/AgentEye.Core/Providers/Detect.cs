using System.Text.RegularExpressions;

namespace AgentEye.Core.Providers;

/// <summary>识别结果:detect(key, hintUrl) 的产出。</summary>
public sealed record DetectOutcome(string Kind, string BaseUrl, string Confidence, string Notes);

/// <summary>
/// Key 形态识别:根据 API key 前缀 + 可选 base_url 提示推断 provider 类型。
/// 端口自 Python 版 detect.py,分支顺序与文案逐条对齐。
/// </summary>
public static partial class Detect
{
    private static readonly (string Prefix, string Kind, string DefaultUrl, string Confidence, string Note)[]
        KeyPrefixes =
        [
            ("sk-cp-", "minimax", "https://api.minimaxi.com", "high",
             "key 以 'sk-cp-' 开头 → MiniMax Coding Plan"),
        ];

    // "ey" 开头的三段式 JWT:MiniMax 的 token_plan 普通 key 和 OpenCode Go
    // 的 key 都是这种形态,光看形状分不出来。
    [GeneratedRegex(@"^ey[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$")]
    private static partial Regex JwtShape();

    private static readonly (string Marker, string Kind, string DefaultUrl, string Note)[]
        UrlHostHints =
        [
            ("deepseek.com", "deepseek", "https://api.deepseek.com", "URL 含 'deepseek.com' → DeepSeek 官方"),
            ("bigmodel.cn", "zhipu", "https://open.bigmodel.cn", "URL 含 'bigmodel.cn' → 智谱 GLM"),
            ("minimaxi.com", "minimax", "https://api.minimaxi.com", "URL 含 'minimaxi.com' → MiniMax"),
            ("minimax.cn", "minimax", "https://api.minimaxi.com", "URL 含 'minimax.cn' → MiniMax"),
            ("opencode.ai", "opencode_go", "https://opencode.ai", "URL 含 'opencode.ai' → OpenCode Go"),
        ];

    public static DetectOutcome Run(string key = "", string hintUrl = "")
    {
        key = (key ?? "").Trim();
        hintUrl = (hintUrl ?? "").Trim().TrimEnd('/');

        if (hintUrl.Length > 0)
        {
            var host = Regex.Replace(hintUrl, @"^https?://", "").ToLowerInvariant();
            foreach (var (marker, kind, defaultUrl, note) in UrlHostHints)
            {
                if (host.Contains(marker, StringComparison.Ordinal))
                    return new DetectOutcome(kind, defaultUrl, "high", note);
            }
            if (hintUrl.EndsWith("/v1", StringComparison.Ordinal))
                return new DetectOutcome("generic_openai", hintUrl, "medium",
                    "URL 含 '/v1' → 通用 OpenAI 兼容");
            return new DetectOutcome("generic_openai", hintUrl, "low",
                "未识别 URL,按通用 OpenAI 兼容处理");
        }

        if (key.Length == 0)
            return new DetectOutcome("generic_openai", "", "low",
                "未提供 key 与 URL,需要更多信息");

        foreach (var (prefix, kind, defaultUrl, confidence, note) in KeyPrefixes)
        {
            if (key.StartsWith(prefix, StringComparison.Ordinal))
                return new DetectOutcome(kind, defaultUrl, confidence, note);
        }

        if (JwtShape().IsMatch(key))
        {
            // 两种 JWT 分不出谁是谁:给 opencode_go 默认 URL 但置信度降为
            // low,让用户核对。
            return new DetectOutcome("opencode_go", "https://opencode.ai", "low",
                "key 是 JWT 形态,可能是 OpenCode Go,也可能是 MiniMax 的 token_plan key;" +
                "填 URL 提示可纠正,新增后请核对");
        }

        if (key.StartsWith("sk-", StringComparison.Ordinal))
            return new DetectOutcome("generic_openai", "", "low",
                "key 以 'sk-' 开头,疑似 OpenAI 兼容,需要 base_url");

        return new DetectOutcome("generic_openai", "", "low",
            $"无法识别 key 形态 (长度 {key.Length}),按通用处理,请提供 base_url");
    }
}
