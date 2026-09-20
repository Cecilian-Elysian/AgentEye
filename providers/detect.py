"""Key 形态识别:根据 API key 前缀 + 可选 base_url 提示推断 provider 类型。"""

import re

KEY_PREFIXES = (
    ("sk-cp-", "minimax", "https://api.minimaxi.com", "high",
     "key 以 'sk-cp-' 开头 → MiniMax Coding Plan"),
    ("ey", "opencode_go", "https://opencode.ai", "medium",
     "key 以 'ey' 开头疑似 JWT → OpenCode Go"),
)

URL_HOST_HINTS = (
    ("deepseek.com", "deepseek", "https://api.deepseek.com",
     "URL 含 'deepseek.com' → DeepSeek 官方"),
    ("bigmodel.cn", "zhipu", "https://open.bigmodel.cn",
     "URL 含 'bigmodel.cn' → 智谱 GLM"),
    ("minimaxi.com", "minimax", "https://api.minimaxi.com",
     "URL 含 'minimaxi.com' → MiniMax"),
    ("minimax.cn", "minimax", "https://api.minimaxi.com",
     "URL 含 'minimax.cn' → MiniMax"),
    ("opencode.ai", "opencode_go", "https://opencode.ai",
     "URL 含 'opencode.ai' → OpenCode Go"),
)


def detect(key="", hint_url=""):
    """根据 key 形态 + 可选 URL 提示推断 provider 类型。

    Returns:
        dict: {kind, base_url, confidence, notes}
        kind ∈ {"minimax", "opencode_go", "deepseek", "zhipu",
                "relay", "generic_openai"}
    """
    key = (key or "").strip()
    hint_url = (hint_url or "").strip().rstrip("/")

    if hint_url:
        host = re.sub(r"https?://", "", hint_url).lower()
        for marker, kind, default_url, note in URL_HOST_HINTS:
            if marker in host:
                return {
                    "kind": kind,
                    "base_url": default_url,
                    "confidence": "high",
                    "notes": note,
                }
        if hint_url.endswith("/v1") or "/v1" in hint_url.split("/")[-1:]:
            return {
                "kind": "generic_openai",
                "base_url": hint_url,
                "confidence": "medium",
                "notes": "URL 含 '/v1' → 通用 OpenAI 兼容",
            }
        return {
            "kind": "generic_openai",
            "base_url": hint_url,
            "confidence": "low",
            "notes": "未识别 URL,按通用 OpenAI 兼容处理",
        }

    if not key:
        return {
            "kind": "generic_openai",
            "base_url": "",
            "confidence": "low",
            "notes": "未提供 key 与 URL,需要更多信息",
        }

    for prefix, kind, default_url, confidence, note in KEY_PREFIXES:
        if key.startswith(prefix):
            return {
                "kind": kind,
                "base_url": default_url,
                "confidence": confidence,
                "notes": note,
            }

    if key.startswith("sk-"):
        return {
            "kind": "generic_openai",
            "base_url": "",
            "confidence": "low",
            "notes": "key 以 'sk-' 开头,疑似 OpenAI 兼容,需要 base_url",
        }

    return {
        "kind": "generic_openai",
        "base_url": "",
        "confidence": "low",
        "notes": f"无法识别 key 形态 (长度 {len(key)}),按通用处理,请提供 base_url",
    }
