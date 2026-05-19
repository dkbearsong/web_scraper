# Web Crawler Microservice

A powerful, production-ready Python microservice for extracting data from any website, including JavaScript-rendered SPAs, paginated content, and iframe-embedded pages. Built with Flask, BeautifulSoup, and Selenium.

## Features

- **Multiple Extraction Strategies**: Generic, Product, Article, and highly customizable CSS Selector-based extraction
- **JavaScript Rendering**: Full Selenium-based rendering for SPAs built with React, Vue, Angular, Next.js, Nuxt, etc.
- **Advanced Pagination**: Support for URL-based pagination, click-based pagination, and infinite scroll
- **Iframe Support**: Extract content from embedded iframes (Ashby job boards, embedded widgets, etc.)
- **Intelligent Click Handling**: Automatic overlay dismissal, element interception handling, and JavaScript click fallbacks
- **Content Change Detection**: Ensures page content actually updates between pagination clicks
- **Page Structure Analysis**: Automatic detection of page structure, content patterns, and recommended strategies
- **Table/List Extraction**: Extract structured data from HTML tables with configurable column mappings
- **Attribute Extraction**: Extract href, src, data-*, or any HTML attribute
- **Multi-page Crawling**: Recursive crawling with depth control and same-domain link following

---

## Table of Contents

