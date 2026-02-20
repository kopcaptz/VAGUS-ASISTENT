"""Careful login test with explicit waits for Streamlit."""
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.edge.options import Options
from selenium.common.exceptions import TimeoutException

def wait_for_streamlit_ready(driver, timeout=10):
    """Wait for Streamlit to finish loading."""
    try:
        # Wait for Streamlit's main container
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "[data-testid='stApp']"))
        )
        return True
    except TimeoutException:
        return False

def find_input_by_label(driver, label_text):
    """Find input field by its label text."""
    try:
        # Streamlit labels are usually in a div before the input
        labels = driver.find_elements(By.XPATH, f"//*[contains(text(), '{label_text}')]")
        for label in labels:
            # Try to find input in the same container or next sibling
            parent = label.find_element(By.XPATH, "./..")
            inputs = parent.find_elements(By.TAG_NAME, "input")
            if inputs:
                return inputs[0]
    except:
        pass
    return None

def run_careful_login():
    """Execute careful login with explicit waits."""
    print("=" * 70)
    print("CAREFUL LOGIN TEST WITH EXPLICIT WAITS")
    print("=" * 70)
    
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--disable-gpu')
    driver = webdriver.Edge(options=options)
    driver.set_page_load_timeout(30)
    
    try:
        # Step 1: Refresh page
        print("\n[Step 1] Loading/refreshing page at http://localhost:8501...")
        driver.get("http://localhost:8501")
        
        # Wait for Streamlit to be ready
        if not wait_for_streamlit_ready(driver):
            print("  [FAIL] Streamlit app did not load")
            return "FAIL", "Streamlit app did not load"
        
        print("  [OK] Page loaded")
        time.sleep(2)  # Additional wait for dynamic content
        
        # Step 2: Wait until username/password fields visible
        print("\n[Step 2] Waiting for login form fields to be visible...")
        
        username_field = None
        password_field = None
        
        # Try multiple strategies to find fields
        for attempt in range(3):
            print(f"  Attempt {attempt + 1}/3...")
            time.sleep(2)
            
            # Strategy 1: Find by label text
            username_field = find_input_by_label(driver, "Логин")
            password_field = find_input_by_label(driver, "Пароль")
            
            # Strategy 2: Find all inputs and identify by type
            if not username_field or not password_field:
                inputs = driver.find_elements(By.TAG_NAME, "input")
                print(f"    Found {len(inputs)} input elements")
                
                for inp in inputs:
                    try:
                        input_type = inp.get_attribute("type")
                        if input_type == "text" and not username_field:
                            username_field = inp
                        elif input_type == "password" and not password_field:
                            password_field = inp
                    except:
                        continue
            
            if username_field and password_field:
                print("  [OK] Both fields found!")
                break
        
        if not username_field or not password_field:
            print(f"  [FAIL] Could not find login fields")
            print(f"    Username field: {'Found' if username_field else 'NOT FOUND'}")
            print(f"    Password field: {'Found' if password_field else 'NOT FOUND'}")
            
            # Debug: print page structure
            page_text = driver.page_source[:1000]
            if 'логин' in page_text.lower() or 'login' in page_text.lower():
                print("    Note: Login text found in page source")
            
            return "FAIL", "Login form fields not found after 3 attempts"
        
        # Step 3: Clear fields then fill exactly
        print("\n[Step 3] Filling credentials...")
        
        try:
            # Clear and fill username
            print("  Clearing username field...")
            username_field.click()
            time.sleep(0.5)
            username_field.clear()
            time.sleep(0.5)
            
            print("  Typing username: admin")
            username_field.send_keys("admin")
            time.sleep(0.5)
            
            username_value = username_field.get_attribute("value")
            print(f"  Username field value: '{username_value}'")
            
            # Clear and fill password
            print("  Clearing password field...")
            password_field.click()
            time.sleep(0.5)
            password_field.clear()
            time.sleep(0.5)
            
            print("  Typing password: admin")
            password_field.send_keys("admin")
            time.sleep(0.5)
            
            print("  [OK] Credentials entered")
            
        except Exception as e:
            print(f"  [FAIL] Error filling fields: {e}")
            return "FAIL", f"Error filling credentials: {e}"
        
        # Step 4: Click login button once
        print("\n[Step 4] Finding and clicking login button...")
        
        login_button = None
        buttons = driver.find_elements(By.TAG_NAME, "button")
        print(f"  Found {len(buttons)} buttons")
        
        for i, btn in enumerate(buttons):
            try:
                btn_text = btn.text.strip()
                print(f"    Button {i}: '{btn_text}'")
                if 'войти' in btn_text.lower() or 'login' in btn_text.lower():
                    login_button = btn
                    print(f"    [OK] This is the login button")
                    break
            except:
                continue
        
        if not login_button:
            print("  [FAIL] Login button not found")
            return "FAIL", "Login button not found"
        
        print("  Clicking login button...")
        try:
            login_button.click()
        except:
            # Fallback to JavaScript click
            driver.execute_script("arguments[0].click();", login_button)
        
        print("  [OK] Button clicked")
        
        # Step 5: Wait and observe for up to 8 seconds
        print("\n[Step 5] Observing response for 8 seconds...")
        
        for second in range(1, 9):
            time.sleep(1)
            print(f"  {second}s...", end=" ", flush=True)
            
            # Check page state every 2 seconds
            if second % 2 == 0:
                page_source = driver.page_source
                page_lower = page_source.lower()
                
                # Check for success indicators
                if 'авторизованы' in page_lower or 'успешный вход' in page_lower:
                    print("\n  [OK] SUCCESS DETECTED!")
                    break
                
                # Check for error
                if 'неверный' in page_lower or 'error' in page_lower:
                    print("\n  [X] ERROR DETECTED")
                    break
        
        print()  # New line after countdown
        
        # Step 6: Final analysis
        print("\n[Step 6] Final analysis...")
        
        final_page = driver.page_source
        final_lower = final_page.lower()
        
        # Check for success
        if 'авторизованы' in final_lower or 'вы авторизованы' in final_lower:
            print("  [OK] LOGIN SUCCESSFUL - 'Вы авторизованы' found")
            
            # Check for sidebar/navigation
            if 'tasks' in final_lower or 'monitoring' in final_lower or 'plugins' in final_lower:
                print("  [OK] Sidebar navigation visible")
                
                # Try to find Plugins link
                try:
                    plugins_link = driver.find_element(By.PARTIAL_LINK_TEXT, "Plugins")
                    print("  [OK] Plugins page link found in sidebar")
                except:
                    print("  [!] Plugins link not found in sidebar")
            
            return "PASS", "Login successful - dashboard accessible"
        
        # Check for error message
        if 'неверный' in final_lower or 'error' in final_lower:
            print("  [X] LOGIN FAILED - Error message present")
            
            # Extract exact error text
            try:
                error_elements = driver.find_elements(By.XPATH, 
                    "//*[contains(text(), 'неверный') or contains(text(), 'Неверный') or contains(text(), 'error') or contains(text(), 'Error')]")
                
                for elem in error_elements:
                    error_text = elem.text.strip()
                    if error_text:
                        print(f"  Exact error: '{error_text}'")
                        return "FAIL", f"Login failed with error: {error_text}"
            except:
                pass
            
            return "FAIL", "Login failed - error message detected"
        
        # Check if login form still present
        if 'пароль' in final_lower and 'логин' in final_lower:
            print("  [!] Login form still visible - login may have failed silently")
            return "FAIL", "Login form still present after submission"
        
        # Unclear state
        print("  ? Status unclear - no clear success or error indicator")
        
        # Check what content is visible
        has_dashboard = 'dashboard' in final_lower
        has_vagus = 'vagus' in final_lower
        has_tasks = 'tasks' in final_lower
        
        print(f"  Content indicators:")
        print(f"    - Dashboard: {has_dashboard}")
        print(f"    - Vagus: {has_vagus}")
        print(f"    - Tasks: {has_tasks}")
        
        if has_dashboard or has_tasks:
            return "PARTIAL", "Login status unclear but dashboard content visible"
        else:
            return "FAIL", "No clear indication of successful login"
        
    except Exception as e:
        print(f"\n[ERROR] Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        return "FAIL", f"Exception: {e}"
    
    finally:
        driver.quit()
        print("\n" + "=" * 70)

if __name__ == "__main__":
    verdict, details = run_careful_login()
    print(f"\nFINAL VERDICT: {verdict}")
    print(f"DETAILS: {details}")
