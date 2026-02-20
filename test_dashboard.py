"""Test script to verify dashboard is accessible."""
import requests
import time

def test_dashboard():
    """Test if dashboard loads and check for errors."""
    try:
        # Test main page
        response = requests.get('http://localhost:8502', timeout=10)
        print(f"Status Code: {response.status_code}")
        print(f"Content Length: {len(response.content)}")
        
        # Check for error indicators in HTML
        content = response.text.lower()
        has_errors = False
        
        if 'error' in content:
            print("\nWARNING: 'error' found in page content")
            has_errors = True
        if 'traceback' in content:
            print("WARNING: 'traceback' found in page content")
            has_errors = True
        if 'modulenotfounderror' in content:
            print("WARNING: 'ModuleNotFoundError' found in page content")
            has_errors = True
        
        # Check if page contains expected elements
        if 'vagus asistent' in content:
            print("\nOK: Dashboard title found")
        if 'streamlit' in content:
            print("OK: Streamlit detected")
        
        if not has_errors:
            print("\nOK: Dashboard appears to be loading successfully")
        
        # Print first 500 chars of content
        print("\n--- First 500 chars of response ---")
        print(response.text[:500])
        return True
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Error accessing dashboard: {e}")
        return False

if __name__ == "__main__":
    print("Testing Streamlit Dashboard at http://localhost:8502...\n")
    test_dashboard()
