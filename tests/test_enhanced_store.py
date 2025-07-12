"""
Validates real operations of ``EnhancedMemoryStore``:
* adding memories
* retrieving statistics
* semantic search
* reactions to edge cases
"""
import asyncio
import secrets
import time

import numpy as np
import pytest

from memory_system.config.settings import UnifiedSettings
from memory_system.core.enhanced_store import EnhancedMemoryStore
from memory_system.core.index import ANNIndexError


@pytest.fixture(scope="function")
async def store():
    settings = UnifiedSettings.for_testing()
    s = EnhancedMemoryStore(settings)
    yield s
    await s.close()


def _rand_vec(dim: int, seed: int = 42) -> list[float]:
    rng = np.random.default_rng(seed)
    return rng.random(dim).astype("float32").tolist()


@pytest.mark.asyncio
async def test_add_and_search(store):
    vec = _rand_vec(store.settings.model.vector_dim)
    ts = time.time()

    # 1) add a memory
    await store.add_memory(
        text="hello world",
        role="user",
        tags=["demo"],
        importance=0.2,
        embedding=vec,
        created_at=ts,
        updated_at=ts,
        valence=0.0,
        emotional_intensity=0.0,
    )

    stats = await store.get_stats()
    assert stats["total_memories"] == 1
    assert stats["index_size"] == 1

    # 2) search using the same vector
    res = await store.semantic_search(vector=vec, k=1)
    assert len(res) == 1
    assert res[0].text == "hello world"


@pytest.mark.asyncio
async def test_search_empty_store(store):
    vec = _rand_vec(store.settings.model.vector_dim)
    res = await store.semantic_search(vector=vec, k=1)
    assert res == []


@pytest.mark.asyncio
async def test_invalid_vector_length(store):
    # vector shorter than required 384 elements
    bad_vec = [0.1, 0.2, 0.3]
    with pytest.raises(ANNIndexError):
        await store.semantic_search(vector=bad_vec, k=1)


# Optional extended check
@pytest.mark.asyncio
async def test_duplicate_vectors_rejected(store):
    dim = store.settings.model.vector_dim
    v1 = _rand_vec(dim, seed=1)
    now = time.time()

    # add the first memory
    await store.add_memory(
        text="dup",
        importance=0.1,
        embedding=v1,
        created_at=now,
        updated_at=now,
        role=None,
        tags=None,
        valence=0.0,
        emotional_intensity=0.0,
    )
    # FAISS will not allow the same ID twice,
    # we check duplicate detection at the index level
    with pytest.raises(ValueError):
        store._index.add_vectors(
            [store._index._id_map[1]], np.asarray([v1], dtype=np.float32)
        )
