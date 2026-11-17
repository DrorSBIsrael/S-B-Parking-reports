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
        try:
            cur.execute("ALTER TABLE tenant_building_settings ADD COLUMN logo_data TEXT")
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
        sb = _get_supabase()
        if sb:
            try:
                res = sb.table('tenant_building_settings').select('*').eq('project_number', p_num).execute()
                if res.data:
                    return res.data[0]
            except Exception as _sbe:
                _trip_sb_circuit_if_missing(_sbe)
        with _db_lock:
            conn = sqlite3.connect(SQLITE_PATH)
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM tenant_building_settings WHERE project_number = ?", (p_num,)).fetchone()
            conn.close()
            if row:
                return dict(row)
        return {
            'project_number': p_num,
            'parking_name': default_name,
            'max_bookings_per_day': 5,
            'max_bookings_per_month': 30,
            'check_interval_minutes': 30,
            'reminder_minutes_before': 30,
            'logo_data': ''
        }

    @staticmethod
    def save_building_settings(project_number, parking_name, max_day, max_month, check_interval=30, reminder_mins=30, logo_data=None):
        p_num = str(project_number)
        now_iso = get_il_now().isoformat()
        existing = TenantStore.get_building_settings(p_num, parking_name)
        final_logo = logo_data if logo_data is not None else (existing.get('logo_data') or '')
        payload = {
            'project_number': p_num,
            'parking_name': parking_name or '',
            'max_bookings_per_day': int(max_day),
            'max_bookings_per_month': int(max_month),
            'check_interval_minutes': int(check_interval),
            'reminder_minutes_before': int(reminder_mins),
            'logo_data': final_logo,
            'updated_at': now_iso
        }
        sb = _get_supabase()
        if sb:
            try:
                sb.table('tenant_building_settings').upsert(payload).execute()
            except Exception as _sbe:
                _trip_sb_circuit_if_missing(_sbe)
        with _db_lock:
            conn = sqlite3.connect(SQLITE_PATH)
            conn.execute("""
                INSERT INTO tenant_building_settings
                (project_number, parking_name, max_bookings_per_day, max_bookings_per_month, check_interval_minutes, reminder_minutes_before, logo_data, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_number) DO UPDATE SET
                    parking_name=excluded.parking_name,
                    max_bookings_per_day=excluded.max_bookings_per_day,
                    max_bookings_per_month=excluded.max_bookings_per_month,
                    check_interval_minutes=excluded.check_interval_minutes,
                    reminder_minutes_before=excluded.reminder_minutes_before,
                    logo_data=excluded.logo_data,
                    updated_at=excluded.updated_at
            """, (p_num, payload['parking_name'], payload['max_bookings_per_day'], payload['max_bookings_per_month'],
                  payload['check_interval_minutes'], payload['reminder_minutes_before'], final_logo, now_iso))
            conn.commit()
            conn.close()
        return payload

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
    def find_tenant_by_phone(phone_number, project_number=None):
        clean_p = clean_il_phone(phone_number)
        sb = _get_supabase()
        if sb:
            try:
                q = sb.table('tenant_users').select('*').eq('phone_number', clean_p).eq('is_active', True)
                if project_number:
                    q = q.eq('project_number', str(project_number))
                res = q.execute()
                if res.data:
                    return res.data[0]
            except Exception as _sbe:
                _trip_sb_circuit_if_missing(_sbe)
        with _db_lock:
            conn = sqlite3.connect(SQLITE_PATH)
            conn.row_factory = sqlite3.Row
            if project_number:
                row = conn.execute("SELECT * FROM tenant_users WHERE phone_number = ? AND project_number = ? AND is_active = 1", (clean_p, str(project_number))).fetchone()
            else:
                row = conn.execute("SELECT * FROM tenant_users WHERE phone_number = ? AND is_active = 1", (clean_p,)).fetchone()
            conn.close()
            return dict(row) if row else None

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
        payload = {
            'project_number': p_num,
            'parking_name': parking_name or '',
            'full_name': full_name.strip(),
            'phone_number': clean_p,
            'apartment_number': str(apartment_number).strip(),
            'base_max_counter': int(base_max_counter or 1),
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
        sb = _get_supabase()
        if sb:
            try:
                q = sb.table('tenant_spot_shares').select('*').eq('project_number', p_num)
                if active_only:
                    q = q.eq('is_active', True)
                res = q.order('id', desc=True).execute()
                if res.data is not None:
                    return res.data
            except Exception as _sbe:
                _trip_sb_circuit_if_missing(_sbe)
        with _db_lock:
            conn = sqlite3.connect(SQLITE_PATH)
            conn.row_factory = sqlite3.Row
            sql = "SELECT * FROM tenant_spot_shares WHERE project_number = ?" + (" AND is_active = 1" if active_only else "") + " ORDER BY id DESC"
            rows = conn.execute(sql, (p_num,)).fetchall()
            conn.close()
            return [dict(r) for r in rows]

    @staticmethod
    def create_share(data):
        now_iso = get_il_now().isoformat()
        payload = {
            'project_number': str(data['project_number']),
            'owner_tenant_id': int(data.get('owner_tenant_id') or 0),
            'owner_name': data.get('owner_name') or '',
            'owner_apartment': str(data['owner_apartment']).strip(),
            'spots_offered': int(data.get('spots_offered') or 1),
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
                _trip_sb_circuit_if_missing(_sbe)
        with _db_lock:
            conn = sqlite3.connect(SQLITE_PATH)
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO tenant_spot_shares
                (project_number, owner_tenant_id, owner_name, owner_apartment, spots_offered, share_target_type, target_apartment,
                 schedule_type, days_of_week, specific_date, start_time, end_time, is_active, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
            """, (payload['project_number'], payload['owner_tenant_id'], payload['owner_name'], payload['owner_apartment'],
                  payload['spots_offered'], payload['share_target_type'], payload['target_apartment'],
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
                    return res.data
            except Exception as _sbe:
                _trip_sb_circuit_if_missing(_sbe)
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
            rows = conn.execute(f"SELECT * FROM tenant_quota_transfers{where_sql} ORDER BY id DESC", params).fetchall()
            conn.close()
            return [dict(r) for r in rows]

    @staticmethod
    def create_transfer(data):
        now_iso = get_il_now().isoformat()
        payload = {
            'share_id': int(data['share_id']),
            'slot_index': int(data.get('slot_index') or 1),
            'project_number': str(data['project_number']),
            'from_apartment': str(data['from_apartment']).strip(),
            'to_apartment': str(data['to_apartment']).strip(),
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
                _trip_sb_circuit_if_missing(_sbe)
        with _db_lock:
            conn = sqlite3.connect(SQLITE_PATH)
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO tenant_quota_transfers
                (share_id, slot_index, project_number, from_apartment, to_apartment, borrower_tenant_id, borrower_name, borrower_phone,
                 booking_date, start_time, end_time, window_start, window_end, status, notified_start, notified_ending_soon, late_exit_flag, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 0, ?)
            """, (payload['share_id'], payload['slot_index'], payload['project_number'], payload['from_apartment'],
                  payload['to_apartment'], payload['borrower_tenant_id'], payload['borrower_name'], payload['borrower_phone'],
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

def get_apartment_pooling_status(project_number, apartment_number):
    """קריאת maxCounter ו-presentCounter של דירה (חברה) מתוך שיידט."""
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
            return {'success': False, 'message': f'HTTP {resp.status_code}'}
        resp.encoding = 'utf-8'
        ns = {'ns': 'http://gsph.sub.com/cust/types'}
        root = ET.fromstring(resp.content)
        contract_node = root.find('ns:contract', ns)
        contract_name = contract_node.findtext('ns:name', default='', namespaces=ns) if contract_node is not None else ''
        pooling_node = root.find('.//ns:pooling', ns)
        max_c = 0
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
                max_c = int(chosen.findtext('ns:maxCounter', default='0', namespaces=ns) or 0)
                pres_c = int(chosen.findtext('ns:presentCounter', default='0', namespaces=ns) or 0)
        return {
            'success': True,
            'apartment': str(apartment_number),
            'contractName': contract_name,
            'maxCounter': max_c,
            'presentCounter': pres_c,
            'availableSpots': max(0, max_c - pres_c)
        }
    except Exception as e:
        return {'success': False, 'message': str(e)}

def adjust_apartment_max_counter(project_number, apartment_number, delta):
    """שינוי maxCounter של דירה ב-+1 או -1 מול שיידט (PUT /contracts/{id}/detail)."""
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

        max_el = target_detail.find('ns:maxCounter', ns)
        pres_el = target_detail.find('ns:presentCounter', ns)
        old_max = int((max_el.text if max_el is not None else '0') or 0)
        pres_val = int((pres_el.text if pres_el is not None else '0') or 0)
        new_max = max(0, old_max + int(delta))
        if max_el is not None:
            max_el.text = str(new_max)

        xml_payload = ET.tostring(root, encoding='utf-8', method='xml')
        put_resp = sess.put(url, data=xml_payload, headers=_skidata_headers('application/xml'), verify=False, timeout=15)
        if put_resp.status_code in (200, 201, 204):
            return {
                'success': True,
                'oldMaxCounter': old_max,
                'newMaxCounter': new_max,
                'presentCounter': pres_val
            }
        return {'success': False, 'message': f'PUT rejected with HTTP {put_resp.status_code}: {put_resp.text[:200]}'}
    except Exception as e:
        return {'success': False, 'message': str(e)}

def get_apartment_subscribers(project_number, apartment_number):
    """שליפת המנויים והרכבים של הדירה מתוך שיידט."""
    conn = _get_parking_conn(project_number)
    if not conn or not conn.get('ip_address'):
        return {'success': False, 'message': 'לא נמצאו פרטי חיבור לחניון', 'subscribers': []}
    ip = conn['ip_address']
    port = conn.get('port', 8443)
    url = f"https://{ip}:{port}/CustomerMediaWebService/contracts/{apartment_number}/consumersdetail"
    try:
        sess = _get_http_session()
        resp = sess.get(url, headers=_skidata_headers(), verify=False, timeout=25)
        if resp.status_code != 200:
            return {'success': False, 'message': f'HTTP {resp.status_code}', 'subscribers': []}
        resp.encoding = 'utf-8'
        ns = {'ns': 'http://gsph.sub.com/cust/types'}
        root = ET.fromstring(resp.content)
        subs = []
        for cd in root.findall('.//ns:consumerDetail', ns):
            cons = cd.find('ns:consumer', ns)
            person = cd.find('ns:person', ns)
            ident = cd.find('ns:identification', ns)
            sid = cons.findtext('ns:id', default='', namespaces=ns) if cons is not None else ''
            fname = (person.findtext('ns:firstName', default='', namespaces=ns) if person is not None else '') or cd.findtext('ns:firstName', default='', namespaces=ns)
            lname = (person.findtext('ns:surname', default='', namespaces=ns) if person is not None else '') or cd.findtext('ns:surname', default='', namespaces=ns)
            pres = ident.findtext('ns:present', default='false', namespaces=ns) if ident is not None else 'false'
            lpn1 = (cd.findtext('ns:lpn1', default='', namespaces=ns) or '').strip()
            lpn2 = (cd.findtext('ns:lpn2', default='', namespaces=ns) or '').strip()
            lpn3 = (cd.findtext('ns:lpn3', default='', namespaces=ns) or '').strip()
            subs.append({
                'id': sid,
                'apartment': str(apartment_number),
                'firstName': fname.strip(),
                'lastName': lname.strip(),
                'present': str(pres).lower() in ('true', '1', 'yes'),
                'lpn1': lpn1,
                'lpn2': lpn2,
                'lpn3': lpn3
            })
        return {'success': True, 'subscribers': subs}
    except Exception as e:
        return {'success': False, 'message': str(e), 'subscribers': []}

def update_apartment_subscriber_plates(project_number, apartment_number, subscriber_id, lpn1, lpn2, lpn3):
    """עדכון מספרי רכב של מנוי בדירה בשיידט, כולל תמיכה מלאה בעדכון כאשר המנוי נמצא בחניון (present=true)."""
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

        cur_lpn1 = re.sub(r'[^0-9CCDמ]', '', (root.findtext('ns:lpn1', default='', namespaces=ns) or '').strip().upper())
        cur_lpn2 = re.sub(r'[^0-9CCDמ]', '', (root.findtext('ns:lpn2', default='', namespaces=ns) or '').strip().upper())
        cur_lpn3 = re.sub(r'[^0-9CCDמ]', '', (root.findtext('ns:lpn3', default='', namespaces=ns) or '').strip().upper())
        cur_map = {'lpn1': cur_lpn1, 'lpn2': cur_lpn2, 'lpn3': cur_lpn3}

        def _validate_plate(raw_val):
            """מתיר ספרות בלבד, או הצירופים CC / CD (דיפלומטי) או האות 'מ' (משטרה)."""
            s = re.sub(r'[\s\-]', '', str(raw_val or '').strip()).upper()
            if not s:
                return True, ''
            # הסרת הצירופים המותרים ובדיקה שנותרו אך ורק ספרות (ושיש לפחות ספרה אחת)
            rem = s.replace('CC', '', 1).replace('CD', '', 1).replace('מ', '', 1)
            if not rem.isdigit() or not any(ch.isdigit() for ch in s):
                return False, s
            # אל תאפשר גם CC/CD וגם מ' יחד או כפילויות של אותיות
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

        if not changed_tags:
            return {'success': True, 'message': 'מספרי הרכב עודכנו בהצלחה בחניון!'}

        lpn_xml_parts = ''.join(f'<{k}>{v}</{k}>' for k, v in changed_tags.items())
        minimal_xml = (
            f'<?xml version="1.0" encoding="UTF-8"?>'
            f'<consumerDetail xmlns="{ns_uri}">'
            f'<consumer href="/consumers/{apt_str},{sid_str}">'
            f'<id>{sid_str}</id><contractid>{apt_str}</contractid>'
            f'</consumer>'
            f'{lpn_xml_parts}'
            f'</consumerDetail>'
        ).encode('utf-8')

        def _reset_stuck_presence(fac_id, comp_id, dev_id):
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

        def _get_open_entry_info():
            """מחזיר (fac_id, comp_id, dev_id, days_in_parking) של הכניסה הפעילה בחניון."""
            try:
                pt_url = f"https://{ip}:{port}/CustomerMediaWebService/consumers/{apt_str},{sid_str}/parktrans"
                pt_resp = sess.get(pt_url, headers=_skidata_headers(), verify=False, timeout=10)
                if pt_resp.status_code == 200:
                    pt_root = ET.fromstring(pt_resp.content)
                    for tx in pt_root.findall('.//ns:parkTransaction', ns):
                        fin = int(tx.findtext('ns:facilityin', default='0', namespaces=ns) or 0)
                        if fin > 0:
                            comp = int(tx.findtext('ns:computer', default='2152', namespaces=ns) or 2152)
                            dev = int(tx.findtext('ns:device', default='101', namespaces=ns) or 101)
                            tx_time_str = (tx.findtext('ns:transactionTime', default='', namespaces=ns) or '').strip()
                            days_in = 0.0
                            if tx_time_str:
                                try:
                                    tx_dt = datetime.datetime.fromisoformat(tx_time_str)
                                    now_dt = datetime.datetime.now(tx_dt.tzinfo) if tx_dt.tzinfo else datetime.datetime.now()
                                    days_in = max(0.0, (now_dt - tx_dt).total_seconds() / 86400.0)
                                except Exception:
                                    days_in = 0.0
                            return fin, comp, dev, days_in
            except Exception:
                pass
            return 2280, 2152, 101, 0.0

        # הוספת/עדכון רכב 2 או רכב 3 בלבד (ללא שינוי רכב 1) עובדת ישירות ללא נגיעה בנוכחות.
        # לעומת זאת, אם המנוי נמצא בחניון (present=true) ומנסים להחליף את רכב 1:
        # - אם הרכב בחניון פחות מ-7 ימים -> לא משחררים נוכחות! מודיעים שלא ניתן להחליף רכב בזמן שהוא בחניון.
        # - רק אם הרכב כבר 7 ימים ומעלה בחניון (נוכחות תקועה) -> מאפסים את הנוכחות ומחליפים את הרכב.
        need_presence_check = is_present and ('lpn1' in changed_tags)

        if not need_presence_check:
            put_resp = sess.put(url, data=minimal_xml, headers=_skidata_headers('application/xml'), verify=False, timeout=15)
            if put_resp.status_code in (200, 201, 204):
                return {'success': True, 'message': 'מספרי הרכב עודכנו בהצלחה בחניון!'}
            if is_present:
                need_presence_check = True
            else:
                return {'success': False, 'message': f'בקר החניון דחה את העדכון ({put_resp.status_code})'}

        if need_presence_check:
            fac_id, comp_id, dev_id, days_in_parking = _get_open_entry_info()
            if days_in_parking < 7.0:
                return {
                    'success': False,
                    'error_code': 'CAR_IN_PARKING',
                    'message': 'לא ניתן להחליף את מספר הרכב בזמן שהרכב נמצא בחניון. יש להמתין ליציאת הרכב מהחניון (איפוס נוכחות אוטומטי מתבצע רק כאשר הרכב רשום בחניון מעל 7 ימים).'
                }
            # הרכב רשום בחניון כבר 7 ימים או יותר -> מאפסים נוכחות ומבצעים את ההחלפה!
            exit_res = _reset_stuck_presence(fac_id, comp_id, dev_id)
            if exit_res.status_code in (200, 201, 204):
                time.sleep(0.2)
                put_resp = sess.put(url, data=minimal_xml, headers=_skidata_headers('application/xml'), verify=False, timeout=15)
                if put_resp.status_code in (200, 201, 204):
                    return {'success': True, 'message': 'נוכחות הרכב (שהיה רשום בחניון מעל 7 ימים) אופסה ומספרי הרכב עודכנו בהצלחה!'}
            return {'success': False, 'message': 'לא ניתן להחליף את מספר הרכב בזמן שהרכב נמצא בחניון.'}
    except Exception as e:
        return {'success': False, 'message': str(e)}

# ============================================================================
# 3. WHATSAPP NOTIFICATIONS HELPER
# ============================================================================
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
        if not clean_p:
            return False, "מספר טלפון חסר"
        url = f"https://api.green-api.com/waInstance{green_id}/sendMessage/{green_token}"
        resp = requests.post(url, json={"chatId": f"{clean_p}@c.us", "message": text_message}, timeout=10)
        return (resp.status_code == 200), resp.text
    except Exception as e:
        print(f"Error sending WhatsApp message: {e}")
        return False, str(e)

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
            msg = (
                f"שלום {transfer.get('borrower_name') or ''}! 🚗\n"
                f"החניה שהזמנת (מדירה {from_apt}) פנויה וזמינה עבורך כעת ועד השעה *{transfer.get('end_time')}*.\n"
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

def run_scheduler_cycle():
    """רץ ברקע כל דקה: מפעיל חניות שהגיע זמנן, שולח תזכורת 30 דק' לפני סיום, ומחזיר מונים בסיום."""
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

    return jsonify({
        'success': True,
        'manager': {
            'username': mgr.get('username'),
            'email': mgr.get('email'),
            'project_number': p_num,
            'parking_name': b_settings.get('parking_name') or p_name
        },
        'settings': b_settings,
        'tenants': tenants,
        'shares': shares,
        'active_transfers': active_transfers
    })

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
        logo_data=data.get('logo_data')
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

    # נסה לשלוף את מכסת החניות הקבועה של הדירה מתוך שיידט
    pool_info = get_apartment_pooling_status(p_num, apt)
    base_max = pool_info.get('maxCounter', 1) if pool_info.get('success') else int(data.get('base_max_counter') or 1)

    tenant = TenantStore.create_tenant(
        project_number=p_num,
        parking_name=p_name,
        full_name=full_name,
        phone_number=clean_p,
        apartment_number=apt,
        base_max_counter=base_max,
        created_by=mgr.get('email')
    )

    # שליחת הודעת וואטסאפ אוטומטית לדייר החדש עם קישור ישיר לאתר
    host_url = request.host_url.rstrip('/')
    portal_link = f"{host_url}/tenant-portal?phone={display_il_phone(clean_p)}"
    welcome_msg = (
        f"שלום {full_name}! 🏢\n"
        f"צורפת למערכת ניהול ושיתוף החניות של *{p_name or 'המתחם'}* (דירה {apt}).\n\n"
        f"לכניסה למערכת (צפייה ועדכון רכבים, שחרור חניה או תפיסת חניה פנויה) לחץ על הקישור:\n"
        f"{portal_link}"
    )
    wa_ok, _ = send_whatsapp_message(clean_p, welcome_msg)
    wa_note = " (נשלחה הודעת וואטסאפ עם קישור לדייר)" if wa_ok else " (הדייר נשמר, אך שליחת וואטסאפ נכשלה)"

    return jsonify({'success': True, 'message': f'דייר (דירה {apt}) נוסף בהצלחה!{wa_note}', 'tenant': tenant, 'whatsapp_sent': wa_ok})

@tenant_bp.route('/api/tenant-manager/tenants/<int:tenant_id>/send-invite', methods=['POST'])
def api_tenant_manager_send_invite(tenant_id):
    mgr = _get_logged_in_tenant_manager()
    if not mgr:
        return jsonify({'success': False, 'message': 'לא מורשה'}), 401
    t = TenantStore.get_tenant_by_id(tenant_id)
    if not t:
        return jsonify({'success': False, 'message': 'דייר לא נמצא'})
    host_url = request.host_url.rstrip('/')
    clean_p = clean_il_phone(t.get('phone_number'))
    portal_link = f"{host_url}/tenant-portal?phone={display_il_phone(clean_p)}"
    p_name = t.get('parking_name') or mgr.get('parking_name') or 'המתחם'
    msg = (
        f"שלום {t.get('full_name')}! 🏢\n"
        f"קישור לכניסה למערכת החניות של *{p_name}* (דירה {t.get('apartment_number')}):\n"
        f"{portal_link}"
    )
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
    if not t:
        return jsonify({'success': False, 'message': 'דייר לא נמצא'})

    p_num = str(t.get('project_number') or mgr.get('project_number') or '')
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
    if request.method == 'DELETE':
        TenantStore.delete_tenant(tenant_id)
        return jsonify({'success': True, 'message': 'הדייר נמחק בהצלחה'})

    data = request.get_json() or {}
    p_num = str(mgr.get('project_number') or '')
    apt = str(data.get('apartment_number') or '').strip()
    pool_info = get_apartment_pooling_status(p_num, apt)
    auto_max = pool_info.get('maxCounter') if pool_info.get('success') else None

    TenantStore.update_tenant(
        tenant_id=tenant_id,
        full_name=data.get('full_name', ''),
        phone_number=data.get('phone_number', ''),
        apartment_number=apt,
        base_max_counter=auto_max,
        is_active=data.get('is_active', True)
    )
    return jsonify({'success': True, 'message': 'פרטי הדייר עודכנו והמכסה סונכרנה מהמערכת'})

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

        # Calculate duration in hours
        hours = 0.0
        try:
            ws = datetime.datetime.fromisoformat(str(tr['window_start']).replace('Z', ''))
            we = datetime.datetime.fromisoformat(str(tr['window_end']).replace('Z', ''))
            hours = max(0.0, round((we - ws).total_seconds() / 3600.0, 1))
        except Exception:
            pass

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
            'logo_data': b.get('logo_data') or ''
        })
    return jsonify({'success': False})

@tenant_bp.route('/api/tenant/send-otp', methods=['POST'])
def api_tenant_send_otp():
    data = request.get_json() or {}
    phone = data.get('phone_number')
    project_number = data.get('project_number')

    tenant = TenantStore.find_tenant_by_phone(phone, project_number)
    if not tenant:
        return jsonify({'success': False, 'message': 'מספר הטלפון לא רשום במערכת הדיירים. אנא פנה למנהל המתחם.'})

    otp_code = str(random.randint(100000, 999999))
    expires_iso = (get_il_now() + timedelta(minutes=10)).isoformat()
    TenantStore.save_otp(tenant['id'], otp_code, expires_iso)

    host_url = request.host_url.rstrip('/')
    magic_link = f"{host_url}/tenant-portal?phone={display_il_phone(tenant['phone_number'])}&code={otp_code}"

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
        'message': 'קוד אימות נשלח לוואטסאפ שלך!'
    })

@tenant_bp.route('/api/tenant/verify-otp', methods=['POST'])
def api_tenant_verify_otp():
    data = request.get_json() or {}
    phone = data.get('phone_number')
    code = str(data.get('otp_code') or '').strip()
    project_number = data.get('project_number')

    tenant = TenantStore.find_tenant_by_phone(phone, project_number)
    if not tenant:
        return jsonify({'success': False, 'message': 'משתמש לא נמצא'})

    saved_otp = str(tenant.get('mobile_otp') or '').strip()
    if not saved_otp or saved_otp != code:
        return jsonify({'success': False, 'message': 'קוד האימות שגוי'})

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

    auth_token = _create_tenant_mobile_token(tenant['id'])

    return jsonify({
        'success': True,
        'auth_token': auth_token,
        'tenant': {
            'id': tenant['id'],
            'full_name': tenant['full_name'],
            'phone_number': display_il_phone(tenant['phone_number']),
            'apartment_number': tenant['apartment_number'],
            'project_number': tenant['project_number'],
            'parking_name': tenant.get('parking_name') or ''
        }
    })

def _create_tenant_mobile_token(tenant_id):
    import hmac, hashlib
    secret = (os.getenv('SECRET_KEY') or 'sb-tenant-mobile-secret-2026').encode('utf-8')
    payload_str = f"{int(tenant_id)}:{int(time.time())}"
    sig = hmac.new(secret, payload_str.encode('utf-8'), hashlib.sha256).hexdigest()
    return f"{payload_str}:{sig}"

def _verify_tenant_mobile_token(token_str):
    import hmac, hashlib
    if not token_str or ':' not in token_str:
        return None
    parts = str(token_str).strip().split(':')
    if len(parts) != 3:
        return None
    tid_str, ts_str, sig = parts
    secret = (os.getenv('SECRET_KEY') or 'sb-tenant-mobile-secret-2026').encode('utf-8')
    expected = hmac.new(secret, f"{tid_str}:{ts_str}".encode('utf-8'), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        return int(tid_str)
    except Exception:
        return None

@tenant_bp.route('/api/tenant/logout', methods=['POST'])
def api_tenant_logout():
    session.pop('tenant_user_id', None)
    session.pop('tenant_project_number', None)
    session.pop('tenant_apartment', None)
    return jsonify({'success': True})

def _get_current_tenant():
    tid = session.get('tenant_user_id')
    if tid:
        now_ts = time.time()
        last_act = session.get('tenant_last_activity')
        if last_act and (now_ts - float(last_act) > SESSION_INACTIVITY_TIMEOUT_SEC):
            session.pop('tenant_user_id', None)
            session.pop('tenant_project_number', None)
            session.pop('tenant_apartment', None)
            session.pop('tenant_last_activity', None)
            return None
        session['tenant_last_activity'] = now_ts
        return TenantStore.get_tenant_by_id(tid)

    # תמיכה באפליקציית מובייל (Expo iOS / Android) באמצעות X-Tenant-Token
    mob_token = request.headers.get('X-Tenant-Token') or request.args.get('auth_token')
    if mob_token:
        mob_tid = _verify_tenant_mobile_token(mob_token)
        if mob_tid:
            return TenantStore.get_tenant_by_id(mob_tid)
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

    threading.Thread(target=run_scheduler_cycle, daemon=True).start()

    p_num = str(tenant['project_number'])
    my_apt = str(tenant['apartment_number'])

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

    all_shares = TenantStore.list_shares(p_num, active_only=True)
    my_shares = [sh for sh in all_shares if str(sh.get('owner_apartment')) == my_apt]

    available_slots = _compute_available_slots_for_tenant(p_num, my_apt, days_ahead=7)

    active_bookings = [
        tr for tr in TenantStore.list_transfers(project_number=p_num, statuses=['SCHEDULED', 'WAITING_FOR_EXIT', 'ACTIVE'])
        if str(tr.get('to_apartment')) == my_apt or str(tr.get('from_apartment')) == my_apt
    ]

    return jsonify({
        'success': True,
        'tenant': {
            'id': tenant['id'],
            'full_name': tenant['full_name'],
            'phone_number': display_il_phone(tenant['phone_number']),
            'apartment_number': my_apt,
            'base_max_counter': int(pooling_info.get('maxCounter') if pooling_info.get('success') else (tenant.get('base_max_counter') or 1)),
            'project_number': p_num,
            'parking_name': b_settings.get('parking_name') or tenant.get('parking_name') or f'מתחם {p_num}',
            'logo_data': b_settings.get('logo_data') or ''
        },
        'quota_limits': {
            'max_per_day': int(b_settings.get('max_bookings_per_day') or 5),
            'used_today': len(my_bookings_today),
            'max_per_month': int(b_settings.get('max_bookings_per_month') or 30),
            'used_this_month': len(my_Bookings_month)
        },
        'pooling': pooling_info,
        'subscribers': subs_info.get('subscribers', []),
        'my_shares': my_shares,
        'available_slots': available_slots,
        'active_bookings': active_bookings
    })

@tenant_bp.route('/api/tenant/update-plates', methods=['POST'])
def api_tenant_update_plates():
    tenant = _get_current_tenant()
    if not tenant:
        return jsonify({'success': False, 'message': 'לא מחובר'}), 401

    data = request.get_json() or {}
    sub_id = str(data.get('subscriber_id') or '').strip()
    if not sub_id:
        return jsonify({'success': False, 'message': 'חסר מזהה מנוי'})

    res = update_apartment_subscriber_plates(
        project_number=tenant['project_number'],
        apartment_number=tenant['apartment_number'],
        subscriber_id=sub_id,
        lpn1=data.get('lpn1', ''),
        lpn2=data.get('lpn2', ''),
        lpn3=data.get('lpn3', '')
    )
    return jsonify(res)

@tenant_bp.route('/api/tenant/share-spot', methods=['POST'])
def api_tenant_share_spot():
    tenant = _get_current_tenant()
    if not tenant:
        return jsonify({'success': False, 'message': 'לא מחובר'}), 401

    data = request.get_json() or {}
    start_time = (data.get('start_time') or '').strip()
    end_time = (data.get('end_time') or '').strip()
    spots_offered = int(data.get('spots_offered') or 1)
    share_target_type = data.get('share_target_type', 'POOL')
    target_apartment = str(data.get('target_apartment') or '').strip()
    schedule_type = data.get('schedule_type', 'WEEKLY')
    days_of_week = data.get('days_of_week', '')
    specific_date = data.get('specific_date', '')

    max_allowed_spots = int(tenant.get('base_max_counter') or 1)
    pool_chk = get_apartment_pooling_status(tenant['project_number'], tenant['apartment_number'])
    if pool_chk.get('success') and int(pool_chk.get('maxCounter') or 0) > max_allowed_spots:
        max_allowed_spots = int(pool_chk.get('maxCounter'))
    if spots_offered < 1 or spots_offered > max(1, max_allowed_spots):
        return jsonify({'success': False, 'message': f'כמות החניות לשחרור חייבת להיות בין 1 ל-{max(1, max_allowed_spots)} (כמות החניות של דירתך)'})

    if not start_time or not end_time or start_time >= end_time:
        return jsonify({'success': False, 'message': 'נא לבחור שעת התחלה ושעת סיום תקינות (שעת סיום אחרי שעת התחלה)'})

    if share_target_type == 'APT' and not target_apartment:
        return jsonify({'success': False, 'message': 'נא להזין את מספר הדירה שעבורה משחררים את החניה'})

    if schedule_type == 'WEEKLY' and not str(days_of_week).strip():
        return jsonify({'success': False, 'message': 'נא לבחור לפחות יום אחד בשבוע'})

    if schedule_type == 'ONCE' and not str(specific_date).strip():
        return jsonify({'success': False, 'message': 'נא לבחור תאריך לשחרור החניה'})

    created = TenantStore.create_share({
        'project_number': tenant['project_number'],
        'owner_tenant_id': tenant['id'],
        'owner_name': tenant['full_name'],
        'owner_apartment': tenant['apartment_number'],
        'spots_offered': spots_offered,
        'share_target_type': share_target_type,
        'target_apartment': target_apartment if share_target_type == 'APT' else None,
        'schedule_type': schedule_type,
        'days_of_week': days_of_week,
        'specific_date': specific_date,
        'start_time': start_time,
        'end_time': end_time
    })

    # אם שוחררה חניה במיוחד עבור דירה ספציפית, שלח לה הודעת וואטסאפ!
    if share_target_type == 'APT' and target_apartment:
        all_tenants = TenantStore.list_tenants(tenant['project_number'])
        for t in all_tenants:
            if str(t.get('apartment_number')) == target_apartment and t.get('phone_number'):
                host_url = request.host_url.rstrip('/')
                msg = (
                    f"שלום {t.get('full_name')} (דירה {target_apartment})! 🎁\n"
                    f"דירה {tenant['apartment_number']} ({tenant['full_name']}) שחררה עבורך {spots_offered} חניה/ות "
                    f"בין השעות *{start_time}* עד *{end_time}*.\n"
                    f"לצפייה ותפיסת החניה היכנס לפורטל הדיירים:\n{host_url}/tenant-portal"
                )
                send_whatsapp_message(t['phone_number'], msg)

    return jsonify({'success': True, 'message': 'הגדרת שחרור החניה נשמרה בהצלחה!', 'share': created})

@tenant_bp.route('/api/tenant/cancel-share/<int:share_id>', methods=['POST'])
def api_tenant_cancel_share(share_id):
    tenant = _get_current_tenant()
    if not tenant:
        return jsonify({'success': False, 'message': 'לא מחובר'}), 401
    TenantStore.deactivate_share(share_id, tenant['project_number'])
    return jsonify({'success': True, 'message': 'שחרור החניה בוטל'})

@tenant_bp.route('/api/tenant/claim-spot', methods=['POST'])
def api_tenant_claim_spot():
    """דייר לוקח חניה פנויה מהפול הכללי או חניה שפנויה עבורו (עם נעילת סלוט ובדיקת מכסה יומית/חודשית)."""
    tenant = _get_current_tenant()
    if not tenant:
        return jsonify({'success': False, 'message': 'לא מחובר'}), 401

    data = request.get_json() or {}
    share_id = int(data.get('share_id') or 0)
    booking_date = str(data.get('booking_date') or '').strip()

    p_num = str(tenant['project_number'])
    my_apt = str(tenant['apartment_number'])

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

    transfer = TenantStore.create_transfer({
        'share_id': share_id,
        'slot_index': slot_index,
        'project_number': p_num,
        'from_apartment': from_apt,
        'to_apartment': my_apt,
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

    # אם חלון הזמן כבר פעיל כעת - נסה להעביר את המונה מיד!
    if w_start_dt <= now < w_end_dt:
        act_res = try_activate_transfer(transfer)
        if act_res.get('activated'):
            return jsonify({
                'success': True,
                'message': f'החניה מדירה {from_apt} הופעלה עבורך מיד! מכסת החניות של דירתך עלתה ב-1 עד {share["end_time"]}.'
            })
        elif act_res.get('status') == 'WAITING_FOR_EXIT':
            return jsonify({
                'success': True,
                'message': f'החניה מדירה {from_apt} שוריינה עבורך! הרכב של דירה {from_apt} עדיין בחניון – ברגע שייצא, המכסה תועבר אליך ותקבל הודעת וואטסאפ.'
            })

    return jsonify({
        'success': True,
        'message': f'החניה מדירה {from_apt} שוריינה עבורך לתאריך {booking_date} בין {share["start_time"]} ל-{share["end_time"]}! תקבל הודעת וואטסאפ ברגע שהחניה תיכנס לתוקף.'
    })

@tenant_bp.route('/api/tenant/release-booking/<int:transfer_id>', methods=['POST'])
def api_tenant_release_booking(transfer_id):
    """סיום מוקדם / ביטול הזמנת חניה ע"י הדייר והחזרת המונה לבעל החניה."""
    tenant = _get_current_tenant()
    if not tenant:
        return jsonify({'success': False, 'message': 'לא מחובר'}), 401

    tr = TenantStore.get_transfer_by_id(transfer_id)
    if not tr or str(tr.get('project_number')) != str(tenant['project_number']):
        return jsonify({'success': False, 'message': 'הזמנה לא נמצאה'})

    my_apt = str(tenant['apartment_number'])
    if str(tr.get('to_apartment')) != my_apt and str(tr.get('from_apartment')) != my_apt:
        return jsonify({'success': False, 'message': 'אין הרשאה להזמנה זו'})

    restore_active_transfer(tr, early_cancel=True)
    return jsonify({'success': True, 'message': 'ההזמנה הסתיימה והמכסה הוחזרה לדירה המקורית!'})
