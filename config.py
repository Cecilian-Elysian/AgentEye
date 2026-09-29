import copy
import json
import os
import sys
import tempfile
import time
import uuid
from pathlib import Path

CONFIG_PATH = Path.home() / ".agenteye" / "config.json"


class ConfigError(Exception):
    """配置不可用。调用方据此提示用户,不要静默吞掉。"""


class ConfigVersionError(ConfigError):
    """配置的 schema_version 高于本程序支持的版本。"""


class PlaintextKeyError(ConfigError):
    """拒绝把明文 key 写进 config.json。"""


def _encrypt_providers(providers):
    """就地加密:把 providers 里的明文 key 升级为 key_enc(移除 key)。

    仅在**副本**上调用(见 _prepare_for_disk),绝不改写调用方的 cfg。
    明文优先于 key_enc:用户在 DPAPI 解密失败后重输的 key 必须能落盘,
    否则"换机器/换账户"场景下用户无法自救。
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
        if p.get("_key_from_env"):
            # 来自环境变量的密钥不落盘,配置文件里不留副本
            p.pop("key", None)
            p.pop("_key_from_env", None)
            changed = True
            continue
        plain = p.get("key")
        if not plain:
            continue
        enc = secure.protect(plain)
        if not enc:
            # 加密失败:保留明文,由 _prepare_for_disk 的兜底断言拦下
            continue
        p["key_enc"] = enc
        p.pop("key", None)
        changed = True
    return changed


def _decrypt_providers(providers):
    """就地解密:key_enc → 明文 key,并清掉 key_enc。

    只在**内存态** cfg 上调用(见 load_v2),使运行期永远拿到明文。
    解密失败保留原 key_enc,plain_key 仍能再试,用户也可重输 key 覆盖。
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
    """深拷贝 cfg 并加密其中的 key,得到可直接写盘的形态。

    磁盘态契约:provider 只有 key_enc,绝不能残留明文 key。加密不可用或
    失败时宁可拒绝写盘,也不能把明文 sk- 落到用户目录里。
    """
    data = copy.deepcopy(cfg)
    _encrypt_providers(data.get("providers") or [])
    leaked = [p.get("name") or p.get("id") or "?"
              for p in (data.get("providers") or [])
              if isinstance(p, dict) and p.get("key")]
    if leaked:
        raise PlaintextKeyError(
            "拒绝写盘:以下 provider 的 key 未能加密(DPAPI 不可用?)——"
            + ", ".join(str(n) for n in leaked))
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

