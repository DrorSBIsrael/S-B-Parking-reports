import os
import re
import json
import time
import random
import sqlite3
import base64
import threading
import datetime
from datetime import timezone, timedelta
import xml.etree.ElementTree as ET
import requests
import urllib3
from flask import Blueprint, render_template, request, jsonify, session, redirect

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

tenant_bp = Blueprint('tenant_bp', __name__)

# Israel Timezone helper (UTC+2 / UTC+3)
def get_il_now():
    return datetime.datetime.now()

def clean_il_phone(phone):
    if not phone:
        return ""
    digits = ''.join(filter(str.isdigit, str(phone)))
    if digits.startswith('0') and len(digits) >= 9:
        digits = '972' + digits[1:]
    elif len(digits) == 9 and digits.startswith('5'):
        digits = '972' + digits
    return digits

def display_il_phone(phone):
    digits = clean_il_phone(phone)
    if digits.startswith('972') and len(digits) == 12:
        local = '0' + digits[3:]
        return f"{local[:3]}-{local[3:]}"
    return str(phone or '')

# ============================================================================
# 1. STORAGE LAYER (Supabase Primary + Local SQLite Fallback/Mirror)
# ============================================================================
SQLITE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tenant_data.db')
_db_lock = threading.Lock()
_action_dedup_lock = threading.Lock()

def _init_sqlite():
    with _db_lock:
        conn = sqlite3.connect(SQLITE_PATH)
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tenant_building_settings (
                project_number TEXT PRIMARY KEY,
                parking_name TEXT,
                max_bookings_per_day INTEGER DEFAULT 5,
                max_bookings_per_month INTEGER DEFAULT 30,
                check_interval_minutes INTEGER DEFAULT 30,
                reminder_minutes_before INTEGER DEFAULT 30,
                logo_data TEXT,
                updated_at TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tenant_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_number TEXT NOT NULL,
                parking_name TEXT,
                full_name TEXT NOT NULL,
                phone_number TEXT NOT NULL,
                apartment_number TEXT NOT NULL,
                base_max_counter INTEGER DEFAULT 1,
                mobile_otp TEXT,
                otp_expires_at TEXT,
                is_active INTEGER DEFAULT 1,
                created_by TEXT,
                created_at TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tenant_spot_shares (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_number TEXT NOT NULL,
                owner_tenant_id INTEGER,
                owner_name TEXT,
                owner_apartment TEXT NOT NULL,
                spots_offered INTEGER DEFAULT 1,
                share_target_type TEXT DEFAULT 'POOL',
                target_apartment TEXT,
                schedule_type TEXT DEFAULT 'WEEKLY',
                days_of_week TEXT,
                specific_date TEXT,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                is_active INTEGER DEFAULT 1,
                created_at TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tenant_quota_transfers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                share_id INTEGER NOT NULL,
                slot_index INTEGER DEFAULT 1,
                project_number TEXT NOT NULL,
                from_apartment TEXT NOT NULL,
                to_apartment TEXT NOT NULL,
                borrower_tenant_id INTEGER,
                borrower_name TEXT,
                borrower_phone TEXT,
                booking_date TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                window_start TEXT NOT NULL,
                window_end TEXT NOT NULL,
                status TEXT DEFAULT 'SCHEDULED',
                actual_activated_at TEXT,
                actual_restored_at TEXT,
                last_checked_at TEXT,
                notified_start INTEGER DEFAULT 0,
                notified_ending_soon INTEGER DEFAULT 0,
                late_exit_flag INTEGER DEFAULT 0,
                created_at TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tenant_local_subscribers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_number TEXT NOT NULL,
                apartment_number TEXT NOT NULL,
                subscriber_index INTEGER DEFAULT 1,
                family_name TEXT,
                first_name TEXT,
                parking_spot TEXT,
                lpn1 TEXT,
                lpn2 TEXT,
                lpn3 TEXT,
                updated_at TEXT
            )
        """)
        for col_sql in [
            "ALTER TABLE tenant_building_settings ADD COLUMN logo_data TEXT",
            "ALTER TABLE tenant_building_settings ADD COLUMN parking_lat REAL",
            "ALTER TABLE tenant_building_settings ADD COLUMN parking_lng REAL",
            "ALTER TABLE tenant_building_settings ADD COLUMN parking_address TEXT",
            "ALTER TABLE tenant_building_settings ADD COLUMN standalone_mode INTEGER DEFAULT 0",
            "ALTER TABLE tenant_building_settings ADD COLUMN ios_app_url TEXT",
            "ALTER TABLE tenant_building_settings ADD COLUMN android_app_url TEXT",
            "ALTER TABLE tenant_spot_shares ADD COLUMN parking_spot_number TEXT",
            "ALTER TABLE tenant_quota_transfers ADD COLUMN parking_spot_number TEXT",
            "CREATE INDEX IF NOT EXISTS idx_tu_phone ON tenant_users (phone_number, is_active)",
            "CREATE INDEX IF NOT EXISTS idx_tu_proj_apt ON tenant_users (project_number, apartment_number)",
            "CREATE INDEX IF NOT EXISTS idx_tss_proj_act ON tenant_spot_shares (project_number, is_active)",
            "CREATE INDEX IF NOT EXISTS idx_tqt_proj_date ON tenant_quota_transfers (project_number, booking_date)",
            "CREATE INDEX IF NOT EXISTS idx_tqt_status ON tenant_quota_transfers (status)",
            "CREATE INDEX IF NOT EXISTS idx_tls_proj_apt ON tenant_local_subscribers (project_number, apartment_number)"
        ]:
            try:
                cur.execute(col_sql)
            except Exception:
                pass
        conn.commit()
        conn.close()

_init_sqlite()

def _get_app_module():
    import sys
    return sys.modules.get('app') or sys.modules.get('__main__')

_sb_circuit_disabled_until = 0

def _get_raw_supabase():
    """מחזיר את חיבור ה-Supabase עבור טבלאות הליבה הקיימות (user_parkings, parkings)."""
    app_mod = _get_app_module()
    return getattr(app_mod, 'supabase', None) if app_mod else None

def _get_supabase():
    """מחזיר את חיבור ה-Supabase עבור טבלאות הדיירים החדשות (עם מנגנון הגנה אם טרם הורץ ה-SQL)."""
    global _sb_circuit_disabled_until
    if time.time() < _sb_circuit_disabled_until:
        return None
    return _get_raw_supabase()

def _trip_sb_circuit_if_missing(err):
    global _sb_circuit_disabled_until
    err_s = str(err)
    if 'PGRST205' in err_s or '42P01' in err_s or 'Could not find the table' in err_s or 'getaddrinfo failed' in err_s:
        _sb_circuit_disabled_until = time.time() + 300

class TenantStore:
    """שכבת נתונים היברידית: שומרת ב-Supabase (אם הטבלאות קיימות וזמינות) ומסנכרנת מקומית ל-SQLite."""

    @staticmethod
    def get_building_settings(project_number, default_name=''):
        p_num = str(project_number)
        sb_row = None
        sb = _get_supabase()
        if sb:
            try:
                res = sb.table('tenant_building_settings').select('*').eq('project_number', p_num).execute()
                if res.data:
                    sb_row = dict(res.data[0])
            except Exception as _sbe:
                _trip_sb_circuit_if_missing(_sbe)
        local_row = None
        with _db_lock:
            conn = sqlite3.connect(SQLITE_PATH)
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM tenant_building_settings WHERE project_number = ?", (p_num,)).fetchone()
            conn.close()
            if row:
                local_row = dict(row)
        if sb_row:
            if local_row:
                for k in ('logo_data', 'parking_lat', 'parking_lng', 'parking_address', 'standalone_mode', 'ios_app_url', 'android_app_url'):
                    if sb_row.get(k) in (None, '') and local_row.get(k) not in (None, ''):
                        sb_row[k] = local_row[k]
            return sb_row
        if local_row:
            return local_row
        return {
            'project_number': p_num,
            'parking_name': default_name,
            'max_bookings_per_day': 5,
            'max_bookings_per_month': 30,
            'check_interval_minutes': 30,
            'reminder_minutes_before': 30,
            'logo_data': '',
            'parking_lat': None,
            'parking_lng': None,
            'parking_address': '',
            'standalone_mode': 0,
            'ios_app_url': '',
            'android_app_url': ''
        }

    @staticmethod
    def save_building_settings(project_number, parking_name, max_day=5, max_month=30, check_interval=30, reminder_mins=30, logo_data=None, parking_lat=None, parking_lng=None, parking_address=None, standalone_mode=None, ios_app_url=None, android_app_url=None):
        p_num = str(project_number)
        now_iso = get_il_now().isoformat()
        existing = TenantStore.get_building_settings(p_num, parking_name)
        final_logo = logo_data if logo_data is not None else (existing.get('logo_data') or '')
        final_addr = str(parking_address).strip() if parking_address is not None else (existing.get('parking_address') or '')
        final_standalone = (1 if bool(standalone_mode) else 0) if standalone_mode is not None else int(existing.get('standalone_mode') or 0)
        final_ios_url = str(ios_app_url).strip() if ios_app_url is not None else (existing.get('ios_app_url') or '')
        final_android_url = str(android_app_url).strip() if android_app_url is not None else (existing.get('android_app_url') or '')

        def _parse_coord(val, fallback):
            if val is None:
                return fallback
            s = str(val).strip()
            if not s:
                return None
            try:
                return float(s)
            except Exception:
                return fallback

        final_lat = _parse_coord(parking_lat, existing.get('parking_lat'))
        final_lng = _parse_coord(parking_lng, existing.get('parking_lng'))

        payload = {
            'project_number': p_num,
            'parking_name': parking_name or '',
            'max_bookings_per_day': int(max_day),
            'max_bookings_per_month': int(max_month),
            'check_interval_minutes': int(check_interval),
            'reminder_minutes_before': int(reminder_mins),
            'logo_data': final_logo,
            'parking_lat': final_lat,
            'parking_lng': final_lng,
            'parking_address': final_addr,
            'standalone_mode': final_standalone,
            'ios_app_url': final_ios_url,
            'android_app_url': final_android_url,
            'updated_at': now_iso
        }
        sb = _get_supabase()
        if sb:
            try:
                sb.table('tenant_building_settings').upsert(payload).execute()
            except Exception as _sbe:
                # אם העמודות החדשות טרם נוספו ב-Supabase, שמור את עמודות הבסיס כדי שלא תיכשל השמירה
                try:
                    base_payload = {k: v for k, v in payload.items() if k not in ('parking_lat', 'parking_lng', 'parking_address', 'standalone_mode', 'ios_app_url', 'android_app_url')}
                    sb.table('tenant_building_settings').upsert(base_payload).execute()
                except Exception as _sbe2:
                    _trip_sb_circuit_if_missing(_sbe2)
        with _db_lock:
            conn = sqlite3.connect(SQLITE_PATH)
            conn.execute("""
                INSERT INTO tenant_building_settings
                (project_number, parking_name, max_bookings_per_day, max_bookings_per_month, check_interval_minutes, reminder_minutes_before, logo_data, parking_lat, parking_lng, parking_address, standalone_mode, ios_app_url, android_app_url, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_number) DO UPDATE SET
                    parking_name=excluded.parking_name,
                    max_bookings_per_day=excluded.max_bookings_per_day,
                    max_bookings_per_month=excluded.max_bookings_per_month,
                    check_interval_minutes=excluded.check_interval_minutes,
                    reminder_minutes_before=excluded.reminder_minutes_before,
                    logo_data=excluded.logo_data,
                    parking_lat=excluded.parking_lat,
                    parking_lng=excluded.parking_lng,
                    parking_address=excluded.parking_address,
                    standalone_mode=excluded.standalone_mode,
                    ios_app_url=excluded.ios_app_url,
                    android_app_url=excluded.android_app_url,
                    updated_at=excluded.updated_at
            """, (p_num, payload['parking_name'], payload['max_bookings_per_day'], payload['max_bookings_per_month'],
                  payload['check_interval_minutes'], payload['reminder_minutes_before'], final_logo,
                  final_lat, final_lng, final_addr, final_standalone, final_ios_url, final_android_url, now_iso))
            conn.commit()
            conn.close()
        return payload

    @staticmethod
    def list_local_subscribers(project_number, apartment_number=None):
        p_num = str(project_number)
        sb = _get_supabase()
        if sb:
            try:
                q = sb.table('tenant_local_subscribers').select('*').eq('project_number', p_num)
                if apartment_number is not None:
                    q = q.eq('apartment_number', str(apartment_number).strip())
                res = q.order('id').execute()
                if res.data:
                    return [dict(r) for r in res.data]
            except Exception:
                pass
        with _db_lock:
            conn = sqlite3.connect(SQLITE_PATH)
            conn.row_factory = sqlite3.Row
            if apartment_number is not None:
                rows = conn.execute(
                    "SELECT * FROM tenant_local_subscribers WHERE project_number = ? AND apartment_number = ? ORDER BY subscriber_index, id",
                    (p_num, str(apartment_number).strip())
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM tenant_local_subscribers WHERE project_number = ? ORDER BY CAST(apartment_number AS INTEGER), apartment_number, subscriber_index, id",
                    (p_num,)
                ).fetchall()
            conn.close()
            return [dict(r) for r in rows]

    @staticmethod
    def upsert_local_subscribers_for_apartment(project_number, apartment_number, subs_rows):
        """מחליף/מעדכן את רשימת המנויים והרכבים המקומיים של דירה ספציפית (למתחם ללא בקר חניון)."""
        p_num = str(project_number)
        apt_str = str(apartment_number).strip()
        now_iso = get_il_now().isoformat()
        batch_payload = []
        for idx, sr in enumerate(subs_rows, start=1):
            batch_payload.append({
                'project_number': p_num,
                'apartment_number': apt_str,
                'subscriber_index': idx,
                'family_name': (sr.get('family_name') or sr.get('last_name') or '').strip(),
                'first_name': (sr.get('first_name') or '').strip(),
                'parking_spot': (sr.get('parking_spot') or sr.get('parking_spot_number') or '').strip(),
                'lpn1': (sr.get('lpn1') or sr.get('plate_1') or '').strip(),
                'lpn2': (sr.get('lpn2') or sr.get('plate_2') or '').strip(),
                'lpn3': (sr.get('lpn3') or sr.get('plate_3') or '').strip(),
                'updated_at': now_iso
            })
        sb = _get_supabase()
        if sb and batch_payload:
            try:
                sb.table('tenant_local_subscribers').delete().eq('project_number', p_num).eq('apartment_number', apt_str).execute()
                sb.table('tenant_local_subscribers').insert(batch_payload).execute()
            except Exception:
                pass
        with _db_lock:
            conn = sqlite3.connect(SQLITE_PATH)
            conn.execute("DELETE FROM tenant_local_subscribers WHERE project_number = ? AND apartment_number = ?", (p_num, apt_str))
            conn.executemany("""
                INSERT INTO tenant_local_subscribers
                (project_number, apartment_number, subscriber_index, family_name, first_name, parking_spot, lpn1, lpn2, lpn3, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                (
                    r['project_number'], r['apartment_number'], r['subscriber_index'],
                    r['family_name'], r['first_name'], r['parking_spot'],
                    r['lpn1'], r['lpn2'], r['lpn3'], r['updated_at']
                )
                for r in batch_payload
            ])
            conn.commit()
            conn.close()

    @staticmethod
    def bulk_upsert_local_subscribers_for_project(project_number, by_apt_dict):
        """שמירה מרוכזת ומהירה של כל המנויים והרכבים של הבניין בבת אחת (מונע אלפי פניות בודדות ל-DB בטעינת קובץ של 400 דיירים!)."""
        p_num = str(project_number)
        now_iso = get_il_now().isoformat()
        all_payloads = []
        apt_keys = list(by_apt_dict.keys())
        for apt_str, subs_rows in by_apt_dict.items():
            for idx, sr in enumerate(subs_rows, start=1):
                all_payloads.append({
                    'project_number': p_num,
                    'apartment_number': str(apt_str).strip(),
                    'subscriber_index': idx,
                    'family_name': (sr.get('family_name') or sr.get('last_name') or '').strip(),
                    'first_name': (sr.get('first_name') or '').strip(),
                    'parking_spot': (sr.get('parking_spot') or sr.get('parking_spot_number') or '').strip(),
                    'lpn1': (sr.get('lpn1') or sr.get('plate_1') or '').strip(),
                    'lpn2': (sr.get('lpn2') or sr.get('plate_2') or '').strip(),
                    'lpn3': (sr.get('lpn3') or sr.get('plate_3') or '').strip(),
                    'updated_at': now_iso
                })
        sb = _get_supabase()
        if sb and all_payloads:
            try:
                sb.table('tenant_local_subscribers').delete().eq('project_number', p_num).in_('apartment_number', apt_keys).execute()
                # Insert in chunks of 200 for Supabase safety
                for i in range(0, len(all_payloads), 200):
                    sb.table('tenant_local_subscribers').insert(all_payloads[i:i+200]).execute()
            except Exception:
                pass
        with _db_lock:
            conn = sqlite3.connect(SQLITE_PATH)
            for ak in apt_keys:
                conn.execute("DELETE FROM tenant_local_subscribers WHERE project_number = ? AND apartment_number = ?", (p_num, str(ak).strip()))
            conn.executemany("""
                INSERT INTO tenant_local_subscribers
                (project_number, apartment_number, subscriber_index, family_name, first_name, parking_spot, lpn1, lpn2, lpn3, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                (
                    r['project_number'], r['apartment_number'], r['subscriber_index'],
                    r['family_name'], r['first_name'], r['parking_spot'],
                    r['lpn1'], r['lpn2'], r['lpn3'], r['updated_at']
                )
                for r in all_payloads
            ])
            conn.commit()
            conn.close()

    @staticmethod
    def update_local_subscriber_plates(project_number, apartment_number, subscriber_id, lpn1, lpn2, lpn3, first_name=None, last_name=None):
        p_num = str(project_number)
        apt_str = str(apartment_number).strip()
        sid_str = str(subscriber_id).strip()
        now_iso = get_il_now().isoformat()
        upd_dict = {'lpn1': lpn1, 'lpn2': lpn2, 'lpn3': lpn3, 'updated_at': now_iso}
        if first_name is not None:
            upd_dict['first_name'] = str(first_name).strip()
        if last_name is not None:
            upd_dict['family_name'] = str(last_name).strip()
        sb = _get_supabase()
        if sb:
            try:
                sb.table('tenant_local_subscribers').update(upd_dict).eq('project_number', p_num).eq('apartment_number', apt_str).eq('subscriber_index', int(sid_str)).execute()
            except Exception:
                pass
        with _db_lock:
            conn = sqlite3.connect(SQLITE_PATH)
            sid_int = int(sid_str) if sid_str.isdigit() else -1
            if first_name is not None or last_name is not None:
                cur_row = conn.execute(
                    "SELECT first_name, family_name FROM tenant_local_subscribers WHERE project_number = ? AND apartment_number = ? AND (subscriber_index = ? OR id = ?)",
                    (p_num, apt_str, sid_int, sid_int)
                ).fetchone()
                fn_val = str(first_name).strip() if first_name is not None else (cur_row[0] if cur_row else '')
                ln_val = str(last_name).strip() if last_name is not None else (cur_row[1] if cur_row else '')
                cur = conn.execute("""
                    UPDATE tenant_local_subscribers
                    SET first_name = ?, family_name = ?, lpn1 = ?, lpn2 = ?, lpn3 = ?, updated_at = ?
                    WHERE project_number = ? AND apartment_number = ? AND (subscriber_index = ? OR id = ?)
                """, (fn_val, ln_val, lpn1, lpn2, lpn3, now_iso, p_num, apt_str, sid_int, sid_int))
            else:
                fn_val = f'דירה {apt_str}'
                ln_val = ''
                cur = conn.execute("""
                    UPDATE tenant_local_subscribers
                    SET lpn1 = ?, lpn2 = ?, lpn3 = ?, updated_at = ?
                    WHERE project_number = ? AND apartment_number = ? AND (subscriber_index = ? OR id = ?)
                """, (lpn1, lpn2, lpn3, now_iso, p_num, apt_str, sid_int, sid_int))
            if cur.rowcount == 0:
                conn.execute("""
                    INSERT INTO tenant_local_subscribers
                    (project_number, apartment_number, subscriber_index, family_name, first_name, parking_spot, lpn1, lpn2, lpn3, updated_at)
                    VALUES (?, ?, 1, ?, ?, '', ?, ?, ?, ?)
                """, (p_num, apt_str, ln_val, fn_val or f'דירה {apt_str}', lpn1, lpn2, lpn3, now_iso))
            conn.commit()
            conn.close()
        return True

    @staticmethod
    def list_tenants(project_number):
        p_num = str(project_number)
        sb = _get_supabase()
        if sb:
            try:
                res = sb.table('tenant_users').select('*').eq('project_number', p_num).order('apartment_number').execute()
                if res.data is not None:
                    return res.data
            except Exception as _sbe:
                _trip_sb_circuit_if_missing(_sbe)
        with _db_lock:
            conn = sqlite3.connect(SQLITE_PATH)
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM tenant_users WHERE project_number = ? ORDER BY CAST(apartment_number AS INTEGER), apartment_number", (p_num,)).fetchall()
            conn.close()
            return [dict(r) for r in rows]

    @staticmethod
    def find_tenants_by_phone(phone_number, project_number=None):
        """מחזיר את כל רשומות הדייר הפעילות עבור מספר טלפון (יכול להיות משויך ליותר מחניון/דירה אחת)."""
        clean_p = clean_il_phone(phone_number)
        if not clean_p:
            return []
        results = []
        seen_keys = set()
        sb = _get_supabase()
        if sb:
            try:
                q = sb.table('tenant_users').select('*').eq('phone_number', clean_p).eq('is_active', True)
                if project_number:
                    q = q.eq('project_number', str(project_number))
                res = q.execute()
                if res.data:
                    for r in res.data:
                        d = dict(r)
                        k = (str(d.get('project_number') or ''), str(d.get('apartment_number') or ''))
                        if k not in seen_keys:
                            seen_keys.add(k)
                            results.append(d)
            except Exception as _sbe:
                _trip_sb_circuit_if_missing(_sbe)
        with _db_lock:
            conn = sqlite3.connect(SQLITE_PATH)
            conn.row_factory = sqlite3.Row
            if project_number:
                rows = conn.execute("SELECT * FROM tenant_users WHERE phone_number = ? AND project_number = ? AND is_active = 1", (clean_p, str(project_number))).fetchall()
            else:
                rows = conn.execute("SELECT * FROM tenant_users WHERE phone_number = ? AND is_active = 1", (clean_p,)).fetchall()
            conn.close()
            for r in rows:
                d = dict(r)
                k = (str(d.get('project_number') or ''), str(d.get('apartment_number') or ''))
                if k not in seen_keys:
                    seen_keys.add(k)
                    results.append(d)
        return results

    @staticmethod
    def find_tenant_by_phone(phone_number, project_number=None):
        matches = TenantStore.find_tenants_by_phone(phone_number, project_number)
        return matches[0] if matches else None

    @staticmethod
    def get_tenant_by_id(tenant_id):
        sb = _get_supabase()
        if sb:
            try:
                res = sb.table('tenant_users').select('*').eq('id', int(tenant_id)).execute()
                if res.data:
                    return res.data[0]
            except Exception as _sbe:
                _trip_sb_circuit_if_missing(_sbe)
        with _db_lock:
            conn = sqlite3.connect(SQLITE_PATH)
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM tenant_users WHERE id = ?", (int(tenant_id),)).fetchone()
            conn.close()
            return dict(row) if row else None

    @staticmethod
    def create_tenant(project_number, parking_name, full_name, phone_number, apartment_number, base_max_counter=1, created_by=''):
        p_num = str(project_number)
        clean_p = clean_il_phone(phone_number)
        now_iso = get_il_now().isoformat()
        b_max = 1 if base_max_counter is None else int(base_max_counter)
        payload = {
            'project_number': p_num,
            'parking_name': parking_name or '',
            'full_name': full_name.strip(),
            'phone_number': clean_p,
            'apartment_number': str(apartment_number).strip(),
            'base_max_counter': b_max,
            'is_active': True,
            'created_by': created_by or '',
            'created_at': now_iso
        }
        sb = _get_supabase()
        if sb:
            try:
                res = sb.table('tenant_users').insert(payload).execute()
                if res.data:
                    payload['id'] = res.data[0].get('id')
            except Exception as _sbe:
                _trip_sb_circuit_if_missing(_sbe)
        with _db_lock:
            conn = sqlite3.connect(SQLITE_PATH)
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO tenant_users
                (project_number, parking_name, full_name, phone_number, apartment_number, base_max_counter, is_active, created_by, created_at)
                VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
            """, (p_num, payload['parking_name'], payload['full_name'], clean_p, payload['apartment_number'],
                  payload['base_max_counter'], payload['created_by'], now_iso))
            if 'id' not in payload or not payload['id']:
                payload['id'] = cur.lastrowid
            conn.commit()
            conn.close()
        return payload

    @staticmethod
    def update_tenant(tenant_id, full_name, phone_number, apartment_number, base_max_counter=None, is_active=True):
        clean_p = clean_il_phone(phone_number)
        upd = {
            'full_name': full_name.strip(),
            'phone_number': clean_p,
            'apartment_number': str(apartment_number).strip(),
            'is_active': bool(is_active)
        }
        if base_max_counter is not None:
            upd['base_max_counter'] = int(base_max_counter)
        sb = _get_supabase()
        if sb:
            try:
                sb.table('tenant_users').update(upd).eq('id', int(tenant_id)).execute()
            except Exception as _sbe:
                _trip_sb_circuit_if_missing(_sbe)
        with _db_lock:
            conn = sqlite3.connect(SQLITE_PATH)
            if base_max_counter is not None:
                conn.execute("""
                    UPDATE tenant_users SET full_name=?, phone_number=?, apartment_number=?, base_max_counter=?, is_active=?
                    WHERE id=?
                """, (upd['full_name'], clean_p, upd['apartment_number'], int(base_max_counter), 1 if is_active else 0, int(tenant_id)))
            else:
                conn.execute("""
                    UPDATE tenant_users SET full_name=?, phone_number=?, apartment_number=?, is_active=?
                    WHERE id=?
                """, (upd['full_name'], clean_p, upd['apartment_number'], 1 if is_active else 0, int(tenant_id)))
            conn.commit()
            conn.close()
        return True

    @staticmethod
    def delete_tenant(tenant_id):
        sb = _get_supabase()
        if sb:
            try:
                sb.table('tenant_users').delete().eq('id', int(tenant_id)).execute()
            except Exception as _sbe:
                _trip_sb_circuit_if_missing(_sbe)
        with _db_lock:
            conn = sqlite3.connect(SQLITE_PATH)
            conn.execute("DELETE FROM tenant_users WHERE id=?", (int(tenant_id),))
            conn.commit()
            conn.close()
        return True

    @staticmethod
    def save_otp(tenant_id, otp_code, expires_iso):
        sb = _get_supabase()
        if sb:
            try:
                sb.table('tenant_users').update({'mobile_otp': otp_code, 'otp_expires_at': expires_iso}).eq('id', int(tenant_id)).execute()
            except Exception as _sbe:
                _trip_sb_circuit_if_missing(_sbe)
        with _db_lock:
            conn = sqlite3.connect(SQLITE_PATH)
            conn.execute("UPDATE tenant_users SET mobile_otp=?, otp_expires_at=? WHERE id=?", (otp_code, expires_iso, int(tenant_id)))
            conn.commit()
            conn.close()

    @staticmethod
    def list_shares(project_number, active_only=True):
        p_num = str(project_number)
        local_map = {}
        with _db_lock:
            conn = sqlite3.connect(SQLITE_PATH)
            conn.row_factory = sqlite3.Row
            sql = "SELECT * FROM tenant_spot_shares WHERE project_number = ?" + (" AND is_active = 1" if active_only else "") + " ORDER BY id DESC"
            local_rows = [dict(r) for r in conn.execute(sql, (p_num,)).fetchall()]
            conn.close()
            for lr in local_rows:
                local_map[int(lr['id'])] = lr

        sb = _get_supabase()
        if sb:
            try:
                q = sb.table('tenant_spot_shares').select('*').eq('project_number', p_num)
                if active_only:
                    q = q.eq('is_active', True)
                res = q.order('id', desc=True).execute()
                if res.data is not None:
                    out = []
                    for row in res.data:
                        d = dict(row)
                        if not d.get('parking_spot_number') and int(d['id']) in local_map:
                            d['parking_spot_number'] = local_map[int(d['id'])].get('parking_spot_number') or ''
                        out.append(d)
                    return out
            except Exception as _sbe:
                _trip_sb_circuit_if_missing(_sbe)
        return local_rows

    @staticmethod
    def create_share(data):
        now_iso = get_il_now().isoformat()
        spot_no = str(data.get('parking_spot_number') or '').strip()
        payload = {
            'project_number': str(data['project_number']),
            'owner_tenant_id': int(data.get('owner_tenant_id') or 0),
            'owner_name': data.get('owner_name') or '',
            'owner_apartment': str(data['owner_apartment']).strip(),
            'spots_offered': int(data.get('spots_offered') or 1),
            'parking_spot_number': spot_no,
            'share_target_type': data.get('share_target_type', 'POOL'),
            'target_apartment': str(data.get('target_apartment') or '').strip() or None,
            'schedule_type': data.get('schedule_type', 'WEEKLY'),
            'days_of_week': str(data.get('days_of_week') or ''),
            'specific_date': str(data.get('specific_date') or '') or None,
            'start_time': data['start_time'],
            'end_time': data['end_time'],
            'is_active': True,
            'created_at': now_iso
        }
        sb = _get_supabase()
        if sb:
            try:
                res = sb.table('tenant_spot_shares').insert(payload).execute()
                if res.data:
                    payload['id'] = res.data[0].get('id')
            except Exception as _sbe:
                try:
                    base_payload = {k: v for k, v in payload.items() if k != 'parking_spot_number'}
                    res = sb.table('tenant_spot_shares').insert(base_payload).execute()
                    if res.data:
                        payload['id'] = res.data[0].get('id')
                except Exception as _sbe2:
                    _trip_sb_circuit_if_missing(_sbe2)
        with _db_lock:
            conn = sqlite3.connect(SQLITE_PATH)
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO tenant_spot_shares
                (project_number, owner_tenant_id, owner_name, owner_apartment, spots_offered, parking_spot_number, share_target_type, target_apartment,
                 schedule_type, days_of_week, specific_date, start_time, end_time, is_active, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
            """, (payload['project_number'], payload['owner_tenant_id'], payload['owner_name'], payload['owner_apartment'],
                  payload['spots_offered'], spot_no, payload['share_target_type'], payload['target_apartment'],
                  payload['schedule_type'], payload['days_of_week'], payload['specific_date'],
                  payload['start_time'], payload['end_time'], now_iso))
            if 'id' not in payload or not payload['id']:
                payload['id'] = cur.lastrowid
            conn.commit()
            conn.close()
        return payload

    @staticmethod
    def deactivate_share(share_id, project_number):
        sb = _get_supabase()
        if sb:
            try:
                sb.table('tenant_spot_shares').update({'is_active': False}).eq('id', int(share_id)).eq('project_number', str(project_number)).execute()
            except Exception as _sbe:
                _trip_sb_circuit_if_missing(_sbe)
        with _db_lock:
            conn = sqlite3.connect(SQLITE_PATH)
            conn.execute("UPDATE tenant_spot_shares SET is_active = 0 WHERE id = ? AND project_number = ?", (int(share_id), str(project_number)))
            conn.commit()
            conn.close()
        return True

    @staticmethod
    def list_transfers(project_number=None, booking_date=None, statuses=None, month_prefix=None):
        local_map = {}
        with _db_lock:
            conn = sqlite3.connect(SQLITE_PATH)
            conn.row_factory = sqlite3.Row
            conds = []
            params = []
            if project_number:
                conds.append("project_number = ?")
                params.append(str(project_number))
            if booking_date:
                conds.append("booking_date = ?")
                params.append(str(booking_date))
            if statuses:
                placeholders = ','.join('?' for _ in statuses)
                conds.append(f"status IN ({placeholders})")
                params.extend(statuses)
            if month_prefix:
                conds.append("booking_date LIKE ?")
                params.append(f"{month_prefix}%")
            where_sql = (" WHERE " + " AND ".join(conds)) if conds else ""
            local_rows = [dict(r) for r in conn.execute(f"SELECT * FROM tenant_quota_transfers{where_sql} ORDER BY id DESC", params).fetchall()]
            conn.close()
            for lr in local_rows:
                local_map[int(lr['id'])] = lr

        sb = _get_supabase()
        if sb:
            try:
                q = sb.table('tenant_quota_transfers').select('*')
                if project_number:
                    q = q.eq('project_number', str(project_number))
                if booking_date:
                    q = q.eq('booking_date', str(booking_date))
                if statuses:
                    q = q.in_('status', list(statuses))
                if month_prefix:
                    q = q.like('booking_date', f"{month_prefix}%")
                res = q.order('id', desc=True).execute()
                if res.data is not None:
                    out = []
                    for row in res.data:
                        d = dict(row)
                        if not d.get('parking_spot_number') and int(d['id']) in local_map:
                            d['parking_spot_number'] = local_map[int(d['id'])].get('parking_spot_number') or ''
                        out.append(d)
                    return out
            except Exception as _sbe:
                _trip_sb_circuit_if_missing(_sbe)
        return local_rows

    @staticmethod
    def create_transfer(data):
        now_iso = get_il_now().isoformat()
        spot_no = str(data.get('parking_spot_number') or '').strip()
        payload = {
            'share_id': int(data['share_id']),
            'slot_index': int(data.get('slot_index') or 1),
            'project_number': str(data['project_number']),
            'from_apartment': str(data['from_apartment']).strip(),
            'to_apartment': str(data['to_apartment']).strip(),
            'parking_spot_number': spot_no,
            'borrower_tenant_id': int(data.get('borrower_tenant_id') or 0),
            'borrower_name': data.get('borrower_name') or '',
            'borrower_phone': clean_il_phone(data.get('borrower_phone') or ''),
            'booking_date': str(data['booking_date']),
            'start_time': str(data['start_time']),
            'end_time': str(data['end_time']),
            'window_start': str(data['window_start']),
            'window_end': str(data['window_end']),
            'status': data.get('status', 'SCHEDULED'),
            'notified_start': False,
            'notified_ending_soon': False,
            'late_exit_flag': False,
            'created_at': now_iso
        }
        sb = _get_supabase()
        if sb:
            try:
                res = sb.table('tenant_quota_transfers').insert(payload).execute()
                if res.data:
                    payload['id'] = res.data[0].get('id')
            except Exception as _sbe:
                try:
                    base_payload = {k: v for k, v in payload.items() if k != 'parking_spot_number'}
                    res = sb.table('tenant_quota_transfers').insert(base_payload).execute()
                    if res.data:
                        payload['id'] = res.data[0].get('id')
                except Exception as _sbe2:
                    _trip_sb_circuit_if_missing(_sbe2)
        with _db_lock:
            conn = sqlite3.connect(SQLITE_PATH)
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO tenant_quota_transfers
                (share_id, slot_index, project_number, from_apartment, to_apartment, parking_spot_number, borrower_tenant_id, borrower_name, borrower_phone,
                 booking_date, start_time, end_time, window_start, window_end, status, notified_start, notified_ending_soon, late_exit_flag, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 0, ?)
            """, (payload['share_id'], payload['slot_index'], payload['project_number'], payload['from_apartment'],
                  payload['to_apartment'], spot_no, payload['borrower_tenant_id'], payload['borrower_name'], payload['borrower_phone'],
                  payload['booking_date'], payload['start_time'], payload['end_time'], payload['window_start'],
                  payload['window_end'], payload['status'], now_iso))
            if 'id' not in payload or not payload['id']:
                payload['id'] = cur.lastrowid
            conn.commit()
            conn.close()
        return payload

    @staticmethod
    def update_transfer(transfer_id, updates):
        sb = _get_supabase()
        if sb:
            try:
                sb.table('tenant_quota_transfers').update(updates).eq('id', int(transfer_id)).execute()
            except Exception as _sbe:
                _trip_sb_circuit_if_missing(_sbe)
        with _db_lock:
            conn = sqlite3.connect(SQLITE_PATH)
            cols = []
            vals = []
            for k, v in updates.items():
                cols.append(f"{k} = ?")
                if isinstance(v, bool):
                    vals.append(1 if v else 0)
                else:
                    vals.append(v)
            vals.append(int(transfer_id))
            conn.execute(f"UPDATE tenant_quota_transfers SET {', '.join(cols)} WHERE id = ?", vals)
            conn.commit()
            conn.close()

    @staticmethod
    def get_transfer_by_id(transfer_id):
        sb = _get_supabase()
        if sb:
            try:
                res = sb.table('tenant_quota_transfers').select('*').eq('id', int(transfer_id)).execute()
                if res.data:
                    return res.data[0]
            except Exception as _sbe:
                _trip_sb_circuit_if_missing(_sbe)
        with _db_lock:
            conn = sqlite3.connect(SQLITE_PATH)
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM tenant_quota_transfers WHERE id = ?", (int(transfer_id),)).fetchone()
            conn.close()
            return dict(row) if row else None

