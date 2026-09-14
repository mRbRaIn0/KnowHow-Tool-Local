"""Bounded shared text cache; stat signatures keep external edits visible."""
from collections import OrderedDict
from pathlib import Path
from threading import RLock

_LIMIT = 16 * 1024 * 1024
_cache = OrderedDict()
_lock = RLock()
_size = 0


def read_search_text(path: Path) -> tuple[str, str]:
    global _size
    stat = path.stat()
    if stat.st_size > 1_500_000:
        return "", ""
    key = str(path.resolve())
    signature = (stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size)
    with _lock:
        old = _cache.get(key)
        if old and old[0] == signature:
            _cache.move_to_end(key)
            return old[1], old[2]
    text = path.read_text(encoding="utf-8", errors="ignore")
    lower = text.lower()
    cost = (len(text) + len(lower)) * 4
    with _lock:
        old = _cache.pop(key, None)
        if old:
            _size -= old[3]
        _cache[key] = (signature, text, lower, cost)
        _size += cost
        while _size > _LIMIT and _cache:
            _size -= _cache.popitem(last=False)[1][3]
    return text, lower
