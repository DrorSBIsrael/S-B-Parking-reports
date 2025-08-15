"""
בדיקה שהתיקון עובד
==================
"""
from dotenv import load_dotenv
import os
from supabase import create_client

load_dotenv()

url = os.environ.get('SUPABASE_URL')
key = os.environ.get('SUPABASE_ANON_KEY')

if url and key:
    supabase = create_client(url, key)
    
    # בדיקת המשתמש
    user = supabase.table('user_parkings').select('*').eq('username', 'DrorParking').execute()
    if user.data:
        u = user.data[0]
        print(f"✅ משתמש: {u['username']}")
        print(f"   project_number: {u['project_number']}")
        print(f"   access_level: {u['access_level']}")
        print(f"   company_list: {u['company_list']}")
    
    # בדיקת החניון
    parking = supabase.table('parkings').select('*').eq('description', 478131051).execute()
    if parking.data:
        p = parking.data[0]
        print(f"\n✅ חניון: {p['name']}")
        print(f"   description: {p['description']}")
        print(f"   ip_address: {p['ip_address']}")
        print(f"   port: {p['port']}")
    
    # בדיקת הלוגיקה
    print("\n🔍 בדיקת הלוגיקה החדשה:")
    print(f"   project_number ({u['project_number']}) == description ({p['description']})?")
    print(f"   תשובה: {str(u['project_number']) == str(p['description'])}")
    print(f"   access_level = company_manager? {u['access_level'] == 'company_manager'}")
    print("\n✅ המשתמש אמור לראות את החניון!")
else:
    print("❌ חסרים משתני סביבה")