- [Installation](#installation)
- [Quick Start](#quick-start)
- [API Endpoints](#api-endpoints)
- [Extraction Strategies](#extraction-strategies)
- [JavaScript Configuration](#javascript-configuration)
- [Pagination Handling](#pagination-handling)
- [Advanced Features](#advanced-features)
- [Complete Examples](#complete-examples)
- [Troubleshooting](#troubleshooting)
- [Performance & Security](#performance--security)

---

## Installation

### Prerequisites

- Python 3.8 or higher
- Chrome/Chromium browser (for JavaScript rendering)
- pip package manager

### Step 1: Install Dependencies

```bash
pip install flask requests beautifulsoup4 selenium webdriver-manager
```

### Step 2: Save and Run

Save the microservice code as `app.py`, then:

```bash
python app.py
```

The service will start on `http://localhost:5000`

### Docker Installation

```dockerfile
FROM python:3.9-slim

# Install Chrome
RUN apt-get update && apt-get install -y \
    wget gnupg2 \
    && wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google.list \
    && apt-get update && apt-get install -y google-chrome-stable

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app.py .
EXPOSE 5000

CMD ["python", "app.py"]
```

---

## Quick Start

### Extract from a Static Page

```bash
curl -X POST http://localhost:5000/extract \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com/product",
    "strategy": "product"
  }'
```

### Extract from a JavaScript-Rendered Page

```bash
curl -X POST http://localhost:5000/extract-js \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://react-app.com/jobs",
    "strategy": "selector",
    "selectors": {
      "jobs": ".job-listing"
    },
    "js_config": {
      "wait": {
        "type": "element",
        "value": ".job-listing",
        "timeout": 10
      },
      "headless": true,
      "user_data_dir": "/home/youruser/.config/google-chrome",
      "profile": "Default"
    }
  }'
```

---

## API Endpoints

### 1. Health Check

**GET** `/health`

Check if the service is running.

```bash
curl http://localhost:5000/health
```

**Response:**
```json
{
  "status": "healthy",
  "service": "web-crawler"
}
```

---

### 2. List Strategies

**GET** `/strategies`

Get available extraction strategies with descriptions.

```bash
curl http://localhost:5000/strategies
```

---

### 3. Quick Page Extraction (Static)

**POST** `/extract`

Extract data from static HTML pages (no JavaScript execution).

**Request Body:**
```json
{
  "url": "https://example.com",
  "strategy": "generic|product|article|selector",
  "selectors": {}
}
```

**Example:**
```bash
curl -X POST http://localhost:5000/extract \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://shop.example.com/product/123",
    "strategy": "product"
  }'
```

---

### 4. JavaScript Page Extraction

**POST** `/extract-js`

Extract data from JavaScript-rendered pages with full browser automation and advanced interaction capabilities.

#### **Basic Usage**
```bash
curl -X POST http://localhost:5052/extract-js \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://react-spa.example.com",
    "strategy": "selector",
    "selectors": {
      "title": "h1",
      "content": ".main-content"
    },
    "js_config": {
      "headless": true,
      "wait": {
        "type": "element",
        "value": ".main-content",
        "timeout": 10
      }
    }
  }'
```

#### **Request Body Parameters**

**Required:**
- `url` (string): Target URL to extract from
- `strategy` (string): Extraction strategy - `generic`, `product`, `article`, or `selector`

**Optional:**
- `selectors` (object): CSS selectors for extraction (required for `selector` strategy)
- `js_config` (object): JavaScript rendering configuration (see below)

#### **JavaScript Configuration (`js_config`)**

**Browser Settings:**
```json
{
  "js_config": {
    "headless": true,
    "user_data_dir": "/path/to/.config/google-chrome",
    "profile": "Default",
    "debug": false
  }
}
```
- `headless` (bool, default: `true`): Run Chrome in headless mode
- `user_data_dir` (string): Path to Chrome user data directory (enables cookie persistence)
- `profile` (string): Chrome profile name (e.g., "Default", "Profile 1")
- `debug` (bool, default: `false`): Enable debug logging and HTML output

**Wait Strategies:**

The `wait` configuration determines when to consider the page "ready" for extraction:

```json
{
  "wait": {
    "type": "time",
    "value": 3,
    "timeout": 10
  }
}
```

Available wait types:

| Type | Value | Description |
|------|-------|-------------|
| `time` | seconds (number) | Wait fixed seconds (e.g., 3) |
| `element` | CSS selector | Wait for element to appear (timeout in seconds) |
| `script` | JavaScript code | Wait for custom JS condition (e.g., `return document.readyState === 'complete'`) |
| `network_idle` | N/A | Wait for network activity to settle |

Examples:
```json
{
  "wait": {
    "type": "element",
    "value": ".content-loaded",
    "timeout": 15
  }
}
```

```json
{
  "wait": {
    "type": "script",
    "value": "return document.querySelectorAll('.job-card').length > 0",
    "timeout": 20
  }
}
```

**Action Sequences:**

Perform automated interactions before extraction:

```json
{
  "actions": [
    {"type": "click", "selector": "#accept-cookies", "use_js": true},
    {"type": "wait", "seconds": 2},
    {"type": "scroll", "max_scrolls": 5, "pause_time": 1.5},
    {"type": "click_until_gone", "selector": ".load-more", "max_clicks": 20},
    {"type": "load_all", "method": "scroll", "selector": ".load-more", "max_iterations": 10},
    {"type": "script", "code": "document.querySelectorAll('.popup').forEach(el => el.remove())"}
  ]
}
```

Action types:

| Type | Parameters | Description |
|------|------------|-------------|
| `click` | `selector`, `use_js` | Click an element (use_js=true for JS click) |
| `wait` | `seconds` | Wait for specified seconds |
| `scroll` | `max_scrolls`, `pause_time` | Scroll page down (pause between scrolls) |
| `click_until_gone` | `selector`, `max_clicks` | Click element repeatedly until it disappears |
| `load_all` | `method`, `selector`, `max_iterations` | Load all items (scroll or click method) |
| `script` | `code` | Execute custom JavaScript |

**Iframe Support:**

Extract content from iframes:

```json
{
  "js_config": {
    "iframe": "iframe[src*='ashby']"
  }
}
```

#### **Complete Example: Complex SPA with Actions**
```json
{
  "url": "https://careers.example.com/jobs",
  "strategy": "selector",
  "selectors": {
    "jobs": {
      "selector": ".job-card",
      "columns": [
        {"name": "title", "selector": ".title", "extract": "text"},
        {"name": "location", "selector": ".location", "extract": "text"},
        {"name": "link", "selector": "a@href"}
      ]
    }
  },
  "js_config": {
    "headless": true,
    "user_data_dir": "/home/user/.config/google-chrome",
    "profile": "Default",
    "wait": {
      "type": "element",
      "value": ".job-card",
      "timeout": 15
    },
    "actions": [
      {"type": "click", "selector": "#accept-all", "use_js": true},
      {"type": "wait", "seconds": 2},
      {"type": "scroll", "max_scrolls": 10, "pause_time": 1}
    ],
    "debug": false
  }
}
```

**Response:**
```json
{
  "success": true,
  "url": "https://careers.example.com/jobs",
  "data": {
    "jobs": [
      {
        "title": "Software Engineer",
        "location": "San Francisco, CA",
        "link": "https://careers.example.com/jobs/123"
      }
    ]
  }
}
```

---

### 5. Multi-Page Crawling (Static)

**POST** `/crawl`

Crawl multiple pages by following internal links.

**Request Body:**
```json
{
  "url": "https://example.com/blog",
  "strategy": "article",
  "config": {
    "max_depth": 2,
    "max_pages": 20,
    "delay": 1.5,
    "follow_links": true
  }
}
```

---

### 6. Multi-Page Crawling (JavaScript)

**POST** `/crawl-js`

Crawl JavaScript-rendered pages with link following.

**Request Body:**
```json
{
  "url": "https://spa-site.com",
  "strategy": "selector",
  "selectors": {"articles": "article"},
  "config": {
    "max_depth": 2,
    "max_pages": 10,
    "follow_links": true
  },
  "js_config": {
    "wait": {"type": "time", "value": 3},
    "headless": true
  }
}
```

---

### 7. Paginated Content Extraction

**POST** `/extract-paginated`

Extract data from multi-page results with support for both URL-based pagination (page numbers in URL) and click-based pagination (clicking "Next" button). Handles both static and JavaScript-rendered pages.

#### **Pagination Method 1: URL-Based Pagination**

Use when page numbers are in the URL (e.g., `?page=1`, `?p=2`).

**Request:**
```json
{
  "url_template": "https://jobs.example.com/search?keywords=python&page={page}",
  "start_page": 1,
  "end_page": 5,
  "strategy": "selector",
  "selectors": {
    "jobs": {
      "selector": ".job-card",
      "columns": [
        {"name": "title", "selector": ".title", "extract": "text"},
        {"name": "company", "selector": ".company", "extract": "text"},
        {"name": "link", "selector": "a@href"}
      ]
    }
  },
  "delay": 1.5
}
```

**URL-Based Parameters:**
- `url_template` (string, required): URL with `{page}` placeholder for page numbers
- `start_page` (int, default: 1): First page number
- `end_page` (int, default: 10): Last page number
- `strategy` (string): Extraction strategy (`generic`, `product`, `article`, `selector`)
- `selectors` (object): Selectors for data extraction
- `delay` (float, default: 1.0): Delay between page requests (seconds)
- `js_config` (object, optional): For JavaScript-rendered pages

**Example with JavaScript Rendering:**
```json
{
  "url_template": "https://react-jobs.app/search?q=python&page={page}",
  "start_page": 1,
  "end_page": 10,
  "strategy": "selector",
  "selectors": {
    "title": ".job-title",
    "company": ".company-name"
  },
  "js_config": {
    "headless": true,
    "wait": {
      "type": "element",
      "value": ".job-title",
      "timeout": 10
    },
    "user_data_dir": "/home/user/.config/google-chrome",
    "profile": "Default"
  },
  "delay": 2.0
}
```

**Response:**
```json
{
  "success": true,
  "total_pages": 5,
  "data": [
    {
      "page": 1,
      "url": "https://jobs.example.com/search?keywords=python&page=1",
      "items": [
        {"title": "Senior Python Dev", "company": "TechCorp", "link": "..."}
      ]
    },
    {
      "page": 2,
      "url": "https://jobs.example.com/search?keywords=python&page=2",
      "items": [...]
    }
  ]
}
```

---

#### **Pagination Method 2: Click-Based Pagination**

Use when you click a "Next" button or similar element to load next page.

**Basic Click Pagination:**
```json
{
  "url": "https://jobs.example.com/search",
  "pagination": {
    "method": "click",
    "next_selector": "a.pagination-next",
    "max_pages": 10,
    "wait_after_click": 3
  },
  "strategy": "selector",
  "selectors": {
    "jobs": ".job-listing"
  },
  "js_config": {
    "headless": true,
    "wait": {
      "type": "element",
      "value": ".job-listing",
      "timeout": 10
    }
  }
}
```

**Click-Based Parameters:**

**pagination object:**
- `method` (string, required): "click" for click-based pagination
- `next_selector` (string, required): CSS selector for the "Next" button/link
- `max_pages` (int, default: 10): Maximum number of pages to scrape
- `wait_after_click` (float, default: 2): Wait time after clicking Next (seconds)
- `use_js` (bool, default: true): Use JavaScript click instead of Selenium click
- `content_change_selector` (string, optional): Selector to verify page content changed

**js_config object:** Same as extract-js endpoint

**Example: LinkedIn-Style Pagination**
```json
{
  "url": "https://linkedin.com/jobs/search/?keywords=python",
  "pagination": {
    "method": "click",
    "next_selector": "button.jobs-search-pagination__button--next",
    "max_pages": 5,
    "wait_after_click": 3,
    "use_js": true,
    "content_change_selector": "div.artdeco-entity-lockup"
  },
  "strategy": "selector",
  "selectors": {
    "title": "div.artdeco-entity-lockup__title a span strong",
    "company": "div.artdeco-entity-lockup__subtitle span",
    "location": "div.artdeco-entity-lockup__caption span[dir='ltr']",
    "link": "div.artdeco-entity-lockup__title a@href"
  },
  "js_config": {
    "headless": true,
    "user_data_dir": "/home/user/.config/google-chrome",
    "profile": "Default",
    "wait": {
      "type": "element",
      "value": "div.artdeco-entity-lockup",
      "timeout": 15
    }
  }
}
```

**Content Change Detection:**

Click-based pagination automatically detects when new content loads by comparing page content before/after the click. You can customize this detection:

```json
{
  "pagination": {
    "method": "click",
    "next_selector": ".next-page",
    "max_pages": 20,
    "wait_after_click": 2,
    "content_change_selector": ".item-card"
  }
}
```

The scraper will:
1. Get a snapshot of content matching `content_change_selector` before click
2. Click the Next button
3. Wait for new content to appear (verifying actual page change)
4. Extract data from new content
5. Repeat until Next button disappears or max_pages reached

**Advanced: Initial Actions**

Perform setup actions before pagination starts:

```json
{
  "url": "https://example.com/jobs",
  "pagination": {
    "method": "click",
    "next_selector": ".next-btn",
    "max_pages": 10,
    "wait_after_click": 2
  },
  "strategy": "selector",
  "selectors": {"jobs": ".job-card"},
  "js_config": {
    "headless": true,
    "wait": {"type": "time", "value": 2},
    "actions": [
      {"type": "click", "selector": "#filters"},
      {"type": "wait", "seconds": 1},
      {"type": "scroll", "max_scrolls": 3}
    ]
  }
}
```

**Response:**
```json
{
  "success": true,
  "total_pages": 5,
  "data": [
    {
      "page": 1,
      "url": "https://jobs.example.com/search",
      "items": [
        {
          "title": "Senior Python Developer",
          "company": "TechCorp",
          "location": "Remote",
          "link": "https://..."
        }
      ]
    },
    {
      "page": 2,
      "url": "https://jobs.example.com/search",
      "items": [...]
    }
  ]
}
```

**Error Handling:**

If pagination stops before reaching `max_pages`, the response will include information about why:

```json
{
  "success": true,
  "total_pages": 3,
  "stopped_reason": "No next button found on page 3",
  "data": [...]
}
```

---

### 8. Page Structure Analysis

**POST** `/analyze`

Automatically analyze page structure and get recommended extraction strategies.

**Request Body:**
```json
{
  "url": "https://example.com/product"
}
```

**Response:**
```json
{
  "success": true,
  "analysis": {
    "metadata": {
      "title": "Product Name",
      "description": "...",
      "og_tags": {}
    },
    "structure": {
      "headings": [...],
      "main_container": {...}
    },
    "content_hints": {
      "price_indicators": [{"selector": ".price", "text": "$29.99"}],
      "date_indicators": [...]
    },
    "recommended_strategy": {
      "recommended": "product",
      "confidence": 5,
      "custom_selector_template": {
        "title": ".product-title",
        "price": ".price-tag"
      }
    }
  }
}
```

---

## Extraction Strategies

### 1. Generic Strategy

Extracts common elements from any page.

```json
{
  "strategy": "generic"
}
```

**Extracts:** Title, headings (H1-H6), paragraphs, images, meta tags

---

### 2. Product Strategy

Optimized for e-commerce product pages.

```json
{
  "strategy": "product"
}
```

**Extracts:** Product name, price, description, availability, images

---

### 3. Article Strategy

Optimized for blog posts and news articles.

```json
{
  "strategy": "article"
}
```

**Extracts:** Headline, author, publish date, content, tags

---

### 4. Selector Strategy (Most Powerful)

Custom CSS selector-based extraction with advanced features.

#### **Simple Text Extraction**
```json
{
  "strategy": "selector",
  "selectors": {
    "title": "h1.product-title",
    "price": ".price"
  }
}
```

#### **Attribute Extraction**
```json
{
  "selectors": {
    "product_link": "a.product@href",
    "image": "img.product@src",
    "data_id": ".product@data-id"
  }
}
```

#### **Advanced Configuration**
```json
{
  "selectors": {
    "description": {
      "selector": ".description",
      "extract": "html",
      "multiple": false
    },
    "main_link": {
      "selector": ".product",
      "child": "a",
      "extract": "attr",
      "attribute": "href"
    }
  }
}
```

#### **Table/Structured Data Extraction**
```json
{
  "selectors": {
    "jobs": {
      "selector": "table.jobs tbody tr",
      "extract": "table",
      "columns": [
        {"name": "title", "selector": "td:nth-child(1) a", "extract": "text"},
        {"name": "location", "selector": "td:nth-child(2)", "extract": "text"},
        {"name": "link", "selector": "td:nth-child(1) a@href"}
      ]
    }
  }
}
```

**Extract Types:**
- `text` - Extract text content (default)
- `html` - Extract raw HTML
- `attr` - Extract specific attribute
- `table` - Extract structured rows with columns

---

## JavaScript Configuration

### Wait Strategies

#### **Time-Based Wait**
```json
{
  "wait": {
    "type": "time",
    "value": 3
  }
}
```

#### **Wait for Element**
```json
{
  "wait": {
    "type": "element",
    "value": ".product-list",
    "timeout": 10
  }
}
```

#### **Wait for Script Condition**
```json
{
  "wait": {
    "type": "script",
    "value": "return document.querySelectorAll('.item').length > 10",
    "timeout": 15
  }
}
```

#### **Wait for Content to Load (Next.js/Nuxt)**
```json
{
  "wait": {
    "type": "script",
    "value": "return document.querySelectorAll('.job-card').length > 0 && document.querySelector('.job-card').textContent.trim().length > 10",
    "timeout": 15
  }
}
```

---

### Actions

Execute actions before or during extraction.

#### **Click Element**
```json
{
  "type": "click",
  "selector": ".load-more",
  "use_js": true,
  "dismiss_overlays": true
}
```

#### **Click Until Element Gone**
```json
{
  "type": "click_until_gone",
  "selector": ".load-more",
  "max_clicks": 20,
  "pause_time": 2,
  "use_js": true
}
```

#### **Scroll to Bottom**
```json
{
  "type": "scroll",
  "max_scrolls": 5,
  "pause_time": 1.5
}
```

#### **Load All Content**
```json
{
  "type": "load_all",
  "method": "scroll",
  "max_iterations": 10,
  "pause_time": 2
}
```

Or for click-based:
```json
{
  "type": "load_all",
  "method": "click",
  "selector": ".load-more",
  "max_iterations": 20,
  "pause_time": 2
}
```

#### **Execute Custom JavaScript**
```json
{
  "type": "script",
  "code": "document.querySelector('.modal-overlay')?.remove();"
}
```

#### **Wait/Pause**
```json
{
  "type": "wait",
  "seconds": 2
}
```

---

### Iframe Support

Extract content from embedded iframes:

```json
{
  "js_config": {
    "iframe": "iframe[src*='ashbyhq.com']",
    "wait": {
      "type": "element",
      "value": ".job-listing",
      "timeout": 10
    }
  }
}
```

---

## Pagination Handling

### URL-Based Pagination

When page numbers are in the URL:

```json
{
  "url_template": "https://example.com/jobs?page={page}",
  "start_page": 1,
  "end_page": 20,
  "strategy": "selector",
  "selectors": {...},
  "delay": 1.5
}
```

Works with:
- Query parameters: `?page=1`
- Path parameters: `/page/1`
- Hash routes: `#/page/1`

### Click-Based Pagination

When clicking "Next" button:

```json
{
  "url": "https://example.com/jobs",
  "pagination": {
    "method": "click",
    "next_selector": "a[title='Next']",
    "max_pages": 20,
    "wait_after_click": 3,
    "use_js": true
  },
  "strategy": "selector",
  "selectors": {...}
}
```

**Tips for Finding the Right Selector:**
- Use `a[title='Next']` for buttons with title attribute
- Use `.pagination-next` for class-based selectors
- Use `a[aria-label*='next']` for aria-label attributes
- Avoid dynamic class names like `_container_j2da7_1`
- Use stable classes like `pagination-link` or `ashby-job-posting`

---

## Advanced Features

### Handling Intercepted Clicks

When modals or overlays block clicks:

```json
{
  "js_config": {
    "actions": [
      {
        "type": "script",
        "code": "document.querySelectorAll('.modal, .overlay').forEach(el => el.remove());"
      },
      {
        "type": "click",
        "selector": ".next-button",
        "use_js": true,
        "dismiss_overlays": true
      }
    ]
  }
}
```

The system automatically:
- Dismisses common overlays before clicks
- Falls back to JavaScript click if regular click fails
- Scrolls elements into view
- Waits for elements to be clickable

### Dynamic Class Names (CSS Modules)

For Next.js/Nuxt sites with hashed class names:

❌ **Bad:** `._container_j2da7_1` (changes on each build)

✅ **Good:** `.ashby-job-posting-brief-title` (stable)

```json
{
  "selectors": {
    "title": ".ashby-job-posting-brief-title",
    "jobs": ".job-card"
  }
}
```

### Content Change Detection

The paginated endpoint automatically detects when content changes after clicking "Next":

- Captures page content before click
- Clicks next button
- Waits and verifies content actually changed
- Retries up to 10 times if needed
- Stops if content doesn't change

---

## Complete Examples

### Example 1: E-commerce Product Scraping

```bash
curl -X POST http://localhost:5000/extract \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://shop.example.com/product/123",
    "strategy": "selector",
    "selectors": {
      "name": "h1.product-name",
      "price": ".price-current",
      "availability": ".stock-status",
      "images": "img.product-image@src",
      "description": {
        "selector": ".product-description",
        "extract": "html"
      }
    }
  }'
```

---

### Example 2: Job Listings (JavaScript-Rendered)

```bash
curl -X POST http://localhost:5000/extract-js \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://careers.example.com/jobs",
    "strategy": "selector",
    "selectors": {
      "jobs": {
        "selector": "div.job-card",
        "extract": "table",
        "columns": [
          {"name": "title", "selector": "h3", "extract": "text"},
          {"name": "location", "selector": ".location", "extract": "text"},
          {"name": "link", "selector": "a@href"}
        ]
      }
    },
    "js_config": {
      "wait": {
        "type": "element",
        "value": ".job-card",
        "timeout": 10
      },
      "headless": true
    }
  }'
```

---

### Example 3: Paginated Job Board

```bash
curl -X POST http://localhost:5000/extract-paginated \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://monday.com/careers",
    "pagination": {
      "method": "click",
      "next_selector": "a.pagination-link[title=\"Next\"]",
      "max_pages": 22,
      "wait_after_click": 3,
      "use_js": true
    },
    "strategy": "selector",
    "selectors": {
      "title": "div.position-name",
      "location": "div.tags div:nth-child(2) span",
      "link": "a[href]@href"
    },
    "js_config": {
      "wait": {"type": "time", "value": 3},
      "headless": true
    }
  }'
```

---

### Example 4: Iframe-Embedded Content

```bash
curl -X POST http://localhost:5000/extract-js \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://n8n.io/careers/",
    "strategy": "selector",
    "selectors": {
      "title": ".ashby-job-posting-brief-title",
      "location": ".ashby-job-posting-brief-details p",
      "link": "a[href*=\"/n8n/\"]@href"
    },
    "js_config": {
      "iframe": "iframe[src*=\"ashbyhq.com\"]",
      "wait": {
        "type": "element",
        "value": ".ashby-job-posting-brief-title",
        "timeout": 15
      },
      "headless": true
    }
  }'
```

---

### Example 5: Infinite Scroll

```bash
curl -X POST http://localhost:5000/extract-js \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://social.example.com/feed",
    "strategy": "selector",
    "selectors": {
      "posts": ".post-item"
    },
    "js_config": {
      "wait": {"type": "time", "value": 2},
      "actions": [
        {
          "type": "load_all",
          "method": "scroll",
          "max_iterations": 10,
          "pause_time": 2
        }
      ],
      "headless": true
    }
  }'
```

---

## Troubleshooting

### Issue: Null Values from Next.js/Nuxt Sites

**Problem:** Elements exist but data is null.

**Solution:** Use script-based wait for content hydration:

```json
{
  "js_config": {
    "wait": {
      "type": "script",
      "value": "return document.querySelectorAll('.job-card').length > 0 && document.querySelector('.job-card').textContent.trim().length > 10",
      "timeout": 15
    },
    "actions": [
      {"type": "wait", "seconds": 3}
    ]
  }
}
```

### Issue: Element Click Intercepted

**Problem:** `element click intercepted` error.

**Solution:** Use JavaScript click with overlay dismissal:

```json
{
  "js_config": {
    "actions": [
      {
        "type": "click",
        "selector": ".button",
        "use_js": true,
        "dismiss_overlays": true
      }
    ]
  }
}
```

### Issue: Wrong Pagination Button Selected

**Problem:** Clicking page number instead of next arrow.

**Solution:** Use specific attributes:

```json
{
  "pagination": {
    "next_selector": "a[title='Next']"
  }
}
```

Or target by content:
```json
{
  "pagination": {
    "next_selector": "a.pagination-link:not([aria-label])"
  }
}
```

### Issue: Pagination Returns Same Data

**Problem:** All pages return identical data.

**Cause:** Content not changing after click.

**Solution:** The system now automatically detects this. Check console logs for:
```
Warning: Content didn't change after clicking next on page X
```

Increase `wait_after_click`:
```json
{
  "pagination": {
    "wait_after_click": 5
  }
}
```

### Issue: Chrome Driver Errors

**Solution:**

```bash
# Update webdriver-manager
pip install --upgrade webdriver-manager

# Or set Chrome binary
export CHROME_BIN=/usr/bin/google-chrome
```

### Debugging Tips

1. **Use `headless: false`** to see what's happening:
```json
{
  "js_config": {
    "headless": false
  }
}
```

2. **Check console output** for debug messages showing page numbers and content changes

3. **Use `/analyze` endpoint** to discover correct selectors

4. **Test selectors in browser DevTools** before using them

---

## Performance & Security

### Performance Tips

1. **Use `/extract` for static pages** - Much faster than `/extract-js`
2. **Set appropriate delays** - Respect rate limits with `delay` config
3. **Limit crawl scope** - Use `max_depth` and `max_pages`
4. **Use specific selectors** - More specific = faster extraction
5. **Enable headless mode** - Always use `"headless": true` in production
6. **Batch operations** - Use table extraction instead of multiple selectors

### Security Considerations

- **Rate Limiting**: Implement rate limiting in production environments
- **URL Validation**: Validate and sanitize input URLs
- **Resource Limits**: Set max timeout and page limits
- **Authentication**: Add API key authentication for production
- **CORS**: Configure CORS policies appropriately
- **Logging**: Monitor for abuse patterns
- **Sandboxing**: Run in containerized environment

### Rate Limiting Example

```python
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["100 per hour"]
)

@app.route('/extract-js', methods=['POST'])
@limiter.limit("10 per minute")
def extract_js():
    # ...
```

---

## API Summary

| Endpoint | Use Case | JavaScript | Pagination |
|----------|----------|------------|------------|
| `/extract` | Static HTML pages | ❌ | ❌ |
| `/extract-js` | Single JS-rendered page | ✅ | ❌ |
| `/crawl` | Multi-page static crawl | ❌ | Link following |
| `/crawl-js` | Multi-page JS crawl | ✅ | Link following |
| `/extract-paginated` | Numbered pages | ✅ | URL or Click |
| `/analyze` | Page structure analysis | ❌ | ❌ |

---

## Contributing

Contributions welcome! Please:

1. Test changes thoroughly
2. Follow existing code style
3. Add documentation for new features
4. Update this README

---

## License

MIT License - Free to use in your projects!

---

## Support

For issues, questions, or feature requests, please open an issue on the project repository.

---

## Changelog

### Version 2.0
- Added iframe support for embedded content
- Enhanced click handling with automatic overlay dismissal
- Improved pagination with content change detection
- Added support for Next.js/Nuxt dynamic class names
- Better error messages and debug logging
- Fixed table extraction with @ attribute syntax

### Version 1.0
- Initial release
- Basic extraction strategies
- JavaScript rendering support
- Multi-page crawling
- Page analysis