"""
Web Crawling Microservice
A customizable framework for extracting data from websites via REST API
"""

from flask import Flask, request, jsonify
import requests
from bs4 import BeautifulSoup
import time
from random import random
from dataclasses import asdict
import aiohttp
import asyncio
from typing import Optional
import datetime
import logging

# Modules
from app.data_models import CrawlConfig
from app.extraction_strategies import ExtractionStrategy, GenericStrategy, SelectorStrategy, ProductStrategy, ArticleStrategy
from app.call_Ollama import OllamaClient
from app.page_analyzer import PageAnalyzer
from app.crawler import WebCrawler, JSWebCrawler
from app.javascript_renderer import JavaScriptRenderer
from app.extract_paginated import paginated
import threading
from urllib.parse import urlparse
from random import uniform
from functools import wraps

class DomainLockManager:
    def __init__(self):
        self.locks = {}
        self.last_finish_times = {}
        self.manager_lock = threading.Lock()

    def get_lock(self, domain: str):
        with self.manager_lock:
            if domain not in self.locks:
                self.locks[domain] = threading.Lock()
            return self.locks[domain]

    def record_finish(self, domain: str):
        with self.manager_lock:
            self.last_finish_times[domain] = time.time()

    def get_last_finish(self, domain: str) -> float:
        with self.manager_lock:
            return self.last_finish_times.get(domain, 0.0)

domain_lock_manager = DomainLockManager()

