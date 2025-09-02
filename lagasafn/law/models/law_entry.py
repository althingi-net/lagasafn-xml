"""Law entry model for index listings."""

from pydantic import BaseModel
from lagasafn.constants import CURRENT_PARLIAMENT_VERSION


class LawEntry(BaseModel):
    """A legal entry in the law index."""
    
    codex_version: str = CURRENT_PARLIAMENT_VERSION
    identifier: str = ""
    name: str = ""
    chapter_count: int = 0
    art_count: int = 0
    nr: int = 0
    year: int = 0
    problems: dict = {}

    def display_content_success(self) -> str:
        """Display content success as percentage."""
        if "content" not in self.problems:
            return "unknown"

        from math import floor
        content_success = self.problems["content"]["success"]
        return f"{float(floor(content_success * 10000) / 100):.2f}%"

    def content_success(self) -> float:
        """Get the content success rate."""
        return self.problems["content"]["success"]

    def original_url(self) -> str:
        """Reconstruct URL to original HTML on Althingi's website."""
        from lagasafn.utils import traditionalize_law_nr
        
        original_law_filename = f"{self.year}{traditionalize_law_nr(self.nr)}.html"
        return f"https://www.althingi.is/lagas/{CURRENT_PARLIAMENT_VERSION}/{original_law_filename}"

    def __str__(self) -> str:
        return self.identifier