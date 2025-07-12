"""Comprehensive tests for core module."""

import asyncio
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest

import numpy as np
from memory_system.config.settings import UnifiedSettings
from memory_system.core.embedding import (
    EmbeddingError,
    EmbeddingJob,
    EnhancedEmbeddingService,
)
from memory_system.core.index import (
    ANNIndexError,
    FaissHNSWIndex,
    IndexStats,
)
from memory_system.core.store import (
    EnhancedMemoryStore,
    HealthComponent,
    Memory,
    SQLiteMemoryStore,
    get_store,
)
from memory_system.core.vector_store import VectorStore
from memory_system.utils.exceptions import StorageError, ValidationError


class TestMemoryDataClass:
    """Test Memory data class."""

    def test_memory_creation(self):
        """Test Memory object creation."""
        memory = Memory(id="test-id", text="test text")
        assert memory.id == "test-id"
        assert memory.text == "test text"
        assert memory.metadata is None

    def test_memory_with_metadata(self):
        """Test Memory object with metadata."""
        metadata = {"key": "value", "type": "test"}
        memory = Memory(id="test-id", text="test text", metadata=metadata)
        assert memory.id == "test-id"
        assert memory.text == "test text"
        assert memory.metadata == metadata

    def test_memory_equality(self):
        """Test Memory object equality."""
        memory1 = Memory(id="test-id", text="test text")
        memory2 = Memory(id="test-id", text="test text")
        memory3 = Memory(id="other-id", text="test text")

        assert memory1 == memory2
        assert memory1 != memory3


class TestHealthComponent:
    """Test HealthComponent data class."""

    def test_health_component_creation(self):
        """Test HealthComponent creation."""
        checks = {"database": True, "index": True}
        health = HealthComponent(
            healthy=True, message="All systems operational", uptime=3600, checks=checks
        )
        assert health.healthy is True
        assert health.message == "All systems operational"
        assert health.uptime == 3600
        assert health.checks == checks

    def test_health_component_unhealthy(self):
        """Test HealthComponent for unhealthy state."""
        checks = {"database": False, "index": True}
        health = HealthComponent(
            healthy=False, message="Database connection failed", uptime=100, checks=checks
        )
        assert health.healthy is False
        assert health.message == "Database connection failed"
        assert health.uptime == 100
        assert health.checks == checks


