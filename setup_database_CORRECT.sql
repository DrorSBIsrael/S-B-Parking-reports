-- ================================================
-- SQL מתוקן למבנה הקיים של בסיס הנתונים
-- ================================================
-- זה הקובץ הנכון שמתאים למה שיש לך בפועל!

-- 1. טבלת משתמשים (user_parkings) - כבר קיימת!
-- מבנה נכון עם BIGINT ל-project_number
CREATE TABLE IF NOT EXISTS user_parkings (
    user_id SERIAL PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    email TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT DEFAULT 'user',
    project_number BIGINT,  -- נכון! BIGINT
    parking_name TEXT,
    company_type TEXT,
    access_level TEXT DEFAULT 'single_parking',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    verification_code VARCHAR(10),
    code_expires_at TIMESTAMP,
    code_type VARCHAR(50),
    company_list TEXT,
    password_changed_at TIMESTAMP,
    password_expires_at TIMESTAMP,
    is_temp_password BOOLEAN DEFAULT FALSE,
    permissions VARCHAR(50)
);

-- 2. טבלת חניונים (parkings) - לא parking_lots!
-- מבנה נכון עם BIGINT ל-description
CREATE TABLE IF NOT EXISTS parkings (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    location VARCHAR(255),
    address TEXT,
    capacity INTEGER,
    client_logo_url TEXT,
    settings JSONB DEFAULT '{}',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    description BIGINT,  -- נכון! BIGINT שמקושר ל-project_number
    ip_address VARCHAR(50),
    port INTEGER,
    future_code VARCHAR(100)
);

-- 3. טבלת נתוני חניה (כבר קיימת אצלך)
CREATE TABLE IF NOT EXISTS parking_data (
    id SERIAL PRIMARY KEY,
    parking_id TEXT,
    entry_date DATE,
    entry_time TIME,
    exit_date DATE,
    exit_time TIME,
    duration_hours NUMERIC(10,2),
    duration_minutes INTEGER,
    amount NUMERIC(10,2),
    card_number TEXT,
    driver_name TEXT,
    car_number TEXT,
    parking_name TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    project_number BIGINT,
    transaction_date DATE,
    transaction_type TEXT,
    record_type TEXT
);