# ============================================================================
# 2. Scheidt & Bachmann INTEGRATION (maxCounter Pooling & Apartment Vehicles)
# ============================================================================
def _get_parking_conn(project_number):
    app_mod = _get_app_module()
    if not app_mod:
        return None
    cache = getattr(app_mod, '_parking_info_cache', {})
    p_key = str(project_number)
    now_ts = time.time()
    cached = cache.get(p_key)
    if cached and (now_ts - cached.get('ts', 0) < 600):
        return cached
    fn = getattr(app_mod, 'get_parking_connection_details', None)
    if fn:
        details = fn(project_number)
        if details and details.get('ip_address'):
            details['ts'] = now_ts
            cache[p_key] = details
            return details
    return None

def _get_http_session():
    app_mod = _get_app_module()
    return getattr(app_mod, '_parking_http_session', requests.Session())

def _skidata_headers(content_type=None):
    auth_str = base64.b64encode(b'2022:2022').decode('ascii')
    h = {
        'Authorization': f'Basic {auth_str}',
        'Accept': 'application/xml, text/xml'
    }
    if content_type:
        h['Content-Type'] = content_type
    return h

def is_standalone_building(project_number):
    """בודק האם המתחם פועל במצב עצמאי (ללא מערכת בקר חניון - מבוסס קובץ דירות)."""
    p_num = str(project_number)
    b_settings = TenantStore.get_building_settings(p_num)
    if int(b_settings.get('standalone_mode') or 0) == 1:
        return True
    conn = _get_parking_conn(p_num)
    ip_val = str((conn or {}).get('ip_address') or '').strip().lower()
    if not conn or not ip_val or ip_val in ('0', '0.0.0.0', 'none', 'standalone', 'local', 'no-system', '-'):
        return True
    return False

def _get_standalone_pooling_status(project_number, apartment_number):
    """חישוב מכסת חניות של דירה במתחם עצמאי (ללא בקר חניון): אין בדיקות נוכחות, המכסה נקבעת לפי בסיס הדירה +- השאלות פעילות כעת."""
    p_num = str(project_number)
    apt_str = str(apartment_number).strip()
    local_subs = TenantStore.list_local_subscribers(p_num, apt_str)
    tenants = [t for t in TenantStore.list_tenants(p_num) if str(t.get('apartment_number') or '').strip() == apt_str]

    family_name = ''
    for ls in local_subs:
        if ls.get('family_name'):
            family_name = str(ls['family_name']).strip()
            break
    if not family_name and tenants:
        family_name = (tenants[0].get('full_name') or '').strip()

    if tenants and tenants[0].get('base_max_counter') is not None:
        base_max = int(tenants[0].get('base_max_counter') or 0)
    else:
        spots_with_num = [s for s in local_subs if (s.get('parking_spot') or '').strip()]
        base_max = len(spots_with_num) if spots_with_num else (len(local_subs) if local_subs else 1)

    active_trs = TenantStore.list_transfers(project_number=p_num, statuses=['ACTIVE'])
    lent_now = sum(1 for tr in active_trs if str(tr.get('from_apartment') or '').strip() == apt_str)
    borrowed_now = sum(1 for tr in active_trs if str(tr.get('to_apartment') or '').strip() == apt_str)

    effective_max = max(0, base_max - lent_now + borrowed_now)
    return {
        'success': True,
        'standaloneMode': True,
        'apartment': apt_str,
        'contractName': family_name,
        'contractStatus': 2 if effective_max == 0 else 0,
        'isBlockedZeroSpot': (base_max == 0 and borrowed_now == 0),
        'rawMaxCounter': base_max,
        'maxCounter': effective_max,
        'presentCounter': 0,
        'availableSpots': effective_max
    }

def get_apartment_pooling_status(project_number, apartment_number):
    """קריאת maxCounter, presentCounter ו-status של דירה (חברה) מתוך שיידט, או מקומית במתחם ללא בקר חניון."""
    if is_standalone_building(project_number):
        return _get_standalone_pooling_status(project_number, apartment_number)
    conn = _get_parking_conn(project_number)
    if not conn or not conn.get('ip_address'):
        local_subs = TenantStore.list_local_subscribers(project_number, apartment_number)
        if local_subs:
            return _get_standalone_pooling_status(project_number, apartment_number)
        return {'success': False, 'message': 'לא נמצאו פרטי חיבור לחניון'}
    ip = conn['ip_address']
    port = conn.get('port', 8443)
    url = f"https://{ip}:{port}/CustomerMediaWebService/contracts/{apartment_number}/detail"
    try:
        sess = _get_http_session()
        resp = sess.get(url, headers=_skidata_headers(), verify=False, timeout=15)
        if resp.status_code != 200:
            return {'success': False, 'message': f'HTTP {resp.status_code}'}
        resp.encoding = 'utf-8'
        ns = {'ns': 'http://gsph.sub.com/cust/types'}
        root = ET.fromstring(resp.content)
        contract_node = root.find('ns:contract', ns)
        contract_name = contract_node.findtext('ns:name', default='', namespaces=ns) if contract_node is not None else ''
        contract_status = int(root.findtext('ns:status', default='0', namespaces=ns) or 0)
        pooling_node = root.find('.//ns:pooling', ns)
        raw_max_c = 0
        pres_c = 0
        if pooling_node is not None:
            details = pooling_node.findall('ns:poolingDetail', ns)
            chosen = None
            for d in details:
                f = d.findtext('ns:facility', default='0', namespaces=ns)
                p = d.findtext('ns:extCardProfile', default='0', namespaces=ns)
                if f == '0' and p == '0':
                    chosen = d
                    break
            if chosen is None and details:
                chosen = details[0]
            if chosen is not None:
                raw_max_c = int(chosen.findtext('ns:maxCounter', default='0', namespaces=ns) or 0)
                pres_c = int(chosen.findtext('ns:presentCounter', default='0', namespaces=ns) or 0)

        # אם החוזה בסטטוס חסום (status == 2) ו-maxCounter הוא 1 או פחות, זו דירה שהוגדרה כ"דירה ללא חניה (0 חניות)".
        # אם בבקר מוגדר maxCounter > 1 (למשל דירה עם 2 חניות כמו 1133), נציג את כמות החניות האמיתית שלה (raw_max_c).
        is_blocked_zero = (contract_status != 0 and raw_max_c <= 1)
        effective_max_c = 0 if is_blocked_zero else raw_max_c

        return {
            'success': True,
            'apartment': str(apartment_number),
            'contractName': contract_name,
            'contractStatus': contract_status,
            'isBlockedZeroSpot': is_blocked_zero,
            'rawMaxCounter': raw_max_c,
            'maxCounter': effective_max_c,
            'presentCounter': pres_c,
            'availableSpots': max(0, effective_max_c - pres_c)
        }
    except Exception as e:
        return {'success': False, 'message': str(e)}

