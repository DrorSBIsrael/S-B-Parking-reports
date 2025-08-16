"""
בדיקת חיבור עם בעיות SSL וHostname
"""
import requests
import urllib3
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.poolmanager import PoolManager
import ssl
import base64

# ביטול אזהרות SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# הגדרות
IP = "192.117.0.122"
PORT = "8240"
HOSTNAMES = ['olymplr1', 'olymplr1.local', 'localhost', IP]

print("=" * 60)
print("🔍 בדיקת חיבור לחניון עם טיפול ב-SSL")
print("=" * 60)

# מחלקה לעקוף בעיות hostname verification
class SSLAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        kwargs['ssl_context'] = context
        return super(SSLAdapter, self).init_poolmanager(*args, **kwargs)

# נסה פרוטוקולים שונים
protocols = ['https', 'http']

for protocol in protocols:
    for hostname in HOSTNAMES:
        print(f"\n🧪 מנסה: {protocol}://{IP}:{PORT}/api/contracts")
        print(f"   Host Header: {hostname}")
        
        try:
            # יצירת session עם הגדרות SSL מיוחדות
            session = requests.Session()
            session.mount('https://', SSLAdapter())
            session.mount('http://', SSLAdapter())
            
            # הגדרת headers
            headers = {
                'Host': hostname,
                'Accept': '*/*',
                'User-Agent': 'Python/requests',
                'Content-Type': 'application/json'
            }
            
            # הוספת Basic Auth
            auth_string = base64.b64encode(b'2022:2022').decode('ascii')
            headers['Authorization'] = f'Basic {auth_string}'
            
            url = f"{protocol}://{IP}:{PORT}/api/contracts"
            
            # ניסיון חיבור
            response = session.get(url, headers=headers, verify=False, timeout=10)
            
            print(f"   ✅ הצלחה! Status: {response.status_code}")
            print(f"   Response: {response.text[:200]}...")
            
            # אם הצליח, שמור את ההגדרות
            print("\n" + "🎯" * 30)
            print(f"🎯 הגדרות עובדות:")
            print(f"   Protocol: {protocol}")
            print(f"   Host Header: {hostname}")
            print("🎯" * 30)
            break
            
        except requests.exceptions.Timeout:
            print(f"   ⏱️ Timeout")
        except requests.exceptions.SSLError as e:
            print(f"   🔐 SSL Error: {str(e)[:100]}")
        except requests.exceptions.ConnectionError as e:
            print(f"   ❌ Connection Error: {str(e)[:100]}")
        except Exception as e:
            print(f"   ❌ Error: {type(e).__name__}: {str(e)[:100]}")
    else:
        continue
    break

print("\n" + "=" * 60)
print("📌 המלצות:")
print("1. אם אף אחד לא עבד - הבעיה היא בחיבור/פיירוול")
print("2. אם משהו עבד - עדכן את ההגדרות ב-appV3.py")
print("3. שים לב לשם ה-Host שעבד - זה קריטי!")
print("=" * 60)
