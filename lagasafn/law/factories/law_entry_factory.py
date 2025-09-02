"""Factory for creating LawEntry instances from XML data."""

from typing import Dict, Any
from lxml import etree
from ..models.law_entry import LawEntry


class LawEntryFactory:
    """Creates LawEntry instances from XML nodes."""
    
    @staticmethod
    def from_xml_node(
        node_law_entry: etree._Element, 
        codex_version: str, 
        problems: Dict[str, Any]
    ) -> LawEntry:
        """Create LawEntry from XML index node."""
        identifier = node_law_entry.attrib["identifier"]
        name = node_law_entry.find("name").text
        chapter_count = int(node_law_entry.find("meta/chapter-count").text)
        art_count = int(node_law_entry.find("meta/art-count").text)
        
        nr, year = [int(p) for p in identifier.split("/")]
        
        return LawEntry(
            codex_version=codex_version,
            identifier=identifier,
            name=name,
            chapter_count=chapter_count,
            art_count=art_count,
            nr=nr,
            year=year,
            problems=problems
        )