def set_apartment_zero_spot_mode(project_number, apartment_number, is_zero_spot):
    """הגדרת דירה בבקר שיידט כ'דירה ללא חניה (0 חניות)' באמצעות status=2 ו-maxCounter=1,
    או שחרור החסימה (status=0) לדירה עם חניה."""
    if is_standalone_building(project_number):
        local_subs = TenantStore.list_local_subscribers(project_number, apartment_number)
        spots_with_num = [s for s in local_subs if (s.get('parking_spot') or '').strip() not in ('', '0', '-')]
        restored_max = len(spots_with_num) if spots_with_num else (len(local_subs) if local_subs else 1)
        return {
            'success': True,
            'standaloneMode': True,
            'effectiveMaxCounter': 0 if is_zero_spot else max(1, restored_max),
            'contractStatus': 2 if is_zero_spot else 0
        }
    conn = _get_parking_conn(project_number)
    if not conn or not conn.get('ip_address'):
        return {'success': True, 'effectiveMaxCounter': 0 if is_zero_spot else 1, 'contractStatus': 2 if is_zero_spot else 0}
    ip = conn['ip_address']
    port = conn.get('port', 8443)
    url = f"https://{ip}:{port}/CustomerMediaWebService/contracts/{apartment_number}/detail"
    try:
        sess = _get_http_session()
        resp = sess.get(url, headers=_skidata_headers(), verify=False, timeout=15)
        if resp.status_code != 200:
            return {'success': False, 'message': f'Failed GET contract {apartment_number}: HTTP {resp.status_code}'}
        ns_uri = 'http://gsph.sub.com/cust/types'
        ns = {'ns': ns_uri}
        ET.register_namespace('', ns_uri)
        root = ET.fromstring(resp.content)

        st_el = root.find('ns:status', ns)
        if st_el is None:
            st_el = ET.SubElement(root, f'{{{ns_uri}}}status')

        pooling_node = root.find('.//ns:pooling', ns)
        max_el = None
        if pooling_node is not None:
            details = pooling_node.findall('ns:poolingDetail', ns)
            target_detail = None
            for d in details:
                f = d.findtext('ns:facility', default='0', namespaces=ns)
                p = d.findtext('ns:extCardProfile', default='0', namespaces=ns)
                if f == '0' and p == '0':
                    target_detail = d
                    break
            if target_detail is None and details:
                target_detail = details[0]
            if target_detail is not None:
                max_el = target_detail.find('ns:maxCounter', ns)

        if is_zero_spot:
            # חסימה 2 + מונה 1 (כיוון ש-0 בשיידט נחשב ללא הגבלה)
            st_el.text = '2'
            if max_el is not None:
                max_el.text = '1'
            effective_max = 0
        else:
            st_el.text = '0'
            cur_raw_max = int((max_el.text if max_el is not None else '1') or 1)
            # אם בבקר יש מספר מנויים עם חניה מוגדרת (matchCode), שחזר את כמות החניות לפי כמות החניות של המנויים
            try:
                subs_url = f"https://{ip}:{port}/CustomerMediaWebService/contracts/{apartment_number}/consumersdetail"
                s_resp = sess.get(subs_url, headers=_skidata_headers(), verify=False, timeout=10)
                if s_resp.status_code == 200:
                    s_root = ET.fromstring(s_resp.content)
                    spots_cnt = sum(
                        1 for cd in s_root.findall('.//ns:consumerDetail', ns)
                        if ((cd.findtext('.//ns:matchCode', default='', namespaces=ns) or '').strip() not in ('', '0', '-'))
                    )
                    if spots_cnt > cur_raw_max:
                        cur_raw_max = spots_cnt
                        if max_el is not None:
                            max_el.text = str(cur_raw_max)
            except Exception:
                pass
            if cur_raw_max < 1 and max_el is not None:
                max_el.text = '1'
                cur_raw_max = 1
            effective_max = cur_raw_max

        xml_payload = ET.tostring(root, encoding='utf-8', method='xml')
        put_resp = sess.put(url, data=xml_payload, headers=_skidata_headers('application/xml'), verify=False, timeout=15)
        if put_resp.status_code in (200, 201, 204):
            return {
                'success': True,
                'effectiveMaxCounter': effective_max,
                'contractStatus': 2 if is_zero_spot else 0
            }
        return {'success': False, 'message': f'PUT rejected with HTTP {put_resp.status_code}'}
    except Exception as e:
        return {'success': False, 'message': str(e)}

def adjust_apartment_max_counter(project_number, apartment_number, delta):
    """שינוי מכסת החניות הפעילה של דירה ב-+1 או -1 מול שיידט (PUT /contracts/{id}/detail).
    במתחם עצמאי (ללא בקר חניון) המכסה מחושבת אוטומטית מההעברות הפעילות."""
    if is_standalone_building(project_number):
        return {'success': True, 'standaloneMode': True}
    conn = _get_parking_conn(project_number)
    if not conn or not conn.get('ip_address'):
        return {'success': False, 'message': 'לא נמצאו פרטי חיבור לחניון'}
    ip = conn['ip_address']
    port = conn.get('port', 8443)
    url = f"https://{ip}:{port}/CustomerMediaWebService/contracts/{apartment_number}/detail"
    try:
        sess = _get_http_session()
        resp = sess.get(url, headers=_skidata_headers(), verify=False, timeout=15)
        if resp.status_code != 200:
            return {'success': False, 'message': f'Failed GET contract {apartment_number}: HTTP {resp.status_code}'}
        ns_uri = 'http://gsph.sub.com/cust/types'
        ns = {'ns': ns_uri}
        ET.register_namespace('', ns_uri)
        root = ET.fromstring(resp.content)
        pooling_node = root.find('.//ns:pooling', ns)
        if pooling_node is None:
            return {'success': False, 'message': 'No pooling node in contract XML'}
        details = pooling_node.findall('ns:poolingDetail', ns)
        target_detail = None
        for d in details:
            f = d.findtext('ns:facility', default='0', namespaces=ns)
            p = d.findtext('ns:extCardProfile', default='0', namespaces=ns)
            if f == '0' and p == '0':
                target_detail = d
                break
        if target_detail is None and details:
            target_detail = details[0]
        if target_detail is None:
            return {'success': False, 'message': 'No poolingDetail found'}

        st_el = root.find('ns:status', ns)
        if st_el is None:
            st_el = ET.SubElement(root, f'{{{ns_uri}}}status')
            st_el.text = '0'
        cur_status = int((st_el.text if st_el is not None else '0') or 0)

        max_el = target_detail.find('ns:maxCounter', ns)
        pres_el = target_detail.find('ns:presentCounter', ns)
        raw_old_max = int((max_el.text if max_el is not None else '1') or 1)
        pres_val = int((pres_el.text if pres_el is not None else '0') or 0)

        # אם החוזה היה חסום (status != 0), המכסה הפעילה שלו לפני השינוי הייתה 0
        old_effective_max = 0 if cur_status != 0 else raw_old_max
        new_effective_max = max(0, old_effective_max + int(delta))

        if new_effective_max == 0:
            # 0 חניות פעילות -> בשיידט שמים מונה 1 וסטטוס חסימה 2
            if max_el is not None:
                max_el.text = '1'
            st_el.text = '2'
        else:
            # חניה 1 או יותר פעילות -> משחררים חסימה (status=0) ומגדירים את המונה למכסה הפעילה
            if max_el is not None:
                max_el.text = str(new_effective_max)
            st_el.text = '0'

        xml_payload = ET.tostring(root, encoding='utf-8', method='xml')
        put_resp = sess.put(url, data=xml_payload, headers=_skidata_headers('application/xml'), verify=False, timeout=15)
        if put_resp.status_code in (200, 201, 204):
            return {
                'success': True,
                'oldMaxCounter': old_effective_max,
                'newMaxCounter': new_effective_max,
                'contractStatus': 2 if new_effective_max == 0 else 0,
                'presentCounter': pres_val
            }
        return {'success': False, 'message': f'PUT rejected with HTTP {put_resp.status_code}: {put_resp.text[:200]}'}
    except Exception as e:
        return {'success': False, 'message': str(e)}

def _get_subscriber_parked_info(sess, ip, port, apt_str, sid_str, cur_lpn1='', cur_lpn2='', cur_lpn3=''):
    """
    בודק מול /parktrans של שיידט איזה רכב ספציפי (lpn1 / lpn2 / lpn3) נמצא כעת בחניון
    וכמה ימים עברו מהפעולה האחרונה (transactionTime).
    מחזיר מילון: {
        'fac_id': int, 'comp_id': int, 'dev_id': int,
        'parked_lpn': str, 'parked_slot': 'lpn1'|'lpn2'|'lpn3',
        'days_in_parking': float, 'entry_time_str': str
    }
    """
    ns_uri = 'http://gsph.sub.com/cust/types'
    ns = {'ns': ns_uri}
    c1 = re.sub(r'[^0-9CCDמ]', '', str(cur_lpn1 or '').strip().upper())
    c2 = re.sub(r'[^0-9CCDמ]', '', str(cur_lpn2 or '').strip().upper())
    c3 = re.sub(r'[^0-9CCDמ]', '', str(cur_lpn3 or '').strip().upper())

    fac_id, comp_id, dev_id = 2280, 2152, 101
    parked_lpn = ''
    entry_time_str = ''
    days_in_parking = 0.0

    try:
        pt_url = f"https://{ip}:{port}/CustomerMediaWebService/consumers/{apt_str},{sid_str}/parktrans"
        pt_resp = sess.get(pt_url, headers=_skidata_headers(), verify=False, timeout=10)
        if pt_resp.status_code == 200:
            pt_root = ET.fromstring(pt_resp.content)
            tx_list = pt_root.findall('.//ns:parkTransaction', ns)
            # מיון מהפעולה החדשה ביותר לישנה ביותר לפי transactionTime
            def _tx_sort_key(tx_el):
                return (tx_el.findtext('ns:transactionTime', default='', namespaces=ns) or '').strip()
            tx_list_sorted = sorted(tx_list, key=_tx_sort_key, reverse=True)

            # זמן הפעולה האחרונה בכלל
            latest_tx_time_str = _tx_sort_key(tx_list_sorted[0]) if tx_list_sorted else ''

            for tx in tx_list_sorted:
                fin = int(tx.findtext('ns:facilityin', default='0', namespaces=ns) or 0)
                if fin > 0:
                    fac_id = fin
                    comp_id = int(tx.findtext('ns:computer', default='2152', namespaces=ns) or 2152)
                    dev_id = int(tx.findtext('ns:device', default='101', namespaces=ns) or 101)
                    raw_tx_lpn = (tx.findtext('ns:lpn', default='', namespaces=ns) or '').strip().upper()
                    parked_lpn = re.sub(r'[^0-9CCDמ]', '', raw_tx_lpn)
                    entry_time_str = (tx.findtext('ns:transactionTime', default='', namespaces=ns) or '').strip()
                    break

            ref_time_str = entry_time_str or latest_tx_time_str
            if ref_time_str:
                try:
                    tx_dt = datetime.datetime.fromisoformat(ref_time_str)
                    now_dt = datetime.datetime.now(tx_dt.tzinfo) if tx_dt.tzinfo else datetime.datetime.now()
                    days_in_parking = max(0.0, (now_dt - tx_dt).total_seconds() / 86400.0)
                except Exception:
                    days_in_parking = 0.0
    except Exception:
        pass

    # זיהוי איזה שדה רכב (lpn1 / lpn2 / lpn3) הוא הרכב שנמצא בחניון
    parked_slot = 'lpn1'
    if parked_lpn:
        if parked_lpn == c1:
            parked_slot = 'lpn1'
        elif parked_lpn == c2:
            parked_slot = 'lpn2'
        elif parked_lpn == c3:
            parked_slot = 'lpn3'
        elif c1 and parked_lpn.lstrip('0') == c1.lstrip('0'):
            parked_slot = 'lpn1'
        elif c2 and parked_lpn.lstrip('0') == c2.lstrip('0'):
            parked_slot = 'lpn2'
        elif c3 and parked_lpn.lstrip('0') == c3.lstrip('0'):
            parked_slot = 'lpn3'
    else:
        if c1:
            parked_slot = 'lpn1'
            parked_lpn = c1
        elif c2:
            parked_slot = 'lpn2'
            parked_lpn = c2
        elif c3:
            parked_slot = 'lpn3'
            parked_lpn = c3

    return {
        'fac_id': fac_id,
        'comp_id': comp_id,
        'dev_id': dev_id,
        'parked_lpn': parked_lpn,
        'parked_slot': parked_slot,
        'days_in_parking': days_in_parking,
        'entry_time_str': entry_time_str
    }

def _get_standalone_subscribers(project_number, apartment_number):
    p_num = str(project_number)
    apt_str = str(apartment_number).strip()
    rows = TenantStore.list_local_subscribers(p_num, apt_str)
    if not rows:
        tenants = [t for t in TenantStore.list_tenants(p_num) if str(t.get('apartment_number') or '').strip() == apt_str]
        if tenants:
            t0 = tenants[0]
            return {
                'success': True,
                'standaloneMode': True,
                'subscribers': [{
                    'id': '1',
                    'apartment': apt_str,
                    'firstName': (t0.get('full_name') or '').strip(),
                    'lastName': '',
                    'parking_spot': '',
                    'present': False,
                    'parked_slot': None,
                    'parked_lpn': '',
                    'days_in_parking': 0.0,
                    'can_edit_parked': True,
                    'standaloneMode': True,
                    'lpn1': '',
                    'lpn2': '',
                    'lpn3': ''
                }]
            }
        return {'success': True, 'standaloneMode': True, 'subscribers': []}

    subs = []
    for idx, r in enumerate(rows, start=1):
        sid = str(r.get('subscriber_index') or idx)
        subs.append({
            'id': sid,
            'apartment': apt_str,
            'firstName': (r.get('first_name') or '').strip(),
            'lastName': (r.get('family_name') or '').strip(),
            'parking_spot': (r.get('parking_spot') or '').strip(),
            'present': False,
            'parked_slot': None,
            'parked_lpn': '',
            'days_in_parking': 0.0,
            'can_edit_parked': True,
            'standaloneMode': True,
            'lpn1': (r.get('lpn1') or '').strip(),
            'lpn2': (r.get('lpn2') or '').strip(),
            'lpn3': (r.get('lpn3') or '').strip()
        })
    return {'success': True, 'standaloneMode': True, 'subscribers': subs}

def get_apartment_subscribers(project_number, apartment_number):
    """שליפת המנויים והרכבים של הדירה מתוך שיידט, או מתוך הקובץ המקומי במתחם ללא בקר חניון."""
    if is_standalone_building(project_number):
        return _get_standalone_subscribers(project_number, apartment_number)
    conn = _get_parking_conn(project_number)
    if not conn or not conn.get('ip_address'):
        local_rows = TenantStore.list_local_subscribers(project_number, apartment_number)
        if local_rows:
            return _get_standalone_subscribers(project_number, apartment_number)
        return {'success': False, 'message': 'לא נמצאו פרטי חיבור לחניון', 'subscribers': []}
    ip = conn['ip_address']
    port = conn.get('port', 8443)
    apt_str = str(apartment_number).strip()
    url = f"https://{ip}:{port}/CustomerMediaWebService/contracts/{apt_str}/consumersdetail"
    try:
        sess = _get_http_session()
        resp = sess.get(url, headers=_skidata_headers(), verify=False, timeout=25)
        if resp.status_code != 200:
            return {'success': False, 'message': f'HTTP {resp.status_code}', 'subscribers': []}
        resp.encoding = 'utf-8'
        ns = {'ns': 'http://gsph.sub.com/cust/types'}
        root = ET.fromstring(resp.content)
        all_cds = root.findall('.//ns:consumerDetail', ns)
        subs = []
        for cd in all_cds:
            cons = cd.find('ns:consumer', ns)
            person = cd.find('ns:person', ns)
            ident = cd.find('ns:identification', ns)
            sid = (cons.findtext('ns:id', default='', namespaces=ns) if cons is not None else '').strip()
            fname = ((person.findtext('ns:firstName', default='', namespaces=ns) if person is not None else '') or cd.findtext('ns:firstName', default='', namespaces=ns) or '').strip()
            lname = ((person.findtext('ns:surname', default='', namespaces=ns) if person is not None else '') or cd.findtext('ns:surname', default='', namespaces=ns) or '').strip()
            match_code = ((person.findtext('ns:matchCode', default='', namespaces=ns) if person is not None else '') or cd.findtext('ns:matchCode', default='', namespaces=ns) or '').strip()
            pres = ident.findtext('ns:present', default='false', namespaces=ns) if ident is not None else 'false'
            is_pres = str(pres).lower() in ('true', '1', 'yes')
            lpn1 = (cd.findtext('ns:lpn1', default='', namespaces=ns) or '').strip()
            lpn2 = (cd.findtext('ns:lpn2', default='', namespaces=ns) or '').strip()
            lpn3 = (cd.findtext('ns:lpn3', default='', namespaces=ns) or '').strip()

            # דילוג על כרטיסי שלד ריקים בבקר ("שם המנוי" ללא רכב וללא מספר חניה) כאשר כבר יש מנויים אמיתיים בדירה
            if len(all_cds) > 1 and lname in ('שם המנוי', 'Default') and not fname and not lpn1 and not lpn2 and not lpn3 and not match_code and not is_pres:
                continue

            parked_slot = None
            parked_lpn = ''
            days_in_parking = 0.0
            can_edit_parked = True
            if is_pres and sid:
                p_info = _get_subscriber_parked_info(sess, ip, port, apt_str, sid, lpn1, lpn2, lpn3)
                parked_slot = p_info['parked_slot']
                parked_lpn = p_info['parked_lpn']
                days_in_parking = round(p_info['days_in_parking'], 1)
                can_edit_parked = bool(p_info['days_in_parking'] >= 7.0)

            subs.append({
                'id': sid,
                'apartment': apt_str,
                'firstName': fname.strip(),
                'lastName': lname.strip(),
                'parking_spot': match_code,
                'present': is_pres,
                'parked_slot': parked_slot,
                'parked_lpn': parked_lpn,
                'days_in_parking': days_in_parking,
                'can_edit_parked': can_edit_parked,
                'lpn1': lpn1,
                'lpn2': lpn2,
                'lpn3': lpn3
            })
        return {'success': True, 'subscribers': subs}
    except Exception as e:
        return {'success': False, 'message': str(e), 'subscribers': []}

