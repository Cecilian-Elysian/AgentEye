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


def normalize_providers(cfg):
    """把 providers 归一成"list[dict]",丢弃并报告非法成员。

    config.json 是允许手改的(菜单里就有"打开配置文件"),所以
    `"providers": [null]`、`["x"]`、甚至 `{}` 都可能出现在磁盘上。
    merge_v2_defaults 是整体赋值,不会纠正形状;下游任何一处
    `p.get("kind")` 都会 AttributeError,表现成"每次启动都崩"。
    """
    raw = cfg.get("providers")
    if raw is None:
        cfg["providers"] = []
        return cfg
    if isinstance(raw, dict):
        raw = [raw]                      # 少写个中括号,当单条处理
    if not isinstance(raw, list):
        sys.stderr.write(
            f"配置里 providers 不是列表(实际 {type(raw).__name__}),已置空\n")
        cfg["providers"] = []
        return cfg
    good, bad = [], 0
    for p in raw:
        if isinstance(p, dict):
            good.append(p)
        else:
            bad += 1
    if bad:
        sys.stderr.write(
            f"配置里 providers 有 {bad} 个非对象条目,已丢弃"
            "(provider 必须是 {...} 对象)\n")
    cfg["providers"] = good
    return cfg


def apply_env_v2(cfg):
    """v2 schema 环境变量覆盖。必须在 _decrypt_providers **之后**调用,
    否则磁盘里解出来的 key 会把 env 覆盖回去,环境变量形同虚设。"""
    env_map = ENV_DEFAULTS
    for p in cfg.get("providers") or []:
        if not isinstance(p, dict):      # 手改配置可能塞进非 dict
            continue
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


V1_BACKUP_MARK = "agenteye.v1.bak"


def _backup_v1_encrypted(user_cfg):
    """迁移前把 v1 原文加密存成 config.json.v1.bak。

    v1 的 key 是明文数组,直接 atomic_save 会在用户目录永久留下
    一份 sk- 明文,且这份备份比迁移后的配置活得更久(用户之后每次
    改配置都不会动它)。所以整个文档走 DPAPI 加密后再落盘。

    DPAPI 不可用时不能退回明文:宁可中止迁移(配置原封不动),
    也不能为了迁移而在磁盘上写出明文密钥。
    """
    backup = CONFIG_PATH.with_suffix(".v1.bak")
    if backup.exists():
        return
    try:
        import secure
    except Exception as e:
        raise ConfigError(f"secure 不可用,已中止 v1 迁移({e})") from e
    if not secure.is_available():
        raise ConfigError(
            "DPAPI 不可用,已中止 v1 迁移:备份会写出明文密钥")
    blob = json.dumps(user_cfg, ensure_ascii=False)
    enc = secure.protect(blob)
    if not enc:
        raise ConfigError("v1 备份加密失败,已中止迁移:不愿写出明文密钥")
    try:
        atomic_save(backup, {V1_BACKUP_MARK: enc})
    except OSError as e:
        raise ConfigError(
            f"无法写入 v1 备份({e}),已中止迁移以免密钥丢失") from e


def restore_v1_backup():
    """读回并解密 config.json.v1.bak(解密失败时抛 ConfigError)。"""
    backup = CONFIG_PATH.with_suffix(".v1.bak")
    if not backup.exists():
        raise ConfigError(f"没有备份文件:{backup}")
    data = json.loads(backup.read_text(encoding="utf-8"))
    enc = data.get(V1_BACKUP_MARK)
    if not enc:
        raise ConfigError(f"{backup} 不是本程序写的加密备份")
    import secure
    raw = secure.unprotect(enc)
    if not raw:
        raise ConfigError(
            f"{backup} 解密失败:DPAPI 绑定当前用户,换账户/换机器无法恢复")
    return json.loads(raw)


READ_RETRIES = 3
READ_RETRY_DELAY = 0.15


def _read_config_text():
    """读配置原文,失败时区分"内容坏了"和"暂时读不到"。

    - OSError(杀软/OneDrive/开了第二个实例/编辑器锁)先重试,仍失败
      抛 ConfigError。**这类情况绝不能当损坏处理**:文件是好的,
      改名留证等于把用户仅有的配置挪走,随后空模板还会覆盖它。
    - 只有 UnicodeDecodeError(字节流坏)才按损坏处理。
    """
    last = None
    for attempt in range(READ_RETRIES):
        try:
            return CONFIG_PATH.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            raise                      # 内容真的坏了,重试无意义
        except OSError as e:
            last = e
            if attempt < READ_RETRIES - 1:
                time.sleep(READ_RETRY_DELAY * (attempt + 1))
    raise ConfigError(
        f"无法读取配置文件 {CONFIG_PATH}({last.__class__.__name__}: {last})。"
        "请关闭正在占用它的程序(记事本/编辑器/另一个 AgentEye 实例)后重试;"
        "为避免覆盖你的配置,本次不做任何写入。")


def load_v2():
    """加载 v2 配置。

    四条硬性要求:
    - 文件损坏 ≠ 首次运行。损坏时把原文改名留证并**不写盘**,
      绝不能让 save_v2 用空模板盖掉用户仅有的 provider 与 key。
    - 读不到(OSError)≠ 损坏。重试后仍读不到就报错退出,不碰磁盘。
    - schema_version 高于 2 时抛 ConfigVersionError,不能当 v1 迁移
      (那会把 providers[] 清成空数组再写回)。
    - 迁移前必须先成功备份 v1 原文,且备份本身是加密的。
    """
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not CONFIG_PATH.exists():
        # 全新安装:空 providers,面板据此显示"右键 + 添加 Key"空态
        v2 = copy.deepcopy(V2_TEMPLATE)
        save_v2(v2)
        return v2

    try:
        user_cfg = json.loads(_read_config_text())
    except ValueError as e:
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
        normalize_providers(merged)
        # 顺序要紧:先解密成明文,再让环境变量覆盖,否则 env 永远不生效
        _decrypt_providers(merged.get("providers") or [])
        apply_env_v2(merged)
        return merged

    if isinstance(version, int) and not isinstance(version, bool) and version > 2:
        raise ConfigVersionError(
            f"配置版本 schema_version={version} 高于本程序支持的 2。"
            "请升级 AgentEye,或手动改回 2。")

    # 只有缺版本号 / 1 才走 v1 迁移
    _backup_v1_encrypted(user_cfg)
    migrated = migrate_v1_to_v2(user_cfg)
    normalize_providers(migrated)
    _decrypt_providers(migrated.get("providers") or [])
    apply_env_v2(migrated)
    save_v2(migrated)
    return migrated