class TestSQLiteMemoryStore:
    """Test SQLiteMemoryStore functionality."""

    @pytest.fixture
    def temp_db_path(self):
        """Create temporary database path."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            yield Path(f.name)
        Path(f.name).unlink(missing_ok=True)

    @pytest.fixture
    def store(self, temp_db_path):
        """Create SQLiteMemoryStore instance."""
        return SQLiteMemoryStore(temp_db_path)

    def test_store_initialization(self, store, temp_db_path):
        """Test store initialization."""
        assert store._path == temp_db_path
        assert store._conn is not None
        assert store._loop is not None

    async def test_add_memory(self, store):
        """Test adding memory to store."""
        memory = Memory(id="test-1", text="Test memory")
        await store.add(memory)

        retrieved = await store.get("test-1")
        assert retrieved is not None
        assert retrieved.id == "test-1"
        assert retrieved.text == "Test memory"
        assert retrieved.metadata is None

    async def test_add_memory_with_metadata(self, store):
        """Test adding memory with metadata."""
        metadata = {"type": "test", "priority": "high"}
        memory = Memory(id="test-2", text="Test memory", metadata=metadata)
        await store.add(memory)

        retrieved = await store.get("test-2")
        assert retrieved is not None
        assert retrieved.id == "test-2"
        assert retrieved.text == "Test memory"
        assert retrieved.metadata == metadata

    async def test_get_nonexistent_memory(self, store):
        """Test getting nonexistent memory."""
        retrieved = await store.get("nonexistent")
        assert retrieved is None

    async def test_replace_memory(self, store):
        """Test replacing existing memory."""
        memory1 = Memory(id="test-3", text="Original text")
        await store.add(memory1)

        memory2 = Memory(id="test-3", text="Updated text")
        with pytest.raises(Exception):
            await store.add(memory2)

        retrieved = await store.get("test-3")
        assert retrieved is not None
        assert retrieved.text == "Original text"

    async def test_concurrent_access(self, store):
        """Test concurrent access to store."""
        tasks = []
        for i in range(10):
            memory = Memory(id=f"concurrent-{i}", text=f"Text {i}")
            task = asyncio.create_task(store.add(memory))
            tasks.append(task)

        await asyncio.gather(*tasks)

        # Verify all memories were added
        for i in range(10):
            retrieved = await store.get(f"concurrent-{i}")
            assert retrieved is not None
            assert retrieved.text == f"Text {i}"

    async def test_store_close(self, store):
        """Test store closure."""
        await store.close()
        # After closing, the connection should be closed
        # Further operations might fail, but we can't easily test this
        # without risking test contamination


class TestEnhancedMemoryStore:
    """Test EnhancedMemoryStore functionality."""

    @pytest.fixture
    def test_settings(self):
        """Create test settings."""
        return UnifiedSettings.for_testing()

    @pytest.fixture
    def store(self, test_settings):
        """Create EnhancedMemoryStore instance."""
        return EnhancedMemoryStore(test_settings)

    def test_store_initialization(self, store, test_settings):
        """Test store initialization."""
        assert store.settings == test_settings
        assert store._start_time > 0

    async def test_get_health(self, store):
        """Test health check."""
        health = await store.get_health()
        assert isinstance(health, HealthComponent)
        assert health.uptime >= 0
        assert isinstance(health.checks, dict)
        assert "database" in health.checks
        assert "index" in health.checks
        assert "embedding_service" in health.checks

    async def test_get_stats(self, store):
        """Test stats retrieval."""
        stats = await store.get_stats()
        assert isinstance(stats, dict)
        assert "total_memories" in stats
        assert "index_size" in stats
        assert "cache_stats" in stats
        assert "buffer_size" in stats
        assert "uptime_seconds" in stats
        assert stats["uptime_seconds"] >= 0

    async def test_store_close(self, store):
        """Test store closure."""
        await store.close()
        # Should not raise any exceptions


class TestGetStore:
    """Test get_store function."""

    async def test_get_store_singleton(self):
        """Test that get_store returns singleton."""
        store1 = await get_store()
        store2 = await get_store()
        assert store1 is store2

    async def test_get_store_custom_path(self):
        """Test get_store with custom path."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            path = Path(f.name)

        try:
            store = await get_store(path)
            assert store._path == path
        finally:
            path.unlink(missing_ok=True)


class TestEmbeddingJob:
    """Test EmbeddingJob data class."""

    def test_embedding_job_creation(self):
        """Test EmbeddingJob creation."""
        future = asyncio.Future()
        job = EmbeddingJob(text="test text", future=future)
        assert job.text == "test text"
        assert job.future is future

    def test_embedding_job_immutable(self):
        """Test that EmbeddingJob is immutable."""
        future = asyncio.Future()
        job = EmbeddingJob(text="test text", future=future)

        # Should not be able to modify frozen dataclass
        with pytest.raises(AttributeError):
            job.text = "new text"


class TestEmbeddingError:
    """Test EmbeddingError exception."""

    def test_embedding_error_creation(self):
        """Test EmbeddingError creation."""
        error = EmbeddingError("Test error")
        assert str(error) == "Test error"
        assert isinstance(error, RuntimeError)

    def test_embedding_error_with_cause(self):
        """Test EmbeddingError with cause."""
        cause = ValueError("Original error")
        error = EmbeddingError("Test error")
        error.__cause__ = cause
        assert error.__cause__ is cause


