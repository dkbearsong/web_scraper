from typing import Dict, List, Any, Optional
import requests
import time
import json
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup
import cloudscraper
import os
import datetime
import logging

logger = logging.getLogger(__name__)


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
        self.scraper = cloudscraper.create_scraper()  # Create once, reuse throughout

        headers = {
            'User-Agent': config.user_agent
        }
        if config.headers:
            headers.update(config.headers)
        self.session.headers.update(headers)
    
    def crawl(self) -> List[CrawlResult]:
        """Start crawling from the initial URL"""
        logger.debug(f"crawl() - Starting crawl from {self.config.url}, max_depth={self.config.max_depth}, max_pages={self.config.max_pages}")
        self._crawl_recursive(self.config.url, 0)
        logger.debug(f"crawl() - Completed. Results: {len(self.results)} pages visited")
        return self.results
    
    def _crawl_recursive(self, url: str, depth: int):
        """Recursively crawl pages"""
        logger.debug(f"_crawl_recursive() - depth={depth}, url={url}")
        if depth > self.config.max_depth or len(self.results) >= self.config.max_pages:
            logger.debug(f"_crawl_recursive() - Stopping: depth_limit={depth > self.config.max_depth}, page_limit={len(self.results) >= self.config.max_pages}")
            return
        
        if url in self.visited:
            logger.debug(f"_crawl_recursive() - URL already visited, skipping")
            return
        
        self.visited.add(url)
        
        try:
            time.sleep(self.config.delay)
            logger.debug(f"_crawl_recursive() - Fetching {url} (attempt 1 with requests)")
            response = self.session.get(url, timeout=self.config.timeout)
            logger.debug(f"_crawl_recursive() - Got response: status={response.status_code}, content_length={len(response.content)}")
            if response.status_code == 403:
                # Handle Cloudflare protection - reuse stored scraper
                logger.debug(f"_crawl_recursive() - Got 403, retrying with cloudscraper")
                response = self.scraper.get(url, timeout=self.config.timeout)
                logger.debug(f"_crawl_recursive() - Cloudscraper response: status={response.status_code}")

            soup = BeautifulSoup(response.content, 'html.parser')
            logger.debug(f"_crawl_recursive() - Parsing HTML, extracting data with {self.strategy.__class__.__name__}")
            data = self.strategy.extract(soup, url, debug=False)
            logger.debug(f"_crawl_recursive() - Extraction complete. Extracted keys: {list(data.keys()) if isinstance(data, dict) else 'N/A'}")
            
            links = []
            if self.config.follow_links and depth < self.config.max_depth:
                links = self._extract_links(soup, url)
                logger.debug(f"_crawl_recursive() - Found {len(links)} links on page")
            
            result = CrawlResult(
                url=url,
                status_code=response.status_code,
                data=data,
                links=links
            )
            self.results.append(result)
            logger.debug(f"_crawl_recursive() - Result added. Total results: {len(self.results)}")
            
            # Follow links if configured
            if self.config.follow_links:
                for link in links[:5]:  # Limit links per page
                    logger.debug(f"_crawl_recursive() - Following link: {link}")
                    self._crawl_recursive(link, depth + 1)
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
        self.renderer = None  # Reuse renderer across pages
    
    def _get_renderer(self):
        """Get or create a reusable renderer"""
        if self.renderer is None:
            headless = self.js_config.get('headless', True)
            user_data_dir = self.js_config.get('user_data_dir')
            profile = self.js_config.get('profile')

            logger.debug(
                "Initializing JavaScriptRenderer with headless=%s, user_data_dir=%s, profile=%s",
                headless,
                user_data_dir,
                profile,
            )

            self.renderer = JavaScriptRenderer(
                headless=headless,
                user_data_dir=user_data_dir,
                profile=profile,
            )
            self.renderer.__enter__()
        return self.renderer
    
    def _cleanup_renderer(self):
        """Cleanup renderer when done"""
        if self.renderer is not None:
            try:
                self.renderer.__exit__(None, None, None)
            finally:
                self.renderer = None
    
    def crawl(self) -> List[CrawlResult]:
        """Start crawling from the initial URL"""
        logger.debug(f"JSWebCrawler.crawl() - Starting JS-enabled crawl from {self.config.url}")
        try:
            self._crawl_recursive(self.config.url, 0)
        finally:
            logger.debug(f"JSWebCrawler.crawl() - Cleaning up renderer")
            self._cleanup_renderer()
        logger.debug(f"JSWebCrawler.crawl() - Completed. Visited {len(self.visited)} pages")
        return self.results
    
    def _crawl_recursive(self, url: str, depth: int):
        """Recursively crawl pages with JS rendering"""
        logger.debug(f"JSWebCrawler._crawl_recursive() - depth={depth}, url={url}")
        if depth > self.config.max_depth or len(self.results) >= self.config.max_pages:
            logger.debug(f"JSWebCrawler._crawl_recursive() - Stopping: depth_limit={depth > self.config.max_depth}, page_limit={len(self.results) >= self.config.max_pages}")
            return
        
        if url in self.visited:
            logger.debug(f"JSWebCrawler._crawl_recursive() - URL already visited, skipping")
            return
        
        self.visited.add(url)
        
        try:
            time.sleep(self.config.delay)
            
            # Reuse renderer for all pages
            renderer = self._get_renderer()
            wait_config = self.js_config.get('wait')
            actions = self.js_config.get('actions', [])
            
            # Load and render page
            logger.debug(f"JSWebCrawler._crawl_recursive() - Rendering page with wait_config={wait_config}")
            html = renderer.render_page(url, wait_config)
            
            # Perform actions
            logger.debug(f"JSWebCrawler._crawl_recursive() - Executing {len(actions)} actions")
            for i, action in enumerate(actions):
                action_type = action.get('type')
                logger.debug(f"JSWebCrawler._crawl_recursive() - Action {i+1}: type={action_type}, config={action}")
                
                if action_type == 'click':
                    renderer.click_element(action.get('selector'))
                elif action_type == 'scroll':
                    renderer.scroll_to_bottom(
                        action.get('pause_time', 1.0),
                        action.get('max_scrolls', 10)
                    )
                elif action_type == 'click_until_gone':
                    selector = action.get('selector')
                    max_clicks = action.get('max_clicks', 10)
                    pause_time = action.get('pause_time', 1.0)
                    if selector:
                        renderer.click_until_gone(selector, max_clicks, pause_time)
                elif action_type == 'load_all':
                    method = action.get('method', 'scroll')
                    selector = action.get('selector')
                    max_iterations = action.get('max_iterations', 10)
                    pause_time = action.get('pause_time', 1.0)
                    renderer.load_all_content(method, selector, max_iterations, pause_time)
                elif action_type == 'script':
                    renderer.execute_script(action.get('code'))
                elif action_type == 'wait':
                    time.sleep(action.get('seconds', 1))
                logger.debug(f"JSWebCrawler._crawl_recursive() - Action {i+1} complete")
            
            # Get final HTML
            html = renderer.driver.page_source
            
            # Debug: save HTML to file
            if self.js_config.get('debug', False):
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                url_hash = hash(url) % 10000
                filename = f"debug_{timestamp}_{url_hash}.html"
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(html)
                logger.debug(f"Saved HTML to {filename}")
            
            # Parse and extract
            logger.debug(f"JSWebCrawler._crawl_recursive() - Parsing HTML and extracting data with {self.strategy.__class__.__name__}")
            soup = BeautifulSoup(html, 'html.parser')
            data = self.strategy.extract(soup, url, debug=self.js_config.get('debug', False))
            
            # Count extracted items
            item_count = 0
            if isinstance(data, dict):
                for v in data.values():
                    if isinstance(v, list):
                        item_count = len(v)
                        break
            elif isinstance(data, list):
                item_count = len(data)
            
            # Log summary: always report extraction success and count
            logger.info(f"Extracted {item_count} items from {url}")
            
            # Debug: log extraction details (goes to debug.log only)
            if self.js_config.get('debug', False):
                logger.debug(f"Strategy type: {type(self.strategy).__name__}")
                if hasattr(self.strategy, 'selectors') and self.strategy.selectors:
                    logger.debug(f"Selectors used: {self.strategy.selectors}")
            
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