# הוסף את השורות האלה בלבד לתחילת הקובץ שלך (אחרי ה-imports הקיימים):

try:
    import imaplib
    import email
    import csv
    import io
    import threading
    import time
    import schedule
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    import smtplib
    EMAIL_MONITORING_AVAILABLE = True
    print("✅ Email monitoring libraries loaded successfully")
except ImportError as e:
    EMAIL_MONITORING_AVAILABLE = False
    print(f"⚠️ Email monitoring not available: {e}")

# הוסף אחרי ההגדרות הקיימות:
if EMAIL_MONITORING_AVAILABLE:
    EMAIL_CHECK_INTERVAL = 5  # בדיקה כל 5 דקות
    PROCESSED_EMAILS_LIMIT = 100  # מקסימום מיילים לזכור
    processed_email_ids = []  # רשימה לזכור מיילים שכבר עובדו

# הוסף את הפונקציות האלה לפני ה-routes:

def connect_to_gmail_imap():
    """התחברות ל-Gmail IMAP"""
    if not EMAIL_MONITORING_AVAILABLE:
        return None
        
    try:
        mail = imaplib.IMAP4_SSL('imap.gmail.com')
        
        gmail_user = os.environ.get('GMAIL_USERNAME')
        gmail_password = os.environ.get('GMAIL_APP_PASSWORD')
        
        if not gmail_user or not gmail_password:
            print("❌ Missing Gmail credentials in environment variables")
            return None
            
        mail.login(gmail_user, gmail_password)
        print(f"✅ Connected to Gmail: {gmail_user}")
        
        return mail
        
    except Exception as e:
        print(f"❌ Gmail IMAP connection failed: {str(e)}")
        return None

def download_csv_from_email(msg):
    """הורדת קובץ CSV מהמייל"""
    csv_files = []
    
    try:
        for part in msg.walk():
            if part.get_content_disposition() == 'attachment':
                filename = part.get_filename()
                
                if filename and (filename.lower().endswith('.csv') or filename.lower().endswith('.txt')):
                    file_data = part.get_payload(decode=True)
                    
                    if file_data:
                        csv_files.append({
                            'filename': filename,
                            'data': file_data.decode('utf-8-sig', errors='ignore')
                        })
                        
                        print(f"📎 Found CSV attachment: {filename}")
        
        return csv_files
        
    except Exception as e:
        print(f"❌ Error downloading CSV: {str(e)}")
        return []

def parse_csv_content(csv_content):
    """פרסור תוכן CSV"""
    try:
        csv_reader = csv.DictReader(io.StringIO(csv_content))
        rows = list(csv_reader)
        
        print(f"📊 CSV parsed: {len(rows)} rows")
        
        if len(rows) > 0:
            columns = list(rows[0].keys())
            print(f"📊 Columns found: {columns}")
        
        required_columns = ['ProjectNumber', 'TTCRET', 'SCASH', 'SCREDIT']
        
        if len(rows) > 0:
            missing_columns = [col for col in required_columns if col not in rows[0]]
            
            if missing_columns:
                print(f"⚠️ Missing required columns: {missing_columns}")
                return None
        
        return rows
        
    except Exception as e:
        print(f"❌ CSV parsing error: {str(e)}")
        return None