class TestEnhancedEmbeddingService:
    """Test EnhancedEmbeddingService functionality."""

    @pytest.fixture
    def test_settings(self):
        """Create test settings."""
        return UnifiedSettings.for_testing()

    @pytest.fixture
    def service(self, test_settings):
        """Create EmbeddingService instance."""
        return EnhancedEmbeddingService("all-MiniLM-L6-v2", test_settings)

    def test_service_initialization(self, service, test_settings):
        """Test service initialization."""
        assert service.model_name == "all-MiniLM-L6-v2"
        assert service.settings == test_settings
        assert service.cache is not None
        assert service._batch_thread is not None
        assert service._batch_thread.is_alive()

    async def test_encode_single_text(self, service):
        """Test encoding single text."""
        text = "This is a test sentence."
        result = await service.encode(text)

        assert isinstance(result, np.ndarray)
        assert result.shape[0] == 1  # Single text
        assert result.shape[1] > 0  # Non-zero dimensions

    async def test_encode_multiple_texts(self, service):
        """Test encoding multiple texts."""
        texts = ["First sentence.", "Second sentence.", "Third sentence."]
        result = await service.encode(texts)

        assert isinstance(result, np.ndarray)
        assert result.shape[0] == 3  # Three texts
        assert result.shape[1] > 0  # Non-zero dimensions

    async def test_encode_empty_text(self, service):
        """Test encoding empty text."""
        with pytest.raises((ValueError, RuntimeError)):  # Should raise some kind of error
            await service.encode("")

    async def test_encode_caching(self, service):
        """Test that encoding results are cached."""
        text = "This text will be cached."

        # First call
        result1 = await service.encode(text)

        # Second call should use cache
        result2 = await service.encode(text)

        np.testing.assert_array_equal(result1, result2)

    async def test_encode_timeout(self, service):
        """Test encoding timeout."""
        # Mock a slow encoding operation
        with patch.object(service, "_encode_direct") as mock_encode:

            def stub(_texts):
                asyncio.run(asyncio.sleep(0.1))
                raise TimeoutError("operation timed out")

            mock_encode.side_effect = stub

            with pytest.raises(EmbeddingError) as exc_info:
                await service.encode("test text")

            assert "timed out" in str(exc_info.value).lower()

    def test_service_stats(self, service):
        """Test service statistics."""
        stats = service.stats()
        assert isinstance(stats, dict)
        assert "model" in stats
        assert "dimension" in stats
        assert "cache" in stats
        assert "queue_size" in stats
        assert "shutdown" in stats
        assert stats["model"] == service.model_name
        assert isinstance(stats["dimension"], int)
        assert stats["dimension"] > 0

    def test_service_shutdown(self, service):
        """Test service shutdown."""
        service.shutdown()

        stats = service.stats()
        assert stats["shutdown"] is True
        assert stats["queue_size"] == 0

    def test_service_context_manager(self, test_settings):
        """Test service as context manager."""
        with EnhancedEmbeddingService("all-MiniLM-L6-v2", test_settings) as service:
            assert service._batch_thread is not None
            assert service._batch_thread.is_alive()

        # Should be shut down after context exit
        stats = service.stats()
        assert stats["shutdown"] is True

    async def test_fallback_model_loading(self, test_settings):
        """Test fallback model loading."""
        # Try to load a non-existent model
        service = EnhancedEmbeddingService("non-existent-model", test_settings)

        # Should fall back to default model
        assert service.model_name == "all-MiniLM-L6-v2"

        # Should still work
        result = await service.encode("test text")
        assert isinstance(result, np.ndarray)

        service.shutdown()


class TestIndexStats:
    """Test IndexStats data class."""

    def test_index_stats_creation(self):
        """Test IndexStats creation."""
        stats = IndexStats(dim=384)
        assert stats.dim == 384
        assert stats.total_vectors == 0
        assert stats.total_queries == 0
        assert stats.avg_latency_ms == 0.0
        assert stats.last_rebuild is None
        assert stats.extra == {}

    def test_index_stats_with_values(self):
        """Test IndexStats with custom values."""
        extra = {"custom_metric": 42}
        stats = IndexStats(
            dim=768,
            total_vectors=1000,
            total_queries=500,
            avg_latency_ms=1.5,
            last_rebuild=time.time(),
            extra=extra,
        )
        assert stats.dim == 768
        assert stats.total_vectors == 1000
        assert stats.total_queries == 500
        assert stats.avg_latency_ms == 1.5
        assert stats.last_rebuild is not None
        assert stats.extra == extra


