"""Search cache middleware for Crawl4AI MCP Server.

Provides LRU + TTL caching for search results to avoid
redundant API calls.
"""

import hashlib
import time as _time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Optional

from .pipeline import Middleware, PipelineContext

# Cache settings
_SEARCH_CACHE_MAX_SIZE = 5
_SEARCH_CACHE_TTL_SECONDS = 3600  # 1 hour


@dataclass
class _CacheEntry:
    """Cache entry with data and timestamp."""
    data: dict
    timestamp: float


class SearchCache:
    """LRU + TTL cache for search results, encapsulated as a class.

    Replaces the previous module-level ``OrderedDict`` so that concurrent
    transports (HTTP) can safely hold their own instance and tests can
    clear state without global side effects.
    """

    def __init__(self, max_size: int = _SEARCH_CACHE_MAX_SIZE,
                 ttl_seconds: float = _SEARCH_CACHE_TTL_SECONDS):
        self._store: OrderedDict[str, _CacheEntry] = OrderedDict()
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds

    def _cleanup_expired(self) -> None:
        now = _time.time()
        expired = [
            key for key, entry in self._store.items()
            if now - entry.timestamp > self.ttl_seconds
        ]
        for key in expired:
            del self._store[key]

    def get(self, cache_key: str) -> Optional[dict]:
        if cache_key in self._store:
            entry = self._store[cache_key]
            if _time.time() - entry.timestamp <= self.ttl_seconds:
                self._store.move_to_end(cache_key)
                return entry.data
            del self._store[cache_key]
        return None

    def put(self, cache_key: str, result: dict) -> None:
        if cache_key in self._store:
            self._store.move_to_end(cache_key)
            self._store[cache_key] = _CacheEntry(data=result, timestamp=_time.time())
        else:
            if len(self._store) >= self.max_size:
                self._cleanup_expired()
                if len(self._store) >= self.max_size:
                    self._store.popitem(last=False)
            self._store[cache_key] = _CacheEntry(data=result, timestamp=_time.time())

    def clear(self) -> None:
        self._store.clear()

    def __len__(self) -> int:
        return len(self._store)


# Module-level cache instance — maintains the same public API surface.
_search_cache = SearchCache()


class SearchCacheMiddleware(Middleware):
    """LRU + TTL cache for search results.

    On before(): checks cache and returns cached result if available.
    On after(): stores the result in cache.
    """

    async def before(self, ctx: PipelineContext) -> Optional[dict]:
        request = ctx.params.get('request', {})
        if not request:
            return None

        cache_key = _get_search_cache_key(request)
        ctx.metadata['cache_key'] = cache_key

        cached = _search_cache.get(cache_key)
        if cached is not None:
            result = cached.copy()
            result['cache_hit'] = True
            return result

        return None

    async def after(self, ctx: PipelineContext) -> None:
        if not isinstance(ctx.result, dict):
            return
        if ctx.result.get('cache_hit'):
            return

        cache_key = ctx.metadata.get('cache_key')
        if cache_key and ctx.result.get('success', True):
            _search_cache.put(cache_key, ctx.result)


def _get_search_cache_key(request: dict) -> str:
    """Generate cache key for search query including all relevant parameters.

    Normalizes defaults to match actual search behavior and avoid cache misses.
    """
    # Normalize num_results (clamp to valid range 1-100, default 10)
    num_results = request.get('num_results', 10)
    if num_results is None:
        num_results = 10
    num_results = max(1, min(100, int(num_results)))

    # Normalize language (default 'en')
    language = request.get('language') or 'en'

    # Normalize region (default 'us')
    region = request.get('region') or 'us'

    # Normalize recent_days (None/0/'' all mean no filter)
    recent_days = request.get('recent_days')
    recent_days_str = str(recent_days) if recent_days else ''

    # Normalize safe_search (default True)
    safe_search = request.get('safe_search', True)
    if safe_search is None:
        safe_search = True

    # Normalize search_genre (None/'' both mean no genre filter)
    search_genre = request.get('search_genre') or ''

    # Build cache key with all parameters that affect search results
    key_parts = [
        request.get('query', ''),
        str(num_results),
        search_genre,
        language,
        region,
        recent_days_str,
        str(safe_search),
    ]
    key_str = ":".join(key_parts)
    return hashlib.md5(key_str.encode()).hexdigest()


def clear_search_cache() -> None:
    """Clear the search result cache. Useful for testing."""
    _search_cache.clear()
