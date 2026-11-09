"""
In-Memory Cache Module (MemoryCache).
Provides thread-safe local caching and atomic sequence number generation.
"""

import asyncio
from typing import Dict, Any, Optional

class MemoryCache:
    """Thread-safe in-memory cache implementation."""

    def __init__(self):
        self._store: Dict[str, Any] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[Any]:
        """Retrieves a value from cache by key."""
        async with self._lock:
            return self._store.get(key)

    async def set(self, key: str, value: Any) -> None:
        """Sets a value in cache by key."""
        async with self._lock:
            self._store[key] = value

    async def delete(self, key: str) -> None:
        """Deletes a key from cache."""
        async with self._lock:
            self._store.pop(key, None)

    async def get_next_sequence(self, company_id: int, area_code: str) -> int:
        """Atomically increments and returns the next sequence number for an area code."""
        key = f"seq:{company_id}:{area_code}"
        async with self._lock:
            current = self._store.get(key, 0)
            next_val = current + 1
            self._store[key] = next_val
            return next_val

    async def set_sequence_if_higher(self, company_id: int, area_code: str, val: int) -> None:
        """Updates sequence cache if the provided value is higher than current."""
        key = f"seq:{company_id}:{area_code}"
        async with self._lock:
            current = self._store.get(key, 0)
            if val > current:
                self._store[key] = val

cache = MemoryCache()