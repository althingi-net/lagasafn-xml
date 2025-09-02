"""Repository layer for law data access."""

from .law_index_repository import LawIndexRepository
from .law_document_repository import LawDocumentRepository

__all__ = ['LawIndexRepository', 'LawDocumentRepository']