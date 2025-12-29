from abc import ABC, abstractmethod
from bs4 import BeautifulSoup, Tag
from typing import Dict, List, Any, Optional, Union
import re

# ==================== Extraction Strategies ====================

class ExtractionStrategy(ABC):
    """Base class for extraction strategies"""
    
    @abstractmethod
    def extract(self, soup: BeautifulSoup, url: str) -> Dict[str, Any]:
        """Extract data from BeautifulSoup object"""
        pass

class GenericStrategy(ExtractionStrategy):
    """Generic extraction - gets common elements"""
    
    def extract(self, soup: BeautifulSoup, url: str) -> Dict[str, Any]:
        return {
            'title': soup.title.string if soup.title else None,
            'headings': [h.get_text(strip=True) for h in soup.find_all(['h1', 'h2', 'h3'])],
            'paragraphs': [p.get_text(strip=True) for p in soup.find_all('p')[:5]],
            'images': [img.get('src') or img.get('data-src') for img in soup.find_all('img')],
            'meta_description': self._get_meta(soup, 'description'),
            'meta_keywords': self._get_meta(soup, 'keywords')
        }
    
    def _get_meta(self, soup: BeautifulSoup, name: str) -> Optional[str]:
        tag = soup.find('meta', attrs={'name': name}) or soup.find('meta', attrs={'property': f'og:{name}'})
        if tag:
            content = tag.get('content')
            if isinstance(content, list):
                return content[0] if content else None
            return content
        return None

class SelectorStrategy(ExtractionStrategy):
    """CSS selector-based extraction with advanced attribute support"""
    
    def __init__(self, selectors: Dict[str, Any]):
        """
        Initialize with selectors that support multiple extraction modes
        
        Selector formats:
        
        1. Simple text extraction:
           "field": "css_selector"
        
        2. Attribute extraction:
           "field": "css_selector@attr"
        
        3. Advanced extraction (dict format):
           "field": {
               "selector": "css_selector",
               "extract": "text|html|attr",  // What to extract
               "attribute": "href",           // Required if extract="attr"
               "multiple": true|false,        // Extract all matches or just first
               "child": "a",                  // Find child element first
               "child_attribute": "href"      // Extract from child
           }
        
        4. Table/list extraction:
           "field": {
               "selector": "table.data tr",
               "extract": "table",
               "columns": [
                   {"selector": "td:nth-child(1) a", "extract": "text"},
                   {"selector": "td:nth-child(1) a@href"},
                   {"selector": "td:nth-child(2)", "extract": "text"}
               ]
           }
        
        Examples:
        - "title": "h1.product-title"
        - "link": "a.product-link@href"
        - "description": {"selector": ".desc", "extract": "html"}
        - "data": {
              "selector": "table.info tr",
              "extract": "table",
              "columns": [
                  {"selector": "td:first-child", "extract": "text"},
                  {"selector": "td:last-child a@href"}
              ]
          }
        """
        self.selectors = selectors
    
    def extract(self, soup: BeautifulSoup, url: str) -> Dict[str, Any]:
        result = {}
        for key, selector_config in self.selectors.items():
            result[key] = self._extract_field(soup, selector_config)
        return result
    
    def _extract_field(self, soup: BeautifulSoup, config: Any) -> Any:
        """Extract a single field based on configuration"""
        
        # Handle simple string selector (backward compatible)
        if isinstance(config, str):
            return self._extract_simple(soup, config)
        
        # Handle advanced dict configuration
        if isinstance(config, dict):
            return self._extract_advanced(soup, config)
        
        return None
    
    def _extract_simple(self, soup: Union[BeautifulSoup, Tag], selector: str) -> Any:
        """Extract using simple string selector (text or attribute)"""
        
        # Check if attribute extraction is specified
        if '@' in selector:
            css_selector, attribute = selector.split('@', 1)
            elements = soup.select(css_selector.strip())
            
            if len(elements) == 1:
                return elements[0].get(attribute.strip())
            elif len(elements) > 1:
                return [el.get(attribute.strip()) for el in elements]
            else:
                return None
        else:
            # Extract text content
            elements = soup.select(selector)
            
            if len(elements) == 1:
                return elements[0].get_text(strip=True)
            elif len(elements) > 1:
                return [el.get_text(strip=True) for el in elements]
            else:
                return None
    
    def _extract_advanced(self, soup: BeautifulSoup, config: Dict) -> Any:
        """Extract using advanced dict configuration"""
        
        selector = config.get('selector')
        if not selector:
            return None
        
        extract_type = config.get('extract', 'text')
        multiple = config.get('multiple', True)
        
        # Special handling for table extraction
        if extract_type == 'table':
            return self._extract_table(soup, config)
        
        # Find elements
        elements = soup.select(selector)
        
        if not elements:
            return None
        
        # Handle single vs multiple elements
        if not multiple and elements:
            elements = [elements[0]]
        
        # Extract based on type
        results = []
        for element in elements:
            value = self._extract_from_element(element, config)
            if value is not None:
                results.append(value)
        
        # Return single value or list
        if not multiple and results:
            return results[0]
        elif len(results) == 1 and multiple:
            return results[0]
        else:
            return results if results else None
    
    def _extract_from_element(self, element, config: Dict) -> Any:
        """Extract value from a single element"""
        
        extract_type = config.get('extract', 'text')
        
        # Handle child element selection first
        if 'child' in config:
            child_selector = config['child']
            child = element.select_one(child_selector)
            if child:
                element = child
            else:
                return None
        
        # Extract based on type
        if extract_type == 'text':
            return element.get_text(strip=True)
        
        elif extract_type == 'html':
            return str(element)
        
        elif extract_type == 'attr':
            attribute = config.get('attribute')
            if attribute:
                return element.get(attribute)
            return None
        
        elif extract_type == 'child_attr':
            # Extract attribute from child element
            child_selector = config.get('child', '*')
            attribute = config.get('child_attribute')
            if attribute:
                child = element.select_one(child_selector)
                if child:
                    return child.get(attribute)
            return None
        
        return None
    
    def _extract_table(self, soup: BeautifulSoup, config: Dict) -> List[Dict]:
        """Extract structured data from table or list"""
        
        selector = config.get('selector')
        columns = config.get('columns', [])
        
        if not columns or not selector:
            return []
        
        # Find all rows
        rows = soup.select(selector)
        
        results = []
        for row in rows:
            row_data = {}
            
            for idx, col_config in enumerate(columns):
                # Generate key name
                if isinstance(col_config, dict) and 'name' in col_config:
                    key = col_config['name']
                else:
                    key = f"column_{idx}"
                
                # Extract column data
                if isinstance(col_config, str):
                    # Simple string selector - handle @ syntax
                    if '@' in col_config:
                        # Split selector and attribute
                        css_selector, attribute = col_config.split('@', 1)
                        element = row.select_one(css_selector.strip())
                        value = element.get(attribute.strip()) if element else None
                    else:
                        # Regular text extraction
                        element = row.select_one(col_config)
                        value = element.get_text(strip=True) if element else None
                elif isinstance(col_config, dict):
                    col_selector = col_config.get('selector')
                    if col_selector:
                        # Check if selector has @ syntax
                        if '@' in col_selector:
                            css_selector, attribute = col_selector.split('@', 1)
                            element = row.select_one(css_selector.strip())
                            value = element.get(attribute.strip()) if element else None
                        else:
                            # Use element-based extraction for other types
                            element = row.select_one(col_selector)
                            if element:
                                single_config = {**col_config, 'multiple': False}
                                value = self._extract_from_element(element, single_config)
                            else:
                                value = None
                else:
                    value = None
                
                row_data[key] = value
            
            results.append(row_data)
        
        return results

