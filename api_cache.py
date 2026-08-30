import time
import functools
import threading
from typing import Any, Callable, Optional, Dict

class APICache:
    """
    Thread-safe, high-performance in-memory TTL cache with namespace partitioning
    and statistical metrics tracking for ESG Stock Prediction API routes and ML services.
    """
    def __init__(self, default_ttl: int = 300, max_size: int = 1000):
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()
        self._default_ttl = default_ttl
        self._max_size = max_size
        self._stats = {
            'hits': 0,
            'misses': 0,
            'sets': 0,
            'evictions': 0
        }

    def _make_key(self, namespace: str, key: str) -> str:
        return f"{namespace}:{key}"

    def get(self, key: str, namespace: str = "default") -> Optional[Any]:
        full_key = self._make_key(namespace, key)
        now = time.time()
        with self._lock:
            if full_key in self._cache:
                entry = self._cache[full_key]
                if now < entry['expires_at']:
                    self._stats['hits'] += 1
                    return entry['data']
                else:
                    # Expired
                    del self._cache[full_key]
                    self._stats['evictions'] += 1
            self._stats['misses'] += 1
            return None

    def set(self, key: str, data: Any, ttl: Optional[int] = None, namespace: str = "default") -> None:
        full_key = self._make_key(namespace, key)
        ttl = ttl if ttl is not None else self._default_ttl
        expires_at = time.time() + ttl

        with self._lock:
            # Enforce max size limit by evicting oldest expired or earliest created entries
            if len(self._cache) >= self._max_size and full_key not in self._cache:
                self._evict_oldest()

            self._cache[full_key] = {
                'data': data,
                'expires_at': expires_at,
                'created_at': time.time(),
                'namespace': namespace,
                'key': key
            }
            self._stats['sets'] += 1

    def delete(self, key: str, namespace: str = "default") -> bool:
        full_key = self._make_key(namespace, key)
        with self._lock:
            if full_key in self._cache:
                del self._cache[full_key]
                return True
            return False

    def clear(self, namespace: Optional[str] = None) -> int:
        with self._lock:
            if namespace is None:
                count = len(self._cache)
                self._cache.clear()
                return count
            else:
                keys_to_del = [k for k, v in self._cache.items() if v.get('namespace') == namespace]
                for k in keys_to_del:
                    del self._cache[k]
                return len(keys_to_del)

    def _evict_oldest(self) -> None:
        now = time.time()
        # First pass: evict all expired entries
        expired_keys = [k for k, v in self._cache.items() if v['expires_at'] <= now]
        if expired_keys:
            for k in expired_keys:
                del self._cache[k]
                self._stats['evictions'] += 1
            return

        # Second pass: evict oldest 10% of entries
        if self._cache:
            sorted_items = sorted(self._cache.items(), key=lambda x: x[1]['created_at'])
            num_to_evict = max(1, len(sorted_items) // 10)
            for k, _ in sorted_items[:num_to_evict]:
                del self._cache[k]
                self._stats['evictions'] += 1

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            total_requests = self._stats['hits'] + self._stats['misses']
            hit_ratio = round((self._stats['hits'] / total_requests * 100), 2) if total_requests > 0 else 0.0
            
            # Count active non-expired keys by namespace
            now = time.time()
            active_by_ns: Dict[str, int] = {}
            active_total = 0
            for item in self._cache.values():
                if item['expires_at'] > now:
                    ns = item['namespace']
                    active_by_ns[ns] = active_by_ns.get(ns, 0) + 1
                    active_total += 1

            return {
                'hits': self._stats['hits'],
                'misses': self._stats['misses'],
                'sets': self._stats['sets'],
                'evictions': self._stats['evictions'],
                'total_requests': total_requests,
                'hit_ratio_pct': hit_ratio,
                'active_cached_items': active_total,
                'items_by_namespace': active_by_ns
            }


# Global singleton cache instance
global_cache = APICache(default_ttl=300, max_size=1500)


def cached_call(ttl: int = 300, namespace: str = "func", key_builder: Optional[Callable[..., str]] = None):
    """
    Decorator for caching function responses (API endpoints or ML inference calls).
    """
    def decorator(fn: Callable):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            if key_builder:
                cache_key = key_builder(*args, **kwargs)
            else:
                # Default key based on function name and serialized arguments
                arg_strs = [str(a) for a in args]
                kwarg_strs = [f"{k}={v}" for k, v in sorted(kwargs.items())]
                cache_key = f"{fn.__name__}:" + ":".join(arg_strs + kwarg_strs)

            cached_val = global_cache.get(cache_key, namespace=namespace)
            if cached_val is not None:
                return cached_val

            result = fn(*args, **kwargs)
            # Only cache valid non-error results
            if result is not None:
                if isinstance(result, dict) and result.get('error'):
                    pass  # Don't cache errors
                else:
                    global_cache.set(cache_key, result, ttl=ttl, namespace=namespace)
            return result
        return wrapper
    return decorator
