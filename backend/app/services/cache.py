"""LLM 结果缓存：对完全相同的问题缓存答案，加速重复提问、降低 API 成本。"""
import threading
import time

_TTL = 3600  # 缓存有效期（秒）
_MAX_SIZE = 1000

_cache: dict[str, tuple[float, dict]] = {}
_lock = threading.Lock()


def get(key: str):
    with _lock:
        item = _cache.get(key)
        if item is None:
            return None
        if time.time() - item[0] < _TTL:
            return item[1]
        _cache.pop(key, None)
        return None


def set(key: str, value: dict) -> None:
    with _lock:
        _cache[key] = (time.time(), value)
        # 简单容量控制：超出后淘汰最旧条目
        if len(_cache) > _MAX_SIZE:
            oldest = min(_cache, key=lambda k: _cache[k][0])
            _cache.pop(oldest, None)
