from typing import Dict, Any, Optional
import time

# Selenium imports
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# ==================== JavaScript Renderer ====================

class JavaScriptRenderer:
    """Handles rendering of JavaScript-heavy pages using Selenium"""
    
    def __init__(self, headless: bool = True, wait_time: int = 10):
        self.headless = headless
        self.wait_time = wait_time
        self.driver = None
    
    def __enter__(self):
        """Context manager entry - initialize driver"""
        self.driver = self._create_driver()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - cleanup driver"""
        if self.driver:
            self.driver.quit()
    
    def _create_driver(self):
        """Create and configure Chrome WebDriver"""
        chrome_options = Options()
        
        if self.headless:
            chrome_options.add_argument('--headless')
        
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        
        # Install and setup ChromeDriver automatically
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.set_page_load_timeout(30)
        
        return driver
    
    def render_page(self, url: str, wait_config: Optional[Dict] = None, iframe_selector: Optional[str] = None) -> str:
        """
        Render a page and return HTML after JavaScript execution
        
        Args:
            url: URL to render
            wait_config: Optional wait configuration
                {
                    "type": "time|element|script",
                    "value": 5 or "css_selector" or "return document.readyState === 'complete'",
                    "timeout": 10
                }
            iframe_selector: Optional CSS selector for iframe to switch into
        """
        if not self.driver:
            raise RuntimeError("Driver not initialized. Use context manager.")
        
        self.driver.get(url)
        
        # Handle different wait strategies
        if wait_config:
            self._wait_for_content(wait_config)
        else:
            # Default: wait for page load
            time.sleep(2)
        
        # Switch to iframe if specified
        if iframe_selector:
            try:
                iframe = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, iframe_selector))
                )
                self.driver.switch_to.frame(iframe)
                time.sleep(1)  # Wait for iframe content to load
            except TimeoutException:
                print(f"Could not find iframe with selector: {iframe_selector}")
        
        # Return rendered HTML
        return self.driver.page_source
    
    def _wait_for_content(self, wait_config: Dict):
        """Wait for content based on configuration"""
        if not self.driver:
            raise RuntimeError("Driver not initialized")
        
        wait_type = wait_config.get('type', 'time')
        timeout = wait_config.get('timeout', self.wait_time)
        
        if wait_type == 'time':
            # Simple time-based wait
            wait_seconds = wait_config.get('value', 2)
            time.sleep(wait_seconds)
        
        elif wait_type == 'element':
            # Wait for specific element to appear
            selector = wait_config.get('value')
            if selector:
                try:
                    WebDriverWait(self.driver, timeout).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                except TimeoutException:
                    print(f"Timeout waiting for element: {selector}")
        
        elif wait_type == 'script':
            # Wait for custom JavaScript condition
            script = wait_config.get('value')
            if script:
                try:
                    WebDriverWait(self.driver, timeout).until(
                        lambda d: d.execute_script(script)
                    )
                except TimeoutException:
                    print(f"Timeout waiting for script condition")
        
        elif wait_type == 'network_idle':
            # Wait for network to be idle (no pending requests)
            time.sleep(wait_config.get('value', 1))
    
    def execute_script(self, script: str) -> Any:
        """Execute custom JavaScript and return result"""
        if not self.driver:
            raise RuntimeError("Driver not initialized")
        return self.driver.execute_script(script)
    
    def _dismiss_common_overlays(self):
        """Attempt to dismiss common overlay elements that might intercept clicks"""
        overlay_dismissal_scripts = [
            # Remove common overlay classes
            "document.querySelectorAll('.modal-backdrop, .overlay, .popup-overlay').forEach(el => el.remove());",
            # Close modals
            "document.querySelectorAll('.modal.show, .modal.open').forEach(el => el.classList.remove('show', 'open'));",
            # Remove fixed position overlays
            "document.querySelectorAll('[style*=\"position: fixed\"]').forEach(el => { if(el.style.zIndex > 100) el.remove(); });",
            # Hide body overflow (often set when modals open)
            "document.body.style.overflow = 'auto';",
        ]
        
        for script in overlay_dismissal_scripts:
            try:
                self.driver.execute_script(script)
            except:
                pass

    def click_element(self, selector: str, use_js: bool = False, dismiss_overlays: bool = True):
        """
        Click an element (useful for load more buttons, etc.)
        
        Args:
            selector: CSS selector for element to click
            use_js: If True, use JavaScript click instead of Selenium click
            dismiss_overlays: If True, try to remove common overlays before clicking
        """
        if not self.driver:
            raise RuntimeError("Driver not initialized")
        
        try:
            # Optionally dismiss common overlays
            if dismiss_overlays:
                self._dismiss_common_overlays()
            
            element = WebDriverWait(self.driver, self.wait_time).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, selector))
            )
            
            # Scroll element into view
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
            time.sleep(0.5)
            
            if use_js:
                # JavaScript click (works when element is intercepted)
                self.driver.execute_script("arguments[0].click();", element)
            else:
                # Try regular click first
                try:
                    element = WebDriverWait(self.driver, 5).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                    )
                    element.click()
                except Exception as e:
                    # Fall back to JavaScript click if intercepted
                    print(f"Regular click failed, using JS click: {e}")
                    self.driver.execute_script("arguments[0].click();", element)
            
            time.sleep(1)
            
        except (TimeoutException, NoSuchElementException) as e:
            print(f"Could not click element {selector}: {e}")
            try:
                element = WebDriverWait(self.driver, self.wait_time).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                )
                element.click()
                time.sleep(1)  # Wait for content to load after click
            except (TimeoutException, NoSuchElementException) as e:
                print(f"Could not click element {selector}: {e}")
    
    def scroll_to_bottom(self, pause_time: float = 1.0, max_scrolls: int = 10):
        """Scroll to bottom of page (useful for infinite scroll)"""
        if not self.driver:
            raise RuntimeError("Driver not initialized")
        
        last_height = self.driver.execute_script("return document.body.scrollHeight")
        scrolls = 0
        
        while scrolls < max_scrolls:
            # Scroll down
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(pause_time)
            
            # Calculate new scroll height
            new_height = self.driver.execute_script("return document.body.scrollHeight")
            
            if new_height == last_height:
                break
            
            last_height = new_height
            scrolls += 1

    def click_until_gone(
            self, selector: str,
            max_clicks: int = 10,
            pause_time: float = 1.0,
            use_js: bool = False,
            dismiss_overlays: bool = True
        ):
        """
        Repeatedly click an element until it's no longer available
        Useful for "Load More" buttons that disappear when all content is loaded
        
        Args:
            selector: CSS selector for the element to click
            max_clicks: Maximum number of times to click
            pause_time: Time to wait between clicks
        
        Returns:
            Number of successful clicks
        """
        if not self.driver:
            raise RuntimeError("Driver not initialized")
        
        clicks = 0
        
        for _ in range(max_clicks):
            try:
                # Check if element exists and is clickable
                element = WebDriverWait(self.driver, 2).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                )
                
                # Scroll element into view
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                time.sleep(0.5)
                
                # Click the element
                element.click()
                clicks += 1
                
                # Wait for content to load
                time.sleep(pause_time)
                
            except (TimeoutException, NoSuchElementException):
                # Element not found or not clickable anymore - we're done
                break
            except Exception as e:
                print(f"Error clicking element: {e}")
                break
        
        return clicks

    def load_all_content(self, method: str = "scroll", selector: Optional[str] = None, 
                        max_iterations: int = 10, pause_time: float = 1.0):
        """
        Load all content on a page using various methods
        
        Args:
            method: "scroll" for infinite scroll, "click" for load more buttons
            selector: CSS selector for load more button (required if method="click")
            max_iterations: Maximum number of scrolls/clicks
            pause_time: Time to wait between iterations
        
        Returns:
            Number of iterations performed
        """
        if method == "scroll":
            self.scroll_to_bottom(pause_time, max_iterations)
            return max_iterations
        elif method == "click" and selector:
            return self.click_until_gone(selector, max_iterations, pause_time)
        else:
            raise ValueError("Invalid method or missing selector for click method")