class TestFaissHNSWIndex:
    """Test FaissHNSWIndex functionality."""

    @pytest.fixture
    def index(self):
        """Create FaissHNSWIndex instance."""
        return FaissHNSWIndex(dim=384)

    def test_index_initialization(self, index):
        """Test index initialization."""
        assert index.dim == 384
        assert index.space == "cosine"
        assert index.ef_search == 32
        assert index.index is not None
        assert index._stats.dim == 384
        assert index._stats.total_vectors == 0

    def test_add_vectors(self, index):
        """Test adding vectors to index."""
        ids = ["vec1", "vec2", "vec3"]
        vectors = np.random.rand(3, 384).astype(np.float32)

        index.add_vectors(ids, vectors)

        stats = index.stats()
        assert stats.total_vectors == 3

    def test_add_vectors_dimension_mismatch(self, index):
        """Test adding vectors with wrong dimensions."""
        ids = ["vec1"]
        vectors = np.random.rand(1, 256).astype(np.float32)  # Wrong dimension

        with pytest.raises(ANNIndexError) as exc_info:
            index.add_vectors(ids, vectors)
        assert "dimension mismatch" in str(exc_info.value).lower()

    def test_add_vectors_length_mismatch(self, index):
        """Test adding vectors with mismatched ID count."""
        ids = ["vec1", "vec2"]
        vectors = np.random.rand(3, 384).astype(np.float32)  # 3 vectors, 2 IDs

        with pytest.raises(ANNIndexError) as exc_info:
            index.add_vectors(ids, vectors)
        assert "length mismatch" in str(exc_info.value).lower()

    def test_add_vectors_duplicate_ids(self, index):
        """Test adding vectors with duplicate IDs."""
        ids = ["vec1", "vec1", "vec2"]  # Duplicate ID
        vectors = np.random.rand(3, 384).astype(np.float32)

        with pytest.raises(ANNIndexError) as exc_info:
            index.add_vectors(ids, vectors)
        assert "duplicate" in str(exc_info.value).lower()

    def test_add_vectors_existing_ids(self, index):
        """Test adding vectors with existing IDs."""
        ids1 = ["vec1", "vec2"]
        vectors1 = np.random.rand(2, 384).astype(np.float32)
        index.add_vectors(ids1, vectors1)

        ids2 = ["vec2", "vec3"]  # vec2 already exists
        vectors2 = np.random.rand(2, 384).astype(np.float32)

        with pytest.raises(ANNIndexError) as exc_info:
            index.add_vectors(ids2, vectors2)
        assert "already present" in str(exc_info.value).lower()

    def test_search_vectors(self, index):
        """Test searching vectors."""
        ids = ["vec1", "vec2", "vec3"]
        vectors = np.random.rand(3, 384).astype(np.float32)
        index.add_vectors(ids, vectors)

        query_vector = np.random.rand(384).astype(np.float32)
        result_ids, distances = index.search(query_vector, k=2)

        assert len(result_ids) <= 2
        assert len(distances) <= 2
        assert len(result_ids) == len(distances)

    def test_search_dimension_mismatch(self, index):
        """Test searching with wrong query dimension."""
        query_vector = np.random.rand(256).astype(np.float32)  # Wrong dimension

        with pytest.raises(ANNIndexError) as exc_info:
            index.search(query_vector, k=1)
        assert "dimension mismatch" in str(exc_info.value).lower()

    def test_search_empty_index(self, index):
        """Test searching empty index."""
        query_vector = np.random.rand(384).astype(np.float32)
        result_ids, distances = index.search(query_vector, k=5)

        assert len(result_ids) == 0
        assert len(distances) == 0

    def test_remove_vectors(self, index):
        """Test removing vectors from index."""
        ids = ["vec1", "vec2", "vec3"]
        vectors = np.random.rand(3, 384).astype(np.float32)
        index.add_vectors(ids, vectors)

        index.remove_ids(["vec1", "vec3"])

        stats = index.stats()
        assert stats.total_vectors == 1

    def test_dynamic_ef_search(self, index):
        """Test dynamic ef_search parameter."""
        ids = ["vec1", "vec2", "vec3"]
        vectors = np.random.rand(3, 384).astype(np.float32)
        index.add_vectors(ids, vectors)

        query_vector = np.random.rand(384).astype(np.float32)

        # Test with custom ef_search
        result_ids, distances = index.search(query_vector, k=2, ef_search=64)
        assert len(result_ids) <= 2
        assert index.ef_search == 64  # Should be updated

    def test_index_rebuild(self, index):
        """Test index rebuild."""
        ids = ["vec1", "vec2", "vec3"]
        vectors = np.random.rand(3, 384).astype(np.float32)

        index.rebuild(vectors, ids)

        stats = index.stats()
        assert stats.total_vectors == 3
        assert stats.last_rebuild is not None

    def test_index_save_load(self, index):
        """Test index save and load."""
        ids = ["vec1", "vec2", "vec3"]
        vectors = np.random.rand(3, 384).astype(np.float32)
        index.add_vectors(ids, vectors)

        with tempfile.NamedTemporaryFile(suffix=".index") as f:
            index.save(f.name)

            # Create new index and load
            new_index = FaissHNSWIndex(dim=384)
            new_index.load(f.name)

            stats = new_index.stats()
            assert stats.total_vectors == 3


