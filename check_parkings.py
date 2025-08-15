#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
בדיקת החניונים בבסיס הנתונים
===========================
"""

from supabase.client import create_client
from dotenv import load_dotenv
import os

# טעינת משתני סביבה
load_dotenv()

# התחברות ל-Supabase
SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_ANON_KEY')

if not SUPABASE_URL or not SUPABASE_KEY:
    print("❌ חסרים נתוני Supabase")
    exit(1)

try:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    print("✅ מחובר ל-Supabase")
    
    # קבלת כל החניונים
    result = supabase.table('parkings').select('*').execute()
    
    if result.data:
        print(f"\n📋 נמצאו {len(result.data)} חניונים:\n")
        print("-" * 80)
        
        for parking in result.data:
            print(f"🏢 שם: {parking.get('name', 'ללא שם')}")
            print(f"   ID: {parking.get('id', '')}")
            print(f"   Project Number: {parking.get('description', '')}")
            print(f"   IP: {parking.get('ip_address', '')}:{parking.get('port', '')}")
            print(f"   מיקום: {parking.get('location', '')}")
            print(f"   פעיל: {'✅' if parking.get('is_active') else '❌'}")
            print("-" * 80)
    else:
        print("❌ לא נמצאו חניונים")
        
except Exception as e:
    print(f"❌ שגיאה: {e}")

