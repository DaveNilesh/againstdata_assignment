import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
try:
    from .scraper import Scraper
except ImportError:
    from scraper import Scraper

class Discovery:
    def __init__(self):
        self.scraper = Scraper()

    def find_policy_links(self, domain: str) -> dict:
        base_url = f"https://{domain}"
        html = self.scraper.fetch_page(base_url)
        if not html:
             base_url = f"http://{domain}"
             html = self.scraper.fetch_page(base_url)
        
        if not html:
            return {"privacy": None, "terms": None}

        soup = BeautifulSoup(html, 'html.parser')
        links = soup.find_all('a', href=True)
        
        discovered = {"privacy": None, "terms": None}
        
        for link in links:
            href = link['href']
            text = link.get_text().lower()
            full_url = urljoin(base_url, href)
            
            # Simple heuristics
            if not discovered["privacy"] and ("privacy" in text or "privacy" in href.lower()):
                discovered["privacy"] = full_url
            
            if not discovered["terms"] and ("terms" in text or "conditions" in text or "tos" in href.lower()):
                discovered["terms"] = full_url
                
            if discovered["privacy"] and discovered["terms"]:
                break
                
        return discovered