def update_apartment_subscriber_plates(project_number, apartment_number, subscriber_id, lpn1, lpn2, lpn3, first_name=None, last_name=None):
    """
    עדכון שם ומספרי רכב של מנוי בדירה:
    - במתחם עצמאי (ללא בקר חניון): מעדכן ישירות בטבלת המנויים המקומית ללא בדיקת נוכחות.
    - במתחם עם בקר שיידט: מעדכן מול הבקר כולל בדיקת נוכחות רכב ספציפי ו-7 ימים.
    """
    from xml.sax.saxutils import escape as _xml_esc

    def _validate_plate_common(raw_val):
        s = re.sub(r'[\s\-]', '', str(raw_val or '').strip()).upper()
        if not s:
            return True, ''
        rem = s.replace('CC', '', 1).replace('CD', '', 1).replace('מ', '', 1)
        if not rem.isdigit() or not any(ch.isdigit() for ch in s):
            return False, s
        letters_only = ''.join(ch for ch in s if not ch.isdigit())
        if letters_only not in ('', 'CC', 'CD', 'מ'):
            return False, s
        return True, s

    if is_standalone_building(project_number):
        clean_vals = {}
        for k, v in [('lpn1', lpn1), ('lpn2', lpn2), ('lpn3', lpn3)]:
            ok, cl = _validate_plate_common(v)
            if not ok:
                return {'success': False, 'message': 'במספר רכב מותר להזין ספרות בלבד, או CC / CD לרכב דיפלומטי, או האות מ׳ לרכב משטרה.'}
            clean_vals[k] = cl
        TenantStore.update_local_subscriber_plates(
            project_number, apartment_number, subscriber_id,
            clean_vals['lpn1'], clean_vals['lpn2'], clean_vals['lpn3'],
            first_name=first_name, last_name=last_name
        )
        return {'success': True, 'message': 'פרטי המנוי ומספרי הרכב עודכנו ונשמרו בהצלחה!'}

    conn = _get_parking_conn(project_number)
    if not conn or not conn.get('ip_address'):
        return {'success': False, 'message': 'לא נמצאו פרטי חיבור לחניון'}
    ip = conn['ip_address']
    port = conn.get('port', 8443)
    apt_str = str(apartment_number).strip()
    sid_str = str(subscriber_id).strip()
    url = f"https://{ip}:{port}/CustomerMediaWebService/consumers/{apt_str},{sid_str}/detail"
    try:
        sess = _get_http_session()
        resp = sess.get(url, headers=_skidata_headers(), verify=False, timeout=15)
        if resp.status_code != 200:
            return {'success': False, 'message': f'שגיאה בקריאת מנוי ({resp.status_code})'}
        ns_uri = 'http://gsph.sub.com/cust/types'
        ns = {'ns': ns_uri}
        root = ET.fromstring(resp.content)

        ident = root.find('ns:identification', ns)
        pres_txt = ident.findtext('ns:present', default='false', namespaces=ns) if ident is not None else 'false'
        is_present = str(pres_txt).strip().lower() in ('true', '1', 'yes')

        person_el = root.find('ns:person', ns)
        cur_first = ((person_el.findtext('ns:firstName', default='', namespaces=ns) if person_el is not None else '') or root.findtext('ns:firstName', default='', namespaces=ns) or '').strip()
        cur_last = ((person_el.findtext('ns:surname', default='', namespaces=ns) if person_el is not None else '') or root.findtext('ns:surname', default='', namespaces=ns) or '').strip()
        cur_match_code = ((person_el.findtext('ns:matchCode', default='', namespaces=ns) if person_el is not None else '') or '').strip()

        new_first = str(first_name).strip() if first_name is not None else cur_first
        new_last = str(last_name).strip() if last_name is not None else cur_last
        name_changed = (first_name is not None and new_first != cur_first) or (last_name is not None and new_last != cur_last)

        cur_lpn1 = re.sub(r'[^0-9CCDמ]', '', (root.findtext('ns:lpn1', default='', namespaces=ns) or '').strip().upper())
        cur_lpn2 = re.sub(r'[^0-9CCDמ]', '', (root.findtext('ns:lpn2', default='', namespaces=ns) or '').strip().upper())
        cur_lpn3 = re.sub(r'[^0-9CCDמ]', '', (root.findtext('ns:lpn3', default='', namespaces=ns) or '').strip().upper())
        cur_map = {'lpn1': cur_lpn1, 'lpn2': cur_lpn2, 'lpn3': cur_lpn3}

        def _validate_plate(raw_val):
            """מתיר ספרות בלבד, או הצירופים CC / CD (דיפלומטי) או האות 'מ' (משטרה)."""
            s = re.sub(r'[\s\-]', '', str(raw_val or '').strip()).upper()
            if not s:
                return True, ''
            rem = s.replace('CC', '', 1).replace('CD', '', 1).replace('מ', '', 1)
            if not rem.isdigit() or not any(ch.isdigit() for ch in s):
                return False, s
            letters_only = ''.join(ch for ch in s if not ch.isdigit())
            if letters_only not in ('', 'CC', 'CD', 'מ'):
                return False, s
            return True, s

        changed_tags = {}
        for tag_name, val in [('lpn1', lpn1), ('lpn2', lpn2), ('lpn3', lpn3)]:
            if val is None:
                continue
            is_ok, clean_plate = _validate_plate(val)
            if not is_ok:
                return {
                    'success': False,
                    'message': 'במספר רכב מותר להזין ספרות בלבד, או CC / CD לרכב דיפלומטי, או האות מ׳ לרכב משטרה.'
                }
            if clean_plate != cur_map.get(tag_name, ''):
                # בשיידט שליחת רווח בודד מנקה את מספר הרכב אם המשתמש מחק אותו
                changed_tags[tag_name] = clean_plate if clean_plate else ' '

        if not changed_tags and not name_changed:
            return {'success': True, 'message': 'פרטי המנוי ומספרי הרכב עודכנו בהצלחה בחניון!'}

        person_xml_part = ''
        cons_name_tag = ''
        if name_changed:
            mc_tag = f'<matchCode>{_xml_esc(cur_match_code)}</matchCode>' if cur_match_code else ''
            person_xml_part = f'<person><firstName>{_xml_esc(new_first)}</firstName><surname>{_xml_esc(new_last)}</surname>{mc_tag}</person>'
            cons_name_val = f"{new_last} {new_first}".strip()
            if cons_name_val:
                cons_name_tag = f'<name>{_xml_esc(cons_name_val)}</name>'

        lpn_xml_parts = ''.join(f'<{k}>{v}</{k}>' for k, v in changed_tags.items())
        minimal_xml = (
            f'<?xml version="1.0" encoding="UTF-8"?>'
            f'<consumerDetail xmlns="{ns_uri}">'
            f'<consumer href="/consumers/{apt_str},{sid_str}">'
            f'<id>{sid_str}</id><contractid>{apt_str}</contractid>{cons_name_tag}'
            f'</consumer>'
            f'{person_xml_part}'
            f'{lpn_xml_parts}'
            f'</consumerDetail>'
        ).encode('utf-8')

        if not changed_tags and name_changed:
            put_resp = sess.put(url, data=minimal_xml, headers=_skidata_headers('application/xml'), verify=False, timeout=15)
            if put_resp.status_code in (200, 201, 204):
                return {'success': True, 'message': 'שם המנוי עודכן בהצלחה בחניון!'}
            return {'success': False, 'message': f'בקר החניון דחה את העדכון ({put_resp.status_code})'}

        def _book_exit(fac_id, comp_id, dev_id):
            now_tx = datetime.datetime.now().astimezone().isoformat(timespec='milliseconds')
            tx_xml = (
                f'<?xml version="1.0" encoding="UTF-8"?>'
                f'<bookParkTransaction xmlns="{ns_uri}">'
                f'<exitParkTransaction>'
                f'<transactionTime>{now_tx}</transactionTime>'
                f'<transactionType>12</transactionType>'
                f'<facilityin>0</facilityin><facilityout>{fac_id}</facilityout>'
                f'<computer>{comp_id}</computer><device>{dev_id}</device><amount>0</amount>'
                f'<contractid>{apt_str}</contractid><consumerid>{sid_str}</consumerid>'
                f'</exitParkTransaction>'
                f'</bookParkTransaction>'
            ).encode('utf-8')
            pt_url = f"https://{ip}:{port}/CustomerMediaWebService/consumers/{apt_str},{sid_str}/parktrans"
            return sess.post(pt_url, data=tx_xml, headers=_skidata_headers('application/xml'), verify=False, timeout=15)

        def _book_reentry(fac_id, comp_id, dev_id, entry_lpn, orig_time_str=''):
            tx_time = orig_time_str or datetime.datetime.now().astimezone().isoformat(timespec='milliseconds')
            lpn_tag = f'<lpn>{entry_lpn}</lpn>' if entry_lpn else ''
            tx_xml = (
                f'<?xml version="1.0" encoding="UTF-8"?>'
                f'<bookParkTransaction xmlns="{ns_uri}">'
                f'<enterParkTransaction>'
                f'<transactionTime>{tx_time}</transactionTime>'
                f'<transactionType>10</transactionType>'
                f'<facilityin>{fac_id}</facilityin><facilityout>0</facilityout>'
                f'<computer>{comp_id}</computer><device>{dev_id}</device><amount>0</amount>'
                f'<contractid>{apt_str}</contractid><consumerid>{sid_str}</consumerid>'
                f'{lpn_tag}'
                f'</enterParkTransaction>'
                f'</bookParkTransaction>'
            ).encode('utf-8')
            pt_url = f"https://{ip}:{port}/CustomerMediaWebService/consumers/{apt_str},{sid_str}/parktrans"
            return sess.post(pt_url, data=tx_xml, headers=_skidata_headers('application/xml'), verify=False, timeout=15)

        if not is_present:
            put_resp = sess.put(url, data=minimal_xml, headers=_skidata_headers('application/xml'), verify=False, timeout=15)
            if put_resp.status_code in (200, 201, 204):
                return {'success': True, 'message': 'מספרי הרכב עודכנו בהצלחה בחניון!'}
            return {'success': False, 'message': f'בקר החניון דחה את העדכון ({put_resp.status_code})'}

        # המנוי נמצא בחניון (is_present=True) -> בודקים איזה רכב ספציפי נמצא בחניון וכמה ימים עברו
        p_info = _get_subscriber_parked_info(sess, ip, port, apt_str, sid_str, cur_lpn1, cur_lpn2, cur_lpn3)
        parked_slot = p_info['parked_slot']
        parked_lpn = p_info['parked_lpn']
        days_in_parking = p_info['days_in_parking']
        fac_id, comp_id, dev_id = p_info['fac_id'], p_info['comp_id'], p_info['dev_id']

        slot_names = {'lpn1': 'רכב 1', 'lpn2': 'רכב 2', 'lpn3': 'רכב 3'}
        parked_label = slot_names.get(parked_slot, 'הרכב')

        # 1. האם המשתמש מנסה לשנות את הרכב הספציפי שנמצא כעת בחניון?
        if parked_slot in changed_tags:
            if days_in_parking < 7.0:
                plate_disp = f" ({parked_lpn})" if parked_lpn else ""
                return {
                    'success': False,
                    'error_code': 'CAR_IN_PARKING',
                    'parked_slot': parked_slot,
                    'parked_lpn': parked_lpn,
                    'days_in_parking': round(days_in_parking, 1),
                    'message': f'לא ניתן לשנות את {parked_label}{plate_disp} בזמן שהוא נמצא בחניון. ניתן לשנות את הרכבים האחרים במנוי שאינם בחניון (איפוס נוכחות אוטומטי מתאפשר רק אם הרכב תקוע בחניון מעל 7 ימים).'
                }
            # הרכב הספציפי נמצא בחניון כבר 7 ימים ומעלה -> מאפסים נוכחות ומעדכנים!
            exit_res = _book_exit(fac_id, comp_id, dev_id)
            if exit_res.status_code in (200, 201, 204):
                time.sleep(0.2)
                put_resp = sess.put(url, data=minimal_xml, headers=_skidata_headers('application/xml'), verify=False, timeout=15)
                if put_resp.status_code in (200, 201, 204):
                    return {'success': True, 'message': f'נוכחות {parked_label} (שהיה רשום בחניון מעל 7 ימים) אופסה ומספרי הרכב עודכנו בהצלחה!'}
            return {'success': False, 'message': f'לא ניתן להחליף את {parked_label} בזמן שהוא בחניון.'}

        # 2. המשתמש משנה רק רכב שאינו נמצא בחניון (למשל רכב 1 בחניון והמשתמש משנה את רכב 2 או 3, או להיפך)
        if 'lpn1' not in changed_tags:
            # שינוי של lpn2 / lpn3 בלבד נתמך ישירות בבקר ללא נגיעה בנוכחות
            put_resp = sess.put(url, data=minimal_xml, headers=_skidata_headers('application/xml'), verify=False, timeout=15)
            if put_resp.status_code in (200, 201, 204):
                return {'success': True, 'message': 'מספרי הרכב עודכנו בהצלחה בחניון!'}
            return {'success': False, 'message': f'בקר החניון דחה את העדכון ({put_resp.status_code})'}
        else:
            # רכב 2 או רכב 3 נמצא בחניון, והמשתמש משנה את רכב 1 (שאינו בחניון):
            # בקר שיידט דורש יציאה זמנית כדי לעדכן את השדה הראשי lpn1, ומיד מחזירים את הנוכחות לרכב שבחניון
            exit_res = _book_exit(fac_id, comp_id, dev_id)
            if exit_res.status_code in (200, 201, 204):
                time.sleep(0.15)
                put_resp = sess.put(url, data=minimal_xml, headers=_skidata_headers('application/xml'), verify=False, timeout=15)
                _book_reentry(fac_id, comp_id, dev_id, parked_lpn, p_info.get('entry_time_str', ''))
                if put_resp.status_code in (200, 201, 204):
                    return {'success': True, 'message': 'מספרי הרכב עודכנו בהצלחה בחניון!'}
            return {'success': False, 'message': 'לא ניתן לעדכן את מספר הרכב כעת.'}
    except Exception as e:
        return {'success': False, 'message': str(e)}

# ============================================================================
# 3. WHATSAPP NOTIFICATIONS HELPER & RATE-LIMITED BULK QUEUE (10 msgs / 10 sec)
# ============================================================================
import queue as _py_queue

_wa_bulk_queue = _py_queue.Queue()
_wa_bulk_worker_started = False
_wa_bulk_lock = threading.Lock()
_wa_bulk_stats = {
    'queued': 0,
    'sent': 0,
    'failed': 0,
    'in_progress': False,
    'last_sent_at': None
}

def send_whatsapp_message(phone_number, text_message):
    """שליחת הודעת וואטסאפ דרך GreenAPI הקיים במערכת."""
    try:
        import whatsapp_service
        green_id = whatsapp_service.GREEN_API_ID
        green_token = whatsapp_service.GREEN_API_TOKEN
        if not green_id or not green_token:
            print(f"[WhatsApp Mock] To {phone_number}: {text_message}")
            return False, "הגדרות GreenAPI חסרות"
        clean_p = clean_il_phone(phone_number)
        if not clean_p or len(clean_p) < 11:
            return False, "מספר טלפון חסר או לא תקין"
        url = f"https://api.green-api.com/waInstance{green_id}/sendMessage/{green_token}"
        resp = requests.post(url, json={"chatId": f"{clean_p}@c.us", "message": text_message}, timeout=10)
        return (resp.status_code == 200), resp.text
    except Exception as e:
        print(f"Error sending WhatsApp message: {e}")
        return False, str(e)

def _wa_bulk_worker_loop():
    """תהליכון רקע לשליחת הודעות וואטסאפ מרוכזות בקצב מבוקר: עד 10 הודעות ב-10 שניות (השהיה בין הודעות ובין קבוצות של 10)."""
    batch_counter = 0
    while True:
        item = _wa_bulk_queue.get()
        try:
            _wa_bulk_stats['in_progress'] = True
            phone, msg = item
            ok, _ = send_whatsapp_message(phone, msg)
            if ok:
                _wa_bulk_stats['sent'] += 1
            else:
                _wa_bulk_stats['failed'] += 1
            _wa_bulk_stats['last_sent_at'] = get_il_now().isoformat()
            batch_counter += 1

            # קצב מבוקר: 10 הודעות ב-10 שניות (1.0 שניה בין הודעה להודעה + עצירה נוספת כל 10 הודעות במידת הצורך)
            if not _wa_bulk_queue.empty():
                if batch_counter >= 10:
                    batch_counter = 0
                    time.sleep(2.0)
                else:
                    time.sleep(1.0)
            else:
                batch_counter = 0
                _wa_bulk_stats['in_progress'] = False
        except Exception as e:
            print(f"Bulk WhatsApp worker error: {e}")
        finally:
            _wa_bulk_queue.task_done()

def enqueue_bulk_whatsapp_messages(messages_list):
    """מוסיף רשימת הודעות [(phone, text), ...] לתור השליחה המבוקר ברקע (10 הודעות ב-10 שניות)."""
    global _wa_bulk_worker_started
    if not messages_list:
        return 0
    with _wa_bulk_lock:
        if not _wa_bulk_worker_started:
            _wa_bulk_worker_started = True
            t = threading.Thread(target=_wa_bulk_worker_loop, daemon=True)
            t.start()
    added = 0
    seen_phones = set()
    for phone, msg in messages_list:
        clean_p = clean_il_phone(phone)
        if not clean_p or len(clean_p) < 11 or clean_p in seen_phones:
            continue
        seen_phones.add(clean_p)
        _wa_bulk_queue.put((clean_p, msg))
        _wa_bulk_stats['queued'] += 1
        added += 1
    return added

# ============================================================================
# 4. QUOTA TRANSFER ENGINE & BACKGROUND SCHEDULER
# ============================================================================
def try_activate_transfer(transfer):
    """
    מנסה להפעיל העברת מונה (maxCounter):
    בודק אם בדירה המשחררת (from_apartment) יש מקום פנוי (presentCounter < maxCounter).
    אם כן -> מוריד 1 מהדירה המשחררת, מעלה 1 לדירה המזמינה, ושולח וואטסאפ שהחניה פנויה!
    אם לא -> מעביר לסטטוס WAITING_FOR_EXIT לבדיקה חוזרת.
    """
    t_id = transfer['id']
    p_num = transfer['project_number']
    from_apt = transfer['from_apartment']
    to_apt = transfer['to_apartment']
    now_iso = get_il_now().isoformat()

    # במתחם עצמאי (ללא בקר חניון): אין בדיקות נוכחות - מפעילים מיד עם הגעת שעת ההתחלה!
    if is_standalone_building(p_num):
        TenantStore.update_transfer(t_id, {
            'status': 'ACTIVE',
            'actual_activated_at': now_iso,
            'last_checked_at': now_iso,
            'notified_start': True
        })
        borrower_phone = transfer.get('borrower_phone')
        if borrower_phone:
            spot_no = (transfer.get('parking_spot_number') or '').strip()
            spot_line = f"🅿️ מספר חניה: *{spot_no}*\n" if spot_no else ""
            msg = (
                f"שלום {transfer.get('borrower_name') or ''}! 🚗\n"
                f"החניה שהזמנת (מדירה {from_apt}) פנויה וזמינה עבורך כעת ועד השעה *{transfer.get('end_time')}*.\n"
                f"{spot_line}"
                f"חניה נעימה!"
            )
            send_whatsapp_message(borrower_phone, msg)
        return {'activated': True, 'status': 'ACTIVE'}

    status_res = get_apartment_pooling_status(p_num, from_apt)
    if not status_res.get('success'):
        TenantStore.update_transfer(t_id, {'last_checked_at': now_iso})
        return {'activated': False, 'reason': 'connection_error', 'message': status_res.get('message')}

    max_c = status_res.get('maxCounter', 0)
    pres_c = status_res.get('presentCounter', 0)

    # בדיקה האם החניה פנויה בחניון (המנוי של הדירה המשחררת לא תופס את כל המכסה)
    if pres_c < max_c and max_c > 0:
        dec_res = adjust_apartment_max_counter(p_num, from_apt, -1)
        if not dec_res.get('success'):
            return {'activated': False, 'reason': 'decrement_failed', 'message': dec_res.get('message')}

        inc_res = adjust_apartment_max_counter(p_num, to_apt, +1)
        if not inc_res.get('success'):
            # Rollback decrement if increment failed
            adjust_apartment_max_counter(p_num, from_apt, +1)
            return {'activated': False, 'reason': 'increment_failed', 'message': inc_res.get('message')}

        TenantStore.update_transfer(t_id, {
            'status': 'ACTIVE',
            'actual_activated_at': now_iso,
            'last_checked_at': now_iso,
            'notified_start': True
        })

        # שליחת הודעת וואטסאפ לדייר שהחניה שלו פנויה וזמינה!
        borrower_phone = transfer.get('borrower_phone')
        if borrower_phone:
            spot_no = (transfer.get('parking_spot_number') or '').strip()
            spot_line = f"🅿️ מספר חניה: *{spot_no}*\n" if spot_no else ""
            msg = (
                f"שלום {transfer.get('borrower_name') or ''}! 🚗\n"
                f"החניה שהזמנת (מדירה {from_apt}) פנויה וזמינה עבורך כעת ועד השעה *{transfer.get('end_time')}*.\n"
                f"{spot_line}"
                f"מכסת החניות של דירה {to_apt} הוגדלה ב-1. חניה נעימה!"
            )
            send_whatsapp_message(borrower_phone, msg)

        return {'activated': True, 'status': 'ACTIVE'}
    else:
        # הרכב של הדירה המשחררת עדיין בחניון - ממתינים ליציאה ובודקים שוב בהמשך
        TenantStore.update_transfer(t_id, {
            'status': 'WAITING_FOR_EXIT',
            'last_checked_at': now_iso
        })
        return {'activated': False, 'status': 'WAITING_FOR_EXIT', 'reason': 'owner_still_in_parking'}

def restore_active_transfer(transfer, early_cancel=False):
    """מחזיר את המונה (maxCounter) מהדירה השואלת חזרה לדירה המשחררת בסיום הזמן או בביטול."""
    t_id = transfer['id']
    p_num = transfer['project_number']
    from_apt = transfer['from_apartment']
    to_apt = transfer['to_apartment']
    cur_status = transfer.get('status')
    now_iso = get_il_now().isoformat()

    if cur_status == 'ACTIVE':
        if is_standalone_building(p_num):
            TenantStore.update_transfer(t_id, {
                'status': 'CANCELLED' if early_cancel else 'RESTORED',
                'actual_restored_at': now_iso,
                'late_exit_flag': False
            })
            return True

        # בדיקה האם הדייר השואל איחר בפינוי החניה
        late_flag = False
        if not early_cancel:
            to_status = get_apartment_pooling_status(p_num, to_apt)
            if to_status.get('success'):
                if to_status.get('presentCounter', 0) >= to_status.get('maxCounter', 1):
                    late_flag = True

        # הורדת 1 מהדירה השואלת והחזרת 1 לדירה המשחררת
        adjust_apartment_max_counter(p_num, to_apt, -1)
        adjust_apartment_max_counter(p_num, from_apt, +1)

        TenantStore.update_transfer(t_id, {
            'status': 'CANCELLED' if early_cancel else 'RESTORED',
            'actual_restored_at': now_iso,
            'late_exit_flag': late_flag
        })
        return True
    else:
        TenantStore.update_transfer(t_id, {
            'status': 'CANCELLED' if early_cancel else 'EXPIRED',
            'actual_restored_at': now_iso
        })
        return True

_last_scheduler_run_ts = 0.0

def run_scheduler_cycle(min_interval_sec=0):
    """רץ ברקע כל דקה: מפעיל חניות שהגיע זמנן, שולח תזכורת 30 דק' לפני סיום, ומחזיר מונים בסיום."""
    global _last_scheduler_run_ts
    now_ts = time.time()
    if min_interval_sec > 0 and (now_ts - _last_scheduler_run_ts) < min_interval_sec:
        return
    _last_scheduler_run_ts = now_ts
    try:
        now = get_il_now()
        active_or_pending = TenantStore.list_transfers(statuses=['SCHEDULED', 'WAITING_FOR_EXIT', 'ACTIVE'])
        settings_cache = {}

        for tr in active_or_pending:
            p_num = tr['project_number']
            if p_num not in settings_cache:
                settings_cache[p_num] = TenantStore.get_building_settings(p_num)
            b_settings = settings_cache[p_num]
            check_interval_mins = int(b_settings.get('check_interval_minutes') or 30)
            reminder_mins = int(b_settings.get('reminder_minutes_before') or 30)

            try:
                w_start = datetime.datetime.fromisoformat(str(tr['window_start']).replace('Z', ''))
                w_end = datetime.datetime.fromisoformat(str(tr['window_end']).replace('Z', ''))
            except Exception:
                continue

            status = tr.get('status')

            # 1. האם הגיע זמן הסיום?
            if now >= w_end:
                restore_active_transfer(tr, early_cancel=False)
                continue

            # 2. אם ההזמנה בסטטוס SCHEDULED או WAITING_FOR_EXIT והחלון פעיל כעת
            if status in ('SCHEDULED', 'WAITING_FOR_EXIT') and w_start <= now < w_end:
                should_check = True
                if status == 'WAITING_FOR_EXIT' and tr.get('last_checked_at'):
                    try:
                        last_chk = datetime.datetime.fromisoformat(str(tr['last_checked_at']).replace('Z', ''))
                        if (now - last_chk).total_seconds() < (check_interval_mins * 60):
                            should_check = False
                    except Exception:
                        pass
                if should_check:
                    try_activate_transfer(tr)

            # 3. אם ההזמנה בסטטוס ACTIVE ונותרו 30 דקות (או פחות) לסיום - שלח תזכורת וואטסאפ!
            elif status == 'ACTIVE' and not tr.get('notified_ending_soon'):
                mins_left = (w_end - now).total_seconds() / 60.0
                if 0 < mins_left <= reminder_mins:
                    borrower_phone = tr.get('borrower_phone')
                    if borrower_phone:
                        msg = (
                            f"⏰ תזכורת לדירה {tr.get('to_apartment')}:\n"
                            f"חלון הזמן של החניה ששאלת מדירה {tr.get('from_apartment')} מסתיים בעוד כ-{int(round(mins_left))} דקות (בשעה *{tr.get('end_time')}*).\n"
                            f"נא לשחרר את החניה בזמן."
                        )
                        send_whatsapp_message(borrower_phone, msg)
                    TenantStore.update_transfer(tr['id'], {'notified_ending_soon': True})
    except Exception as e:
        print(f"[TenantScheduler] Error in cycle: {e}")

_scheduler_started = False

def start_tenant_scheduler():
    global _scheduler_started
    if _scheduler_started:
        return
    _scheduler_started = True

    def _loop():
        while True:
            time.sleep(60)
            run_scheduler_cycle()

    t = threading.Thread(target=_loop, daemon=True)
    t.start()

start_tenant_scheduler()

# ============================================================================
# 5. TENANT MANAGER ROUTES (ממשק מנהל המתחם - כניסה רגילה עם קוד אימות במייל)
# ============================================================================
SESSION_INACTIVITY_TIMEOUT_SEC = 30 * 60  # 30 דקות ללא פעילות

def _get_logged_in_tenant_manager():
    if 'user_email' not in session:
        return None
    now_ts = time.time()
    last_act = session.get('tm_last_activity')
    if last_act and (now_ts - float(last_act) > SESSION_INACTIVITY_TIMEOUT_SEC):
        session.clear()
        return None
    session['tm_last_activity'] = now_ts
    sb = _get_raw_supabase()
    if not sb:
        return {'email': session['user_email'], 'project_number': '1000', 'parking_name': 'מתחם מגורים', 'code_type': 'tenant_manager'}
    try:
        res = sb.table('user_parkings').select('user_id, username, email, code_type, project_number, parking_name, company_type').eq('email', session['user_email']).execute()
        if res.data:
            u = res.data[0]
            ct = str(u.get('code_type') or '').strip().lower().replace('-', '_')
            if ct in ('tenant_manager', 'master', 'parking_manager'):
                return u
    except Exception as e:
        print(f"Error checking tenant manager session: {e}")
    return None

