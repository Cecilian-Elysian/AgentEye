using System.Text.Json;
using System.Text.Json.Nodes;

namespace AgentEye.Core.Config;

/// <summary>
/// JSON 工具:解析为 CLR 原生图(int/double/bool/string/Dictionary/List),
/// 与序列化回去。选 CLR 图而不是 JsonNode/JsonElement 贯穿全程,是因为
/// 配置层契约以 Python 版为准——那里 json.loads 出来就是 int/float/dict,
/// 后续所有合并、加密、迁移逻辑都基于这个语义。
/// </summary>
public static class JsonUtil
{
    private static readonly JsonSerializerOptions WriteIndentedOpts = new()
    {
        WriteIndented = true,
        // 等价于 json.dumps(ensure_ascii=False):中文原样输出,不转 \uXXXX
        Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
    };

    private static readonly JsonSerializerOptions WriteCompactOpts = new()
    {
        WriteIndented = false,
        Encoder = WriteIndentedOpts.Encoder,
    };

    /// <summary>解析 JSON 文本;非法输入返回 null(调用方按损坏处理)。</summary>
    public static Dictionary<string, object?>? ParseObject(string text)
    {
        try
        {
            var node = JsonNode.Parse(text);
            if (node is not JsonObject obj) return null;
            return ToClr(obj) as Dictionary<string, object?>;
        }
        catch (JsonException)
        {
            return null;
        }
    }

    /// <summary>序列化为紧凑单行 JSON(用于 DPAPI 加密前的 v1 备份原文)。</summary>
    public static string DumpCompact(Dictionary<string, object?> cfg) =>
        JsonSerializer.Serialize(FromClr(cfg), WriteCompactOpts);

    /// <summary>序列化为 2 空格缩进、无尾换行的格式(与 Python json.dumps(indent=2) 对齐)。</summary>
    public static string Dump(Dictionary<string, object?> cfg) =>
        JsonSerializer.Serialize(FromClr(cfg), WriteIndentedOpts);

    /// <summary>深拷贝(JSON 往返),等价于 Python 的 copy.deepcopy。</summary>
    public static Dictionary<string, object?> DeepClone(Dictionary<string, object?> cfg) =>
        ParseObject(DumpCompact(cfg)) ?? new Dictionary<string, object?>();

    /// <summary>JsonObject → CLR 原生图。</summary>
    private static object? ToClr(JsonNode? node) => node switch
    {
        null => null,
        JsonObject obj => obj.ToDictionary(kv => kv.Key,
            kv => ToClr(kv.Value)),
        JsonArray arr => arr.Select(ToClr).ToList(),
        JsonValue v => v.GetValueKind() switch
        {
            JsonValueKind.True => true,
            JsonValueKind.False => false,
            JsonValueKind.Number => v.TryGetValue<long>(out var l) ? (l is >= int.MinValue and <= int.MaxValue ? (object)(int)l : l) : v.GetValue<double>(),
            JsonValueKind.String => v.GetValue<string>(),
            _ => null,
        },
        _ => null,
    };

    /// <summary>CLR 原生图 → JsonNode(System.Text.Json 只认它)。</summary>
    public static JsonNode? FromClr(object? value) => value switch
    {
        null => null,
        bool b => b,
        int i => i,
        long l => l,
        double d => d,
        float f => f,
        string s => s,
        Dictionary<string, object?> dict => new JsonObject(
            dict.Select(kv => new KeyValuePair<string, JsonNode?>(kv.Key, FromClr(kv.Value)))),
        IDictionary<string, object?> dict => new JsonObject(
            dict.Select(kv => new KeyValuePair<string, JsonNode?>(kv.Key, FromClr(kv.Value)))),
        IEnumerable<object?> list => new JsonArray(
            list.Select(FromClr).ToArray()),
        _ => throw new ArgumentException($"不可序列化的类型:{value.GetType().Name}"),
    };
}
