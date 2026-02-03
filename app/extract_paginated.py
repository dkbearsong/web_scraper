from flask import jsonify
from bs4 import BeautifulSoup
import requests
import time
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.support import expected_conditions as EC
from typing import Dict, Any
from app.javascript_renderer import JavaScriptRenderer
from app.extraction_strategies import StrategyFactory

class paginated:
    def _extract_url_pagination(self, data: Dict) -> Any:
        """Handle URL-based pagination (page numbers in URL)"""
        url_template = data['url_template']
        start_page = data.get('start_page', 1)
        end_page = data.get('end_page', 10)
        delay = data.get('delay', 1.0)
        
        # Check if JS rendering is needed
        use_js = 'js_config' in data
        js_config = data.get('js_config', {})
        
        # Create strategy
        strategy_type = data.get('strategy', 'generic')
        strategy = StrategyFactory.create(
            strategy_type,
            selectors=data.get('selectors', {})
        )
        
        all_results = []
        
        if use_js:
            # Use Selenium for JS-rendered pages
            headless = js_config.get('headless', True)
            wait_config = js_config.get('wait')
            actions = js_config.get('actions', [])
            
            with JavaScriptRenderer(headless=headless) as renderer:
                for page_num in range(start_page, end_page + 1):
                    try:
                        url = url_template.format(page=page_num)
                        
                        # Render page
                        html = renderer.render_page(url, wait_config)
                        
                        # Perform actions
                        for action in actions:
                            self._perform_action(renderer, action)
                        
                        # Get final HTML
                        html = renderer.driver.page_source
                        soup = BeautifulSoup(html, 'html.parser')
                        
                        # Extract data
                        page_data = strategy.extract(soup, url)
                        
                        all_results.append({
                            'page': page_num,
                            'url': url,
                            'data': page_data
                        })
                        
                        time.sleep(delay)
                        
                    except Exception as e:
                        all_results.append({
                            'page': page_num,
                            'url': url,
                            'error': str(e)
                        })
        else:
            # Use requests for static pages
            session = requests.Session()
            session.headers.update({'User-Agent': 'CustomCrawler/1.0'})
            
            try:
                for page_num in range(start_page, end_page + 1):
                    try:
                        url = url_template.format(page=page_num)
                        
                        response = session.get(url, timeout=10)
                        soup = BeautifulSoup(response.content, 'html.parser')
                        
                        # Extract data
                        page_data = strategy.extract(soup, url)
                        
                        all_results.append({
                            'page': page_num,
                            'url': url,
                            'status_code': response.status_code,
                            'data': page_data
                        })
                        
                        time.sleep(delay)
                        
                    except Exception as e:
                        all_results.append({
                            'page': page_num,
                            'url': url,
                            'error': str(e)
                        })
            finally:
                session.close()  # Properly close the session
        
        # Aggregate data from all pages
        aggregated_data = []
        for page in all_results:
            if 'data' in page:
                page_data = page['data']
                # Transform to list of dicts
                if isinstance(page_data, dict):
                    keys = list(page_data.keys())
                    if keys:
                        lengths = [len(v) if isinstance(v, list) else 1 for v in page_data.values()]
                        max_len = max(lengths) if lengths else 1
                        for k in keys:
                            if isinstance(page_data[k], list):
                                if len(page_data[k]) < max_len:
                                    page_data[k].extend([None] * (max_len - len(page_data[k])))
                            else:
                                page_data[k] = [page_data[k]] * max_len
                        page_list = [dict(zip(keys, vals)) for vals in zip(*[page_data[k] for k in keys])]
                    else:
                        page_list = []
                elif isinstance(page_data, list):
                    page_list = page_data
                else:
                    page_list = [page_data] if page_data else []
                aggregated_data.extend(page_list)
        
        return jsonify({
            'status_code': 200,
            'success': True,
            'data': aggregated_data,
            'total_pages': len(all_results)
        })
        
    def _extract_click_pagination(self, data: Dict) -> Any:
        """Handle click-based pagination (clicking Next button)"""
        url = data['url']
        pagination_config = data['pagination']
        
        next_selector = pagination_config.get('next_selector')
        max_pages = pagination_config.get('max_pages', 10)
        wait_after_click = pagination_config.get('wait_after_click', 2)
        use_js_click = pagination_config.get('use_js', True)  # Default to JS click for pagination
        
        js_config = data.get('js_config', {})
        headless = js_config.get('headless', True)
        wait_config = js_config.get('wait')
        initial_actions = js_config.get('actions', [])
        
        # Extract job/item selector from config for content change detection
        selectors_config = data.get('selectors', {})
        job_selector = None
        # Try to find the main item selector (usually the first key in selectors)
        if selectors_config:
            # Look for common keys like 'jobs', 'items', 'results', etc.
            for key in ['jobs', 'items', 'results', 'listings', 'products']:
                if key in selectors_config:
                    job_config = selectors_config[key]
                    if isinstance(job_config, dict) and 'selector' in job_config:
                        job_selector = job_config['selector']
                        break
            # If not found, use the first selector's selector
            if not job_selector and selectors_config:
                first_key = list(selectors_config.keys())[0]
                first_config = selectors_config[first_key]
                if isinstance(first_config, dict) and 'selector' in first_config:
                    job_selector = first_config['selector']
        
        # Create strategy
        strategy_type = data.get('strategy', 'generic')
        strategy = StrategyFactory.create(
            strategy_type,
            selectors=selectors_config
        )
        
        all_results = []
        
        with JavaScriptRenderer(headless=headless) as renderer:
            # Load initial page
            html = renderer.render_page(url, wait_config)
            
            # Perform initial actions
            for action in initial_actions:
                self._perform_action(renderer, action)
            
            # Extract from each page
            for page_num in range(1, max_pages + 1):
                try:
                    # Wait a bit for page to stabilize
                    time.sleep(1)

                    # Get a unique identifier from the current page using the actual job selector
                    # This helps us detect when content actually changes
                    old_content_marker = None
                    try:
                        if job_selector:
                            # Use the actual job selector from config
                            escaped_selector = job_selector.replace("'", "\\'")
                            old_content_marker = renderer.driver.execute_script(
                                f"const containers = document.querySelectorAll('{escaped_selector}'); "
                                "if (containers.length > 0) { "
                                "  return Array.from(containers).slice(0, 3).map(c => c.textContent.trim().substring(0, 100)).join('|'); "
                                "} "
                                "return document.body.innerText.substring(0, 300);"
                            )
                        else:
                            # Fallback to body text
                            old_content_marker = renderer.driver.execute_script(
                                "return document.body.innerText.substring(0, 300);"
                            )
                    except Exception as e:
                        print(f"Warning: Could not get content marker: {e}")
                        old_content_marker = renderer.driver.execute_script("return document.body.innerText.substring(0, 300);")
                    
                    # Get current page HTML
                    html = renderer.driver.page_source
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    # Extract data
                    page_data = strategy.extract(soup, renderer.driver.current_url)
                    
                    # Count items extracted for logging
                    item_count = 0
                    if isinstance(page_data, dict):
                        # For table extraction, count items in the first list value
                        for key, value in page_data.items():
                            if isinstance(value, list):
                                item_count = len(value)
                                break
                    elif isinstance(page_data, list):
                        item_count = len(page_data)
                    
                    all_results.append({
                        'page': page_num,
                        'url': renderer.driver.current_url,
                        'data': page_data
                    })
                
                    print(f"Extracted page {page_num}, found {item_count} items")
                
                    # Try to click next button
                    if page_num < max_pages:
                        try:
                            # Scroll to bottom first to ensure pagination is visible
                            renderer.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                            time.sleep(0.5)
                            
                            # Find the element
                            element = WebDriverWait(renderer.driver, 5).until(
                                EC.presence_of_element_located((By.CSS_SELECTOR, next_selector))
                            )
                            
                            # Check if button is disabled (no more pages)
                            element_class = element.get_attribute('class') or ''
                            parent_class = ''
                            try:
                                parent = element.find_element(By.XPATH, '..')
                                parent_class = parent.get_attribute('class') or ''
                            except:
                                pass
                            
                            is_disabled = (element.get_attribute('disabled') or 
                                        'is-disabled' in element_class or 
                                        'disabled' in element_class or
                                        'is-disabled' in parent_class or
                                        element.get_attribute('aria-disabled') == 'true')
                            if is_disabled:
                                print(f"Next button is disabled on page {page_num}, stopping")
                                break
                            
                            # Scroll element into center of viewport
                            renderer.driver.execute_script(
                                "arguments[0].scrollIntoView({behavior: 'instant', block: 'center', inline: 'center'});", 
                                element
                            )
                            time.sleep(0.5)
                            
                            # Try to dismiss any overlays
                            renderer._dismiss_common_overlays()
                            
                            print(f"Clicking next button for page {page_num + 1}...")
                            
                            # Use JavaScript click (more reliable for pagination)
                            if use_js_click:
                                renderer.driver.execute_script("arguments[0].click();", element)
                            else:
                                # Try regular click with fallback
                                try:
                                    element = WebDriverWait(renderer.driver, 3).until(
                                        EC.element_to_be_clickable((By.CSS_SELECTOR, next_selector))
                                    )
                                    element.click()
                                except Exception:
                                    # Fall back to JS click
                                    element = renderer.driver.find_element(By.CSS_SELECTOR, next_selector)
                                    renderer.driver.execute_script("arguments[0].click();", element)
                            
                            # Initial wait for navigation
                            time.sleep(wait_after_click)
                            
                            # Wait for job listings to appear if we have a job selector
                            if job_selector:
                                try:
                                    WebDriverWait(renderer.driver, 10).until(
                                        EC.presence_of_element_located((By.CSS_SELECTOR, job_selector))
                                    )
                                    print(f"Job listings appeared after click")
                                except TimeoutException:
                                    print(f"Warning: Job listings did not appear within timeout, continuing anyway")
                            
                            # Verify content actually changed
                            content_changed = False
                            max_retries = 15  # Increased retries for slower loading
                            for retry in range(max_retries):
                                try:
                                    if job_selector:
                                        # Use the actual job selector from config
                                        escaped_selector = job_selector.replace("'", "\\'")
                                        new_content_marker = renderer.driver.execute_script(
                                            f"const containers = document.querySelectorAll('{escaped_selector}'); "
                                            "if (containers.length > 0) { "
                                            "  return Array.from(containers).slice(0, 3).map(c => c.textContent.trim().substring(0, 100)).join('|'); "
                                            "} "
                                            "return document.body.innerText.substring(0, 300);"
                                        )
                                    else:
                                        new_content_marker = renderer.driver.execute_script(
                                            "return document.body.innerText.substring(0, 300);"
                                        )
                                    
                                    if new_content_marker != old_content_marker and new_content_marker:
                                        # Content changed, we're on a new page
                                        print(f"Content changed after {retry + 1} checks, moving to page {page_num + 1}")
                                        content_changed = True
                                        break
                                    else:
                                        # Content hasn't changed yet, wait a bit more
                                        time.sleep(0.5)
                                except Exception as e:
                                    print(f"Error checking content change (retry {retry + 1}): {e}")
                                    time.sleep(0.5)
                            
                            if not content_changed:
                                print(f"Warning: Content didn't change after clicking next on page {page_num}, stopping")
                                print(f"Old marker: {old_content_marker[:100] if old_content_marker else 'None'}...")
                                print(f"New marker: {new_content_marker[:100] if 'new_content_marker' in locals() and new_content_marker else 'None'}...")
                                break
                            
                        except (TimeoutException, NoSuchElementException) as e:
                            # No more pages
                            print(f"No next button found on page {page_num}: {e}")
                            break
                        except Exception as e:
                            print(f"Error clicking next button on page {page_num}: {e}")
                            import traceback
                            traceback.print_exc()
                            break
                            
                except Exception as e:
                    print(f"Error on page {page_num}: {e}")
                    import traceback
                    traceback.print_exc()
                    all_results.append({
                        'page': page_num,
                        'error': str(e)
                    })
                    # Don't break on extraction errors, continue to next page
                    if page_num < max_pages:
                        continue
                    else:
                        break
        
        # Aggregate data from all pages
        aggregated_data = []
        for page in all_results:
            if 'data' in page:
                page_data = page['data']
                # Transform to list of dicts
                if isinstance(page_data, dict):
                    keys = list(page_data.keys())
                    if keys:
                        lengths = [len(v) if isinstance(v, list) else 1 for v in page_data.values()]
                        max_len = max(lengths) if lengths else 1
                        for k in keys:
                            if isinstance(page_data[k], list):
                                if len(page_data[k]) < max_len:
                                    page_data[k].extend([None] * (max_len - len(page_data[k])))
                            else:
                                page_data[k] = [page_data[k]] * max_len
                        page_list = [dict(zip(keys, vals)) for vals in zip(*[page_data[k] for k in keys])]
                    else:
                        page_list = []
                elif isinstance(page_data, list):
                    page_list = page_data
                else:
                    page_list = [page_data] if page_data else []
                aggregated_data.extend(page_list)
        
        return jsonify({
            'status_code': 200,
            'success': True,
            'data': aggregated_data,
            'total_pages': len(all_results)
        })

    def _perform_action(self, renderer: JavaScriptRenderer, action: Dict):
        """Helper to perform a single action"""
        action_type = action.get('type')
        
        if action_type == 'click':
            use_js = action.get('use_js', False)
            dismiss_overlays = action.get('dismiss_overlays', True)
            renderer.click_element(action.get('selector'), use_js, dismiss_overlays)
        elif action_type == 'scroll':
            renderer.scroll_to_bottom(
                action.get('pause_time', 1.0),
                action.get('max_scrolls', 10)
            )
        elif action_type == 'click_until_gone':
            selector = action.get('selector')
            if selector:
                use_js = action.get('use_js', False)
                dismiss_overlays = action.get('dismiss_overlays', True)
                renderer.click_until_gone(
                    selector,
                    action.get('max_clicks', 10),
                    action.get('pause_time', 1.0),
                    use_js,
                    dismiss_overlays
                )
        elif action_type == 'load_all':
            renderer.load_all_content(
                action.get('method', 'scroll'),
                action.get('selector'),
                action.get('max_iterations', 10),
                action.get('pause_time', 1.0)
            )
        elif action_type == 'wait_for_element':
            # NEW: Wait for element to appear
            selector = action.get('selector')
            timeout = action.get('timeout', 10)
            if selector:
                try:
                    WebDriverWait(renderer.driver, timeout).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                except TimeoutException:
                    print(f"Timeout waiting for element: {selector}")
        elif action_type == 'wait_for_gone':
            # NEW: Wait for element to disappear
            selector = action.get('selector')
            timeout = action.get('timeout', 10)
            if selector:
                try:
                    WebDriverWait(renderer.driver, timeout).until_not(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                except TimeoutException:
                    print(f"Timeout waiting for element to disappear: {selector}")
        elif action_type == 'wait_for_attribute':
            # NEW: Wait for element attribute to have specific value
            selector = action.get('selector')
            attribute = action.get('attribute')
            value = action.get('value')
            timeout = action.get('timeout', 10)
            
            if selector and attribute:
                try:
                    if value is not None:
                        # Wait for attribute to equal specific value
                        WebDriverWait(renderer.driver, timeout).until(
                            lambda d: d.find_element(By.CSS_SELECTOR, selector).get_attribute(attribute) == str(value)
                        )
                    else:
                        # Wait for attribute to exist (any value)
                        WebDriverWait(renderer.driver, timeout).until(
                            lambda d: d.find_element(By.CSS_SELECTOR, selector).get_attribute(attribute) is not None
                        )
                    print(f"Element {selector} attribute {attribute} = {value}")
                except TimeoutException:
                    print(f"Timeout waiting for {selector} attribute {attribute} to be {value}")
                except Exception as e:
                    print(f"Error waiting for attribute: {e}")
        elif action_type == 'wait_for_class':
            # NEW: Wait for element to have/not have specific class
            selector = action.get('selector')
            class_name = action.get('class_name')
            should_have = action.get('should_have', True)
            timeout = action.get('timeout', 10)
            
            if selector and class_name:
                try:
                    if should_have:
                        # Wait for class to be added
                        WebDriverWait(renderer.driver, timeout).until(
                            lambda d: class_name in (d.find_element(By.CSS_SELECTOR, selector).get_attribute('class') or '')
                        )
                        print(f"Element {selector} has class {class_name}")
                    else:
                        # Wait for class to be removed
                        WebDriverWait(renderer.driver, timeout).until(
                            lambda d: class_name not in (d.find_element(By.CSS_SELECTOR, selector).get_attribute('class') or '')
                        )
                        print(f"Element {selector} no longer has class {class_name}")
                except TimeoutException:
                    print(f"Timeout waiting for class {class_name} on {selector}")
                except Exception as e:
                    print(f"Error waiting for class: {e}")
        elif action_type == 'script':
            script = action.get('code')
            if script:
                renderer.execute_script(script)
        elif action_type == 'wait':
            time.sleep(action.get('seconds', 1))
