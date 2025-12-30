# Web Crawler Microservice

A powerful, customizable Python-based microservice for extracting data from websites, including JavaScript-rendered pages. Built with Flask, BeautifulSoup, and Selenium.

## Features

- **Multiple Extraction Strategies**: Generic, Product, Article, and Custom Selector-based extraction
- **JavaScript Support**: Full support for SPA and dynamically-loaded content using Selenium
- **Flexible Selectors**: Extract text, HTML, attributes, and structured table data
- **Page Analysis**: Automatic detection of page structure and content patterns
- **Multi-page Crawling**: Recursive crawling with depth control and link following
- **RESTful API**: Easy integration with any application via HTTP endpoints

---

## Installation

### Prerequisites

- Python 3.8 or higher
- Chrome/Chromium browser (for JavaScript rendering)
- pip package manager

### Step 1: Clone or Download

Save the microservice code to a file named `app.py`.

### Step 2: Install Dependencies

```bash
pip install flask requests beautifulsoup4 selenium webdriver-manager
```

### Step 3: Run the Service

```bash
python app.py
```

The service will start on `http://localhost:5000`

### Docker Installation (Optional)

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

## API Endpoints

### Health Check

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

### List Available Strategies

**GET** `/strategies`

Get information about available extraction strategies.

```bash
curl http://localhost:5000/strategies
```

---

### Quick Single-Page Extraction

**POST** `/extract`

Extract data from a single page (no JavaScript rendering).

**Request Body:**
```json
{
  "url": "https://example.com",
  "strategy": "generic",
  "selectors": {}
}
```

**Example:**
```bash
curl -X POST http://localhost:5000/extract \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com/product",
    "strategy": "product"
  }'
```

**Response:**
```json
{
  "success": true,
  "data": {
    "url": "https://example.com/product",
    "status_code": 200,
    "data": {
      "product_name": "Example Product",
      "price": "$29.99",
      "description": "Product description..."
    }
  }
}
```

---

### JavaScript-Rendered Page Extraction

**POST** `/extract-js`

Extract data from JavaScript-heavy pages (SPAs, React, Vue, Angular, etc.).

**Request Body:**
```json
{
  "url": "https://example.com",
  "strategy": "selector",
  "selectors": {
    "title": "h1",
    "data": {
      "selector": "table tr",
      "extract": "table",
      "columns": [
        {"name": "name", "selector": "td:first-child", "extract": "text"},
        {"name": "link", "selector": "td:first-child a@href"}
      ]
    }
  },
  "js_config": {
    "wait": {
      "type": "element",
      "value": "table",
      "timeout": 10
    },
    "actions": [
      {"type": "scroll", "max_scrolls": 3},
      {"type": "click", "selector": ".load-more"}
    ],
    "headless": true
  }
}
```

**Example:**
```bash
curl -X POST http://localhost:5000/extract-js \
  -H "Content-Type: application/json" \
  -d @request.json
```

---

### Multi-Page Crawling

**POST** `/crawl`

Crawl multiple pages following internal links.

**Request Body:**
```json
{
  "url": "https://example.com",
  "strategy": "generic",
  "config": {
    "max_depth": 2,
    "max_pages": 20,
    "delay": 1.0,
    "follow_links": true
  }
}
```

**Example:**
```bash
curl -X POST http://localhost:5000/crawl \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com/blog",
    "strategy": "article",
    "config": {
      "max_depth": 1,
      "max_pages": 10,
      "follow_links": true
    }
  }'
```

---

### Multi-Page Crawling with JavaScript

**POST** `/crawl-js`

Crawl multiple JavaScript-rendered pages.

