"""Repository for law index operations."""

import os
from datetime import datetime
from functools import cache
from typing import List, Dict, Any
from lxml import etree
from lagasafn.constants import (
    PROBLEMS_FILENAME, 
    XML_BASE_DIR, 
    XML_INDEX_FILENAME
)


class LawIndexRepository:
    """Handles data access for law indexes."""
    
    @staticmethod
    @cache
    def get_index_xml(codex_version: str) -> etree._Element:
        """Load and parse law index XML file."""
        return etree.parse(
            os.path.join(XML_INDEX_FILENAME % codex_version)
        ).getroot()
    
    @staticmethod
    @cache  
    def get_problems_data(codex_version: str) -> Dict[str, Dict[str, Any]]:
        """Load and parse problems XML into a lookup dictionary."""
        problem_map = {}
        problems = etree.parse(
            os.path.join(PROBLEMS_FILENAME % codex_version)
        ).getroot()
        
        for problem_law_entry in problems.findall("problem-law-entry"):
            statuses = {}
            for status_node in problem_law_entry.findall("status"):
                success = float(status_node.attrib.get("success", "0.0"))
                message = status_node.attrib.get("message")
                
                statuses[status_node.attrib["type"]] = {
                    "success": success,
                    "message": message,
                }
            problem_map[problem_law_entry.attrib["identifier"]] = statuses
        
        return problem_map
    
    @staticmethod
    @cache
    def get_codex_versions() -> List[str]:
        """Get all available codex versions."""
        import re
        from os import listdir
        from os.path import isfile
        
        codex_versions = []
        for item_name in listdir(XML_BASE_DIR):
            # Check directory name format
            if re.match(r"\d{3}[a-z]?", item_name) is None:
                continue
            
            # Check if index file exists
            if not isfile(XML_INDEX_FILENAME % item_name):
                continue
                
            codex_versions.append(item_name)
        
        codex_versions.sort()
        return codex_versions
    
    @staticmethod
    def extract_index_metadata(xml_index: etree._Element) -> Dict[str, Any]:
        """Extract metadata from index XML."""
        return {
            'date_from': datetime.fromisoformat(xml_index.attrib["date-from"]),
            'date_to': datetime.fromisoformat(xml_index.attrib["date-to"]),
            'total_count': int(xml_index.xpath("/index/stats/total-count")[0].text),
            'empty_count': int(xml_index.xpath("/index/stats/empty-count")[0].text),
            'non_empty_count': int(xml_index.xpath("/index/stats/non-empty-count")[0].text),
        }