"""pytest 共享配置。

两件事:

1. Windows 上同一进程里反复创建/销毁多个 Tk root 时,tk.Tk() 偶发
   TclError("tk wasn't installed properly")。这里给 Tk.__init__ 加
   有限次重试,消掉这种环境级抖动;不改变任何测试语义。

2. 每个测试都跑在独立的临时目录里。config 与 cache 的路径都是**模块级
   全局**,不隔离的话任何调 load_v2() 的测试都会读写真实的
   ~/.agenteye/config.json(包括把用户的 key_enc 解密进内存),文件不存在
   时还会顺手替用户建一个。历史上 test_m6_light_readability 就踩过这个坑。
   AGENTS.md「测试不得读写用户真实配置」靠的就是这个 fixture。
"""

import time
import tkinter as tk

import pytest

import cache as cache_mod
import config as config_mod

_orig_tk_init = tk.Tk.__init__


def _retrying_tk_init(self, *args, **kwargs):
    last_err = None
    for _ in range(5):
        try:
            _orig_tk_init(self, *args, **kwargs)
            return
        except tk.TclError as e:
            last_err = e
            time.sleep(0.2)
    raise last_err


tk.Tk.__init__ = _retrying_tk_init


@pytest.fixture(autouse=True)
def isolated_state_paths(tmp_path, monkeypatch):
    """把 config / cache 的落盘位置重定向到本测试专属的临时目录。"""
    cfg_dir = tmp_path / "agenteye"
    cache_dir = cfg_dir / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(config_mod, "CONFIG_PATH", cfg_dir / "config.json")
    monkeypatch.setattr(cache_mod, "CACHE_DIR", cache_dir)
    monkeypatch.setattr(cache_mod, "MODELS_CACHE", cache_dir / "models.json")
    monkeypatch.setattr(cache_mod, "PROBE_LOG", cache_dir / "probe.jsonl")
    monkeypatch.setattr(cache_mod, "ALERT_STATE",
                        cache_dir / "alert_state.json")
    yield
