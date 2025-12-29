from typing import Dict, List, Any, Optional
from bs4 import BeautifulSoup
import json
import re

# ==================== Page Analyzer ====================

class PageAnalyzer:
    """Analyzes webpage structure to suggest extraction strategies"""
    
    def __init__(self, soup: BeautifulSoup, url: str):
        self.soup = soup
        self.url = url
    
    def analyze(self) -> Dict[str, Any]:
        """Perform comprehensive page analysis"""
        return {
            'metadata': self._analyze_metadata(),
            'structure': self._analyze_structure(),
            'content_hints': self._analyze_content(),
            'suggested_selectors': self._suggest_selectors(),
            'detected_patterns': self._detect_patterns(),
            'recommended_strategy': self._recommend_strategy()
        }
    
    def _analyze_metadata(self) -> Dict[str, Any]:
        """Extract metadata and meta tags"""
        meta = {
            'title': self.soup.title.string if self.soup.title else None,
            'description': None,
            'keywords': None,
            'og_tags': {},
            'schema_org': []
        }
        
        # Meta tags
        for tag in self.soup.find_all('meta'):
            name = str(tag.get('name', '')).lower()
            prop = str(tag.get('property', '')).lower()
            content = str(tag.get('content', ''))
            
            if name == 'description':
                meta['description'] = content
            elif name == 'keywords':
                meta['keywords'] = content
            elif prop.startswith('og:'):
                meta['og_tags'][prop] = content
        
        # Schema.org structured data
        for script in self.soup.find_all('script', type='application/ld+json'):
            try:
                if script.string:
                    schema_data = json.loads(script.string)
                    meta['schema_org'].append(schema_data)
            except:
                pass
        
        return meta
    
    def _analyze_structure(self) -> Dict[str, Any]:
        """Analyze HTML structure and hierarchy"""
        structure = {
            'headings': self._get_heading_structure(),
            'main_container': self._find_main_container(),
            'navigation': self._find_navigation(),
            'forms': len(self.soup.find_all('form')),
            'tables': len(self.soup.find_all('table')),
            'images': len(self.soup.find_all('img')),
            'links': len(self.soup.find_all('a')),
            'semantic_tags': self._find_semantic_tags()
        }
        
        return structure
    
    def _get_heading_structure(self) -> List[Dict[str, str]]:
        """Get all headings with their hierarchy"""
        headings = []
        for tag in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
            for heading in self.soup.find_all(tag):
                text = heading.get_text(strip=True)
                if text:
                    headings.append({
                        'level': tag,
                        'text': text[:100],  # Limit length
                        'selector': self._generate_selector(heading)
                    })
        return headings
    
    def _find_main_container(self) -> Optional[Dict[str, str]]:
        """Find the main content container"""
        # Look for semantic tags first
        for tag in ['main', 'article']:
            element = self.soup.find(tag)
            if element:
                tags = {
                    'tag': tag,
                    'selector': self._generate_selector(element),
                    'id': element.get('id'),
                    'classes': element.get('class') or []
                }
                return tags
        
        # Look for common content class patterns
        patterns = [
            re.compile(r'content', re.I),
            re.compile(r'main', re.I),
            re.compile(r'article', re.I),
            re.compile(r'post', re.I)
        ]
        
        for pattern in patterns:
            element = self.soup.find(class_=pattern)
            if element:
                pat = {
                    'tag': element.name,
                    'selector': self._generate_selector(element),
                    'id': element.get('id'),
                    'classes': element.get('class') or []
                }
                return pat
        
        return None
    
    def _find_navigation(self) -> List[Dict[str, str]]:
        """Find navigation elements"""
        nav_elements = []
        
        for nav in self.soup.find_all('nav'):
            nav_elements.append({
                'selector': self._generate_selector(nav),
                'links': len(nav.find_all('a')),
                'id': nav.get('id'),
                'classes': nav.get('class') or []
            })
        
        return nav_elements
    
    def _find_semantic_tags(self) -> Dict[str, int]:
        """Count semantic HTML5 tags"""
        semantic_tags = ['header', 'footer', 'nav', 'main', 'article', 'section', 'aside']
        return {tag: len(self.soup.find_all(tag)) for tag in semantic_tags}
    
    def _analyze_content(self) -> Dict[str, Any]:
        """Analyze content patterns to identify key information"""
        hints = {
            'price_indicators': self._find_price_indicators(),
            'date_indicators': self._find_date_indicators(),
            'author_indicators': self._find_author_indicators(),
            'product_indicators': self._find_product_indicators(),
            'article_indicators': self._find_article_indicators()
        }
        
        return hints
    
    def _find_price_indicators(self) -> List[Dict[str, str]]:
        """Find elements that likely contain prices"""
        indicators = []
        
        # Look for elements with price-related classes
        price_patterns = [
            re.compile(r'price', re.I),
            re.compile(r'cost', re.I),
            re.compile(r'amount', re.I)
        ]
        
        for pattern in price_patterns:
            elements = self.soup.find_all(class_=pattern)
            for elem in elements[:3]:  # Limit results
                text = elem.get_text(strip=True)
                # Check if contains currency symbols or numbers
                if re.search(r'[$£€¥]|\d+[.,]\d{2}', text):
                    indicators.append({
                        'selector': self._generate_selector(elem),
                        'text': text[:50],
                        'pattern_matched': 'class'
                    })
        
        # Look for itemprop="price"
        for elem in self.soup.find_all(attrs={'itemprop': 'price'}):
            indicators.append({
                'selector': self._generate_selector(elem),
                'text': elem.get_text(strip=True)[:50],
                'pattern_matched': 'itemprop'
            })
        
        return indicators
    
    def _find_date_indicators(self) -> List[Dict[str, str]]:
        """Find elements that likely contain dates"""
        indicators = []
        
        # Look for time tags
        for time_tag in self.soup.find_all('time'):
            indicators.append({
                'selector': self._generate_selector(time_tag),
                'datetime': time_tag.get('datetime'),
                'text': time_tag.get_text(strip=True)[:50],
                'pattern_matched': 'time_tag'
            })
        
        # Look for date-related classes
        date_patterns = [re.compile(r'date', re.I), re.compile(r'published', re.I)]
        for pattern in date_patterns:
            for elem in self.soup.find_all(class_=pattern)[:3]:
                indicators.append({
                    'selector': self._generate_selector(elem),
                    'text': elem.get_text(strip=True)[:50],
                    'pattern_matched': 'class'
                })
        
        return indicators
    
    def _find_author_indicators(self) -> List[Dict[str, str]]:
        """Find elements that likely contain author information"""
        indicators = []
        
        # Meta tag
        author_meta = self.soup.find('meta', {'name': 'author'})
        if author_meta:
            indicators.append({
                'selector': 'meta[name="author"]',
                'content': author_meta.get('content'),
                'pattern_matched': 'meta'
            })
        
        # Class patterns
        author_patterns = [re.compile(r'author', re.I), re.compile(r'byline', re.I)]
        for pattern in author_patterns:
            for elem in self.soup.find_all(class_=pattern)[:3]:
                indicators.append({
                    'selector': self._generate_selector(elem),
                    'text': elem.get_text(strip=True)[:50],
                    'pattern_matched': 'class'
                })
        
        return indicators
    
    def _find_product_indicators(self) -> Dict[str, bool]:
        """Check for product page indicators"""
        return {
            'has_add_to_cart': bool(self.soup.find(text=re.compile(r'add to cart', re.I))),
            'has_buy_button': bool(self.soup.find(text=re.compile(r'buy now', re.I))),
            'has_price': bool(self.soup.find(class_=re.compile(r'price', re.I))),
            'has_product_schema': any('Product' in str(s) for s in self.soup.find_all('script', type='application/ld+json'))
        }
    
    def _find_article_indicators(self) -> Dict[str, bool]:
        """Check for article/blog page indicators"""
        return {
            'has_article_tag': bool(self.soup.find('article')),
            'has_author': bool(self.soup.find(class_=re.compile(r'author', re.I))),
            'has_publish_date': bool(self.soup.find('time')),
            'has_article_schema': any('Article' in str(s) for s in self.soup.find_all('script', type='application/ld+json'))
        }
    
    def _suggest_selectors(self) -> Dict[str, List[str]]:
        """Suggest CSS selectors for common data types. Starts by suggesting main content and title,
        then suggests selectors for images and links. Returns a dictionary with selectors."""
        suggestions = {
            'title': [],
            'main_content': [],
            'images': [],
            'links': [],
            'lists': []
        }
        
        # Title suggestions
        h1 = self.soup.find('h1')
        if h1:
            suggestions['title'].append(self._generate_selector(h1))
        
        # Main content suggestions
        main_container = self._find_main_container()
        if main_container:
            suggestions['main_content'].append(main_container['selector'])
        
        # Image suggestions
        for img in self.soup.find_all('img', class_=True)[:3]:
            suggestions['images'].append(self._generate_selector(img))
        
        return suggestions
    
    def _detect_patterns(self) -> List[str]:
        """Detect common web patterns (e-commerce, blog, news, etc.) and return a list of detected patterns.
        Starts by detecting common patterns and then scoring them based on the presence of specific elements or classes.
        Appends detected patterns to the patterns list, then returns the list."""
        patterns = []
        
        # E-commerce patterns
        if (self.soup.find(text=re.compile(r'add to cart', re.I)) or 
            self.soup.find(class_=re.compile(r'price', re.I))):
            patterns.append('e-commerce')
        
        # Blog/Article patterns
        if (self.soup.find('article') or 
            self.soup.find(class_=re.compile(r'post|article', re.I))):
            patterns.append('blog/article')
        
        # News patterns
        if self.soup.find(class_=re.compile(r'news|headline', re.I)):
            patterns.append('news')
        
        # Documentation patterns
        if self.soup.find(class_=re.compile(r'docs|documentation', re.I)):
            patterns.append('documentation')
        
        # Landing page patterns
        if len(self.soup.find_all(class_=re.compile(r'hero|banner', re.I))) > 0:
            patterns.append('landing_page')
        
        return patterns
    
    def _recommend_strategy(self) -> Dict[str, Any]:
        """Recommend the best extraction strategy based on analysis. First, it checks for specific patterns,
        then scores them based on the presence of specific elements or classes, and finally recommends the 
        best strategy based on the score. Returns a dictionary with the recommended strategy, confidence 
        score, and reasoning."""
        patterns = self._detect_patterns()
        product_indicators = self._find_product_indicators()
        article_indicators = self._find_article_indicators()
        
        # Scoring system
        scores = {
            'product': 0,
            'article': 0,
            'generic': 1  # Always possible
        }
        
        # Score product strategy
        if 'e-commerce' in patterns:
            scores['product'] += 3
        if sum(product_indicators.values()) >= 2:
            scores['product'] += 2
        
        # Score article strategy
        if 'blog/article' in patterns or 'news' in patterns:
            scores['article'] += 3
        if sum(article_indicators.values()) >= 2:
            scores['article'] += 2
        
        # Determine best strategy
        best_strategy = max(scores.items(), key=lambda x: x[1])
        
        recommendation = {
            'recommended': best_strategy[0],
            'confidence': best_strategy[1],
            'scores': scores,
            'reasoning': []
        }
        
        # Add reasoning
        if best_strategy[0] == 'product':
            recommendation['reasoning'].append('Page contains e-commerce indicators (price, add to cart)')
        elif best_strategy[0] == 'article':
            recommendation['reasoning'].append('Page contains article indicators (author, date, article tag)')
        else:
            recommendation['reasoning'].append('No specific pattern detected, generic strategy recommended')
        
        # Suggest custom selectors if needed
        if best_strategy[1] < 3:
            recommendation['reasoning'].append('Consider using selector strategy with custom selectors')
            recommendation['custom_selector_template'] = self._generate_selector_template()
        
        return recommendation
    
    def _generate_selector_template(self) -> Dict[str, str]:
        """Generate a template for custom selector strategy."""
        template = {}
        
        # Title
        h1 = self.soup.find('h1')
        if h1:
            template['title'] = self._generate_selector(h1)
        
        # Main content
        main_container = self._find_main_container()
        if main_container:
            template['content'] = f"{main_container['selector']} p"
        
        # Price (if found)
        price_elem = self.soup.find(class_=re.compile(r'price', re.I))
        if price_elem:
            template['price'] = self._generate_selector(price_elem)
        
        return template
    
    def _generate_selector(self, element) -> str:
        """Generate a CSS selector for an element"""
        selector_parts = []
        
        # Use ID if available (most specific)
        if element.get('id'):
            return f"#{element.get('id')}"
        
        # Use classes
        classes = element.get('class', [])
        if classes:
            # Use first class that's not generic
            for cls in classes:
                if cls and not cls.lower() in ['container', 'wrapper', 'content']:
                    selector_parts.append(f".{cls}")
                    break
        
        # Add tag name
        if not selector_parts:
            selector_parts.insert(0, element.name)
        
        return ''.join(selector_parts) if selector_parts else element.name