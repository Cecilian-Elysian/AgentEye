"""缓存层:模型列表 (TTL 6h) + 试调日志 (append-only JSONL)。

所有缓存文件位于 ~/.agenteye/cache/,与 config.json 平级但独立。
"""

import hashlib
import json
import os
import time
from pathlib import Path

CACHE_DIR = Path.home() / ".agenteye" / "cache"
MODELS_CACHE = CACHE_DIR / "models.json"
PROBE_LOG = CACHE_DIR / "probe.jsonl"

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
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}


def _save_json(path, data):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def get_models(base_url, api_key, ttl=None):
    _ensure()
    ttl = ttl if ttl is not None else DEFAULT_TTL["models"]
    cache = _load_json(MODELS_CACHE)
    entry = cache.get(_hash(base_url, api_key))
    if not entry:
        return None
    if time.time() - entry.get("fetched_at", 0) > ttl:
        return None
    models = entry.get("models") or []
    order = entry.get("order") or []
    if order:
        present = [m for m in models if m in order]
        present_set = set(present)
        extras = [m for m in models if m not in present_set]
        ordered = [m for m in order if m in present_set] + extras
        return ordered
    return models


def set_models(base_url, api_key, models):
    _ensure()
    cache = _load_json(MODELS_CACHE)
    cache[_hash(base_url, api_key)] = {
        "models": models,
        "fetched_at": time.time(),
    }
    _save_json(MODELS_CACHE, cache)


def save_model_order(base_url, api_key, order):
    """仅持久化排序,不更新 models 列表。"""
    _ensure()
    cache = _load_json(MODELS_CACHE)
    key = _hash(base_url, api_key)
    entry = cache.get(key) or {"models": [], "fetched_at": time.time()}
    entry["order"] = list(order)
    entry["fetched_at"] = time.time()
    cache[key] = entry
    _save_json(MODELS_CACHE, cache)
    # Prune order to only models that still exist
    models = entry.get("models") or []
    if models:
        pruned = [m for m in order if m in models]
        if pruned != order:
            entry["order"] = pruned
            cache[key] = entry
            _save_json(MODELS_CACHE, cache)


def invalidate_models(base_url=None, api_key=None):
    _ensure()
    if base_url is None and api_key is None:
        if MODELS_CACHE.exists():
            MODELS_CACHE.unlink()
        return
    cache = _load_json(MODELS_CACHE)
    key = _hash(base_url or "", api_key or "")
    cache.pop(key, None)
    _save_json(MODELS_CACHE, cache)


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
