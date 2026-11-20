#!/usr/bin/env python3
"""
S&B Parking - Database Backup Script
תואם ל-supabase 1.2.0
"""

import os
import json
import csv
from datetime import datetime
try:
    from supabase import create_client
except ImportError:
    from supabase.client import create_client
import zipfile

def backup_supabase():
    """פונקציה לגיבוי Supabase - תואם לכל הגרסאות"""
    
    print("🚀 Starting S&B Parking database backup...")
    
    # הגדרות Supabase
    SUPABASE_URL = os.environ.get('SUPABASE_URL')
    SUPABASE_KEY = os.environ.get('SUPABASE_KEY')
    
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("❌ Missing Supabase credentials")
        return False
    
    try:
        # חיבור ל-Supabase
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        print("✅ Connected to Supabase")
        
        # יצירת תיקיית גיבויים
        today = datetime.now().strftime('%Y-%m-%d_%H-%M')
        backup_dir = f"backups/{today}"
        os.makedirs(backup_dir, exist_ok=True)
        
        # רשימת הטבלאות
        tables = [
            'csv_field_mapping',
            'csv_import_shekels', 
            'debug_logs',
            'file_uploads',
            'parking_data',
            'parkings',
            'project_parking_mapping',
            'user_parkings',
            'users',
            'whatsapp_codes'
        ]
        
        successful_backups = []
        failed_backups = []
        total_records = 0
        
        # גיבוי כל טבלה
        for table_name in tables:
            try:
                print(f"🔄 Backing up {table_name}...")
                
                # שליפת הנתונים - תואם לכל הגרסאות
                response = supabase.table(table_name).select("*").execute()
                
                # טיפול בתגובה לפי הגרסה
                if hasattr(response, 'data'):
                    result_data = response.data
                elif hasattr(response, 'content'):
                    result_data = response.content
                else:
                    result_data = response
                
                if not isinstance(result_data, list):
                    print(f"⚠️ {table_name}: Unexpected response format")
                    continue
                
                record_count = len(result_data)
                total_records += record_count
                
                # שמירה כJSON
                json_file = f"{backup_dir}/{table_name}.json"
                with open(json_file, 'w', encoding='utf-8') as f:
                    json.dump(result_data, f, ensure_ascii=False, indent=2, default=str)
                
                # שמירה כCSV (אם יש נתונים)
                if result_data and len(result_data) > 0:
                    csv_file = f"{backup_dir}/{table_name}.csv"
                    with open(csv_file, 'w', newline='', encoding='utf-8') as f:
                        # שימוש בכל המפתחות מכל השורות
                        all_keys = set()
                        for row in result_data:
                            if isinstance(row, dict):
                                all_keys.update(row.keys())
                        
                        if all_keys:
                            writer = csv.DictWriter(f, fieldnames=list(all_keys))
                            writer.writeheader()
                            for row in result_data:
                                if isinstance(row, dict):
                                    writer.writerow(row)
                
                successful_backups.append({
                    'table': table_name,
                    'records': record_count
                })
                print(f"✅ {table_name}: {record_count} records")
                
            except Exception as e:
                failed_backups.append({
                    'table': table_name,
                    'error': str(e)
                })
                print(f"❌ {table_name}: {str(e)}")
        
        # יצירת דוח גיבוי
        report_file = f"{backup_dir}/backup_report.json"
        backup_report = {
            'timestamp': datetime.now().isoformat(),
            'total_tables': len(tables),
            'successful_backups': len(successful_backups),
            'failed_backups': len(failed_backups),
            'total_records': total_records,
            'successful_tables': successful_backups,
            'failed_tables': failed_backups
        }
        
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(backup_report, f, ensure_ascii=False, indent=2)
        
        # יצירת קובץ README
        readme_file = f"{backup_dir}/README.md"
        with open(readme_file, 'w', encoding='utf-8') as f:
            f.write(f"""# S&B Parking Database Backup
            
**תאריך גיבוי:** {datetime.now().strftime('%d/%m/%Y %H:%M')}
**סה"כ רשומות:** {total_records:,}

## טבלאות שגובו בהצלחה:
""")
            for backup in successful_backups:
                f.write(f"- **{backup['table']}**: {backup['records']:,} רשומות\n")
            
            if failed_backups:
                f.write(f"\n## שגיאות:\n")
                for failure in failed_backups:
                    f.write(f"- **{failure['table']}**: {failure['error']}\n")
        
        # יצירת ZIP
        try:
            zip_file = f"backups/sb_parking_backup_{today}.zip"
            with zipfile.ZipFile(zip_file, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for root, dirs, files in os.walk(backup_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, backup_dir)
                        zipf.write(file_path, arcname)
            
            print(f"📦 Created ZIP: {zip_file}")
            
        except Exception as e:
            print(f"⚠️ ZIP creation failed: {str(e)}")
        
        # סיכום
        print(f"\n🎉 S&B Parking Backup Summary:")
        print(f"✅ Tables backed up: {len(successful_backups)}/{len(tables)}")
        print(f"📊 Total records: {total_records:,}")
        print(f"📁 Backup location: {backup_dir}")
        
        if failed_backups:
            print(f"❌ Failed tables: {len(failed_backups)}")
            for failure in failed_backups:
                print(f"  - {failure['table']}: {failure['error']}")
        
        return len(successful_backups) > 0
        
    except Exception as e:
        print(f"❌ General backup error: {str(e)}")
        return False

if __name__ == "__main__":
    print("=" * 50)
    print("🏢 S&B Parking - Database Backup")
    print("=" * 50)
    
    success = backup_supabase()
    
    if success:
        print("\n✅ Backup completed successfully!")
    else:
        print("\n❌ Backup failed!")
    
    exit(0 if success else 1)