@tenant_bp.route('/tenant-manager')
def tenant_manager_page():
    mgr = _get_logged_in_tenant_manager()
    if not mgr:
        return redirect('/login')
    return render_template('tenant_manager.html')

def _calc_transfer_used_hours(tr):
    """מחשב שעות חניה שנתן הדייר ושנוצלו בפועל (רק כאשר הסטטוס ACTIVE או RESTORED)."""
    if tr.get('status') not in ('ACTIVE', 'RESTORED'):
        return 0.0
    win_hours = 0.0
    try:
        ws = datetime.datetime.fromisoformat(str(tr['window_start']).replace('Z', ''))
        we = datetime.datetime.fromisoformat(str(tr['window_end']).replace('Z', ''))
        win_hours = max(0.0, (we - ws).total_seconds() / 3600.0)
    except Exception:
        pass
    if tr.get('actual_activated_at') and tr.get('actual_restored_at'):
        try:
            act_s = datetime.datetime.fromisoformat(str(tr['actual_activated_at']).replace('Z', ''))
            act_e = datetime.datetime.fromisoformat(str(tr['actual_restored_at']).replace('Z', ''))
            act_h = max(0.1, (act_e - act_s).total_seconds() / 3600.0)
            if win_hours > 0:
                return round(min(win_hours, act_h), 1)
            return round(act_h, 1)
        except Exception:
            pass
    return round(win_hours, 1)

@tenant_bp.route('/api/tenant-manager/init', methods=['GET'])
def api_tenant_manager_init():
    mgr = _get_logged_in_tenant_manager()
    if not mgr:
        return jsonify({'success': False, 'message': 'לא מחובר או אין הרשאת מנהל מתחם'}), 401

    p_num = str(mgr.get('project_number') or '')
    p_name = mgr.get('parking_name') or f'מתחם {p_num}'
    run_scheduler_cycle()
    b_settings = TenantStore.get_building_settings(p_num, p_name)
    tenants = TenantStore.list_tenants(p_num)
    shares = TenantStore.list_shares(p_num, active_only=True)
    active_transfers = TenantStore.list_transfers(
        project_number=p_num,
        statuses=['SCHEDULED', 'WAITING_FOR_EXIT', 'ACTIVE']
    )

    # חישוב שעות שכל דירה נתנה ושנוצלו בפועל (ACTIVE / RESTORED) להצגת כוכב ⭐ ליד כל דייר
    used_transfers = TenantStore.list_transfers(
        project_number=p_num,
        statuses=['ACTIVE', 'RESTORED']
    )
    cur_month = get_il_now().strftime('%Y-%m')
    apt_used_total = {}
    apt_used_month = {}
    apt_used_count = {}
    for tr in used_transfers:
        f_apt = str(tr.get('from_apartment') or '').strip()
        if not f_apt:
            continue
        hrs = _calc_transfer_used_hours(tr)
        apt_used_total[f_apt] = round(apt_used_total.get(f_apt, 0.0) + hrs, 1)
        apt_used_count[f_apt] = apt_used_count.get(f_apt, 0) + 1
        if str(tr.get('booking_date') or '').startswith(cur_month):
            apt_used_month[f_apt] = round(apt_used_month.get(f_apt, 0.0) + hrs, 1)

    for t in tenants:
        apt_k = str(t.get('apartment_number') or '').strip()
        t['given_used_hours_total'] = apt_used_total.get(apt_k, 0.0)
        t['given_used_hours_month'] = apt_used_month.get(apt_k, 0.0)
        t['given_used_count'] = apt_used_count.get(apt_k, 0)

    return jsonify({
        'success': True,
        'manager': {
            'username': mgr.get('username'),
            'email': mgr.get('email'),
            'project_number': p_num,
            'parking_name': b_settings.get('parking_name') or p_name
        },
        'settings': b_settings,
        'standalone_mode': is_standalone_building(p_num),
        'tenants': tenants,
        'shares': shares,
        'active_transfers': active_transfers
    })

def _build_tenant_invite_whatsapp_text(host_url, project_number, parking_name, full_name, apartment_number, clean_phone):
    disp_p = display_il_phone(clean_phone)
    portal_link = f"{host_url}/tenant-portal?phone={disp_p}"
    ios_link = f"{host_url}/app/ios?project={project_number}"
    android_link = f"{host_url}/app/android?project={project_number}"
    return (
        f"שלום {full_name}! 🏢\n"
        f"צורפת למערכת ניהול ושיתוף החניות של *{parking_name or 'המתחם'}* (דירה {apartment_number}).\n\n"
        f"📱 *להורדת אפליקציית הדיירים:*\n"
        f"🍎 לאייפון (Apple): {ios_link}\n"
        f"🤖 לאנדרואיד (Google): {android_link}\n\n"
        f"🌐 *או לכניסה ישירה דרך הדפדפן:*\n"
        f"{portal_link}"
    )

@tenant_bp.route('/api/tenant-manager/settings', methods=['POST'])
def api_tenant_manager_save_settings():
    mgr = _get_logged_in_tenant_manager()
    if not mgr:
        return jsonify({'success': False, 'message': 'לא מורשה'}), 401
    data = request.get_json() or {}
    p_num = str(mgr.get('project_number') or '')
    saved = TenantStore.save_building_settings(
        project_number=p_num,
        parking_name=data.get('parking_name') or mgr.get('parking_name') or '',
        max_day=data.get('max_bookings_per_day', 5),
        max_month=data.get('max_bookings_per_month', 30),
        check_interval=data.get('check_interval_minutes', 30),
        reminder_mins=data.get('reminder_minutes_before', 30),
        logo_data=data.get('logo_data'),
        parking_lat=data.get('parking_lat'),
        parking_lng=data.get('parking_lng'),
        parking_address=data.get('parking_address'),
        standalone_mode=data.get('standalone_mode'),
        ios_app_url=data.get('ios_app_url'),
        android_app_url=data.get('android_app_url')
    )
    return jsonify({'success': True, 'message': 'הגדרות המתחם נשמרו בהצלחה', 'settings': saved})

@tenant_bp.route('/api/tenant-manager/tenants', methods=['POST'])
def api_tenant_manager_create_tenant():
    mgr = _get_logged_in_tenant_manager()
    if not mgr:
        return jsonify({'success': False, 'message': 'לא מורשה'}), 401
    data = request.get_json() or {}
    full_name = (data.get('full_name') or '').strip()
    phone = (data.get('phone_number') or '').strip()
    apt = str(data.get('apartment_number') or '').strip()

    if not full_name or not phone or not apt:
        return jsonify({'success': False, 'message': 'חובה למלא שם דייר, מספר נייד ומספר דירה'})

    clean_p = clean_il_phone(phone)
    if len(clean_p) < 11:
        return jsonify({'success': False, 'message': 'מספר טלפון נייד לא תקין'})

    p_num = str(mgr.get('project_number') or '')
    p_name = mgr.get('parking_name') or ''

    with _action_dedup_lock:
        # מניעת הקמה כפולה של אותו דייר בלחיצה כפולה (אותו טלפון באותו מתחם)
        existing_tenants = TenantStore.list_tenants(p_num)
        empty_phone_apt_row = None
        for ex in existing_tenants:
            ex_phone = clean_il_phone(ex.get('phone_number'))
            if ex_phone and ex_phone == clean_p:
                if str(ex.get('apartment_number') or '').strip() == apt:
                    return jsonify({
                        'success': True,
                        'deduplicated': True,
                        'message': f'דייר (דירה {apt} - {ex.get("full_name")}) כבר קיים במערכת!',
                        'tenant': ex
                    })
                return jsonify({
                    'success': False,
                    'message': f'מספר הטלפון {display_il_phone(clean_p)} כבר רשום במערכת עבור דירה {ex.get("apartment_number")} ({ex.get("full_name")})'
                })
            if not ex_phone and str(ex.get('apartment_number') or '').strip() == apt:
                empty_phone_apt_row = ex

        is_zero_spot = bool(data.get('is_zero_spot'))
        if is_zero_spot:
            set_apartment_zero_spot_mode(p_num, apt, True)
            base_max = 0
        else:
            # נסה לשלוף את מכסת החניות הקבועה של הדירה מתוך שיידט (אם החוזה חסום status=2 יחזור 0)
            pool_info = get_apartment_pooling_status(p_num, apt)
            if pool_info.get('success'):
                base_max = int(pool_info.get('maxCounter') or 0)
            else:
                raw_bm = data.get('base_max_counter')
                base_max = 1 if raw_bm is None else int(raw_bm)

        if empty_phone_apt_row:
            TenantStore.update_tenant(
                tenant_id=empty_phone_apt_row['id'],
                full_name=full_name,
                phone_number=clean_p,
                apartment_number=apt,
                base_max_counter=base_max,
                is_active=True
            )
            tenant = dict(empty_phone_apt_row)
            tenant['full_name'] = full_name
            tenant['phone_number'] = clean_p
            tenant['base_max_counter'] = base_max
        else:
            tenant = TenantStore.create_tenant(
                project_number=p_num,
                parking_name=p_name,
                full_name=full_name,
                phone_number=clean_p,
                apartment_number=apt,
                base_max_counter=base_max,
                created_by=mgr.get('email')
            )

    # שליחת הודעת וואטסאפ אוטומטית לדייר החדש עם קישורים לאייפון, לגוגל ולאתר
    host_url = request.host_url.rstrip('/')
    welcome_msg = _build_tenant_invite_whatsapp_text(host_url, p_num, p_name, full_name, apt, clean_p)
    wa_ok, _ = send_whatsapp_message(clean_p, welcome_msg)
    wa_note = " (נשלחה הודעת וואטסאפ עם קישור לדייר)" if wa_ok else " (הדייר נשמר, אך שליחת וואטסאפ נכשלה)"

    return jsonify({'success': True, 'message': f'דייר (דירה {apt}) נוסף בהצלחה!{wa_note}', 'tenant': tenant, 'whatsapp_sent': wa_ok})

@tenant_bp.route('/api/tenant-manager/tenants/<int:tenant_id>/send-invite', methods=['POST'])
def api_tenant_manager_send_invite(tenant_id):
    mgr = _get_logged_in_tenant_manager()
    if not mgr:
        return jsonify({'success': False, 'message': 'לא מורשה'}), 401
    t = TenantStore.get_tenant_by_id(tenant_id)
    p_num = str(mgr.get('project_number') or '')
    if not t or str(t.get('project_number') or '') != p_num:
        return jsonify({'success': False, 'message': 'דייר לא נמצא במתחם שלך'}), 404
    host_url = request.host_url.rstrip('/')
    clean_p = clean_il_phone(t.get('phone_number'))
    p_name = t.get('parking_name') or mgr.get('parking_name') or 'המתחם'
    msg = _build_tenant_invite_whatsapp_text(host_url, p_num, p_name, t.get('full_name'), t.get('apartment_number'), clean_p)
    wa_ok, wa_err = send_whatsapp_message(clean_p, msg)
    if wa_ok:
        return jsonify({'success': True, 'message': f'הודעת וואטסאפ עם קישור נשלחה ל-{t.get("full_name")}!'})
    return jsonify({'success': False, 'message': f'שגיאה בשליחת וואטסאפ: {wa_err}'})

@tenant_bp.route('/api/tenant-manager/tenants/<int:tenant_id>/refresh-quota', methods=['POST'])
def api_tenant_manager_refresh_quota(tenant_id):
    """רענון כמות החניות (maxCounter ו-presentCounter) של דירה ספציפית ישירות מבקר החניון (שיידט את בכמן)."""
    mgr = _get_logged_in_tenant_manager()
    if not mgr:
        return jsonify({'success': False, 'message': 'לא מורשה'}), 401
    t = TenantStore.get_tenant_by_id(tenant_id)
    p_num = str(mgr.get('project_number') or '')
    if not t or str(t.get('project_number') or '') != p_num:
        return jsonify({'success': False, 'message': 'דייר לא נמצא במתחם שלך'}), 404

    apt = str(t.get('apartment_number') or '').strip()
    pool_info = get_apartment_pooling_status(p_num, apt)
    if not pool_info.get('success'):
        return jsonify({
            'success': False,
            'message': f'לא ניתן למשוך נתונים מבקר החניון עבור דירה {apt}: {pool_info.get("message")}'
        })

    new_max = int(pool_info.get('maxCounter') or 0)
    pres_c = int(pool_info.get('presentCounter') or 0)
    TenantStore.update_tenant(
        tenant_id=tenant_id,
        full_name=t.get('full_name', ''),
        phone_number=t.get('phone_number', ''),
        apartment_number=apt,
        base_max_counter=new_max,
        is_active=t.get('is_active', True)
    )
    return jsonify({
        'success': True,
        'apartment_number': apt,
        'base_max_counter': new_max,
        'present_counter': pres_c,
        'contract_name': pool_info.get('contractName', ''),
        'message': f'דירה {apt} רועננה מהחניון: {new_max} חניות מוגדרות ({pres_c} רכבים בחניון כעת)'
    })

@tenant_bp.route('/api/tenant-manager/refresh-all-quotas', methods=['POST'])
def api_tenant_manager_refresh_all_quotas():
    """רענון כמות החניות מבקר החניון עבור כל הדירות במתחם."""
    mgr = _get_logged_in_tenant_manager()
    if not mgr:
        return jsonify({'success': False, 'message': 'לא מורשה'}), 401
    p_num = str(mgr.get('project_number') or '')
    tenants = TenantStore.list_tenants(p_num)
    updated_count = 0
    live_status = {}
    for t in tenants:
        apt = str(t.get('apartment_number') or '').strip()
        if not apt:
            continue
        if apt not in live_status:
            live_status[apt] = get_apartment_pooling_status(p_num, apt)
        p_info = live_status[apt]
        if p_info.get('success'):
            new_max = int(p_info.get('maxCounter') or 0)
            TenantStore.update_tenant(
                tenant_id=t['id'],
                full_name=t.get('full_name', ''),
                phone_number=t.get('phone_number', ''),
                apartment_number=apt,
                base_max_counter=new_max,
                is_active=t.get('is_active', True)
            )
            updated_count += 1
    return jsonify({
        'success': True,
        'updated_count': updated_count,
        'live_status': live_status,
        'message': f'רועננו בהצלחה נתוני החניות עבור {updated_count} דיירים מתוך בקר החניון!'
    })

@tenant_bp.route('/api/tenant-manager/import-apartments', methods=['POST'])
def api_tenant_manager_import_apartments():
    """טעינת דירות (חוזים) מבקר החניון עם קוד אבטחה מיוחד (1qaz@WSX):
    אם הדירה כבר קיימת - מעדכן בלבד (כמות חניות ושם אם חסר) ולא דורס מספרי טלפון קיימים!
    אם הדירה לא קיימת - מקים אותה במערכת."""
    mgr = _get_logged_in_tenant_manager()
    if not mgr:
        return jsonify({'success': False, 'message': 'לא מורשה'}), 401

    data = request.get_json() or {}
    special_code = str(data.get('special_code') or '').strip()
    if special_code != '1qaz@WSX':
        return jsonify({'success': False, 'message': 'קוד מיוחד שגוי! טעינת הדירות לא אושרה.'})

    p_num = str(mgr.get('project_number') or '')
    p_name = mgr.get('parking_name') or ''
    conn = _get_parking_conn(p_num)
    if not conn or not conn.get('ip_address'):
        return jsonify({'success': False, 'message': 'לא נמצאו פרטי חיבור לבקר החניון עבור מתחם זה'})

    ip = conn['ip_address']
    port = conn.get('port', 8443)
    contracts_url = f"https://{ip}:{port}/CustomerMediaWebService/contracts"

    try:
        sess = _get_http_session()
        resp = sess.get(contracts_url, headers=_skidata_headers(), verify=False, timeout=20)
        if resp.status_code != 200:
            return jsonify({'success': False, 'message': f'שגיאה במשיכת רשימת דירות מבקר החניון (HTTP {resp.status_code})'})
        resp.encoding = 'utf-8'
        root = ET.fromstring(resp.content)
        ns = {'ns': 'http://gsph.sub.com/cust/types'}
        contracts_list = []
        for c_el in root.findall('.//ns:contract', ns):
            cid = (c_el.findtext('ns:id', default='', namespaces=ns) or '').strip()
            cname = (c_el.findtext('ns:name', default='', namespaces=ns) or '').strip()
            if cid:
                contracts_list.append({'apt': cid, 'name': cname})
        # Fallback if namespace differs
        if not contracts_list:
            for elem in root.iter():
                tname = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
                if tname == 'contract':
                    cid = ''
                    cname = ''
                    for child in elem:
                        ctag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
                        if ctag == 'id' and child.text:
                            cid = child.text.strip()
                        elif ctag == 'name' and child.text:
                            cname = child.text.strip()
                    if cid:
                        contracts_list.append({'apt': cid, 'name': cname})
    except Exception as e:
        return jsonify({'success': False, 'message': f'שגיאת תקשורת מול בקר החניון: {e}'})

    if not contracts_list:
        return jsonify({'success': False, 'message': 'לא נמצאו דירות (חוזים) בבקר החניון'})

    import concurrent.futures
    pool_results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
        fut_map = {ex.submit(get_apartment_pooling_status, p_num, item['apt']): item['apt'] for item in contracts_list}
        for fut in concurrent.futures.as_completed(fut_map):
            apt_k = fut_map[fut]
            try:
                pool_results[apt_k] = fut.result()
            except Exception:
                pool_results[apt_k] = {'success': False}

    with _action_dedup_lock:
        existing_tenants = TenantStore.list_tenants(p_num)
        by_apt = {}
        for t in existing_tenants:
            a_str = str(t.get('apartment_number') or '').strip()
            if a_str:
                by_apt.setdefault(a_str, []).append(t)

        added_count = 0
        updated_count = 0
        live_status = {}

        for item in contracts_list:
            apt_str = str(item['apt']).strip()
            c_name = (item.get('name') or '').strip()
            p_info = pool_results.get(apt_str) or {}
            if p_info.get('success'):
                live_status[apt_str] = p_info
                max_c = int(p_info.get('maxCounter') or 0)
                if not c_name and p_info.get('contractName'):
                    c_name = str(p_info.get('contractName')).strip()
            else:
                max_c = 1

            final_name = c_name or f'דירה {apt_str}'

            if apt_str in by_apt:
                # הדירה כבר קיימת - עדכן בלבד ושמור על מספרי הטלפון הקיימים!
                for ex_t in by_apt[apt_str]:
                    existing_phone = ex_t.get('phone_number') or ''
                    existing_name = (ex_t.get('full_name') or '').strip()
                    # אם כבר יש שם ספציפי שהוזן ע"י המנהל נשמור עליו; אם היה ריק או גנרי ("דירה X") נעדכן לשם מהבקר
                    if not existing_name or existing_name == f'דירה {apt_str}':
                        name_to_keep = final_name
                    else:
                        name_to_keep = existing_name
                    TenantStore.update_tenant(
                        tenant_id=ex_t['id'],
                        full_name=name_to_keep,
                        phone_number=existing_phone,
                        apartment_number=apt_str,
                        base_max_counter=max_c,
                        is_active=ex_t.get('is_active', True)
                    )
                updated_count += 1
            else:
                # דירה חדשה - הקם אותה ללא דריסת דירות קיימות
                TenantStore.create_tenant(
                    project_number=p_num,
                    parking_name=p_name,
                    full_name=final_name,
                    phone_number='',
                    apartment_number=apt_str,
                    base_max_counter=max_c,
                    created_by=mgr.get('email')
                )
                added_count += 1

    return jsonify({
        'success': True,
        'added_count': added_count,
        'updated_count': updated_count,
        'live_status': live_status,
        'message': f'טעינת דירות הושלמה בהצלחה! נוספו {added_count} דירות חדשות ועודכנו {updated_count} דירות קיימות (מספרי הטלפון הקיימים נשמרו ללא שינוי).'
    })

def _parse_uploaded_apartments_table(file_storage):
    """קורא קובץ Excel (.xlsx) או CSV של רשימת דירות, שמות, רכבים (1-3) ומספרי חניה."""
    import io, csv
    filename = (file_storage.filename or '').lower()
    raw_bytes = file_storage.read()
    rows_2d = []

    if filename.endswith('.xlsx') or filename.endswith('.xls'):
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(raw_bytes), data_only=True)
        ws = wb.active
        for row in ws.iter_rows(values_only=True):
            if any(c is not None and str(c).strip() != '' for c in row):
                rows_2d.append([str(c).strip() if c is not None else '' for c in row])
    else:
        text = None
        for enc in ('utf-8-sig', 'utf-8', 'cp1255', 'iso-8859-8'):
            try:
                text = raw_bytes.decode(enc)
                break
            except Exception:
                continue
        if text is None:
            text = raw_bytes.decode('utf-8', errors='replace')
        reader = csv.reader(io.StringIO(text))
        for r in reader:
            if any(str(c).strip() != '' for c in r):
                rows_2d.append([str(c).strip() for c in r])

    if not rows_2d:
        return []

    header = [h.strip() for h in rows_2d[0]]
    has_header = any(
        any(k in h for k in ('דירה', 'משפחה', 'שם', 'רכב', 'חניה', 'טלפון', 'נייד', 'apartment', 'name', 'car', 'spot', 'phone'))
        for h in header
    )

    col_map = {
        'apt': 0,
        'last_name': 1,
        'first_name': 2,
        'plate_1': 3,
        'plate_2': 4,
        'plate_3': 5,
        'spot': 6,
        'phone': 7
    }

    if has_header:
        custom_map = {}
        car_cols = []
        for idx, h in enumerate(header):
            hl = h.lower()
            if ('דירה' in hl or 'חברה' in hl or 'apt' in hl or 'apartment' in hl) and 'apt' not in custom_map:
                custom_map['apt'] = idx
            elif ('משפחה' in hl or 'last' in hl or 'family' in hl) and 'last_name' not in custom_map:
                custom_map['last_name'] = idx
            elif ('פרטי' in hl or 'שם' in hl or 'first' in hl or 'name' in hl) and 'first_name' not in custom_map:
                custom_map['first_name'] = idx
            elif ('חניה' in hl or 'מקום' in hl or 'spot' in hl or 'parking' in hl) and 'spot' not in custom_map:
                custom_map['spot'] = idx
            elif ('טלפון' in hl or 'נייד' in hl or 'phone' in hl or 'mobile' in hl) and 'phone' not in custom_map:
                custom_map['phone'] = idx
            elif 'רכב' in hl or 'רישוי' in hl or 'car' in hl or 'plate' in hl:
                car_cols.append(idx)
        if len(car_cols) >= 1:
            custom_map['plate_1'] = car_cols[0]
        if len(car_cols) >= 2:
            custom_map['plate_2'] = car_cols[1]
        if len(car_cols) >= 3:
            custom_map['plate_3'] = car_cols[2]
        if 'apt' in custom_map:
            col_map.update(custom_map)
        data_rows = rows_2d[1:]
    else:
        data_rows = rows_2d

    def _val(r, key):
        idx = col_map.get(key)
        if idx is None or idx >= len(r):
            return ''
        v = str(r[idx] or '').strip()
        if v.endswith('.0') and v[:-2].isdigit():
            v = v[:-2]
        return v

    parsed = []
    for r in data_rows:
        apt = _val(r, 'apt')
        if not apt:
            continue
        parsed.append({
            'apartment_number': apt,
            'last_name': _val(r, 'last_name'),
            'family_name': _val(r, 'last_name'),
            'first_name': _val(r, 'first_name'),
            'lpn1': re.sub(r'[^0-9A-Za-zמ]', '', _val(r, 'plate_1')),
            'lpn2': re.sub(r'[^0-9A-Za-zמ]', '', _val(r, 'plate_2')),
            'lpn3': re.sub(r'[^0-9A-Za-zמ]', '', _val(r, 'plate_3')),
            'plate_1': re.sub(r'[^0-9A-Za-zמ]', '', _val(r, 'plate_1')),
            'plate_2': re.sub(r'[^0-9A-Za-zמ]', '', _val(r, 'plate_2')),
            'plate_3': re.sub(r'[^0-9A-Za-zמ]', '', _val(r, 'plate_3')),
            'parking_spot': _val(r, 'spot'),
            'parking_spot_number': _val(r, 'spot'),
            'phone_number': _val(r, 'phone')
        })
    return parsed