def convert_to_csv_import_format(csv_rows):
    """המרה לפורמט מסד הנתונים"""
    converted_rows = []
    
    for index, row in enumerate(csv_rows):
        try:
            # המרת תאריך
            date_str = str(row.get('TTCRET', '')).strip()
            if '/' in date_str:
                parts = date_str.split('/')
                if len(parts) == 3:
                    day, month, year = parts
                    formatted_date = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
                else:
                    formatted_date = date_str
            else:
                formatted_date = date_str
                
            def safe_int(value, default=0):
                try:
                    if value is None or value == '':
                        return default
                    return int(float(str(value)))
                except (ValueError, TypeError):
                    return default
            
            cash_agorot = safe_int(row.get('SCASH'))
            credit_agorot = safe_int(row.get('SCREDIT'))
            pango_agorot = safe_int(row.get('SPANGO'))
            celo_agorot = safe_int(row.get('SCELO'))
            
            cash_shekels = round(cash_agorot / 100, 2)
            credit_shekels = round(credit_agorot / 100, 2)
            pango_shekels = round(pango_agorot / 100, 2)
            celo_shekels = round(celo_agorot / 100, 2)
            
            converted_row = {
                'project_number': str(row.get('ProjectNumber', '')),
                'l_global_ref': safe_int(row.get('LGLOBALREF')),
                's_computer': safe_int(row.get('SCOMPUTER')),
                's_shift_id': safe_int(row.get('SSHIFTID')),
                'report_start_time': str(row.get('TTCRET', '')),
                'report_end_time': str(row.get('TTENDT', '')),
                'report_date': formatted_date,
                'ctext': str(row.get('CTEXT', '')),
                
                # כסף בשקלים
                's_cash_shekels': cash_shekels,
                's_credit_shekels': credit_shekels,
                's_pango_shekels': pango_shekels,
                's_celo_shekels': celo_shekels,
                'total_revenue_shekels': cash_shekels + credit_shekels + pango_shekels + celo_shekels,
                'net_revenue_shekels': cash_shekels + credit_shekels + pango_shekels + celo_shekels,
                
                # כסף באגורות
                's_cash_agorot': cash_agorot,
                's_credit_agorot': credit_agorot,
                's_pango_agorot': pango_agorot,
                's_celo_agorot': celo_agorot,
                'stot_cacr': safe_int(row.get('STOTCACR')),
                's_exp_agorot': safe_int(row.get('SEXP')),
                
                # מקודדים
                's_encoder1': safe_int(row.get('SENCODER1')),
                's_encoder2': safe_int(row.get('SENCODER2')),
                's_encoder3': safe_int(row.get('SENCODER3')),
                'sencodertot': safe_int(row.get('SENCODERTOT')),
                
                # תנועה
                't_open_b': safe_int(row.get('TOPENB')),
                't_entry_s': safe_int(row.get('TENTRYS')),
                't_entry_p': safe_int(row.get('TENTRYP')),
                't_entry_tot': safe_int(row.get('TENTRYTOT')),
                't_exit_s': safe_int(row.get('TEEITS')),
                't_exit_p': safe_int(row.get('TEEITP')),
                't_exit_tot': safe_int(row.get('TEEITTOT')),
                't_entry_ap': safe_int(row.get('TENTRYAP')),
                't_exit_ap': safe_int(row.get('TEEITAP')),
                
                # זמני שהייה
                'tsper1': safe_int(row.get('TSPER1')),
                'tsper2': safe_int(row.get('TSPER2')),
                'stay_015': safe_int(row.get('STAY015')),
                'stay_030': safe_int(row.get('STAY030')),
                'stay_045': safe_int(row.get('STAY045')),
                'stay_060': safe_int(row.get('STAY060')),
                'stay_2': safe_int(row.get('STAY2')),
                'stay_3': safe_int(row.get('STAY3')),
                'stay_4': safe_int(row.get('STAY4')),
                'stay_5': safe_int(row.get('STAY5')),
                'stay_6': safe_int(row.get('STAY6')),
                'stay_724': safe_int(row.get('STAY724')),
                'tsper3': safe_int(row.get('TSPER3')),
                'tsper4': safe_int(row.get('TSPER4')),
                'tsper5': safe_int(row.get('TSPER5')),
                'tsper6': safe_int(row.get('TSPER6')),
                
                # מטא-דטה
                'created_at': datetime.now().isoformat(),
                'uploaded_by': 'email_automation'
            }
            
            converted_rows.append(converted_row)
            
        except Exception as e:
            print(f"❌ Error converting row {index}: {str(e)}")
            continue
    
    return converted_rows

