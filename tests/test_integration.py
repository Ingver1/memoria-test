"""Comprehensive integration tests for Unified Memory System."""

import asyncio
import json
import tempfile
import time
from pathlib import Path

import pytest

import httpx
from fastapi.testclient import TestClient
from memory_system.api.app import create_app
from memory_system.config.settings import UnifiedSettings
from memory_system.core.embedding import EnhancedEmbeddingService
from memory_system.core.index import FaissHNSWIndex
from memory_system.core.store import EnhancedMemoryStore
from memory_system.core.vector_store import VectorStore
from memory_system.utils.security import EncryptionManager, EnhancedPIIFilter


class TestEndToEndMemoryWorkflow:
    """Test complete end-to-end memory management workflow."""

    @pytest.fixture
    async def full_system(self):
        """Create a complete system setup."""
        settings = UnifiedSettings.for_testing()

        # Create components
        store = EnhancedMemoryStore(settings)
        embedding_service = EnhancedEmbeddingService("all-MiniLM-L6-v2", settings)

        # Create temporary paths
        with tempfile.TemporaryDirectory() as tmpdir:
            vector_store = VectorStore(Path(tmpdir) / "vectors", dim=384)
            index = FaissHNSWIndex(dim=384)

            yield {
                "settings": settings,
                "store": store,
                "embedding_service": embedding_service,
                "vector_store": vector_store,
                "index": index,
            }

            # Cleanup
            await store.close()
            embedding_service.shutdown()
            vector_store.close()

    async def test_complete_memory_lifecycle(self, full_system):
        """Test complete memory lifecycle from creation to search."""
        components = full_system
        embedding_service = components["embedding_service"]
        vector_store = components["vector_store"]
        index = components["index"]

        # Test data
        memories = [
            {
                "id": "mem1",
                "text": "Machine learning algorithms are powerful tools for data analysis.",
            },
            {"id": "mem2", "text": "Deep learning neural networks can recognize complex patterns."},
            {
                "id": "mem3",
                "text": "Natural language processing enables computers to understand human text.",
            },
            {
                "id": "mem4",
                "text": "Computer vision allows machines to interpret visual information.",
            },
            {
                "id": "mem5",
                "text": "Reinforcement learning helps agents learn through trial and error.",
            },
        ]

        # Step 1: Generate embeddings
        texts = [mem["text"] for mem in memories]
        embeddings = await embedding_service.encode(texts)

        assert embeddings.shape[0] == len(memories)
        assert embeddings.shape[1] == 384

        # Step 2: Store vectors
        for i, memory in enumerate(memories):
            vector_store.add_vector(memory["id"], embeddings[i])

        # Step 3: Add to search index
        memory_ids = [mem["id"] for mem in memories]
        index.add_vectors(memory_ids, embeddings)

        # Step 4: Verify storage
        stored_ids = set(vector_store.list_ids())
        assert stored_ids == set(memory_ids)

        index_stats = index.stats()
        assert index_stats.total_vectors == len(memories)

        # Step 5: Search for similar memories
        query_text = "deep learning and neural networks"
        query_embedding = await embedding_service.encode(query_text)

        result_ids, distances = index.search(query_embedding.flatten(), k=3)

        # Should find relevant memories
        assert len(result_ids) <= 3
        assert len(distances) <= 3

        # Step 6: Retrieve full vectors
        for result_id in result_ids:
            if result_id in memory_ids:
                retrieved_vector = vector_store.get_vector(result_id)
                assert retrieved_vector.shape == (384,)

        # Step 7: Verify semantic relevance
        # The query about "deep learning and neural networks" should find mem2
        # as the most relevant result
        if result_ids:
            # Find the original memory text for the top result
            top_result_id = result_ids[0]
            top_memory = next(mem for mem in memories if mem["id"] == top_result_id)

            # Should be about neural networks or deep learning
            assert any(
                keyword in top_memory["text"].lower() for keyword in ["neural", "deep", "learning"]
            )

    async def test_memory_search_precision(self, full_system):
        """Test search precision and recall."""
        components = full_system
        embedding_service = components["embedding_service"]
        vector_store = components["vector_store"]
        index = components["index"]

        # Create memories with known semantic relationships
        memory_groups = {
            "programming": [
                {"id": "prog1", "text": "Python is a versatile programming language."},
                {"id": "prog2", "text": "JavaScript is essential for web development."},
                {"id": "prog3", "text": "Java is widely used in enterprise applications."},
            ],
            "science": [
                {"id": "sci1", "text": "Physics explains the fundamental laws of nature."},
                {"id": "sci2", "text": "Chemistry studies the composition of matter."},
                {"id": "sci3", "text": "Biology explores living organisms and life processes."},
            ],
            "cooking": [
                {"id": "cook1", "text": "Italian cuisine features pasta and tomato sauces."},
                {"id": "cook2", "text": "French cooking emphasizes butter and wine."},
                {"id": "cook3", "text": "Asian dishes often use soy sauce and rice."},
            ],
        }

        # Store all memories
        all_memories = []
        for group_memories in memory_groups.values():
            all_memories.extend(group_memories)

        texts = [mem["text"] for mem in all_memories]
        embeddings = await embedding_service.encode(texts)

        memory_ids = [mem["id"] for mem in all_memories]

        # Add to storage
        for i, memory in enumerate(all_memories):
            vector_store.add_vector(memory["id"], embeddings[i])

        index.add_vectors(memory_ids, embeddings)

        # Test searches within each domain
        test_queries = {
            "programming": "software development and coding",
            "science": "scientific research and experiments",
            "cooking": "recipes and food preparation",
        }

        for domain, query in test_queries.items():
            query_embedding = await embedding_service.encode(query)
            result_ids, distances = index.search(query_embedding.flatten(), k=5)

            # Check that results are relevant to the domain
            domain_memories = {mem["id"] for mem in memory_groups[domain]}

            # Count how many results are from the correct domain
            correct_domain_results = sum(
                1 for result_id in result_ids if result_id in domain_memories
            )

            # Should find at least one relevant result
            assert correct_domain_results > 0

            # Calculate precision (what fraction of results are relevant)
            precision = correct_domain_results / len(result_ids) if result_ids else 0

            # Should have reasonable precision (at least 33% for this test)
            assert precision >= 0.33

    async def test_memory_persistence(self, full_system):
        """Test memory persistence across system restarts."""
        components = full_system
        embedding_service = components["embedding_service"]
        vector_store = components["vector_store"]
        index = components["index"]

        # Add some memories
        memories = [
            {"id": "persist1", "text": "This memory should persist across restarts."},
            {"id": "persist2", "text": "Persistence is important for data durability."},
        ]

        texts = [mem["text"] for mem in memories]
        embeddings = await embedding_service.encode(texts)

        # Store memories
        for i, memory in enumerate(memories):
            vector_store.add_vector(memory["id"], embeddings[i])

        memory_ids = [mem["id"] for mem in memories]
        index.add_vectors(memory_ids, embeddings)

        # Save index to file
        with tempfile.NamedTemporaryFile(suffix=".index", delete=False) as f:
            index_path = f.name

        try:
            index.save(index_path)

            # Create new index and load
            new_index = FaissHNSWIndex(dim=384)
            new_index.load(index_path)

            # Verify loaded index has the same data
            new_stats = new_index.stats()
            assert new_stats.total_vectors == len(memories)

            # Test search on loaded index
            query_text = "persistence and durability"
            query_embedding = await embedding_service.encode(query_text)

            result_ids, distances = new_index.search(query_embedding.flatten(), k=2)

            # Should find the persisted memories
            assert len(result_ids) <= 2
            assert all(result_id in memory_ids for result_id in result_ids)

        finally:
            Path(index_path).unlink(missing_ok=True)

    async def test_concurrent_memory_operations(self, full_system):
        """Test concurrent memory operations."""
        components = full_system
        embedding_service = components["embedding_service"]
        vector_store = components["vector_store"]
        index = components["index"]

        async def add_memories(batch_id: int, count: int):
            """Add a batch of memories concurrently."""
            batch_memories = []
            for i in range(count):
                memory = {
                    "id": f"concurrent_{batch_id}_{i}",
                    "text": f"Concurrent memory {batch_id}-{i} for testing parallel operations.",
                }
                batch_memories.append(memory)

            # Generate embeddings for batch
            texts = [mem["text"] for mem in batch_memories]
            embeddings = await embedding_service.encode(texts)

            # Add to storage (sequential within batch to avoid conflicts)
            for i, memory in enumerate(batch_memories):
                vector_store.add_vector(memory["id"], embeddings[i])

            # Add to index
            memory_ids = [mem["id"] for mem in batch_memories]
            index.add_vectors(memory_ids, embeddings)

            return batch_memories

        # Create multiple concurrent batches
        batch_size = 5
        num_batches = 3

        tasks = []
        for batch_id in range(num_batches):
            task = asyncio.create_task(add_memories(batch_id, batch_size))
            tasks.append(task)

        # Wait for all batches to complete
        batch_results = await asyncio.gather(*tasks)

        # Verify all memories were added
        all_memories = []
        for batch_memories in batch_results:
            all_memories.extend(batch_memories)

        stored_ids = set(vector_store.list_ids())
        expected_ids = {mem["id"] for mem in all_memories}

        assert stored_ids == expected_ids

        index_stats = index.stats()
        assert index_stats.total_vectors == len(all_memories)

        # Test concurrent searches
        async def search_memories(query_text: str):
            """Perform concurrent searches."""
            query_embedding = await embedding_service.encode(query_text)
            result_ids, distances = index.search(query_embedding.flatten(), k=3)
            return result_ids, distances

        # Multiple concurrent searches
        search_tasks = []
        for i in range(5):
            query = f"concurrent testing parallel operations {i}"
            task = asyncio.create_task(search_memories(query))
            search_tasks.append(task)

        search_results = await asyncio.gather(*search_tasks)

        # All searches should return results
        for result_ids, distances in search_results:
            assert len(result_ids) <= 3
            assert len(distances) <= 3


