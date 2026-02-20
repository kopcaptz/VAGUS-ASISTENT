"""Debug authentication test with screenshots."""
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.edge.options import Options
from selenium.webdriver.common.keys import Keys

options = Options()
# Remove headless to see what's happening
# options.add_argument('--headless')
driver = webdriver.Edge(options=options)

try:
    print("Loading dashboard...")
    driver.get("http://localhost:8501")
    time.sleep(4)
    
    print("Looking for form fields...")
    inputs = driver.find_elements(By.TAG_NAME, "input")
    print(f"Found {len(inputs)} input fields")
    
    username_field = None
    password_field = None
    
    for i, inp in enumerate(inputs):
        input_type = inp.get_attribute("type") or "text"
        placeholder = inp.get_attribute("placeholder") or ""
        aria_label = inp.get_attribute("aria-label") or ""
        
        print(f"Input {i}: type={input_type}, placeholder='{placeholder}', aria-label='{aria_label}'")
        
        if input_type == "text" or "логин" in placeholder.lower():
            username_field = inp
            print(f"  -> Using as username field")
        elif input_type == "password":
            password_field = inp
            print(f"  -> Using as password field")
    
    if username_field and password_field:
        print("\nFilling username...")
        username_field.click()
        time.sleep(0.5)
        username_field.clear()
        username_field.send_keys("admin")
        print(f"Username field value: '{username_field.get_attribute('value')}'")
        
        print("\nFilling password...")
        password_field.click()
        time.sleep(0.5)
        password_field.clear()
        password_field.send_keys("admin")
        # Don't print password value for security
        print("Password filled")
        
        time.sleep(1)
        
        print("\nLooking for submit button...")
        buttons = driver.find_elements(By.TAG_NAME, "button")
        for i, btn in enumerate(buttons):
            btn_text = btn.text
            print(f"Button {i}: '{btn_text}'")
            if 'войти' in btn_text.lower() or 'login' in btn_text.lower():
                print(f"  -> Clicking this button")
                btn.click()
                break
        
        print("\nWaiting for response...")
        time.sleep(6)
        
        page_after = driver.page_source
        
        if 'успешный' in page_after.lower() or 'success' in page_after.lower():
            print("\n✓ SUCCESS detected in page!")
        elif 'неверный' in page_after.lower() or 'error' in page_after.lower():
            print("\n✗ ERROR detected in page!")
            # Find error messages
            errors = driver.find_elements(By.XPATH, "//*[contains(text(), 'неверный') or contains(text(), 'Неверный') or contains(text(), 'error') or contains(text(), 'Error')]")
            for err in errors:
                if err.text:
                    print(f"Error text: {err.text}")
        else:
            print("\n? Status unclear")
        
        # Check if we're logged in
        if 'авторизованы' in page_after.lower():
            print("✓ 'Вы авторизованы' found - LOGIN SUCCESSFUL!")
        
        print("\nKeeping browser open for 10 seconds for manual inspection...")
        time.sleep(10)
    else:
        print(f"\nERROR: Could not find form fields (username: {username_field is not None}, password: {password_field is not None})")
        time.sleep(5)

finally:
    driver.quit()
    print("\nTest complete")