@tenant_bp.route('/api/tenant-manager/sample-apartments-csv', methods=['GET'])
def api_tenant_manager_sample_apartments_csv():
    """הורדת קובץ תבנית CSV לדוגמה לטעינת דירות, רכבים וחניות (ללא מערכת חניון)."""
    import io, csv
    from flask import Response
    output = io.StringIO()
    output.write('\ufeff')  # UTF-8 BOM for Excel Hebrew support
    writer = csv.writer(output)
    writer.writerow(['מספר דירה', 'שם משפחה', 'שם פרטי', 'רכב 1', 'רכב 2', 'רכב 3', 'מספר חניה', 'טלפון נייד'])
    writer.writerow(['301', 'פרינץ', 'דרור', '12345678', '', '', '28ג', '0525551234'])
    writer.writerow(['301', 'פרינץ', 'עלמה', '23456789', '', '', '33-2', ''])
    writer.writerow(['302', 'פזרקן', 'משפחת פזרקן', '87654321', '11223344', '', '', '0501234567'])
    csv_data = output.getvalue().encode('utf-8')
    return Response(
        csv_data,
        mimetype='text/csv; charset=utf-8',
        headers={'Content-Disposition': 'attachment; filename="apartments_template.csv"'}
    )

@tenant_bp.route('/api/tenant-manager/upload-apartments-file', methods=['POST'])
def api_tenant_manager_upload_apartments_file():
    """טעינת קובץ דירות, רכבים ומספרי חניה (חניון עצמאי ללא בקר שיידט ובכמן). מוגן בסיסמה מיוחדת 1qaz@WSX."""
    mgr = _get_logged_in_tenant_manager()
    if not mgr:
        return jsonify({'success': False, 'message': 'לא מורשה'}), 401

    special_pwd = (request.form.get('special_password') or '').strip()
    if special_pwd != '1qaz@WSX':
        return jsonify({'success': False, 'message': 'סיסמת ההרשאה לטעינת קובץ דירות שגויה'}), 403

    f = request.files.get('file')
    if not f or not f.filename:
        return jsonify({'success': False, 'message': 'נא לבחור קובץ אקסל (.xlsx) או CSV לטעינה'}), 400

    p_num = str(mgr.get('project_number') or '').strip()
    p_name = mgr.get('parking_name') or ''

    try:
        rows = _parse_uploaded_apartments_table(f)
    except Exception as e:
        return jsonify({'success': False, 'message': f'שגיאה בקריאת הקובץ: {str(e)}'}), 400

    if not rows:
        return jsonify({'success': False, 'message': 'לא נמצאו שורות תקינות בקובץ'}), 400

    # קיבוץ שורות לפי מספר דירה (דירה עם 2 חניות יכולה להופיע ב-2 שורות בקובץ)
    by_apt = {}
    for r in rows:
        apt_str = str(r['apartment_number']).strip()
        by_apt.setdefault(apt_str, []).append(r)

    added_count = 0
    updated_count = 0
    total_subscribers = 0
    send_welcome_flag = str(request.form.get('send_welcome_whatsapp') or '').strip().lower() in ('1', 'true', 'yes', 'on')
    host_url = request.host_url.rstrip('/')
    wa_queue_items = []

    with _action_dedup_lock:
        # הפעלת מצב עצמאי (ללא בקר חניון) עבור הבניין
        TenantStore.save_building_settings(
            project_number=p_num,
            parking_name=p_name,
            standalone_mode=True
        )

        existing_tenants = TenantStore.list_tenants(p_num)
        by_apt_existing = {}
        for t in existing_tenants:
            ak = str(t.get('apartment_number') or '').strip()
            if ak:
                by_apt_existing.setdefault(ak, []).append(t)

        # שמירה מרוכזת (Batch) של כל המנויים והרכבים של הדירות בקובץ בבת אחת (ביצועים מהירים גם ל-400 דירות!)
        TenantStore.bulk_upsert_local_subscribers_for_project(p_num, by_apt)

        for apt_str, apt_rows in by_apt.items():
            total_subscribers += len(apt_rows)

            # חישוב כמות החניות הקבועות של הדירה:
            # אם יש מספרי חניה מוגדרים בשורות - כמות החניות היא כמות השורות עם מספר חניה;
            # אם באף שורה של הדירה אין מספר חניה - במידה וכתוב "0" או ריק נחשיב לפי שורות עם חניה (או 1 אם יש שורה רגילה, או 0 אם צוין 0)
            spots_defined = [r for r in apt_rows if r.get('parking_spot_number') and str(r.get('parking_spot_number')).strip() not in ('0', '-')]
            explicit_zero = any(str(r.get('parking_spot_number') or '').strip() == '0' for r in apt_rows)
            if explicit_zero and not spots_defined:
                max_c = 0
            elif spots_defined:
                max_c = len(spots_defined)
            else:
                max_c = len(apt_rows)

            first_row = apt_rows[0]
            fam = (first_row.get('last_name') or '').strip()
            fn = (first_row.get('first_name') or '').strip()
            display_name = f"{fn} {fam}".strip() if (fn or fam) else f"דירה {apt_str}"
            file_phone = clean_il_phone(first_row.get('phone_number') or '')

            if apt_str in by_apt_existing:
                for ex_t in by_apt_existing[apt_str]:
                    cur_name = (ex_t.get('full_name') or '').strip()
                    final_name = cur_name if (cur_name and not cur_name.startswith('דירה ')) else display_name
                    # שמירה על מספר הטלפון הקיים! אם לא היה טלפון כלל ויש בקובץ - נעדכן מהקובץ
                    existing_phone = (ex_t.get('phone_number') or '').strip()
                    final_phone = existing_phone if existing_phone else (file_phone if len(file_phone) >= 11 else '')
                    TenantStore.update_tenant(
                        tenant_id=ex_t['id'],
                        full_name=final_name,
                        phone_number=final_phone,
                        apartment_number=apt_str,
                        base_max_counter=max_c,
                        is_active=ex_t.get('is_active', True)
                    )
                    if send_welcome_flag and not existing_phone and len(final_phone) >= 11:
                        w_msg = _build_tenant_invite_whatsapp_text(host_url, p_num, p_name, final_name, apt_str, final_phone)
                        wa_queue_items.append((final_phone, w_msg))
                updated_count += 1
            else:
                valid_ph = file_phone if len(file_phone) >= 11 else ''
                TenantStore.create_tenant(
                    project_number=p_num,
                    parking_name=p_name,
                    full_name=display_name,
                    phone_number=valid_ph,
                    apartment_number=apt_str,
                    base_max_counter=max_c,
                    created_by=mgr.get('email')
                )
                if send_welcome_flag and valid_ph:
                    w_msg = _build_tenant_invite_whatsapp_text(host_url, p_num, p_name, display_name, apt_str, valid_ph)
                    wa_queue_items.append((valid_ph, w_msg))
                added_count += 1

    queued_wa = enqueue_bulk_whatsapp_messages(wa_queue_items) if wa_queue_items else 0
    wa_info_str = f" כמו כן, {queued_wa} הודעות וואטסאפ הוכנסו לתור שליחה מבוקר ברקע (10 הודעות כל 10 שניות)." if queued_wa > 0 else ""

    return jsonify({
        'success': True,
        'added_count': added_count,
        'updated_count': updated_count,
        'total_subscribers': total_subscribers,
        'queued_whatsapp_count': queued_wa,
        'standalone_mode': True,
        'message': f'הקובץ נטען בהצלחה! נוספו {added_count} דירות חדשות, עודכנו {updated_count} דירות קיימות ({total_subscribers} חניות/מנויים ורכבים). מספרי טלפון קיימים נשמרו ללא שינוי.{wa_info_str}'
    })

@tenant_bp.route('/api/tenant-manager/send-bulk-invites', methods=['POST'])
def api_tenant_manager_send_bulk_invites():
    """שליחה מרוכזת של קישור הפורטל בוואטסאפ לכל הדיירים עם מספר טלפון במתחם — בקצב מבוקר של 10 הודעות ב-10 שניות!"""
    mgr = _get_logged_in_tenant_manager()
    if not mgr:
        return jsonify({'success': False, 'message': 'לא מורשה'}), 401
    p_num = str(mgr.get('project_number') or '').strip()
    b_set = TenantStore.get_building_settings(p_num, mgr.get('parking_name') or '')
    p_name = b_set.get('parking_name') or mgr.get('parking_name') or 'המתחם'
    host_url = request.host_url.rstrip('/')

    tenants = TenantStore.list_tenants(p_num)
    items = []
    for t in tenants:
        clean_p = clean_il_phone(t.get('phone_number') or '')
        if len(clean_p) >= 11:
            msg = _build_tenant_invite_whatsapp_text(host_url, p_num, p_name, t.get('full_name'), t.get('apartment_number'), clean_p)
            items.append((clean_p, msg))

    if not items:
        return jsonify({'success': False, 'message': 'לא נמצאו דיירים עם מספר טלפון תקין לשליחה במתחם זה.'})

    queued_count = enqueue_bulk_whatsapp_messages(items)
    est_seconds = max(10, int((queued_count / 10.0) * 11))
    return jsonify({
        'success': True,
        'queued_count': queued_count,
        'message': f'{queued_count} הודעות וואטסאפ הוכנסו לתור שליחה מבוקר ברקע (קצב בטוח של 10 הודעות ב-10 שניות, סיום משוער תוך כ-{est_seconds} שניות).'
    })

@tenant_bp.route('/api/tenant-manager/whatsapp-queue-status', methods=['GET'])
def api_tenant_manager_whatsapp_queue_status():
    mgr = _get_logged_in_tenant_manager()
    if not mgr:
        return jsonify({'success': False, 'message': 'לא מורשה'}), 401
    return jsonify({
        'success': True,
        'pending_in_queue': _wa_bulk_queue.qsize(),
        'stats': _wa_bulk_stats
    })

@tenant_bp.route('/api/tenant-manager/cancel-share/<int:share_id>', methods=['POST'])
def api_tenant_manager_cancel_share(share_id):
    mgr = _get_logged_in_tenant_manager()
    if not mgr:
        return jsonify({'success': False, 'message': 'לא מורשה'}), 401
    p_num = str(mgr.get('project_number') or '')
    TenantStore.deactivate_share(share_id, p_num)
    return jsonify({'success': True, 'message': 'שחרור החניה בוטל בהצלחה'})

@tenant_bp.route('/api/tenant-manager/release-transfer/<int:transfer_id>', methods=['POST'])
def api_tenant_manager_release_transfer(transfer_id):
    mgr = _get_logged_in_tenant_manager()
    if not mgr:
        return jsonify({'success': False, 'message': 'לא מורשה'}), 401
    p_num = str(mgr.get('project_number') or '')
    tr = TenantStore.get_transfer_by_id(transfer_id)
    if not tr or str(tr.get('project_number')) != p_num:
        return jsonify({'success': False, 'message': 'העברה לא נמצאה'})
    restore_active_transfer(tr, early_cancel=True)
    return jsonify({'success': True, 'message': 'ההשאלה הסתיימה והמכסה הוחזרה לדירה המקורית!'})

@tenant_bp.route('/api/tenant-manager/tenants/<int:tenant_id>', methods=['PUT', 'DELETE'])
def api_tenant_manager_modify_tenant(tenant_id):
    mgr = _get_logged_in_tenant_manager()
    if not mgr:
        return jsonify({'success': False, 'message': 'לא מורשה'}), 401
    p_num = str(mgr.get('project_number') or '')
    existing_t = TenantStore.get_tenant_by_id(tenant_id)
    if not existing_t or str(existing_t.get('project_number') or '') != p_num:
        return jsonify({'success': False, 'message': 'דייר לא נמצא במתחם שלך'}), 404
    if request.method == 'DELETE':
        TenantStore.delete_tenant(tenant_id)
        return jsonify({'success': True, 'message': 'הדייר נמחק בהצלחה'})

    data = request.get_json() or {}
    apt = str(data.get('apartment_number') or '').strip()

    if 'is_zero_spot' in data and data.get('is_zero_spot') is not None:
        want_zero = bool(data.get('is_zero_spot'))
        z_res = set_apartment_zero_spot_mode(p_num, apt, want_zero)
        if want_zero:
            auto_max = 0
        else:
            auto_max = z_res.get('effectiveMaxCounter', 1) if z_res.get('success') else 1
    else:
        pool_info = get_apartment_pooling_status(p_num, apt)
        auto_max = int(pool_info.get('maxCounter') or 0) if pool_info.get('success') else None

    TenantStore.update_tenant(
        tenant_id=tenant_id,
        full_name=data.get('full_name', ''),
        phone_number=data.get('phone_number', ''),
        apartment_number=apt,
        base_max_counter=auto_max,
        is_active=data.get('is_active', True)
    )
    # עדכן את אותו base_max_counter לכל הדיירים הרשומים באותה דירה
    if auto_max is not None:
        for other_t in TenantStore.list_tenants(p_num):
            if str(other_t.get('apartment_number') or '').strip() == apt and int(other_t['id']) != int(tenant_id):
                TenantStore.update_tenant(
                    tenant_id=other_t['id'],
                    full_name=other_t.get('full_name', ''),
                    phone_number=other_t.get('phone_number', ''),
                    apartment_number=apt,
                    base_max_counter=auto_max,
                    is_active=other_t.get('is_active', True)
                )
    status_note = ' (הדירה הוגדרה ללא חניה קבועה - חסומה בבקר עד לקבלת חניה משכן)' if auto_max == 0 else ''
    return jsonify({'success': True, 'message': f'פרטי הדייר עודכנו והמכסה סונכרנה מול בקר החניון!{status_note}'})

@tenant_bp.route('/api/tenant-manager/monthly-report', methods=['GET'])
def api_tenant_manager_monthly_report():
    """דו"ח חודשי למנהל המתחם: כמה ימי/שעות חניה כל דירה שחררה וכמה לקחה + מאזן נטו לזיכוי/תגמול."""
    mgr = _get_logged_in_tenant_manager()
    if not mgr:
        return jsonify({'success': False, 'message': 'לא מורשה'}), 401

    p_num = str(mgr.get('project_number') or '')
    month = request.args.get('month') or get_il_now().strftime('%Y-%m')

    tenants = TenantStore.list_tenants(p_num)
    transfers = TenantStore.list_transfers(project_number=p_num, month_prefix=month)

    apt_stats = {}
    for t in tenants:
        apt = str(t['apartment_number'])
        if apt not in apt_stats:
            apt_stats[apt] = {
                'apartment_number': apt,
                'tenant_names': [],
                'given_count': 0,
                'given_hours': 0.0,
                'taken_count': 0,
                'taken_hours': 0.0,
                'net_balance': 0,
                'late_exits': 0
            }
        if t['full_name'] not in apt_stats[apt]['tenant_names']:
            apt_stats[apt]['tenant_names'].append(t['full_name'])

    counted_transfers = []
    for tr in transfers:
        st = tr.get('status')
        if st not in ('ACTIVE', 'RESTORED'):
            continue
        from_apt = str(tr.get('from_apartment'))
        to_apt = str(tr.get('to_apartment'))

        # חישוב שעות שנוצלו בפועל (ACTIVE או RESTORED)
        hours = _calc_transfer_used_hours(tr)

        for apt_key in (from_apt, to_apt):
            if apt_key not in apt_stats:
                apt_stats[apt_key] = {
                    'apartment_number': apt_key,
                    'tenant_names': [f'דירה {apt_key}'],
                    'given_count': 0,
                    'given_hours': 0.0,
                    'taken_count': 0,
                    'taken_hours': 0.0,
                    'net_balance': 0,
                    'late_exits': 0
                }

        apt_stats[from_apt]['given_count'] += 1
        apt_stats[from_apt]['given_hours'] = round(apt_stats[from_apt]['given_hours'] + hours, 1)

        apt_stats[to_apt]['taken_count'] += 1
        apt_stats[to_apt]['taken_hours'] = round(apt_stats[to_apt]['taken_hours'] + hours, 1)
        if tr.get('late_exit_flag'):
            apt_stats[to_apt]['late_exits'] += 1

        tr_copy = dict(tr)
        tr_copy['duration_hours'] = hours
        counted_transfers.append(tr_copy)

    summary_list = []
    for apt, st_obj in apt_stats.items():
        st_obj['tenant_name'] = ', '.join(st_obj['tenant_names']) if st_obj['tenant_names'] else f'דירה {apt}'
        st_obj['net_balance'] = st_obj['given_count'] - st_obj['taken_count']
        st_obj['net_hours'] = round(st_obj['given_hours'] - st_obj['taken_hours'], 1)
        summary_list.append(st_obj)

    summary_list.sort(key=lambda x: (int(x['apartment_number']) if str(x['apartment_number']).isdigit() else 999999, x['apartment_number']))

    return jsonify({
        'success': True,
        'month': month,
        'summary': summary_list,
        'transfers': transfers
    })

# ============================================================================
# 6. TENANT PORTAL ROUTES (פורטל הדייר - כניסה בוואטסאפ בלבד + ניהול ושיתוף חניה)
# ============================================================================
DEFAULT_ANDROID_APK_URL = 'https://expo.dev/artifacts/eas/s8Z1w2Loxm8yQv1wZ7x5bB.apk'
DEFAULT_GOOGLE_PLAY_URL = 'https://play.google.com/store/apps/details?id=com.drorprince.tenantsapp'

def _resolve_store_urls(project_number=None):
    ios_url = (os.getenv('TENANT_IOS_APP_URL') or '').strip()
    android_url = (os.getenv('TENANT_ANDROID_APP_URL') or '').strip()
    if project_number:
        b = TenantStore.get_building_settings(project_number)
        if b.get('ios_app_url'):
            ios_url = str(b['ios_app_url']).strip()
        if b.get('android_app_url'):
            android_url = str(b['android_app_url']).strip()
    if not ios_url or not android_url:
        # בדוק אם הוגדר קישור באחד המתחמים במערכת כברירת מחדל גלובלית
        try:
            with _db_lock:
                conn = sqlite3.connect(SQLITE_PATH)
                conn.row_factory = sqlite3.Row
                rows = conn.execute("SELECT ios_app_url, android_app_url FROM tenant_building_settings").fetchall()
                conn.close()
                for r in rows:
                    if not ios_url and r['ios_app_url']:
                        ios_url = str(r['ios_app_url']).strip()
                    if not android_url and r['android_app_url']:
                        android_url = str(r['android_app_url']).strip()
        except Exception:
            pass
    if not android_url:
        android_url = DEFAULT_GOOGLE_PLAY_URL
    return ios_url, android_url

def _is_safe_store_redirect_url(url_str):
    s = str(url_str or '').strip()
    return s.startswith('https://') or s.startswith('http://') or s.startswith('itms-apps://') or s.startswith('market://')

@tenant_bp.route('/app/ios')
def tenant_app_ios_redirect():
    from flask import redirect
    proj = request.args.get('project') or ''
    ios_url, _ = _resolve_store_urls(proj)
    if ios_url and _is_safe_store_redirect_url(ios_url):
        return redirect(ios_url)
    return redirect('/tenant-portal')

@tenant_bp.route('/app/android')
def tenant_app_android_redirect():
    from flask import redirect
    proj = request.args.get('project') or ''
    _, android_url = _resolve_store_urls(proj)
    if android_url and _is_safe_store_redirect_url(android_url):
        return redirect(android_url)
    return redirect('/tenant-portal')

@tenant_bp.route('/app')
def tenant_app_smart_redirect():
    from flask import redirect
    proj = request.args.get('project') or ''
    ua = (request.headers.get('User-Agent') or '').lower()
    ios_url, android_url = _resolve_store_urls(proj)
    if ('iphone' in ua or 'ipad' in ua or 'ipod' in ua) and ios_url and _is_safe_store_redirect_url(ios_url):
        return redirect(ios_url)
    if 'android' in ua and android_url and _is_safe_store_redirect_url(android_url):
        return redirect(android_url)
    return redirect('/tenant-portal')

@tenant_bp.route('/tenant-portal')
def tenant_portal_page():
    return render_template('tenant_portal.html')

@tenant_bp.route('/api/tenant/building-info', methods=['GET'])
def api_tenant_building_info():
    """מחזיר שם ולוגו של הבניין לפי project או phone (להצגת הלוגו כבר במסך הכניסה)."""
    proj = request.args.get('project')
    phone = request.args.get('phone')
    if not proj and phone:
        t = TenantStore.find_tenant_by_phone(phone)
        if t:
            proj = t.get('project_number')
    if not proj:
        proj = session.get('tenant_project_number')
    if proj:
        b = TenantStore.get_building_settings(proj)
        return jsonify({
            'success': True,
            'parking_name': b.get('parking_name') or '',
            'logo_data': b.get('logo_data') or '',
            'parking_lat': b.get('parking_lat'),
            'parking_lng': b.get('parking_lng'),
            'parking_address': b.get('parking_address') or ''
        })
    return jsonify({'success': False})

