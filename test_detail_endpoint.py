#!/usr/bin/env python3
import requests
import json

# Test the contract detail endpoint directly

print("="*60)
print("🔍 Testing contract/2/detail endpoint")
print("="*60)

# Try local server
try:
    print("\n📡 Testing local server...")
    response = requests.post('http://localhost:5000/api/company-manager/proxy',
        json={
            'parking_id': 'b4954e1c-646d-4905-9ab8-9e433bed75e4',
            'endpoint': 'contracts/2/detail',
            'method': 'GET'
        }
    )
    
    print(f"   Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        if data.get('success'):
            detail = data.get('data', {})
            pooling = detail.get('pooling', {})
            if pooling:
                print(f"   ✅ Found pooling data!")
                print(f"   📊 {json.dumps(pooling, indent=2)}")
            else:
                print(f"   ⚠️ No pooling data found")
                print(f"   Response: {json.dumps(detail, indent=2)[:500]}")
        else:
            print(f"   ❌ Error: {data.get('error')}")
    else:
        print(f"   ❌ HTTP {response.status_code}")
        print(f"   {response.text[:200]}")
        
except Exception as e:
    print(f"   ❌ Local server not running: {e}")

# Test Render
print("\n📡 Testing Render server...")
try:
    response = requests.post('https://s-b-parking-reports.onrender.com/api/company-manager/proxy',
        json={
            'parking_id': 'b4954e1c-646d-4905-9ab8-9e433bed75e4',
            'endpoint': 'contracts/2/detail',
            'method': 'GET'
        }
    )
    
    print(f"   Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        if data.get('success'):
            detail = data.get('data', {})
            pooling = detail.get('pooling', {})
            if pooling:
                print(f"   ✅ Found pooling data!")
                print(f"   📊 {json.dumps(pooling, indent=2)[:500]}")
            else:
                print(f"   ⚠️ No pooling data found")
                print(f"   Response: {json.dumps(detail, indent=2)[:500]}")
        else:
            print(f"   ❌ Error: {data.get('error')}")
    else:
        print(f"   ❌ HTTP {response.status_code}")
        print(f"   {response.text[:200]}")
        
except Exception as e:
    print(f"   ❌ Error: {e}")

print("\n" + "="*60)
