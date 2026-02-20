"""Test API login endpoint."""
import requests

def test_login(username, password):
    """Test login with given credentials."""
    url = "http://localhost:8000/api/v1/auth/token"
    payload = {"username": username, "password": password}
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
        
        if response.status_code == 200:
            data = response.json()
            if "access_token" in data:
                print(f"\n[SUCCESS] Login successful!")
                print(f"Token: {data['access_token'][:50]}...")
                return True
        else:
            print(f"\n[FAIL] Login failed")
            return False
            
    except Exception as e:
        print(f"[ERROR] {e}")
        return False

if __name__ == "__main__":
    print("Testing API login with admin/admin...")
    test_login("admin", "admin")