def _make_demo_viewer_tenant(phone_number=''):
    clean_p = clean_il_phone(phone_number) or '972500000000'
    return {
        'id': -1,
        'project_number': 'DEMO',
        'parking_name': 'חניון הדגמה (מצב צפייה בלבד)',
        'full_name': 'אורח (צפייה בלבד)',
        'phone_number': clean_p,
        'apartment_number': '101',
        'base_max_counter': 2,
        'is_demo_viewer': True
    }

def _build_demo_viewer_dashboard_payload(tenant):
    today_str = get_il_now().strftime('%Y-%m-%d')
    tomorrow_str = (get_il_now() + timedelta(days=1)).strftime('%Y-%m-%d')
    return {
        'success': True,
        'is_demo_viewer': True,
        'parkings_options': [],
        'tenant': {
            'id': -1,
            'full_name': tenant.get('full_name') or 'אורח (צפייה בלבד)',
            'family_name': 'הדגמה',
            'parking_spots': ['12א', '14ב'],
            'phone_number': display_il_phone(tenant.get('phone_number') or '0500000000'),
            'apartment_number': '101',
            'base_max_counter': 2,
            'project_number': 'DEMO',
            'parking_name': 'חניון הדגמה (מצב צפייה בלבד)',
            'logo_data': '',
            'parking_lat': 32.0853,
            'parking_lng': 34.7818,
            'parking_address': 'תל אביב',
            'standalone_mode': True,
            'is_demo_viewer': True
        },
        'quota_limits': {
            'max_per_day': 5,
            'used_today': 1,
            'max_per_month': 30,
            'used_this_month': 4,
            'given_used_hours_month': 12.5,
            'given_used_hours_total': 36.0,
            'given_used_count': 6
        },
        'pooling': {
            'success': True,
            'apartment': '101',
            'contractName': 'משפחת ישראלי (הדגמה)',
            'maxCounter': 2,
            'presentCounter': 1,
            'availableSpots': 1
        },
        'subscribers': [
            {
                'id': '1',
                'firstName': 'ישראל',
                'lastName': 'ישראלי',
                'parking_spot': '12א',
                'present': True,
                'parked_slot': 'lpn1',
                'can_edit_parked': True,
                'lpn1': '12345678',
                'lpn2': '87654321',
                'lpn3': ''
            },
            {
                'id': '2',
                'firstName': 'מיכל',
                'lastName': 'ישראלי',
                'parking_spot': '14ב',
                'present': False,
                'parked_slot': None,
                'can_edit_parked': True,
                'lpn1': '23456789',
                'lpn2': '',
                'lpn3': ''
            }
        ],
        'my_shares': [
            {
                'id': 9001,
                'owner_apartment': '101',
                'owner_name': 'ישראל ישראלי',
                'spots_offered': 1,
                'parking_spot_number': '14ב',
                'share_target_type': 'POOL',
                'target_apartment': '',
                'schedule_type': 'WEEKLY',
                'days_of_week': '0,1,2,3,4',
                'specific_date': '',
                'start_time': '08:00',
                'end_time': '17:00'
            }
        ],
        'available_slots': [
            {
                'share_id': 9002,
                'owner_apartment': '204',
                'owner_name': 'משפחת כהן',
                'parking_spot_number': '25ג',
                'share_target_type': 'POOL',
                'target_apartment': '',
                'is_for_me_specifically': False,
                'is_mine': False,
                'booking_date': today_str,
                'start_time': '08:00',
                'end_time': '18:00',
                'spots_offered': 1,
                'spots_remaining': 1
            },
            {
                'share_id': 9003,
                'owner_apartment': '305',
                'owner_name': 'משפחת לוי',
                'parking_spot_number': '31א',
                'share_target_type': 'APT',
                'target_apartment': '101',
                'is_for_me_specifically': True,
                'is_mine': False,
                'booking_date': tomorrow_str,
                'start_time': '09:00',
                'end_time': '19:00',
                'spots_offered': 1,
                'spots_remaining': 1
            }
        ],
        'active_bookings': []
    }

def _format_parking_options_for_tenants(matches):
    opts = []
    for m in matches:
        p_num = str(m.get('project_number') or '')
        b_set = TenantStore.get_building_settings(p_num, m.get('parking_name') or '')
        p_name = b_set.get('parking_name') or m.get('parking_name') or f'חניון {p_num}'
        opts.append({
            'tenant_id': m['id'],
            'project_number': p_num,
            'parking_name': p_name,
            'apartment_number': str(m.get('apartment_number') or ''),
            'full_name': m.get('full_name') or '',
            'logo_data': b_set.get('logo_data') or ''
        })
    return opts

_otp_fail_tracker = {}  # phone -> {'count': int, 'locked_until': float}

@tenant_bp.route('/api/tenant/send-otp', methods=['POST'])
def api_tenant_send_otp():
    data = request.get_json() or {}
    phone = data.get('phone_number')
    project_number = data.get('project_number')
    tenant_id_req = data.get('tenant_id')

    matches = TenantStore.find_tenants_by_phone(phone, project_number)
    if tenant_id_req:
        matches = [m for m in matches if str(m.get('id')) == str(tenant_id_req)] or matches

    if not matches:
        # מספר טלפון שאינו רשום במערכת -> כניסה אוטומטית למצב צפייה בלבד (Demo / Read-Only Mode) עבור בדיקות ואישור Apple App Store!
        demo_t = _make_demo_viewer_tenant(phone)
        session['tenant_user_id'] = -1
        session['tenant_demo_phone'] = demo_t['phone_number']
        session['tenant_project_number'] = 'DEMO'
        session['tenant_apartment'] = '101'
        session['tenant_last_activity'] = time.time()
        session.permanent = True
        auth_token = _create_tenant_mobile_token(-1, demo_t['phone_number'])
        return jsonify({
            'success': True,
            'demo_viewer': True,
            'auth_token': auth_token,
            'tenant': {
                'id': -1,
                'full_name': demo_t['full_name'],
                'phone_number': display_il_phone(demo_t['phone_number']),
                'apartment_number': demo_t['apartment_number'],
                'project_number': demo_t['project_number'],
                'parking_name': demo_t['parking_name'],
                'is_demo_viewer': True
            },
            'message': 'מספר זה אינו רשום במתחם — נכנסת למצב צפייה בלבד (תצוגת הדגמה).'
        })

    if len(matches) > 1 and not project_number and not tenant_id_req:
        # למספר הטלפון יש יותר מחניון/דירה אחת — החזר רשימת חניונים לבחירה!
        return jsonify({
            'success': True,
            'choose_parking': True,
            'parkings': _format_parking_options_for_tenants(matches),
            'message': 'נמצאו מספר חניונים המשויכים למספר הטלפון שלך. נא לבחור חניון לכניסה:'
        })

    tenant = matches[0]
    clean_p = clean_il_phone(tenant.get('phone_number') or phone)
    _otp_fail_tracker.pop(clean_p, None)
    otp_code = str(random.randint(100000, 999999))
    expires_iso = (get_il_now() + timedelta(minutes=10)).isoformat()
    for m in matches:
        TenantStore.save_otp(m['id'], otp_code, expires_iso)

    host_url = request.host_url.rstrip('/')
    magic_link = f"{host_url}/tenant-portal?phone={display_il_phone(tenant['phone_number'])}&code={otp_code}&project={tenant['project_number']}"

    msg = (
        f"שלום {tenant.get('full_name')} (דירה {tenant.get('apartment_number')})!\n"
        f"קוד הכניסה שלך למערכת החניות הוא: *{otp_code}*\n\n"
        f"לכניסה מהירה בלחיצה אחת לחץ כאן:\n{magic_link}"
    )
    # שליחת הוואטסאפ בתהליכון רקע כדי שהמסך באייפון/אנדרואיד יתקדם מיד (ללא המתנה)
    threading.Thread(target=send_whatsapp_message, args=(tenant['phone_number'], msg), daemon=True).start()

    return jsonify({
        'success': True,
        'otp_code': otp_code,
        'selected_project': tenant.get('project_number'),
        'selected_tenant_id': tenant.get('id'),
        'message': 'קוד אימות נשלח לוואטסאפ שלך!'
    })

@tenant_bp.route('/api/tenant/verify-otp', methods=['POST'])
def api_tenant_verify_otp():
    data = request.get_json() or {}
    phone = data.get('phone_number')
    code = str(data.get('otp_code') or '').strip()
    project_number = data.get('project_number')
    tenant_id_req = data.get('tenant_id')

    clean_p = clean_il_phone(phone)
    now_ts = time.time()
    fail_info = _otp_fail_tracker.get(clean_p)
    if fail_info and now_ts < fail_info.get('locked_until', 0):
        wait_s = int(fail_info['locked_until'] - now_ts)
        return jsonify({'success': False, 'message': f'יותר מדי ניסיונות שגויים. נא להמתין {wait_s} שניות או לבקש קוד חדש.'}), 429

    matches = TenantStore.find_tenants_by_phone(phone, project_number)
    if tenant_id_req:
        matches = [m for m in matches if str(m.get('id')) == str(tenant_id_req)] or matches
    tenant = matches[0] if matches else None
    if not tenant:
        return jsonify({'success': False, 'message': 'משתמש לא נמצא'})

    saved_otp = str(tenant.get('mobile_otp') or '').strip()
    if not saved_otp or saved_otp != code:
        cnt = (fail_info.get('count', 0) if fail_info else 0) + 1
        locked_until = (now_ts + 120) if cnt >= 5 else 0
        _otp_fail_tracker[clean_p] = {'count': cnt, 'locked_until': locked_until}
        if cnt >= 5:
            TenantStore.save_otp(tenant['id'], '', '')
            return jsonify({'success': False, 'message': 'קוד האימות בוטל עקב 5 ניסיונות שגויים. נא לבקש קוד חדש.'}), 429
        return jsonify({'success': False, 'message': 'קוד האימות שגוי'})

    _otp_fail_tracker.pop(clean_p, None)

    if tenant.get('otp_expires_at'):
        try:
            exp = datetime.datetime.fromisoformat(str(tenant['otp_expires_at']).replace('Z', ''))
            if get_il_now() > exp:
                return jsonify({'success': False, 'message': 'קוד האימות פג תוקף, נא לבקש קוד חדש'})
        except Exception:
            pass

    # Clear OTP and store tenant session
    TenantStore.save_otp(tenant['id'], '', '')
    session['tenant_user_id'] = tenant['id']
    session['tenant_project_number'] = str(tenant['project_number'])
    session['tenant_apartment'] = str(tenant['apartment_number'])
    session['tenant_last_activity'] = time.time()

    auth_token = _create_tenant_mobile_token(tenant['id'], tenant.get('phone_number') or '')
    all_for_phone = TenantStore.find_tenants_by_phone(phone)

    return jsonify({
        'success': True,
        'auth_token': auth_token,
        'parkings_options': _format_parking_options_for_tenants(all_for_phone) if len(all_for_phone) > 1 else [],
        'tenant': {
            'id': tenant['id'],
            'full_name': tenant['full_name'],
            'phone_number': display_il_phone(tenant['phone_number']),
            'apartment_number': tenant['apartment_number'],
            'project_number': tenant['project_number'],
            'parking_name': tenant.get('parking_name') or ''
        }
    })

@tenant_bp.route('/api/tenant/switch-parking', methods=['POST'])
def api_tenant_switch_parking():
    """מעבר מהיר בין חניונים כאשר למספר הטלפון של הדייר יש יותר מחניון אחד (ללא צורך בקוד OTP נוסף)."""
    cur = _get_current_tenant()
    if not cur or cur.get('is_demo_viewer'):
        return jsonify({'success': False, 'message': 'לא מחובר'}), 401
    data = request.get_json() or {}
    target_tid = data.get('tenant_id')
    target_proj = data.get('project_number')
    all_matches = TenantStore.find_tenants_by_phone(cur.get('phone_number'))
    chosen = None
    if target_tid:
        chosen = next((m for m in all_matches if str(m.get('id')) == str(target_tid)), None)
    if not chosen and target_proj:
        chosen = next((m for m in all_matches if str(m.get('project_number')) == str(target_proj)), None)
    if not chosen:
        return jsonify({'success': False, 'message': 'החניון המבוקש לא נמצא עבור מספר הטלפון שלך'}), 404

    session['tenant_user_id'] = chosen['id']
    session['tenant_project_number'] = str(chosen['project_number'])
    session['tenant_apartment'] = str(chosen['apartment_number'])
    session['tenant_last_activity'] = time.time()
    session.permanent = True
    new_token = _create_tenant_mobile_token(chosen['id'], chosen.get('phone_number') or '')
    return jsonify({
        'success': True,
        'auth_token': new_token,
        'tenant': {
            'id': chosen['id'],
            'full_name': chosen['full_name'],
            'phone_number': display_il_phone(chosen['phone_number']),
            'apartment_number': chosen['apartment_number'],
            'project_number': chosen['project_number'],
            'parking_name': chosen.get('parking_name') or ''
        }
    })

def _create_tenant_mobile_token(tenant_id, phone_number=''):
    import hmac, hashlib
    secret = (os.getenv('SECRET_KEY') or 'sb-tenant-mobile-secret-2026').encode('utf-8')
    clean_p = clean_il_phone(phone_number)
    payload_str = f"{int(tenant_id)}:{clean_p}:{int(time.time())}"
    sig = hmac.new(secret, payload_str.encode('utf-8'), hashlib.sha256).hexdigest()
    return f"{payload_str}:{sig}"