def insert_to_csv_import_shekels(converted_data):
    """הכנסה לטבלת csv_import_shekels"""
    if not supabase:
        print("❌ Supabase not available")
        return 0
        
    try:
        supabase.table('csv_import_shekels').delete().neq('id', 0).execute()
        
        batch_size = 500
        total_inserted = 0
        
        for i in range(0, len(converted_data), batch_size):
            batch = converted_data[i:i + batch_size]
            
            result = supabase.table('csv_import_shekels').insert(batch).execute()
            
            if result.data:
                total_inserted += len(result.data)
                print(f"✅ Inserted to csv_import_shekels: batch {i//batch_size + 1}, {len(result.data)} rows")
        
        print(f"✅ Total inserted to csv_import_shekels: {total_inserted} rows")
        return total_inserted
        
    except Exception as e:
        print(f"❌ Error inserting to csv_import_shekels: {str(e)}")
        return 0

def transfer_to_parking_data():
    """העברה מ csv_import_shekels ל parking_data"""
    if not supabase:
        print("❌ Supabase not available")
        return 0
        
    try:
        csv_data = supabase.table('csv_import_shekels').select('*').execute()
        
        if not csv_data.data:
            print("⚠️ No data in csv_import_shekels to transfer")
            return 0
        
        result = supabase.table('parking_data').insert(csv_data.data).execute()
        
        if result.data:
            transferred_count = len(result.data)
            print(f"✅ Transferred {transferred_count} rows to parking_data")
            
            supabase.table('csv_import_shekels').delete().neq('id', 0).execute()
            print("🧹 Cleaned csv_import_shekels table")
            
            return transferred_count
        else:
            print("❌ Failed to transfer data to parking_data")
            return 0
            
    except Exception as e:
        print(f"❌ Error transferring to parking_data: {str(e)}")
        return 0

def send_success_notification(sender_email, processed_files, total_rows):
    """שליחת התראת הצלחה"""
    if not EMAIL_MONITORING_AVAILABLE:
        return
        
    try:
        msg = MIMEMultipart()
        msg['From'] = os.environ.get('GMAIL_USERNAME')
        msg['To'] = sender_email
        msg['Subject'] = '✅ קבצי הנתונים עובדו בהצלחה - S&B Parking'
        
        files_list = '\n'.join([f"• {file['name']} - {file['rows']} שורות" for file in processed_files])
        
        body = f"""
שלום,

קבצי הנתונים שלך עובדו בהצלחה במערכת S&B Parking:

{files_list}

סה"כ שורות שנוספו: {total_rows}

הנתונים זמינים כעת בדשבורד.

תודה,
מערכת S&B Parking (אוטומטית)
        """
        
        msg.attach(MIMEText(body, 'plain', 'utf-8'))
        
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(os.environ.get('GMAIL_USERNAME'), os.environ.get('GMAIL_APP_PASSWORD'))
        server.send_message(msg)
        server.quit()
        
        print(f"📧 Success notification sent to {sender_email}")
        
    except Exception as e:
        print(f"❌ Failed to send notification: {str(e)}")

def send_error_notification(sender_email, error_message):
    """שליחת התראת שגיאה"""
    if not EMAIL_MONITORING_AVAILABLE:
        return
        
    try:
        msg = MIMEMultipart()
        msg['From'] = os.environ.get('GMAIL_USERNAME')
        msg['To'] = sender_email
        msg['Subject'] = '❌ שגיאה בעיבוד קבצי הנתונים - S&B Parking'
        
        body = f"""
שלום,

התרחשה שגיאה בעיבוד קבצי הנתונים שלך:

{error_message}

אנא בדוק את הקובץ ונסה שוב, או פנה לתמיכה.

מערכת S&B Parking (אוטומטית)
        """
        
        msg.attach(MIMEText(body, 'plain', 'utf-8'))
        
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(os.environ.get('GMAIL_USERNAME'), os.environ.get('GMAIL_APP_PASSWORD'))
        server.send_message(msg)
        server.quit()
        
        print(f"📧 Error notification sent to {sender_email}")
        
    except Exception as e:
        print(f"❌ Failed to send error notification: {str(e)}")

