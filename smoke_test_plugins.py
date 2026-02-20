"""
Automated UI smoke test for Streamlit Plugins dashboard.
Tests http://localhost:8501 with comprehensive checks.
"""
import time
import sys
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.edge.options import Options

class PluginDashboardSmokeTest:
    def __init__(self):
        self.url = "http://localhost:8501"
        self.driver = None
        self.results = []
        self.issues = []
        self.blockers = []
        
    def setup(self):
        """Initialize Edge browser in headless mode."""
        try:
            options = Options()
            options.add_argument('--headless')
            options.add_argument('--disable-gpu')
            options.add_argument('--no-sandbox')
            self.driver = webdriver.Edge(options=options)
            self.driver.set_page_load_timeout(30)
            return True
        except Exception as e:
            self.blockers.append(f"Browser setup failed: {e}")
            return False
    
    def check_page_loads(self):
        """Step 1-2: Open URL and confirm app loads."""
        try:
            self.driver.get(self.url)
            time.sleep(3)  # Wait for Streamlit to initialize
            
            # Check if page loaded (not blank/error)
            page_source = self.driver.page_source.lower()
            
            if 'streamlit' in page_source or 'vagus' in page_source:
                self.results.append(("Page loads", "PASS"))
                return True
            else:
                self.results.append(("Page loads", "FAIL"))
                self.issues.append("Page loaded but no Streamlit/Vagus content detected")
                return False
                
        except TimeoutException:
            self.results.append(("Page loads", "FAIL"))
            self.blockers.append("Page load timeout after 30s")
            return False
        except Exception as e:
            self.results.append(("Page loads", "FAIL"))
            self.blockers.append(f"Page load error: {e}")
            return False
    
    def navigate_to_plugins(self):
        """Step 3: Navigate to Plugins page."""
        try:
            # Wait for page to fully load
            time.sleep(3)
            
            # Try multiple selectors for Plugins link
            selectors = [
                ("xpath", "//a[contains(text(), 'Plugins')]"),
                ("xpath", "//a[contains(text(), '8_Plugins')]"),
                ("xpath", "//span[contains(text(), 'Plugins')]"),
                ("partial_link_text", "Plugins")
            ]
            
            plugins_link = None
            for selector_type, selector in selectors:
                try:
                    if selector_type == "xpath":
                        plugins_link = self.driver.find_element(By.XPATH, selector)
                    elif selector_type == "partial_link_text":
                        plugins_link = self.driver.find_element(By.PARTIAL_LINK_TEXT, selector)
                    
                    if plugins_link:
                        # Try JavaScript click if regular click fails
                        try:
                            plugins_link.click()
                        except:
                            self.driver.execute_script("arguments[0].click();", plugins_link)
                        
                        time.sleep(3)
                        self.results.append(("Navigate to Plugins page", "PASS"))
                        return True
                        
                except NoSuchElementException:
                    continue
            
            # If navigation failed, check if we're already on a page with plugin content
            page_source = self.driver.page_source.lower()
            if 'plugin' in page_source and ('installed' in page_source or 'marketplace' in page_source):
                self.results.append(("Navigate to Plugins page", "WARN"))
                self.issues.append("Could not click Plugins link but plugin content detected")
                return True
            
            self.results.append(("Navigate to Plugins page", "FAIL"))
            self.issues.append("Could not find or navigate to Plugins page")
            return False
                
        except Exception as e:
            self.results.append(("Navigate to Plugins page", "FAIL"))
            self.issues.append(f"Navigation error: {e}")
            return False
    
    def check_tabs_present(self):
        """Step 4: Verify tabs are present."""
        expected_tabs = ['Installed', 'Marketplace', 'Trending', 'Hot Reload']
        found_tabs = []
        
        try:
            page_text = self.driver.page_source.lower()
            
            for tab in expected_tabs:
                if tab.lower() in page_text:
                    found_tabs.append(tab)
                    self.results.append((f"Tab '{tab}' present", "PASS"))
                else:
                    self.results.append((f"Tab '{tab}' present", "FAIL"))
                    self.issues.append(f"Tab '{tab}' not found in page")
            
            return len(found_tabs) > 0
            
        except Exception as e:
            self.results.append(("Check tabs", "FAIL"))
            self.issues.append(f"Tab check error: {e}")
            return False
    
    def test_installed_tab(self):
        """Step 5: Test Installed tab functionality."""
        try:
            # Check if demo-plugin is visible
            page_source = self.driver.page_source.lower()
            
            if 'demo-plugin' in page_source or 'demo plugin' in page_source:
                self.results.append(("demo-plugin visible", "PASS"))
            else:
                self.results.append(("demo-plugin visible", "WARN"))
                self.issues.append("demo-plugin not found (may not be installed)")
            
            # Look for action controls (buttons)
            buttons = self.driver.find_elements(By.TAG_NAME, "button")
            action_buttons = [b for b in buttons if b.text.lower() in 
                            ['enable', 'disable', 'refresh', 'config', 'reload']]
            
            if action_buttons:
                self.results.append(("Action controls present", "PASS"))
                
                # Try clicking first action button
                try:
                    action_buttons[0].click()
                    time.sleep(1)
                    
                    # Check for feedback message
                    page_after = self.driver.page_source.lower()
                    if 'success' in page_after or 'error' in page_after or 'enabled' in page_after:
                        self.results.append(("Action feedback message", "PASS"))
                    else:
                        self.results.append(("Action feedback message", "WARN"))
                        self.issues.append("No clear feedback after action")
                        
                except Exception as e:
                    self.results.append(("Action button click", "FAIL"))
                    self.issues.append(f"Button click failed: {e}")
            else:
                self.results.append(("Action controls present", "FAIL"))
                self.issues.append("No action buttons found")
            
            # Check for dependency section
            if 'dependency' in page_source or 'dependencies' in page_source:
                self.results.append(("Dependency section present", "PASS"))
            else:
                self.results.append(("Dependency section present", "WARN"))
                
        except Exception as e:
            self.results.append(("Installed tab test", "FAIL"))
            self.issues.append(f"Installed tab error: {e}")
    
    def test_marketplace_tab(self):
        """Step 6: Test Marketplace tab."""
        try:
            # Look for search input
            inputs = self.driver.find_elements(By.TAG_NAME, "input")
            search_input = None
            
            for inp in inputs:
                placeholder = inp.get_attribute("placeholder") or ""
                if 'search' in placeholder.lower() or 'поиск' in placeholder.lower():
                    search_input = inp
                    break
            
            if search_input:
                self.results.append(("Marketplace search input", "PASS"))
                
                # Try search interaction
                try:
                    search_input.send_keys("test")
                    time.sleep(1)
                    
                    # Check if results render
                    page_after = self.driver.page_source.lower()
                    if 'result' in page_after or 'plugin' in page_after or 'not found' in page_after or 'не найдены' in page_after:
                        self.results.append(("Marketplace search results", "PASS"))
                    else:
                        self.results.append(("Marketplace search results", "WARN"))
                        
                except Exception as e:
                    self.results.append(("Marketplace search interaction", "FAIL"))
                    self.issues.append(f"Search interaction failed: {e}")
            else:
                self.results.append(("Marketplace search input", "FAIL"))
                self.issues.append("No search input found in Marketplace")
                
        except Exception as e:
            self.results.append(("Marketplace tab test", "FAIL"))
            self.issues.append(f"Marketplace error: {e}")
    
    def test_hot_reload_tab(self):
        """Step 7: Test Hot Reload tab."""
        try:
            page_source = self.driver.page_source.lower()
            
            # Check for status widgets/metrics
            if 'status' in page_source or 'metric' in page_source:
                self.results.append(("Hot Reload status widgets", "PASS"))
            else:
                self.results.append(("Hot Reload status widgets", "WARN"))
            
            # Look for Refresh button
            buttons = self.driver.find_elements(By.TAG_NAME, "button")
            refresh_button = None
            
            for btn in buttons:
                if 'refresh' in btn.text.lower() or 'reload' in btn.text.lower():
                    refresh_button = btn
                    break
            
            if refresh_button:
                self.results.append(("Hot Reload refresh button", "PASS"))
                try:
                    refresh_button.click()
                    time.sleep(1)
                    self.results.append(("Refresh button click", "PASS"))
                except Exception as e:
                    self.results.append(("Refresh button click", "FAIL"))
                    self.issues.append(f"Refresh click failed: {e}")
            else:
                self.results.append(("Hot Reload refresh button", "WARN"))
                
        except Exception as e:
            self.results.append(("Hot Reload tab test", "FAIL"))
            self.issues.append(f"Hot Reload error: {e}")
    
    def check_for_errors(self):
        """Step 8: Capture visible UI errors."""
        try:
            page_source = self.driver.page_source
            
            error_indicators = [
                'Traceback',
                'ModuleNotFoundError',
                'Exception',
                'Error:',
                'Failed to',
                'stacktrace'
            ]
            
            found_errors = []
            for indicator in error_indicators:
                if indicator in page_source:
                    found_errors.append(indicator)
            
            if found_errors:
                self.results.append(("No UI errors", "FAIL"))
                self.issues.append(f"UI errors detected: {', '.join(found_errors)}")
            else:
                self.results.append(("No UI errors", "PASS"))
                
        except Exception as e:
            self.issues.append(f"Error check failed: {e}")
    
    def run(self):
        """Execute full smoke test."""
        print("=" * 60)
        print("STREAMLIT PLUGINS DASHBOARD - UI SMOKE TEST")
        print("=" * 60)
        print()
        
        if not self.setup():
            return self.generate_report()
        
        try:
            # Execute test steps
            if not self.check_page_loads():
                return self.generate_report()
            
            if not self.navigate_to_plugins():
                return self.generate_report()
            
            self.check_tabs_present()
            self.test_installed_tab()
            self.test_marketplace_tab()
            self.test_hot_reload_tab()
            self.check_for_errors()
            
        finally:
            if self.driver:
                self.driver.quit()
        
        return self.generate_report()
    
    def generate_report(self):
        """Generate structured pass/fail report."""
        # Calculate verdict
        passes = sum(1 for _, status in self.results if status == "PASS")
        fails = sum(1 for _, status in self.results if status == "FAIL")
        warns = sum(1 for _, status in self.results if status == "WARN")
        
        if len(self.blockers) > 0:
            verdict = "FAIL"
        elif fails > 0:
            verdict = "FAIL"
        elif warns > 0:
            verdict = "PARTIAL"
        else:
            verdict = "PASS"
        
        # Print report
        print(f"OVERALL VERDICT: {verdict}")
        print()
        print("TEST RESULTS:")
        print("-" * 60)
        
        for check, status in self.results:
            icon = "[PASS]" if status == "PASS" else "[WARN]" if status == "WARN" else "[FAIL]"
            print(f"{icon} {check}: {status}")
        
        if self.issues:
            print()
            print("ISSUES FOUND:")
            print("-" * 60)
            for i, issue in enumerate(self.issues, 1):
                print(f"{i}. {issue}")
        
        if self.blockers:
            print()
            print("BLOCKERS:")
            print("-" * 60)
            for i, blocker in enumerate(self.blockers, 1):
                print(f"{i}. {blocker}")
        
        print()
        print("=" * 60)
        print(f"Summary: {passes} passed, {fails} failed, {warns} warnings")
        print("=" * 60)
        
        return verdict

if __name__ == "__main__":
    test = PluginDashboardSmokeTest()
    verdict = test.run()
    sys.exit(0 if verdict == "PASS" else 1)
