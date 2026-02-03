# Memory Leak Analysis Report

## Critical Issues Found

### 1. **CRITICAL: Unclosed Selenium WebDriver in JSWebCrawler** ⚠️
**File:** [app/crawler.py](app/crawler.py#L123)  
**Issue:** The `JSWebCrawler._crawl_recursive()` method creates a `JavaScriptRenderer` context manager inside a loop. However, if an exception occurs during recursive crawling, the driver may not be properly cleaned up.

```python
with JavaScriptRenderer(headless=headless) as renderer:
    # ... operations ...
    if self.config.follow_links:
        for link in links[:5]:
            if len(self.results) < self.config.max_pages:
                self._crawl_recursive(link, depth + 1)  # Recursive call
```

**Problem:** When recursion happens, multiple WebDriver instances are created and kept in memory. Each recursive call creates new Selenium instances that aren't cleaned up until the recursion unwinds.

**Impact:** HIGH - This is likely your primary memory leak. Selenium WebDriver consumes 100+ MB per instance.

---

### 2. **CRITICAL: Duplicate Link Following Logic** ⚠️
**File:** [app/crawler.py](app/crawler.py#L77-L85)  
**Issue:** The link-following code is duplicated and runs twice:

```python
# Follow links if configured - FIRST TIME
if self.config.follow_links:
    for link in links[:5]:
        if len(self.results) < self.config.max_pages:
            self._crawl_recursive(link, depth + 1)

# Follow links if configured - SECOND TIME (DUPLICATE!)
if self.config.follow_links:
    for link in links[:5]:
        if len(self.results) < self.config.max_pages:
            self._crawl_recursive(link, depth + 1)
```

**Problem:** Every link gets crawled twice, doubling memory usage and causing 2x more WebDriver instances.

**Impact:** HIGH - This directly multiplies your memory consumption.

---

### 3. **HIGH: Unclosed HTTP Session in extract_paginated.py**
**File:** [app/extract_paginated.py](app/extract_paginated.py#L70)  
**Issue:** `requests.Session()` is created but never explicitly closed:

```python
session = requests.Session()
session.headers.update({'User-Agent': 'CustomCrawler/1.0'})

for page_num in range(start_page, end_page + 1):
    # ... loop ...
    time.sleep(delay)
    # session never explicitly closed!
```

**Problem:** Session objects hold connection pools. Not closing them leaves connections open, consuming memory and file descriptors.

**Impact:** MEDIUM - Accumulates over multiple pagination requests.

---

### 4. **HIGH: Multiple cloudscraper Instances**
**File:** [app/crawler.py](app/crawler.py#L28)  
**Issue:** A `cloudscraper` instance is created and stored in `__init__`, but a new one is also created inside `_crawl_recursive()`:

```python
def __init__(self, ...):
    self.scraper = cloudscraper.create_scraper()  # Instance 1

def _crawl_recursive(self, url: str, depth: int):
    if response.status_code == 403:
        scraper = cloudscraper.create_scraper()  # Instance 2 (new one each time!)
```

**Problem:** Each time a 403 error occurs, a new `cloudscraper` instance is created and abandoned (not reused or cleaned up).

**Impact:** MEDIUM - Creates memory leak when encountering 403 responses.

---

### 5. **HIGH: aiohttp ClientSession Never Closed**
**File:** [app/job_search_agent.py](app/job_search_agent.py#L44)  
**Issue:** An `aiohttp.ClientSession` is created but never explicitly closed:

```python
@classmethod
async def create(cls):
    # ...
    session = aiohttp.ClientSession()  # Created but never closed!
    client = OllamaClient(session, ...)
    return cls(client)
```

**Problem:** aiohttp sessions hold TCP connections and memory that must be explicitly closed.

**Impact:** MEDIUM-HIGH - Each agent instance leaks a session connection.

---

### 6. **MEDIUM: Unbounded Results List in WebCrawler**
**File:** [app/crawler.py](app/crawler.py#L44)  
**Issue:** `self.results` list grows indefinitely:

```python
def crawl(self) -> List[CrawlResult]:
    self._crawl_recursive(self.config.url, 0)
    return self.results  # Returned but never cleared
```

**Problem:** After a crawl completes, the results list stays in memory for the object's lifetime. If the same crawler object is reused, results accumulate.

**Impact:** LOW-MEDIUM - Only problematic if crawler objects are reused.

---

### 7. **MEDIUM: BeautifulSoup Parser Caching**
**File:** Multiple files  
**Issue:** BeautifulSoup with html.parser doesn't explicitly clean up:

```python
soup = BeautifulSoup(response.content, 'html.parser')
```

**Problem:** Large HTML documents parsed into soup objects consume memory. When parsed frequently, they can accumulate.

**Impact:** LOW - Usually garbage collected, but worth monitoring with large pages.

---

### 8. **MEDIUM: PostgreSQL Connection Not Always Closed**
**File:** [app/postgres_mgr.py](app/postgres_mgr.py#L58-L69)  
**Issue:** In `database_exists()`, a temporary connection is created:

```python
def database_exists(self, dbname: str) -> bool:
    temp_conn = psycopg2.connect(...)
    temp_conn.autocommit = True
    try:
        with temp_conn.cursor() as cur:
            # ...
    finally:
        temp_conn.close()  # Good! But only in finally
```

**Problem:** While this has a finally block, if an exception occurs during connection creation, the connection object might not be properly closed in all scenarios.

**Impact:** LOW - The finally block helps, but connection pooling isn't used.

---

### 9. **MEDIUM: Flask Debug Mode in Production**
**File:** [main.py](main.py#L475)  
**Issue:**

```python
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5052, debug=True)
```

**Problem:** `debug=True` keeps more memory-intensive debugging features active and reloads the app on file changes, potentially causing resource leaks.

**Impact:** LOW - But should be `False` in production.

---

## Recommended Fixes (Priority Order)

### 🔴 PRIORITY 1: Fix WebDriver Memory Leaks
1. Create a WebDriver pool instead of creating new drivers per page
2. Reuse drivers across multiple pages in recursive crawling
3. Implement proper cleanup with try-except-finally

### 🔴 PRIORITY 2: Remove Duplicate Link Following
Delete the duplicated link-following code in [app/crawler.py](app/crawler.py#L80-L85)

### 🟠 PRIORITY 3: Close HTTP Sessions
Wrap session creation in context manager or explicitly close in try-finally

### 🟠 PRIORITY 4: Fix aiohttp Session Leak
Add async cleanup method to close the session

### 🟠 PRIORITY 5: Fix cloudscraper Instances
Reuse scraper instance or clean up properly when creating new ones

### 🟡 PRIORITY 6: Add Garbage Collection
Call `gc.collect()` after large operations

---

## Testing Recommendation

Monitor memory usage while running:
```bash
watch -n 1 'ps aux | grep python'
```

Or use Python's memory profiler:
```bash
pip install memory-profiler
python -m memory_profiler main.py
```
