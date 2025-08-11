
# ========== API למנהל חברה - חניונים ומנויים ==========

@app.route('/api/company-manager/get-parkings', methods=['GET'])
def company_manager_get_parkings():
    """קבלת רשימת חניונים עבור מנהל חברה"""
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
        company_list = user_data.get('company_list', '')
        permissions = user_data.get('permissions', '')
        
        # בדיקת הרשאות
        if 'R' not in permissions and 'P' not in permissions:
            return jsonify({'success': False, 'message': 'אין הרשאת דוחות'}), 403
        
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
                    except:
                        pass
                else:
                    try:
                        allowed_companies.append(int(part))
                    except:
                        pass
        
        # חיפוש חניונים בטבלת parkings
        parkings_result = supabase.table('parkings').select(
            'id, name, location, description, ip_address, port, is_active'
        ).execute()
        
        parkings = []
        for parking in parkings_result.data:
            # בדיקה אם החניון ברשימת החברות המורשות
            try:
                parking_number = int(parking.get('description', 0))
                if not allowed_companies or parking_number in allowed_companies:
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
            except:
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


@app.route('/api/company-manager/get-subscribers', methods=['GET'])
def company_manager_get_subscribers():
    """קבלת רשימת מנויים מחניון ספציפי"""
    try:
        if 'user_email' not in session:
            return jsonify({'success': False, 'message': 'לא מחובר'}), 401
        
        parking_id = request.args.get('parking_id')
        if not parking_id:
            return jsonify({'success': False, 'message': 'חסר מזהה חניון'}), 400
        
        # קבלת נתוני המשתמש
        user_permissions = session.get('user_permissions', '')
        company_list = session.get('user_company_list', '')
        
        # בדיקת הרשאות
        if 'R' not in user_permissions and 'P' not in user_permissions:
            return jsonify({'success': False, 'message': 'אין הרשאת דוחות'}), 403
        
        # קבלת נתוני החניון כולל IP ופורט
        parking_result = supabase.table('parkings').select(
            'name, ip_address, port, description'
        ).eq('id', parking_id).execute()
        
        if not parking_result.data:
            return jsonify({'success': False, 'message': 'חניון לא נמצא'}), 404
        
        parking_data = parking_result.data[0]
        
        # בדיקה אם החניון ברשימת החברות המורשות
        if company_list:
            allowed_companies = []
            parts = company_list.split(',')
            for part in parts:
                part = part.strip()
                if '-' in part:
                    try:
                        start, end = part.split('-')
                        allowed_companies.extend(range(int(start), int(end) + 1))
                    except:
                        pass
                else:
                    try:
                        allowed_companies.append(int(part))
                    except:
                        pass
            
            try:
                parking_number = int(parking_data.get('description', 0))
                if allowed_companies and parking_number not in allowed_companies:
                    return jsonify({'success': False, 'message': 'אין הרשאה לחניון זה'}), 403
            except:
                pass
        
        # יצירת URL לקריאה לשרת החניון
        ip_address = parking_data.get('ip_address')
        port = parking_data.get('port', 443)
        
        if not ip_address:
            return jsonify({'success': False, 'message': 'חסרים נתוני חיבור לחניון'}), 500
        
        # כאן צריך לבצע קריאה לשרת החניון
        # לעת עתה מחזירים דוגמה
        return jsonify({
            'success': True,
            'parking_name': parking_data['name'],
            'parking_api_url': f"https://{ip_address}:{port}",
            'subscribers': [],  # יתמלא מהקריאה לשרת החניון
            'message': 'נדרש חיבור לשרת החניון'
        })
        
    except Exception as e:
        print(f"❌ Error getting subscribers: {str(e)}")
        return jsonify({'success': False, 'message': 'שגיאה בטעינת מנויים'}), 500


@app.route('/api/company-manager/proxy', methods=['POST'])
def company_manager_proxy():
    """Proxy לקריאות API לשרתי החניונים"""
    try:
        if 'user_email' not in session:
            return jsonify({'success': False, 'message': 'לא מחובר'}), 401
        
        data = request.get_json()
        parking_id = data.get('parking_id')
        endpoint = data.get('endpoint')
        method = data.get('method', 'GET')
        payload = data.get('payload', {})
        
        if not parking_id or not endpoint:
            return jsonify({'success': False, 'message': 'חסרים פרמטרים'}), 400
        
        # קבלת נתוני החניון
        parking_result = supabase.table('parkings').select(
            'ip_address, port, description'
        ).eq('id', parking_id).execute()
        
        if not parking_result.data:
            return jsonify({'success': False, 'message': 'חניון לא נמצא'}), 404
        
        parking_data = parking_result.data[0]
        ip_address = parking_data.get('ip_address')
        port = parking_data.get('port', 443)
        
        if not ip_address:
            return jsonify({'success': False, 'message': 'חסרים נתוני חיבור'}), 500
        
        # בניית URL
        protocol = "https" if port == 443 or port == 8443 else "http"
        url = f"{protocol}://{ip_address}:{port}/api/{endpoint}"
        
        # ביצוע הקריאה
        headers = {'Content-Type': 'application/json'}
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, verify=False, timeout=10)
            elif method == 'POST':
                response = requests.post(url, json=payload, headers=headers, verify=False, timeout=10)
            elif method == 'PUT':
                response = requests.put(url, json=payload, headers=headers, verify=False, timeout=10)
            elif method == 'DELETE':
                response = requests.delete(url, headers=headers, verify=False, timeout=10)
            else:
                return jsonify({'success': False, 'message': 'שיטה לא נתמכת'}), 400
            
            # החזרת התוצאה
            if response.status_code == 200:
                return jsonify({
                    'success': True,
                    'data': response.json() if response.text else {}
                })
            else:
                return jsonify({
                    'success': False,
                    'message': f'שגיאה בקריאה לשרת החניון: {response.status_code}'
                }), response.status_code
                
        except requests.exceptions.Timeout:
            return jsonify({'success': False, 'message': 'זמן ההמתנה לשרת החניון פג'}), 504
        except requests.exceptions.ConnectionError:
            return jsonify({'success': False, 'message': 'לא ניתן להתחבר לשרת החניון'}), 503
        except Exception as e:
            print(f"❌ Proxy error: {str(e)}")
            return jsonify({'success': False, 'message': 'שגיאה בחיבור לשרת החניון'}), 500
            
    except Exception as e:
        print(f"❌ Company manager proxy error: {str(e)}")
        return jsonify({'success': False, 'message': 'שגיאה כללית'}), 500
