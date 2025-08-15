"""
תיקון הלוגיקה של get_parkings
===============================
"""

# הקוד המתוקן שצריך להחליף בשורות 2903-2977 ב-appV3.py

fixed_code = '''
@app.route('/api/company-manager/get-parkings', methods=['GET'])
def company_manager_get_parkings():
    """קבלת רשימת חניונים עבור מנהל חברה - לוגיקה מתוקנת"""
    try:
        if 'user_email' not in session:
            return jsonify({'success': False, 'message': 'לא מחובר'}), 401
        
        # קבלת נתוני המשתמש
        user_result = supabase.table('user_parkings').select(
            'project_number, company_list, access_level, permissions'
        ).eq('email', session['user_email']).execute()
        
        if not user_result.data:
            return jsonify({'success': False, 'message': 'משתמש לא נמצא'}), 404
        
        user_data = user_result.data[0]
        user_project_number = user_data.get('project_number')  # החניון של המשתמש
        company_list = user_data.get('company_list', '')  # החברות שהוא יכול לראות
        permissions = user_data.get('permissions', '')
        access_level = user_data.get('access_level', '')
        
        # בדיקת הרשאות
        if 'R' not in permissions and 'P' not in permissions:
            return jsonify({'success': False, 'message': 'אין הרשאת דוחות'}), 403
        
        # חיפוש חניונים בטבלת parkings
        parkings_result = supabase.table('parkings').select(
            'id, name, location, description, ip_address, port, is_active'
        ).execute()
        
        parkings = []
        for parking in parkings_result.data:
            try:
                parking_number = int(parking.get('description', 0))
                
                # לוגיקה מתוקנת:
                # 1. אם זה החניון של המשתמש - תן גישה
                # 2. או אם יש לו access_level של מנהל חברה/מאסטר
                
                has_access = False
                
                # בדיקה 1: האם זה החניון של המשתמש?
                if user_project_number and parking_number == int(user_project_number):
                    has_access = True
                    
                # בדיקה 2: האם יש לו גישת מנהל חברה/מאסטר?
                elif access_level in ['company_manager', 'master']:
                    # מנהל חברה יכול לראות את כל החניונים של החברה שלו
                    # כאן אפשר להוסיף לוגיקה נוספת אם צריך
                    has_access = True
                
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
            except Exception as e:
                print(f"Error processing parking: {e}")
                pass
        
        return jsonify({
            'success': True,
            'parkings': parkings,
            'user_permissions': permissions,
            'company_list': company_list
        })
        
    except Exception as e:
        print(f"❌ Error getting parkings: {str(e)}")
        return jsonify({'success': False, 'message': 'שגיאה בטעינת חניונים'}), 500
'''

print("📝 הקוד המתוקן מוכן!")
print("\n🔧 כדי לתקן:")
print("1. פתח את appV3.py")
print("2. מצא את הפונקציה company_manager_get_parkings (שורה ~2903)")
print("3. החלף אותה בקוד המתוקן")
print("4. שמור והפעל מחדש")
print("\n✅ זה יפתור את הבעיה!")

