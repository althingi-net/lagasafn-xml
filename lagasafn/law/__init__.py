"""
Law domain module - handles all law-related functionality.

This module provides a clean interface for working with Icelandic laws,
including models, services, and data access patterns.
"""

# Models - Pure data containers
from .models.law_entry import LawEntry
from .models.law_document import LawDocument
from .models.law_index import LawIndex
from .models.law_index_info import LawIndexInfo

# Services - Business logic
from .services.law_index_service import LawIndexService
from .services.law_document_service import LawDocumentService

# Factories - Model creation
from .factories.law_entry_factory import LawEntryFactory
from .factories.law_document_factory import LawDocumentFactory

__all__ = [
    # Models
    'LawEntry',
    'LawDocument', 
    'LawIndex',
    'LawIndexInfo',
    # Services
    'LawIndexService',
    'LawDocumentService',
    # Factories
    'LawEntryFactory',
    'LawDocumentFactory',
]