def process_single_email(mail, email_id):
    """עיבוד מייל יחיד"""
    try:
        _, msg_data = mail.fetch(email_id, '(RFC822)')
        email_body = msg_data[0][1]
        email_message = email.message_from_bytes(email_body)
        
        sender = email_message['From']
        subject = email_message['Subject'] or ''
        date = email_message['Date'] or ''
        
        print(f"\n📧 Processing email from: {sender}")
        print(f"   Subject: {subject}")
        print(f"   Date: {date}")
        
        csv_files = download_csv_from_email(email_message)
        
        if not csv_files:
            print("⚠️ No CSV files found in email")
            return False
        
        all_converted_data = []
        processed_files = []
        
        for csv_file in csv_files:
            print(f"\n🔄 Processing file: {csv_file['filename']}")
            
            csv_rows = parse_csv_content(csv_file['data'])
            if csv_rows is None:
                continue
            
            converted_data = convert_to_csv_import_format(csv_rows)
            if not converted_data:
                continue
            
            all_converted_data.extend(converted_data)
            processed_files.append({
                'name': csv_file['filename'],
                'rows': len(converted_data)
            })
            
            print(f"✅ File {csv_file['filename']}: {len(converted_data)} rows converted")
        
        if not all_converted_data:
            error_msg = "לא נמצאו נתונים תקינים בקבצים המצורפים"
            send_error_notification(sender, error_msg)
            return False
        
        inserted_count = insert_to_csv_import_shekels(all_converted_data)
        if inserted_count == 0:
            error_msg = "שגיאה בהכנסת הנתונים לטבלת הביניים"
            send_error_notification(sender, error_msg)
            return False
        
        transferred_count = transfer_to_parking_data()
        if transferred_count == 0:
            error_msg = "שגיאה בהעברת הנתונים לטבלה הסופית"
            send_error_notification(sender, error_msg)
            return False
        
        send_success_notification(sender, processed_files, transferred_count)
        
        print(f"🎉 Email processed successfully: {transferred_count} rows added")
        return True
        
    except Exception as e:
        print(f"❌ Error processing email: {str(e)}")
        try:
            sender = email_message['From'] if 'email_message' in locals() else 'unknown'
            send_error_notification(sender, f"שגיאה טכנית: {str(e)}")
        except:
            pass
        return False

def verify_email_system():
    """בדיקת התקינות של מערכת המיילים"""
    if not EMAIL_MONITORING_AVAILABLE:
        print("⚠️ Email libraries not available - email monitoring disabled")
        return False
        
    print("🔧 Verifying email system configuration...")
    
    gmail_user = os.environ.get('GMAIL_USERNAME')
    gmail_password = os.environ.get('GMAIL_APP_PASSWORD')
    
    print(f"📧 Gmail Username: {'✅ SET' if gmail_user else '❌ MISSING'}")
    print(f"🔑 Gmail Password: {'✅ SET' if gmail_password else '❌ MISSING'}")
    
    if not gmail_user or not gmail_password:
        print("⚠️ WARNING: Gmail credentials missing! Email monitoring will not work.")
        return False
    
    try:
        mail = imaplib.IMAP4_SSL('imap.gmail.com', timeout=10)
        mail.login(gmail_user, gmail_password)
        mail.logout()
        print("🌐 Gmail IMAP connection: ✅ SUCCESS")
        return True
    except Exception as e:
        print(f"❌ Gmail IMAP connection failed: {str(e)}")
        return False

