"""Service layer for law business logic."""

from .law_index_service import LawIndexService
from .law_document_service import LawDocumentService

__all__ = ['LawIndexService', 'LawDocumentService']