class ProductStrategy(ExtractionStrategy):
    """E-commerce product extraction"""
    
    def extract(self, soup: BeautifulSoup, url: str) -> Dict[str, Any]:
        return {
            'product_name': self._find_by_patterns(soup, [
                {'itemprop': 'name'},
                {'class_': re.compile(r'product.*title', re.I)}
            ]),
            'price': self._find_by_patterns(soup, [
                {'itemprop': 'price'},
                {'class_': re.compile(r'price', re.I)}
            ]),
            'description': self._find_by_patterns(soup, [
                {'itemprop': 'description'},
                {'class_': re.compile(r'description', re.I)}
            ]),
            'availability': self._find_by_patterns(soup, [
                {'itemprop': 'availability'}
            ]),
            'images': [img.get('src') or img.get('data-src') 
                      for img in soup.find_all('img', class_=re.compile(r'product', re.I))]
        }
    
    def _find_by_patterns(self, soup: BeautifulSoup, patterns: List[Dict]) -> Optional[str]:
        for pattern in patterns:
            element = soup.find(attrs=pattern)
            if element:
                return element.get_text(strip=True)
        return None

class ArticleStrategy(ExtractionStrategy):
    """News article/blog extraction"""
    
    def extract(self, soup: BeautifulSoup, url: str) -> Dict[str, Any]:
        return {
            'headline': self._get_headline(soup),
            'author': self._get_author(soup),
            'publish_date': self._get_date(soup),
            'content': self._get_content(soup),
            'tags': self._get_tags(soup)
        }
    
    def _get_headline(self, soup: BeautifulSoup) -> Optional[str]:
        h1 = soup.find('h1')
        if h1:
            return h1.get_text(strip=True)
        return soup.title.string if soup.title else None
    
    def _get_author(self, soup: BeautifulSoup) -> Optional[str]:
        author = soup.find('meta', {'name': 'author'})
        if author:
            content = author.get('content')
            if isinstance(content, list):
                return content[0] if content else None
            return content
        author = soup.find(class_=re.compile(r'author', re.I))
        return author.get_text(strip=True) if author else None
    
    def _get_date(self, soup: BeautifulSoup) -> Optional[str]:
        date = soup.find('time')
        if date:
            datetime_attr = date.get('datetime')
            if datetime_attr:
                return datetime_attr[0] if isinstance(datetime_attr, list) else datetime_attr
            return date.get_text(strip=True)
        return None
    
    def _get_content(self, soup: BeautifulSoup) -> List[str]:
        article = soup.find('article') or soup.find(class_=re.compile(r'content|article', re.I))
        if article:
            return [p.get_text(strip=True) for p in article.find_all('p')]
        return [p.get_text(strip=True) for p in soup.find_all('p')]
    
    def _get_tags(self, soup: BeautifulSoup) -> List[str]:
        tags = soup.find_all('meta', {'property': 'article:tag'})
        result = []
        for tag in tags:
            content = tag.get('content')
            if content:
                if isinstance(content, list):
                    result.extend(content)
                else:
                    result.append(content)
        return result