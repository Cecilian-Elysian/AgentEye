import copy
import json
import os
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