def _verify_tenant_mobile_token(token_str):
    import hmac, hashlib
    if not token_str or ':' not in token_str:
        return None, None
    parts = str(token_str).strip().split(':')
    secret = (os.getenv('SECRET_KEY') or 'sb-tenant-mobile-secret-2026').encode('utf-8')
    if len(parts) == 3:
        tid_str, ts_str, sig = parts
        expected = hmac.new(secret, f"{tid_str}:{ts_str}".encode('utf-8'), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None, None
        try:
            return int(tid_str), None
        except Exception:
            return None, None
    elif len(parts) == 4:
        tid_str, clean_p, ts_str, sig = parts
        expected = hmac.new(secret, f"{tid_str}:{clean_p}:{ts_str}".encode('utf-8'), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None, None
        try:
            return int(tid_str), clean_p
        except Exception:
            return None, clean_p
    return None, None

@tenant_bp.route('/api/tenant/logout', methods=['POST'])
def api_tenant_logout():
    session.pop('tenant_user_id', None)
    session.pop('tenant_project_number', None)
    session.pop('tenant_apartment', None)
    return jsonify({'success': True})

def _get_current_tenant():
    # תמיכה בטוקן קבוע (X-Tenant-Token)חתום криптоגרפית כך שרק בהתקנה הראשונה מתבקש קוד, אך לא ניתן להתחזות עם מספר טלפון ללא חתימה!
    req_proj = request.headers.get('X-Tenant-Project') or request.args.get('project_number') or session.get('tenant_project_number')
    mob_token = request.headers.get('X-Tenant-Token') or request.args.get('auth_token')
    if mob_token:
        mob_tid, mob_phone = _verify_tenant_mobile_token(mob_token)
        if mob_tid == -1:
            return _make_demo_viewer_tenant(mob_phone)
        t = None
        if mob_tid:
            t = TenantStore.get_tenant_by_id(mob_tid)
            if t and req_proj and str(req_proj) != 'DEMO' and str(t.get('project_number')) != str(req_proj):
                alt = TenantStore.find_tenant_by_phone(t.get('phone_number'), req_proj)
                if alt:
                    t = alt
        if not t and mob_phone:
            # אם ה-ID המקומי ב-SQLite השתנה לאחר אתחול שרת ב-Render, החתימה ב-mob_token מאשרת את mob_phone המאומת!
            t = TenantStore.find_tenant_by_phone(mob_phone, req_proj if req_proj != 'DEMO' else None)
        if t:
            session['tenant_user_id'] = t['id']
            session['tenant_project_number'] = str(t['project_number'])
            session['tenant_apartment'] = str(t['apartment_number'])
            session['tenant_last_activity'] = time.time()
            session.permanent = True
            return t

    tid = session.get('tenant_user_id')
    if tid == -1:
        return _make_demo_viewer_tenant(session.get('tenant_demo_phone') or '')
    if tid:
        session['tenant_last_activity'] = time.time()
        session.permanent = True
        t = TenantStore.get_tenant_by_id(tid)
        if t and req_proj and str(req_proj) != 'DEMO' and str(t.get('project_number')) != str(req_proj):
            alt = TenantStore.find_tenant_by_phone(t.get('phone_number'), req_proj)
            if alt:
                return alt
        return t
    return None

def _compute_available_slots_for_tenant(project_number, my_apt, days_ahead=7):
    """מחשב את כל החניות הפנויות בפול הכללי או ששוחררו ספציפית עבור הדירה שלי ב-7 הימים הקרובים."""
    shares = TenantStore.list_shares(project_number, active_only=True)
    existing_transfers = TenantStore.list_transfers(
        project_number=project_number,
        statuses=['SCHEDULED', 'WAITING_FOR_EXIT', 'ACTIVE']
    )

    # Map (share_id, booking_date) -> list of taken slot_index
    taken_map = {}
    for tr in existing_transfers:
        key = (int(tr['share_id']), str(tr['booking_date']))
        taken_map.setdefault(key, []).append(tr)

    now = get_il_now()
    today = now.date()
    available_slots = []

    for day_offset in range(days_ahead):
        d = today + timedelta(days=day_offset)
        d_str = d.strftime('%Y-%m-%d')
        # Convert Python weekday (Mon=0..Sun=6) to Israel weekday (Sun=0..Sat=6)
        il_weekday = (d.weekday() + 1) % 7

        for sh in shares:
            owner_apt = str(sh['owner_apartment'])
            target_type = sh.get('share_target_type', 'POOL')
            target_apt = str(sh.get('target_apartment') or '').strip()

            # אם שוחרר לדירה ספציפית אחרת - דלג
            if target_type == 'APT' and target_apt != str(my_apt) and owner_apt != str(my_apt):
                continue

            sched_type = sh.get('schedule_type', 'WEEKLY')
            if sched_type == 'ONCE':
                if str(sh.get('specific_date')) != d_str:
                    continue
            else:
                days_list = [x.strip() for x in str(sh.get('days_of_week') or '').split(',') if x.strip() != '']
                if str(il_weekday) not in days_list:
                    continue

            try:
                end_dt = datetime.datetime.strptime(f"{d_str} {sh['end_time']}", "%Y-%m-%d %H:%M")
                if end_dt <= now:
                    continue
            except Exception:
                continue

            total_offered = int(sh.get('spots_offered') or 1)
            taken_list = taken_map.get((int(sh['id']), d_str), [])
            spots_remaining = max(0, total_offered - len(taken_list))

            available_slots.append({
                'share_id': sh['id'],
                'owner_apartment': owner_apt,
                'owner_name': sh.get('owner_name') or f'דירה {owner_apt}',
                'parking_spot_number': sh.get('parking_spot_number') or '',
                'share_target_type': target_type,
                'target_apartment': target_apt,
                'is_for_me_specifically': (target_type == 'APT' and target_apt == str(my_apt)),
                'is_mine': (owner_apt == str(my_apt)),
                'booking_date': d_str,
                'start_time': sh['start_time'],
                'end_time': sh['end_time'],
                'spots_offered': total_offered,
                'spots_remaining': spots_remaining
            })

    # Sort: specifically for me first, then date & start_time
    available_slots.sort(key=lambda x: (0 if x['is_for_me_specifically'] else 1, x['booking_date'], x['start_time']))
    return available_slots

@tenant_bp.route('/api/tenant/dashboard', methods=['GET'])
def api_tenant_dashboard():
    tenant = _get_current_tenant()
    if not tenant:
        return jsonify({'success': False, 'message': 'לא מחובר'}), 401

    if tenant.get('is_demo_viewer') or int(tenant.get('id') or 0) == -1:
        return jsonify(_build_demo_viewer_dashboard_payload(tenant))

    threading.Thread(target=run_scheduler_cycle, args=(25,), daemon=True).start()

    p_num = str(tenant['project_number'])
    my_apt = str(tenant['apartment_number'])
    all_for_phone = TenantStore.find_tenants_by_phone(tenant.get('phone_number') or '')
    parkings_options = _format_parking_options_for_tenants(all_for_phone) if len(all_for_phone) > 1 else []

    b_settings = TenantStore.get_building_settings(p_num, tenant.get('parking_name') or '')

    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        fut_pool = ex.submit(get_apartment_pooling_status, p_num, my_apt)
        fut_subs = ex.submit(get_apartment_subscribers, p_num, my_apt)
        pooling_info = fut_pool.result()
        subs_info = fut_subs.result()

    # חישוב ניצול מכסה יומית וחודשית של הדירה שלי
    now = get_il_now()
    today_str = now.strftime('%Y-%m-%d')
    month_str = now.strftime('%Y-%m')

    month_transfers = TenantStore.list_transfers(project_number=p_num, month_prefix=month_str)
    my_Bookings_month = [
        tr for tr in month_transfers
        if str(tr.get('to_apartment')) == my_apt and tr.get('status') in ('SCHEDULED', 'WAITING_FOR_EXIT', 'ACTIVE', 'RESTORED')
    ]
    my_bookings_today = [tr for tr in my_Bookings_month if str(tr.get('booking_date')) == today_str]

    # חישוב שעות חניה שהדייר נתן ושנוצלו בפועל על ידי שכנים (ACTIVE / RESTORED)
    all_used_transfers = TenantStore.list_transfers(project_number=p_num, statuses=['ACTIVE', 'RESTORED'])
    my_given_used_all = [tr for tr in all_used_transfers if str(tr.get('from_apartment')) == my_apt]
    my_given_used_month = [tr for tr in my_given_used_all if str(tr.get('booking_date') or '').startswith(month_str)]
    given_used_hours_total = round(sum(_calc_transfer_used_hours(tr) for tr in my_given_used_all), 1)
    given_used_hours_month = round(sum(_calc_transfer_used_hours(tr) for tr in my_given_used_month), 1)

    all_shares = TenantStore.list_shares(p_num, active_only=True)
    my_shares = [sh for sh in all_shares if str(sh.get('owner_apartment')) == my_apt]

    available_slots = _compute_available_slots_for_tenant(p_num, my_apt, days_ahead=7)

    active_bookings = [
        tr for tr in TenantStore.list_transfers(project_number=p_num, statuses=['SCHEDULED', 'WAITING_FOR_EXIT', 'ACTIVE'])
        if str(tr.get('to_apartment')) == my_apt or str(tr.get('from_apartment')) == my_apt
    ]

    subs_list = subs_info.get('subscribers', [])
    apt_parking_spots = [s.get('parking_spot') for s in subs_list if s.get('parking_spot')]
    family_name = (pooling_info.get('contractName') or '').strip()

    return jsonify({
        'success': True,
        'is_demo_viewer': False,
        'parkings_options': parkings_options,
        'tenant': {
            'id': tenant['id'],
            'full_name': tenant['full_name'],
            'family_name': family_name,
            'parking_spots': apt_parking_spots,
            'phone_number': display_il_phone(tenant['phone_number']),
            'apartment_number': my_apt,
            'base_max_counter': int(pooling_info.get('maxCounter') if pooling_info.get('success') else (tenant.get('base_max_counter') or 1)),
            'project_number': p_num,
            'parking_name': b_settings.get('parking_name') or tenant.get('parking_name') or f'מתחם {p_num}',
            'logo_data': b_settings.get('logo_data') or '',
            'parking_lat': b_settings.get('parking_lat'),
            'parking_lng': b_settings.get('parking_lng'),
            'parking_address': b_settings.get('parking_address') or '',
            'standalone_mode': is_standalone_building(p_num)
        },
        'quota_limits': {
            'max_per_day': int(b_settings.get('max_bookings_per_day') or 5),
            'used_today': len(my_bookings_today),
            'max_per_month': int(b_settings.get('max_bookings_per_month') or 30),
            'used_this_month': len(my_Bookings_month),
            'given_used_hours_month': given_used_hours_month,
            'given_used_hours_total': given_used_hours_total,
            'given_used_count': len(my_given_used_all)
        },
        'pooling': pooling_info,
        'subscribers': subs_list,
        'my_shares': my_shares,
        'available_slots': available_slots,
        'active_bookings': active_bookings
    })

@tenant_bp.route('/api/tenant/update-plates', methods=['POST'])
def api_tenant_update_plates():
    tenant = _get_current_tenant()
    if not tenant:
        return jsonify({'success': False, 'message': 'לא מחובר'}), 401
    if tenant.get('is_demo_viewer'):
        return jsonify({'success': False, 'demo_viewer': True, 'message': 'מצב צפייה בלבד (הדגמה) — לא ניתן לשמור שינויים בחניון הדגמה.'})

    data = request.get_json() or {}
    sub_id = str(data.get('subscriber_id') or '').strip()
    if not sub_id:
        return jsonify({'success': False, 'message': 'חסר מזהה מנוי'})

    first_name = data.get('first_name')
    last_name = data.get('last_name')

    res = update_apartment_subscriber_plates(
        project_number=tenant['project_number'],
        apartment_number=tenant['apartment_number'],
        subscriber_id=sub_id,
        lpn1=data.get('lpn1', ''),
        lpn2=data.get('lpn2', ''),
        lpn3=data.get('lpn3', ''),
        first_name=first_name,
        last_name=last_name
    )

    if res.get('success') and (first_name is not None or last_name is not None):
        fn_clean = str(first_name or '').strip()
        ln_clean = str(last_name or '').strip()
        new_full_name = f"{fn_clean} {ln_clean}".strip()
        if new_full_name and int(tenant.get('id') or 0) > 0:
            try:
                TenantStore.update_tenant(
                    tenant['id'],
                    new_full_name,
                    tenant['phone_number'],
                    tenant['apartment_number'],
                    tenant.get('base_max_counter'),
                    True
                )
            except Exception:
                pass

    return jsonify(res)

@tenant_bp.route('/api/tenant/share-spot', methods=['POST'])
def api_tenant_share_spot():
    tenant = _get_current_tenant()
    if not tenant:
        return jsonify({'success': False, 'message': 'לא מחובר'}), 401
    if tenant.get('is_demo_viewer'):
        return jsonify({'success': False, 'demo_viewer': True, 'message': 'מצב צפייה בלבד (הדגמה) — לא ניתן לשחרר חניה בחניון הדגמה.'})

    data = request.get_json() or {}
    start_time = (data.get('start_time') or '').strip()
    end_time = (data.get('end_time') or '').strip()
    spots_offered = int(data.get('spots_offered') or 1)
    parking_spot_number = str(data.get('parking_spot_number') or '').strip()
    share_target_type = data.get('share_target_type', 'POOL')
    target_apartment = str(data.get('target_apartment') or '').strip()
    schedule_type = data.get('schedule_type', 'WEEKLY')
    days_of_week = data.get('days_of_week', '')
    specific_date = data.get('specific_date', '')

    raw_t_base = tenant.get('base_max_counter')
    max_allowed_spots = 1 if raw_t_base is None else int(raw_t_base)
    pool_chk = get_apartment_pooling_status(tenant['project_number'], tenant['apartment_number'])
    if pool_chk.get('success'):
        max_allowed_spots = int(pool_chk.get('maxCounter') or 0)
    if max_allowed_spots <= 0:
        return jsonify({'success': False, 'message': 'לדירתך לא משויכת חניה קבועה לשחרור (0 חניות). באפשרותך לבקש חניה משכנים או לתפוס חניה פנויה!'})
    if spots_offered < 1 or spots_offered > max_allowed_spots:
        return jsonify({'success': False, 'message': f'כמות החניות לשחרור חייבת להיות בין 1 ל-{max_allowed_spots} (כמות החניות של דירתך)'})

    if not start_time or not end_time or start_time >= end_time:
        return jsonify({'success': False, 'message': 'נא לבחור שעת התחלה ושעת סיום תקינות (שעת סיום אחרי שעת התחלה)'})

    if share_target_type == 'APT' and not target_apartment:
        return jsonify({'success': False, 'message': 'נא להזין את מספר הדירה שעבורה משחררים את החניה'})

    if schedule_type == 'WEEKLY' and not str(days_of_week).strip():
        return jsonify({'success': False, 'message': 'נא לבחור לפחות יום אחד בשבוע'})

    if schedule_type == 'ONCE' and not str(specific_date).strip():
        return jsonify({'success': False, 'message': 'נא לבחור תאריך לשחרור החניה'})

    # אם הדייר לא הזין ידנית מספר חניה, משוך אוטומטית משדה קוד התאמה (matchCode) של מנויי הדירה
    if not parking_spot_number:
        try:
            subs_res = get_apartment_subscribers(tenant['project_number'], tenant['apartment_number'])
            spots_from_subs = [s.get('parking_spot') for s in subs_res.get('subscribers', []) if s.get('parking_spot')]
            if spots_from_subs:
                parking_spot_number = ', '.join(spots_from_subs[:spots_offered])
        except Exception:
            pass

    family_name = (pool_chk.get('contractName') or '').strip() if pool_chk.get('success') else ''
    owner_disp_name = tenant['full_name']
    if family_name and family_name not in owner_disp_name:
        owner_disp_name = f"{owner_disp_name} ({family_name})"

    with _action_dedup_lock:
        # מניעת שחרור כפול של אותה חניה בלחיצה כפולה
        existing_shares = TenantStore.list_shares(tenant['project_number'], active_only=True)
        for ex_sh in existing_shares:
            if (
                str(ex_sh.get('owner_apartment')) == str(tenant['apartment_number'])
                and str(ex_sh.get('schedule_type') or 'WEEKLY') == str(schedule_type)
                and str(ex_sh.get('start_time') or '') == str(start_time)
                and str(ex_sh.get('end_time') or '') == str(end_time)
                and str(ex_sh.get('share_target_type') or 'POOL') == str(share_target_type)
                and str(ex_sh.get('target_apartment') or '') == (str(target_apartment) if share_target_type == 'APT' else '')
                and str(ex_sh.get('parking_spot_number') or '').strip() == str(parking_spot_number).strip()
            ):
                if schedule_type == 'ONCE' and str(ex_sh.get('specific_date') or '') == str(specific_date):
                    spot_confirm = f" (חניה: {parking_spot_number})" if parking_spot_number else ""
                    return jsonify({'success': True, 'deduplicated': True, 'message': f'הגדרת שחרור החניה{spot_confirm} נשמרה בהצלחה!', 'share': ex_sh})
                if schedule_type == 'WEEKLY' and str(ex_sh.get('days_of_week') or '') == str(days_of_week):
                    spot_confirm = f" (חניה: {parking_spot_number})" if parking_spot_number else ""
                    return jsonify({'success': True, 'deduplicated': True, 'message': f'הגדרת שחרור החניה{spot_confirm} נשמרה בהצלחה!', 'share': ex_sh})

        created = TenantStore.create_share({
            'project_number': tenant['project_number'],
            'owner_tenant_id': tenant['id'],
            'owner_name': owner_disp_name,
            'owner_apartment': tenant['apartment_number'],
            'spots_offered': spots_offered,
            'parking_spot_number': parking_spot_number,
            'share_target_type': share_target_type,
            'target_apartment': target_apartment if share_target_type == 'APT' else None,
            'schedule_type': schedule_type,
            'days_of_week': days_of_week,
            'specific_date': specific_date,
            'start_time': start_time,
            'end_time': end_time
        })

    # אם שוחררה חניה במיוחד עבור דירה ספציפית, שלח לה הודעת וואטסאפ עם מספר החניה!
    if share_target_type == 'APT' and target_apartment:
        all_tenants = TenantStore.list_tenants(tenant['project_number'])
        spot_txt = f" (חניה מס׳: *{parking_spot_number}*)" if parking_spot_number else ""
        for t in all_tenants:
            if str(t.get('apartment_number')) == target_apartment and t.get('phone_number'):
                host_url = request.host_url.rstrip('/')
                msg = (
                    f"שלום {t.get('full_name')} (דירה {target_apartment})! 🎁\n"
                    f"דירה {tenant['apartment_number']} ({owner_disp_name}) שחררה עבורך {spots_offered} חניה/ות{spot_txt} "
                    f"בין השעות *{start_time}* עד *{end_time}*.\n"
                    f"לצפייה ותפיסת החניה היכנס לפורטל הדיירים:\n{host_url}/tenant-portal"
                )
                send_whatsapp_message(t['phone_number'], msg)

    spot_confirm = f" (חניה: {parking_spot_number})" if parking_spot_number else ""
    return jsonify({'success': True, 'message': f'הגדרת שחרור החניה{spot_confirm} נשמרה בהצלחה!', 'share': created})


@tenant_bp.route('/api/tenant/request-spot', methods=['POST'])
def api_tenant_request_spot():
    """דירה מבקשת חניה (חד-פעמי כברירת מחדל או קבוע לפי ימים) -> שולח לדירה עצמה וואטסאפ מוכן להעתקה לקבוצת הבניין עם קישור חכם שממלא אוטומטית את שחרור החניה."""
    tenant = _get_current_tenant()
    if not tenant:
        return jsonify({'success': False, 'message': 'לא מחובר'}), 401
    if tenant.get('is_demo_viewer'):
        return jsonify({'success': False, 'demo_viewer': True, 'message': 'מצב צפייה בלבד (הדגמה) — לא ניתן לשלוח בקשת חניה בחניון הדגמה.'})

    data = request.get_json() or {}
    schedule_type = (data.get('schedule_type') or 'ONCE').strip().upper()
    specific_date = str(data.get('specific_date') or '').strip()
    days_of_week = str(data.get('days_of_week') or '').strip()
    start_time = (data.get('start_time') or '').strip()
    end_time = (data.get('end_time') or '').strip()

    if not start_time or not end_time or start_time >= end_time:
        return jsonify({'success': False, 'message': 'נא לבחור שעת התחלה ושעת סיום תקינות (שעת סיום אחרי שעת התחלה)'})

    if schedule_type == 'ONCE' and not specific_date:
        return jsonify({'success': False, 'message': 'נא לבחור תאריך לבקשת החניה'})

    if schedule_type == 'WEEKLY' and not days_of_week:
        return jsonify({'success': False, 'message': 'נא לבחור לפחות יום אחד בשבוע'})

    p_num = str(tenant['project_number'])
    my_apt = str(tenant['apartment_number'])
    b_settings = TenantStore.get_building_settings(p_num, tenant.get('parking_name') or '')
    p_name = b_settings.get('parking_name') or tenant.get('parking_name') or f'מתחם {p_num}'

    pool_chk = get_apartment_pooling_status(p_num, my_apt)
    family_name = (pool_chk.get('contractName') or '').strip() if pool_chk.get('success') else ''
    req_disp_name = tenant['full_name']
    if family_name and family_name not in req_disp_name:
        req_disp_name = f"{req_disp_name} ({family_name})"

    day_names_he = ['ראשון', 'שני', 'שלישי', 'רביעי', 'חמישי', 'שישי', 'שבת']
    if schedule_type == 'ONCE':
        sched_text = f"בתאריך *{specific_date}*"
    else:
        d_idxs = [int(x) for x in days_of_week.split(',') if x.strip().isdigit() and 0 <= int(x) <= 6]
        d_labels = ', '.join(f"יום {day_names_he[i]}" for i in d_idxs)
        sched_text = f"בימים קבועים: *{d_labels}*"

    if start_time == '00:00' and end_time == '23:59':
        hours_text = "*יום מלא (00:00 עד 23:59)*"
    else:
        hours_text = f"*{start_time} עד {end_time}*"

    from urllib.parse import urlencode
    host_url = request.host_url.rstrip('/')
    q_params = {
        'action': 'fulfill_request',
        'req_apt': my_apt,
        'req_name': req_disp_name,
        'sched': schedule_type,
        'date': specific_date if schedule_type == 'ONCE' else '',
        'days': days_of_week if schedule_type == 'WEEKLY' else '',
        'start': start_time,
        'end': end_time
    }
    smart_link = f"{host_url}/tenant-portal?{urlencode(q_params)}"

    wa_msg = (
        f"שלום שכנים יקרים! 👋🏢\n"
        f"דירה *{my_apt}* ({req_disp_name}) מחפשת חניה פנויה ב*{p_name}*:\n"
        f"📅 {sched_text}\n"
        f"🕒 שעות: {hours_text}\n\n"
        f"מי שיכול לשחרר לנו חניה — לחצו על הקישור (הפרטים כבר מוזנים אוטומטית עבור דירה {my_apt}, נשאר רק ללחוץ על \"פרסם ושחרר חניה\"):\n"
        f"{smart_link}\n\n"
        f"תודה רבה! 🙏"
    )

    wa_ok, wa_err = send_whatsapp_message(tenant['phone_number'], wa_msg)
    if wa_ok:
        msg_out = 'הבקשה נשלחה לוואטסאפ שלך! העתק והדבק אותה בקבוצת הוואטסאפ של הבניין.'
    else:
        msg_out = 'הבקשה הוכנה! (ניתן להעתיק אותה מכאן ולהדביק בקבוצת הוואטסאפ של הבניין).'

    return jsonify({
        'success': True,
        'whatsapp_sent': wa_ok,
        'message': msg_out,
        'share_text': wa_msg,
        'smart_link': smart_link
    })

@tenant_bp.route('/api/tenant/cancel-share/<int:share_id>', methods=['POST'])
def api_tenant_cancel_share(share_id):
    tenant = _get_current_tenant()
    if not tenant:
        return jsonify({'success': False, 'message': 'לא מחובר'}), 401
    if tenant.get('is_demo_viewer'):
        return jsonify({'success': False, 'demo_viewer': True, 'message': 'מצב צפייה בלבד (הדגמה) — לא ניתן לבטל שחרור חניה בחניון הדגמה.'})
    TenantStore.deactivate_share(share_id, tenant['project_number'])
    return jsonify({'success': True, 'message': 'שחרור החניה בוטל'})

@tenant_bp.route('/api/tenant/claim-spot', methods=['POST'])
def api_tenant_claim_spot():
    """דייר לוקח חניה פנויה מהפול הכללי או חניה שפנויה עבורו (עם נעילת סלוט ובדיקת מכסה יומית/חודשית)."""
    tenant = _get_current_tenant()
    if not tenant:
        return jsonify({'success': False, 'message': 'לא מחובר'}), 401
    if tenant.get('is_demo_viewer'):
        return jsonify({'success': False, 'demo_viewer': True, 'message': 'מצב צפייה בלבד (הדגמה) — לא ניתן לתפוס חניה בחניון הדגמה.'})

    data = request.get_json() or {}
    share_id = int(data.get('share_id') or 0)
    booking_date = str(data.get('booking_date') or '').strip()

    p_num = str(tenant['project_number'])
    my_apt = str(tenant['apartment_number'])

    with _action_dedup_lock:
        shares = TenantStore.list_shares(p_num, active_only=True)
        share = next((s for s in shares if int(s['id']) == share_id), None)
        if not share:
            return jsonify({'success': False, 'message': 'שחרור החניה לא נמצא או שבוטל'})

        from_apt = str(share['owner_apartment'])
        if from_apt == my_apt:
            return jsonify({'success': False, 'message': 'לא ניתן להזמין חניה של הדירה שלך עצמך'})

        if share.get('share_target_type') == 'APT' and str(share.get('target_apartment')) != my_apt:
            return jsonify({'success': False, 'message': 'חניה זו שוחררה עבור דירה אחרת בלבד'})

        # 1. בדיקת מכסה יומית וחודשית של המתחם
        b_settings = TenantStore.get_building_settings(p_num)
        max_day = int(b_settings.get('max_bookings_per_day') or 5)
        max_month = int(b_settings.get('max_bookings_per_month') or 30)

        month_prefix = booking_date[:7]
        month_transfers = TenantStore.list_transfers(project_number=p_num, month_prefix=month_prefix)
        my_month_active = [
            tr for tr in month_transfers
            if str(tr.get('to_apartment')) == my_apt and tr.get('status') in ('SCHEDULED', 'WAITING_FOR_EXIT', 'ACTIVE', 'RESTORED')
        ]
        my_day_active = [tr for tr in my_month_active if str(tr.get('booking_date')) == booking_date]

        if len(my_day_active) >= max_day:
            return jsonify({'success': False, 'message': f'הגעת למגבלת החניות המותרת ליום אחד במתחם ({max_day} חניות ביום)'})
        if len(my_month_active) >= max_month:
            return jsonify({'success': False, 'message': f'הגעת למגבלת החניות המותרת לחודש במתחם ({max_month} חניות בחודש)'})

        # 2. בדיקה שהסלוט עדיין פנוי ולא נתפס ע"י דייר אחר!
        existing_for_share = [
            tr for tr in month_transfers
            if int(tr.get('share_id')) == share_id and str(tr.get('booking_date')) == booking_date
            and tr.get('status') in ('SCHEDULED', 'WAITING_FOR_EXIT', 'ACTIVE')
        ]
        spots_offered = int(share.get('spots_offered') or 1)
        if len(existing_for_share) >= spots_offered:
            return jsonify({'success': False, 'message': 'כל החניות בחלון זמן זה כבר נתפסו על ידי דיירים אחרים'})

        used_slots = {int(tr.get('slot_index') or 1) for tr in existing_for_share}
        slot_index = 1
        while slot_index in used_slots:
            slot_index += 1

        w_start_dt = datetime.datetime.strptime(f"{booking_date} {share['start_time']}", "%Y-%m-%d %H:%M")
        w_end_dt = datetime.datetime.strptime(f"{booking_date} {share['end_time']}", "%Y-%m-%d %H:%M")
        now = get_il_now()

        if w_end_dt <= now:
            return jsonify({'success': False, 'message': 'חלון הזמן של חניה זו כבר הסתיים'})

        raw_share_spots = str(share.get('parking_spot_number') or '').strip()
        assigned_spot_no = raw_share_spots
        if ',' in raw_share_spots:
            parts = [p.strip() for p in raw_share_spots.split(',') if p.strip()]
            if parts:
                assigned_spot_no = parts[min(slot_index - 1, len(parts) - 1)]

        transfer = TenantStore.create_transfer({
            'share_id': share_id,
            'slot_index': slot_index,
            'project_number': p_num,
            'from_apartment': from_apt,
            'to_apartment': my_apt,
            'parking_spot_number': assigned_spot_no,
            'borrower_tenant_id': tenant['id'],
            'borrower_name': tenant['full_name'],
            'borrower_phone': tenant['phone_number'],
            'booking_date': booking_date,
            'start_time': share['start_time'],
            'end_time': share['end_time'],
            'window_start': w_start_dt.isoformat(),
            'window_end': w_end_dt.isoformat(),
            'status': 'SCHEDULED'
        })

    spot_msg_part = f" (חניה מס׳: {assigned_spot_no})" if assigned_spot_no else ""

    # אם חלון הזמן כבר פעיל כעת - נסה להעביר את המונה מיד!
    if w_start_dt <= now < w_end_dt:
        act_res = try_activate_transfer(transfer)
        if act_res.get('activated'):
            return jsonify({
                'success': True,
                'message': f'החניה מדירה {from_apt}{spot_msg_part} הופעלה עבורך מיד! מכסת החניות של דירתך עלתה ב-1 עד {share["end_time"]}.'
            })
        elif act_res.get('status') == 'WAITING_FOR_EXIT':
            return jsonify({
                'success': True,
                'message': f'החניה מדירה {from_apt}{spot_msg_part} שוריינה עבורך! הרכב של דירה {from_apt} עדיין בחניון – ברגע שייצא, המכסה תועבר אליך ותקבל הודעת וואטסאפ.'
            })

    return jsonify({
        'success': True,
        'message': f'החניה מדירה {from_apt}{spot_msg_part} שוריינה עבורך לתאריך {booking_date} בין {share["start_time"]} ל-{share["end_time"]}! תקבל הודעת וואטסאפ ברגע שהחניה תיכנס לתוקף.'
    })

@tenant_bp.route('/api/tenant/release-booking/<int:transfer_id>', methods=['POST'])
def api_tenant_release_booking(transfer_id):
    """סיום מוקדם / ביטול הזמנת חניה ע"י הדייר והחזרת המונה לבעל החניה."""
    tenant = _get_current_tenant()
    if not tenant:
        return jsonify({'success': False, 'message': 'לא מחובר'}), 401
    if tenant.get('is_demo_viewer'):
        return jsonify({'success': False, 'demo_viewer': True, 'message': 'מצב צפייה בלבד (הדגמה).'})

    tr = TenantStore.get_transfer_by_id(transfer_id)
    if not tr or str(tr.get('project_number')) != str(tenant['project_number']):
        return jsonify({'success': False, 'message': 'הזמנה לא נמצאה'})

    my_apt = str(tenant['apartment_number'])
    if str(tr.get('to_apartment')) != my_apt and str(tr.get('from_apartment')) != my_apt:
        return jsonify({'success': False, 'message': 'אין הרשאה להזמנה זו'})

    restore_active_transfer(tr, early_cancel=True)
    return jsonify({'success': True, 'message': 'ההזמנה הסתיימה והמכסה הוחזרה לדירה המקורית!'})
