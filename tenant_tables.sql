-- ============================================================================
-- S&B Parking Reports - Tenant Parking Sharing System Tables (Supabase / PostgreSQL)
-- ============================================================================

-- 1. הגדרות מתחם מגורים (מכסות יומיות/חודשיות והתראות)
CREATE TABLE IF NOT EXISTS public.tenant_building_settings (
    project_number TEXT PRIMARY KEY,
    parking_name TEXT,
    max_bookings_per_day INTEGER DEFAULT 5,
    max_bookings_per_month INTEGER DEFAULT 30,
    check_interval_minutes INTEGER DEFAULT 30,
    reminder_minutes_before INTEGER DEFAULT 30,
    logo_data TEXT,
    parking_lat DOUBLE PRECISION,
    parking_lng DOUBLE PRECISION,
    parking_address TEXT,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2. טבלת דיירי הבניין (כניסה באמצעות טלפון ווואטסאפ בלבד - ללא מייל)
CREATE TABLE IF NOT EXISTS public.tenant_users (
    id BIGSERIAL PRIMARY KEY,
    project_number TEXT NOT NULL,
    parking_name TEXT,
    full_name TEXT NOT NULL,
    phone_number TEXT NOT NULL,
    apartment_number TEXT NOT NULL,
    base_max_counter INTEGER DEFAULT 1,
    mobile_otp TEXT,
    otp_expires_at TIMESTAMPTZ,
    is_active BOOLEAN DEFAULT TRUE,
    created_by TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tenant_users_phone ON public.tenant_users (phone_number);
CREATE INDEX IF NOT EXISTS idx_tenant_users_project_apt ON public.tenant_users (project_number, apartment_number);

-- 3. טבלת שחרורי חניות ע"י דיירים (לפי ימים ושעות, לפול כללי או לדירה ספציפית)
CREATE TABLE IF NOT EXISTS public.tenant_spot_shares (
    id BIGSERIAL PRIMARY KEY,
    project_number TEXT NOT NULL,
    owner_tenant_id BIGINT,
    owner_name TEXT,
    owner_apartment TEXT NOT NULL,
    spots_offered INTEGER DEFAULT 1,
    share_target_type TEXT DEFAULT 'POOL', -- 'POOL' או 'APT'
    target_apartment TEXT,
    schedule_type TEXT DEFAULT 'WEEKLY',   -- 'WEEKLY' או 'ONCE'
    days_of_week TEXT,                     -- למשל '1,3' (0=ראשון .. 6=שבת)
    specific_date TEXT,                    -- YYYY-MM-DD עבור 'ONCE'
    start_time TEXT NOT NULL,              -- HH:MM
    end_time TEXT NOT NULL,                -- HH:MM
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tenant_shares_project ON public.tenant_spot_shares (project_number, is_active);

-- 4. טבלת הזמנות חניה והעברות מונה (maxCounter) בפועל
CREATE TABLE IF NOT EXISTS public.tenant_quota_transfers (
    id BIGSERIAL PRIMARY KEY,
    share_id BIGINT NOT NULL,
    slot_index INTEGER DEFAULT 1,
    project_number TEXT NOT NULL,
    from_apartment TEXT NOT NULL,
    to_apartment TEXT NOT NULL,
    borrower_tenant_id BIGINT,
    borrower_name TEXT,
    borrower_phone TEXT,
    booking_date TEXT NOT NULL,            -- YYYY-MM-DD
    start_time TEXT NOT NULL,              -- HH:MM
    end_time TEXT NOT NULL,                -- HH:MM
    window_start TIMESTAMPTZ NOT NULL,
    window_end TIMESTAMPTZ NOT NULL,
    status TEXT DEFAULT 'SCHEDULED',       -- 'SCHEDULED', 'WAITING_FOR_EXIT', 'ACTIVE', 'RESTORED', 'CANCELLED', 'EXPIRED'
    actual_activated_at TIMESTAMPTZ,
    actual_restored_at TIMESTAMPTZ,
    last_checked_at TIMESTAMPTZ,
    notified_start BOOLEAN DEFAULT FALSE,
    notified_ending_soon BOOLEAN DEFAULT FALSE,
    late_exit_flag BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tenant_transfers_project_date ON public.tenant_quota_transfers (project_number, booking_date);
CREATE INDEX IF NOT EXISTS idx_tenant_transfers_status ON public.tenant_quota_transfers (status);

-- הוספת עמודות לוגו וקואורדינטות חניון אם הטבלה כבר קיימת:
ALTER TABLE public.tenant_building_settings ADD COLUMN IF NOT EXISTS logo_data TEXT;
ALTER TABLE public.tenant_building_settings ADD COLUMN IF NOT EXISTS parking_lat DOUBLE PRECISION;
ALTER TABLE public.tenant_building_settings ADD COLUMN IF NOT EXISTS parking_lng DOUBLE PRECISION;
ALTER TABLE public.tenant_building_settings ADD COLUMN IF NOT EXISTS parking_address TEXT;
