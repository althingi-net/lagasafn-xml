"""Service for law document operations."""

from typing import List, Dict, Any, Iterator
from lxml import etree
from ..models.law_document import LawDocument
from ..repositories.law_document_repository import LawDocumentRepository
from ..factories.law_document_factory import LawDocumentFactory


class LawDocumentService:
    """Handles law document business logic."""
    
    @staticmethod
    def get_law_document(identifier: str, codex_version: str) -> LawDocument:
        """Get a complete law document."""
        # Create base document
        law_document = LawDocumentFactory.from_identifier(identifier, codex_version)
        
        # Enrich with references
        references = LawDocumentService.get_references(law_document.nr, law_document.year)
        law_document.references = references
        
        return law_document
    
    @staticmethod
    def get_references(nr: int, year: int) -> List[Dict[str, Any]]:
        """Get references for a law."""
        return LawDocumentRepository.get_law_references(str(nr), year)
    
    @staticmethod
    def get_xml_content(law_document: LawDocument) -> etree._ElementTree:
        """Get XML content for a law document."""
        return LawDocumentRepository.get_law_xml(
            law_document.codex_version, law_document.year, str(law_document.nr)
        )
    
    @staticmethod
    def get_xml_text(law_document: LawDocument) -> str:
        """Get raw XML text for a law document."""
        return LawDocumentRepository.get_law_xml_text(
            law_document.codex_version, law_document.year, str(law_document.nr)
        )
    
    @staticmethod
    def get_html_text(law_document: LawDocument) -> str:
        """Get HTML text for a law document."""
        return LawDocumentRepository.get_law_html_text(
            law_document.codex_version, law_document.year, str(law_document.nr)
        )
    
    @staticmethod
    def iter_structure(law_document: LawDocument) -> Iterator[etree._Element]:
        """Iterate through law structure for comparisons."""
        xml_tree = LawDocumentService.get_xml_content(law_document)
        xml_root = xml_tree.getroot()
        
        for element in xml_root.iter():
            yield element
    
    @staticmethod
    def get_interim_adverts(law_document: LawDocument) -> List[Dict[str, Any]]:
        """Get interim adverts for a law."""
        # Import here to avoid circular dependencies
        from importlib import import_module
        AdvertManager = getattr(import_module("lagasafn.models.advert"), "AdvertManager")
        
        return AdvertManager.by_affected_law(
            law_document.codex_version, 
            str(law_document.nr), 
            law_document.year
        )