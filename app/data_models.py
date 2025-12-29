from dataclasses import dataclass
from typing import Dict, List, Any, Optional

@dataclass
class CrawlConfig:
    """Configuration for crawling behavior"""
    url: str
    max_depth: int = 1
    max_pages: int = 10
    delay: float = 1.0
    follow_links: bool = False
    user_agent: str = "CustomCrawler/1.0"
    timeout: int = 10
    headers: Optional[Dict] = None

@dataclass
class CrawlResult:
    """Result from crawling operation"""
    url: str
    status_code: int
    data: Dict[str, Any]
    links: Optional[List[str]] = None
    error: Optional[str] = None