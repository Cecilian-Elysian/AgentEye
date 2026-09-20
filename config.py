import copy
import json
import os
import uuid
from pathlib import Path

CONFIG_PATH = Path.home() / ".agenteye" / "config.json"

ENV_DEFAULTS = {
    "minimax": "MINIMAX_API_KEY",
    "opencode_go": "OPENCODE_GO_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "zhipu": "ZHIPU_API_KEY",
}

TEMPLATE = {
    "refresh_interval_sec": 300,
    "alert": {
        "enable": True,
        "warn_pct": 30,
        "critical_pct": 10,
        "warn_amount": 10,
        "critical_amount": 3,
        "cooldown_min": 60,
    },
    "ui": {"x": None, "y": None},
    "relay_sites": [
        {
            "name": "元序",
            "base_url": "https://token.yuanxuai.xyz",
            "token": "在这里粘贴中转站的key",
            "email": "站点登录邮箱(管理接口需登录时填)",
            "password": "站点登录密码(不需要登录就删掉这两行)"
        }
    ],
    "minimax": [{"name": "MiniMax", "api_key": "在这里粘贴订阅Key"}],
    "opencode_go": [{"name": "OpenCode Go", "api_key": "在这里粘贴Go的key"}],
    "deepseek": [
        {
            "name": "DeepSeek",
            "api_key": "在这里粘贴DeepSeek的key",
            "warn_amount": 10,
            "critical_amount": 5,
        }
    ],
    "zhipu": [{"name": "智谱 GLM", "api_key": "在这里粘贴智谱的key"}],
}


def load():
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    user_cfg = None
    if CONFIG_PATH.exists():
        try:
            user_cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            user_cfg = None
    else:
        save(TEMPLATE)
    cfg = _merge(copy.deepcopy(TEMPLATE), user_cfg or {})
    _apply_env(cfg)
    return cfg


def save(cfg):
    try:
        CONFIG_PATH.write_text(
            json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError:
        pass


def _merge(base, user):
    for k, v in user.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _merge(base[k], v)
        else:
            base[k] = v
    return base


def _apply_env(cfg):
    for kind, entries in (
        ("relay", cfg.get("relay_sites") or []),
        ("minimax", cfg.get("minimax") or []),
        ("opencode_go", cfg.get("opencode_go") or []),
        ("deepseek", cfg.get("deepseek") or []),
        ("zhipu", cfg.get("zhipu") or []),
    ):
        for entry in entries:
            env_name = entry.get("api_key_env") or ENV_DEFAULTS.get(kind)
            if env_name and os.environ.get(env_name):
                if kind == "relay":
                    entry["token"] = os.environ[env_name]
                else:
                    entry["api_key"] = os.environ[env_name]


def clamp_interval(cfg):
    try:
        sec = int(cfg.get("refresh_interval_sec", 300))
    except (TypeError, ValueError):
        sec = 300
    return max(30, min(3600, sec))


# ============================================================================
# v2 schema (新增,P5 阶段接入主流程;P2 仅作为工具函数 + 测试存在)
# ============================================================================

V2_TEMPLATE = {
    "schema_version": 2,
    "refresh_interval_sec": 30,
    "alert": {
        "enable": True,
        "warn_pct": 30,
        "critical_pct": 10,
        "warn_amount": 10,
        "critical_amount": 3,
        "cooldown_min": 60,
    },
    "aggregate": {
        "enabled": True,
        "monthly_budget_usd": 100.0,
        "currency_rate_cny_per_usd": 7.2,
    },
    "ui": {"x": None, "y": None},
    "providers": [],
}

KIND_FROM_V1_KEY = {
    "relay_sites": "relay",
    "minimax": "minimax",
    "opencode_go": "opencode_go",
    "deepseek": "deepseek",
    "zhipu": "zhipu",
}

DEFAULT_BASE_URLS = {
    "relay": "",
    "minimax": "https://api.minimaxi.com",
    "opencode_go": "https://opencode.ai",
    "deepseek": "https://api.deepseek.com",
    "zhipu": "https://open.bigmodel.cn",
    "generic_openai": "",
}

V1_ENTRY_KEY_FIELDS = {"api_key", "token", "key"}
V1_LIFTED_FIELDS = {"name", "base_url"}
V1_PROVIDER_KEEP_FIELDS = {"warn_amount", "critical_amount", "warn_pct",
                           "critical_pct", "quota_per_usd",
                           "new_api_user_id", "headers"}


def _gen_id():
    return uuid.uuid4().hex[:12]


def migrate_v1_to_v2(v1_cfg):
    """将 v1 schema (5 个分立数组) 转换为 v2 (统一 providers[])。"""
    if not isinstance(v1_cfg, dict):
        return copy.deepcopy(V2_TEMPLATE)

    v2 = copy.deepcopy(V2_TEMPLATE)
    v2["refresh_interval_sec"] = v1_cfg.get("refresh_interval_sec",
                                            V2_TEMPLATE["refresh_interval_sec"])
    if isinstance(v1_cfg.get("alert"), dict):
        v2["alert"].update(v1_cfg["alert"])
    if isinstance(v1_cfg.get("ui"), dict):
        v2["ui"] = v1_cfg["ui"]

    providers = []
    for v1_key, kind in KIND_FROM_V1_KEY.items():
        for entry in v1_cfg.get(v1_key) or []:
            if not isinstance(entry, dict):
                continue
            key = ""
            for f in V1_ENTRY_KEY_FIELDS:
                if entry.get(f):
                    key = entry[f]
                    break
            base_url = entry.get("base_url") or DEFAULT_BASE_URLS.get(kind, "")
            extra = {k: v for k, v in entry.items()
                     if k not in V1_ENTRY_KEY_FIELDS
                     and k not in V1_LIFTED_FIELDS
                     and k not in V1_PROVIDER_KEEP_FIELDS}
            provider = {
                "id": _gen_id(),
                "kind": kind,
                "name": entry.get("name") or f"{kind}-{len(providers) + 1}",
                "key": key,
                "base_url": base_url,
                "extra": extra,
            }
            for k in V1_PROVIDER_KEEP_FIELDS:
                if k in entry:
                    provider[k] = entry[k]
            providers.append(provider)

    v2["providers"] = providers
    return v2


def atomic_save(path, data):
    """原子写入:写 .tmp 后 os.replace,避免中途崩溃损坏文件。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def save_v2(cfg):
    """保存 v2 schema 配置(原子写)。"""
    try:
        atomic_save(CONFIG_PATH, cfg)
    except OSError:
        pass


def clamp_interval_v2(cfg):
    try:
        sec = int(cfg.get("refresh_interval_sec", 30))
    except (TypeError, ValueError):
        sec = 30
    return max(15, min(3600, sec))


def apply_env_v2(cfg):
    """v2 schema 环境变量覆盖。"""
    env_map = ENV_DEFAULTS
    for p in cfg.get("providers") or []:
        kind = p.get("kind")
        env_name = p.get("api_key_env") or env_map.get(kind)
        if env_name and os.environ.get(env_name):
            p["key"] = os.environ[env_name]


def merge_v2_defaults(base, user):
    """递归合并 user 到 base(深 merge dict)。"""
    for k, v in (user or {}).items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            merge_v2_defaults(base[k], v)
        else:
            base[k] = v
    return base