def check_for_new_emails():
    """בדיקת מיילים חדשים"""
    global processed_email_ids
    
    if not EMAIL_MONITORING_AVAILABLE:
        print("⚠️ Email check skipped - libraries not available")
        return
    
    print(f"\n🔍 ===== EMAIL CHECK STARTED at {datetime.now()} =====")
    
    gmail_user = os.environ.get('GMAIL_USERNAME')
    gmail_password = os.environ.get('GMAIL_APP_PASSWORD')
    
    if not gmail_user or not gmail_password:
        print("❌ Missing Gmail credentials - skipping email check")
        return
    
    print(f"📧 Gmail user: {gmail_user}")
    print(f"🔑 Gmail password: {'***' if gmail_password else 'MISSING'}")
    
    mail = connect_to_gmail_imap()
    if not mail:
        print("❌ Failed to connect to Gmail IMAP")
        return
    
    try:
        print("📂 Selecting inbox...")
        mail.select('inbox')
        
        since_date = (datetime.now() - timedelta(days=1)).strftime('%d-%b-%Y')
        search_criteria = f'(SINCE "{since_date}" SUBJECT "parking" OR SUBJECT "report" OR SUBJECT "data")'
        
        print(f"🔍 Search criteria: {search_criteria}")
        
        _, message_ids = mail.search(None, search_criteria)
        
        if not message_ids[0]:
            print("📭 No relevant emails found")
            print(f"📊 Processed emails cache: {len(processed_email_ids)} emails")
            mail.logout()
            return
        
        email_ids = message_ids[0].split()
        print(f"📧 Found {len(email_ids)} relevant emails")
        
        new_emails = 0
        
        for email_id in email_ids:
            email_id_str = email_id.decode()
            
            if email_id_str in processed_email_ids:
                print(f"⏭️ Skipping already processed email: {email_id_str}")
                continue
            
            print(f"\n🆕 Processing new email ID: {email_id_str}")
            
            success = process_single_email(mail, email_id)
            
            processed_email_ids.append(email_id_str)
            new_emails += 1
            
            if len(processed_email_ids) > PROCESSED_EMAILS_LIMIT:
                processed_email_ids = processed_email_ids[-PROCESSED_EMAILS_LIMIT:]
                print(f"🧹 Cleaned processed emails cache, now: {len(processed_email_ids)}")
            
            time.sleep(2)
        
        print(f"✅ Email check completed: {new_emails} new emails processed")
        print(f"📊 Total emails in cache: {len(processed_email_ids)}")
        
    except Exception as e:
        print(f"❌ Error in email check: {str(e)}")
    
    finally:
        try:
            mail.logout()
            print("🔓 Gmail connection closed")
        except:
            pass
        
        print(f"===== EMAIL CHECK ENDED at {datetime.now()} =====\n")

def start_email_monitoring_with_logs():
    """הפעלת מעקב מיילים עם לוגים"""
    if not EMAIL_MONITORING_AVAILABLE:
        print("⚠️ Email monitoring not available - libraries missing")
        return
        
    try:
        print("🚀 Starting email monitoring system...")
        
        if not verify_email_system():
            print("❌ Email system verification failed. Monitoring will not start.")
            return
        
        def scheduled_check():
            with app.app_context():
                print(f"⏰ Scheduled email check triggered at {datetime.now()}")
                check_for_new_emails()
        
        schedule.every(EMAIL_CHECK_INTERVAL).minutes.do(scheduled_check)
        print(f"⏰ Email checks scheduled every {EMAIL_CHECK_INTERVAL} minutes")
        
        def monitoring_loop():
            print("🔄 Email monitoring loop started")
            check_count = 0
            
            while True:
                try:
                    schedule.run_pending()
                    time.sleep(60)
                    
                    check_count += 1
                    if check_count % 5 == 0:
                        print(f"💓 Email monitoring alive - {check_count} minutes running")
                        
                except KeyboardInterrupt:
                    print("\n🛑 Email monitoring stopped by user")
                    break
                except Exception as e:
                    print(f"❌ Email monitoring error: {str(e)}")
                    print("⏳ Retrying in 5 minutes...")
                    time.sleep(300)
        
        monitor_thread = threading.Thread(target=monitoring_loop, daemon=True)
        monitor_thread.start()
        
        print("✅ Email monitoring started successfully in background")
        
        print("🚀 Running initial email check...")
        
        def initial_check():
            with app.app_context():
                check_for_new_emails()
        
        threading.Thread(target=initial_check, daemon=True).start()
        
    except Exception as e:
        print(f"❌ Failed to start email monitoring: {str(e)}")

