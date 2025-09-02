"""Web scraper for Althingi website integration."""

from typing import List, Dict, Any, Optional
import requests
from lxml import html, etree
from django.conf import settings
from lagasafn.utils import traditionalize_law_nr


class AlthingiScraper:
    """Handles web scraping from Althingi website."""
    
    def __init__(self):
        self._remote_contents: Dict[str, Any] = {}
    
    def get_law_box(self, nr: int, year: int, box_title: str) -> List[Dict[str, Any]]:
        """Get law box information from Althingi website."""
        if "law_box" not in settings.FEATURES or not settings.FEATURES["law_box"]:
            return []
        
        box_links = []
        
        url = f"https://www.althingi.is/lagas/nuna/{year}{traditionalize_law_nr(nr)}.html"
        
        # Get content (with caching)
        if url in self._remote_contents:
            content = self._remote_contents[url]
        else:
            response = requests.get(url)
            if response.status_code != 200:
                return []
            
            content = html.fromstring(response.content)
            self._remote_contents[url] = content
        
        # Find the specific box section
        h5_elements = content.xpath(f"//h5[normalize-space(text())='{box_title}']")
        if not h5_elements:
            return box_links
        
        ul_element = h5_elements[0].getnext()
        if ul_element is None or ul_element.tag != 'ul':
            return box_links
        
        # Extract links
        for li_element in ul_element.xpath("li"):
            a_element = li_element.find("a")
            if a_element is None:
                continue
            
            try:
                doc_nr, doc_parliament = self._get_doc_nr_and_parliament(
                    a_element.attrib["href"]
                )
                issue_status, proposer = self._get_issue_status_from_doc(
                    doc_nr, doc_parliament
                )
                
                box_links.append({
                    "link": a_element.attrib["href"],
                    "law_name": a_element.attrib.get("title", ""),
                    "document_name": a_element.text or "",
                    "date": (a_element.tail or "").lstrip(", "),
                    "issue_status": issue_status,
                    "proposer": proposer,
                })
            except Exception:
                # Skip malformed entries
                continue
        
        return box_links
    
    def get_ongoing_issues(self, nr: int, year: int) -> List[Dict[str, Any]]:
        """Get ongoing issues for a law."""
        return self.get_law_box(nr, year, "Frumvörp til breytinga á lögunum:")
    
    def _get_doc_nr_and_parliament(self, href: str) -> tuple[int, int]:
        """Extract document number and parliament from URL."""
        pieces = href.split("/")
        parliament = int(pieces[4])
        doc_nr = int(pieces[6].rstrip(".html"))
        return doc_nr, parliament
    
    def _get_issue_status_from_doc(self, doc_nr: int, parliament: int) -> tuple[str, Optional[Dict[str, str]]]:
        """Get issue status and proposer from document."""
        # Get document XML
        response = requests.get(
            f"https://www.althingi.is/altext/xml/thingskjol/thingskjal/?lthing={parliament}&skjalnr={doc_nr}"
        )
        response.encoding = "utf-8"
        
        doc_xml = etree.fromstring(response.content)
        
        # Extract issue information
        issue_node = doc_xml.xpath("/þingskjal/málalisti/mál")[0]
        issue_nr = int(issue_node.attrib["málsnúmer"])
        issue_parliament = int(issue_node.attrib["þingnúmer"])
        
        # Extract proposer information
        proposer = None
        proposer_nodes = doc_xml.xpath("/þingskjal/þingskjal/flutningsmenn/flutningsmaður")
        if proposer_nodes:
            proposer_node = proposer_nodes[0]
            proposer_nr = int(proposer_node.attrib["id"])
            proposer = {
                "name": proposer_node.find("nafn").text,
                "link": f"https://www.althingi.is/altext/cv/is/?nfaerslunr={proposer_nr}",
            }
        
        # Get issue status
        response = requests.get(
            f"https://www.althingi.is/altext/xml/thingmalalisti/thingmal/?lthing={issue_parliament}&malnr={issue_nr}"
        )
        response.encoding = "utf-8"
        
        issue_xml = etree.fromstring(response.content)
        status = issue_xml.xpath("/þingmál/mál/staðamáls")[0].text
        
        return status, proposer