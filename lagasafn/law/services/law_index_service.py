"""Service for law index operations."""

from datetime import datetime
from functools import cache
from typing import List
from lagasafn.exceptions import LawException
from ..models.law_index import LawIndex
from ..models.law_index_info import LawIndexInfo
from ..repositories.law_index_repository import LawIndexRepository
from ..factories.law_entry_factory import LawEntryFactory


class LawIndexService:
    """Handles law index business logic."""
    
    @staticmethod
    @cache
    def get_index(codex_version: str) -> LawIndex:
        """Get complete law index for a codex version."""
        # Get raw data
        xml_index = LawIndexRepository.get_index_xml(codex_version)
        problems_map = LawIndexRepository.get_problems_data(codex_version)
        metadata = LawIndexRepository.extract_index_metadata(xml_index)
        
        # Create info object
        info = LawIndexInfo(
            codex_version=codex_version,
            date_from=metadata['date_from'],
            date_to=metadata['date_to'],
            total_count=metadata['total_count'],
            empty_count=metadata['empty_count'],
            non_empty_count=metadata['non_empty_count']
        )
        
        # Create law entries
        laws = []
        for node_law_entry in xml_index.findall("law-entries/law-entry"):
            # Skip empty laws
            if node_law_entry.find("meta/is-empty").text == "true":
                continue
            
            # Get problems for this law
            identifier = node_law_entry.attrib["identifier"]
            problems = problems_map.get(identifier, {})
            
            # Create law entry
            law_entry = LawEntryFactory.from_xml_node(
                node_law_entry, codex_version, problems
            )
            laws.append(law_entry)
        
        return LawIndex(info=info, laws=laws)
    
    @staticmethod
    @cache
    def get_codex_versions() -> List[str]:
        """Get all available codex versions."""
        return LawIndexRepository.get_codex_versions()
    
    @staticmethod
    def get_codex_version_at_date(timing: datetime) -> str:
        """Find the appropriate codex version for a given date."""
        result = ""
        codex_versions = LawIndexService.get_codex_versions()
        
        # Check versions in reverse order (newest first)
        for codex_version in reversed(codex_versions):
            index = LawIndexService.get_index(codex_version)
            if timing >= index.info.date_to:
                result = codex_version
                break
        
        if not result:
            raise LawException(f"Could not determine codex version at date: {timing}")
        
        return result
    
    @staticmethod
    def content_search(search_string: str, codex_version: str) -> List[dict]:
        """Search for content across all laws in an index."""
        from lagasafn.utils import search_xml_doc, generate_legal_reference
        from lagasafn.pathing import make_xpath_from_node
        from ..factories.law_document_factory import LawDocumentFactory
        from ..repositories.law_document_repository import LawDocumentRepository
        
        results = []
        index = LawIndexService.get_index(codex_version)
        
        for law_entry in index.laws:
            # Get law XML
            law_xml = LawDocumentRepository.get_law_xml(
                codex_version, law_entry.year, str(law_entry.nr)
            )
            
            # Search for content
            nodes = search_xml_doc(law_xml, search_string)
            
            findings = []
            for node in nodes:
                legal_reference = ""
                try:
                    legal_reference = generate_legal_reference(
                        node.getparent(), skip_law=True
                    )
                except:
                    pass
                
                findings.append({
                    "legal_reference": legal_reference,
                    "node": node,
                    "xpath": make_xpath_from_node(node),
                })
            
            if findings:
                results.append({
                    "law_entry": law_entry,
                    "findings": findings,
                })
        
        return results