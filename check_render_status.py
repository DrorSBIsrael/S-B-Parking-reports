import requests
import time

print("="*60)
print("   CHECKING RENDER DEPLOYMENT STATUS")
print("="*60)

# Check if proxy endpoint exists
proxy_url = "https://s-b-parking-reports.onrender.com/api/company-manager/proxy"

print("\n1. Testing proxy endpoint...")
try:
    r = requests.get(proxy_url, timeout=5)
    print(f"   Status: {r.status_code}")
    
    if r.status_code == 404:
        print("   ❌ Proxy STILL returning 404")
        print("\n   Possible reasons:")
        print("   1. Render is still building (takes 3-5 minutes)")
        print("   2. The deployment failed")
        print("   3. There's an error in the route definition")
        
    elif r.status_code == 200:
        print("   ✅ Proxy endpoint is LIVE!")
        print(f"   Response: {r.json()}")
        
    elif r.status_code == 401:
        print("   ⚠️ Proxy exists but requires authentication")
        
except Exception as e:
    print(f"   Error: {e}")

# Check Render build status page
print("\n2. Check Render dashboard:")
print("   https://dashboard.render.com/web/srv-ct5gfkd6l47c73ai5390/deploys")
print("\n   Look for:")
print("   - Is there a deployment in progress? (spinning icon)")
print("   - Did the last deployment succeed? (green checkmark)")
print("   - Any error messages in the logs?")

# Test a simple endpoint to see if the server is up
print("\n3. Testing if server is responding...")
test_url = "https://s-b-parking-reports.onrender.com/api/test-proxy"
try:
    r = requests.get(test_url, timeout=5)
    print(f"   Test endpoint status: {r.status_code}")
    if r.status_code == 200:
        print("   ✅ Server is running")
except:
    print("   ❌ Server might be down or restarting")

print("\n" + "="*60)
print("   WHAT TO DO:")
print("="*60)
print("\nIf proxy still returns 404:")
print("1. Wait 2-3 more minutes for Render to finish")
print("2. Check Render dashboard for errors")
print("3. We might need to check the app.py route definition")
