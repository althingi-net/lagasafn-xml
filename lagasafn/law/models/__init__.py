"""Pure Pydantic models for law domain."""

from .law_entry import LawEntry
from .law_document import LawDocument  
from .law_index import LawIndex
from .law_index_info import LawIndexInfo

__all__ = ['LawEntry', 'LawDocument', 'LawIndex', 'LawIndexInfo']