def start_background_email_monitoring():
    """נקודת כניסה להפעלת מעקב מיילים ברקע"""
    if not EMAIL_MONITORING_AVAILABLE:
        print("⚠️ Email monitoring not available - libraries missing")
        return
        
    try:
        print("📧 Initializing background email monitoring...")
        
        def delayed_start():
            time.sleep(5)
            start_email_monitoring_with_logs()
        
        startup_thread = threading.Thread(target=delayed_start, daemon=True)
        startup_thread.start()
        
        print("📧 Background email monitoring initialization started")
        
    except Exception as e:
        print(f"❌ Background email monitoring initialization failed: {str(e)}")

# הוסף את ה-route החדש הזה בין ה-routes הקיימים:

@app.route('/api/test-email-system', methods=['GET'])
def test_email_system():
    """API לבדיקת מערכת המיילים"""
    try:
        if not EMAIL_MONITORING_AVAILABLE:
            return jsonify({
                'success': False, 
                'message': 'Email system not available - missing libraries'
            })
            
        print("🧪 Manual email system test initiated")
        
        system_ok = verify_email_system()
        
        if system_ok:
            def test_check():
                with app.app_context():
                    check_for_new_emails()
            
            threading.Thread(target=test_check, daemon=True).start()
            
            return jsonify({
                'success': True, 
                'message': 'Email system test completed successfully. Check server logs for details.'
            })
        else:
            return jsonify({
                'success': False, 
                'message': 'Email system test failed. Check server logs for details.'
            })
            
    except Exception as e:
        print(f"❌ Email system test error: {str(e)}")
        return jsonify({
            'success': False, 
            'message': f'Test error: {str(e)}'
        })

# עדכן את הפונקציה manual_email_check הקיימת שלך עם הקוד הזה:
# (החלף את התוכן של הפונקציה בלבד, לא את ה-@app.route)

def manual_email_check():
    """API לבדיקת מיילים ידנית"""
    try:
        if 'user_email' not in session:
            return jsonify({'success': False, 'message': 'לא מחובר'}), 401
        
        if not supabase:
            return jsonify({'success': False, 'message': 'מסד הנתונים לא זמין'})
        
        if not EMAIL_MONITORING_AVAILABLE:
            return jsonify({'success': False, 'message': 'מערכת מיילים לא זמינה'})
        
        email = session['user_email']
        user_result = supabase.table('user_parkings').select('role, access_level').eq('email', email).execute()
        
        if not user_result.data:
            return jsonify({'success': False, 'message': 'משתמש לא נמצא'})
        
        user_data = user_result.data[0]
        if user_data.get('role') != 'admin' and user_data.get('access_level') != 'group_manager':
            return jsonify({'success': False, 'message': 'אין הרשאה לבדיקת מיילים'})
        
        def test_check():
            with app.app_context():
                check_for_new_emails()
        
        threading.Thread(target=test_check, daemon=True).start()
        
        return jsonify({'success': True, 'message': 'בדיקת מיילים החלה ברקע'})
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

# עדכן את if __name__ == '__main__': לכלול את זה:

if __name__ == '__main__':
    print("\n🔧 Pre-flight email system check...")
    
    if EMAIL_MONITORING_AVAILABLE:
        email_system_ready = verify_email_system()
        
        if email_system_ready:
            print("✅ Email system ready - starting background monitoring")
            start_background_email_monitoring()
        else:
            print("⚠️ Email system not ready - monitoring disabled")
            print("💡 You can still use manual email checks via API")
    else:
        print("⚠️ Email libraries not available - monitoring disabled")
    
    print("\n🌐 Starting Flask web server...")
    
    port = int(os.environ.get('PORT', 5000))
    debug_mode = os.environ.get('FLASK_ENV') == 'development'
    
    print(f"🔍 Port: {port}")
    print(f"🔍 Debug mode: {debug_mode}")
    
    app.run(host='0.0.0.0', port=port, debug=debug_mode)
else:
    # אם זה לא הקובץ הראשי (למשל Gunicorn), הפעל את המעקב
    if EMAIL_MONITORING_AVAILABLE:
        print("📧 Initializing email monitoring for production...")
        start_background_email_monitoring()