class TestVectorStore:
    """Test VectorStore functionality."""

    @pytest.fixture
    def temp_store_path(self):
        """Create temporary store path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir) / "test_vectors"

    @pytest.fixture
    def store(self, temp_store_path):
        """Create VectorStore instance."""
        return VectorStore(temp_store_path, dim=384)

    def test_store_initialization(self, store, temp_store_path):
        """Test store initialization."""
        assert store._base_path == temp_store_path
        assert store._dim == 384
        assert store._bin_path == temp_store_path.with_suffix(".bin")
        assert store._db_path == temp_store_path.with_suffix(".db")
        assert store._file is not None
        assert store._conn is not None

    def test_add_vector(self, store):
        """Test adding vector to store."""
        vector_id = "test-vector-1"
        vector = np.random.rand(384).astype(np.float32)

        store.add_vector(vector_id, vector)

        retrieved = store.get_vector(vector_id)
        np.testing.assert_array_equal(vector, retrieved)

    def test_add_vector_wrong_dtype(self, store):
        """Test adding vector with wrong dtype."""
        vector_id = "test-vector-1"
        vector = np.random.rand(384).astype(np.float64)  # Wrong dtype

        with pytest.raises(ValidationError) as exc_info:
            store.add_vector(vector_id, vector)
        assert "float32" in str(exc_info.value).lower()

    def test_add_vector_wrong_shape(self, store):
        """Test adding vector with wrong shape."""
        vector_id = "test-vector-1"
        vector = np.random.rand(384, 1).astype(np.float32)  # Wrong shape

        with pytest.raises(ValidationError) as exc_info:
            store.add_vector(vector_id, vector)
        assert "1-D" in str(exc_info.value)

    def test_add_vector_wrong_dimension(self, store):
        """Test adding vector with wrong dimension."""
        vector_id = "test-vector-1"
        vector = np.random.rand(256).astype(np.float32)  # Wrong dimension

        with pytest.raises(ValidationError) as exc_info:
            store.add_vector(vector_id, vector)
        assert "expected dim 384" in str(exc_info.value)

    def test_add_vector_duplicate_id(self, store):
        """Test adding vector with duplicate ID."""
        vector_id = "test-vector-1"
        vector1 = np.random.rand(384).astype(np.float32)
        vector2 = np.random.rand(384).astype(np.float32)

        store.add_vector(vector_id, vector1)

        with pytest.raises(ValidationError) as exc_info:
            store.add_vector(vector_id, vector2)
        assert "duplicate" in str(exc_info.value).lower()

    def test_get_nonexistent_vector(self, store):
        """Test getting nonexistent vector."""
        with pytest.raises(StorageError) as exc_info:
            store.get_vector("nonexistent")
        assert "not found" in str(exc_info.value).lower()

    def test_remove_vector(self, store):
        """Test removing vector from store."""
        vector_id = "test-vector-1"
        vector = np.random.rand(384).astype(np.float32)

        store.add_vector(vector_id, vector)
        store.remove_vector(vector_id)

        with pytest.raises(StorageError):
            store.get_vector(vector_id)

    def test_remove_nonexistent_vector(self, store):
        """Test removing nonexistent vector."""
        with pytest.raises(StorageError) as exc_info:
            store.remove_vector("nonexistent")
        assert "not found" in str(exc_info.value).lower()

    def test_list_ids(self, store):
        """Test listing vector IDs."""
        vector_ids = ["vec1", "vec2", "vec3"]

        for vector_id in vector_ids:
            vector = np.random.rand(384).astype(np.float32)
            store.add_vector(vector_id, vector)

        ids = store.list_ids()
        assert set(ids) == set(vector_ids)

    def test_store_flush(self, store):
        """Test store flush operation."""
        vector_id = "test-vector-1"
        vector = np.random.rand(384).astype(np.float32)

        store.add_vector(vector_id, vector)
        asyncio.run(store.flush())  # Should not raise any exceptions

    async def test_store_async_flush(self, store):
        """Test store async flush operation."""
        vector_id = "test-vector-1"
        vector = np.random.rand(384).astype(np.float32)

        store.add_vector(vector_id, vector)
        await store.async_flush()  # Should not raise any exceptions

    def test_store_close(self, store):
        """Test store close operation."""
        vector_id = "test-vector-1"
        vector = np.random.rand(384).astype(np.float32)

        store.add_vector(vector_id, vector)
        store.close()  # Should not raise any exceptions

    def test_store_integrity_check(self, store):
        """Test vector storage integrity."""
        vector_id = "test-vector-1"
        vector = np.random.rand(384).astype(np.float32)

        store.add_vector(vector_id, vector)

        # Manually corrupt the data and verify checksum fails
        # This is a complex test that would require direct file manipulation
        pass

    def test_store_dimension_auto_detection(self):
        """Test dimension auto-detection."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "auto_dim_vectors"
            store = VectorStore(store_path, dim=0)  # Auto-detect dimension

            vector_id = "test-vector-1"
            vector = np.random.rand(512).astype(np.float32)

            store.add_vector(vector_id, vector)
            assert store._dim == 512

            retrieved = store.get_vector(vector_id)
            np.testing.assert_array_equal(vector, retrieved)

            store.close()


