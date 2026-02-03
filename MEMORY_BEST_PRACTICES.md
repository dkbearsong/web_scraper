# Memory Leak Prevention Best Practices

## For Future Development

### 1. **Resource Management Pattern**
Always use context managers or explicit cleanup:

```python
# ❌ BAD - Resource leak risk
import requests
session = requests.Session()
# ... use session ...
# Missing close!

# ✅ GOOD - Explicit cleanup
import requests
session = requests.Session()
try:
    # ... use session ...
finally:
    session.close()

# ✅ BETTER - Context manager
import requests
# requests.Session doesn't support context manager, but you can create a wrapper:
with closing(requests.Session()) as session:
    # ... use session ...
    # Automatically closed
```

### 2. **Selenium WebDriver Pattern**
```python
# ❌ BAD - Multiple drivers not cleaned up
def crawl_pages(pages):
    for page in pages:
        driver = webdriver.Chrome()  # NEW DRIVER EACH TIME
        # ... use driver ...
        # driver never quit!

# ✅ GOOD - Single reusable driver
def crawl_pages(pages):
    driver = webdriver.Chrome()
    try:
        for page in pages:
            # ... use driver ...
    finally:
        driver.quit()

# ✅ BETTER - Context manager
class ManagedDriver:
    def __enter__(self):
        self.driver = webdriver.Chrome()
        return self.driver
    
    def __exit__(self, *args):
        self.driver.quit()

def crawl_pages(pages):
    with ManagedDriver() as driver:
        for page in pages:
            # ... use driver ...
```

### 3. **aiohttp Session Pattern**
```python
# ❌ BAD - Session never closed
async def fetch_data():
    session = aiohttp.ClientSession()
    # ... use session ...
    # session never closed!

# ✅ GOOD - Explicit cleanup
async def fetch_data():
    session = aiohttp.ClientSession()
    try:
        # ... use session ...
    finally:
        await session.close()

# ✅ BETTER - Store in app state
class MyApp:
    async def startup(self):
        self.session = aiohttp.ClientSession()
    
    async def shutdown(self):
        await self.session.close()
```

### 4. **Database Connection Pattern**
```python
# ❌ BAD - Connection pooling not used, connections leak
import psycopg2
def query_db(sql):
    conn = psycopg2.connect(...)
    # ... use conn ...
    # conn.close() forgotten in error paths

# ✅ GOOD - Connection pooling with cleanup
from psycopg2 import pool

db_pool = pool.SimpleConnectionPool(5, 20, "...")

def query_db(sql):
    conn = db_pool.getconn()
    try:
        # ... use conn ...
    finally:
        db_pool.putconn(conn)

# ✅ BETTER - Use context manager
def query_db(sql):
    with get_db_connection() as conn:
        # ... use conn ...
        # Automatically returned to pool
```

### 5. **File Handling Pattern**
```python
# ❌ BAD - File never closed
def process_file(filename):
    f = open(filename, 'r')
    data = f.read()
    # File not closed on error!

# ✅ GOOD - Explicit cleanup
def process_file(filename):
    f = open(filename, 'r')
    try:
        data = f.read()
    finally:
        f.close()

# ✅ BETTER - Context manager
def process_file(filename):
    with open(filename, 'r') as f:
        data = f.read()
    # Automatically closed
```

### 6. **BeautifulSoup Pattern**
```python
# ❌ BAD - Large soup objects accumulate
def extract_all_pages(urls):
    results = []
    for url in urls:
        response = requests.get(url)
        soup = BeautifulSoup(response.content, 'html.parser')
        results.append(soup)  # Keeps all in memory!
    return results

# ✅ GOOD - Process and discard
def extract_all_pages(urls):
    results = []
    for url in urls:
        response = requests.get(url)
        soup = BeautifulSoup(response.content, 'html.parser')
        data = extract_data(soup)  # Extract, don't keep soup
        results.append(data)
    return results

# ✅ BETTER - Generator for large datasets
def extract_all_pages(urls):
    for url in urls:
        response = requests.get(url)
        soup = BeautifulSoup(response.content, 'html.parser')
        yield extract_data(soup)  # Memory freed after each iteration
```

---

## Code Review Checklist

Before pushing code, verify:

- [ ] All file handles closed (`.close()` or context manager)
- [ ] All database connections returned to pool or closed
- [ ] All aiohttp sessions closed
- [ ] All Selenium drivers quitted
- [ ] No circular references between objects
- [ ] Large objects not kept in memory unnecessarily
- [ ] Exception paths have cleanup (try-finally or context managers)
- [ ] No growth in memory over time during operation
- [ ] Long-running loops have cleanup points

---

## Debugging Memory Leaks

### Method 1: Memory Profiler
```bash
pip install memory-profiler
python -m memory_profiler your_script.py
```

### Method 2: psutil
```python
import psutil
import os

process = psutil.Process(os.getpid())
print(f"Memory: {process.memory_info().rss / 1024 / 1024:.2f} MB")
```

### Method 3: objgraph (Best for Finding Leaks)
```bash
pip install objgraph
```

```python
import objgraph

# At start
objgraph.show_most_common_types(limit=10)

# At end
objgraph.show_growth()  # Shows new objects
```

### Method 4: tracemalloc (Python built-in)
```python
import tracemalloc

tracemalloc.start()

# ... your code ...

snapshot = tracemalloc.take_snapshot()
top_stats = snapshot.statistics('lineno')
for stat in top_stats[:10]:
    print(stat)
```

---

## Common Memory Leak Causes

1. **Unclosed resources** - Connections, files, sessions
2. **Growing caches** - Lists/dicts that never clear
3. **Circular references** - Objects referencing each other
4. **Event listeners** - Not unregistered
5. **Timer/interval functions** - Not cleared
6. **Large intermediate objects** - Not discarded after use
7. **String concatenation in loops** - Creates new strings each time
8. **Keeping old references** - Objects never garbage collected

---

## Flask-Specific Issues

```python
# ❌ BAD - Request context leaks
@app.route('/crawl')
def crawl():
    driver = webdriver.Chrome()  # Per-request but not cleaned up

# ✅ GOOD - Teardown cleanup
@app.teardown_request
def cleanup(exception):
    if hasattr(g, 'driver'):
        g.driver.quit()

# ✅ BETTER - Use context in request
from flask import g

@app.route('/crawl')
def crawl():
    with ManagedDriver() as driver:
        # ... use driver ...
        # Cleaned up after request
```

---

## Performance Impact

These patterns have minimal performance impact:
- Context managers: <1% overhead
- Try-finally: <1% overhead
- Connection pooling: **10-50% improvement**
- Memory efficiency: **100-1000% improvement** (less garbage collection)

Apply these patterns for better reliability and performance!
