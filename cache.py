"""缓存层:模型列表 (TTL 6h) + 试调日志 (append-only JSONL)。

所有缓存文件位于 ~/.agenteye/cache/,与 config.json 平级但独立。
"""

import hashlib
import json
import os
import tempfile
import threading
import time
from pathlib import Path

CACHE_DIR = Path.home() / ".agenteye" / "cache"
MODELS_CACHE = CACHE_DIR / "models.json"
PROBE_LOG = CACHE_DIR / "probe.jsonl"
ALERT_STATE = CACHE_DIR / "alert_state.json"

# 读-改-写必须串行。set_models 跑在轮询的 worker 线程里,
# save_model_order / remove_provider_entries 跑在 Tk 主线程里,
# 没有锁时两边的 write_text 会互相截断,os.replace 还会吃掉对方的 tmp,
# 结果是整个 models.json 变成截断的 JSON -> _load_json 返回 {} ->
# 所有 provider 的模型缓存一起消失。
_lock = threading.RLock()

DEFAULT_TTL = {
    "models": 6 * 3600,
}


def _ensure():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _hash(base_url, api_key):
    raw = (base_url.rstrip("/") + "|" + (api_key or "")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def _load_json(path):
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_json(path, data):
    """原子写:唯一临时名 + fsync。

    临时名必须唯一(不能 path.with_suffix('.tmp') 那种固定名):两个写者
    会互相截断同一个 tmp 文件。fsync 是因为 os.replace 在 NTFS 上只保证
    对读者原子,不保证数据已落盘,断电后可能留下 0 字节文件,
    而 _load_json 对 0 字节文件返回 {} = 缓存全清。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, indent=2)
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


def get_models(base_url, api_key, ttl=None):
    _ensure()
    ttl = ttl if ttl is not None else DEFAULT_TTL["models"]
    with _lock:
        cache = _load_json(MODELS_CACHE)
    key = _hash(base_url, api_key)
    entry = cache.get(key)
    # 手改过的 / 被并发写坏的 models.json 里,字段类型不可信
    if not isinstance(entry, dict):
        return None
    fetched = entry.get("fetched_at")
    if not isinstance(fetched, (int, float)) or isinstance(fetched, bool):
        return None
    if time.time() - fetched > ttl:
        return None
    models = entry.get("models")
    if not isinstance(models, list):
        return None
    order = entry.get("order")
    if not isinstance(order, list):
        order = []
    if order:
        present = [m for m in models if m in order]
        present_set = set(present)
        extras = [m for m in models if m not in present_set]
        ordered = [m for m in order if m in present_set] + extras
        return ordered
    return models


def set_models(base_url, api_key, models):
    _ensure()
    key = _hash(base_url, api_key)
    with _lock:
        cache = _load_json(MODELS_CACHE)
        prev = cache.get(key)
        prev = prev if isinstance(prev, dict) else {}
        entry = {
            "models": list(models),
            "fetched_at": time.time(),
        }
        if isinstance(prev.get("order"), list) and prev["order"]:
            entry["order"] = prev["order"]      # 别把用户排好的顺序冲掉
        cache[key] = entry
        _save_json(MODELS_CACHE, cache)


def save_model_order(base_url, api_key, order):
    """仅持久化排序,不更新 models 列表。"""
    _ensure()
    key = _hash(base_url, api_key)
    with _lock:
        cache = _load_json(MODELS_CACHE)
        entry = cache.get(key)
        entry = dict(entry) if isinstance(entry, dict) else {
            "models": [], "fetched_at": time.time()}
        models = entry.get("models")
        models = models if isinstance(models, list) else []
        order = list(order)
        if models:
            order = [m for m in order if m in models]
        entry["order"] = order
        entry.setdefault("models", models)
        entry["fetched_at"] = time.time()
        cache[key] = entry
        _save_json(MODELS_CACHE, cache)


def invalidate_models(base_url=None, api_key=None):
    _ensure()
    with _lock:
        if base_url is None and api_key is None:
            if MODELS_CACHE.exists():
                MODELS_CACHE.unlink()
            return
        cache = _load_json(MODELS_CACHE)
        cache.pop(_hash(base_url or "", api_key or ""), None)
        _save_json(MODELS_CACHE, cache)


PROBE_LOG_MAX_LINES = 2000


def _trim_probe_log():
    """probe.jsonl 只保留最近若干行。

    它是 append-only 且无上限,常驻运行几个月会单调增长;而
    recent_probes 每次都要整份读进内存再反转。超过阈值就从头部裁掉。
    """
    try:
        with _lock:
            if not PROBE_LOG.exists():
                return
            lines = PROBE_LOG.read_text(encoding="utf-8").splitlines()
            if len(lines) <= PROBE_LOG_MAX_LINES:
                return
            keep = lines[-PROBE_LOG_MAX_LINES:]
            _save_text_atomic(PROBE_LOG, "\n".join(keep) + "\n")
    except OSError:
        pass


def _save_text_atomic(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".",
                               suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
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


def log_probe(provider_name, model_id, success, latency_ms, error=""):
    _ensure()
    line = {
        "ts": time.time(),
        "provider": provider_name,
        "model": model_id,
        "success": bool(success),
        "latency_ms": float(latency_ms),
        "error": str(error) if error else "",
    }
    with PROBE_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(line, ensure_ascii=False) + "\n")
    _trim_probe_log()


def save_alert_state(notified):
    """原子保存 per-provider 告警冷却状态,让 60 分钟冷却跨重启生效。

    notified 形如 ``{"DeepSeek": ["critical", 1758000000.0], ...}``。
    内容非法时按空表处理,不阻塞主流程。
    """
    _ensure()
    clean = {}
    if isinstance(notified, dict):
        for name, value in notified.items():
            if not isinstance(name, str) or not isinstance(value, (list, tuple)):
                continue
            if len(value) != 2:
                continue
            level, ts = value
            if level not in ("warn", "critical"):
                continue
            try:
                ts = float(ts)
            except (TypeError, ValueError):
                continue
            # NTP 回拨 / 手改文件都可能给出未来的时间戳。不夹取的话
            # now - ts 是大负数,冷却判定会把这个 provider 静默到天荒地老
            if ts > time.time() + 60:
                continue
            clean[name] = [level, ts]
    with _lock:
        _save_json(ALERT_STATE, {"notified": clean})


def load_alert_state():
    """读取告警冷却状态。缺失、损坏或旧版单 ts 格式一律返回 {}。"""
    _ensure()
    data = _load_json(ALERT_STATE)
    raw = data.get("notified")
    if not isinstance(raw, dict):
        return {}
    out = {}
    for name, value in raw.items():
        if not isinstance(name, str) or not isinstance(value, (list, tuple)):
            continue
        if len(value) != 2 or value[0] not in ("warn", "critical"):
            continue
        try:
            ts = float(value[1])
        except (TypeError, ValueError):
            continue
        if ts > time.time() + 60:
            continue
        out[name] = [value[0], ts]
    return out


def remove_provider_entries(base_url, api_key):
    """从 models.json 删除该 (base_url, key) 的条目(列表 + 排序)。"""
    _ensure()
    cache = _load_json(MODELS_CACHE)
    key = _hash(base_url or "", api_key or "")
    if key in cache:
        cache.pop(key, None)
        _save_json(MODELS_CACHE, cache)
        return True
    return False


def log_provider_deleted(provider_name, base_url=""):
    """probe 日志只追加,不删历史。"""
    _ensure()
    line = {
        "ts": time.time(),
        "event": "provider_deleted",
        "provider": provider_name,
        "base_url": base_url or "",
    }
    with PROBE_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(line, ensure_ascii=False) + "\n")


def recent_probes(provider_name=None, limit=20):
    _ensure()
    if not PROBE_LOG.exists():
        return []
    lines = PROBE_LOG.read_text(encoding="utf-8").strip().splitlines()
    out = []
    for line in reversed(lines):
        if not line:
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if provider_name and entry.get("provider") != provider_name:
            continue
        out.append(entry)
        if len(out) >= limit:
            break
    return out


def last_probe(provider_name, model_id):
    for entry in recent_probes(provider_name, limit=200):
        if entry.get("model") == model_id:
            return entry
    return None
