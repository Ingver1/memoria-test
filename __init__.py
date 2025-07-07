"""
Unified Memory System v0.8.0a0
==========================

Enterprise-grade memory system with vector search, FastAPI, and comprehensive monitoring.

Author: Enhanced Memory Team
License: Apache License Version 2.0
"""

__version__ = "0.8.0a0"
__author__ = "Enhanced Memory Team"
__license__ = "Apache License Version 2.0"

from memory_system.api.app import create_app
from memory_system.config.settings import UnifiedSettings
from memory_system.core.store import EnhancedMemoryStore

__all__ = [
    "EnhancedMemoryStore",
    "create_app",
    "UnifiedSettings",
]
