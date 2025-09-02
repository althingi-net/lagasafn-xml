"""Factory for creating LawDocument instances."""

from typing import Dict, Any, List
from lxml import etree
from lagasafn.exceptions import LawException
from ..models.law_document import LawDocument
from ..repositories.law_document_repository import LawDocumentRepository


class LawDocumentFactory:
    """Creates LawDocument instances from various sources."""
    
    @staticmethod
    def from_identifier(identifier: str, codex_version: str) -> LawDocument:
        """Create LawDocument from identifier string (e.g., '6/2025')."""
        try:
            nr, year_str = identifier.split("/")
            year = int(year_str)
        except (ValueError, TypeError):
            raise LawException(f"Invalid identifier format: '{identifier}'")
        
        if not LawDocumentRepository.law_exists(codex_version, year, nr):
            from lagasafn.exceptions import NoSuchLawException
            raise NoSuchLawException(f"Could not find law '{identifier}'")
        
        # Load XML to get basic info
        xml_tree = LawDocumentRepository.get_law_xml(codex_version, year, nr)
        xml_root = xml_tree.getroot()
        name = xml_root.find("name").text or ""
        
        return LawDocument(
            identifier=identifier,
            codex_version=codex_version,
            nr=int(nr),
            year=year,
            name=name,
            superchapters=LawDocumentFactory._extract_superchapters(xml_root),
            chapters=LawDocumentFactory._extract_chapters(xml_root),
            articles=LawDocumentFactory._extract_articles(xml_root)
        )
    
    @staticmethod
    def _extract_superchapters(xml_root: etree._Element) -> List[Dict[str, Any]]:
        """Extract superchapter structure from XML."""
        superchapters = []
        
        for superchapter in xml_root.findall("superchapter"):
            _superchapter = {
                "nr": superchapter.attrib["nr"],
                "chapters": [],
            }
            
            # Add nr-title if exists
            nr_title = superchapter.find("nr-title")
            if nr_title is not None:
                _superchapter["nr_title"] = nr_title.text
            
            # Add name if exists
            name = superchapter.find("name")
            if name is not None:
                _superchapter["name"] = name.text
            
            # Add chapters
            for chapter in superchapter.findall("chapter"):
                _chapter = LawDocumentFactory._make_chapter(chapter)
                _superchapter["chapters"].append(_chapter)
            
            superchapters.append(_superchapter)
        
        return superchapters
    
    @staticmethod
    def _extract_chapters(xml_root: etree._Element) -> List[Dict[str, Any]]:
        """Extract chapter structure from XML."""
        chapters = []
        
        for chapter in xml_root.findall("chapter"):
            chapters.append(LawDocumentFactory._make_chapter(chapter))
        
        return chapters
    
    @staticmethod
    def _extract_articles(xml_root: etree._Element) -> List[Dict[str, Any]]:
        """Extract article structure from XML."""
        articles = []
        
        for art in xml_root.findall("art"):
            articles.append(LawDocumentFactory._make_article(art))
        
        return articles
    
    @staticmethod
    def _make_chapter(chapter: etree._Element) -> Dict[str, Any]:
        """Create chapter dictionary from XML node."""
        _chapter = {
            "nr": chapter.attrib["nr"],
            "articles": [],
        }
        
        # Add nr-title if exists
        nr_title = chapter.find("nr-title")
        if nr_title is not None:
            _chapter["nr_title"] = nr_title.text
        
        # Add name if exists
        name = chapter.find("name")
        if name is not None:
            _chapter["name"] = name.text
        
        # Add articles
        for art in chapter.findall("art"):
            _article = LawDocumentFactory._make_article(art)
            _chapter["articles"].append(_article)
        
        return _chapter
    
    @staticmethod
    def _make_article(art: etree._Element) -> Dict[str, Any]:
        """Create article dictionary from XML node."""
        _art = {
            "nr": art.attrib["nr"],
            "nr_title": LawDocument.toc_name(art.find("nr-title").text),
        }
        
        # Add name if exists
        art_name = art.find("name")
        if art_name is not None:
            _art["name"] = LawDocument.toc_name(art_name.text)
        
        return _art