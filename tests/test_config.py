"""Comprehensive tests for configuration module."""

import json
import os
import tempfile
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from pydantic import ValidationError

from memory_system.config.settings import (
    APIConfig,
    DatabaseConfig,
    ModelConfig,
    MonitoringConfig,
    PerformanceConfig,
    ReliabilityConfig,
    SecurityConfig,
    UnifiedSettings,
    get_settings,
)


class TestDatabaseConfig:
    """Test DatabaseConfig validation and functionality."""

    def test_database_config_defaults(self):
        """Test default database configuration."""
        config = DatabaseConfig()
        assert config.db_path == Path("data/memory.db")
        assert config.vec_path == Path("data/memory.vectors")
        assert config.cache_path == Path("data/memory.cache")
        assert config.connection_pool_size == 10

    def test_database_config_custom_paths(self):
        """Test custom database paths."""
        config = DatabaseConfig(
            db_path=Path("/tmp/custom.db"),
            vec_path=Path("/tmp/custom.vec"),
            cache_path=Path("/tmp/custom.cache"),
            connection_pool_size=5,
        )
        assert config.db_path == Path("/tmp/custom.db")
        assert config.vec_path == Path("/tmp/custom.vec")
        assert config.cache_path == Path("/tmp/custom.cache")
        assert config.connection_pool_size == 5

    def test_database_config_immutable(self):
        """Test that DatabaseConfig is immutable."""
        config = DatabaseConfig()
        with pytest.raises(ValidationError):
            config.db_path = Path("/new/path")


class TestModelConfig:
    """Test ModelConfig validation and functionality."""

    def test_model_config_defaults(self):
        """Test default model configuration."""
        config = ModelConfig()
        assert config.model_name == "all-MiniLM-L6-v2"
        assert config.batch_add_size == 128
        assert config.hnsw_m == 32
        assert config.hnsw_ef_construction == 200
        assert config.hnsw_ef_search == 100
        assert config.vector_dim == 384

    def test_model_config_custom_values(self):
        """Test custom model configuration."""
        config = ModelConfig(
            model_name="custom-model",
            batch_add_size=64,
            hnsw_m=16,
            hnsw_ef_construction=100,
            hnsw_ef_search=50,
            vector_dim=768,
        )
        assert config.model_name == "custom-model"
        assert config.batch_add_size == 64
        assert config.hnsw_m == 16
        assert config.hnsw_ef_construction == 100
        assert config.hnsw_ef_search == 50
        assert config.vector_dim == 768


class TestSecurityConfig:
    """Test SecurityConfig validation and functionality."""

    def test_security_config_defaults(self):
        """Test default security configuration."""
        config = SecurityConfig()
        assert config.encrypt_at_rest is False
        assert config.encryption_key == ""
        assert config.filter_pii is True
        assert config.max_text_length == 10_000
        assert config.rate_limit_per_minute == 1_000
        assert config.api_token == "your-secret-token-change-me"

    def test_security_config_api_token_validation(self):
        """Test API token validation."""
        # Valid token
        config = SecurityConfig(api_token="valid-token-12345678")
        assert config.api_token == "valid-token-12345678"

        # Invalid token (too short)
        with pytest.raises(ValidationError) as exc_info:
            SecurityConfig(api_token="short")
        assert "API token must be at least 8 characters long" in str(exc_info.value)

    def test_security_config_encryption_key_validation(self):
        """Test encryption key validation."""
        # Valid key
        valid_key = Fernet.generate_key().decode()
        config = SecurityConfig(encryption_key=valid_key)
        assert config.encryption_key == valid_key

        # Invalid key
        with pytest.raises(ValidationError) as exc_info:
            SecurityConfig(encryption_key="invalid-key")
        assert "Invalid encryption key" in str(exc_info.value)

    def test_security_config_custom_values(self):
        """Test custom security configuration."""
        valid_key = Fernet.generate_key().decode()
        config = SecurityConfig(
            encrypt_at_rest=True,
            encryption_key=valid_key,
            filter_pii=False,
            max_text_length=5000,
            rate_limit_per_minute=500,
            api_token="custom-token-87654321",
        )
        assert config.encrypt_at_rest is True
        assert config.encryption_key == valid_key
        assert config.filter_pii is False
        assert config.max_text_length == 5000
        assert config.rate_limit_per_minute == 500
        assert config.api_token == "custom-token-87654321"


