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

# Modules
from app.data_models import CrawlConfig
from app.extraction_strategies import ExtractionStrategy, GenericStrategy, SelectorStrategy, ProductStrategy, ArticleStrategy
from app.page_analyzer import PageAnalyzer
from app.crawler import WebCrawler, JSWebCrawler
from app.javascript_renderer import JavaScriptRenderer
from app.extract_paginated import paginated

app = Flask(__name__)


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
        
        if not data or 'url' not in data:
            return jsonify({'status_code': 400, 'error': 'URL is required'}), 400
        
        config = CrawlConfig(
            url=data['url'],
            max_depth=0,
            max_pages=1,
            delay=0
        )
        
        strategy_type = data.get('strategy', 'generic')
        strategy = StrategyFactory.create(
            strategy_type,
            selectors=data.get('selectors', {})
        )
        
        crawler = WebCrawler(config, strategy)
        results = crawler.crawl()
        
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
            "headless": true
        }
    }
    """
    try:
        data = request.get_json()
        
        if not data or 'url' not in data:
            return jsonify({'status_code': 400, 'error': 'URL is required'}), 400
        
        url = data['url']
        js_config = data.get('js_config', {})
        
        # Extract JS config
        wait_config = js_config.get('wait')
        actions = js_config.get('actions', [])
        headless = js_config.get('headless', True)        
        iframe_selector = js_config.get('iframe')  # NEW: Extract iframe selector
        
        # Render page with Selenium
        with JavaScriptRenderer(headless=headless) as renderer:

            # Load page and wait for content (with optional iframe switch)
            html = renderer.render_page(url, wait_config, iframe_selector)  # CHANGED: Pass iframe_selector
            
            # Perform actions if specified
            for action in actions:
                action_type = action.get('type')
                
                if action_type == 'click':
                    selector = action.get('selector')
                    if selector:
                        use_js = action.get('use_js', False)
                        dismiss_overlays = action.get('dismiss_overlays', True)
                        renderer.click_element(selector, use_js, dismiss_overlays)
                
                elif action_type == 'scroll':
                    max_scrolls = action.get('max_scrolls', 10)
                    pause_time = action.get('pause_time', 1.0)
                    renderer.scroll_to_bottom(pause_time, max_scrolls)

                elif action_type == 'click_until_gone':
                    selector = action.get('selector')
                    max_clicks = action.get('max_clicks', 10)
                    pause_time = action.get('pause_time', 1.0)
                    if selector:
                        clicks = renderer.click_until_gone(selector, max_clicks, pause_time)
                        print(f"Clicked '{selector}' {clicks} times")

                elif action_type == 'load_all':
                    method = action.get('method', 'scroll')
                    selector = action.get('selector')
                    max_iterations = action.get('max_iterations', 10)
                    pause_time = action.get('pause_time', 1.0)
                    renderer.load_all_content(method, selector, max_iterations, pause_time)
                
                elif action_type == 'script':
                    script = action.get('code')
                    if script:
                        renderer.execute_script(script)
                
                elif action_type == 'wait':
                    # Additional wait after previous actions
                    rand_time = 3 * random()
                    time.sleep(action.get('seconds', rand_time))
            
            # Get final rendered HTML
            html = renderer.driver.page_source
        
        # Parse with BeautifulSoup
        soup = BeautifulSoup(html, 'html.parser')
        
        # Create strategy
        strategy_type = data.get('strategy', 'generic')
        strategy = StrategyFactory.create(
            strategy_type,
            selectors=data.get('selectors', {})
        )
        
        # Extract data
        extracted_data = strategy.extract(soup, url)
        
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
            "headless": true
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
    

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5052, debug=True)