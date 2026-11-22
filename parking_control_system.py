import os
import re
import json
import time
import hmac
import hashlib
import random
import sqlite3
import base64
import socket
import threading
import datetime
from datetime import timezone, timedelta
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
import urllib3
from flask import Blueprint, render_template, request, jsonify, session, redirect, Response

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

parking_control_bp = Blueprint('parking_control_bp', __name__)

@parking_control_bp.before_request
def _handle_control_cors_preflight():
    if request.method == 'OPTIONS':
        resp = Response('', status=200)
        resp.headers['Access-Control-Allow-Origin'] = '*'
        resp.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
        resp.headers['Access-Control-Allow-Headers'] = 'Content-Type, X-Control-Token, X-Control-Project, Authorization'
        return resp

@parking_control_bp.after_request
def _add_control_cors_headers(resp):
    resp.headers['Access-Control-Allow-Origin'] = '*'
    resp.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    resp.headers['Access-Control-Allow-Headers'] = 'Content-Type, X-Control-Token, X-Control-Project, Authorization'
    return resp

# ============================================================================
# 0. HELPERS & HTTP SESSION POOLING
# ============================================================================
_sb_session = requests.Session()
_sb_session.verify = False
_sb_adapter = requests.adapters.HTTPAdapter(pool_connections=25, pool_maxsize=25)
_sb_session.mount("https://", _sb_adapter)
_sb_session.mount("http://", _sb_adapter)

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

def _get_app_module():
    import sys
    return sys.modules.get('app') or sys.modules.get('__main__')

def _get_supabase():
    app_mod = _get_app_module()
    return getattr(app_mod, 'supabase', None) if app_mod else None

def send_whatsapp_message(phone_number, text_message):
    """שליחת הודעת וואטסאפ דרך GreenAPI הקיים במערכת."""
    try:
        import whatsapp_service
        green_id = whatsapp_service.GREEN_API_ID
        green_token = whatsapp_service.GREEN_API_TOKEN
        if not green_id or not green_token:
            print(f"[WhatsApp Control Mock] To {phone_number}: {text_message}")
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
# 1. LOCAL SQLITE STORAGE FOR AUDIT LOGS, SESSIONS & CACHED CONFIG
# ============================================================================
SQLITE_CONTROL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'parking_control_data.db')
_db_lock = threading.Lock()

def _init_control_sqlite():
    with _db_lock:
        conn = sqlite3.connect(SQLITE_CONTROL_PATH)
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS control_audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_number TEXT NOT NULL,
                parking_name TEXT,
                user_id INTEGER,
                username TEXT,
                phone_number TEXT,
                action_type TEXT NOT NULL,
                cell_number TEXT,
                unit_number TEXT,
                unit_name TEXT,
                command_code TEXT,
                plate TEXT,
                reason TEXT,
                sb_command_ok INTEGER DEFAULT 0,
                sb_audit_ok INTEGER DEFAULT 0,
                details_json TEXT,
                created_at TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS control_otp_sessions (
                phone_number TEXT PRIMARY KEY,
                user_id INTEGER,
                project_number TEXT,
                otp_code TEXT,
                otp_expires_at TEXT,
                updated_at TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS control_local_parkings (
                project_number TEXT PRIMARY KEY,
                parking_name TEXT,
                ip_address TEXT,
                port INTEGER DEFAULT 8443,
                updated_at TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS control_local_users (
                user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT,
                phone_number TEXT,
                verification_code TEXT,
                project_number TEXT,
                parking_name TEXT,
                code_type TEXT DEFAULT 'parking_control_manager',
                company_list TEXT DEFAULT 'ALL',
                role TEXT DEFAULT 'parking_control_manager'
            )
        """)
        # Seed default local parking 3050 (10.35.122.200) for local server operation (like tenant_system)
        cur.execute("""
            INSERT OR IGNORE INTO control_local_parkings (project_number, parking_name, ip_address, port, updated_at)
            VALUES ('3050', 'מבנה תוצרת הארץ (10.35.122.200)', '10.35.122.200', 8443, ?)
        """, (get_il_now().isoformat(),))
        conn.commit()
        conn.close()

_init_control_sqlite()

def record_local_audit_event(project_number, parking_name, user_obj, action_type, cell="", unit="", unit_name="", command_code="", plate="", reason="", sb_cmd_ok=True, sb_audit_ok=False, details=None):
    now_iso = get_il_now().strftime("%Y-%m-%d %H:%M:%S")
    u_id = user_obj.get('user_id') if isinstance(user_obj, dict) else 0
    u_name = (user_obj.get('username') or user_obj.get('email') or 'מנהל חניון') if isinstance(user_obj, dict) else 'מנהל חניון'
    u_phone = (user_obj.get('phone_number') or '') if isinstance(user_obj, dict) else ''
    details_str = json.dumps(details or {}, ensure_ascii=False)
    try:
        with _db_lock:
            conn = sqlite3.connect(SQLITE_CONTROL_PATH)
            conn.execute("""
                INSERT INTO control_audit_events
                (project_number, parking_name, user_id, username, phone_number, action_type, cell_number, unit_number, unit_name, command_code, plate, reason, sb_command_ok, sb_audit_ok, details_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                str(project_number or ''),
                str(parking_name or ''),
                int(u_id or 0),
                str(u_name),
                str(u_phone),
                str(action_type),
                str(cell or '1'),
                str(unit or ''),
                str(unit_name or ''),
                str(command_code or ''),
                str(plate or ''),
                str(reason or ''),
                1 if sb_cmd_ok else 0,
                1 if sb_audit_ok else 0,
                details_str,
                now_iso
            ))
            conn.commit()
            conn.close()
    except Exception as e:
        print(f"Error recording local audit event: {e}")

def get_recent_local_audit_events(project_number, limit=40):
    try:
        with _db_lock:
            conn = sqlite3.connect(SQLITE_CONTROL_PATH)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM control_audit_events WHERE project_number = ? ORDER BY id DESC LIMIT ?",
                (str(project_number), int(limit))
            ).fetchall()
            conn.close()
            return [dict(r) for r in rows]
    except Exception:
        return []

# ============================================================================
# 2. SENSITIVE OPERATIONS SESSION AUTH (30-MINUTE TIMEOUT + WHATSAPP OTP)
# ============================================================================
# מערכת רגישה לתפעול מחסומים - טוקן זיהוי תקף עד 30 דקות (ניתוק אוטומטי אחרי 30 דקות בגלל בטיחות המידע),
# ובכל כניסה חדשה מתבצע אימות OTP ישיר מהוואטסאפ.
CONTROL_TOKEN_MAX_AGE_SEC = 30 * 60  # 30 minutes max session lifetime for information security

ALLOWED_CONTROL_CODE_TYPES = (
    'parking_control_manager',
    'control_parking',
    'parking_controller',
    'mobile_controller',
    'parking_manager',
    'master'
)

def _create_control_token(user_id, phone_number, project_number):
    secret = (os.getenv('SECRET_KEY') or 'sb-parking-control-secret-2026').encode('utf-8')
    clean_p = clean_il_phone(phone_number)
    ts = int(time.time())
    payload = f"{int(user_id or 0)}:{clean_p}:{project_number}:{ts}"
    sig = hmac.new(secret, payload.encode('utf-8'), hashlib.sha256).hexdigest()
    return f"{payload}:{sig}"

