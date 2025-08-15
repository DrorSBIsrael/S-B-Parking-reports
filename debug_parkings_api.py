"""
סקריפט דיבאג מפורט לבעיית החניונים
=====================================
"""

import os
import sys

# הוספת לוג מפורט ל-API
debug_code = """
@app.route('/api/company-manager/get-parkings', methods=['GET'])
def company_manager_get_parkings():
    \"\"\"קבלת רשימת חניונים עבור מנהל חברה - עם דיבאג מפורט\"\"\"
    try:
        print("\\n" + "="*60)
        print("🔍 DEBUG: Starting get-parkings API")
        print("="*60)
        
        if 'user_email' not in session:
            print("❌ No user in session")
            return jsonify({'success': False, 'message': 'לא מחובר'}), 401
        
        print(f"✅ User email: {session['user_email']}")
        
        # קבלת נתוני המשתמש
        user_result = supabase.table('user_parkings').select(
            'project_number, company_list, access_level, permissions'
        ).eq('email', session['user_email']).execute()
        
        if not user_result.data:
            print("❌ User not found in database")
            return jsonify({'success': False, 'message': 'משתמש לא נמצא'}), 404
        
        user_data = user_result.data[0]
        company_list = user_data.get('company_list', '')
        permissions = user_data.get('permissions', '')
        
        print(f"📋 User data:")
        print(f"   - project_number: {user_data.get('project_number')}")
        print(f"   - company_list: {company_list}")
        print(f"   - permissions: {permissions}")
        print(f"   - access_level: {user_data.get('access_level')}")
        
        # בדיקת הרשאות
        if 'R' not in permissions and 'P' not in permissions:
            print("❌ No report permissions (R or P)")
            return jsonify({'success': False, 'message': 'אין הרשאת דוחות'}), 403
        
        print("✅ User has report permissions")
        
        # פענוח רשימת החברות
        allowed_companies = []
        if company_list:
            parts = company_list.split(',')
            for part in parts:
                part = part.strip()
                if '-' in part:
                    try:
                        start, end = part.split('-')
                        allowed_companies.extend(range(int(start), int(end) + 1))
                    except Exception as e:
                        print(f"⚠️ Error parsing range '{part}': {e}")
                else:
                    try:
                        allowed_companies.append(int(part))
                    except Exception as e:
                        print(f"⚠️ Error parsing number '{part}': {e}")
        
        print(f"📊 Allowed companies: {allowed_companies}")
        
        # חיפוש חניונים בטבלת parkings
        print("\\n🔍 Fetching parkings from database...")
        parkings_result = supabase.table('parkings').select(
            'id, name, location, description, ip_address, port, is_active'
        ).execute()
        
        print(f"📦 Found {len(parkings_result.data)} parkings in database")
        
        parkings = []
        for idx, parking in enumerate(parkings_result.data):
            print(f"\\n🏢 Parking #{idx + 1}:")
            print(f"   - name: {parking['name']}")
            print(f"   - description (project_number): {parking.get('description')}")
            print(f"   - ip_address: {parking.get('ip_address')}")
            print(f"   - is_active: {parking.get('is_active')}")
            
            # בדיקה אם החניון ברשימת החברות המורשות
            try:
                parking_number = int(parking.get('description', 0))
                print(f"   - parsed number: {parking_number}")
                
                # בדיקת גישה
                has_access = not allowed_companies or parking_number in allowed_companies
                print(f"   - has_access: {has_access}")
                print(f"     (checking if {parking_number} in {allowed_companies})")
                
                if has_access:
                    parkings.append({
                        'id': parking['id'],
                        'name': parking['name'],
                        'location': parking.get('location', ''),
                        'project_number': parking.get('description', ''),
                        'ip_address': parking.get('ip_address', ''),
                        'port': parking.get('port', 443),
                        'is_active': parking.get('is_active', False),
                        'api_url': f"https://{parking.get('ip_address', '')}:{parking.get('port', 443)}"
                    })
                    print(f"   ✅ Added to results")
                else:
                    print(f"   ❌ No access - skipped")
                    
            except Exception as e:
                print(f"   ⚠️ Error processing parking: {e}")
        
        print(f"\\n📊 Final results: {len(parkings)} accessible parkings")
        
        result = {
            'success': True,
            'parkings': parkings,
            'user_permissions': permissions,
            'company_list': company_list
        }
        
        print(f"\\n✅ Returning result:")
        print(f"   - success: {result['success']}")
        print(f"   - parkings count: {len(result['parkings'])}")
        print(f"   - permissions: {result['user_permissions']}")
        print(f"   - company_list: {result['company_list']}")
        print("="*60 + "\\n")
        
        return jsonify(result)
        
    except Exception as e:
        print(f"\\n❌ ERROR in get-parkings: {str(e)}")
        import traceback
        print(traceback.format_exc())
        print("="*60 + "\\n")
        return jsonify({'success': False, 'message': 'שגיאה בטעינת חניונים'}), 500
"""

print("📝 קוד הדיבאג מוכן!")
print("\nכדי להשתמש בו:")
print("1. החלף את הפונקציה company_manager_get_parkings ב-appV3.py בקוד הזה")
print("2. הפעל מחדש את השרת")
print("3. נסה להיכנס לעמוד ותראה לוגים מפורטים בקונסול")
print("\nאו:")
print("הרץ את fix_company_list.sql כדי לתקן את הבעיה ישירות!")

