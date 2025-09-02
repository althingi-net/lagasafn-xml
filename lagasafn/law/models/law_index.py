"""Law index collection model."""

from typing import List
from pydantic import BaseModel
from .law_index_info import LawIndexInfo
from .law_entry import LawEntry


class LawIndex(BaseModel):
    """Collection of law entries with metadata."""
    
    info: LawIndexInfo = LawIndexInfo()
    laws: List[LawEntry] = []