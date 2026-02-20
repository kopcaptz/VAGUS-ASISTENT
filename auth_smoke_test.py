"""
Authenticated UI smoke test for Streamlit Plugins dashboard.
"""
import time
import sys
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.edge.options import Options

def run_authenticated_test():
    """Run smoke test with authentication."""
    print("=" * 60)
    print("AUTHENTICATED STREAMLIT PLUGINS SMOKE TEST")
    print("=" * 60)
    print()
    
    # Setup browser
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    driver = webdriver.Edge(options=options)
    driver.set_page_load_timeout(30)
    
    try:
        # Step 1: Load dashboard
        print("[1] Loading dashboard at http://localhost:8501...")
        driver.get("http://localhost:8501")
        time.sleep(4)
        
        # Step 2: Detect and fill login form
        print("[2] Detecting login form...")
        page_source = driver.page_source.lower()
        
        if 'login' in page_source or 'password' in page_source or 'вход' in page_source:
            print("    Login form detected!")
            
            # Find username/login input
            username_input = None
            password_input = None
            login_button = None
            
            # Try to find username field
            inputs = driver.find_elements(By.TAG_NAME, "input")
            for inp in inputs:
                input_type = (inp.get_attribute("type") or "").lower()
                placeholder = (inp.get_attribute("placeholder") or "").lower()
                
                if input_type == "text" or 'login' in placeholder or 'логин' in placeholder:
                    username_input = inp
                elif input_type == "password" or 'password' in placeholder or 'пароль' in placeholder:
                    password_input = inp
            
            if username_input and password_input:
                print("    Found username and password fields")
                
                # Fill credentials
                username_input.clear()
                username_input.send_keys("admin")
                print("    Entered username: admin")
                
                password_input.clear()
                password_input.send_keys("admin")
                print("    Entered password: admin")
                
                time.sleep(1)
                
                # Find and click login button
                buttons = driver.find_elements(By.TAG_NAME, "button")
                for btn in buttons:
                    btn_text = btn.text.lower()
                    if 'login' in btn_text or 'войти' in btn_text or 'submit' in btn_text:
                        login_button = btn
                        break
                
                if login_button:
                    print("    Clicking login button...")
                    try:
                        login_button.click()
                    except:
                        driver.execute_script("arguments[0].click();", login_button)
                    
                    # Wait longer for Streamlit to process
                    print("    Waiting for login response...")
                    time.sleep(5)
                    
                    # Check if login succeeded
                    page_after = driver.page_source
                    page_after_lower = page_after.lower()
                    
                    # Look for error messages
                    if 'error' in page_after_lower or 'неверный' in page_after_lower:
                        # Try to extract exact error message
                        error_elements = driver.find_elements(By.XPATH, "//*[contains(text(), 'error') or contains(text(), 'Error') or contains(text(), 'неверный') or contains(text(), 'Неверный')]")
                        
                        exact_error = "Login failed - error detected"
                        if error_elements:
                            exact_error = f"Error message: '{error_elements[0].text}'"
                        elif 'неверный логин или пароль' in page_after_lower:
                            exact_error = "Error: 'Неверный логин или пароль'"
                        
                        print(f"\n[FAIL] {exact_error}")
                        
                        # Also check if there's a visible error container
                        try:
                            error_divs = driver.find_elements(By.CSS_SELECTOR, "[data-testid='stAlert'], .stAlert, [role='alert']")
                            if error_divs:
                                for div in error_divs:
                                    if div.text:
                                        print(f"    Alert text: '{div.text}'")
                        except:
                            pass
                        
                        return "FAIL", exact_error
                    
                    # Check for success indicators
                    has_success = 'success' in page_after_lower or 'успешный' in page_after_lower
                    has_dashboard = 'vagus' in page_after_lower or 'dashboard' in page_after_lower
                    has_tasks = 'tasks' in page_after_lower or 'задач' in page_after_lower
                    
                    if has_success:
                        print("    [PASS] Login succeeded! (success message detected)")
                    elif has_dashboard or has_tasks:
                        print("    [PASS] Login succeeded! (dashboard content detected)")
                    else:
                        print("    Login status unclear, checking for login form...")
                        # If login form still present, login failed
                        if 'password' in page_after_lower and ('login' in page_after_lower or 'вход' in page_after_lower):
                            print("    [WARN] Login form still present - may have failed silently")
                        else:
                            print("    Proceeding (login form no longer visible)...")
                else:
                    print("    [FAIL] Login button not found")
                    return "FAIL", "Login button not found"
            else:
                print(f"    [FAIL] Login fields not found (username: {username_input is not None}, password: {password_input is not None})")
                return "FAIL", "Login form fields incomplete"
        else:
            print("    No login form detected - may already be authenticated")
        
        # Step 3: Navigate to Plugins page
        print("\n[3] Navigating to Plugins page...")
        time.sleep(2)
        
        # Try to find Plugins link
        plugins_link = None
        try:
            plugins_link = driver.find_element(By.PARTIAL_LINK_TEXT, "Plugins")
        except:
            try:
                plugins_link = driver.find_element(By.XPATH, "//a[contains(text(), 'Plugins')]")
            except:
                pass
        
        if plugins_link:
            try:
                plugins_link.click()
            except:
                driver.execute_script("arguments[0].click();", plugins_link)
            
            time.sleep(3)
            print("    Navigated to Plugins page")
        else:
            print("    Could not find Plugins link, checking current page...")
        
        # Step 4: Verify tabs are visible
        print("\n[4] Verifying tabs presence...")
        page_content = driver.page_source
        
        tabs_found = []
        tabs_expected = ["Installed", "Marketplace", "Trending", "Hot Reload"]
        
        for tab in tabs_expected:
            if tab in page_content:
                tabs_found.append(tab)
                print(f"    [PASS] Tab '{tab}' found")
            else:
                print(f"    [FAIL] Tab '{tab}' NOT found")
        
        # Check for plugin-related content
        page_lower = page_content.lower()
        has_plugin_content = 'plugin' in page_lower
        has_install = 'install' in page_lower or 'установ' in page_lower
        has_enabled = 'enabled' in page_lower or 'включено' in page_lower
        
        print(f"\n[5] Plugin content indicators:")
        print(f"    - Plugin mentions: {'YES' if has_plugin_content else 'NO'}")
        print(f"    - Install functionality: {'YES' if has_install else 'NO'}")
        print(f"    - Enable/Disable indicators: {'YES' if has_enabled else 'NO'}")
        
        # Final verdict
        print("\n" + "=" * 60)
        if len(tabs_found) == 4:
            print("VERDICT: PASS - All 4 tabs visible")
            return "PASS", f"All tabs found: {', '.join(tabs_found)}"
        elif len(tabs_found) > 0:
            print(f"VERDICT: PARTIAL - {len(tabs_found)}/4 tabs visible")
            return "PARTIAL", f"Found {len(tabs_found)} tabs: {', '.join(tabs_found)}"
        else:
            print("VERDICT: FAIL - No tabs visible")
            return "FAIL", "No tabs found on Plugins page"
        
    except Exception as e:
        print(f"\n[ERROR] Test failed with exception: {e}")
        return "FAIL", str(e)
    
    finally:
        driver.quit()
        print("=" * 60)

if __name__ == "__main__":
    verdict, details = run_authenticated_test()
    print(f"\nFinal Result: {verdict}")
    print(f"Details: {details}")
    sys.exit(0 if verdict == "PASS" else 1)