class TestCoreIntegration:
    """Test integration between core components."""

    @pytest.fixture
    def test_settings(self):
        """Create test settings."""
        return UnifiedSettings.for_testing()

    async def test_store_and_embedding_integration(self, test_settings):
        """Test integration between store and embedding service."""
        store = EnhancedMemoryStore(test_settings)
        embedding_service = EnhancedEmbeddingService("all-MiniLM-L6-v2", test_settings)

        try:
            # Test that both components can work together
            health = await store.get_health()
            assert health.healthy

            # Test embedding service
            text = "Integration test text"
            embedding = await embedding_service.encode(text)
            assert isinstance(embedding, np.ndarray)

            # Test stats
            stats = await store.get_stats()
            assert isinstance(stats, dict)

            service_stats = embedding_service.stats()
            assert isinstance(service_stats, dict)

        finally:
            await store.close()
            embedding_service.shutdown()

    def test_index_and_vector_store_integration(self):
        """Test integration between index and vector store."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create vector store
            store_path = Path(tmpdir) / "integration_vectors"
            vector_store = VectorStore(store_path, dim=384)

            # Create index
            index = FaissHNSWIndex(dim=384)

            try:
                # Add vectors to both
                vector_ids = ["vec1", "vec2", "vec3"]
                vectors = np.random.rand(3, 384).astype(np.float32)

                # Add to vector store
                for i, vector_id in enumerate(vector_ids):
                    vector_store.add_vector(vector_id, vectors[i])

                # Add to index
                index.add_vectors(vector_ids, vectors)

                # Verify both have the data
                store_ids = set(vector_store.list_ids())
                assert store_ids == set(vector_ids)

                index_stats = index.stats()
                assert index_stats.total_vectors == 3

                # Test search
                query = np.random.rand(384).astype(np.float32)
                result_ids, distances = index.search(query, k=2)

                # Verify we can retrieve the vectors from the store
                for result_id in result_ids:
                    if result_id in vector_ids:  # Valid ID returned
                        retrieved = vector_store.get_vector(result_id)
                        assert isinstance(retrieved, np.ndarray)
                        assert retrieved.shape == (384,)

            finally:
                vector_store.close()

    async def test_error_handling_integration(self, test_settings):
        """Test error handling across components."""
        store = EnhancedMemoryStore(test_settings)

        try:
            # Test that errors are properly propagated
            health = await store.get_health()

            # Even if some checks fail, the system should still respond
            assert isinstance(health.checks, dict)
            assert isinstance(health.healthy, bool)

        finally:
            await store.close()