class TestAPIIntegration:
    """Test API integration with core components."""

    @pytest.fixture
    def test_app(self):
        """Create test FastAPI app."""
        return create_app()

    @pytest.fixture
    def client(self, test_app):
        """Create test client."""
        return TestClient(test_app)

    @pytest.fixture
    async def async_client(self, test_app):
        """Create async test client."""
        async with httpx.AsyncClient(app=test_app, base_url="http://test") as client:
            yield client

    def test_api_health_integration(self, client):
        """Test API health endpoint integration."""
        response = client.get("/api/v1/health")
        assert response.status_code == 200

        data = response.json()
        assert data["version"] == "0.8.0a0"
        assert "memory_store_health" in data
        assert "checks" in data
        assert isinstance(data["checks"], dict)

        # Should have core system checks
        expected_checks = ["database", "index", "embedding_service"]
        for check in expected_checks:
            assert check in data["checks"]

    def test_api_stats_integration(self, client):
        """Test API stats endpoint integration."""
        response = client.get("/api/v1/stats")
        assert response.status_code == 200

        data = response.json()
        assert "total_memories" in data
        assert "memory_store_stats" in data
        assert "api_stats" in data

        # Verify stats structure
        assert isinstance(data["total_memories"], int)
        assert isinstance(data["memory_store_stats"], dict)
        assert isinstance(data["api_stats"], dict)

    async def test_api_concurrent_requests(self, async_client):
        """Test concurrent API requests."""
        # Make multiple concurrent requests
        tasks = []
        for _i in range(10):
            task = asyncio.create_task(async_client.get("/api/v1/health"))
            tasks.append(task)

        responses = await asyncio.gather(*tasks)

        # All requests should succeed
        for response in responses:
            assert response.status_code == 200
            data = response.json()
            assert data["version"] == "0.8-alpha"

    def test_api_error_handling_integration(self, client):
        """Test API error handling integration."""
        # Test 404 error
        response = client.get("/api/v1/nonexistent")
        assert response.status_code == 404

        # Test 405 error
        response = client.post("/api/v1/health")
        assert response.status_code == 405

    def test_api_middleware_integration(self, client):
        """Test API middleware integration."""
        # Test that middleware is working
        response = client.get("/api/v1/health")
        assert response.status_code == 200

        # Check for expected headers (CORS, etc.)
        # This depends on the middleware configuration

        # Test rate limiting doesn't block normal usage
        for _i in range(5):
            response = client.get("/api/v1/health")
            assert response.status_code == 200