def limit_domain_concurrency(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            data = request.get_json(silent=True) or {}
        except Exception:
            data = {}
        
        url = data.get('url') or data.get('url_template') or request.args.get('url')
        
        if not url:
            return f(*args, **kwargs)
            
        try:
            parsed = urlparse(url)
            domain = parsed.netloc or parsed.path
        except Exception:
            domain = None
            
        if not domain:
            return f(*args, **kwargs)
            
        lock = domain_lock_manager.get_lock(domain)
        logger.info(f"Acquiring lock for domain: {domain}")
        with lock:
            last_finish = domain_lock_manager.get_last_finish(domain)
            if last_finish > 0:
                pause_time = uniform(1.0, 2.0)
                elapsed = time.time() - last_finish
                wait_time = pause_time - elapsed
                if wait_time > 0:
                    logger.info(f"Waiting {wait_time:.2f}s before starting next request on domain: {domain}")
                    time.sleep(wait_time)
            
            logger.info(f"Starting request on domain: {domain}")
            try:
                return f(*args, **kwargs)
            finally:
                domain_lock_manager.record_finish(domain)
                logger.info(f"Finished request on domain: {domain}")
                
    return decorated_function

app = Flask(__name__)

# Configure logging - apply to ROOT logger so all modules inherit handlers
# Console handler: INFO level only (minimal console output)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_formatter = logging.Formatter('%(levelname)s - %(message)s')
console_handler.setFormatter(console_formatter)

# Main file handler: INFO level and above
main_file_handler = logging.FileHandler('web_scraper.log')
main_file_handler.setLevel(logging.INFO)
main_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
main_file_handler.setFormatter(main_formatter)

# Debug file handler: DEBUG level only (all DEBUG messages)
debug_file_handler = logging.FileHandler('debug.log')
debug_file_handler.setLevel(logging.DEBUG)
debug_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
debug_file_handler.setFormatter(debug_formatter)

# Configure ROOT logger - this affects all modules
root_logger = logging.getLogger()
root_logger.setLevel(logging.DEBUG)  # Capture all levels

# Prevent duplicate handlers when Flask auto-reloads
# Clear existing handlers to avoid duplication
root_logger.handlers.clear()

root_logger.addHandler(console_handler)
root_logger.addHandler(main_file_handler)
root_logger.addHandler(debug_file_handler)

# suppress overly verbose third‑party loggers
for noisy in [
    "selenium",
    "selenium.webdriver.remote.remote_connection",
    "urllib3",
    "werkzeug",
]:
    logging.getLogger(noisy).setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# Test that debug logging is working
logger.debug("=== MAIN.PY INITIALIZED - DEBUG LOGGING ENABLED ===")
logger.info("=== MAIN.PY INITIALIZED - INFO LOGGING ENABLED ===")


# ==================== Strategy Factory ====================

class StrategyFactory:
    """Factory for creating extraction strategies"""
    
    @staticmethod
    def create(strategy_type: str, **kwargs) -> ExtractionStrategy:
        if strategy_type not in ['generic', 'product', 'article', 'selector']:
            raise ValueError(f"Unknown strategy: {strategy_type}")
        
        if strategy_type == 'generic':
            return GenericStrategy()
        elif strategy_type == 'product':
            return ProductStrategy()
        elif strategy_type == 'article':
            return ArticleStrategy()
        else:  # strategy_type == 'selector'
            return SelectorStrategy(kwargs.get('selectors', {}))

# ==================== API Endpoints ====================

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({'status': 'healthy', 'service': 'web-crawler'})

@app.route('/crawl', methods=['POST'])
@limit_domain_concurrency
def crawl():
    """
    Main crawling endpoint
    
    Request body:
    {
        "url": "https://example.com",
        "strategy": "generic|product|article|selector",
        "selectors": {"title": "h1.title", "price": ".price"},  // for selector strategy
        "config": {
            "max_depth": 1,
            "max_pages": 10,
            "delay": 1.0,
            "follow_links": false
        }
    }
    """
    try:
        data = request.get_json()
        
        if not data or 'url' not in data:
            return jsonify({'status_code': 400, 'error': 'URL is required'}), 400
        
        # Create configuration
        config_data = data.get('config', {})
        config = CrawlConfig(
            url=data['url'],
            max_depth=config_data.get('max_depth', 1),
            max_pages=config_data.get('max_pages', 10),
            delay=config_data.get('delay', 1.0),
            follow_links=config_data.get('follow_links', False),
            user_agent=config_data.get('user_agent', 'CustomCrawler/1.0'),
            timeout=config_data.get('timeout', 10),
            headers=config_data.get('headers')
        )
        
        # Create strategy
        strategy_type = data.get('strategy', 'generic')
        strategy = StrategyFactory.create(
            strategy_type,
            selectors=data.get('selectors', {})
        )
        
        # Execute crawl
        crawler = WebCrawler(config, strategy)
        results = crawler.crawl()
        
        return jsonify({
            'status_code': 200,
            'success': True,
            'pages_crawled': len(results),
            'results': [asdict(r) for r in results]
        })
        
    except Exception as e:
        return jsonify({'status_code': 500, 'error': str(e)}), 500

@app.route('/strategies', methods=['GET'])
def list_strategies():
    """List available extraction strategies"""
    return jsonify({
        'strategies': [
            {
                'name': 'generic',
                'description': 'Extract common elements (title, headings, paragraphs, images)'
            },
            {
                'name': 'product',
                'description': 'Extract e-commerce product data (name, price, description)'
            },
            {
                'name': 'article',
                'description': 'Extract article/blog content (headline, author, content)'
            },
            {
                'name': 'selector',
                'description': 'Custom CSS selector-based extraction',
                'requires': 'selectors parameter with field: selector mapping'
            }
        ]
    })

@app.route('/analyze', methods=['POST'])
@limit_domain_concurrency
def analyze_page():
    """
    Analyze page structure to build custom extraction strategy
    
    Request body:
    {
        "url": "https://example.com"
    }
    
    Returns a detailed map of the page structure with suggestions for selectors
    """
    try:
        data = request.get_json()
        
        if not data or 'url' not in data:
            return jsonify({'status_code': 400, 'error': 'URL is required'}), 400
        
        url = data['url']
        
        # Fetch the page
        response = requests.get(url, timeout=10, headers={
            'User-Agent': 'CustomCrawler/1.0'
        })
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Analyze page structure
        analyzer = PageAnalyzer(soup, url)
        analysis = analyzer.analyze()
        
        return jsonify({
            'status_code': 200,
            'success': True,
            'url': url,
            'analysis': analysis
        })
        
    except Exception as e:
        return jsonify({'status_code': 500, 'error': str(e)}), 500

@app.route('/extract', methods=['POST'])
@limit_domain_concurrency
def quick_extract():
    """
    Quick single-page extraction
    
    Request body:
    {
        "url": "https://example.com",
        "strategy": "generic",
        "selectors": {}  // optional, for selector strategy
    }
    """
    try:
        data = request.get_json()
        logger.debug(f"quick_extract() - Endpoint called with url={data.get('url') if data else 'N/A'}")
        
        if not data or 'url' not in data:
            logger.warning(f"quick_extract() - Missing URL in request")
            return jsonify({'status_code': 400, 'error': 'URL is required'}), 400
        
        config = CrawlConfig(
            url=data['url'],
            max_depth=0,
            max_pages=1,
            delay=0
        )
        
        strategy_type = data.get('strategy', 'generic')
        logger.debug(f"quick_extract() - Using strategy: {strategy_type}")
        strategy = StrategyFactory.create(
            strategy_type,
            selectors=data.get('selectors', {})
        )
        
        logger.debug(f"quick_extract() - Starting crawl")
        crawler = WebCrawler(config, strategy)
        results = crawler.crawl()
        logger.debug(f"quick_extract() - Crawl complete, got {len(results)} results")
        
        if results:
            extracted_data = results[0].data
            # Transform to list of dicts
            if isinstance(extracted_data, dict):
                if 'data' in extracted_data and isinstance(extracted_data['data'], list) and extracted_data['data'] and isinstance(extracted_data['data'][0], dict):
                    # Already list of dicts
                    extracted_data = extracted_data['data']
                else:
                    # Dict of lists -> list of dicts
                    keys = list(extracted_data.keys())
                    if keys:
                        lengths = [len(v) if isinstance(v, list) else 1 for v in extracted_data.values()]
                        max_len = max(lengths) if lengths else 1
                        # Pad shorter lists
                        for k in keys:
                            if isinstance(extracted_data[k], list):
                                if len(extracted_data[k]) < max_len:
                                    extracted_data[k].extend([None] * (max_len - len(extracted_data[k])))
                            else:
                                extracted_data[k] = [extracted_data[k]] * max_len
                        extracted_data = [dict(zip(keys, vals)) for vals in zip(*[extracted_data[k] for k in keys])]
                    else:
                        extracted_data = []
            return jsonify({
                'status_code': results[0].status_code,
                'success': True,
                'data': extracted_data
            })
        else:
            return jsonify({'status_code': 500, 'error': 'No data extracted'}), 500
            
    except Exception as e:
        return jsonify({'status_code': 500, 'error': str(e)}), 500

@app.route('/extract-js', methods=['POST'])
@limit_domain_concurrency
def extract_js():
    """
    Extract data from JavaScript-rendered pages using Selenium
    
    Request body:
    {
        "url": "https://example.com",
        "strategy": "generic|product|article|selector",
        "selectors": {},  // for selector strategy
        "js_config": {
            "wait": {
                "type": "time|element|script|network_idle",
                "value": 5 or "css_selector" or "return condition",
                "timeout": 10
            },
            "actions": [
                {"type": "click", "selector": ".tab-button"},
                {"type": "scroll", "max_scrolls": 5, "pause_time": 1.5},
                {"type": "click_until_gone", "selector": ".load-more", "max_clicks": 20, "pause_time": 2},
                {"type": "load_all", "method": "scroll|click", "selector": ".load-more", "max_iterations": 10},
                {"type": "script", "code": "document.querySelector('.modal').remove()"},
                {"type": "wait", "seconds": 2}
            ],
            "headless": true,
            // optionally point at a real Chrome profile to inherit cookies
            "user_data_dir": "/home/user/.config/google-chrome",
            "profile": "Default",
            "debug": false  // save HTML to file and log extraction details
        }
    }
    """
    try:
        data = request.get_json()
        logger.debug(f"extract_js() - Endpoint called with url={data.get('url') if data else 'N/A'}")
        
        if not data or 'url' not in data:
            logger.warning(f"quick_extract() - Missing URL in request")
            return jsonify({'status_code': 400, 'error': 'URL is required'}), 400
        
        url = data['url']
        js_config = data.get('js_config', {})
        
        # Extract JS config
        wait_config = js_config.get('wait')
        actions = js_config.get('actions', [])
        headless = js_config.get('headless', True)
        user_data_dir = js_config.get('user_data_dir')
        profile = js_config.get('profile')
        iframe_selector = js_config.get('iframe')  # NEW: Extract iframe selector
        debug = js_config.get('debug', False)
        block_images = js_config.get('block_images', False)
        page_load_strategy = js_config.get('page_load_strategy', 'normal')

        # log the parsed JS configuration for troubleshooting
        logger.debug(
            "Parsed js_config: headless=%s, user_data_dir=%s, profile=%s, "
            "actions=%s, wait=%s, iframe=%s, debug=%s, block_images=%s, page_load_strategy=%s",
            headless,
            user_data_dir,
            profile,
            actions,
            wait_config,
            iframe_selector,
            debug,
            block_images,
            page_load_strategy,
        )

        # Render page with Selenium
        with JavaScriptRenderer(
            headless=headless,
            user_data_dir=user_data_dir,
            profile=profile,
            block_images=block_images,
            page_load_strategy=page_load_strategy,
        ) as renderer:
            
            # Navigate to URL and wait for initial content
            html = renderer.render_page(url, wait_config, iframe_selector)
            logger.debug(f"extract_js() - Initial HTML size: {len(html)} bytes")
            
            # Perform actions if specified
            logger.debug(f"extract_js() - Executing {len(actions)} actions")
            for i, action in enumerate(actions):
                action_type = action.get('type')
                logger.debug(f"extract_js() - Action {i+1}: type={action_type}, config={action}")
                
                if action_type == 'click':
                    selector = action.get('selector')
                    if selector:
                        use_js = action.get('use_js', False)
                        dismiss_overlays = action.get('dismiss_overlays', True)
                        logger.debug(f"extract_js() - Clicking selector: {selector}")
                        renderer.click_element(selector, use_js, dismiss_overlays)
                
                elif action_type == 'scroll':
                    max_scrolls = action.get('max_scrolls', 10)
                    pause_time = action.get('pause_time', 1.0)
                    logger.debug(f"extract_js() - Scrolling with max_scrolls={max_scrolls}, pause_time={pause_time}")
                    renderer.scroll_to_bottom(pause_time, max_scrolls)

                elif action_type == 'click_until_gone':
                    selector = action.get('selector')
                    max_clicks = action.get('max_clicks', 10)
                    pause_time = action.get('pause_time', 1.0)
                    if selector:
                        logger.debug(f"extract_js() - Clicking until gone: {selector}")
                        clicks = renderer.click_until_gone(selector, max_clicks, pause_time)
                        logger.debug(f"extract_js() - Clicked '{selector}' {clicks} times")

                elif action_type == 'load_all':
                    method = action.get('method', 'scroll')
                    selector = action.get('selector')
                    max_iterations = action.get('max_iterations', 10)
                    pause_time = action.get('pause_time', 1.0)
                    logger.debug(f"extract_js() - Load all content: method={method}, selector={selector}")
                    renderer.load_all_content(method, selector, max_iterations, pause_time)
                
                elif action_type == 'script':
                    script = action.get('code')
                    if script:
                        logger.debug(f"extract_js() - Executing custom script")
                        renderer.execute_script(script)
                
                elif action_type == 'wait':
                    # Additional wait after previous actions
                    wait_seconds = action.get('seconds', 3 * random())
                    logger.debug(f"extract_js() - Waiting {wait_seconds} seconds")
                    time.sleep(wait_seconds)
                
                logger.debug(f"extract_js() - Action {i+1} complete")
            
            # Get final rendered HTML
            html = renderer.driver.page_source
            logger.debug(f"extract_js() - Final HTML size: {len(html)} bytes")
        
        # Debug: save HTML to file
        if debug:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            url_hash = hash(url) % 10000  # simple hash for filename
            filename = f"debug_{timestamp}_{url_hash}.html"
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(html)
            logger.debug(f"extract_js() - Saved HTML to {filename}")
        
        # Parse with BeautifulSoup
        logger.debug(f"extract_js() - Parsing HTML with BeautifulSoup")
        soup = BeautifulSoup(html, 'html.parser')
        
        # Create strategy
        strategy_type = data.get('strategy', 'generic')
        logger.debug(f"extract_js() - Using extraction strategy: {strategy_type}")
        strategy = StrategyFactory.create(
            strategy_type,
            selectors=data.get('selectors', {})
        )
        
        # Extract data
        logger.debug(f"extract_js() - Starting data extraction")
        extracted_data = strategy.extract(soup, url, debug=debug)
        logger.debug(f"extract_js() - Extraction complete, extracted keys: {list(extracted_data.keys()) if isinstance(extracted_data, dict) else 'N/A'}")
        
        # Count extracted items
        item_count = 0
        if isinstance(extracted_data, dict):
            for v in extracted_data.values():
                if isinstance(v, list):
                    item_count = len(v)
                    break
        elif isinstance(extracted_data, list):
            item_count = len(extracted_data)
        
        # Log summary: always report extraction success and count
        logger.info(f"Extracted {item_count} items from {url}")
        
        # Debug: log extraction details (goes to debug.log only)
        if debug:
            logger.debug(f"Strategy type: {strategy_type}")
            if hasattr(strategy, 'selectors') and strategy.selectors:
                logger.debug(f"Selectors used: {strategy.selectors}")
        
        # Transform to list of dicts
        if isinstance(extracted_data, dict):
            if 'data' in extracted_data and isinstance(extracted_data['data'], list) and extracted_data['data'] and isinstance(extracted_data['data'][0], dict):
                # Already list of dicts
                extracted_data = extracted_data['data']
            else:
                # Dict of lists -> list of dicts
                keys = list(extracted_data.keys())
                if keys:
                    lengths = [len(v) if isinstance(v, list) else 1 for v in extracted_data.values()]
                    max_len = max(lengths) if lengths else 1
                    # Pad shorter lists
                    for k in keys:
                        if isinstance(extracted_data[k], list):
                            if len(extracted_data[k]) < max_len:
                                extracted_data[k].extend([None] * (max_len - len(extracted_data[k])))
                        else:
                            extracted_data[k] = [extracted_data[k]] * max_len
                    extracted_data = [dict(zip(keys, vals)) for vals in zip(*[extracted_data[k] for k in keys])]
                else:
                    extracted_data = []
        
        return jsonify({
            'status_code': 200,
            'success': True,
            'url': url,
            'rendered': True,
            'data': extracted_data
        })
        
    except Exception as e:
        return jsonify({'status_code': 500, 'error': str(e)}), 500

@app.route('/crawl-js', methods=['POST'])
@limit_domain_concurrency
def crawl_js():
    """
    Multi-page crawling with JavaScript rendering support
    
    Request body:
    {
        "url": "https://example.com",
        "strategy": "generic",
        "config": {
            "max_depth": 2,
            "max_pages": 10,
            "delay": 1.0,
            "follow_links": true
        },
        "js_config": {
            "wait": {...},
            "actions": [...],
            "headless": true,
            "user_data_dir": "/home/user/.config/google-chrome",
            "profile": "Default",
            "debug": false
        }
    }
    """
    try:
        data = request.get_json()
        
        if not data or 'url' not in data:
            return jsonify({'status_code': 400, 'error': 'URL is required'}), 400
        
        # Create configuration
        config_data = data.get('config', {})
        config = CrawlConfig(
            url=data['url'],
            max_depth=config_data.get('max_depth', 1),
            max_pages=config_data.get('max_pages', 10),
            delay=config_data.get('delay', 1.0),
            follow_links=config_data.get('follow_links', False),
            user_agent=config_data.get('user_agent', 'CustomCrawler/1.0'),
            timeout=config_data.get('timeout', 10),
            headers=config_data.get('headers')
        )
        
        # Create strategy
        strategy_type = data.get('strategy', 'generic')
        strategy = StrategyFactory.create(
            strategy_type,
            selectors=data.get('selectors', {})
        )
        
        # Create JS-enabled crawler
        js_config = data.get('js_config', {})
        # js_config may contain user_data_dir/profile fields that will be
        # forwarded into the underlying Selenium renderer so the crawler can
        # benefit from cookies stored by your local Chrome installation.
        crawler = JSWebCrawler(config, strategy, js_config)
        results = crawler.crawl()
        
        return jsonify({
            'status_code': 200,
            'success': True,
            'pages_crawled': len(results),
            'results': [asdict(r) for r in results]
        })
        
    except Exception as e:
        return jsonify({'status_code': 500, 'error': str(e)}), 500

@app.route('/extract-paginated', methods=['POST'])
@limit_domain_concurrency
def extract_paginated():
    """
    Extract data from paginated results (numbered pages)
    
    Request body:
    {
        "url_template": "https://example.com/jobs?page={page}",
        "start_page": 1,
        "end_page": 20,
        "strategy": "selector",
        "selectors": {...},
        "js_config": {...},  // optional - use if pages are JS-rendered
        "delay": 1.5
    }
    
    Or for clicking through pages:
    {
        "url": "https://example.com/jobs",
        "pagination": {
            "method": "click",
            "next_selector": "button.next",
            "max_pages": 20,
            "wait_after_click": 2
        },
        "strategy": "selector",
        "selectors": {...},
        "js_config": {...}
    }
    """
    pag_obj = paginated()
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'status_code': 400, 'error': 'Request body is required'}), 400
        
        # Determine pagination method
        if 'url_template' in data:
            # URL-based pagination
            return pag_obj._extract_url_pagination(data)
        elif 'pagination' in data and data['pagination'].get('method') == 'click':
            # Click-based pagination
            return pag_obj._extract_click_pagination(data)
        else:
            return jsonify({'status_code': 400, 'error': 'Either url_template or pagination config is required'}), 400
            
    except Exception as e:
        return jsonify({'status_code': 500, 'error': str(e)}), 500

