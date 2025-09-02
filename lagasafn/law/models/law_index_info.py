"""Law index metadata model."""

from datetime import datetime
from pydantic import BaseModel
from lagasafn.constants import CURRENT_PARLIAMENT_VERSION


class LawIndexInfo(BaseModel):
    """Metadata about a law index."""
    
    codex_version: str = CURRENT_PARLIAMENT_VERSION
    date_from: datetime = datetime(1970, 1, 1, 0, 0, 0)
    date_to: datetime = datetime(1970, 1, 1, 0, 0, 0)
    total_count: int = 0
    empty_count: int = 0
    non_empty_count: int = 0