def _verify_control_token(token_str):
    if not token_str or ':' not in token_str:
        return None
    parts = str(token_str).strip().split(':')
    if len(parts) != 5:
        return None
    uid_s, clean_p, proj_s, ts_s, sig = parts
    secret = (os.getenv('SECRET_KEY') or 'sb-parking-control-secret-2026').encode('utf-8')
    expected = hmac.new(secret, f"{uid_s}:{clean_p}:{proj_s}:{ts_s}".encode('utf-8'), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        ts_val = int(ts_s)
        if time.time() - ts_val > CONTROL_TOKEN_MAX_AGE_SEC:
            return None
        return {
            'user_id': int(uid_s),
            'phone_number': clean_p,
            'project_number': proj_s,
            'issued_at': ts_val
        }
    except Exception:
        return None

def _find_control_users_by_phone_or_code(phone_raw=None, initial_code=None):
    """
    מחפש משתמשי מנהל חניון / בקרת חניון בטבלת user_parkings (ב-Supabase) ובגיבוי המקומי (control_local_users ב-SQLite, כמו ב-tenant_system).
    """
    sb = _get_supabase()
    clean_p = clean_il_phone(phone_raw) if phone_raw else ""

    matched = []
    if sb:
        try:
            res = sb.table('user_parkings').select('*').execute()
            all_users = res.data or []
            for u in all_users:
                ct = str(u.get('code_type') or '').strip().lower().replace('-', '_').replace(' ', '_')
                role = str(u.get('role') or '').strip().lower()
                is_allowed_type = (ct in ALLOWED_CONTROL_CODE_TYPES) or (role in ('admin', 'master', 'mobile_controller', 'parking_control_manager'))
                if not is_allowed_type:
                    continue

                u_phone_clean = clean_il_phone(u.get('phone_number') or '')
                u_ver_code = str(u.get('verification_code') or '').strip()
                u_username = str(u.get('username') or '').strip()

                if clean_p and u_phone_clean == clean_p:
                    matched.append(u)
                elif initial_code and len(str(initial_code).strip()) >= 4:
                    ic = str(initial_code).strip()
                    if u_ver_code == ic or u_username.lower() == ic.lower():
                        matched.append(u)
        except Exception as e:
            print(f"Error searching control users in Supabase: {e}")

    # Check local SQLite mirror/fallback (like tenant_system.py)
    if not matched:
        try:
            with _db_lock:
                conn = sqlite3.connect(SQLITE_CONTROL_PATH)
                conn.row_factory = sqlite3.Row
                local_users = [dict(r) for r in conn.execute("SELECT * FROM control_local_users").fetchall()]
                for u in local_users:
                    u_phone_clean = clean_il_phone(u.get('phone_number') or '')
                    u_ver_code = str(u.get('verification_code') or '').strip()
                    u_username = str(u.get('username') or '').strip()
                    if clean_p and u_phone_clean == clean_p:
                        matched.append(u)
                    elif initial_code and len(str(initial_code).strip()) >= 3:
                        ic = str(initial_code).strip()
                        if u_ver_code == ic or u_username.lower() == ic.lower():
                            matched.append(u)
                # If running locally (sb is None) and no user exists yet for this phone, auto-register for local testing against 3050 (10.35.122.200)
                if not matched and not sb and (clean_p or initial_code):
                    p_to_save = clean_p or "972500000000"
                    cur = conn.cursor()
                    cur.execute("""
                        INSERT INTO control_local_users (username, phone_number, verification_code, project_number, parking_name, code_type, company_list, role)
                        VALUES (?, ?, ?, '3050', 'מבנה תוצרת הארץ (10.35.122.200)', 'parking_control_manager', 'ALL', 'parking_control_manager')
                    """, (f"מנהל חניון ({display_il_phone(p_to_save)})", p_to_save, str(initial_code or '3050')))
                    new_uid = cur.lastrowid
                    conn.commit()
                    matched.append({
                        'user_id': new_uid,
                        'username': f"מנהל חניון ({display_il_phone(p_to_save)})",
                        'phone_number': p_to_save,
                        'verification_code': str(initial_code or '3050'),
                        'project_number': '3050',
                        'parking_name': 'מבנה תוצרת הארץ (10.35.122.200)',
                        'code_type': 'parking_control_manager',
                        'company_list': 'ALL',
                        'role': 'parking_control_manager'
                    })
                conn.close()
        except Exception as e:
            print(f"Error searching local control users: {e}")

    # Prioritize parking_control_manager first
    matched.sort(key=lambda x: 0 if str(x.get('code_type') or '').strip().lower() == 'parking_control_manager' else 1)
    return matched

def _get_authenticated_control_user():
    """
    מאמת את מנהל החניון מתוך Header (X-Control-Token) או מתוך Query (auth_token / token) או מתוך Flask Session.
    """
    hdr_token = request.headers.get('X-Control-Token') or request.args.get('auth_token') or request.args.get('token')
    req_proj = request.headers.get('X-Control-Project') or request.args.get('project_number')
    sb = _get_supabase()

    if hdr_token:
        tk_data = _verify_control_token(hdr_token)
        if tk_data:
            uid = tk_data['user_id']
            proj = req_proj or tk_data['project_number']
            if sb and uid:
                try:
                    res = sb.table('user_parkings').select('*').eq('user_id', uid).execute()
                    if res.data:
                        u = dict(res.data[0])
                        if proj and str(proj) != '0':
                            u['active_project_number'] = str(proj)
                        else:
                            u['active_project_number'] = str(u.get('project_number') or '')
                        return u
                except Exception:
                    pass
            return {
                'user_id': uid,
                'username': 'מנהל חניון',
                'phone_number': tk_data['phone_number'],
                'project_number': proj,
                'active_project_number': str(proj),
                'parking_name': f'חניון {proj}',
                'code_type': 'parking_control_manager',
                'company_list': 'ALL'
            }

    # Check active web session
    if 'user_email' in session and sb:
        try:
            res = sb.table('user_parkings').select('*').eq('email', session['user_email']).execute()
            if res.data:
                u = dict(res.data[0])
                ct = str(u.get('code_type') or '').strip().lower().replace('-', '_')
                if ct in ALLOWED_CONTROL_CODE_TYPES or u.get('role') in ('admin', 'master'):
                    u['active_project_number'] = str(req_proj or session.get('control_active_project') or u.get('project_number') or '')
                    return u
        except Exception:
            pass

    if session.get('control_user_id') and sb:
        try:
            res = sb.table('user_parkings').select('*').eq('user_id', int(session['control_user_id'])).execute()
            if res.data:
                u = dict(res.data[0])
                u['active_project_number'] = str(req_proj or session.get('control_active_project') or u.get('project_number') or '')
                return u
        except Exception:
            pass

    return None

def _get_available_parkings_for_user(user_obj, all_phone_users=None):
    """
    מחזיר את רשימת החניונים שלמשתמש (או למספר הטלפון שלו על פני מספר רשומות חניונים שונים) יש הרשאה אליהם.
    תומך מלא במקרה שמספר טלפון אחד רשום ביותר מחניון אחד בטבלת user_parkings!
    """
    sb = _get_supabase()
    if all_phone_users is None and user_obj:
        clean_p = clean_il_phone(user_obj.get('phone_number') or '')
        if clean_p:
            all_phone_users = _find_control_users_by_phone_or_code(phone_raw=clean_p)
    users_to_scan = all_phone_users if all_phone_users else ([user_obj] if user_obj else [])

    has_global_access = False
    allowed_projects_map = {}  # project_number -> {user_id, parking_name, company_list}
    for u in users_to_scan:
        if not u:
            continue
        ct = str(u.get('code_type') or '').strip().lower()
        access_lvl = str(u.get('access_level') or '').strip().lower()
        u_proj = str(u.get('project_number') or '').strip()
        if ct == 'master' or access_lvl in ('master', 'group_access', 'group_manager') or u_proj in ('0', ''):
            has_global_access = True
        if u_proj and u_proj != '0':
            if u_proj not in allowed_projects_map:
                allowed_projects_map[u_proj] = {
                    'user_id': u.get('user_id'),
                    'project_number': u_proj,
                    'parking_name': u.get('parking_name') or f'חניון {u_proj}',
                    'company_list': u.get('company_list') or 'ALL',
                    'username': u.get('username') or ''
                }

    parkings_list = []
    seen_projs = set()
    if sb:
        try:
            p_res = sb.table('parkings').select('id, name, description, ip_address, port, is_active').execute()
            for p in (p_res.data or []):
                p_num = str(p.get('description') or '').strip()
                if not p_num or not p.get('ip_address'):
                    continue
                if has_global_access or p_num in allowed_projects_map:
                    u_meta = allowed_projects_map.get(p_num) or {}
                    seen_projs.add(p_num)
                    parkings_list.append({
                        'user_id': u_meta.get('user_id') or (user_obj.get('user_id') if user_obj else None),
                        'project_number': p_num,
                        'parking_name': p.get('name') or u_meta.get('parking_name') or f'חניון {p_num}',
                        'company_list': u_meta.get('company_list') or (user_obj.get('company_list') if user_obj else 'ALL'),
                        'ip_address': p.get('ip_address'),
                        'port': p.get('port', 8443)
                    })
        except Exception:
            pass

    for p_num, u_meta in allowed_projects_map.items():
        if p_num not in seen_projs:
            seen_projs.add(p_num)
            p_name = u_meta.get('parking_name') or f'חניון {p_num}'
            parkings_list.append({
                'user_id': u_meta.get('user_id'),
                'project_number': p_num,
                'parking_name': p_name,
                'project_name': p_name,
                'company_list': u_meta.get('company_list') or 'ALL'
            })

    # Include local SQLite parkings if matching or if parkings_list is empty
    try:
        with _db_lock:
            conn = sqlite3.connect(SQLITE_CONTROL_PATH)
            conn.row_factory = sqlite3.Row
            for lp in conn.execute("SELECT * FROM control_local_parkings").fetchall():
                p_num = str(lp['project_number'])
                if p_num not in seen_projs and (has_global_access or p_num in allowed_projects_map or not parkings_list):
                    seen_projs.add(p_num)
                    p_name = lp['parking_name'] or f'חניון {p_num}'
                    parkings_list.append({
                        'user_id': user_obj.get('user_id') if user_obj else 1,
                        'project_number': p_num,
                        'parking_name': p_name,
                        'project_name': p_name,
                        'company_list': 'ALL',
                        'ip_address': lp['ip_address'],
                        'port': lp['port'] or 8443
                    })
            conn.close()
    except Exception:
        pass

    for item in parkings_list:
        if 'project_name' not in item:
            item['project_name'] = item.get('parking_name') or f"חניון {item.get('project_number')}"

    return parkings_list

# ============================================================================
# 3. S&B PARKING SERVER CONNECTION & PROTOCOL ENGINE
# ============================================================================
_conn_cache = {}
_geom_cache = {}
_live_units_cache = {}  # project_number -> {"units": {}, "timestamp": 0}
_image_bytes_cache = {}
_cache_lock = threading.Lock()

COMMANDS_MAP = {
    "OPEN": (42250, "פתיחת מחסום ידנית (HAND_OPEN)"),
    "CLOSE": (42251, "סגירת מחסום ידנית (HAND_CLOSE)"),
    "LOCK_BARRIER": (42254, "נעילת מחסום פתוח/קבוע (BLOCK_CLOSED)"),
    "UNLOCK_BARRIER": (42255, "שחרור נעילת מחסום (UNBLOCK_CLOSED)"),
    "BLOCK_DEVICE": (41228, "נעילת/חסימת עמדה (EV_DEVICE_BLOCKED)"),
    "UNBLOCK_DEVICE": (41229, "שחרור חסימת עמדה (EV_DEVICE_NOT_BLOCKED)"),
    "OUT_OF_ORDER": (44545, "הוצאת עמדה משירות (OUT_OF_ORDER)"),
    "IN_ORDER": (44546, "החזרת עמדה לשירות (IN_ORDER)"),
    "RETRIGGER_LPR": (42469, "קריאת מצלמת LPR מחדש (RETRIGGER_LPR)"),
    "CANCEL_PAYMENT": (42468, "ביטול תהליך תשלום בעמדה (CANCEL_PAYMENT)")
}

def _get_parking_conn(project_number):
    p_key = str(project_number or '').strip()
    if not p_key:
        return None
    now_ts = time.time()
    with _cache_lock:
        cached = _conn_cache.get(p_key)
        if cached and (now_ts - cached.get('ts', 0) < 300):
            return cached

    app_mod = _get_app_module()
    if app_mod:
        fn = getattr(app_mod, 'get_parking_connection_details', None)
        if fn:
            try:
                details = fn(p_key)
                if details and details.get('ip_address'):
                    details = dict(details)
                    details['ts'] = now_ts
                    with _cache_lock:
                        _conn_cache[p_key] = details
                    return details
            except Exception:
                pass

    sb = _get_supabase()
    if sb:
        try:
            p_res = sb.table('parkings').select('ip_address, port, name, description').eq('description', p_key).execute()
            if p_res.data and p_res.data[0].get('ip_address'):
                d = {
                    'ip_address': p_res.data[0]['ip_address'],
                    'port': p_res.data[0].get('port') or 8443,
                    'name': p_res.data[0].get('name') or f'חניון {p_key}',
                    'ts': now_ts
                }
                with _cache_lock:
                    _conn_cache[p_key] = d
                return d
        except Exception:
            pass

    # Fallback to local SQLite control_local_parkings (like tenant_system.py)
    try:
        with _db_lock:
            conn = sqlite3.connect(SQLITE_CONTROL_PATH)
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM control_local_parkings WHERE project_number = ?", (p_key,)).fetchone()
            if not row:
                row = conn.execute("SELECT * FROM control_local_parkings LIMIT 1").fetchone()
            conn.close()
            if row and row['ip_address']:
                d = {
                    'ip_address': row['ip_address'],
                    'port': int(row['port'] or 8443),
                    'name': row['parking_name'] or f'חניון {p_key}',
                    'ts': now_ts
                }
                with _cache_lock:
                    _conn_cache[p_key] = d
                return d
    except Exception:
        pass
    return None

def make_sb_request(method, ip, port, endpoint, user="2022", password="2022", params=None, data=None, headers=None, timeout=5):
    req_ip = str(ip or "").strip()
    req_port = int(port or 8443)
    # Automatic local LAN routing when running on the developer's machine (10.35.122.200:8443 instead of NAT 192.117.0.122:8122)
    if req_ip == "192.117.0.122" and os.path.exists(r"C:\S-B-Parking-reports\sb_oracle_helper\ojdbc6.jar"):
        req_ip = "10.35.122.200"
        req_port = 8443
    url = f"https://{req_ip}:{req_port}{endpoint}"
    req_headers = {"Accept": "application/xml, application/json, text/plain, */*"}
    if headers:
        req_headers.update(headers)
    try:
        resp = _sb_session.request(
            method=method,
            url=url,
            params=params,
            data=data,
            auth=(user, password),
            timeout=timeout,
            headers=req_headers
        )
        return {
            "status": resp.status_code,
            "data": resp.content,
            "text": resp.text,
            "content_type": resp.headers.get("Content-Type", ""),
            "url": url
        }
    except Exception as e:
        return {
            "status": 500,
            "error": str(e),
            "data": b"",
            "text": "",
            "url": url
        }

def decode_single_state_20bytes(hex_str):
    """
    מפענח מחרוזת בת 40 תווי HEX (20 בייטים) של <device-single-state> לפי תקן S&B DeviceControlWebService:
    מחזיר רשימת התראות/מצבים פעילים כולל זיהוי האם העמדה חסומה/נעולה והאם המחסום פתוח.
    """
    if not hex_str or len(str(hex_str).strip()) < 4:
        return {"active_states": [], "is_locked": False, "is_barrier_open": False, "is_out_of_order": False, "warnings": []}

    clean_hex = re.sub(r'[^0-9A-Fa-f]', '', str(hex_str).strip()).ljust(40, '0')[:40]
    active_ids = set()
    for byte_idx in range(20):
        byte_hex = clean_hex[byte_idx * 2 : byte_idx * 2 + 2]
        try:
            byte_val = int(byte_hex, 16)
        except ValueError:
            byte_val = 0
        for bit_offset in range(8):
            # D7 is first state in byte, D0 is 8th state in byte
            bit_mask = 1 << (7 - bit_offset)
            if byte_val & bit_mask:
                stat_id = byte_idx * 8 + bit_offset + 1
                active_ids.add(stat_id)

    STATE_LABELS_HE = {
        1: "תקין ובפעולה",
        2: "בקר אזורי מנותק (Offline)",
        3: "תקלת חשמל",
        4: "דלת עמדה פתוחה",
        5: "פריצת מחסום (Forced Entry)",
        6: "עובד במצב עצמאי (Stand-alone)",
        7: "מחוץ לשירות ידנית",
        8: "מחוץ לשירות - באתחול",
        21: "פקק ביציאה (Traffic Jam)",
        22: "עמדה חסומה / נעולה (Device Blocked)",
        23: "עמדה במצב שירות טכנאי",
        69: "זרוע מחסום מורמת זמן רב",
        70: "מיקום זרוע מחסום שגוי",
        71: "זרוע מחסום מנותקת / שבורה!",
        72: "מחסום נעול במצב פתוח (Barrier Raised Locked)",
        80: "חניון מלא (Occupied)",
        82: "תקלת מדפסת יומן",
        83: "נגמר נייר במדפסת יומן",
        84: "נייר עומד להיגמר במדפסת",
        86: "תקלת מדפסת קבלות",
        87: "נגמר נייר במדפסת קבלות",
        88: "נייר קבלות עומד להיגמר",
        89: "קופסת איסוף כרטיסים מלאה",
        93: "נגמרו כרטיסים במחסנית 1",
        96: "מעט כרטיסים במחסנית 1",
        97: "מצב מחסום 5 (פתוח קבוע)",
        101: "מצב מחסום 1 (סגור קבוע)",
        102: "מסוף אשראי חיצוני לא זמין",
        151: "תצוגה מחוץ לשירות",
        152: "מסוף אשראי (EPT) מחוץ לשירות"
    }

    is_locked = (22 in active_ids) or (72 in active_ids) or (97 in active_ids) or (101 in active_ids)
    is_barrier_open = (72 in active_ids) or (97 in active_ids) or (69 in active_ids)
    is_out_of_order = (2 in active_ids) or (7 in active_ids) or (8 in active_ids)

    warnings = []
    for sid in sorted(active_ids):
        if sid != 1 and sid in STATE_LABELS_HE:
            warnings.append({"id": sid, "text": STATE_LABELS_HE[sid]})

    return {
        "active_states": sorted(active_ids),
        "is_locked": is_locked,
        "is_barrier_open": is_barrier_open,
        "is_out_of_order": is_out_of_order,
        "warnings": warnings
    }

def get_parking_geometry_and_states(project_number, ip, port, force_refresh=False):
    """
    שולף את כל הנתיבים והמכשירים בחניון מ-DeviceControlWebService/geometry
    ומעשיר אותם בסטטוס החי מ-DeviceControlWebService/lastevents/200 ובתמונת/לוחית LPR אחרונה.
    """
    p_key = str(project_number)
    now_ts = time.time()
    geom_devices = []

    with _cache_lock:
        cached_g = _geom_cache.get(p_key)
        if not force_refresh and cached_g and (now_ts - cached_g["ts"] < 120):
            geom_devices = [dict(d) for d in cached_g["devices"]]

    if not geom_devices:
        res = make_sb_request("GET", ip, port, "/DeviceControlWebService/geometry", timeout=4)
        if res["status"] == 200 and res["data"]:
            try:
                xml_text = res["data"].decode("utf-8", errors="replace")
                xml_text = re.sub(r'\sxmlns="[^"]+"', '', xml_text)
                root = ET.fromstring(xml_text)

                for cell in root.findall(".//cell-computer"):
                    cell_name = (cell.findtext("name") or "").strip()
                    cell_num = (cell.findtext("number") or "1").strip()

                    # Devices directly under cell-computer (e.g. Cashier / PKA)
                    for fac in cell.findall(".//facility"):
                        fac_name = (fac.findtext("name") or "").strip()
                        fac_num = (fac.findtext("number") or "").strip()
                        for dev in fac.findall(".//field-device"):
                            dev_num = (dev.findtext("number") or "").strip()
                            dev_name = (dev.findtext("name") or "").strip()
                            if not dev_num:
                                continue
                            num_int = int(dev_num) if dev_num.isdigit() else 0
                            name_l = dev_name.lower()
                            if 100 <= num_int <= 199 or "entry" in name_l or "כניסה" in name_l:
                                direction = "entry"
                                category_he = "כניסה"
                            elif 200 <= num_int <= 299 or "exit" in name_l or "יציאה" in name_l:
                                direction = "exit"
                                category_he = "יציאה"
                            elif 300 <= num_int <= 399 or "pass" in name_l or "מעבר" in name_l:
                                direction = "passage"
                                category_he = "מעבר"
                            elif 600 <= num_int <= 699:
                                direction = "pka"
                                category_he = "מכונת תשלום"
                            else:
                                direction = "other"
                                category_he = "בקר/עמדה"

                            geom_devices.append({
                                "number": dev_num,
                                "name": dev_name or f"{category_he} {dev_num}",
                                "facility_name": fac_name or "חניון ראשי",
                                "facility_number": fac_num or "1",
                                "cell_number": cell_num or "1",
                                "cell_name": cell_name,
                                "direction": direction,
                                "category_he": category_he
                            })

                def _lane_sort_key(d):
                    fac_n = int(d["facility_number"]) if str(d.get("facility_number")).isdigit() else 9999
                    dir_rank = {"entry": 1, "exit": 2, "passage": 3}.get(d.get("direction"), 4)
                    dev_n = int(d["number"]) if str(d["number"]).isdigit() else 9999
                    return (fac_n, dir_rank, dev_n)

                geom_devices.sort(key=_lane_sort_key)
                with _cache_lock:
                    _geom_cache[p_key] = {"devices": geom_devices, "ts": now_ts}
            except Exception as e:
                print(f"Error parsing geometry for project {p_key}: {e}")

    # Poll lastevents/150 for lane statuses, and fetch latest license plate per lane once every 45 seconds
    events_by_dev = {}
    live_lpr_units = {}
    with _cache_lock:
        if p_key in _live_units_cache and isinstance(_live_units_cache[p_key].get("units"), dict):
            live_lpr_units = dict(_live_units_cache[p_key]["units"])
            cache_age = now_ts - _live_units_cache[p_key].get("timestamp", 0)
        else:
            cache_age = 9999

    def _fetch_last_events():
        ev_res = make_sb_request("GET", ip, port, "/DeviceControlWebService/lastevents/150", timeout=3.5)
        if ev_res["status"] == 200 and ev_res["data"]:
            try:
                ev_xml = re.sub(r'\sxmlns="[^"]+"', '', ev_res["data"].decode("utf-8", errors="replace"))
                ev_root = ET.fromstring(ev_xml)
                all_ev = ev_root.findall(".//event")
                for ev in reversed(all_ev):
                    fdn = (ev.findtext("field-device-number") or "").strip()
                    if not fdn:
                        continue
                    d_state = (ev.findtext("device-state") or "").strip()
                    s_state = (ev.findtext("device-single-state") or ev.findtext("single-state") or "").strip()
                    dyn_state = (ev.findtext("device-high-dyn-state") or "").strip()
                    ev_txt = (ev.findtext("event-text") or ev.findtext("text") or "").strip()
                    ev_time = (ev.findtext("event-date-time") or ev.findtext("time") or "").strip()
                    alarm_val = (ev.findtext("alarm") or "0").strip()

                    if fdn not in events_by_dev:
                        events_by_dev[fdn] = {
                            "device_state": int(d_state) if d_state.isdigit() else 1,
                            "single_state_hex": s_state,
                            "high_dyn_hex": dyn_state,
                            "recent_events": []
                        }
                    if ev_txt and len(events_by_dev[fdn]["recent_events"]) < 6:
                        fmt_t = ev_time
                        if len(ev_time) == 14 and ev_time.isdigit():
                            fmt_t = f"{ev_time[8:10]}:{ev_time[10:12]}:{ev_time[12:14]} ({ev_time[6:8]}/{ev_time[4:6]})"
                        events_by_dev[fdn]["recent_events"].append({
                            "time": fmt_t,
                            "text": ev_txt,
                            "alarm": alarm_val == "1"
                        })
            except Exception as e:
                print(f"Error parsing lastevents: {e}")

    def _fetch_latest_plates_snapshot():
        if not force_refresh and live_lpr_units and cache_age < 45:
            return
        # 1. Quick check of /vehicle-api/live-events.jsp
        try:
            lpr_res = make_sb_request("GET", ip, port, "/vehicle-api/live-events.jsp", params={"since": "0", "timeout": "100"}, timeout=2.0)
            if lpr_res["status"] == 200 and lpr_res["data"]:
                parsed = json.loads(lpr_res["data"].decode("utf-8", errors="replace"))
                if isinstance(parsed.get("units"), dict):
                    for uk, uv in parsed["units"].items():
                        if uv.get("plate"):
                            live_lpr_units[str(uk)] = uv
        except Exception:
            pass

        # 2. Single lightweight SQL query to UDBIDENTDATA for latest plate per device (no images!)
        import subprocess
        helper_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sb_oracle_helper")
        jar_path = os.path.join(helper_dir, "ojdbc6.jar")
        class_file = os.path.join(helper_dir, "SBOracleReportHelper.class")
        oracle_ip = "10.35.122.200" if str(ip) in ("192.117.0.122", "10.35.122.200", "") else str(ip)
        if oracle_ip and os.path.exists(jar_path) and os.path.exists(class_file):
            try:
                cp_sep = ";" if os.name == "nt" else ":"
                cp_arg = f"{helper_dir}{cp_sep}{jar_path}"
                proc = subprocess.run(
                    ["java", "-cp", cp_arg, "SBOracleReportHelper", oracle_ip, "LATEST_PLATES"],
                    capture_output=True,
                    timeout=4
                )
                if proc.returncode == 0 and proc.stdout:
                    for r_line in proc.stdout.decode("utf-8", errors="replace").splitlines():
                        ln = r_line.strip()
                        if not ln or ln.startswith("[SECTION:"):
                            continue
                        pts = ln.split("\t")
                        if len(pts) >= 2:
                            uk = str(pts[0]).strip()
                            lp_val = str(pts[1]).strip()
                            dt_val = pts[2].strip() if len(pts) > 2 else ""
                            if uk and lp_val and len(lp_val) >= 5:
                                live_lpr_units[uk] = {
                                    "unit": uk,
                                    "plate": lp_val,
                                    "raw": lp_val,
                                    "event_time": dt_val
                                }
            except Exception:
                pass

        with _cache_lock:
            _live_units_cache[p_key] = {"units": dict(live_lpr_units), "timestamp": time.time()}

    with ThreadPoolExecutor(max_workers=2) as ex:
        f1 = ex.submit(_fetch_last_events)
        f2 = ex.submit(_fetch_latest_plates_snapshot)
        f1.result()
        f2.result()

    DEVICE_STATE_NAMES = {
        1: ("תקין", "green"),
        2: ("שינוי ידני", "blue"),
        3: ("דרושה תחזוקה", "yellow"),
        4: ("אזהרה", "yellow"),
        5: ("תפקוד חלקי", "orange"),
        6: ("מחוץ לשירות", "red"),
        7: ("פריצת מחסום!", "red"),
        8: ("נתק תקשורת", "red")
    }

    enriched = []
    for d in geom_devices:
        u_num = str(d["number"])
        ev_info = events_by_dev.get(u_num, {})
        st_code = ev_info.get("device_state", 1)
        st_label, st_color = DEVICE_STATE_NAMES.get(st_code, ("פעיל", "green"))
        decoded_single = decode_single_state_20bytes(ev_info.get("single_state_hex", ""))

        # High dynamic state bit 16 = Barrier raised, bit 13 = Barrier loop detector taken
        dyn_hex = ev_info.get("high_dyn_hex", "")
        barrier_raised_dyn = False
        loop_taken_dyn = False
        if dyn_hex and len(dyn_hex) >= 4:
            try:
                dyn_int = int(dyn_hex, 16)
                barrier_raised_dyn = bool(dyn_int & 0x0001)
                loop_taken_dyn = bool(dyn_int & 0x0008)
            except Exception:
                pass

        lpr_unit = live_lpr_units.get(u_num) or {}
        raw_plate = str(lpr_unit.get("plate") or "").strip()
        fmt_plate = raw_plate
        if raw_plate.isdigit():
            if len(raw_plate) == 7:
                fmt_plate = f"{raw_plate[:2]}-{raw_plate[2:5]}-{raw_plate[5:]}"
            elif len(raw_plate) == 8:
                fmt_plate = f"{raw_plate[:3]}-{raw_plate[3:5]}-{raw_plate[5:]}"
        src_file = str(lpr_unit.get("source_file") or "").strip()

        cat_upper = str(d.get("direction") or "entry").upper()
        cat_he_map = {"ENTRY": "כניסה", "EXIT": "יציאה", "PASSAGE": "מעבר"}
        item = dict(d)
        item.update({
            "unit": u_num,
            "category": cat_upper,
            "category_he": cat_he_map.get(cat_upper, d.get("type_label_he", "נתיב")),
            "status_summary_he": "נעול / חסום" if decoded_single["is_locked"] else ("פתוח" if (decoded_single["is_barrier_open"] or barrier_raised_dyn) else st_label),
            "barrier_locked": decoded_single["is_locked"],
            "device_blocked": decoded_single["is_out_of_order"] or (st_code in (6, 8)),
            "always_open": decoded_single["is_barrier_open"],
            "device_state_code": st_code,
            "device_state_label": "נעול / חסום" if decoded_single["is_locked"] else st_label,
            "device_state_color": "orange" if decoded_single["is_locked"] else st_color,
            "is_locked": decoded_single["is_locked"],
            "is_barrier_open": decoded_single["is_barrier_open"] or barrier_raised_dyn,
            "is_loop_occupied": loop_taken_dyn,
            "is_out_of_order": decoded_single["is_out_of_order"] or (st_code in (6, 8)),
            "warnings": decoded_single["warnings"],
            "recent_events": ev_info.get("recent_events", []),
            "last_plate": raw_plate,
            "formatted_plate": fmt_plate,
            "source_file": src_file,
            "has_camera_data": bool(raw_plate or src_file)
        })
        enriched.append(item)

    return enriched

def send_command_and_log_audit(project_number, parking_name, ip, port, user_obj, cell, unit, unit_name, action_key, reason, plate=""):
    """
    שולח פקודת שליטה לנתיב ב-DeviceControlWebService/command/{cell}/{unit}/{cmd}
    ושולח רישום לאירועים (DB.USER_AUDIT דרך /vehicle-api/api/log-audit + SQLite מקומי).
    """
    cmd_tuple = COMMANDS_MAP.get(action_key.upper())
    if not cmd_tuple:
        return {"success": False, "message": f"פקודה לא מוכרת: {action_key}"}

    command_code, action_desc = cmd_tuple
    target_device = str(unit).split(",")[-1].strip()
    cell_id = str(cell or "1").strip() or "1"

    endpoint = f"/DeviceControlWebService/command/{cell_id}/{target_device}/{command_code}"
    cmd_res = make_sb_request(
        "PUT",
        ip,
        port,
        endpoint,
        headers={"Accept": "application/json, application/xml", "Content-Type": "application/json"},
        timeout=5
    )

    cmd_ok = cmd_res.get("status") in (200, 201, 202, 204)
    # Check if XML response had <status>0</status>
    if cmd_ok and cmd_res.get("text"):
        m_st = re.search(r"<status>(\d+)</status>", cmd_res["text"])
        if m_st and m_st.group(1) != "0":
            cmd_ok = False

    u_name = (user_obj.get('username') or user_obj.get('email') or 'מנהל חניון') if isinstance(user_obj, dict) else 'מנהל חניון'
    full_reason_parts = [f"אפליקציית מנהל ({u_name})", action_desc]
    if plate:
        full_reason_parts.append(f"רכב: {plate}")
    if reason:
        full_reason_parts.append(f"הערה: {reason}")
    full_reason = " | ".join(full_reason_parts)[:200]

    # Log to S&B DB.USER_AUDIT via /vehicle-api/api/log-audit
    audit_ok = False
    try:
        audit_payload = {
            "cell": cell_id,
            "device": target_device,
            "reason": full_reason,
            "ip": request.remote_addr or "127.0.0.1",
            "ptcptId": "7",
            "commandCode": str(command_code)
        }
        audit_res = make_sb_request(
            "POST",
            ip,
            port,
            "/vehicle-api/api/log-audit",
            data=audit_payload,
            headers={"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"},
            timeout=3
        )
        if audit_res.get("status") == 200 and '"success"' in (audit_res.get("text") or ""):
            audit_ok = True
    except Exception:
        pass

    record_local_audit_event(
        project_number=project_number,
        parking_name=parking_name,
        user_obj=user_obj,
        action_type=action_key.upper(),
        cell=cell_id,
        unit=target_device,
        unit_name=unit_name,
        command_code=command_code,
        plate=plate,
        reason=full_reason,
        sb_cmd_ok=cmd_ok,
        sb_audit_ok=audit_ok
    )

    if cmd_ok:
        return {
            "success": True,
            "command_code": command_code,
            "action_desc": action_desc,
            "audit_logged": True,
            "sb_audit_ok": audit_ok,
            "message": f"✅ בוצע בהצלחה בנתיב {target_device}: {action_desc} (נרשם ביומן האירועים)"
        }
    return {
        "success": False,
        "command_code": command_code,
        "message": f"⚠️ שליחת הפקודה לנתיב {target_device} נכשלה (HTTP {cmd_res.get('status')})"
    }

# ============================================================================
# 4. LPR SINGLE LANE INSPECTION, SUBSCRIBER / TRANSIENT CHECK & PLATE CORRECTION
# ============================================================================
def _clean_sb_val(val):
    if not val:
        return ""
    v = str(val).strip()
    if v.lower() in ("[not supported]", "null", "none", "-1"):
        return ""
    return v

def _format_sb_entry_time(raw_time):
    if not raw_time:
        return ""
    s = str(raw_time).strip()
    if s == "19770101000000":
        return ""
    digits = re.sub(r"\D", "", s)
    if len(digits) >= 12:
        return f"{digits[8:10]}:{digits[10:12]} ({digits[6:8]}/{digits[4:6]}/{digits[0:4]})"
    return s

def get_transient_ticket_info(ip, port, clean_plate, allow_fuzzy=True):
    """
    בודק כרטיס רכב מזדמן ב-TicketClassificationWebService ומחשב כמה עליו לשלם כעת!
    תומך גם בחיפוש מקורב (license-plate-qflist) במידה והמספר נקרא בשינוי קל במצלמת הכניסה.
    """
    if not clean_plate:
        return {"found": False, "price_display": "לא הוזן מספר"}

    def _query_classification(lpn_to_query):
        res = make_sb_request(
            "GET",
            ip,
            port,
            "/TicketClassificationWebService/ext-medium-ticket-classification",
            params={"licenseplate": lpn_to_query, "requestid": "1000"},
            headers={"Accept": "application/xml"},
            timeout=3.5
        )
        if res["status"] != 200 or not res["text"]:
            return None
        xml_s = res["text"]
        t_match = re.search(r"<ticketdataextmedium>([\s\S]*?)</ticketdataextmedium>", xml_s, re.IGNORECASE)
        e_match = re.search(r"<entrytime>([^<]+)</entrytime>", xml_s, re.IGNORECASE)
        rc_match = re.search(r"<responsecode>([^<]+)</responsecode>", xml_s, re.IGNORECASE)
        raw_entry = e_match.group(1).strip() if e_match else ""
        rc = rc_match.group(1).strip() if rc_match else ""
        if raw_entry == "19770101000000" or rc == "4" or not t_match or not t_match.group(1).strip():
            return None
        return {
            "inner_xml": t_match.group(1),
            "raw_entry": raw_entry,
            "matched_plate": lpn_to_query,
            "full_xml": xml_s
        }

    hit = _query_classification(clean_plate)
    fuzzy_candidates = []

    if not hit and allow_fuzzy:
        qf_res = make_sb_request(
            "GET",
            ip,
            port,
            "/TicketClassificationWebService/license-plate-qflist",
            params={
                "requestid": "1001",
                "licenseplate": clean_plate,
                "maxcountofreturnvalues": "5",
                "maxdistance": "20"
            },
            headers={"Accept": "application/xml"},
            timeout=3
        )
        if qf_res["status"] == 200 and qf_res["text"]:
            entries = re.findall(r"<licenseplateqfentry>([\s\S]*?)</licenseplateqfentry>", qf_res["text"], re.IGNORECASE)
            for ent in entries:
                lp_m = re.search(r"<licenseplate>([^<]+)</licenseplate>", ent, re.IGNORECASE)
                dist_m = re.search(r"<distance>([^<]+)</distance>", ent, re.IGNORECASE)
                if lp_m:
                    cand_lp = lp_m.group(1).strip()
                    cand_dist = float(dist_m.group(1)) if (dist_m and dist_m.group(1).replace('.', '', 1).isdigit()) else 99.0
                    fuzzy_candidates.append({"plate": cand_lp, "distance": cand_dist})
            fuzzy_candidates.sort(key=lambda x: x["distance"])
            if fuzzy_candidates and fuzzy_candidates[0]["distance"] <= 2.5:
                hit = _query_classification(fuzzy_candidates[0]["plate"])

    if not hit:
        return {
            "found": False,
            "amount_nis": None,
            "price_display": "לא נמצא כרטיס חניה פעיל",
            "entry_time": "",
            "duration": "",
            "paid": False,
            "similar_plates": [c["plate"] for c in fuzzy_candidates[:5]]
        }

    inner_xml = hit["inner_xml"]
    entry_formatted = _format_sb_entry_time(hit["raw_entry"])
    dev_m = re.search(r"<device>([^<]+)</device>", inner_xml, re.IGNORECASE)
    fac_m = re.search(r"<entryfacility>([^<]+)</entryfacility>", inner_xml, re.IGNORECASE)
    epan_m = re.search(r"<epan>([^<]+)</epan>", inner_xml, re.IGNORECASE)
    pay_cnt_m = re.search(r"<countofpayments>([^<]+)</countofpayments>", inner_xml, re.IGNORECASE)

    payload = f"<ticketdata>{inner_xml}</ticketdata>"
    price_res = make_sb_request(
        "POST",
        ip,
        port,
        "/TicketClassificationWebService/ext-ticket-calculation?requestid=1001&cashierdevice=750",
        data=payload.encode("utf-8"),
        headers={"Accept": "application/xml", "Content-Type": "application/xml; charset=utf-8"},
        timeout=3.5
    )

    amount_nis = 0.0
    price_str = "₪0"
    duration_str = ""
    if price_res["status"] == 200 and price_res["text"]:
        amt_m = re.search(r"<amount>(-?\d+)</amount>", price_res["text"], re.IGNORECASE)
        dur_m = re.search(r"<duration>([^<]+)</duration>", price_res["text"], re.IGNORECASE)
        if amt_m:
            amount_agorot = int(amt_m.group(1))
            amount_nis = max(0.0, amount_agorot / 100.0)
            price_str = f"₪{int(amount_nis)}" if amount_nis == int(amount_nis) else f"₪{amount_nis:.2f}"
        if dur_m:
            # DD-HH-MM
            raw_dur = dur_m.group(1).strip()
            d_parts = raw_dur.split("-")
            if len(d_parts) == 3:
                days_i = int(d_parts[0]) if d_parts[0].isdigit() else 0
                hrs_i = int(d_parts[1]) if d_parts[1].isdigit() else 0
                mins_i = int(d_parts[2]) if d_parts[2].isdigit() else 0
                if days_i > 0:
                    duration_str = f"{days_i} ימים, {hrs_i} שעות ו-{mins_i} דק׳"
                elif hrs_i > 0:
                    duration_str = f"{hrs_i} שעות ו-{mins_i} דק׳"
                else:
                    duration_str = f"{mins_i} דקות"
            else:
                duration_str = raw_dur

    epan_val = epan_m.group(1).strip() if epan_m else ""
    return {
        "found": True,
        "matched_plate": hit["matched_plate"],
        "is_exact_match": (hit["matched_plate"] == clean_plate),
        "amount_nis": amount_nis,
        "amount_ils": amount_nis,
        "price_display": price_str,
        "entry_time": entry_formatted,
        "duration": duration_str,
        "stay_duration": duration_str,
        "entry_device": dev_m.group(1).strip() if dev_m else "",
        "entry_facility": fac_m.group(1).strip() if fac_m else "",
        "epan": epan_val,
        "ticket_id": epan_val,
        "count_of_payments": int(pay_cnt_m.group(1)) if (pay_cnt_m and pay_cnt_m.group(1).isdigit()) else 0,
        "paid": (amount_nis <= 0),
        "payment_required": (amount_nis > 0),
        "status_he": f"💳 סכום לתשלום: {price_str}" if amount_nis > 0 else "✅ ללא חיוב לתשלום (₪0)",
        "similar_plates": [c["plate"] for c in fuzzy_candidates[:5]]
    }

def inspect_vehicle_by_plate(ip, port, plate, lane_direction="entry", calc_transient_price=True):
    """
    בודק מספר רכב בשרת החניון:
    1. האם הוא מנוי ב-CustomerMediaWebService (כולל שם, חברה, תוקף, נוכחות, מכסת חברה ותנועה אחרונה).
    2. אם אינו מנוי (או בנוסף) -> בודק אם הוא רכב מזדמן שנמצא כעת בחניון וכמה עליו לשלם!
    """
    clean_plate = re.sub(r'[^0-9A-Za-zמ]', '', str(plate or '')).upper()
    if not clean_plate:
        return {
            "is_subscriber": False,
            "status": "empty",
            "status_color": "gray",
            "status_title": "אין רכב בנתיב",
            "plate": "",
            "company": "-",
            "subscriber_name": "-",
            "issues": [],
            "price_info": None
        }

    res = make_sb_request("GET", ip, port, "/CustomerMediaWebService/consumers", params={"lpn": clean_plate}, timeout=3.5)
    consumer_href = None
    if res["status"] == 200 and res["data"]:
        try:
            xml_text = re.sub(r'\sxmlns="[^"]+"', '', res["data"].decode("utf-8", errors="replace"))
            root = ET.fromstring(xml_text)
            c_el = root.find(".//consumer")
            if c_el is not None and c_el.get("href"):
                consumer_href = c_el.get("href")
        except Exception:
            pass

    if not consumer_href:
        p_info = get_transient_ticket_info(ip, port, clean_plate) if calc_transient_price else None
        status_title = "רכב מזדמן בחניון" if (p_info and p_info.get("found")) else "רכב מזדמן (ללא כרטיס פעיל)"
        return {
            "is_subscriber": False,
            "status": "transient",
            "status_color": "red",
            "status_title": status_title,
            "company": "רכב מזדמן / פרטי",
            "subscriber_name": "מזדמן",
            "plate": clean_plate,
            "present": bool(p_info and p_info.get("found")),
            "capacity": None,
            "issues": [],
            "valid_from": "",
            "valid_until": "",
            "last_tx": p_info.get("entry_time", "") if p_info else "",
            "price_info": p_info
        }

    ids = consumer_href.replace("/consumers/", "").strip()
    contract_id = ids.split(",")[0].strip()
    consumer_id = ids.split(",")[1].strip() if "," in ids else ""
    try:
        contract_id_int = int(contract_id)
    except ValueError:
        contract_id_int = 1

    with ThreadPoolExecutor(max_workers=3) as ex:
        f_det = ex.submit(make_sb_request, "GET", ip, port, f"/CustomerMediaWebService/consumers/{ids}/detail", "2022", "2022", None, None, None, 3.0)
        f_con = ex.submit(make_sb_request, "GET", ip, port, f"/CustomerMediaWebService/contracts/{contract_id}/detail", "2022", "2022", None, None, None, 3.0)
        f_tx = ex.submit(make_sb_request, "GET", ip, port, f"/CustomerMediaWebService/consumers/{ids}/parktrans", "2022", "2022", None, None, None, 3.0)
        detail_res = f_det.result()
        contract_res = f_con.result()
        tx_res = f_tx.result()

    subscriber_name = ""
    first_name = ""
    last_name = ""
    valid_from = ""
    valid_until = ""
    present = None
    match_code = ""
    memo = ""
    is_blocked = False
    lpn1, lpn2, lpn3 = clean_plate, "", ""

    if detail_res["status"] == 200 and detail_res["data"]:
        try:
            c_xml = re.sub(r'\sxmlns="[^"]+"', '', detail_res["data"].decode("utf-8", errors="replace"))
            c_root = ET.fromstring(c_xml)
            first_name = _clean_sb_val(c_root.findtext(".//person/firstName", "") or c_root.findtext(".//firstName", ""))
            surnames = [_clean_sb_val(s.text) for s in c_root.findall(".//surname") if _clean_sb_val(s.text)]
            last_name = surnames[0] if surnames else _clean_sb_val(c_root.findtext(".//consumer/name", ""))
            subscriber_name = f"{first_name} {last_name}".strip() or "מנוי רשום"

            valid_from = _clean_sb_val(c_root.findtext(".//identification/validFrom", "") or c_root.findtext(".//validFrom", ""))
            valid_until = _clean_sb_val(c_root.findtext(".//identification/validUntil", "") or c_root.findtext(".//validUntil", ""))
            pres_val = _clean_sb_val(c_root.findtext(".//identification/present", "") or c_root.findtext(".//present", ""))
            if pres_val:
                present = (pres_val.lower() == "true")

            ident_status = _clean_sb_val(c_root.findtext(".//identification/status", ""))
            cons_status = _clean_sb_val(c_root.findtext("./status", ""))
            if ident_status == "2" or cons_status == "2":
                is_blocked = True

            match_code = _clean_sb_val(c_root.findtext(".//matchCode", ""))
            memo = _clean_sb_val(c_root.findtext(".//memo", "") or c_root.findtext(".//displayText", ""))
            lpn1 = _clean_sb_val(c_root.findtext(".//lpn1", "")) or clean_plate
            lpn2 = _clean_sb_val(c_root.findtext(".//lpn2", ""))
            lpn3 = _clean_sb_val(c_root.findtext(".//lpn3", ""))
        except Exception:
            pass

    company_name = f"חברה {contract_id}"
    capacity = None
    if contract_res["status"] == 200 and contract_res["data"]:
        try:
            ct_xml = re.sub(r'\sxmlns="[^"]+"', '', contract_res["data"].decode("utf-8", errors="replace"))
            ct_root = ET.fromstring(ct_xml)
            cname = ct_root.findtext(".//contract/name", "")
            if cname:
                company_name = cname.strip()
            if not valid_from:
                valid_from = ct_root.findtext(".//xValidFrom", "") or ""
            if not valid_until:
                valid_until = ct_root.findtext(".//xValidUntil", "") or ""
            for p in ct_root.findall(".//poolingDetail"):
                mc_s = p.findtext("maxCounter", "")
                pc_s = p.findtext("presentCounter", "")
                if mc_s and pc_s:
                    try:
                        mc, pc = int(mc_s), int(pc_s)
                        if mc > 0 and mc != 9999:
                            capacity = {"max": mc, "present": pc}
                            break
                    except ValueError:
                        pass
        except Exception:
            pass

    last_tx_time = ""
    last_tx_device = ""
    if tx_res["status"] == 200 and tx_res["data"]:
        try:
            tx_xml = re.sub(r'\sxmlns="[^"]+"', '', tx_res["data"].decode("utf-8", errors="replace"))
            tx_blocks = re.findall(r"<parkTransaction>([\s\S]*?)</parkTransaction>", tx_xml, re.IGNORECASE)
            valid_tx = []
            for blk in tx_blocks:
                t_m = re.search(r"<transactionTime>([^<]+)</transactionTime>", blk, re.IGNORECASE)
                ty_m = re.search(r"<transactionType>([^<]+)</transactionType>", blk, re.IGNORECASE)
                dv_m = re.search(r"<device>([^<]+)</device>", blk, re.IGNORECASE)
                if t_m and ty_m:
                    valid_tx.append({
                        "time": t_m.group(1).strip(),
                        "type": ty_m.group(1).strip(),
                        "device": dv_m.group(1).strip() if dv_m else ""
                    })
            if valid_tx:
                valid_tx.sort(key=lambda x: x["time"], reverse=True)
                last_tx_time = valid_tx[0]["time"][:19].replace("T", " ")
                last_tx_device = valid_tx[0]["device"]
        except Exception:
            pass

    is_blocked_company = (10000 <= contract_id_int <= 10010)
    issues = []
    now = datetime.datetime.now()

    if is_blocked_company:
        issues.append("🚨 מנוי בחברת רכבים חסומים (10000–10010)")
    if is_blocked:
        issues.append("מנוי חסום במערכת")
    if valid_until:
        try:
            vu_date = datetime.datetime.fromisoformat(valid_until[:10])
            if now.date() > vu_date.date():
                issues.append(f"פג תוקף ({valid_until[:10]})")
        except Exception:
            pass
    if valid_from:
        try:
            vf_date = datetime.datetime.fromisoformat(valid_from[:10])
            if now.date() < vf_date.date():
                issues.append(f"טרם נכנס לתוקף (מ-{valid_from[:10]})")
        except Exception:
            pass
    if capacity and capacity["max"] > 0 and capacity["present"] >= capacity["max"]:
        if lane_direction == "entry":
            issues.append(f"אין מקום לחברה ({capacity['present']}/{capacity['max']} חונים)")

    if lane_direction == "entry" and present is True:
        issues.append("כניסה כפולה / הרכב כבר רשום כנוכח בחניון")
    elif lane_direction == "exit" and present is False:
        issues.append("יציאה כפולה / הרכב לא רשום כנוכח בחניון")

    if is_blocked_company:
        status, status_color, status_title = "blocked-blink", "red-blink", "🚨 רכב חסום"
    elif issues:
        status, status_color, status_title = "issue", "yellow", "מנוי עם בעיה"
    else:
        status, status_color, status_title = "ok", "green", "מנוי תקין"

    return {
        "is_subscriber": True,
        "subscriber_id": ids,
        "contract_id": contract_id,
        "consumer_id": consumer_id,
        "status": status,
        "status_color": status_color,
        "status_title": status_title,
        "company": company_name,
        "subscriber_name": subscriber_name,
        "first_name": first_name,
        "last_name": last_name,
        "lpn1": lpn1,
        "lpn2": lpn2,
        "lpn3": lpn3,
        "memo": memo,
        "match_code": match_code,
        "present": present,
        "capacity": capacity,
        "issues": issues,
        "plate": clean_plate,
        "valid_from": valid_from[:10] if valid_from else "",
        "valid_until": valid_until[:10] if valid_until else "",
        "last_tx": last_tx_time,
        "last_tx_device": last_tx_device,
        "price_info": None
    }

def _levenshtein_distance(s1, s2):
    if len(s1) < len(s2):
        return _levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    prev = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr = [i + 1]
        for j, c2 in enumerate(s2):
            curr.append(min(prev[j + 1] + 1, curr[j] + 1, prev[j] + (c1 != c2)))
        prev = curr
    return prev[-1]

def validate_plate_similarity(camera_plate, entered_plate, manager_override=False):
    ent = re.sub(r"\D", "", str(entered_plate or ""))
    cam = re.sub(r"\D", "", str(camera_plate or ""))
    if not re.match(r"^\d{7,8}$", ent):
        return False, "מספר רישוי חייב להכיל 7 או 8 ספרות"
    if manager_override or len(cam) < 4:
        return True, ""
    if _levenshtein_distance(cam, ent) <= 2:
        return True, ""
    if len(cam) < len(ent):
        for start in range(len(ent) - len(cam) + 1):
            if _levenshtein_distance(cam, ent[start:start + len(cam)]) <= 1:
                return True, ""
    return False, f"המספר שהוקלד ({ent}) שונה ביותר מ-2 ספרות מזיהוי המצלמה ({cam}). לאישור חריג סמן 'עקיפת מנהל'."

def add_park_transaction(ip, port, subscriber_id, direction, unit, cell="1", facility_id="1", facility_out="0"):
    """
    רושם תנועת כניסה/יציאה/מעבר למנוי ב-CustomerMediaWebService/consumers/{id}/parktrans
    כמו במסך תמונות LPR ושרת האינטרקום.
    """
    try:
        target_device = str(unit).split(",")[-1].strip()
        cell_id = str(cell or "1").strip() or "1"
        parts = str(subscriber_id).split(",")
        contract_id = parts[0].strip()
        consumer_id = parts[1].strip() if len(parts) > 1 else contract_id
        endpoint = f"/CustomerMediaWebService/consumers/{subscriber_id}/parktrans"
        now_str = datetime.datetime.now().astimezone().isoformat(timespec="milliseconds")
        headers = {"Accept": "application/xml", "Content-Type": "application/xml; charset=utf-8"}

        if direction == "entry":
            xml_body = f"""<?xml version="1.0" encoding="UTF-8"?>
<bookParkTransaction xmlns="http://gsph.sub.com/cust/types">
    <entryParkTransaction>
         <transactionTime>{now_str}</transactionTime>
         <transactionType>2</transactionType>
         <facilityin>{facility_id}</facilityin>
         <facilityout>0</facilityout>
         <computer>{cell_id}</computer>
         <device>{target_device}</device>
         <amount>0.0</amount>
         <contractid>{contract_id}</contractid>
         <consumerid>{consumer_id}</consumerid>
    </entryParkTransaction>
</bookParkTransaction>"""
            res = make_sb_request("POST", ip, port, endpoint, data=xml_body.encode("utf-8"), headers=headers, timeout=3.5)
            return res.get("status") in (200, 201, 202, 204)

        elif direction == "exit":
            xml_body = f"""<?xml version="1.0" encoding="UTF-8"?>
<bookParkTransaction xmlns="http://gsph.sub.com/cust/types">
    <exitParkTransaction>
         <transactionTime>{now_str}</transactionTime>
         <transactionType>12</transactionType>
         <facilityin>0</facilityin>
         <facilityout>{facility_id}</facilityout>
         <computer>{cell_id}</computer>
         <device>{target_device}</device>
         <amount>0.0</amount>
         <contractid>{contract_id}</contractid>
         <consumerid>{consumer_id}</consumerid>
    </exitParkTransaction>
</bookParkTransaction>"""
            res = make_sb_request("POST", ip, port, endpoint, data=xml_body.encode("utf-8"), headers=headers, timeout=3.5)
            return res.get("status") in (200, 201, 202, 204)

        else:
            dev_num = int(target_device) if target_device.isdigit() else 301
            is_pass_entry = (direction == "passage_entry") or (dev_num % 2 != 0)
            fac_in = facility_id if is_pass_entry else (facility_out if facility_out != "0" else "1")
            fac_out_val = (facility_out if facility_out != "0" else "1") if is_pass_entry else facility_id
            now_plus_1 = (datetime.datetime.now().astimezone() + timedelta(seconds=1)).isoformat(timespec="milliseconds")

            exit_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<bookParkTransaction xmlns="http://gsph.sub.com/cust/types">
    <exitParkTransaction>
         <transactionTime>{now_str}</transactionTime>
         <transactionType>12</transactionType>
         <facilityin>0</facilityin>
         <facilityout>{fac_out_val}</facilityout>
         <computer>{cell_id}</computer>
         <device>{target_device}</device>
         <amount>0.0</amount>
         <contractid>{contract_id}</contractid>
         <consumerid>{consumer_id}</consumerid>
    </exitParkTransaction>
</bookParkTransaction>"""
            entry_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<bookParkTransaction xmlns="http://gsph.sub.com/cust/types">
    <entryParkTransaction>
         <transactionTime>{now_plus_1}</transactionTime>
         <transactionType>2</transactionType>
         <facilityin>{fac_in}</facilityin>
         <facilityout>0</facilityout>
         <computer>{cell_id}</computer>
         <device>{target_device}</device>
         <amount>0.0</amount>
         <contractid>{contract_id}</contractid>
         <consumerid>{consumer_id}</consumerid>
    </entryParkTransaction>
</bookParkTransaction>"""
            make_sb_request("POST", ip, port, endpoint, data=exit_xml.encode("utf-8"), headers=headers, timeout=3)
            res = make_sb_request("POST", ip, port, endpoint, data=entry_xml.encode("utf-8"), headers=headers, timeout=3)
            return res.get("status") in (200, 201, 202, 204)
    except Exception as e:
        print(f"add_park_transaction error: {e}")
        return False

def force_price_on_exit_column(project_number, parking_name, ip, port, user_obj, cell, unit, price_agorot, reason="שליחת מחיר לעמדת יציאה"):
    """
    שולח פקודת אובדן כרטיס (44080) להערת עמדת היציאה (2XX) ומעדכן את המחיר המדויק דרך disputedfee.
    """
    target_device = str(unit).split(",")[-1].strip()
    physical_cell = str(cell or "1").strip() or "1"
    dev_num = int(target_device) if target_device.isdigit() else 201
    cmd_code = 44080 if (200 <= dev_num < 300) else 44067

    make_sb_request("PUT", ip, port, f"/DeviceControlWebService/command/{physical_cell}/{target_device}/{cmd_code}", timeout=4)
    time.sleep(1.4)

    price_endpoint = f"/DeviceControlWebService/disputedfee-fielddevice-price?cellcomputernumber={physical_cell}&fielddevicenumber={target_device}"
    original_price = 0
    for _ in range(5):
        p_res = make_sb_request("GET", ip, port, price_endpoint, headers={"Accept": "application/xml"}, timeout=2.5)
        if p_res.get("status") == 200 and p_res.get("text"):
            st_m = re.search(r"<status[^>]*>(\d+)</status>", p_res["text"], re.IGNORECASE)
            pr_m = re.search(r"<price[^>]*>(\d+)</price>", p_res["text"], re.IGNORECASE)
            st_val = int(st_m.group(1)) if st_m else -1
            pr_val = int(pr_m.group(1)) if pr_m else 0
            if st_val == 0 and pr_val > 0:
                original_price = pr_val
                break
        time.sleep(0.9)

    if original_price > 0 and original_price != price_agorot:
        dispute_endpoint = (
            f"/DeviceControlWebService/disputedfee?cellcomputernumber={physical_cell}"
            f"&fielddevicenumber={target_device}&originalprice={original_price}"
            f"&discountedprice={price_agorot}&discountreason=manager"
        )
        make_sb_request("PUT", ip, port, dispute_endpoint, headers={"Accept": "application/xml"}, timeout=3)

    record_local_audit_event(
        project_number=project_number,
        parking_name=parking_name,
        user_obj=user_obj,
        action_type="FORCE_EXIT_PRICE",
        cell=physical_cell,
        unit=target_device,
        command_code=str(cmd_code),
        reason=reason,
        sb_cmd_ok=(original_price > 0)
    )

# ============================================================================
# 5. TAB 2: DIFFERENCE COUNTING WEB SERVICE (ONLINE COUNTERS & MANIPULATION)
# ============================================================================
def fetch_online_parking_counters(project_number, ip, port):
    """
    מיישם את פרוטוקול DifferenceCountingWebService ב-Online:
    1. שולף את רשימת האזורים (facilities) מ-/DifferenceCountingWebService/facilities או מ-geometry.
    2. לכל אזור שולף את כל המונים מ-/DifferenceCountingWebService/counters?facilityid={fid}:
       - standard-counter (מזדמנים id=1, מנויים id=2, סה"כ id=3)
       - level-counter (מפלסים וקומות id=11..50)
       - sum-counter (מוני תנועות מצטברים)
    """
    facilities = []
    fac_res = make_sb_request("GET", ip, port, "/DifferenceCountingWebService/facilities", headers={"Accept": "application/xml"}, timeout=3.5)
    if fac_res["status"] == 200 and fac_res["data"]:
        try:
            f_xml = re.sub(r'\sxmlns="[^"]+"', '', fac_res["data"].decode("utf-8", errors="replace"))
            f_root = ET.fromstring(f_xml)
            for f_el in f_root.findall(".//facility"):
                f_id = (
                    f_el.findtext("facilityid")
                    or f_el.findtext("id")
                    or f_el.findtext("number")
                    or f_el.findtext("facility-no")
                    or ""
                ).strip()
                f_name = (
                    f_el.findtext("facilityname")
                    or f_el.findtext("name")
                    or f_el.findtext("text")
                    or f"אזור {f_id}"
                ).strip()
                if f_id:
                    facilities.append({"id": f_id, "name": f_name})
            if not facilities:
                for num_el in f_root.findall(".//facility-no"):
                    if num_el.text and num_el.text.strip():
                        facilities.append({"id": num_el.text.strip(), "name": f"אזור {num_el.text.strip()}"})
        except Exception:
            pass

    if not facilities:
        # Fallback: extract facilities from geometry
        geom_res = make_sb_request("GET", ip, port, "/DeviceControlWebService/geometry", timeout=3.5)
        if geom_res["status"] == 200 and geom_res["data"]:
            try:
                g_xml = re.sub(r'\sxmlns="[^"]+"', '', geom_res["data"].decode("utf-8", errors="replace"))
                g_root = ET.fromstring(g_xml)
                seen_f = set()
                for fac in g_root.findall(".//facility"):
                    fid = (fac.findtext("number") or "").strip()
                    fname = (fac.findtext("name") or f"אזור {fid}").strip()
                    if fid and fid not in seen_f:
                        seen_f.add(fid)
                        facilities.append({"id": fid, "name": fname})
            except Exception:
                pass

    if not facilities:
        facilities = [{"id": "1", "name": "חניון ראשי"}]

    STATUS_VAL_LABELS = {
        0: ("פנוי", "green"),
        1: ("מלא (לפי מונים)", "red"),
        2: ("מלא (נעול ידנית)", "orange"),
        3: ("חסום", "red")
    }

    COUNTER_ID_HE = {
        "0": "מוזמנים מראש (Pre-booked)",
        "1": "מזדמנים (לא שמור)",
        "2": "מנויים (שמור)",
        "3": "סה״כ חניון (מנויים + מזדמנים)"
    }

    def _fetch_facility_counters(fac):
        fid = fac["id"]
        # Use /DifferenceCountingWebService/standardcounters first (lightweight & fast ~900 bytes), fallback to /counters
        c_res = make_sb_request(
            "GET",
            ip,
            port,
            "/DifferenceCountingWebService/standardcounters",
            params={"facilityid": fid},
            headers={"Accept": "application/xml"},
            timeout=5.0
        )
        if c_res["status"] != 200 or not c_res["data"]:
            c_res = make_sb_request(
                "GET",
                ip,
                port,
                "/DifferenceCountingWebService/counters",
                params={"facilityid": fid, "locale": "en_GB"},
                headers={"Accept": "application/xml"},
                timeout=5.0
            )

        standard_counters = []
        level_counters = []
        sum_counters = []

        if c_res["status"] == 200 and c_res["data"]:
            try:
                c_xml = re.sub(r'\sxmlns="[^"]+"', '', c_res["data"].decode("utf-8", errors="replace"))
                c_root = ET.fromstring(c_xml)

                for sc in c_root.findall(".//standard-counter"):
                    cid = (sc.findtext("id") or "").strip()
                    if cid == "0":
                        continue  # Skip Pre-booked (#0), show only Reserved (מנויים) and Not reserved (מזדמנים)
                    raw_txt = (sc.findtext("text") or "").strip()
                    free_v = int(sc.findtext("free") or 0)
                    pres_v = int(sc.findtext("present") or 0)
                    max_v = int(sc.findtext("max") or 0)
                    pct_v = int(sc.findtext("percent") or (round((pres_v / max_v) * 100) if max_v > 0 else 0))
                    st_val = int(sc.findtext("status-value") or 0)
                    st_lbl, st_clr = STATUS_VAL_LABELS.get(st_val, ("פנוי", "green"))

                    standard_counters.append({
                        "id": cid,
                        "facility_id": fid,
                        "type": 0,
                        "name": COUNTER_ID_HE.get(cid, raw_txt or f"מונה {cid}"),
                        "display_name_he": COUNTER_ID_HE.get(cid, raw_txt or f"מונה {cid}"),
                        "raw_text": raw_txt,
                        "free": free_v,
                        "present": pres_v,
                        "max": max_v,
                        "percent": pct_v,
                        "status_value": st_val,
                        "status_label": st_lbl,
                        "status_color": st_clr,
                        "occupied": 1 if st_val in (1, 2, 3) else 0,
                        "occupied_he": st_lbl
                    })

                for lc in c_root.findall(".//level-counter"):
                    cid = (lc.findtext("id") or "").strip()
                    raw_txt = (lc.findtext("text") or f"מפלס {cid}").strip()
                    free_v = int(lc.findtext("free") or 0)
                    pres_v = int(lc.findtext("present") or 0)
                    max_v = int(lc.findtext("max") or 0)
                    pct_v = int(lc.findtext("percent") or (round((pres_v / max_v) * 100) if max_v > 0 else 0))
                    st_val = int(lc.findtext("status-value") or 0)
                    st_lbl, st_clr = STATUS_VAL_LABELS.get(st_val, ("פנוי", "green"))

                    level_counters.append({
                        "id": cid,
                        "facility_id": fid,
                        "type": 1,
                        "name": raw_txt,
                        "display_name_he": raw_txt,
                        "free": free_v,
                        "present": pres_v,
                        "max": max_v,
                        "percent": pct_v,
                        "status_value": st_val,
                        "status_label": st_lbl,
                        "status_color": st_clr,
                        "occupied": 1 if st_val in (1, 2, 3) else 0,
                        "occupied_he": st_lbl
                    })

                for sumc in c_root.findall(".//sum-counter"):
                    cid = (sumc.findtext("id") or "").strip()
                    raw_txt = (sumc.findtext("text") or f"סכימה {cid}").strip()
                    reset_v = int(sumc.findtext("resetable") or 0)
                    unreset_v = int(sumc.findtext("unresetable") or 0)
                    sum_counters.append({
                        "id": cid,
                        "facility_id": fid,
                        "type": 2,
                        "name": raw_txt,
                        "resetable": reset_v,
                        "unresetable": unreset_v
                    })
            except Exception as e:
                print(f"Error parsing counters for facility {fid}: {e}")

        return {
            "facility_id": fid,
            "facility_name": fac["name"],
            "counters": standard_counters + level_counters,
            "standard_counters": standard_counters,
            "level_counters": level_counters,
            "sum_counters": sum_counters
        }

    facilities_data = []
    with ThreadPoolExecutor(max_workers=min(2, len(facilities))) as ex:
        futures = [ex.submit(_fetch_facility_counters, f) for f in facilities]
        for fut in futures:
            facilities_data.append(fut.result())

    # Calculate overall summary across facilities
    total_max = 0
    total_present = 0
    total_free = 0
    transient_present = 0
    subscribers_present = 0
    for fd in facilities_data:
        stds = fd["standard_counters"]
        c1 = next((c for c in stds if c["id"] == "1"), None)
        c2 = next((c for c in stds if c["id"] == "2"), None)
        if c1:
            transient_present += max(0, c1["present"])
        if c2:
            subscribers_present += max(0, c2["present"])
        # Prefer counter id=3 (total), otherwise counter id=1 (not reserved) or sum of 1+2
        c3 = next((c for c in stds if c["id"] == "3" and c["max"] > 0), None)
        if c3:
            total_max += c3["max"]
            total_present += c3["present"]
            total_free += max(0, c3["free"])
        else:
            if c1 and c1["max"] > 0:
                total_max += c1["max"]
                total_present += c1["present"]
                total_free += max(0, c1["free"])
            elif c1:
                total_present += c1["present"]
            if c2 and 0 < c2["max"] < 9999:
                total_max += c2["max"]
                total_present += c2["present"]
                total_free += max(0, c2["free"])
            elif c2:
                total_present += c2["present"]

    overall_pct = round((total_present / total_max) * 100) if total_max > 0 else 0
    return {
        "facilities": facilities_data,
        "summary": {
            "total_max": total_max,
            "total_present": total_present,
            "transient_present": transient_present,
            "subscribers_present": subscribers_present,
            "total_free": total_free,
            "overall_percent": overall_pct,
            "occupancy_percent": overall_pct
        }
    }

def update_online_counter(project_number, parking_name, ip, port, user_obj, facility_id, counter_id, operation, value):
    """
    מעדכן מונה ב-DifferenceCountingWebService/counter/{facilityid}/{counterid}:
    operation:
      - 'occupiedstate': 0 (פנוי) או 1 (מלא ידנית)
      - 'maxplaces': מספר מקסימלי חדש
      - 'increasefreeplaces': כמות להוספה למקומות הפנויים
      - 'decreasefreeplaces': כמות להפחתה מהמקומות הפנויים
    """
    allowed_ops = ('occupiedstate', 'maxplaces', 'increasefreeplaces', 'decreasefreeplaces')
    if operation not in allowed_ops:
        return {"success": False, "message": "פעולת מונה לא חוקית"}

    val_int = int(value)
    endpoint = f"/DifferenceCountingWebService/counter/{facility_id}/{counter_id}?{operation}={val_int}"
    res = make_sb_request("PUT", ip, port, endpoint, headers={"Accept": "application/xml, application/json"}, timeout=5)
    ok = res["status"] in (200, 201, 202, 204)
    if ok and res.get("text"):
        m = re.search(r"<status>(\d+)</status>", res["text"])
        if m and m.group(1) != "0":
            ok = False

    op_names_he = {
        'occupiedstate': f"שינוי סטטוס שלט ל-{'מלא (1)' if val_int == 1 else 'פנוי (0)'}",
        'maxplaces': f"עדכון מקסימום מקומות ל-{val_int}",
        'increasefreeplaces': f"הוספת {val_int} מקומות פנויים",
        'decreasefreeplaces': f"הפחתת {val_int} מקומות פנויים"
    }
    reason_str = f"עדכון מונה {counter_id} באזור {facility_id}: {op_names_he.get(operation, operation)}"

    record_local_audit_event(
        project_number=project_number,
        parking_name=parking_name,
        user_obj=user_obj,
        action_type="COUNTER_UPDATE",
        unit=f"Fac:{facility_id}/Cnt:{counter_id}",
        command_code=operation,
        reason=reason_str,
        sb_cmd_ok=ok
    )

    if ok:
        return {"success": True, "message": f"✅ המונה עודכן בהצלחה: {reason_str}"}
    return {"success": False, "message": f"⚠️ עדכון המונה נדחה ע״י בקר החניון (HTTP {res.get('status')})"}

# ============================================================================
# 6. ROUTES: AUTHENTICATION (WHATSAPP OTP & INITIAL CODE)
# ============================================================================
@parking_control_bp.route('/parking-control')
def parking_control_web_app():
    return render_template('parking_control_app.html')

@parking_control_bp.route('/api/parking-control/auth/send-otp', methods=['POST'])
def api_control_send_otp():
    data = request.get_json(silent=True) or {}
    phone_raw = (data.get('phone_number') or data.get('phone') or '').strip()
    initial_code = (data.get('initial_code') or '').strip()
    req_project = str(data.get('project_number') or '').strip()
    req_user_id = data.get('user_id')

    if not phone_raw and not initial_code:
        return jsonify({'success': False, 'message': 'נא להזין מספר טלפון נייד או קוד זיהוי ראשוני', 'error': 'נא להזין מספר טלפון נייד או קוד זיהוי ראשוני'})

    matched_users = _find_control_users_by_phone_or_code(phone_raw=phone_raw, initial_code=initial_code)
    if not matched_users:
        err_msg = 'מספר הטלפון או הקוד אינם מורשים לאפליקציית תפעול ובקרת חניון. ודא שהוגדר קוד מסוג parking_control_manager.'
        return jsonify({
            'success': False,
            'message': err_msg,
            'error': err_msg
        })

    # בדוק כמה חניונים שונים משויכים למספר הטלפון הזה
    available_parkings = _get_available_parkings_for_user(matched_users[0], all_phone_users=matched_users)

    # אם יש יותר מחניון אחד והמשתמש עוד לא בחר חניון בכניסה - החזר לו מסך בחירת חניון!
    if len(available_parkings) > 1 and not req_project and not req_user_id:
        return jsonify({
            'success': True,
            'choose_parking': True,
            'parkings': available_parkings,
            'message': f'נמצאו {len(available_parkings)} חניונים המשויכים למספר הטלפון שלך. נא לבחור חניון לכניסה:'
        })

    target_user = matched_users[0]
    if req_user_id:
        target_user = next((u for u in matched_users if str(u.get('user_id')) == str(req_user_id)), target_user)
    elif req_project:
        target_user = next((u for u in matched_users if str(u.get('project_number')) == req_project), target_user)

    chosen_proj = req_project or str(target_user.get('project_number') or '')
    if (not chosen_proj or chosen_proj == '0') and available_parkings:
        chosen_proj = str(available_parkings[0]['project_number'])

    clean_p = clean_il_phone(phone_raw or target_user.get('phone_number') or '')
    if not clean_p:
        return jsonify({'success': False, 'message': 'למשתמש זה לא מוגדר מספר טלפון נייד לשליחת קוד וואטסאפ'})

    otp_code = str(random.randint(100000, 999999))
    expires_iso = (get_il_now() + timedelta(minutes=10)).isoformat()

    # Save OTP in Supabase user_parkings for all records of this phone & local SQLite mirror
    sb = _get_supabase()
    if sb:
        for mu in matched_users:
            if mu.get('user_id'):
                try:
                    sb.table('user_parkings').update({
                        'mobile_otp': otp_code,
                        'otp_expires_at': expires_iso
                    }).eq('user_id', mu['user_id']).execute()
                except Exception:
                    pass

    with _db_lock:
        conn = sqlite3.connect(SQLITE_CONTROL_PATH)
        conn.execute("""
            INSERT INTO control_otp_sessions (phone_number, user_id, project_number, otp_code, otp_expires_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(phone_number) DO UPDATE SET
                user_id=excluded.user_id,
                project_number=excluded.project_number,
                otp_code=excluded.otp_code,
                otp_expires_at=excluded.otp_expires_at,
                updated_at=excluded.updated_at
        """, (clean_p, int(target_user.get('user_id') or 0), chosen_proj, otp_code, expires_iso, get_il_now().isoformat()))
        conn.commit()
        conn.close()

    p_name = target_user.get('parking_name') or f"חניון {chosen_proj}"
    for po in available_parkings:
        if str(po['project_number']) == chosen_proj:
            p_name = po['parking_name']
            break

    wa_msg = (
        f"שלום {target_user.get('username') or 'מנהל חניון'}! 🛡️🅿️\n"
        f"קוד הכניסה המאובטח שלך לאפליקציית תפעול ובקרת חניון (*{p_name}*) הוא:\n"
        f"*{otp_code}*\n\n"
        f"(הקוד תקף ל-10 דקות)"
    )
    threading.Thread(target=send_whatsapp_message, args=(clean_p, wa_msg), daemon=True).start()

    return jsonify({
        'success': True,
        'phone_number': display_il_phone(clean_p),
        'otp_code': otp_code,  # מוחזר לתמיכה בכפתור כניסה מהירה ישירה מהודעת הוואטסאפ כמו באפליקציית הדיירים
        'selected_project': chosen_proj,
        'selected_parking': {'project_number': chosen_proj, 'parking_name': p_name, 'project_name': p_name},
        'selected_user_id': target_user.get('user_id'),
        'parking_name': p_name,
        'parkings': available_parkings,
        'parkings_options': available_parkings,
        'message': f'קוד אימות נשלח לוואטסאפ שלך עבור {p_name}!'
    })

@parking_control_bp.route('/api/parking-control/auth/verify-otp', methods=['POST'])
def api_control_verify_otp():
    data = request.get_json(silent=True) or {}
    phone_raw = (data.get('phone_number') or data.get('phone') or '').strip()
    initial_code = (data.get('initial_code') or '').strip()
    otp_code = re.sub(r'\D', '', str(data.get('otp_code') or data.get('otp') or ''))
    req_project = str(data.get('project_number') or '').strip()
    req_user_id = data.get('user_id')

    if len(otp_code) != 6:
        return jsonify({'success': False, 'message': 'נא להזין קוד אימות בן 6 ספרות', 'error': 'נא להזין קוד אימות בן 6 ספרות'})

    matched_users = _find_control_users_by_phone_or_code(phone_raw=phone_raw, initial_code=initial_code)
    if not matched_users:
        return jsonify({'success': False, 'message': 'משתמש לא נמצא', 'error': 'משתמש לא נמצא'})

    target_user = matched_users[0]
    if req_user_id:
        target_user = next((u for u in matched_users if str(u.get('user_id')) == str(req_user_id)), target_user)
    elif req_project:
        target_user = next((u for u in matched_users if str(u.get('project_number')) == req_project), target_user)

    clean_p = clean_il_phone(phone_raw or target_user.get('phone_number') or '')
    saved_proj_from_otp = ''

    # Check OTP against SQLite session or Supabase user_parkings
    otp_valid = False
    with _db_lock:
        conn = sqlite3.connect(SQLITE_CONTROL_PATH)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM control_otp_sessions WHERE phone_number = ?", (clean_p,)).fetchone()
        conn.close()
        if row and str(row['otp_code']) == otp_code:
            otp_valid = True
            saved_proj_from_otp = str(row['project_number'] or '')

    if not otp_valid:
        for mu in matched_users:
            if str(mu.get('mobile_otp') or '').strip() == otp_code:
                otp_valid = True
                break

    if not otp_valid:
        return jsonify({'success': False, 'message': 'קוד האימות שגוי או שפג תוקפו', 'error': 'קוד האימות שגוי או שפג תוקפו'})

    # Clear used OTP
    with _db_lock:
        conn = sqlite3.connect(SQLITE_CONTROL_PATH)
        conn.execute("DELETE FROM control_otp_sessions WHERE phone_number = ?", (clean_p,))
        conn.commit()
        conn.close()

    parkings_options = _get_available_parkings_for_user(target_user, all_phone_users=matched_users)
    active_proj = req_project or saved_proj_from_otp or str(target_user.get('project_number') or '')
    if (not active_proj or active_proj == '0') and parkings_options:
        active_proj = str(parkings_options[0]['project_number'])

    # Match the specific user record for active_proj if one exists
    specific_user = next((u for u in matched_users if str(u.get('project_number')) == active_proj), target_user)

    active_p_name = specific_user.get('parking_name') or ''
    for po in parkings_options:
        if str(po['project_number']) == active_proj:
            active_p_name = po['parking_name']
            break

    session['control_user_id'] = specific_user.get('user_id')
    session['control_active_project'] = active_proj
    if specific_user.get('email'):
        session['user_email'] = specific_user['email']

    auth_token = _create_control_token(specific_user.get('user_id') or 1, clean_p, active_proj)

    record_local_audit_event(
        project_number=active_proj,
        parking_name=active_p_name,
        user_obj=specific_user,
        action_type="LOGIN_SESSION",
        reason=f"כניסה מאובטחת לאפליקציית תפעול חניון ({active_p_name}) באמצעות קוד וואטסאפ"
    )

    return jsonify({
        'success': True,
        'auth_token': auth_token,
        'token': auth_token,
        'user': {
            'user_id': specific_user.get('user_id'),
            'username': specific_user.get('username'),
            'email': specific_user.get('email'),
            'phone_number': display_il_phone(clean_p),
            'code_type': specific_user.get('code_type'),
            'project_number': active_proj,
            'parking_name': active_p_name,
            'project_name': active_p_name,
            'company_list': specific_user.get('company_list') or 'ALL',
            'permissions': specific_user.get('permissions') or 'B'
        },
        'parkings_options': parkings_options
    })

@parking_control_bp.route('/api/parking-control/switch-parking', methods=['POST'])
def api_control_switch_parking():
    """
    החלפה מהירה בין חניונים כאשר למספר הטלפון של מנהל החניון יש הרשאה ליותר מחניון אחד!
    מעדכן את הטוקן והחניון הפעיל וטוען מיד את הנתיבים והנתונים של החניון שנבחר.
    """
    user = _get_authenticated_control_user()
    if not user:
        return jsonify({'success': False, 'message': 'לא מחובר'}), 401

    data = request.get_json(silent=True) or {}
    target_proj = str(data.get('project_number') or '').strip()
    if not target_proj:
        return jsonify({'success': False, 'message': 'חסר מספר חניון למעבר'}), 400

    clean_p = clean_il_phone(user.get('phone_number') or '')
    matched_users = _find_control_users_by_phone_or_code(phone_raw=clean_p) if clean_p else [user]
    parkings_options = _get_available_parkings_for_user(user, all_phone_users=matched_users)

    chosen_opt = next((p for p in parkings_options if str(p['project_number']) == target_proj), None)
    if not chosen_opt:
        return jsonify({'success': False, 'message': 'אין הרשאה לחניון המבוקש'}), 403

    specific_user = next((u for u in matched_users if str(u.get('project_number')) == target_proj), user)
    uid = chosen_opt.get('user_id') or specific_user.get('user_id') or user.get('user_id') or 1
    p_name = chosen_opt.get('parking_name') or f'חניון {target_proj}'

    session['control_user_id'] = uid
    session['control_active_project'] = target_proj
    new_token = _create_control_token(uid, clean_p, target_proj)

    return jsonify({
        'success': True,
        'auth_token': new_token,
        'project_number': target_proj,
        'parking_name': p_name,
        'user': {
            'user_id': uid,
            'username': specific_user.get('username') or user.get('username'),
            'email': specific_user.get('email') or user.get('email'),
            'phone_number': display_il_phone(clean_p),
            'code_type': specific_user.get('code_type') or user.get('code_type'),
            'project_number': target_proj,
            'parking_name': p_name,
            'company_list': chosen_opt.get('company_list') or specific_user.get('company_list') or 'ALL'
        },
        'parkings_options': parkings_options,
        'message': f'עברת לחניון {p_name}!'
    })

# ============================================================================
# 7. ROUTES: TAB 1 - OPERATIONS, LANES, LPR IMAGE, COMMANDS & PLATE FIX
# ============================================================================
@parking_control_bp.route('/api/parking-control/overview', methods=['GET'])
def api_control_overview():
    """
    מחזיר את כל נתוני התפעול הראשוניים למנהל החניון:
    פרטי החניון, רשימת כל הנתיבים (כניסות, יציאות, מעברים) עם סטטוס חי ולוחית אחרונה, ויומן אירועים אחרונים.
    """
    user = _get_authenticated_control_user()
    hdr_token = request.headers.get('X-Control-Token') or request.args.get('auth_token') or request.args.get('token')
    if not user and not hdr_token:
        return jsonify({'success': False, 'message': 'נדרש אימות קוד מחדש למערכת התפעול'}), 401

    proj = str(
        request.args.get('project_number')
        or request.headers.get('X-Control-Project')
        or (user.get('active_project_number') if user else '')
        or (user.get('project_number') if user else '')
        or '473223100'
    )
    parkings_options = _get_available_parkings_for_user(user) if user else []
    if (not proj or proj == '0') and parkings_options:
        proj = str(parkings_options[0]['project_number'])

    conn = _get_parking_conn(proj) or {'ip_address': '10.35.122.200', 'port': 8443, 'name': 'מבנה תל אביב'}
    if not conn or not conn.get('ip_address'):
        return jsonify({
            'success': False,
            'message': f'לא נמצאו פרטי חיבור (IP/Port) לבקר החניון עבור פרויקט {proj}',
            'user': user,
            'parkings_options': parkings_options
        }), 404

    ip = conn['ip_address']
    port = conn.get('port', 8443)
    p_name = conn.get('name') or conn.get('description') or (user.get('parking_name') if user else '') or f'חניון {proj}'
    force = request.args.get('force') == '1'

    lanes = get_parking_geometry_and_states(proj, ip, port, force_refresh=force)
    audit_events = get_recent_local_audit_events(proj, limit=30)

    return jsonify({
        'success': True,
        'project_number': proj,
        'parking_name': p_name,
        'server_connected': len(lanes) > 0,
        'timestamp': get_il_now().strftime('%H:%M:%S'),
        'user': {
            'user_id': user.get('user_id') if user else 0,
            'username': user.get('username') if user else 'DrorControl',
            'phone_number': display_il_phone((user.get('phone_number') if user else '') or ''),
            'code_type': user.get('code_type') if user else 'control_parking',
            'project_number': proj,
            'parking_name': p_name,
            'company_list': (user.get('company_list') if user else 'ALL') or 'ALL'
        },
        'parkings_options': parkings_options,
        'lanes': lanes,
        'audit_events': audit_events
    })

@parking_control_bp.route('/api/parking-control/lane-detail/<unit>', methods=['GET'])
def api_control_lane_detail(unit):
    """
    בבחירה של נתיב בודד:
    מחזיר את המספר האחרון שזוהה בנתיב, פרטי המנוי או חישוב מחיר לרכב מזדמן בנתיב יציאה,
    וסטטוס הנתיב (ללא משיכת תמונות מצלמה).
    """
    user = _get_authenticated_control_user()
    hdr_token = request.headers.get('X-Control-Token') or request.args.get('auth_token') or request.args.get('token')
    if not user and not hdr_token:
        return jsonify({'success': False, 'message': 'לא מחובר'}), 401

    proj = str(
        request.args.get('project_number')
        or request.headers.get('X-Control-Project')
        or (user.get('active_project_number') if user else '')
        or (user.get('project_number') if user else '')
        or '473223100'
    )
    conn = _get_parking_conn(proj) or {'ip_address': '10.35.122.200', 'port': 8443}
    if not conn or not conn.get('ip_address'):
        return jsonify({'success': False, 'message': 'אין חיבור לחניון'}), 404

    ip = conn['ip_address']
    port = conn.get('port', 8443)
    u_str = str(unit).strip()

    # 1. Query /vehicle-api/last-plate.jsp?unit={unit} on demand for this single lane
    plate_data = {}
    lp_res = make_sb_request("GET", ip, port, "/vehicle-api/last-plate.jsp", params={"unit": u_str}, timeout=3.5)
    if lp_res["status"] == 200 and lp_res["data"]:
        try:
            parsed_lp = json.loads(lp_res["data"].decode("utf-8", errors="replace"))
            if parsed_lp.get("plate"):
                plate_data = parsed_lp
        except Exception:
            pass

    # 2. If last-plate.jsp returned no_vehicle (because loop 15 is not currently occupied), fetch the last vehicle on this lane from UDBIDENTDATA
    if (not plate_data or not plate_data.get("plate")) and u_str.isdigit():
        import subprocess
        helper_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sb_oracle_helper")
        jar_path = os.path.join(helper_dir, "ojdbc6.jar")
        class_file = os.path.join(helper_dir, "SBOracleReportHelper.class")
        oracle_ip = "10.35.122.200" if str(ip) in ("192.117.0.122", "10.35.122.200", "") else str(ip)
        if oracle_ip and os.path.exists(jar_path) and os.path.exists(class_file):
            try:
                cp_sep = ";" if os.name == "nt" else ":"
                cp_arg = f"{helper_dir}{cp_sep}{jar_path}"
                proc = subprocess.run(
                    ["java", "-cp", cp_arg, "SBOracleReportHelper", oracle_ip, f"LANE_PLATE:{u_str}"],
                    capture_output=True,
                    timeout=4
                )
                if proc.returncode == 0 and proc.stdout:
                    for r_line in proc.stdout.decode("utf-8", errors="replace").splitlines():
                        ln = r_line.strip()
                        if not ln or ln.startswith("[SECTION:"):
                            continue
                        pts = ln.split("\t")
                        if len(pts) >= 2 and pts[1].strip():
                            plate_data = {
                                "unit": u_str,
                                "plate": pts[1].strip(),
                                "raw": pts[1].strip(),
                                "event_time": pts[2].strip() if len(pts) > 2 else ""
                            }
                            break
            except Exception:
                pass

    if plate_data and plate_data.get("plate"):
        with _cache_lock:
            if proj not in _live_units_cache:
                _live_units_cache[proj] = {"units": {}, "timestamp": time.time()}
            _live_units_cache[proj]["units"][u_str] = dict(plate_data)
            _live_units_cache[proj]["timestamp"] = time.time()

    plate = str(plate_data.get("plate") or "").strip()
    raw_plate = str(plate_data.get("raw") or plate).strip()
    source_file = str(plate_data.get("source_file") or "").strip()
    event_time = str(plate_data.get("event_time") or "").strip()

    fmt_plate = raw_plate
    if plate and plate.isdigit():
        if len(plate) == 7:
            fmt_plate = f"{plate[:2]}-{plate[2:5]}-{plate[5:]}"
        elif len(plate) == 8:
            fmt_plate = f"{plate[:3]}-{plate[3:5]}-{plate[5:]}"

    dev_num = int(u_str) if u_str.isdigit() else 101
    if 100 <= dev_num <= 199:
        direction = "entry"
    elif 200 <= dev_num <= 299:
        direction = "exit"
    elif 300 <= dev_num <= 399:
        direction = "passage"
    else:
        direction = "other"

    vehicle_info = inspect_vehicle_by_plate(
        ip,
        port,
        plate,
        lane_direction=("exit" if direction == "exit" else "entry"),
        calc_transient_price=(direction == "exit")
    )

    return jsonify({
        "success": True,
        "unit": u_str,
        "direction": direction,
        "plate": plate,
        "formatted_plate": fmt_plate,
        "event_time": event_time,
        "source_file": source_file,
        "vehicle": vehicle_info,
        "history": []
    })

@parking_control_bp.route('/api/parking-control/lane-image/<unit>', methods=['GET'])
def api_control_lane_image(unit):
    """
    Proxy מאובטח לתמונת המצלמה האחרונה בנתיב (/vehicle-api/image.jsp?unit={unit}&file={source_file}).
    מאפשר הצגת התמונה בנייד מכל רשת סלולרית ללא צורך בחיבור VPN ישיר למצלמה.
    """
    proj = request.args.get('project_number') or ''
    user = _get_authenticated_control_user()
    if user and not proj:
        proj = str(user.get('active_project_number') or user.get('project_number') or '')

    u_str = str(unit).strip()
    source_file = request.args.get('t', '').strip()
    cache_key = f"{proj}_{u_str}_{source_file}"

    if source_file:
        with _cache_lock:
            if cache_key in _image_bytes_cache:
                img_b, c_type = _image_bytes_cache[cache_key]
                resp = Response(img_b, mimetype=c_type)
                resp.headers["Cache-Control"] = "public, max-age=60"
                resp.headers["Access-Control-Allow-Origin"] = "*"
                return resp

    conn = _get_parking_conn(proj)
    if conn and conn.get('ip_address'):
        ip = conn['ip_address']
        port = conn.get('port', 8443)
        img_params = {"unit": u_str}
        if source_file:
            img_params["file"] = source_file
        img_res = make_sb_request("GET", ip, port, "/vehicle-api/image.jsp", params=img_params, timeout=4.5)
        if img_res["status"] == 200 and img_res["data"] and len(img_res["data"]) > 100:
            c_type = (img_res.get("content_type") or "image/jpeg").split(";")[0].strip()
            if source_file:
                with _cache_lock:
                    if len(_image_bytes_cache) > 120:
                        _image_bytes_cache.clear()
                    _image_bytes_cache[cache_key] = (img_res["data"], c_type)
            resp = Response(img_res["data"], mimetype=c_type)
            resp.headers["Cache-Control"] = "no-cache"
            resp.headers["Access-Control-Allow-Origin"] = "*"
            return resp

    # Fallback clean SVG placeholder if camera has no image yet
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 230" width="100%" height="100%">
        <rect width="100%" height="100%" fill="#0f172a"/>
        <rect x="14" y="14" width="372" height="202" rx="10" fill="none" stroke="#334155" stroke-width="2" stroke-dasharray="6,6"/>
        <circle cx="200" cy="92" r="30" fill="#1e293b" stroke="#38bdf8" stroke-width="2.5"/>
        <circle cx="200" cy="92" r="16" fill="#0f172a" stroke="#64748b" stroke-width="1.5"/>
        <text x="200" y="150" fill="#e2e8f0" font-family="sans-serif" font-size="15" font-weight="700" text-anchor="middle">מצלמת נתיב {u_str}</text>
        <text x="200" y="176" fill="#94a3b8" font-family="sans-serif" font-size="12" text-anchor="middle">ממתין לתמונת רכב ממצלמת ה-LPR</text>
    </svg>"""
    resp = Response(svg, mimetype="image/svg+xml")
    resp.headers["Access-Control-Allow-Origin"] = "*"
    return resp

@parking_control_bp.route('/api/parking-control/command', methods=['POST'])
def api_control_execute_command():
    """
    מבצע פעולת שליטה בנתיב:
    OPEN (42250), CLOSE (42251), LOCK_BARRIER (42254), UNLOCK_BARRIER (42255),
    BLOCK_DEVICE (41228), UNBLOCK_DEVICE (41229), OUT_OF_ORDER (44545), IN_ORDER (44546), RETRIGGER_LPR (42469)
    ושולח לאירועים (USER_AUDIT + לוג מערכת).
    """
    user = _get_authenticated_control_user()
    if not user:
        return jsonify({'success': False, 'message': 'פג תוקף החיבור - נא להתחבר מחדש'}), 401

    data = request.get_json(silent=True) or {}
    proj = str(data.get('project_number') or user.get('active_project_number') or user.get('project_number') or '')
    unit = str(data.get('unit') or '').strip()
    cell = str(data.get('cell') or '1').strip() or '1'
    unit_name = str(data.get('unit_name') or f'נתיב {unit}').strip()
    action = str(data.get('action') or 'OPEN').strip().upper()
    reason = str(data.get('reason') or '').strip()
    plate = str(data.get('plate') or '').strip()

    if not unit:
        return jsonify({'success': False, 'message': 'חסר מספר נתיב'}), 400

    conn = _get_parking_conn(proj)
    if not conn or not conn.get('ip_address'):
        return jsonify({'success': False, 'message': 'לא נמצא חיבור לבקר החניון'}), 404

    res = send_command_and_log_audit(
        project_number=proj,
        parking_name=conn.get('name') or user.get('parking_name') or f'חניון {proj}',
        ip=conn['ip_address'],
        port=conn.get('port', 8443),
        user_obj=user,
        cell=cell,
        unit=unit,
        unit_name=unit_name,
        action_key=action,
        reason=reason,
        plate=plate
    )
    return jsonify(res)

@parking_control_bp.route('/api/parking-control/fix-plate', methods=['POST'])
def api_control_fix_plate_in_lane():
    """
    תיקון רכב בנתיב כמו במסך תמונות LPR:
    1. בודק דמיון למספר שנקרא במצלמה (או עקיפת מנהל).
    2. אם הרכב הוא מנוי תקין -> פותח מחסום (42250), רושם תנועת חניון ב-parktrans, ושולח לאירועים!
    3. אם הרכב מנוי עם בעיה -> מציג את הבעיה למנהל (ומאפשר פתיחת מנהל מאולצת אם סומן force_open).
    4. אם הרכב מזדמן בנתיב יציאה (2XX) -> מחשב מחיר כרטיס:
       - אם 0 ש"ח -> פותח מחסום ורושם לאירועים.
       - אם נדרש תשלום -> מקפיץ את המחיר למסך עמדת היציאה (44080 + disputedfee) ורושם לאירועים!
    """
    user = _get_authenticated_control_user()
    if not user:
        return jsonify({'success': False, 'message': 'לא מחובר'}), 401

    data = request.get_json(silent=True) or {}
    proj = str(data.get('project_number') or user.get('active_project_number') or user.get('project_number') or '')
    unit = str(data.get('unit') or '').strip()
    cell = str(data.get('cell') or '1').strip() or '1'
    facility_id = str(data.get('facility_number') or '1').strip() or '1'
    camera_plate = str(data.get('camera_plate') or '').strip()
    entered_plate = str(data.get('entered_plate') or '').strip()
    manager_override = bool(data.get('manager_override', False))
    force_open = bool(data.get('force_open', False))

    if not unit or not entered_plate:
        return jsonify({'success': False, 'message': 'נא להזין מספר רכב לתיקון בנתיב'}), 400

    is_sim_ok, sim_err = validate_plate_similarity(camera_plate, entered_plate, manager_override=manager_override)
    if not is_sim_ok:
        return jsonify({
            'success': False,
            'action': 'similarity_rejected',
            'can_override': True,
            'message': sim_err
        })

    conn = _get_parking_conn(proj)
    if not conn or not conn.get('ip_address'):
        return jsonify({'success': False, 'message': 'אין חיבור לבקר החניון'}), 404

    ip = conn['ip_address']
    port = conn.get('port', 8443)
    p_name = conn.get('name') or user.get('parking_name') or f'חניון {proj}'

    clean_plate = re.sub(r'[^0-9A-Za-zמ]', '', entered_plate).upper()
    dev_num = int(unit) if unit.isdigit() else 101
    if 100 <= dev_num <= 199:
        eff_dir = "entry"
    elif 200 <= dev_num <= 299:
        eff_dir = "exit"
    elif 300 <= dev_num <= 399:
        eff_dir = "passage_entry" if (dev_num % 2 != 0) else "passage_exit"
    else:
        eff_dir = "entry"

    veh = inspect_vehicle_by_plate(
        ip,
        port,
        clean_plate,
        lane_direction=("entry" if "entry" in eff_dir else "exit"),
        calc_transient_price=(eff_dir == "exit")
    )
    cam_note = f" (מצלמה: {camera_plate})" if camera_plate else ""

    # CASE 1: Subscriber
    if veh.get("is_subscriber"):
        sub_id = veh.get("subscriber_id")
        sub_name = veh.get("subscriber_name")
        company = veh.get("company")
        issues = veh.get("issues") or []

        if (issues or veh.get("status") == "blocked-blink") and not force_open:
            err_txt = ", ".join(issues) if issues else "מנוי חסום"
            record_local_audit_event(
                project_number=proj,
                parking_name=p_name,
                user_obj=user,
                action_type="PLATE_FIX_BLOCKED",
                cell=cell,
                unit=unit,
                plate=clean_plate,
                reason=f"תיקון לוחית נחסם: {clean_plate}{cam_note} - {err_txt}",
                sb_cmd_ok=False
            )
            return jsonify({
                'success': False,
                'action': 'subscriber_issue',
                'can_force_open': True,
                'vehicle': veh,
                'message': f"⛔ מנוי נמצא ({sub_name} - {company}) אך קיימת חסימה: {err_txt}. ניתן לאשר 'פתיחת מנהל מאולצת'."
            })

        reason_str = f"תיקון לוחית בנתיב: {clean_plate}{cam_note} | מנוי: {sub_name} | חברה: {company}"
        open_res = send_command_and_log_audit(
            project_number=proj,
            parking_name=p_name,
            ip=ip,
            port=port,
            user_obj=user,
            cell=cell,
            unit=unit,
            unit_name=f"נתיב {unit}",
            action_key="OPEN",
            reason=reason_str,
            plate=clean_plate
        )
        tx_ok = add_park_transaction(ip, port, sub_id, eff_dir, unit, cell=cell, facility_id=facility_id)
        return jsonify({
            'success': True,
            'action': 'open_barrier_subscriber',
            'vehicle': veh,
            'tx_recorded': tx_ok,
            'message': f"✅ מנוי תקין ({sub_name} - {company})! המחסום בנתיב {unit} נפתח, התנועה נרשמה בבקר ונשלחה לאירועים."
        })

    # CASE 2: Transient on Exit lane (2XX)
    if eff_dir == "exit":
        p_info = veh.get("price_info") or get_transient_ticket_info(ip, port, clean_plate)
        veh["price_info"] = p_info
        if p_info and p_info.get("found"):
            amount_nis = float(p_info.get("amount_nis") or 0.0)
            if amount_nis <= 0 or force_open:
                reason_str = f"תיקון לוחית ביציאה (מזדמן משולם/פטור): {clean_plate}{cam_note}"
                send_command_and_log_audit(
                    project_number=proj,
                    parking_name=p_name,
                    ip=ip,
                    port=port,
                    user_obj=user,
                    cell=cell,
                    unit=unit,
                    unit_name=f"יציאה {unit}",
                    action_key="OPEN",
                    reason=reason_str,
                    plate=clean_plate
                )
                return jsonify({
                    'success': True,
                    'action': 'open_barrier_paid_transient',
                    'vehicle': veh,
                    'message': f"✅ רכב מזדמן ({clean_plate}) משולם / בזמן חינם (₪0) – המחסום נפתח ונרשם באירועים!"
                })
            else:
                price_agorot = int(round(amount_nis * 100))
                reason_str = f"תיקון לוחית ביציאה - שליחת מחיר {p_info.get('price_display')} לעמדה {unit}: {clean_plate}{cam_note}"
                threading.Thread(
                    target=force_price_on_exit_column,
                    args=(proj, p_name, ip, port, user, cell, unit, price_agorot, reason_str),
                    daemon=True
                ).start()
                return jsonify({
                    'success': True,
                    'action': 'transient_price_sent',
                    'payment_required': True,
                    'amount_nis': amount_nis,
                    'price_display': p_info.get('price_display'),
                    'vehicle': veh,
                    'message': f"💰 רכב מזדמן ({clean_plate}) – לתשלום {p_info.get('price_display')}. המחיר נשלח למסך עמדת היציאה {unit} ונרשם באירועים!"
                })
        else:
            return jsonify({
                'success': False,
                'action': 'transient_no_ticket',
                'can_force_open': True,
                'vehicle': veh,
                'message': f"⚠️ המספר {clean_plate} אינו מנוי ולא נמצא עבורו כרטיס כניסה פעיל במערכת."
            })

    return jsonify({
        'success': False,
        'action': 'not_subscriber',
        'can_force_open': True,
        'vehicle': veh,
        'message': f"⛔ המספר {clean_plate} אינו מנוי רשום במערכת (נתיב כניסה/מעבר)."
    })

# ============================================================================
# 8. ROUTES: TAB 2 - ONLINE PARKING COUNTERS, FLEXREP & DAILY/HISTORICAL REPORTS
# ============================================================================
FLEXREP_REPORT_NAMES_HE = {
    "$R{1000025_ReportTitle_Stat800}": "דוח תפוסת חניון (Stat800 Occupancy)",
    "$R{1000026_ReportTitle_Stat801}": "דוח משך שהייה (Stat801 Duration)",
    "$R{1000027_ReportTitle_Stat802}": "התפלגות פדיון ותנועות (Stat802 Turnover & Movement)",
    "$R{1000028_ReportTitle_Stat803}": "סיכום פדיון ותנועות (Stat803 Summary Turnover)",
    "$R{1000029_ReportTitle_Stat804}": "דוח סיכום אירועים (Stat804 Events)",
    "$R{1000030_ReportTitle_Stat805}": "יומן אירועים מפורט (Stat805 Event Journal)",
    "$R{1000035_ReportTitle_Duration}": "דוח זמני שהייה בחניון",
    "$R{1000036_ReportTitle_Occupancy}": "דוח תפוסה לפי שעות",
    "$R{1000037_ReportTitle_Turnover}": "דוח פדיון והכנסות יומי",
    "$R{1000038_ReportTitle_TurnoverCYAD}": "דוח פדיון שנתי/חודשי מצטבר",
    "$R{1000039_ReportTitle_Cashier}": "דוח קופות ומשמרות",
    "$R{1000041_ReportTitle_Events}": "דוח אירועי מערכת",
    "$R{1000042_ReportTitle_LaneActivity}": "פעילות נתיבים לפי שעה ויום",
    "$R{1000043_ReportTitle_LaneActivity}": "פעילות נתיבים וזמני שהייה",
    "$R{1000044_ReportTitle_VPresenceCustCard}": "נוכחות מנויים בחניון",
    "$R{1000045_ReportTitle_AVGDuration}": "ממוצע שהייה ופתיחות מחסום",
    "$R{1000047_ReportTitle_Turnover}": "דוח פדיון מפורט",
    "$R{1000048_ReportTitle_TurnoverWeekday}": "פדיון לפי ימים בשבוע",
    "$R{1000049_ReportTitle_BarOpen}": "דוח פתיחות מחסום ידניות",
    "$R{1000121_ReportTitle_CashContent}": "תכולת מזומן בקופות",
    "$R{1000174_ReportTitle_Additional_Payment}": "תשלומים נוספים של מנויים",
    "$R{1000175_ReportTitle_Parking_Tariff_Analysis}": "ניתוח תעריפי חניה"
}

def _normalize_sb_hebrew_label(txt):
    if not txt:
        return ""
    s = str(txt).strip()
    if s == "הינח":
        return "דמי חניה (תעריף מזדמן)"
    if s.startswith("Turn. "):
        return "אשראי " + s.replace("Turn. ", "").strip()
    if s.startswith("Credit "):
        return "אשראי " + s.replace("Credit ", "").strip()
    return s

def fetch_online_daily_report(project_number, ip, port, target_date=None, end_date=None):
    """
    שולף דוח הכנסות, פילוח אמצעי תשלום (כולל מזומן, אשראי, פנגו #610 וסלופארק #699),
    הנחות/שוברים, כניסות ויציאות של כל המתחמים בחניון (כולל פילוח לכל מתחם),
    פתיחות מחסום ידניות והתפלגות שעתית עבור תאריך בודד או טווח תאריכים (מתאריך עד תאריך):
    1. ישירות מטבלאות ה-FlexRep/UDB/TSETHELP/LOGGVORGANG בבקר החניון (דרך /vehicle-api/daily-report.jsp או פורט 1521).
    2. מטבלת הדוחות הקבועה parking_data ב-Supabase (בשרת Render).
    """
    import subprocess
    today_iso = get_il_now().strftime("%Y-%m-%d")
    if not target_date or not re.match(r"^\d{4}-\d{2}-\d{2}$", str(target_date).strip()):
        start_dt = today_iso
    else:
        start_dt = str(target_date).strip()

    if not end_date or not re.match(r"^\d{4}-\d{2}-\d{2}$", str(end_date).strip()):
        end_dt = start_dt
    else:
        end_dt = str(end_date).strip()

    if start_dt > end_dt:
        start_dt, end_dt = end_dt, start_dt

    is_range = (start_dt != end_dt)
    date_label = f"{start_dt} עד {end_dt}" if is_range else start_dt

    FACILITY_NAMES_HE = {
        3050: "מבנה תוצרת הארץ (3050)",
        3200: "מבנה סוללים (3200)",
        3210: "מבנה 3210",
        3220: "מבנה 3220",
        3300: "מבנה 3300",
        473223100: "מבנה תל אביב (תוצרת הארץ)",
        473223200: "מבנה סוללים"
    }

    report = {
        "report_date": start_dt,
        "start_date": start_dt,
        "end_date": end_dt,
        "is_range": is_range,
        "date_display": date_label,
        "is_today": (start_dt == today_iso and end_dt == today_iso),
        "source": "none",
        "source_label_he": "לא זמין",
        "revenue": {
            "total_revenue_ils": 0.0,
            "pos_turnover_ils": 0.0,
            "cash_ils": 0.0,
            "credit_ils": 0.0,
            "pango_ils": 0.0,
            "pango_count": 0,
            "cello_ils": 0.0,
            "cello_count": 0,
            "net_revenue_no_vat_ils": 0.0,
            "vat_ils": 0.0,
            "gross_tariff_ils": 0.0,
            "discounts_total_ils": 0.0,
            "paid_transactions_count": 0,
            "pos_paid_count": 0
        },
        "payment_channels": [],
        "payment_methods": [],
        "discounts_breakdown": [],
        "traffic": {
            "entries_total": 0,
            "entries_transient": 0,
            "entries_subscribers": 0,
            "entries_app_external": 0,
            "entries_vouchers": 0,
            "exits_total": 0,
            "exits_transient": 0,
            "exits_subscribers": 0,
            "exits_app_external": 0,
            "exits_vouchers": 0,
            "exits_grace_free": 0,
            "barrier_manual_opens": 0,
            "tsethelp_barrier_opens": 0,
            "udb_barrier_opens": 0,
            "user_audit_actions": 0,
            "internal_passages": 0
        },
        "facilities_traffic": [],
        "hourly": [],
        "recent_days": [],
        "flexrep_catalog": []
    }

    def _parse_udb_tsv_output(out_text):
        section = ""
        gross_ils = 0.0
        discounts_ils = 0.0
        net_turnover_ils = 0.0
        vat_ils = 0.0
        pos_paid_cnt = 0
        pay_methods_map = {}

        cash_ils = 0.0
        credit_ils = 0.0
        pango_ils = 0.0
        pango_cnt = 0
        cello_ils = 0.0
        cello_cnt = 0

        tset_cash = 0.0
        tset_cred = 0.0
        tset_pango = 0.0
        tset_celo = 0.0
        tset_open_b = 0
        udb_open_b = 0
        ua_cnt = 0

        for raw_line in out_text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("[SECTION:") and line.endswith("]"):
                section = line[9:-1]
                continue

            parts = line.split("\t")
            if section == "BREAKDOWN" and len(parts) >= 6:
                art_cls = int(parts[0])
                tt = int(parts[1])
                ctext = parts[2].strip()
                qty = int(float(parts[3]))
                cnt = int(float(parts[4]))
                ils = float(parts[5])

                if art_cls == 0:
                    if ils > 0:
                        gross_ils += ils
                    if "grace" in ctext.lower():
                        report["traffic"]["exits_grace_free"] += qty
                elif art_cls == 10:
                    report["traffic"]["entries_total"] += qty
                    if tt == 1:
                        report["traffic"]["entries_transient"] += qty
                    elif tt == 2:
                        report["traffic"]["entries_subscribers"] += qty
                    elif tt == 3:
                        report["traffic"]["entries_vouchers"] += qty
                    elif tt == 4:
                        report["traffic"]["entries_app_external"] += qty
                elif art_cls == 11:
                    report["traffic"]["exits_total"] += qty
                    if tt == 11:
                        report["traffic"]["exits_transient"] += qty
                    elif tt == 12:
                        report["traffic"]["exits_subscribers"] += qty
                    elif tt == 13:
                        report["traffic"]["exits_vouchers"] += qty
                    elif tt == 14:
                        report["traffic"]["exits_app_external"] += qty
                elif art_cls == 17:
                    if tt == 58:
                        report["traffic"]["internal_passages"] += qty
                    elif tt in (88, 90, 51, 63):
                        udb_open_b += qty
                elif art_cls == 901:
                    discounts_ils += ils
                    report["discounts_breakdown"].append({
                        "name": _normalize_sb_hebrew_label(ctext) or "שובר / הנחה",
                        "count": qty,
                        "amount_ils": round(ils, 2)
                    })
                elif art_cls == 1000:
                    net_turnover_ils += ils
                    pos_paid_cnt += qty
                elif art_cls == 1001:
                    lbl = _normalize_sb_hebrew_label(ctext)
                    if "cash" in ctext.lower() or "מזומן" in lbl:
                        cash_ils += ils
                    else:
                        credit_ils += ils
                    if lbl not in pay_methods_map:
                        pay_methods_map[lbl] = {"name": lbl, "count": 0, "amount_ils": 0.0}
                    pay_methods_map[lbl]["count"] += qty
                    pay_methods_map[lbl]["amount_ils"] = round(pay_methods_map[lbl]["amount_ils"] + ils, 2)
                elif art_cls == 1002:
                    vat_ils += ils

            elif section == "FACILITIES_TRAFFIC" and len(parts) >= 11:
                fid = int(float(parts[0]))
                ent_t = int(float(parts[1]))
                ent_tr = int(float(parts[2]))
                ent_sb = int(float(parts[3]))
                ent_ap = int(float(parts[4]))
                ext_t = int(float(parts[5]))
                ext_tr = int(float(parts[6]))
                ext_sb = int(float(parts[7]))
                ext_ap = int(float(parts[8]))
                f_rev = round(float(parts[9]), 2)
                f_bar = int(float(parts[10]))
                if fid > 0 and (ent_t > 0 or ext_t > 0 or f_rev > 0):
                    report["facilities_traffic"].append({
                        "facility_id": fid,
                        "facility_name": FACILITY_NAMES_HE.get(fid, f"מתחם #{fid}"),
                        "entries_total": ent_t,
                        "entries_transient": ent_tr,
                        "entries_subscribers": ent_sb,
                        "entries_app": ent_ap,
                        "exits_total": ext_t,
                        "exits_transient": ext_tr,
                        "exits_subscribers": ext_sb,
                        "exits_app": ext_ap,
                        "pos_revenue_ils": f_rev,
                        "barrier_opens": f_bar
                    })

            elif section == "PANGO_CELLO" and len(parts) >= 3:
                dev_id = int(float(parts[0]))
                pc_cnt = int(float(parts[1]))
                pc_ils = float(parts[2])
                if dev_id == 610:
                    pango_cnt += pc_cnt
                    pango_ils += pc_ils
                elif dev_id == 699:
                    cello_cnt += pc_cnt
                    cello_ils += pc_ils

            elif section == "TSETHELP" and len(parts) >= 7:
                tset_cash += float(parts[2])
                tset_cred += float(parts[3])
                tset_pango += float(parts[4])
                tset_celo += float(parts[5])
                tset_open_b += int(float(parts[6]))

            elif section == "USER_AUDIT_COUNT" and len(parts) >= 1:
                ua_cnt = int(float(parts[0]))

            elif section == "HOURLY" and len(parts) >= 4:
                hr = parts[0].strip()
                report["hourly"].append({
                    "hour": f"{hr}:00",
                    "entries": int(float(parts[1])),
                    "exits": int(float(parts[2])),
                    "revenue_ils": round(float(parts[3]), 2)
                })

            elif section == "RECENT_DAYS" and len(parts) >= 5:
                report["recent_days"].append({
                    "date": parts[0].strip(),
                    "entries": int(float(parts[1])),
                    "exits": int(float(parts[2])),
                    "revenue_ils": round(float(parts[3]), 2),
                    "paid_count": int(float(parts[4]))
                })

            elif section == "FLEXREP_REPORTS" and len(parts) >= 2:
                rid = parts[0].strip()
                rname = parts[1].strip()
                rmemo = parts[2].strip() if len(parts) > 2 else ""
                report["flexrep_catalog"].append({
                    "id": rid,
                    "code": rname,
                    "name_he": FLEXREP_REPORT_NAMES_HE.get(rname, rmemo or rname),
                    "memo": rmemo
                })

        if cash_ils == 0.0 and tset_cash > 0:
            cash_ils = tset_cash
        if credit_ils == 0.0 and tset_cred > 0:
            credit_ils = tset_cred
        if pango_ils == 0.0 and tset_pango > 0:
            pango_ils = tset_pango
        if cello_ils == 0.0 and tset_celo > 0:
            cello_ils = tset_celo

        if net_turnover_ils == 0.0 and (cash_ils + credit_ils) > 0:
            net_turnover_ils = cash_ils + credit_ils

        total_combined_rev = round(net_turnover_ils + pango_ils + cello_ils, 2)
        total_vat = round(total_combined_rev - (total_combined_rev / 1.18), 2) if total_combined_rev > 0 else 0.0
        total_net_no_vat = round(total_combined_rev - total_vat, 2)
        total_paid_vehicles = pos_paid_cnt + pango_cnt + cello_cnt

        best_open_b = udb_open_b if udb_open_b > 0 else tset_open_b
        report["traffic"]["barrier_manual_opens"] = best_open_b
        report["traffic"]["udb_barrier_opens"] = udb_open_b
        report["traffic"]["tsethelp_barrier_opens"] = tset_open_b
        report["traffic"]["user_audit_actions"] = ua_cnt

        report["source"] = "live_udb_flexrep"
        report["source_label_he"] = "חי מבקר החניון (UDB + LOGGVORGANG + TSETHELP)"
        report["revenue"] = {
            "total_revenue_ils": total_combined_rev,
            "pos_turnover_ils": round(net_turnover_ils, 2),
            "cash_ils": round(cash_ils, 2),
            "credit_ils": round(credit_ils if credit_ils > 0 else max(0.0, net_turnover_ils - cash_ils), 2),
            "pango_ils": round(pango_ils, 2),
            "pango_count": pango_cnt,
            "cello_ils": round(cello_ils, 2),
            "cello_count": cello_cnt,
            "net_revenue_no_vat_ils": total_net_no_vat,
            "vat_ils": total_vat,
            "gross_tariff_ils": round((gross_ils if gross_ils > 0 else (net_turnover_ils - discounts_ils)) + pango_ils + cello_ils, 2),
            "discounts_total_ils": round(discounts_ils, 2),
            "paid_transactions_count": total_paid_vehicles,
            "pos_paid_count": pos_paid_cnt
        }

        report["payment_channels"] = [
            {"key": "cash", "name": "💵 מזומן בקופות", "amount_ils": round(cash_ils, 2), "count": 0},
            {"key": "credit", "name": "💳 כרטיסי אשראי (קופות/יציאה)", "amount_ils": round(report["revenue"]["credit_ils"], 2), "count": pos_paid_cnt},
            {"key": "pango", "name": "🅿️ פנגו (Pango #610)", "amount_ils": round(pango_ils, 2), "count": pango_cnt},
            {"key": "cello", "name": "📱 סלופארק (Cellopark #699)", "amount_ils": round(cello_ils, 2), "count": cello_cnt}
        ]

        # Build detailed payment methods list (always including Cash, Credit brands, Pango, Cellopark)
        pm_list = [{"name": "💵 מזומן", "count": 0, "amount_ils": round(cash_ils, 2)}]
        pm_list.extend(sorted(
            list(pay_methods_map.values()),
            key=lambda x: x["amount_ils"],
            reverse=True
        ))
        pm_list.append({"name": "🅿️ פנגו (Pango - מסוף 610)", "count": pango_cnt, "amount_ils": round(pango_ils, 2)})
        pm_list.append({"name": "📱 סלופארק (Cellopark - מסוף 699)", "count": cello_cnt, "amount_ils": round(cello_ils, 2)})
        report["payment_methods"] = pm_list
        return report

    # 1. Try HTTPS call from Render to /vehicle-api/daily-report.jsp?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD on the parking server (port 8443)
    if ip:
        try:
            jsp_res = make_sb_request(
                "GET",
                ip,
                port,
                "/vehicle-api/daily-report.jsp",
                params={"date": start_dt, "start_date": start_dt, "end_date": end_dt},
                timeout=8
            )
            if jsp_res["status"] == 200 and "[SECTION:BREAKDOWN]" in (jsp_res.get("text") or ""):
                return _parse_udb_tsv_output(jsp_res["text"])
        except Exception:
            pass

    # 2. Try Supabase parking_data on Render (permanent daily & historical reports table, aggregating all sub-parkings of the site)
    sb = _get_supabase()
    if sb and project_number:
        try:
            def _row_field_ils(r, shekel_col, agorot_col):
                v = float(r.get(shekel_col) or 0)
                if v > 0:
                    return v
                return int(r.get(agorot_col) or 0) / 100.0

            def _row_rev_ils(r):
                cash_v = _row_field_ils(r, "s_cash_shekels", "s_cash_agorot")
                cred_v = _row_field_ils(r, "s_credit_shekels", "s_credit_agorot")
                pango_v = _row_field_ils(r, "s_pango_shekels", "s_pango_agorot")
                celo_v = _row_field_ils(r, "s_celo_shekels", "s_celo_agorot")
                channels_sum = cash_v + cred_v + pango_v + celo_v
                if channels_sum > 0:
                    return channels_sum
                v = float(r.get("total_revenue_shekels") or 0)
                if v > 0:
                    return v
                return int(r.get("stot_cacr") or 0) / 100.0

            # Include sibling facilities of the same parking site (e.g. 473223100 + 473223200)
            proj_str = str(project_number).strip()
            candidate_projs_str = [proj_str]
            if len(proj_str) == 9 and proj_str.startswith("473223"):
                candidate_projs_str = ["473223100", "473223200"]
            elif proj_str == "3050":
                candidate_projs_str = ["3050", "3200", "473223100", "473223200"]
            candidate_projs_int = [int(x) for x in candidate_projs_str if x.isdigit()]

            all_rows = []
            for tbl_name in ("parking_data", "csv_import_shekels"):
                try:
                    q_res = (
                        sb.table(tbl_name)
                        .select("*")
                        .in_("project_number", candidate_projs_int)
                        .order("report_date", desc=True)
                        .limit(200)
                        .execute()
                    )
                    if q_res.data:
                        all_rows = q_res.data
                        break
                except Exception:
                    pass
                if not all_rows:
                    try:
                        q_res = (
                            sb.table(tbl_name)
                            .select("*")
                            .in_("project_number", candidate_projs_str)
                            .order("report_date", desc=True)
                            .limit(200)
                            .execute()
                        )
                        if q_res.data:
                            all_rows = q_res.data
                            break
                    except Exception:
                        pass

            if all_rows:
                by_date = {}
                for r in all_rows:
                    dt_k = str(r.get("report_date") or "").strip()[:10]
                    if not dt_k:
                        continue
                    by_date.setdefault(dt_k, []).append(r)

                sorted_dates = sorted(by_date.keys(), reverse=True)
                for dt_k in sorted_dates[:14]:
                    d_rows = by_date[dt_k]
                    report["recent_days"].append({
                        "date": dt_k,
                        "entries": sum(int(x.get("t_entry_tot") or 0) for x in d_rows),
                        "exits": sum(int(x.get("t_exit_tot") or 0) for x in d_rows),
                        "revenue_ils": round(sum(_row_rev_ils(x) for x in d_rows), 2),
                        "paid_count": sum(
                            int(x.get("stay_015") or 0) + int(x.get("stay_030") or 0) + int(x.get("stay_045") or 0) +
                            int(x.get("stay_060") or 0) + int(x.get("stay_2") or 0) + int(x.get("stay_3") or 0) +
                            int(x.get("stay_4") or 0) + int(x.get("stay_5") or 0) + int(x.get("stay_6") or 0) +
                            int(x.get("stay_724") or 0)
                            for x in d_rows
                        )
                    })

                rows = []
                for dt_k, d_rows in by_date.items():
                    if start_dt <= dt_k <= end_dt:
                        rows.extend(d_rows)

                if not rows and sorted_dates and report["is_today"]:
                    latest_dt = sorted_dates[0]
                    rows = by_date.get(latest_dt, [])
                    report["report_date"] = latest_dt
                    report["start_date"] = latest_dt
                    report["end_date"] = latest_dt
                    report["date_display"] = latest_dt
                    report["is_today"] = False

                if rows:
                    cash_ils = sum(_row_field_ils(r, "s_cash_shekels", "s_cash_agorot") for r in rows)
                    cred_ils = sum(_row_field_ils(r, "s_credit_shekels", "s_credit_agorot") for r in rows)
                    pango_ils = sum(_row_field_ils(r, "s_pango_shekels", "s_pango_agorot") for r in rows)
                    celo_ils = sum(_row_field_ils(r, "s_celo_shekels", "s_celo_agorot") for r in rows)
                    tot_rev = cash_ils + cred_ils + pango_ils + celo_ils
                    if tot_rev <= 0:
                        tot_rev = sum(_row_rev_ils(r) for r in rows)
                    net_rev = round(tot_rev / 1.18, 2) if tot_rev > 0 else 0.0

                    ent_tot = sum(int(r.get("t_entry_tot") or 0) for r in rows)
                    ent_s = sum(int(r.get("t_entry_s") or 0) for r in rows)
                    ent_p = sum(int(r.get("t_entry_p") or 0) for r in rows)
                    ent_ap = sum(int(r.get("t_entry_ap") or 0) for r in rows)
                    ext_tot = sum(int(r.get("t_exit_tot") or 0) for r in rows)
                    ext_s = sum(int(r.get("t_exit_s") or 0) for r in rows)
                    ext_p = sum(int(r.get("t_exit_p") or 0) for r in rows)
                    ext_ap = sum(int(r.get("t_exit_ap") or 0) for r in rows)
                    open_b = sum(int(r.get("t_open_b") or 0) for r in rows)

                    stay_paid_cnt = sum(
                        int(r.get("stay_015") or 0) + int(r.get("stay_030") or 0) + int(r.get("stay_045") or 0) +
                        int(r.get("stay_060") or 0) + int(r.get("stay_2") or 0) + int(r.get("stay_3") or 0) +
                        int(r.get("stay_4") or 0) + int(r.get("stay_5") or 0) + int(r.get("stay_6") or 0) +
                        int(r.get("stay_724") or 0)
                        for r in rows
                    )

                    # Build per-facility breakdown from rows
                    fac_map = {}
                    for r in rows:
                        f_code = int(r.get("s_computer") or r.get("project_number") or 0)
                        f_name = str(r.get("c_text") or r.get("ctext") or "").strip() or FACILITY_NAMES_HE.get(f_code, f"חניון #{f_code}")
                        if f_code not in fac_map:
                            fac_map[f_code] = {
                                "facility_id": f_code,
                                "facility_name": f_name,
                                "entries_total": 0,
                                "entries_transient": 0,
                                "entries_subscribers": 0,
                                "entries_app": 0,
                                "exits_total": 0,
                                "exits_transient": 0,
                                "exits_subscribers": 0,
                                "exits_app": 0,
                                "pos_revenue_ils": 0.0,
                                "barrier_opens": 0
                            }
                        fm = fac_map[f_code]
                        fm["entries_total"] += int(r.get("t_entry_tot") or 0)
                        fm["entries_transient"] += int(r.get("t_entry_p") or 0)
                        fm["entries_subscribers"] += int(r.get("t_entry_s") or 0)
                        fm["entries_app"] += int(r.get("t_entry_ap") or 0)
                        fm["exits_total"] += int(r.get("t_exit_tot") or 0)
                        fm["exits_transient"] += int(r.get("t_exit_p") or 0)
                        fm["exits_subscribers"] += int(r.get("t_exit_s") or 0)
                        fm["exits_app"] += int(r.get("t_exit_ap") or 0)
                        fm["pos_revenue_ils"] = round(fm["pos_revenue_ils"] + _row_rev_ils(r), 2)
                        fm["barrier_opens"] += int(r.get("t_open_b") or 0)
                    report["facilities_traffic"] = list(fac_map.values())

                    report["source"] = "supabase_parking_data"
                    report["source_label_he"] = "דוח חניון בשרת הענן (Render / Supabase TSETHELP)"
                    report["revenue"] = {
                        "total_revenue_ils": round(tot_rev, 2),
                        "pos_turnover_ils": round(cash_ils + cred_ils, 2),
                        "cash_ils": round(cash_ils, 2),
                        "credit_ils": round(cred_ils, 2),
                        "pango_ils": round(pango_ils, 2),
                        "pango_count": 0,
                        "cello_ils": round(celo_ils, 2),
                        "cello_count": 0,
                        "net_revenue_no_vat_ils": round(net_rev, 2),
                        "vat_ils": round(max(0.0, tot_rev - net_rev), 2),
                        "gross_tariff_ils": round(tot_rev, 2),
                        "discounts_total_ils": 0.0,
                        "paid_transactions_count": stay_paid_cnt if stay_paid_cnt > 0 else ext_p,
                        "pos_paid_count": stay_paid_cnt
                    }
                    report["payment_channels"] = [
                        {"key": "cash", "name": "💵 מזומן בקופות", "amount_ils": round(cash_ils, 2), "count": 0},
                        {"key": "credit", "name": "💳 כרטיסי אשראי (קופות/יציאה)", "amount_ils": round(cred_ils, 2), "count": 0},
                        {"key": "pango", "name": "🅿️ פנגו (Pango #610)", "amount_ils": round(pango_ils, 2), "count": 0},
                        {"key": "cello", "name": "📱 סלופארק (Cellopark #699)", "amount_ils": round(celo_ils, 2), "count": 0}
                    ]
                    report["payment_methods"] = [
                        {"name": "💵 מזומן", "count": 0, "amount_ils": round(cash_ils, 2)},
                        {"name": "💳 כרטיסי אשראי", "count": 0, "amount_ils": round(cred_ils, 2)},
                        {"name": "🅿️ פנגו (Pango)", "count": 0, "amount_ils": round(pango_ils, 2)},
                        {"name": "📱 סלופארק (Cellopark)", "count": 0, "amount_ils": round(celo_ils, 2)}
                    ]
                    report["traffic"].update({
                        "entries_total": ent_tot,
                        "entries_transient": ent_p,
                        "entries_subscribers": ent_s,
                        "entries_app_external": ent_ap,
                        "exits_total": ext_tot,
                        "exits_transient": ext_p,
                        "exits_subscribers": ext_s,
                        "exits_app_external": ext_ap,
                        "barrier_manual_opens": open_b,
                        "tsethelp_barrier_opens": open_b
                    })
                    return report
        except Exception as e:
            print(f"Supabase parking_data report error: {e}")

    # 3. Direct Oracle Helper fallback (uses local LAN IP 10.35.122.200 if external IP 192.117.0.122 is passed locally)
    helper_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sb_oracle_helper")
    jar_path = os.path.join(helper_dir, "ojdbc6.jar")
    class_file = os.path.join(helper_dir, "SBOracleReportHelper.class")

    oracle_ip = "10.35.122.200" if str(ip) in ("192.117.0.122", "10.35.122.200", "") else str(ip)
    if oracle_ip and os.path.exists(jar_path) and os.path.exists(class_file):
        try:
            cp_sep = ";" if os.name == "nt" else ":"
            cp_arg = f"{helper_dir}{cp_sep}{jar_path}"
            proc = subprocess.run(
                ["java", "-cp", cp_arg, "SBOracleReportHelper", oracle_ip, start_dt, end_dt],
                capture_output=True,
                timeout=12
            )
            if proc.returncode == 0 and proc.stdout:
                out_text = proc.stdout.decode("utf-8", errors="replace")
                return _parse_udb_tsv_output(out_text)
        except Exception as e:
            print(f"Live Oracle FlexRep report fallback notice for {oracle_ip}: {e}")

    return report

@parking_control_bp.route('/api/parking-control/counters', methods=['GET'])
def api_control_get_counters():
    user = _get_authenticated_control_user()
    hdr_token = request.headers.get('X-Control-Token') or request.args.get('auth_token') or request.args.get('token')
    if not user and not hdr_token:
        return jsonify({'success': False, 'message': 'לא מחובר'}), 401

    proj = str(
        request.args.get('project_number')
        or request.headers.get('X-Control-Project')
        or (user.get('active_project_number') if user else '')
        or (user.get('project_number') if user else '')
        or '473223100'
    )
    start_date = request.args.get('start_date') or request.args.get('date') or get_il_now().strftime('%Y-%m-%d')
    end_date = request.args.get('end_date') or start_date
    conn = _get_parking_conn(proj) or {'ip_address': '10.35.122.200', 'port': 8443}
    if not conn or not conn.get('ip_address'):
        return jsonify({'success': False, 'message': 'אין חיבור לבקר החניון'}), 404

    ip = conn['ip_address']
    port = conn.get('port', 8443)
    with ThreadPoolExecutor(max_workers=2) as ex:
        f_cnt = ex.submit(fetch_online_parking_counters, proj, ip, port)
        f_rep = ex.submit(fetch_online_daily_report, proj, ip, port, start_date, end_date)
        data = f_cnt.result()
        daily_rep = f_rep.result()

    return jsonify({
        'success': True,
        'project_number': proj,
        'timestamp': get_il_now().strftime('%H:%M:%S'),
        'daily_report': daily_rep,
        **data
    })

@parking_control_bp.route('/api/parking-control/daily-report', methods=['GET'])
def api_control_get_daily_report():
    user = _get_authenticated_control_user()
    hdr_token = request.headers.get('X-Control-Token') or request.args.get('auth_token') or request.args.get('token')
    if not user and not hdr_token:
        return jsonify({'success': False, 'message': 'לא מחובר'}), 401

    proj = str(
        request.args.get('project_number')
        or request.headers.get('X-Control-Project')
        or (user.get('active_project_number') if user else '')
        or (user.get('project_number') if user else '')
        or '3050'
    )
    start_date = request.args.get('start_date') or request.args.get('date') or get_il_now().strftime('%Y-%m-%d')
    end_date = request.args.get('end_date') or start_date
    conn = _get_parking_conn(proj) or {'ip_address': '10.35.122.200', 'port': 8443}

    daily_rep = fetch_online_daily_report(proj, conn['ip_address'], conn.get('port', 8443), start_date, end_date)
    return jsonify({
        'success': True,
        'project_number': proj,
        'timestamp': get_il_now().strftime('%H:%M:%S'),
        'daily_report': daily_rep
    })

@parking_control_bp.route('/api/parking-control/counters/update', methods=['POST'])
def api_control_update_counter():
    user = _get_authenticated_control_user()
    if not user:
        return jsonify({'success': False, 'message': 'לא מחובר'}), 401

    data = request.get_json(silent=True) or {}
    proj = str(data.get('project_number') or user.get('active_project_number') or user.get('project_number') or '')
    facility_id = str(data.get('facility_id') or '1').strip()
    counter_id = str(data.get('counter_id') or '1').strip()
    operation = str(data.get('operation') or '').strip()
    value = data.get('value', 0)

    conn = _get_parking_conn(proj)
    if not conn or not conn.get('ip_address'):
        return jsonify({'success': False, 'message': 'אין חיבור לבקר החניון'}), 404

    res = update_online_counter(
        project_number=proj,
        parking_name=conn.get('name') or user.get('parking_name') or f'חניון {proj}',
        ip=conn['ip_address'],
        port=conn.get('port', 8443),
        user_obj=user,
        facility_id=facility_id,
        counter_id=counter_id,
        operation=operation,
        value=value
    )
    return jsonify(res)

# ============================================================================
# 9. ROUTES: TAB 3 - COMPANIES & SUBSCRIBERS MANAGEMENT
# ============================================================================
def _parse_allowed_companies(company_list_str):
    if not company_list_str or str(company_list_str).strip().lower() in ('all', '', '0'):
        return None  # All allowed
    allowed = set()
    for part in str(company_list_str).split(','):
        part = part.strip()
        if '-' in part:
            try:
                s, e = part.split('-', 1)
                allowed.update(range(int(s.strip()), int(e.strip()) + 1))
            except Exception:
                pass
        elif part.isdigit():
            allowed.add(int(part))
    return allowed if allowed else None

@parking_control_bp.route('/api/parking-control/companies', methods=['GET'])
def api_control_get_companies():
    """
    שולף את כל החברות במערכת המנויים (/CustomerMediaWebService/contracts)
    כולל מכסת חניות ונוכחות במידת הצורך.
    """
    user = _get_authenticated_control_user()
    if not user:
        return jsonify({'success': False, 'message': 'לא מחובר'}), 401

    proj = str(request.args.get('project_number') or user.get('active_project_number') or user.get('project_number') or '')
    conn = _get_parking_conn(proj)
    if not conn or not conn.get('ip_address'):
        return jsonify({'success': False, 'message': 'אין חיבור לבקר החניון'}), 404

    ip = conn['ip_address']
    port = conn.get('port', 8443)
    allowed_set = _parse_allowed_companies(user.get('company_list'))

    res = make_sb_request("GET", ip, port, "/CustomerMediaWebService/contracts", headers={"Accept": "application/xml"}, timeout=10)
    if res["status"] != 200 or not res["data"]:
        return jsonify({'success': False, 'message': f'שגיאה במשיכת רשימת חברות מבקר החניון (HTTP {res["status"]})'})

    companies = []
    try:
        xml_text = re.sub(r'\sxmlns="[^"]+"', '', res["data"].decode("utf-8", errors="replace"))
        root = ET.fromstring(xml_text)
        for c_el in root.findall(".//contract"):
            cid_s = (c_el.findtext("id") or "").strip()
            cname = (c_el.findtext("name") or f"חברה {cid_s}").strip()
            if not cid_s:
                continue
            try:
                cid_int = int(cid_s)
            except ValueError:
                cid_int = 0
            if allowed_set is not None and cid_int not in allowed_set:
                continue
            companies.append({
                "id": cid_s,
                "id_num": cid_int,
                "name": cname,
                "is_blocked_range": (10000 <= cid_int <= 10010)
            })
        companies.sort(key=lambda x: x["id_num"])
    except Exception as e:
        return jsonify({'success': False, 'message': f'שגיאה בפענוח רשימת חברות: {e}'})

    return jsonify({
        'success': True,
        'project_number': proj,
        'total': len(companies),
        'companies': companies
    })

@parking_control_bp.route('/api/parking-control/companies/<contract_id>/subscribers', methods=['GET'])
def api_control_get_company_subscribers(contract_id):
    """
    בבחירה של חברה: שולף את פרטי החברה (מכסת maxCounter ו-presentCounter)
    ואת כל המנויים שלה בבקשה מרוכזת (/CustomerMediaWebService/contracts/{id}/consumersdetail).
    """
    user = _get_authenticated_control_user()
    if not user:
        return jsonify({'success': False, 'message': 'לא מחובר'}), 401

    proj = str(request.args.get('project_number') or user.get('active_project_number') or user.get('project_number') or '')
    conn = _get_parking_conn(proj)
    if not conn or not conn.get('ip_address'):
        return jsonify({'success': False, 'message': 'אין חיבור לבקר החניון'}), 404

    cid = str(contract_id).strip()
    allowed_set = _parse_allowed_companies(user.get('company_list'))
    if allowed_set is not None and cid.isdigit() and int(cid) not in allowed_set:
        return jsonify({'success': False, 'message': 'אין לך הרשאה לצפות בחברה זו'}), 403

    ip = conn['ip_address']
    port = conn.get('port', 8443)

    with ThreadPoolExecutor(max_workers=2) as ex:
        f_con = ex.submit(make_sb_request, "GET", ip, port, f"/CustomerMediaWebService/contracts/{cid}/detail", "2022", "2022", None, None, {"Accept": "application/xml"}, 10)
        f_subs = ex.submit(make_sb_request, "GET", ip, port, f"/CustomerMediaWebService/contracts/{cid}/consumersdetail", "2022", "2022", None, None, {"Accept": "application/xml"}, 25)
        con_res = f_con.result()
        subs_res = f_subs.result()

    company_info = {
        "id": cid,
        "name": f"חברה {cid}",
        "max_counter": 0,
        "present_counter": 0,
        "status": 0,
        "valid_from": "",
        "valid_until": ""
    }
    if con_res["status"] == 200 and con_res["data"]:
        try:
            c_xml = re.sub(r'\sxmlns="[^"]+"', '', con_res["data"].decode("utf-8", errors="replace"))
            c_root = ET.fromstring(c_xml)
            company_info["name"] = (c_root.findtext(".//contract/name") or company_info["name"]).strip()
            company_info["status"] = int(c_root.findtext("status") or 0)
            company_info["valid_from"] = (c_root.findtext("xValidFrom") or "")[:10]
            company_info["valid_until"] = (c_root.findtext("xValidUntil") or "")[:10]
            for pd in c_root.findall(".//poolingDetail"):
                fac_v = (pd.findtext("facility") or "0").strip()
                prof_v = (pd.findtext("extCardProfile") or "0").strip()
                mc_v = int(pd.findtext("maxCounter") or 0)
                pc_v = int(pd.findtext("presentCounter") or 0)
                if fac_v == "0" and prof_v == "0":
                    company_info["max_counter"] = mc_v
                    company_info["present_counter"] = pc_v
                    break
                elif company_info["max_counter"] == 0 and mc_v > 0:
                    company_info["max_counter"] = mc_v
                    company_info["present_counter"] = pc_v
        except Exception:
            pass

    subscribers = []
    if subs_res["status"] == 200 and subs_res["data"]:
        try:
            s_xml = re.sub(r'\sxmlns="[^"]+"', '', subs_res["data"].decode("utf-8", errors="replace"))
            s_root = ET.fromstring(s_xml)
            for cd in s_root.findall(".//consumerDetail"):
                sid = _clean_sb_val(cd.findtext(".//consumer/id", "") or cd.findtext("id", ""))
                fname = _clean_sb_val(cd.findtext(".//person/firstName", "") or cd.findtext("firstName", ""))
                surnames = [_clean_sb_val(s.text) for s in cd.findall(".//surname") if _clean_sb_val(s.text)]
                lname = surnames[0] if surnames else _clean_sb_val(cd.findtext(".//consumer/name", ""))
                lpn1 = _clean_sb_val(cd.findtext("lpn1", ""))
                lpn2 = _clean_sb_val(cd.findtext("lpn2", ""))
                lpn3 = _clean_sb_val(cd.findtext("lpn3", ""))
                pres_s = _clean_sb_val(cd.findtext(".//identification/present", "") or cd.findtext("present", ""))
                is_pres = (pres_s.lower() == "true")
                v_from = _clean_sb_val(cd.findtext(".//identification/validFrom", "") or cd.findtext("validFrom", ""))
                v_until = _clean_sb_val(cd.findtext(".//identification/validUntil", "") or cd.findtext("validUntil", ""))
                memo = _clean_sb_val(cd.findtext("memo", "") or cd.findtext("displayText", ""))
                match_code = _clean_sb_val(cd.findtext("matchCode", ""))
                prof_id = _clean_sb_val(cd.findtext(".//usageProfile/id", ""))
                prof_name = _clean_sb_val(cd.findtext(".//usageProfile/name", "")) or prof_id
                st_val = _clean_sb_val(cd.findtext(".//identification/status", "") or cd.findtext("status", "0"))

                subscribers.append({
                    "id": sid,
                    "contract_id": cid,
                    "composite_id": f"{cid},{sid}",
                    "first_name": fname,
                    "last_name": lname,
                    "full_name": f"{fname} {lname}".strip() or f"מנוי {sid}",
                    "lpn1": lpn1,
                    "lpn2": lpn2,
                    "lpn3": lpn3,
                    "present": is_pres,
                    "valid_from": v_from[:10] if v_from else "",
                    "valid_until": v_until[:10] if v_until else "",
                    "memo": memo,
                    "match_code": match_code,
                    "profile_id": prof_id or "1",
                    "profile_name": prof_name,
                    "is_blocked": (st_val == "2")
                })
            subscribers.sort(key=lambda x: int(x["id"]) if str(x["id"]).isdigit() else 999999)
        except Exception as e:
            print(f"Error parsing consumersdetail for contract {cid}: {e}")

    return jsonify({
        "success": True,
        "company": company_info,
        "subscribers": subscribers,
        "total_subscribers": len(subscribers)
    })

@parking_control_bp.route('/api/parking-control/subscriber/update', methods=['POST'])
def api_control_update_subscriber():
    """
    עדכון פרטי מנוי מהנייד (שם פרטי, שם משפחה, רכב 1-3, תוקף, הערה/חניה, ואיפוס נוכחות במידת הצורך)
    ושליחת העדכון לאירועים.
    """
    user = _get_authenticated_control_user()
    if not user:
        return jsonify({'success': False, 'message': 'לא מחובר'}), 401

    data = request.get_json(silent=True) or {}
    proj = str(data.get('project_number') or user.get('active_project_number') or user.get('project_number') or '')
    contract_id = str(data.get('contract_id') or '').strip()
    subscriber_id = str(data.get('subscriber_id') or '').strip()

    if not contract_id or not subscriber_id:
        return jsonify({'success': False, 'message': 'חסר מזהה חברה או מנוי'}), 400

    conn = _get_parking_conn(proj)
    if not conn or not conn.get('ip_address'):
        return jsonify({'success': False, 'message': 'אין חיבור לבקר החניון'}), 404

    ip = conn['ip_address']
    port = conn.get('port', 8443)
    p_name = conn.get('name') or user.get('parking_name') or f'חניון {proj}'
    comp_id = f"{contract_id},{subscriber_id}"

    # Fetch current XML first to preserve all S&B structure
    get_res = make_sb_request("GET", ip, port, f"/CustomerMediaWebService/consumers/{comp_id}/detail", headers={"Accept": "application/xml"}, timeout=8)
    if get_res["status"] != 200 or not get_res["data"]:
        return jsonify({'success': False, 'message': f'לא ניתן לשלוף את פרטי המנוי מבקר החניון (HTTP {get_res["status"]})'})

    try:
        ns_uri = "http://gsph.sub.com/cust/types"
        ET.register_namespace('', ns_uri)
        ns = {'ns': ns_uri}
        root = ET.fromstring(get_res["data"])

        # Handle Presence Reset if requested or if present and lpn1 is changing
        want_present = data.get('present')
        cur_pres_str = (root.findtext('.//ns:identification/ns:present', default='', namespaces=ns) or '').strip().lower()
        was_present = (cur_pres_str == 'true')

        new_lpn1 = re.sub(r'[^0-9A-Za-zמ]', '', str(data.get('lpn1') or '')).upper()
        new_lpn2 = re.sub(r'[^0-9A-Za-zמ]', '', str(data.get('lpn2') or '')).upper()
        new_lpn3 = re.sub(r'[^0-9A-Za-zמ]', '', str(data.get('lpn3') or '')).upper()
        cur_lpn1 = _clean_sb_val(root.findtext('ns:lpn1', default='', namespaces=ns))

        # If subscriber is present in parking and manager wants to reset presence OR change lpn1, book an exit transaction first
        if was_present and (want_present is False or (new_lpn1 != cur_lpn1)):
            add_park_transaction(ip, port, comp_id, "exit", "201", cell="1", facility_id="1")
            time.sleep(0.2)
            # Re-fetch fresh consumer detail after exit transaction
            refetched = make_sb_request("GET", ip, port, f"/CustomerMediaWebService/consumers/{comp_id}/detail", headers={"Accept": "application/xml"}, timeout=6)
            if refetched["status"] == 200 and refetched["data"]:
                root = ET.fromstring(refetched["data"])

        # Update Person Name
        if 'first_name' in data:
            fn_el = root.find('.//ns:person/ns:firstName', ns)
            if fn_el is not None:
                fn_el.text = str(data.get('first_name') or '').strip()
        if 'last_name' in data:
            sn_el = root.find('.//ns:person/ns:surname', ns)
            if sn_el is not None:
                sn_el.text = str(data.get('last_name') or '').strip()
            cname_el = root.find('.//ns:consumer/ns:name', ns)
            if cname_el is not None:
                cname_el.text = str(data.get('last_name') or '').strip()

        # Update LPNs (in S&B, sending a single space ' ' clears an LPN tag)
        for tag_k, clean_v in [('lpn1', new_lpn1), ('lpn2', new_lpn2), ('lpn3', new_lpn3)]:
            if tag_k in data:
                el = root.find(f'ns:{tag_k}', ns)
                if el is None:
                    el = ET.SubElement(root, f'{{{ns_uri}}}{tag_k}')
                el.text = clean_v if clean_v else ' '

        # Update Validity dates
        ident_el = root.find('.//ns:identification', ns)
        if ident_el is not None:
            if data.get('valid_from'):
                vf_str = str(data['valid_from']).strip()[:10] + "T00:00:00"
                vf_el = ident_el.find('ns:validFrom', ns)
                if vf_el is None:
                    vf_el = ET.SubElement(ident_el, f'{{{ns_uri}}}validFrom')
                vf_el.text = vf_str
            if data.get('valid_until'):
                vu_str = str(data['valid_until']).strip()[:10] + "T23:59:59"
                vu_el = ident_el.find('ns:validUntil', ns)
                if vu_el is None:
                    vu_el = ET.SubElement(ident_el, f'{{{ns_uri}}}validUntil')
                vu_el.text = vu_str

        # Update Memo & MatchCode
        if 'memo' in data:
            memo_el = root.find('ns:memo', ns)
            if memo_el is None:
                memo_el = ET.SubElement(root, f'{{{ns_uri}}}memo')
            memo_el.text = str(data.get('memo') or '').strip()
        if 'match_code' in data:
            mc_el = root.find('.//ns:consumer/ns:matchCode', ns) or root.find('ns:matchCode', ns)
            if mc_el is not None:
                mc_el.text = str(data.get('match_code') or '').strip()

        xml_payload = ET.tostring(root, encoding='utf-8', xml_declaration=True)
        put_res = make_sb_request(
            "PUT",
            ip,
            port,
            f"/CustomerMediaWebService/consumers/{comp_id}/detail",
            data=xml_payload,
            headers={"Accept": "application/xml", "Content-Type": "application/xml; charset=utf-8"},
            timeout=10
        )

        ok = put_res["status"] in (200, 201, 202, 204)
        # If subscriber was present and manager only wanted to change lpn1 (and keep present=True), re-book entry
        if ok and was_present and want_present is not False and (new_lpn1 != cur_lpn1):
            add_park_transaction(ip, port, comp_id, "entry", "101", cell="1", facility_id="1")

        record_local_audit_event(
            project_number=proj,
            parking_name=p_name,
            user_obj=user,
            action_type="SUBSCRIBER_UPDATE",
            unit=f"חברה {contract_id} / מנוי {subscriber_id}",
            plate=new_lpn1,
            reason=f"עדכון מנוי {comp_id}: {data.get('first_name', '')} {data.get('last_name', '')} | רכבים: {new_lpn1}, {new_lpn2}, {new_lpn3}",
            sb_cmd_ok=ok
        )

        if ok:
            return jsonify({'success': True, 'message': f'✅ פרטי המנוי ({comp_id}) עודכנו בהצלחה בבקר החניון!'})
        return jsonify({'success': False, 'message': f'⚠️ בקר החניון דחה את העדכון (HTTP {put_res["status"]})'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'שגיאה בעדכון מנוי: {e}'})

@parking_control_bp.route('/api/parking-control/company/update-quota', methods=['POST'])
def api_control_update_company_quota():
    """
    עדכון מכסת החניות (maxCounter) של חברה ישירות מהנייד.
    """
    user = _get_authenticated_control_user()
    if not user:
        return jsonify({'success': False, 'message': 'לא מחובר'}), 401

    data = request.get_json(silent=True) or {}
    proj = str(data.get('project_number') or user.get('active_project_number') or user.get('project_number') or '')
    contract_id = str(data.get('contract_id') or '').strip()
    new_max = int(data.get('max_counter', 0))

    conn = _get_parking_conn(proj)
    if not conn or not conn.get('ip_address'):
        return jsonify({'success': False, 'message': 'אין חיבור לבקר החניון'}), 404

    ip = conn['ip_address']
    port = conn.get('port', 8443)
    p_name = conn.get('name') or user.get('parking_name') or f'חניון {proj}'

    get_res = make_sb_request("GET", ip, port, f"/CustomerMediaWebService/contracts/{contract_id}/detail", headers={"Accept": "application/xml"}, timeout=8)
    if get_res["status"] != 200 or not get_res["data"]:
        return jsonify({'success': False, 'message': 'שגיאה בשליפת נתוני החברה'})

    try:
        ns_uri = "http://gsph.sub.com/cust/types"
        ET.register_namespace('', ns_uri)
        ns = {'ns': ns_uri}
        root = ET.fromstring(get_res["data"])
        updated = False
        for pd in root.findall('.//ns:poolingDetail', ns):
            f_v = (pd.findtext('ns:facility', default='0', namespaces=ns) or '0').strip()
            p_v = (pd.findtext('ns:extCardProfile', default='0', namespaces=ns) or '0').strip()
            if f_v == '0' and p_v == '0':
                mc_el = pd.find('ns:maxCounter', ns)
                if mc_el is not None:
                    mc_el.text = str(new_max)
                    updated = True
        if not updated:
            first_mc = root.find('.//ns:poolingDetail/ns:maxCounter', ns)
            if first_mc is not None:
                first_mc.text = str(new_max)
                updated = True

        xml_payload = ET.tostring(root, encoding='utf-8', xml_declaration=True)
        put_res = make_sb_request(
            "PUT",
            ip,
            port,
            f"/CustomerMediaWebService/contracts/{contract_id}/detail",
            data=xml_payload,
            headers={"Accept": "application/xml", "Content-Type": "application/xml; charset=utf-8"},
            timeout=8
        )
        ok = put_res["status"] in (200, 201, 202, 204)
        record_local_audit_event(
            project_number=proj,
            parking_name=p_name,
            user_obj=user,
            action_type="COMPANY_QUOTA_UPDATE",
            unit=f"חברה {contract_id}",
            reason=f"עדכון מכסת חניות לחברה {contract_id}: {new_max} מקומות",
            sb_cmd_ok=ok
        )
        if ok:
            return jsonify({'success': True, 'message': f'✅ מכסת החניות של חברה {contract_id} עודכנה ל-{new_max}!'})
        return jsonify({'success': False, 'message': f'עדכון המכסה נדחה (HTTP {put_res["status"]})'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

# ============================================================================
# 10. ROUTES: TAB 4 - VEHICLE SEARCH (SUBSCRIBER OR TRANSIENT + PAYMENT DUE)
# ============================================================================
@parking_control_bp.route('/api/parking-control/search-vehicle', methods=['GET', 'POST'])
def api_control_search_vehicle():
    """
    טאב 4 - חיפוש רכב מהיר כמו של הסייר + בדיקת מנוי או מזדמן וחישוב כמה צריך לשלם:
    מקלידים מספר רכב ומקבלים מיד:
    - האם הוא מנוי (פרטי מנוי, חברה, תוקף, האם נוכח בחניון, תנועה אחרונה).
    - האם הוא מזדמן (שעת כניסה, משך שהייה, נתיב כניסה, האם חייב בתשלום וכמה בדיוק בש"ח).
    """
    user = _get_authenticated_control_user()
    if not user:
        return jsonify({'success': False, 'message': 'לא מחובר'}), 401

    data = (request.get_json(silent=True) or {}) if request.method == 'POST' else request.args
    proj = str(data.get('project_number') or user.get('active_project_number') or user.get('project_number') or '')
    plate_raw = str(data.get('plate') or data.get('license_plate') or '').strip()

    clean_plate = re.sub(r'[^0-9A-Za-zמ]', '', plate_raw).upper()
    if not clean_plate:
        return jsonify({'success': False, 'message': 'נא להקליד מספר רכב לחיפוש'}), 400

    conn = _get_parking_conn(proj)
    if not conn or not conn.get('ip_address'):
        return jsonify({'success': False, 'message': 'אין חיבור לבקר החניון'}), 404

    ip = conn['ip_address']
    port = conn.get('port', 8443)

    # Check both Subscriber and Transient Ticket in parallel for maximum speed & accuracy!
    with ThreadPoolExecutor(max_workers=2) as ex:
        f_sub = ex.submit(inspect_vehicle_by_plate, ip, port, clean_plate, "entry", False)
        f_trans = ex.submit(get_transient_ticket_info, ip, port, clean_plate, True)
        sub_res = f_sub.result()
        trans_res = f_trans.result()

    sub_res["price_info"] = trans_res
    if not sub_res.get("is_subscriber") and trans_res and trans_res.get("found"):
        sub_res["status_title"] = "רכב מזדמן בחניון"
        sub_res["present"] = True
        sub_res["last_tx"] = trans_res.get("entry_time", "")

    fmt_plate = clean_plate
    if clean_plate.isdigit():
        if len(clean_plate) == 7:
            fmt_plate = f"{clean_plate[:2]}-{clean_plate[2:5]}-{clean_plate[5:]}"
        elif len(clean_plate) == 8:
            fmt_plate = f"{clean_plate[:3]}-{clean_plate[3:5]}-{clean_plate[5:]}"

    return jsonify({
        'success': True,
        'plate': clean_plate,
        'formatted_plate': fmt_plate,
        'is_subscriber': sub_res.get('is_subscriber', False),
        'has_active_ticket': bool(trans_res and trans_res.get('found')),
        'vehicle': sub_res,
        'ticket_payment': trans_res
    })