class TestPerformanceConfig:
    """Test PerformanceConfig validation and functionality."""

    def test_performance_config_defaults(self):
        """Test default performance configuration."""
        config = PerformanceConfig()
        assert config.max_workers == 4
        assert config.cache_size == 1000
        assert config.cache_ttl_seconds == 300
        assert config.rebuild_interval_seconds == 3600

    def test_performance_config_max_workers_validation(self):
        """Test max_workers validation."""
        # Valid values
        config = PerformanceConfig(max_workers=8)
        assert config.max_workers == 8

        # Invalid values
        with pytest.raises(ValidationError) as exc_info:
            PerformanceConfig(max_workers=0)
        assert "max_workers must be between 1 and 32" in str(exc_info.value)

        with pytest.raises(ValidationError) as exc_info:
            PerformanceConfig(max_workers=50)
        assert "max_workers must be between 1 and 32" in str(exc_info.value)

    def test_performance_config_custom_values(self):
        """Test custom performance configuration."""
        config = PerformanceConfig(
            max_workers=8, cache_size=2000, cache_ttl_seconds=600, rebuild_interval_seconds=7200
        )
        assert config.max_workers == 8
        assert config.cache_size == 2000
        assert config.cache_ttl_seconds == 600
        assert config.rebuild_interval_seconds == 7200


class TestReliabilityConfig:
    """Test ReliabilityConfig validation and functionality."""

    def test_reliability_config_defaults(self):
        """Test default reliability configuration."""
        config = ReliabilityConfig()
        assert config.max_retries == 3
        assert config.retry_delay_seconds == 1.0
        assert config.backup_enabled is True
        assert config.backup_interval_hours == 24

    def test_reliability_config_custom_values(self):
        """Test custom reliability configuration."""
        config = ReliabilityConfig(
            max_retries=5, retry_delay_seconds=2.5, backup_enabled=False, backup_interval_hours=48
        )
        assert config.max_retries == 5
        assert config.retry_delay_seconds == 2.5
        assert config.backup_enabled is False
        assert config.backup_interval_hours == 48


class TestAPIConfig:
    """Test APIConfig validation and functionality."""

    def test_api_config_defaults(self):
        """Test default API configuration."""
        config = APIConfig()
        assert config.host == "0.0.0.0"
        assert config.port == 8000
        assert config.enable_cors is True
        assert config.enable_api is True
        assert config.cors_origins == ["*"]

    def test_api_config_port_validation(self):
        """Test port validation."""
        # Valid port
        config = APIConfig(port=8080)
        assert config.port == 8080

        # Invalid ports
        with pytest.raises(ValidationError) as exc_info:
            APIConfig(port=500)
        assert "port must be between 1024 and 65535" in str(exc_info.value)

        with pytest.raises(ValidationError) as exc_info:
            APIConfig(port=70000)
        assert "port must be between 1024 and 65535" in str(exc_info.value)

    def test_api_config_custom_values(self):
        """Test custom API configuration."""
        config = APIConfig(
            host="127.0.0.1",
            port=9000,
            enable_cors=False,
            enable_api=False,
            cors_origins=["https://example.com", "https://app.example.com"],
        )
        assert config.host == "127.0.0.1"
        assert config.port == 9000
        assert config.enable_cors is False
        assert config.enable_api is False
        assert config.cors_origins == ["https://example.com", "https://app.example.com"]


class TestMonitoringConfig:
    """Test MonitoringConfig validation and functionality."""

    def test_monitoring_config_defaults(self):
        """Test default monitoring configuration."""
        config = MonitoringConfig()
        assert config.enable_metrics is True
        assert config.enable_rate_limiting is True
        assert config.prom_port == 9100
        assert config.health_check_interval == 30
        assert config.log_level == "INFO"

    def test_monitoring_config_prom_port_validation(self):
        """Test prometheus port validation."""
        # Valid port
        config = MonitoringConfig(prom_port=9090)
        assert config.prom_port == 9090

        # Invalid ports
        with pytest.raises(ValidationError) as exc_info:
            MonitoringConfig(prom_port=500)
        assert "prom_port must be between 1024 and 65535" in str(exc_info.value)

        with pytest.raises(ValidationError) as exc_info:
            MonitoringConfig(prom_port=70000)
        assert "prom_port must be between 1024 and 65535" in str(exc_info.value)

    def test_monitoring_config_custom_values(self):
        """Test custom monitoring configuration."""
        config = MonitoringConfig(
            enable_metrics=False,
            enable_rate_limiting=False,
            prom_port=9090,
            health_check_interval=60,
            log_level="DEBUG",
        )
        assert config.enable_metrics is False
        assert config.enable_rate_limiting is False
        assert config.prom_port == 9090
        assert config.health_check_interval == 60
        assert config.log_level == "DEBUG"