@app.route('/generate-strategy', methods=['POST'])
@limit_domain_concurrency
def generate_strategy():
    """
    Generate extraction strategy using Ollama analysis
    
    Request body:
    {
        "url": "https://example.com",
        "instructions": "Extract job listings with title, company, location, and link",
        "is_paginated": true/false,  // optional, auto-detect if not provided
        "thinking": true/false       // optional, enable thinking capability for better analysis
    }
    
    Returns a strategy JSON that can be used with /crawl or /extract-paginated
    """
    try:
        data = request.get_json()
        
        if not data or 'url' not in data or 'instructions' not in data:
            return jsonify({'status_code': 400, 'error': 'URL and instructions are required'}), 400
        
        url = data['url']
        instructions = data['instructions']
        is_paginated = data.get('is_paginated')  # Optional
        thinking = data.get('thinking', False)   # Optional, default False
        
        # Run async Ollama analysis
        result = asyncio.run(_generate_strategy_async(url, instructions, is_paginated, thinking))
        
        return jsonify({
            'status_code': 200,
            'success': True,
            'strategy': result
        })
        
    except Exception as e:
        return jsonify({'status_code': 500, 'error': str(e)}), 500

async def _generate_strategy_async(url: str, instructions: str, is_paginated: Optional[bool] = None, thinking: bool = False):
    """Async helper to generate strategy using Ollama"""
    
    # Fetch page content
    response = requests.get(url, timeout=10, headers={
        'User-Agent': 'CustomCrawler/1.0'
    })
    response.raise_for_status()
    
    html_content = response.text
    
    # Prepare Ollama prompt
    system_message = """
    You are an expert web scraper who analyzes HTML and generates CSS selectors for data extraction.
    You understand different types of web pages: job listing pages, product catalogs, article pages, etc.
    You can identify pagination patterns and suggest appropriate extraction strategies.
    Always return valid JSON matching the requested schema. Do not use Scrappy syntax. Use standard CSS parser syntax.
    """
    
    json_schema = {
        "type": "object",
        "properties": {
            "url": {"type": "string"},
            "pagination": {
                "type": "object",
                "properties": {
                    "method": {"type": "string", "enum": ["click", "url"]},
                    "next_selector": {"type": "string"},
                    "max_pages": {"type": "number"},
                    "wait_after_click": {"type": "number"},
                    "use_js": {"type": "boolean"}
                }
            },
            "strategy": {"type": "string", "enum": ["selector", "generic", "product", "article"]},
            "selectors": {
                "type": "object",
                "additionalProperties": {"type": "string"}
            },
            "js_config": {
                "type": "object",
                "properties": {
                    "wait": {"type": "object"},
                    "headless": {"type": "boolean"}
                }
            },
            "company_url": {"type": "string"},
            "source": {"type": "string"}
        },
        "required": ["strategy", "selectors"]
    }
    
    user_prompt = f"""
    Analyze this webpage HTML and generate a scraping strategy based on the instructions.
    
    URL: {url}
    Instructions: {instructions}
    Is Paginated: {is_paginated if is_paginated is not None else 'auto-detect'}
    
    HTML Content (first 5000 characters):
    {html_content[:5000]}
    
    Please generate a JSON strategy object that includes:
    - Appropriate CSS selectors for extracting the requested data
    - Pagination configuration if the page appears to be paginated
    - JS config if the page uses JavaScript rendering
    - Strategy type (selector, generic, product, article)
    
    Focus on creating robust selectors that will work reliably.
    If pagination is detected, include pagination config.
    """
    
    # Call Ollama
    async with aiohttp.ClientSession() as session:
        client = OllamaClient(session, system_message=system_message, model="qwen3:8b")
        result = await client.call(user_prompt, json_schema, temp=0.3, top_p=0.7, top_k=10, mt=2048, thinking=thinking)
        
        # Ensure we have required fields
        if 'strategy' not in result:
            result['strategy'] = 'selector'
        if 'selectors' not in result:
            result['selectors'] = {}
        if 'url' not in result:
            result['url'] = url
            
        return result

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5052, debug=True)