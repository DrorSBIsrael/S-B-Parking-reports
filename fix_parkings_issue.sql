-- ================================================
-- בדיקה ותיקון בעיית החניונים
-- ================================================

-- 1. בדיקת המשתמש שלך
-- ----------------------
SELECT 
    username,
    email,
    project_number,
    company_list,
    permissions,
    access_level
FROM user_parkings
WHERE email LIKE '%@%'  -- כל המשתמשים עם אימייל
LIMIT 5;

-- 2. בדיקת חניונים קיימים
-- ------------------------
SELECT 
    id,
    name,
    description as project_number,
    ip_address,
    port,
    is_active
FROM parkings;

-- 3. בדיקת התאמה
-- --------------
SELECT 
    'משתמש' as type,
    u.username,
    u.project_number as user_project,
    u.company_list
FROM user_parkings u
WHERE u.email IS NOT NULL
UNION ALL
SELECT 
    'חניון' as type,
    p.name,
    p.description::text as project,
    'N/A' as company_list
FROM parkings p;

-- ================================================
-- 4. אם אין חניונים - הוסף חניונים לדוגמה
-- ================================================

-- חניון לבדיקות (project_number = 1000)
INSERT INTO parkings (
    name,
    location,
    description,  -- זה ה-project_number
    ip_address,
    port,
    is_active
) VALUES 
(
    'חניון בדיקות',
    'תל אביב',
    1000,  -- תואם ל-company_list שלך
    '10.35.152.100',
    8443,
    true
),
(
    'חניון ראשי',
    'ירושלים', 
    2,  -- תואם ל-company_list שלך
    '10.35.152.101',
    8443,
    true
)
ON CONFLICT DO NOTHING;

-- 5. עדכון משתמש לדוגמה (אם צריך)
-- --------------------------------
-- אם אתה רוצה לעדכן את המשתמש שלך:
UPDATE user_parkings
SET 
    company_list = '1,2,1000',  -- מוסיף גישה לחניונים 1,2,1000
    permissions = 'G,N,R,P',     -- כל ההרשאות
    access_level = 'company_manager'
WHERE username = 'YOUR_USERNAME';  -- החלף ב-username שלך

-- 6. בדיקה סופית
-- --------------
SELECT 
    u.username,
    u.company_list,
    u.permissions,
    p.name as parking_name,
    p.description as parking_project_number,
    CASE 
        WHEN p.description::text = ANY(string_to_array(u.company_list, ','))
        THEN 'יש גישה ✅'
        ELSE 'אין גישה ❌'
    END as access_status
FROM user_parkings u
CROSS JOIN parkings p
WHERE u.email IS NOT NULL
ORDER BY u.username, p.name;

