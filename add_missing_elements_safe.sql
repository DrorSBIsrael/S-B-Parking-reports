-- ================================================
-- סקריפט להוספת אלמנטים חסרים בלבד
-- ================================================
-- זהירות: הרץ כל חלק בנפרד ובדוק שאין שגיאות

-- =====================================
-- חלק 1: אינדקסים (לביצועים טובים יותר)
-- =====================================

-- אינדקסים לטבלת user_parkings
CREATE INDEX IF NOT EXISTS idx_user_parkings_username ON user_parkings(username);
CREATE INDEX IF NOT EXISTS idx_user_parkings_email ON user_parkings(email);
CREATE INDEX IF NOT EXISTS idx_user_parkings_project_number ON user_parkings(project_number);
CREATE INDEX IF NOT EXISTS idx_user_parkings_company_type ON user_parkings(company_type);
CREATE INDEX IF NOT EXISTS idx_user_parkings_access_level ON user_parkings(access_level);

-- אינדקסים לטבלת parkings
CREATE INDEX IF NOT EXISTS idx_parkings_name ON parkings(name);
CREATE INDEX IF NOT EXISTS idx_parkings_description ON parkings(description);
CREATE INDEX IF NOT EXISTS idx_parkings_is_active ON parkings(is_active);

-- אינדקס לקישור בין הטבלאות
CREATE INDEX IF NOT EXISTS idx_parkings_description_btree ON parkings USING btree(description);
CREATE INDEX IF NOT EXISTS idx_user_parkings_project_number_btree ON user_parkings USING btree(project_number);

-- =====================================
-- חלק 2: Extensions (אם לא קיימות)
-- =====================================

-- Extension להצפנה (כנראה כבר קיימת)
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Extension ל-UUID (כנראה כבר קיימת)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- =====================================
-- חלק 3: פונקציות RPC בסיסיות
-- =====================================

-- פונקציה לבדיקת משתמש (אם לא קיימת)
CREATE OR REPLACE FUNCTION check_user_exists(p_username TEXT)
RETURNS BOOLEAN
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN EXISTS (
        SELECT 1 FROM user_parkings 
        WHERE username = p_username
    );
END;
$$;

-- פונקציה לקבלת פרטי חניון לפי project_number
CREATE OR REPLACE FUNCTION get_parking_by_project(p_project_number BIGINT)
RETURNS TABLE (
    parking_id UUID,
    parking_name VARCHAR,
    parking_location VARCHAR,
    ip_address VARCHAR,
    port INTEGER,
    is_active BOOLEAN
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT 
        p.id,
        p.name,
        p.location,
        p.ip_address,
        p.port,
        p.is_active
    FROM parkings p
    WHERE p.description = p_project_number;
END;
$$;

-- פונקציה לקבלת משתמשים לפי חניון
CREATE OR REPLACE FUNCTION get_users_by_parking(p_project_number BIGINT)
RETURNS TABLE (
    user_id INTEGER,
    username TEXT,
    email TEXT,
    role TEXT,
    access_level TEXT
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT 
        u.user_id,
        u.username,
        u.email,
        u.role,
        u.access_level
    FROM user_parkings u
    WHERE u.project_number = p_project_number;
END;
$$;

-- =====================================
-- חלק 4: Policies לאבטחה (אופציונלי)
-- =====================================

-- הפעלת Row Level Security (אם רוצים)
-- ALTER TABLE user_parkings ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE parkings ENABLE ROW LEVEL SECURITY;

-- =====================================
-- חלק 5: Views שימושיות (אופציונלי)
-- =====================================

-- View לקישור בין משתמשים לחניונים
CREATE OR REPLACE VIEW v_user_parking_details AS
SELECT 
    u.user_id,
    u.username,
    u.email,
    u.role,
    u.access_level,
    u.project_number,
    u.parking_name as user_parking_name,
    u.company_type,
    p.id as parking_id,
    p.name as parking_name,
    p.location,
    p.ip_address,
    p.port,
    p.is_active
FROM user_parkings u
LEFT JOIN parkings p ON u.project_number = p.description;

-- View לסטטיסטיקות
CREATE OR REPLACE VIEW v_parking_stats AS
SELECT 
    p.name as parking_name,
    p.description as project_number,
    p.is_active,
    COUNT(DISTINCT u.user_id) as user_count,
    COUNT(DISTINCT u.company_type) as company_count
FROM parkings p
LEFT JOIN user_parkings u ON p.description = u.project_number
GROUP BY p.id, p.name, p.description, p.is_active;

-- =====================================
-- סיום - בדיקת תקינות
-- =====================================

-- הרץ את זה כדי לוודא שהכל עובד
SELECT 'בדיקת אינדקסים' as test, COUNT(*) as count 
FROM pg_indexes 
WHERE tablename IN ('user_parkings', 'parkings');

SELECT 'בדיקת פונקציות' as test, COUNT(*) as count 
FROM information_schema.routines 
WHERE routine_schema = 'public';

SELECT 'בדיקת Views' as test, COUNT(*) as count 
FROM information_schema.views 
WHERE table_schema = 'public';

