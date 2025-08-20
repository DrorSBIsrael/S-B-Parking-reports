import requests

print("="*60)
print("  CHECKING GITHUB STATUS")
print("="*60)

# Check if proxy endpoint exists on GitHub
github_url = "https://raw.githubusercontent.com/aidanhaike1981/S-B-Parking-reports/master/app.py"

print("\n1. Checking GitHub master branch for proxy endpoint...")
try:
    response = requests.get(github_url)
    if response.status_code == 200:
        content = response.text
        
        # Check for proxy endpoint
        if "@app.route('/api/company-manager/proxy'" in content:
            print("   ✅ Proxy endpoint EXISTS on GitHub!")
            
            # Find the line number
            lines = content.split('\n')
            for i, line in enumerate(lines):
                if "/api/company-manager/proxy" in line:
                    print(f"   Found at line {i+1}")
                    break
        else:
            print("   ❌ Proxy endpoint NOT FOUND on GitHub!")
            print("   This means it was never pushed to GitHub")
            
    else:
        print(f"   Error accessing GitHub: {response.status_code}")
        
except Exception as e:
    print(f"   Error: {e}")

print("\n2. Checking production server...")
proxy_url = "https://s-b-parking-reports.onrender.com/api/company-manager/proxy"
try:
    r = requests.get(proxy_url, timeout=5)
    if r.status_code == 404:
        print("   ❌ Proxy endpoint returns 404 on production")
    elif r.status_code == 200:
        print("   ✅ Proxy endpoint is LIVE on production!")
    else:
        print(f"   Status: {r.status_code}")
except Exception as e:
    print(f"   Error: {e}")

print("\n" + "="*60)
print("  DIAGNOSIS:")
print("="*60)
print("\nIf proxy exists on GitHub but not on production:")
print("  → Render hasn't deployed the latest commit")
print("  → Need to trigger manual deploy")
print("\nIf proxy doesn't exist on GitHub:")
print("  → Need to push app.py first!")
print("  → Run: git add app.py && git commit && git push")