-- 4. טבלת מיפוי (כבר קיימת אצלך)
CREATE TABLE IF NOT EXISTS project_parking_mapping (
    id SERIAL PRIMARY KEY,
    project_number BIGINT,
    parking_name TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 5. אינדקסים לביצועים מיטביים
CREATE INDEX IF NOT EXISTS idx_user_parkings_username ON user_parkings(username);
CREATE INDEX IF NOT EXISTS idx_user_parkings_email ON user_parkings(email);
CREATE INDEX IF NOT EXISTS idx_user_parkings_project_number ON user_parkings(project_number);
CREATE INDEX IF NOT EXISTS idx_user_parkings_company_type ON user_parkings(company_type);

CREATE INDEX IF NOT EXISTS idx_parkings_name ON parkings(name);
CREATE INDEX IF NOT EXISTS idx_parkings_description ON parkings(description);
CREATE INDEX IF NOT EXISTS idx_parkings_is_active ON parkings(is_active);

CREATE INDEX IF NOT EXISTS idx_parking_data_project_number ON parking_data(project_number);
CREATE INDEX IF NOT EXISTS idx_parking_data_parking_id ON parking_data(parking_id);
CREATE INDEX IF NOT EXISTS idx_parking_data_transaction_date ON parking_data(transaction_date);

-- 6. Extensions נדרשות
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 7. פונקציות RPC בסיסיות

-- פונקציה לבדיקת התחברות
CREATE OR REPLACE FUNCTION user_login(
    p_username TEXT,
    p_password TEXT
)
RETURNS JSON
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_user RECORD;
BEGIN
    -- חיפוש המשתמש
    SELECT * INTO v_user 
    FROM user_parkings 
    WHERE username = p_username;
    
    IF NOT FOUND THEN
        RETURN json_build_object(
            'success', FALSE, 
            'message', 'שם משתמש או סיסמה שגויים'
        );
    END IF;
    
    -- בדיקת סיסמה עם bcrypt
    IF NOT (v_user.password_hash = crypt(p_password, v_user.password_hash)) THEN
        RETURN json_build_object(
            'success', FALSE, 
            'message', 'שם משתמש או סיסמה שגויים'
        );
    END IF;
    
    -- החזרת פרטי המשתמש
    RETURN json_build_object(
        'success', TRUE,
        'user_data', json_build_object(
            'user_id', v_user.user_id,
            'username', v_user.username,
            'email', v_user.email,
            'role', v_user.role,
            'project_number', v_user.project_number,
            'parking_name', v_user.parking_name,
            'company_type', v_user.company_type,
            'access_level', v_user.access_level,
            'company_list', v_user.company_list,
            'permissions', v_user.permissions,
            'is_temp_password', v_user.is_temp_password
        )
    );
END;
$$;

-- פונקציה לשינוי סיסמה
CREATE OR REPLACE FUNCTION change_user_password(
    p_username TEXT,
    p_old_password TEXT,
    p_new_password TEXT
)
RETURNS JSON
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_user RECORD;
BEGIN
    -- בדיקת משתמש
    SELECT * INTO v_user 
    FROM user_parkings 
    WHERE username = p_username;
    
    IF NOT FOUND THEN
        RETURN json_build_object(
            'success', FALSE, 
            'message', 'משתמש לא נמצא'
        );
    END IF;
    
    -- בדיקת סיסמה ישנה
    IF NOT (v_user.password_hash = crypt(p_old_password, v_user.password_hash)) THEN
        RETURN json_build_object(
            'success', FALSE, 
            'message', 'סיסמה ישנה שגויה'
        );
    END IF;
    
    -- עדכון הסיסמה החדשה
    UPDATE user_parkings 
    SET 
        password_hash = crypt(p_new_password, gen_salt('bf')),
        password_changed_at = NOW(),
        password_expires_at = NOW() + INTERVAL '90 days',
        is_temp_password = FALSE,
        updated_at = NOW()
    WHERE username = p_username;
    
    RETURN json_build_object(
        'success', TRUE, 
        'message', 'סיסמה שונתה בהצלחה'
    );
END;
$$;

-- פונקציה לאיפוס סיסמה על ידי מאסטר
CREATE OR REPLACE FUNCTION master_reset_password(
    p_username TEXT,
    p_new_password TEXT,
    p_reset_by TEXT
)
RETURNS JSON
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    -- בדיקה שהמאפס הוא מאסטר
    IF NOT EXISTS (
        SELECT 1 FROM user_parkings 
        WHERE username = p_reset_by 
        AND (code_type = 'master' OR access_level = 'master')
    ) THEN
        RETURN json_build_object(
            'success', FALSE,
            'message', 'אין הרשאה לאפס סיסמה'
        );
    END IF;
    
    -- עדכון הסיסמה
    UPDATE user_parkings 
    SET 
        password_hash = crypt(p_new_password, gen_salt('bf')),
        is_temp_password = TRUE,
        password_changed_at = NOW(),
        password_expires_at = NOW() + INTERVAL '7 days',
        updated_at = NOW()
    WHERE username = p_username;
    
    IF NOT FOUND THEN
        RETURN json_build_object(
            'success', FALSE,
            'message', 'משתמש לא נמצא'
        );
    END IF;
    
    RETURN json_build_object(
        'success', TRUE,
        'message', 'סיסמה אופסה בהצלחה'
    );
END;
$$;

-- 8. Views שימושיות

-- View לקישור משתמשים וחניונים
CREATE OR REPLACE VIEW v_user_parking_full AS
SELECT 
    u.user_id,
    u.username,
    u.email,
    u.role,
    u.access_level,
    u.project_number,
    u.parking_name as assigned_parking,
    u.company_type,
    u.permissions,
    p.id as parking_uuid,
    p.name as parking_name,
    p.location,
    p.ip_address,
    p.port,
    p.is_active as parking_active
FROM user_parkings u
LEFT JOIN parkings p ON u.project_number = p.description
WHERE u.project_number IS NOT NULL;

-- 9. Policies בסיסיות (אופציונלי - הפעל רק אם צריך)
-- ALTER TABLE user_parkings ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE parkings ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE parking_data ENABLE ROW LEVEL SECURITY;

