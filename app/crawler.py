from typing import Dict, List, Any, Optional
import requests
import time
import json
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup
import cloudscraper


# Modules
from app.data_models import CrawlConfig, CrawlResult
from app.javascript_renderer import JavaScriptRenderer
from app.extraction_strategies import ExtractionStrategy, GenericStrategy, SelectorStrategy, ProductStrategy, ArticleStrategy


#==================== Crawler ====================

class WebCrawler:
    """Main crawler engine"""
    
    def __init__(self, config: CrawlConfig, strategy: ExtractionStrategy):
        self.config = config
        self.strategy = strategy
        self.visited = set()
        self.results = []
        self.session = requests.Session()
        
        headers = {
            'User-Agent': config.user_agent
        }
        if config.headers:
            headers.update(config.headers)
        self.session.headers.update(headers)
    
    def crawl(self) -> List[CrawlResult]:
        """Start crawling from the initial URL"""
        self._crawl_recursive(self.config.url, 0)
        return self.results
    
    def _crawl_recursive(self, url: str, depth: int):
        """Recursively crawl pages"""
        if depth > self.config.max_depth or len(self.results) >= self.config.max_pages:
            return
        
        if url in self.visited:
            return
        
        self.visited.add(url)
        
        try:
            time.sleep(self.config.delay)
            response = self.session.get(url, timeout=self.config.timeout)
            if response.status_code == 403:
                # Handle Cloudflare protection
                scraper = cloudscraper.create_scraper()
                response = scraper.get(url, timeout=self.config.timeout)
            
            soup = BeautifulSoup(response.content, 'html.parser')
            with open('log.json', 'w') as f:
                json.dump({'url': url, 'soup': soup.prettify()}, f)
            data = self.strategy.extract(soup, url)
            
            links = []
            if self.config.follow_links and depth < self.config.max_depth:
                links = self._extract_links(soup, url)
            
            result = CrawlResult(
                url=url,
                status_code=response.status_code,
                data=data,
                links=links
            )
            self.results.append(result)
            
            # Follow links if configured
            if self.config.follow_links:
                for link in links[:5]:  # Limit links per page
                    if len(self.results) < self.config.max_pages:
                        self._crawl_recursive(link, depth + 1)
            
        except Exception as e:
            result = CrawlResult(
                url=url,
                status_code=0,
                data={},
                error=str(e)
            )
            self.results.append(result)
    
    def _extract_links(self, soup: BeautifulSoup, base_url: str) -> List[str]:
        """Extract valid links from page"""
        links = []
        base_domain = urlparse(base_url).netloc
        
        for anchor in soup.find_all('a', href=True):
            href = anchor['href']
            full_url = urljoin(base_url, str(href))
            
            # Only follow links from same domain
            if urlparse(full_url).netloc == base_domain:
                if full_url not in self.visited and full_url not in links:
                    links.append(full_url)
        
        return links

class JSWebCrawler(WebCrawler):
    """Crawler with JavaScript rendering support"""
    
    def __init__(self, config: CrawlConfig, strategy: ExtractionStrategy, js_config: Dict):
        super().__init__(config, strategy)
        self.js_config = js_config
    
    def _crawl_recursive(self, url: str, depth: int):
        """Recursively crawl pages with JS rendering"""
        if depth > self.config.max_depth or len(self.results) >= self.config.max_pages:
            return
        
        if url in self.visited:
            return
        
        self.visited.add(url)
        
        try:
            time.sleep(self.config.delay)
            
            # Render page with Selenium
            headless = self.js_config.get('headless', True)
            wait_config = self.js_config.get('wait')
            actions = self.js_config.get('actions', [])
            
            with JavaScriptRenderer(headless=headless) as renderer:
                # Load and render page
                html = renderer.render_page(url, wait_config)
                
                # Perform actions
                for action in actions:
                    action_type = action.get('type')
                    
                    if action_type == 'click':
                        renderer.click_element(action.get('selector'))
                    elif action_type == 'scroll':
                        renderer.scroll_to_bottom(
                            action.get('pause_time', 1.0),
                            action.get('max_scrolls', 10)
                        )
                    elif action_type == 'script':
                        renderer.execute_script(action.get('code'))
                    elif action_type == 'wait':
                        time.sleep(action.get('seconds', 1))
                
                # Get final HTML
                if renderer.driver:
                    html = renderer.driver.page_source
            
            # Parse and extract
            soup = BeautifulSoup(html, 'html.parser')
            data = self.strategy.extract(soup, url)
            
            links = []
            if self.config.follow_links and depth < self.config.max_depth:
                links = self._extract_links(soup, url)
            
            result = CrawlResult(
                url=url,
                status_code=200,
                data=data,
                links=links
            )
            self.results.append(result)
            
            # Follow links if configured
            if self.config.follow_links:
                for link in links[:5]:
                    if len(self.results) < self.config.max_pages:
                        self._crawl_recursive(link, depth + 1)
            
        except Exception as e:
            result = CrawlResult(
                url=url,
                status_code=0,
                data={},
                error=str(e)
            )
            self.results.append(result)