# 用元组而非 set:set 的迭代顺序随 PYTHONHASHSEED 变化,同一条 v1 配置
# 每次启动可能选中不同的 key 字段,迁移结果不可复现。
V1_ENTRY_KEY_FIELDS = ("api_key", "token", "key")
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
    """原子写入:写唯一临时文件后 os.replace,并 fsync 落盘。

    os.replace 在 NTFS 上对读者是原子的,但不保证数据已落盘;断电/休眠后
    可能得到 0 字节文件,进而被 load_v2 当成损坏配置。所以显式 fsync。
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    # 唯一临时名:两个实例同时保存不会互相截断对方的 tmp
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".",
                               suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
        tmp = None
    finally:
        if tmp is not None and os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass


def save_v2(cfg, retries=3):
    """保存 v2 schema 配置(原子写)。成功返回 True,失败抛 ConfigError。

    只在**深拷贝**上做 DPAPI 加密,调用方手里的 cfg 始终保持明文内存态。
    Windows 上文件被记事本/资源管理器预览/杀软短暂占用时 MoveFileEx 会
    返回 sharing violation,这里重试几次;仍失败则抛错,绝不让调用方
    以为"界面已变所以一定存下来了"。
    """
    data = _prepare_for_disk(cfg)          # PlaintextKeyError 直接冒出去
    last = None
    for attempt in range(retries):
        try:
            atomic_save(CONFIG_PATH, data)
            return True
        except PermissionError as e:       # ERROR_SHARING_VIOLATION / ACCESS_DENIED
            last = e
            if attempt < retries - 1:
                time.sleep(0.15 * (attempt + 1))
        except (OSError, ValueError, TypeError) as e:
            raise ConfigError(f"配置保存失败:{e.__class__.__name__}: {e}")
    raise ConfigError(f"配置保存失败(文件被占用?):{last}")


def clamp_interval_v2(cfg):
    try:
        sec = int(cfg.get("refresh_interval_sec", 30))
    except (TypeError, ValueError):
        sec = 30
    return max(15, min(3600, sec))


def apply_env_v2(cfg):
    """v2 schema 环境变量覆盖。必须在 _decrypt_providers **之后**调用,
    否则磁盘里解出来的 key 会把 env 覆盖回去,环境变量形同虚设。"""
    env_map = ENV_DEFAULTS
    for p in cfg.get("providers") or []:
        kind = p.get("kind")
        env_name = p.get("api_key_env") or env_map.get(kind)
        if env_name and os.environ.get(env_name):
            p["key"] = os.environ[env_name]
            # 标记来源:env 里的密钥不落盘,否则配置文件会多出一份副本
            p["_key_from_env"] = env_name


def merge_v2_defaults(base, user):
    """递归合并 user 到 base(深 merge dict)。"""
    for k, v in (user or {}).items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            merge_v2_defaults(base[k], v)
        else:
            base[k] = v
    return base


def _quarantine_corrupt_config(reason):
    """把损坏的 config.json 改名留证,绝不原地覆盖。"""
    stamp = time.strftime("%Y%m%d-%H%M%S")
    dest = CONFIG_PATH.with_name(f"config.json.corrupt-{stamp}")
    try:
        os.replace(CONFIG_PATH, dest)
        return dest
    except OSError:
        return None


def load_v2():
    """加载 v2 配置。

    三条硬性要求:
    - 文件损坏 ≠ 首次运行。损坏时把原文改名留证并**不写盘**,
      绝不能让 save_v2 用空模板盖掉用户仅有的 provider 与 key。
    - schema_version 高于 2 时抛 ConfigVersionError,不能当 v1 迁移
      (那会把 providers[] 清成空数组再写回)。
    - 迁移前必须先成功备份 v1 原文。
    """
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not CONFIG_PATH.exists():
        # 全新安装:空 providers,面板据此显示"右键 + 添加 Key"空态
        v2 = copy.deepcopy(V2_TEMPLATE)
        save_v2(v2)
        return v2

    try:
        user_cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (ValueError, OSError) as e:
        moved = _quarantine_corrupt_config(str(e))
        sys.stderr.write(
            f"config.json 解析失败({e}),已保留为 {moved or '(重命名失败)'}\n"
            "本次以空配置启动且不会覆盖原文件,请检查后手动恢复。\n")
        return copy.deepcopy(V2_TEMPLATE)

    if not isinstance(user_cfg, dict):
        moved = _quarantine_corrupt_config("根节点不是对象")
        sys.stderr.write(
            f"config.json 根节点不是对象,已保留为 {moved or '(重命名失败)'}\n")
        return copy.deepcopy(V2_TEMPLATE)

    version = user_cfg.get("schema_version")
    if version == 2:
        merged = merge_v2_defaults(copy.deepcopy(V2_TEMPLATE), user_cfg)
        # 顺序要紧:先解密成明文,再让环境变量覆盖,否则 env 永远不生效
        _decrypt_providers(merged.get("providers") or [])
        apply_env_v2(merged)
        return merged

    if isinstance(version, int) and not isinstance(version, bool) and version > 2:
        raise ConfigVersionError(
            f"配置版本 schema_version={version} 高于本程序支持的 2。"
            "请升级 AgentEye,或手动改回 2。")

    # 只有缺版本号 / 1 才走 v1 迁移
    backup = CONFIG_PATH.with_suffix(".v1.bak")
    if not backup.exists():
        try:
            atomic_save(backup, user_cfg)
        except OSError as e:
            raise ConfigError(
                f"无法备份 v1 配置({e}),已中止迁移以免密钥丢失") from e
    migrated = migrate_v1_to_v2(user_cfg)
    _decrypt_providers(migrated.get("providers") or [])
    apply_env_v2(migrated)
    save_v2(migrated)
    return migrated
