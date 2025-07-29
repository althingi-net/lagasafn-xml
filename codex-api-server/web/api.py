from ninja import NinjaAPI
from django.http import HttpRequest
from django.conf import settings
from typing import List, Dict
import xml.etree.ElementTree as ET

api = NinjaAPI()

@api.get("/")
def hello(request: HttpRequest) -> str:
    return "Hello World"

@api.get("/xml-files")
def list_xml_files(request: HttpRequest) -> List[Dict[str, str]]:
    index_file = settings.DATA_DIR / "xml" / settings.CURRENT_PARLIAMENT_VERSION / "index.xml"
    
    try:
        tree = ET.parse(index_file)
        root = tree.getroot()
        
        laws = []
        for law_entry in root.findall(".//law-entry"):
            identifier = law_entry.get("identifier", "")
            name_elem = law_entry.find("name")
            name = name_elem.text if name_elem is not None else ""
            
            meta = law_entry.find("meta")
            if meta is not None:
                chapter_count_elem = meta.find("chapter-count")
                art_count_elem = meta.find("art-count")
                is_empty_elem = meta.find("is-empty")
                
                chapter_count = chapter_count_elem.text if chapter_count_elem is not None else "0"
                art_count = art_count_elem.text if art_count_elem is not None else "0"
                is_empty = is_empty_elem.text if is_empty_elem is not None else "true"
                
                status = "OK" if is_empty.lower() == "false" else "Empty"
            else:
                chapter_count = "0"
                art_count = "0"
                status = "Empty"
            
            laws.append({
                "nr": identifier,
                "name": name,
                "ch": chapter_count,
                "art": art_count,
                "status": status
            })
        
        return laws
        
    except (FileNotFoundError, ET.ParseError):
        return []