class TestSecurityIntegration:
    """Test security integration across components."""

    def test_pii_filtering_integration(self):
        """Test PII filtering across the system."""
        pii_filter = EnhancedPIIFilter()

        # Test data with PII
        test_texts = [
            "Contact John Doe at john.doe@example.com for more information.",
            "Call us at 555-123-4567 or email support@company.com",
            "My credit card number is 1234-5678-9012-3456",
            "SSN: 123-45-6789, DOB: 01/01/1990",
        ]

        for text in test_texts:
            # Detect PII
            detections = pii_filter.detect(text)
            assert len(detections) > 0

            # Redact PII
            redacted, found_pii, pii_types = pii_filter.redact(text)
            assert found_pii is True
            assert len(pii_types) > 0

            # Verify redaction worked
            for _detection_type, detected_values in detections.items():
                for value in detected_values:
                    assert value not in redacted

    def test_encryption_integration(self):
        """Test encryption integration."""
        encryption_manager = EncryptionManager()

        # Test encrypting different types of data
        test_data = [
            "Simple string data",
            json.dumps({"key": "value", "number": 42}),
            "Data with special characters: àáâãäåæçèéêë",
            "Long text " * 100,
        ]

        for data in test_data:
            # Encrypt
            encrypted = encryption_manager.encrypt(data)
            assert isinstance(encrypted, bytes)
            assert encrypted != data.encode()

            # Decrypt
            _decrypted = encryption_manager.decrypt(encrypted)
            assert _decrypted == data

    def test_pii_and_encryption_integration(self):
        """Test PII filtering with encryption."""
        pii_filter = EnhancedPIIFilter()
        encryption_manager = EncryptionManager()

        # Original text with PII
        original_text = "User john.doe@example.com has credit card 1234-5678-9012-3456"

        # Step 1: Redact PII
        redacted, found_pii, pii_types = pii_filter.redact(original_text)
        assert found_pii is True
        assert "email" in pii_types
        assert "credit_card" in pii_types

        # Step 2: Encrypt redacted text
        encrypted = encryption_manager.encrypt(redacted)

        # Step 3: Decrypt and verify
        decrypted = encryption_manager.decrypt(encrypted)
        assert decrypted  # ensure decryption returned something

        # Verify PII is not in final result
        assert "john.doe@example.com" not in decrypted
        assert "1234-5678-9012-3456" not in decrypted
        assert "[EMAIL_REDACTED]" in decrypted
        assert "[CREDIT_CARD_REDACTED]" in decrypted

    def test_security_performance_integration(self):
        """Test security operations performance."""
        pii_filter = EnhancedPIIFilter()
        encryption_manager = EncryptionManager()

        # Generate test data
        test_texts = [
            f"User {i} with email user{i}@example.com and phone {i:03d}-{i:03d}-{i:04d}"
            for i in range(10)
        ]

        start_time = time.time()

        # Process all texts
        for text in test_texts:
            # Detect and redact PII
            redacted, found_pii, pii_types = pii_filter.redact(text)

            # Encrypt result
            encrypted = encryption_manager.encrypt(redacted)

            # Decrypt to verify
            _decrypted = encryption_manager.decrypt(encrypted)
            assert _decrypted

        end_time = time.time()
        processing_time = end_time - start_time

        # Should process 100 texts in reasonable time
        assert processing_time < 30.0  # 30 seconds max
