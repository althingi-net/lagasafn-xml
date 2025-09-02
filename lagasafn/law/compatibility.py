"""
Compatibility layer for backward compatibility during transition.

This module provides the old interface while using the new modular structure.
It maintains the original API so existing code continues to work.
"""

from .services.law_index_service import LawIndexService
from .services.law_document_service import LawDocumentService
from .factories.law_document_factory import LawDocumentFactory
from .external.althingi_scraper import AlthingiScraper


class LawManager:
    """Backward-compatible interface for LawManager."""
    
    @staticmethod
    def index(codex_version: str):
        """Get law index - delegates to new service."""
        return LawIndexService.get_index(codex_version)
    
    @staticmethod
    def codex_versions():
        """Get codex versions - delegates to new service."""
        return LawIndexService.get_codex_versions()
    
    @staticmethod
    def codex_version_at_date(timing):
        """Get codex version at date - delegates to new service.""" 
        return LawIndexService.get_codex_version_at_date(timing)
    
    @staticmethod
    def content_search(search_string: str, codex_version: str):
        """Content search - delegates to new service."""
        return LawIndexService.content_search(search_string, codex_version)


class Law:
    """
    Backward-compatible interface for Law class.
    
    This maintains the old API while using the new modular structure internally.
    """
    
    def __init__(self, identifier: str, codex_version: str):
        # Use new factory to create the law document
        self._law_document = LawDocumentFactory.from_identifier(identifier, codex_version)
        self._scraper = AlthingiScraper()
    
    # Delegate properties to the law document
    @property
    def identifier(self):
        return self._law_document.identifier
    
    @property
    def codex_version(self):
        return self._law_document.codex_version
    
    @property
    def nr(self):
        return str(self._law_document.nr)
    
    @property
    def year(self):
        return self._law_document.year
    
    def name(self):
        return self._law_document.name
    
    def superchapters(self):
        return self._law_document.superchapters
    
    def chapters(self):
        return self._law_document.chapters
    
    def articles(self):
        return self._law_document.articles
    
    def path(self):
        from lagasafn.constants import XML_FILENAME
        return XML_FILENAME % (self.codex_version, self.year, self.nr)
    
    def xml(self):
        return LawDocumentService.get_xml_content(self._law_document)
    
    def xml_text(self):
        return LawDocumentService.get_xml_text(self._law_document)
    
    def html_text(self):
        return LawDocumentService.get_html_text(self._law_document)
    
    def iter_structure(self):
        return LawDocumentService.iter_structure(self._law_document)
    
    def get_references(self):
        return LawDocumentService.get_references(self._law_document.nr, self._law_document.year)
    
    def interim_adverts(self):
        return LawDocumentService.get_interim_adverts(self._law_document)
    
    def get_ongoing_issues(self):
        return self._scraper.get_ongoing_issues(self._law_document.nr, self._law_document.year)
    
    def editor_url(self):
        return self._law_document.editor_url()
    
    def __str__(self):
        return str(self._law_document)