import copy
import json
import os
import uuid
from pathlib import Path

CONFIG_PATH = Path.home() / ".agenteye" / "config.json"


def _encrypt_providers(providers):
    """就地加密:把 providers 里的明文 key 升级为 key_enc(移除 key)。

    仅在**副本**上调用(见 _prepare_for_disk),绝不改写调用方的 cfg。
    secure 不可用或 protect 失败时原样保留明文,静默降级。
    """
    try:
        import secure
    except Exception:
        return False
    if not secure.is_available():
        return False
    changed = False
    for p in providers or []:
        if not isinstance(p, dict):
            continue
        if p.get("key_enc"):
            continue
        plain = p.get("key")
        if not plain:
            continue
        enc = secure.protect(plain)
        if not enc:
            continue
        p["key_enc"] = enc
        p.pop("key", None)
        changed = True
    return changed


def _decrypt_providers(providers):
    """就地解密:key_enc → 明文 key,并清掉 key_enc。

    只在**内存态** cfg 上调用(见 load_v2),使运行期永远拿到明文。
    解密失败回退保留原 key_enc,调用方 plain_key 仍能再试。
    """
    changed = False
    for p in providers or []:
        if not isinstance(p, dict) or not p.get("key_enc"):
            continue
        plain = plain_key(p)
        if plain:
            p["key"] = plain
            p.pop("key_enc", None)
            changed = True
    return changed


def _prepare_for_disk(cfg):
    """深拷贝 cfg 并加密其中的 key,得到可直接写盘的形态。"""
    data = copy.deepcopy(cfg)
    _encrypt_providers(data.get("providers") or [])
    return data


def plain_key(provider):
    """provider dict → 明文 key;优先用 key_enc,失败回退 key。"""
    if not isinstance(provider, dict):
        return ""
    enc = provider.get("key_enc")
    if enc:
        try:
            import secure
            decoded = secure.unprotect(enc)
            if decoded is not None:
                return decoded
        except Exception:
            pass
    return provider.get("key") or ""

ENV_DEFAULTS = {
    "minimax": "MINIMAX_API_KEY",
    "opencode_go": "OPENCODE_GO_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "zhipu": "ZHIPU_API_KEY",
}


# ============================================================================
# v2 schema (新增,P5 阶段接入主流程;P2 仅作为工具函数 + 测试存在)
# ============================================================================

V2_TEMPLATE = {
    "schema_version": 2,
    "refresh_interval_sec": 30,
    "alert": {
        "enable": True,
        "warn_pct": 30,
        "critical_amount_yuan": 5.0,
    },
    "ui": {"x": None, "y": None, "width": 360, "height": 360, "order": [], "pinned": True, "mode": "standard", "theme": "auto"},
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
V1_PROVIDER_KEEP_FIELDS = {"quota_per_usd",
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
    """保存 v2 schema 配置(原子写)。

    只在**深拷贝**上做 DPAPI 加密,调用方手里的 cfg 始终保持明文内存态。
    """
    try:
        atomic_save(CONFIG_PATH, _prepare_for_disk(cfg))
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


def load_v2():
    """加载 v2 配置:首次运行写空模板,v1 自动迁移并备份。"""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    user_cfg = None
    if CONFIG_PATH.exists():
        try:
            user_cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            user_cfg = None

    if not user_cfg:
        # 全新安装:空 providers,面板据此显示"右键 + 添加 Key"空态
        v2 = copy.deepcopy(V2_TEMPLATE)
        save_v2(v2)
        return v2

    if user_cfg.get("schema_version") == 2:
        merged = merge_v2_defaults(copy.deepcopy(V2_TEMPLATE), user_cfg)
        apply_env_v2(merged)
        # 内存态归一:key_enc 解成明文 key,调用方一律读 p["key"]
        _decrypt_providers(merged.get("providers") or [])
        return merged

    backup = CONFIG_PATH.with_suffix(".v1.bak")
    try:
        if not backup.exists():
            atomic_save(backup, user_cfg)
    except OSError:
        pass
    migrated = migrate_v1_to_v2(user_cfg)
    _decrypt_providers(migrated.get("providers") or [])
    save_v2(migrated)
    return migrated