**Request Body:**
```json
{
  "url": "https://example.com",
  "strategy": "selector",
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

### Page Structure Analysis

**POST** `/analyze`

Analyze a page's structure to help build custom extraction strategies.

**Request Body:**
```json
{
  "url": "https://example.com"
}
```

**Example:**
```bash
curl -X POST http://localhost:5000/analyze \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com/product"}'
```

**Response:**
```json
{
  "success": true,
  "url": "https://example.com/product",
  "analysis": {
    "metadata": {
      "title": "Product Name",
      "description": "...",
      "og_tags": {}
    },
    "structure": {
      "headings": [...],
      "main_container": {...},
      "semantic_tags": {}
    },
    "content_hints": {
      "price_indicators": [...],
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

**Extracts:**
- Title
- Headings (H1-H6)
- Paragraphs
- Images
- Meta tags

---

### 2. Product Strategy

Optimized for e-commerce product pages.

```json
{
  "strategy": "product"
}
```

**Extracts:**
- Product name
- Price
- Description
- Availability
- Images

---

### 3. Article Strategy

Optimized for blog posts and news articles.

```json
{
  "strategy": "article"
}
```

**Extracts:**
- Headline
- Author
- Publish date
- Content
- Tags

---

### 4. Selector Strategy

Custom CSS selector-based extraction with advanced features.

#### Simple Text Extraction
```json
{
  "strategy": "selector",
  "selectors": {
    "title": "h1.product-title",
    "price": ".price"
  }
}
```

#### Attribute Extraction
```json
{
  "strategy": "selector",
  "selectors": {
    "product_link": "a.product@href",
    "image": "img.product@src",
    "data_id": ".product@data-id"
  }
}
```

#### Advanced Configuration
```json
{
  "strategy": "selector",
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

#### Table/List Extraction
```json
{
  "strategy": "selector",
  "selectors": {
    "products": {
      "selector": "table.products tr",
      "extract": "table",
      "columns": [
        {"name": "name", "selector": "td:nth-child(1)", "extract": "text"},
        {"name": "url", "selector": "td:nth-child(1) a@href"},
        {"name": "price", "selector": "td:nth-child(2)", "extract": "text"}
      ]
    }
  }
}
```

---

## JavaScript Configuration

### Wait Strategies

#### Time-Based Wait
```json
{
  "wait": {
    "type": "time",
    "value": 3
  }
}
```

#### Wait for Element
```json
{
  "wait": {
    "type": "element",
    "value": ".product-list",
    "timeout": 10
  }
}
```

#### Wait for Script Condition
```json
{
  "wait": {
    "type": "script",
    "value": "return document.querySelectorAll('.item').length > 10",
    "timeout": 15
  }
}
```

#### Network Idle
```json
{
  "wait": {
    "type": "network_idle",
    "value": 2
  }
}
```

---

### Actions

#### Scroll to Bottom
```json
{
  "actions": [
    {
      "type": "scroll",
      "max_scrolls": 5,
      "pause_time": 1.5
    }
  ]
}
```

#### Click Element
```json
{
  "actions": [
    {
      "type": "click",
      "selector": ".load-more"
    }
  ]
}
```

#### Execute Custom JavaScript
```json
{
  "actions": [
    {
      "type": "script",
      "code": "document.querySelector('.modal').remove()"
    }
  ]
}
```

#### Wait Between Actions
```json
{
  "actions": [
    {"type": "click", "selector": ".button"},
    {"type": "wait", "seconds": 2},
    {"type": "scroll", "max_scrolls": 3}
  ]
}
```

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
      "original_price": ".price-original",
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

### Example 2: Job Listings from JS-Rendered Page

```bash
curl -X POST http://localhost:5000/extract-js \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://careers.example.com/jobs",
    "strategy": "selector",
    "selectors": {
      "jobs": {
        "selector": "div.job-list table tr",
        "extract": "table",
        "columns": [
          {"name": "title", "selector": "td:nth-child(1) a", "extract": "text"},
          {"name": "location", "selector": "td:nth-child(2)", "extract": "text"},
          {"name": "department", "selector": "td:nth-child(3)", "extract": "text"},
          {"name": "link", "selector": "td:nth-child(1) a@href"}
        ]
      }
    },
    "js_config": {
      "wait": {
        "type": "element",
        "value": "table",
        "timeout": 10
      },
      "headless": true
    }
  }'
```

---

### Example 3: Infinite Scroll Social Media Feed

```bash
curl -X POST http://localhost:5000/extract-js \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://social.example.com/feed",
    "strategy": "selector",
    "selectors": {
      "posts": {
        "selector": ".post",
        "extract": "text",
        "multiple": true
      }
    },
    "js_config": {
      "wait": {"type": "time", "value": 2},
      "actions": [
        {"type": "scroll", "max_scrolls": 10, "pause_time": 2}
      ],
      "headless": true
    }
  }'
```

---

### Example 4: Multi-Page Blog Crawl

```bash
curl -X POST http://localhost:5000/crawl \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://blog.example.com",
    "strategy": "article",
    "config": {
      "max_depth": 2,
      "max_pages": 50,
      "delay": 1.5,
      "follow_links": true
    }
  }'
```

---

## Troubleshooting

### Chrome Driver Issues

If you encounter Chrome driver issues:

```bash
# Update webdriver-manager
pip install --upgrade webdriver-manager

# Or manually specify Chrome binary location
export CHROME_BIN=/usr/bin/google-chrome
```

### Memory Issues with Large Crawls

Limit the number of pages and add delays:

```json
{
  "config": {
    "max_pages": 10,
    "delay": 2.0
  }
}
```

### Timeout Errors

Increase timeout values:

```json
{
  "config": {
    "timeout": 30
  },
  "js_config": {
    "wait": {
      "timeout": 20
    }
  }
}
```

---

## Performance Tips

1. **Use `/extract` for static pages** - Much faster than `/extract-js`
2. **Set appropriate delays** - Respect rate limits with `delay` config
3. **Limit crawl depth** - Use `max_depth` and `max_pages` to control scope
4. **Use specific selectors** - More specific = faster extraction
5. **Enable headless mode** - Always use `"headless": true` in production

---

## Security Considerations

- **Rate Limiting**: Implement rate limiting in production
- **URL Validation**: Validate and sanitize input URLs
- **Resource Limits**: Set max timeout and page limits
- **Authentication**: Add API key authentication for production use
- **CORS**: Configure CORS policies appropriately

---

## Contributing

Contributions are welcome! Please:

1. Test your changes thoroughly
2. Follow existing code style
3. Add documentation for new features
4. Submit pull requests with clear descriptions

---

## License

MIT License - feel free to use in your projects!

---

## Support

For issues, questions, or feature requests, please open an issue on the project repository.
