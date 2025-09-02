"""Repository for law document operations."""

import os
import re
from functools import cache
from typing import Optional
from lxml import etree
from lagasafn.constants import XML_FILENAME, XML_REFERENCES_FILENAME, CURRENT_PARLIAMENT_VERSION
from lagasafn.exceptions import NoSuchLawException


class LawDocumentRepository:
    """Handles data access for individual law documents."""
    
    @staticmethod
    def get_law_path(codex_version: str, year: int, nr: str) -> str:
        """Get file path for a law XML file."""
        return XML_FILENAME % (codex_version, year, nr)
    
    @staticmethod
    def law_exists(codex_version: str, year: int, nr: str) -> bool:
        """Check if a law file exists."""
        return os.path.isfile(
            LawDocumentRepository.get_law_path(codex_version, year, nr)
        )
    
    @staticmethod
    @cache
    def get_law_xml(codex_version: str, year: int, nr: str) -> etree._ElementTree:
        """Load and parse law XML file."""
        path = LawDocumentRepository.get_law_path(codex_version, year, nr)
        
        if not os.path.isfile(path):
            raise NoSuchLawException(f"Could not find law '{nr}/{year}'")
            
        return etree.parse(path)
    
    @staticmethod
    def get_law_xml_text(codex_version: str, year: int, nr: str) -> str:
        """Get raw XML text content of law."""
        path = LawDocumentRepository.get_law_path(codex_version, year, nr)
        
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    
    @staticmethod
    def get_law_html_text(codex_version: str, year: int, nr: str) -> str:
        """Convert law XML to HTML text."""
        xml_text = LawDocumentRepository.get_law_xml_text(codex_version, year, nr)
        
        # Convert self-closing XML tags to HTML
        e = re.compile(r"<([a-z\-]+)( ?)([^>]*)\/>")
        result = e.sub(r"<\1\2\3></\1>", xml_text)
        result = result.replace('<?xml version="1.0" encoding="utf-8"?>', "").strip()
        
        return result
    
    @staticmethod
    @cache
    def get_references_xml() -> etree._Element:
        """Load and parse references XML file."""
        return etree.parse(
            XML_REFERENCES_FILENAME % CURRENT_PARLIAMENT_VERSION
        ).getroot()
    
    @staticmethod
    def get_law_references(nr: str, year: int) -> list:
        """Get references for a specific law."""
        references_xml = LawDocumentRepository.get_references_xml()
        
        nodes = references_xml.xpath(
            f"/references/law-ref-entry[@law-nr='{nr}' and @law-year='{year}']/node"
        )
        
        references = []
        for node in nodes:
            for xml_ref in node.findall("reference"):
                references.append({
                    "location": node.attrib["location"],
                    "link_label": xml_ref.attrib["link-label"],
                    "inner_reference": xml_ref.attrib["inner-reference"],
                    "law_nr": xml_ref.attrib["law-nr"],
                    "law_year": xml_ref.attrib["law-year"],
                })
        
        return references