class TestUnifiedSettings:
    """Test UnifiedSettings integration and functionality."""

    def test_unified_settings_defaults(self):
        """Test default unified settings."""
        settings = UnifiedSettings()
        assert settings.version == "0.8.0a0"
        assert settings.profile == "development"
        assert isinstance(settings.database, DatabaseConfig)
        assert isinstance(settings.model, ModelConfig)
        assert isinstance(settings.security, SecurityConfig)
        assert isinstance(settings.performance, PerformanceConfig)
        assert isinstance(settings.reliability, ReliabilityConfig)
        assert isinstance(settings.api, APIConfig)
        assert isinstance(settings.monitoring, MonitoringConfig)

    def test_unified_settings_directory_creation(self):
        """Test that directories are created automatically."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "db" / "test.db"
            vec_path = Path(tmpdir) / "vectors" / "test.vec"
            cache_path = Path(tmpdir) / "cache" / "test.cache"

            UnifiedSettings(
                database=DatabaseConfig(db_path=db_path, vec_path=vec_path, cache_path=cache_path)
            )

            assert db_path.parent.exists()
            assert vec_path.parent.exists()
            assert cache_path.parent.exists()

    def test_unified_settings_encryption_key_generation(self):
        """Test automatic encryption key generation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"

            settings = UnifiedSettings(
                database=DatabaseConfig(db_path=db_path),
                security=SecurityConfig(
                    encrypt_at_rest=True,
                    encryption_key="",  # Empty key should trigger generation
                ),
            )

            assert settings.security.encryption_key != ""
            assert len(settings.security.encryption_key) > 0

            # Test that the generated key is valid
            Fernet(settings.security.encryption_key.encode())

    def test_unified_settings_for_testing(self):
        """Test testing preset configuration."""
        settings = UnifiedSettings.for_testing()
        assert settings.performance.max_workers == 2
        assert settings.performance.cache_size == 100
        assert settings.performance.cache_ttl_seconds == 10
        assert settings.api.port == 0
        assert settings.monitoring.enable_metrics is False
        assert settings.monitoring.health_check_interval == 5
        assert settings.security.api_token == "test-token-12345678"
        assert settings.security.rate_limit_per_minute == 10_000

    def test_unified_settings_for_production(self):
        """Test production preset configuration."""
        settings = UnifiedSettings.for_production()
        assert settings.database.connection_pool_size == 20
        assert settings.performance.max_workers == 8
        assert settings.performance.cache_size == 5_000
        assert settings.security.encrypt_at_rest is True
        assert settings.security.filter_pii is True
        assert settings.security.rate_limit_per_minute == 1_000
        assert settings.monitoring.enable_metrics is True
        assert settings.monitoring.log_level == "INFO"

    def test_unified_settings_for_development(self):
        """Test development preset configuration."""
        settings = UnifiedSettings.for_development()
        assert settings.database.connection_pool_size == 5
        assert settings.performance.max_workers == 2
        assert settings.performance.cache_size == 500
        assert settings.monitoring.enable_metrics is True
        assert settings.monitoring.log_level == "DEBUG"
        assert settings.monitoring.health_check_interval == 10
        assert settings.api.enable_cors is True

    def test_unified_settings_get_database_url(self):
        """Test database URL generation."""
        settings = UnifiedSettings()
        url = settings.get_database_url()
        assert url.startswith("sqlite:///")
        assert str(settings.database.db_path) in url

    def test_unified_settings_validate_production_ready(self):
        """Test production readiness validation."""
        # Default settings should have issues
        settings = UnifiedSettings()
        issues = settings.validate_production_ready()
        assert len(issues) > 0
        assert "API token is not set" in issues

        # Production-ready settings should have no issues
        settings = UnifiedSettings.for_production()
        settings.security.api_token = "production-token-12345678"
        issues = settings.validate_production_ready()
        assert len(issues) == 0

    def test_unified_settings_get_config_summary(self):
        """Test configuration summary generation."""
        settings = UnifiedSettings()
        summary = settings.get_config_summary()

        assert "database" in summary
        assert "model" in summary
        assert "security" in summary
        assert "performance" in summary
        assert "api" in summary
        assert "monitoring" in summary

        # Check that sensitive data is not included
        assert "api_token" not in str(summary)
        assert "encryption_key" not in str(summary)

        # Check that non-sensitive flags are included
        assert summary["security"]["encrypt_at_rest"] is False
        assert summary["security"]["filter_pii"] is True
        assert summary["security"]["has_key"] is False  # No key set by default

    def test_unified_settings_save_and_load_from_file(self):
        """Test saving and loading configuration from file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            config_path = Path(f.name)

        try:
            settings = UnifiedSettings.for_testing()
            settings.save_to_file(config_path)

            assert config_path.exists()

            # Verify file contents
            with open(config_path) as f:
                data = json.load(f)

            assert "database" in data
            assert "model" in data
            assert data["performance"]["max_workers"] == 2

            # Test loading (note: this creates a new settings instance)
            loaded_settings = UnifiedSettings.load_from_file(config_path)
            assert loaded_settings.performance.max_workers == 2

        finally:
            config_path.unlink(missing_ok=True)


class TestGetSettings:
    """Test get_settings factory function."""

    def test_get_settings_default(self):
        """Test get_settings with default environment."""
        settings = get_settings()
        assert isinstance(settings, UnifiedSettings)

    def test_get_settings_development(self):
        """Test get_settings with development environment."""
        settings = get_settings("development")
        assert settings.monitoring.log_level == "DEBUG"
        assert settings.performance.max_workers == 2

    def test_get_settings_production(self):
        """Test get_settings with production environment."""
        settings = get_settings("production")
        assert settings.performance.max_workers == 8
        assert settings.security.encrypt_at_rest is True

    def test_get_settings_testing(self):
        """Test get_settings with testing environment."""
        settings = get_settings("testing")
        assert settings.api.port == 0
        assert settings.monitoring.enable_metrics is False

    def test_get_settings_unknown_environment(self):
        """Test get_settings with unknown environment."""
        settings = get_settings("unknown")
        assert isinstance(settings, UnifiedSettings)
        # Should fall back to default settings
        assert settings.version == "0.8.0a0"


class TestEnvironmentVariables:
    """Test environment variable integration."""

    def test_settings_from_environment_variables(self, monkeypatch):
        """Test that settings are loaded from environment variables."""
        monkeypatch.setenv("DATABASE__DB_PATH", "/tmp/test.db")
        monkeypatch.setenv("API__PORT", "9000")
        monkeypatch.setenv("SECURITY__API_TOKEN", "env-token-12345678")
        monkeypatch.setenv("PERFORMANCE__MAX_WORKERS", "16")
        monkeypatch.setenv("MONITORING__LOG_LEVEL", "ERROR")

        settings = UnifiedSettings()
        assert settings.database.db_path == Path("/tmp/test.db")
        assert settings.api.port == 9000
        assert settings.security.api_token == "env-token-12345678"
        assert settings.performance.max_workers == 16
        assert settings.monitoring.log_level == "ERROR"

    def test_settings_from_dotenv_file(self, monkeypatch):
        """Test that settings are loaded from .env file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write("API__HOST=192.168.1.100\n")
            f.write("API__PORT=8080\n")
            f.write("SECURITY__FILTER_PII=false\n")
            f.write("PERFORMANCE__CACHE_SIZE=5000\n")
            env_path = Path(f.name)

        try:
            # Mock the default .env file location
            monkeypatch.setattr(
                "memory_system.config.settings.UnifiedSettings.model_config",
                {"env_file": str(env_path)},
            )
            settings = UnifiedSettings()
            assert settings.api.host == "192.168.1.100"
            assert settings.api.port == 8080
            assert settings.security.filter_pii is False
            assert settings.performance.cache_size == 5000
        finally:
            (os.unlink(env_path),)
