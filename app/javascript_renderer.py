from typing import Dict, Any, Optional
import time
import logging
import os

# Selenium imports
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# Encryption support for Chrome cookies
try:
    import keyring
    HAS_KEYRING = True
except ImportError:
    HAS_KEYRING = False

try:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.backends import default_backend
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False

# Setup logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# ==================== JavaScript Renderer ====================

class JavaScriptRenderer:
    """Handles rendering of JavaScript-heavy pages using Selenium
    
    To enable reuse of existing Chrome cookies (for sites requiring authentication)
    the renderer can be pointed at a local Chrome user data directory and profile
    directory.  When provided the browser will open with the same state as the
    regular desktop instance so the stored cookies and logged‑in sessions will
    be available.  On Linux the default path is usually ``~/.config/google-chrome``
    and the profile directory is ``Default`` or ``Profile X``.
    """
    
    def __init__(
        self,
        headless: bool = True,
        wait_time: int = 10,
        user_data_dir: Optional[str] = None,
        profile: Optional[str] = None,
    ):
        self.headless = headless
        self.wait_time = wait_time
        self.user_data_dir = os.path.expanduser(user_data_dir) if user_data_dir else None
        self.profile = profile
        self.driver = None
        self._profile_cookies = None  # Cache cookies extracted from profile
    
    def __enter__(self):
        """Context manager entry - initialize driver and extract cookies"""
        self.driver = self._create_driver()
        # Extract and cache cookies from profile (for later injection)
        if self.user_data_dir and self.profile:
            logger.debug("Extracting cookies from Chrome profile for caching...")
            self._profile_cookies = self._extract_cookies_from_profile()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - cleanup driver"""
        if self.driver:
            try:
                self.driver.quit()
                logger.debug("Driver closed cleanly")
            except Exception as e:
                logger.warning(f"Error closing driver gracefully: {e}. Force closing...")
                try:
                    # Force kill the Chrome process if graceful shutdown fails
                    import subprocess
                    subprocess.run(['pkill', '-9', '-f', 'chromedriver|chrome'], 
                                 capture_output=True, timeout=5)
                    logger.debug("Force closed Chrome processes")
                except Exception as force_close_error:
                    logger.warning(f"Could not force close Chrome: {force_close_error}")

    
    def _extract_cookies_from_profile(self) -> list:
        """Extract cookies from Chrome profile database"""
        import sqlite3
        import shutil
        import tempfile
        
        if not self.user_data_dir or not self.profile:
            logger.debug("No profile specified, skipping cookie extraction")
            return []
        
        try:
            profile_path = os.path.expanduser(self.user_data_dir)
            cookies_db = os.path.join(profile_path, self.profile, "Cookies")
            
            if not os.path.exists(cookies_db):
                logger.warning(f"Cookies database not found at {cookies_db}")
                return []
            
            logger.debug(f"Starting cookie extraction from {cookies_db}...")
            
            # Chrome locks the cookies database, so we need to copy it first
            temp_db = None
            try:
                temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
                temp_db.close()
                logger.debug(f"Copying cookies database to temp file...")
                shutil.copy2(cookies_db, temp_db.name)
                logger.debug(f"Successfully copied, now parsing...")
                
                # Connect to the temporary copy with timeout
                conn = sqlite3.connect(temp_db.name, timeout=5.0)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                # First, inspect the schema
                cursor.execute("PRAGMA table_info(cookies)")
                columns = [col[1] for col in cursor.fetchall()]
                logger.info(f"Cookies table columns available: {columns}")
                
                # Extract all cookies with full row data
                cursor.execute("SELECT * FROM cookies LIMIT 10000")
                all_cols = [description[0] for description in cursor.description]
                logger.debug(f"Query columns: {all_cols}")
                
                cookies = []
                total_rows = 0
                empty_value_count = 0
                encrypted_value_count = 0
                used_count = 0
                
                for row in cursor.fetchall():
                    total_rows += 1
                    try:
                        row_dict = dict(row)
                        host_key = row_dict.get('host_key', '')
                        name = row_dict.get('name', '')
                        value = row_dict.get('value', '')
                        encrypted_value = row_dict.get('encrypted_value', b'')
                        path = row_dict.get('path', '/')
                        
                        # Log each cookie for debugging
                        has_value = bool(value and len(value) > 0)
                        has_encrypted = bool(encrypted_value and len(encrypted_value) > 0)
                        
                        if not has_value:
                            empty_value_count += 1
                        if has_encrypted:
                            encrypted_value_count += 1
                        
                        if total_rows <= 10 or (has_value and 'linkedin' in host_key.lower()):
                            logger.debug(f"Row {total_rows}: {name}@{host_key} value_len={len(value)}, encrypted_len={len(encrypted_value)}")
                        
                        # Skip cookies without unencrypted values
                        if not has_value:
                            continue
                        
                        # Convert to Selenium cookie format
                        if host_key.startswith('.'):
                            domain = host_key[1:]
                        else:
                            domain = host_key
                        
                        cookie = {
                            'name': name,
                            'value': value,
                            'domain': domain,
                            'path': path,
                        }
                        
                        # Add optional flags if available
                        if 'secure' in row_dict:
                            try:
                                cookie['secure'] = bool(row_dict['secure'])
                            except:
                                pass
                        if 'httponly' in row_dict:
                            try:
                                cookie['httpOnly'] = bool(row_dict['httponly'])
                            except:
                                pass
                        
                        cookies.append(cookie)
                        used_count += 1
                        
                    except Exception as e:
                        logger.debug(f"Could not parse cookie row {total_rows}: {e}")
                        continue
                
                conn.close()
                
                logger.info(f"Cookies database analysis: {total_rows} total rows")
                logger.info(f"  - {empty_value_count} rows with empty value column")
                logger.info(f"  - {encrypted_value_count} rows with encrypted_value (encrypted cookies)")
                logger.info(f"  - {used_count} usable cookies extracted")
                
                if cookies:
                    domains = set(c.get('domain', 'N/A') for c in cookies)
                    logger.info(f"✓ Cookie domains found: {domains}")
                    linkedin_cookies = [c for c in cookies if 'linkedin' in c.get('domain', '').lower()]
                    logger.info(f"✓ LinkedIn cookies: {len(linkedin_cookies)} found - {[c.get('name') for c in linkedin_cookies]}")
                else:
                    logger.warning("⚠ No unencrypted cookies found in database!")
                    logger.warning("  LinkedIn cookies in your Chrome profile may be encrypted.")
                    logger.warning("  This is normal - only unencrypted cookies can be transferred to Selenium.")
                
                return cookies
                
            finally:
                if temp_db and os.path.exists(temp_db.name):
                    try:
                        os.unlink(temp_db.name)
                    except:
                        pass
                        
        except sqlite3.DatabaseError as e:
            logger.warning(f"Could not read Chrome cookies database (may be locked): {e}")
            return []
        except Exception as e:
            logger.warning(f"Could not extract cookies from profile: {type(e).__name__}: {e}")
            import traceback
            logger.debug(f"Traceback: {traceback.format_exc()}")
            return []
    
    def _create_driver(self):
        """
        Create and configure Chrome WebDriver.
        
        IMPORTANT ARCHITECTURE DECISION:
        - Headless mode (recommended): Works reliably with any website, no authentication
        - Non-headless mode: Can be used for debugging but chromium profile support is unreliable
        
        Chrome cookies are encrypted at OS level. While Chrome can decrypt them in non-headless mode,
        using --user-data-dir with Selenium causes Chrome to hang on initialization (DevToolsActivePort error).
        
        Solution: Use headless mode for automated scraping. For authenticated sessions, consider:
        1. Manual login + cookie export before automation
        2. Alternative tools (Puppeteer, Playwright, Scrapy)
        3. API-based scraping instead of browser automation
        """
        import subprocess
        import time as time_module
        
        logger.debug(f"Creating driver: headless={self.headless}, profile={self.profile}")
        
        # Kill any stale Chrome processes
        try:
            subprocess.run(['killall', '-9', 'chrome'], capture_output=True, timeout=2)
        except:
            pass
        time_module.sleep(1)
        
        # Determine if we'll use profile (only for non-headless debugging)
        display_available = os.environ.get('DISPLAY')
        use_profile = False
        
        if self.user_data_dir and self.profile and not self.headless and display_available:
            profile_dir = os.path.expanduser(os.path.join(self.user_data_dir, self.profile))
            if os.path.isdir(profile_dir):
                use_profile = True
                logger.warning(f"⚠ Using profile: {profile_dir}")
                logger.warning("   Note: Chrome may hang on startup. For reliable automation, use headless=true")
        
        # Build Chrome options
        options = Options()
        
        if use_profile:
            # Profile-based launch (NOT RECOMMENDED - unreliable)
            options.add_argument(f"--user-data-dir={os.path.expanduser(self.user_data_dir)}")
            options.add_argument(f"--profile-directory={self.profile}")
            options.add_argument("--disable-sync")
            options.add_argument("--no-first-run")
            options.add_argument("--disable-extensions")
            logger.debug("Profile mode - warning: may timeout")
        else:
            # Fresh Chrome instance (RECOMMENDED)
            if self.headless:
                options.add_argument("--headless=new")  # Modern headless mode
                logger.debug("Headless mode (RECOMMENDED)")
            else:
                logger.warning("Non-headless without profile - browser will open")
        
        # Essential arguments
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1280,720")
        
        # Bypass WebDriver detection (some sites check for this)
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
        
        service = Service(ChromeDriverManager().install())
        
        # Try to create driver (with timeout protection)
        for attempt in range(3):
            try:
                logger.debug(f"Driver creation attempt {attempt + 1}/3...")
                driver = webdriver.Chrome(service=service, options=options)
                driver.set_page_load_timeout(30)
                driver.set_script_timeout(30)
                logger.info("✓ Chrome driver created successfully")
                return driver
            except Exception as e:
                err_msg = str(e)[:80]
                logger.warning(f"Attempt {attempt + 1} failed: {err_msg}")
                if attempt < 2:
                    time_module.sleep(2)
                    try:
                        subprocess.run(['killall', '-9', 'chrome'], capture_output=True, timeout=1)
                    except:
                        pass
        
        raise RuntimeError("Failed to create Chrome driver")
    
    def __enter__(self):
        """Context manager entry - initialize driver and extract cookies"""
        self.driver = self._create_driver()
        # Extract and cache cookies from profile (for later injection)
        if self.user_data_dir and self.profile:
            logger.debug("Extracting cookies from Chrome profile for caching...")
            self._profile_cookies = self._extract_cookies_from_profile()
        return self
    
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
        
        try:
            logger.info(f"[render_page] Starting - Loading URL: {url}")
            logger.debug(f"[render_page] Driver session: {self.driver.session_id}")
            logger.debug(f"[render_page] Current URL before navigation: {self.driver.current_url}")
            
            # Navigate to URL with logging
            logger.debug(f"[render_page] Calling driver.get('{url}')...")
            start_time = time.time()
            self.driver.get(url)
            nav_time = time.time() - start_time
            logger.info(f"[render_page] ✓ Navigation completed in {nav_time:.2f}s")
            logger.debug(f"[render_page] Current URL after navigation: {self.driver.current_url}")
            
            # Check page title
            try:
                title = self.driver.title
                logger.debug(f"[render_page] Page title: '{title}'")
            except Exception as e:
                logger.warning(f"[render_page] Could not get page title: {e}")
            
            # Log cookies (for authentication debugging)
            try:
                cookies = self.driver.get_cookies()
                logger.debug(f"[render_page] Found {len(cookies)} cookies on page")
                if cookies:
                    domains = set(c.get('domain', 'N/A') for c in cookies)
                    logger.debug(f"  Cookie domains: {domains}")
                    linkedin_cookies = [c for c in cookies if 'linkedin' in c.get('domain', '').lower()]
                    if linkedin_cookies:
                        logger.info(f"  ✓ LinkedIn cookies found: {[c.get('name') for c in linkedin_cookies[:5]]}")
            except Exception as e:
                logger.debug(f"  Could not check cookies: {e}")
            
            # Handle different wait strategies
            if wait_config:
                logger.debug(f"[render_page] Waiting for content with config: {wait_config}")
                self._wait_for_content(wait_config)
                logger.debug(f"[render_page] ✓ Wait completed")
            else:
                # Default: wait for page load
                logger.debug("[render_page] Using default 2-second wait")
                time.sleep(2)
                logger.debug("[render_page] ✓ Default wait completed")
            
            # Switch to iframe if specified
            if iframe_selector:
                logger.debug(f"[render_page] Looking for iframe with selector: {iframe_selector}")
                try:
                    iframe = WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, iframe_selector))
                    )
                    self.driver.switch_to.frame(iframe)
                    logger.debug(f"[render_page] ✓ Successfully switched to iframe")
                    time.sleep(1)  # Wait for iframe content to load
                except TimeoutException:
                    logger.warning(f"[render_page] Could not find iframe with selector: {iframe_selector}")
            
            # Return rendered HTML
            html_length = len(self.driver.page_source)
            logger.info(f"[render_page] ✓ Page render successful ({html_length} bytes)")
            return self.driver.page_source
            
        except TimeoutException as e:
            logger.error(f"[render_page] ✗ Timeout: {e}")
            # Try to return partial page anyway
            try:
                partial = self.driver.page_source
                logger.warning(f"[render_page] Returning partial page ({len(partial)} bytes)")
                return partial
            except:
                raise
        except Exception as e:
            logger.error(f"[render_page] ✗ Error: {e}", exc_info=True)
            raise
    
    def _wait_for_content(self, wait_config: Dict):
        """Wait for content based on configuration"""
        wait_type = wait_config.get('type', 'time')
        timeout = wait_config.get('timeout', self.wait_time)
        logger.debug(f"_wait_for_content() - Waiting with type={wait_type}, timeout={timeout}")
        
        if wait_type == 'time':
            # Simple time-based wait
            wait_seconds = wait_config.get('value', 2)
            logger.debug(f"_wait_for_content() - Time-based wait for {wait_seconds} seconds")
            time.sleep(wait_seconds)
        
        elif wait_type == 'element':
            # Wait for specific element to appear
            selector = wait_config.get('value')
            if selector:
                logger.debug(f"_wait_for_content() - Waiting for element: {selector}")
                try:
                    WebDriverWait(self.driver, timeout).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    logger.debug(f"_wait_for_content() - Element found: {selector}")
                except TimeoutException:
                    logger.warning(f"_wait_for_content() - Timeout waiting for element: {selector}")
        
        elif wait_type == 'element_gone':
            # NEW: Wait for element to disappear
            selector = wait_config.get('value')
            if selector:
                try:
                    WebDriverWait(self.driver, timeout).until_not(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                except TimeoutException:
                    print(f"Timeout waiting for element to disappear: {selector}")
        
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
        
        logger.debug(f"click_element() - Attempting to click: {selector}")
        try:
            # Optionally dismiss common overlays
            if dismiss_overlays:
                logger.debug(f"click_element() - Dismissing common overlays")
                self._dismiss_common_overlays()
            
            element = WebDriverWait(self.driver, self.wait_time).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, selector))
            )
            logger.debug(f"click_element() - Element found, text: {element.text[:50] if element.text else 'N/A'}")
            
            # Scroll element into view
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
            logger.debug(f"click_element() - Scrolled element into view")
            time.sleep(0.5)
            
            if use_js:
                # JavaScript click (works when element is intercepted)
                logger.debug(f"click_element() - Using JavaScript click")
                self.driver.execute_script("arguments[0].click();", element)
            else:
                # Try regular click first
                try:
                    element = WebDriverWait(self.driver, 5).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                    )
                    logger.debug(f"click_element() - Using Selenium click")
                    element.click()
                except Exception as e:
                    # Fall back to JavaScript click if intercepted
                    logger.debug(f"click_element() - Selenium click failed ({str(e)[:50]}), falling back to JS click")
                    self.driver.execute_script("arguments[0].click();", element)
            
            logger.debug(f"click_element() - Successfully clicked element, waiting 1 second")
            time.sleep(1)
            
        except (TimeoutException, NoSuchElementException) as e:
            logger.warning(f"click_element() - Failed to find element {selector}: {str(e)[:100]}")
            try:
                element = WebDriverWait(self.driver, self.wait_time).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                )
                element.click()
                logger.debug(f"click_element() - Retry succeeded")
                time.sleep(1)  # Wait for content to load after click
            except (TimeoutException, NoSuchElementException) as e:
                logger.error(f"click_element() - Final click attempt failed for {selector}: {str(e)[:100]}")
    
    def scroll_to_bottom(self, pause_time: float = 1.0, max_scrolls: int = 10):
        """Scroll to bottom of page (useful for infinite scroll)"""
        if not self.driver:
            raise RuntimeError("Driver not initialized")
        
        logger.debug(f"scroll_to_bottom() - Starting scroll with max_scrolls={max_scrolls}, pause_time={pause_time}")
        last_height = self.driver.execute_script("return document.body.scrollHeight")
        logger.debug(f"scroll_to_bottom() - Initial page height: {last_height}")
        scrolls = 0
        
        while scrolls < max_scrolls:
            # Scroll down
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(pause_time)
            
            # Calculate new scroll height
            new_height = self.driver.execute_script("return document.body.scrollHeight")
            
            if new_height == last_height:
                logger.debug(f"scroll_to_bottom() - No new content loaded after {scrolls} scrolls, stopping")
                break
            
            logger.debug(f"scroll_to_bottom() - Scroll {scrolls+1}: height increased from {last_height} to {new_height}")
            last_height = new_height
            scrolls += 1
        
        logger.debug(f"scroll_to_bottom() - Completed with {scrolls} scrolls, final height: {last_height}")

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
        
        logger.debug(f"click_until_gone() - Start clicking '{selector}' up to {max_clicks} times")
        clicks = 0
        
        for attempt in range(max_clicks):
            try:
                # Check if element exists and is clickable
                element = WebDriverWait(self.driver, 2).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                )
                logger.debug(f"click_until_gone() - Click {attempt+1}: element found")
                
                # Scroll element into view
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                time.sleep(0.5)
                
                # Click the element
                element.click()
                clicks += 1
                logger.debug(f"click_until_gone() - Click {attempt+1}: successfully clicked")
                
                # Wait for content to load
                time.sleep(pause_time)
                
            except (TimeoutException, NoSuchElementException):
                # Element not found or not clickable anymore - we're done
                logger.debug(f"click_until_gone() - Element no longer found after {clicks} clicks, stopping")
                break
            except Exception as e:
                logger.error(f"click_until_gone() - Error during click {attempt+1}: {str(e)[:100]}")
                break
        
        logger.debug(f"click_until_gone() - Completed with {clicks} successful clicks")
        return clicks

    def click_if_present_else_wait(
        self,
        click_selector: str,
        wait_selector: str,
        check_timeout: float = 2.0,
        wait_timeout: Optional[float] = None,
        use_js: bool = False,
        dismiss_overlays: bool = True,
    ) -> bool:
        """
        Click an element if it exists (quick check); otherwise wait for a target element to appear.

        Args:
            click_selector: CSS selector for the element to click if present (e.g., "button.show-more")
            wait_selector: CSS selector that indicates the desired content is present after click
            check_timeout: short timeout (seconds) to check for the click element's presence
            wait_timeout: timeout (seconds) to wait for the `wait_selector` after click or when element absent
            use_js: use JavaScript click instead of Selenium click
            dismiss_overlays: attempt to remove common overlays before clicking

        Returns:
            True if the click was performed, False if click element was not present (but waited for `wait_selector`)
        """
        if not self.driver:
            raise RuntimeError("Driver not initialized")

        if wait_timeout is None:
            wait_timeout = self.wait_time

        try:
            # Quick check: does the clickable element exist?
            element = WebDriverWait(self.driver, check_timeout).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, click_selector))
            )

            # If found, attempt to click it (with optional overlay dismissal)
            if dismiss_overlays:
                self._dismiss_common_overlays()

            try:
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                time.sleep(0.3)

                if use_js:
                    self.driver.execute_script("arguments[0].click();", element)
                else:
                    try:
                        clickable = WebDriverWait(self.driver, 3).until(
                            EC.element_to_be_clickable((By.CSS_SELECTOR, click_selector))
                        )
                        clickable.click()
                    except Exception:
                        # Fallback to JS click when normal click fails
                        self.driver.execute_script("arguments[0].click();", element)

            except Exception as e:
                print(f"Click attempt failed, continuing to wait: {e}")

            # After clicking, wait for the expected content
            WebDriverWait(self.driver, wait_timeout).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, wait_selector))
            )
            return True

        except TimeoutException:
            # Click element wasn't found in the quick check — just wait for the target selector
            try:
                WebDriverWait(self.driver, wait_timeout).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, wait_selector))
                )
            except TimeoutException:
                print(f"Timeout waiting for element: {wait_selector}")
            return False
        except Exception as e:
            print(f"click_if_present_else_wait error: {e}")
            return False

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