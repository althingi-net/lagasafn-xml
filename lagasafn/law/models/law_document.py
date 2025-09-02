"""Law document model."""

from typing import List, Dict, Any
from pydantic import BaseModel, Field
from lagasafn.constants import CURRENT_PARLIAMENT_VERSION


class LawDocument(BaseModel):
    """A complete law document with content and metadata."""
    
    identifier: str = Field(..., description="Law identifier in format nr/year")
    codex_version: str = CURRENT_PARLIAMENT_VERSION
    nr: int = Field(..., description="Law number")
    year: int = Field(..., description="Law year")
    name: str = Field(default="", description="Law name/title")
    
    # Structure metadata - populated by factory
    superchapters: List[Dict[str, Any]] = Field(default_factory=list)
    chapters: List[Dict[str, Any]] = Field(default_factory=list) 
    articles: List[Dict[str, Any]] = Field(default_factory=list)
    
    # References and issues - populated by services
    references: List[Dict[str, Any]] = Field(default_factory=list)
    ongoing_issues: List[Dict[str, Any]] = Field(default_factory=list)
    interim_adverts: List[Dict[str, Any]] = Field(default_factory=list)

    @staticmethod
    def toc_name(text: str) -> str:
        """Make name clean for table-of-contents display."""
        from django.utils.html import strip_tags
        return strip_tags(text).replace("  ", " ").strip()

    def editor_url(self) -> str:
        """Get URL for law editor."""
        from django.conf import settings
        return settings.EDITOR_URL % (self.year, self.nr)

    def __str__(self) -> str:
        return self.identifier