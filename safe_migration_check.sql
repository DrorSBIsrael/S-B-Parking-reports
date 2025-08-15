-- ================================================
-- סקריפט בדיקה בטוח לפני שינויים
-- ================================================
-- הרץ את זה ב-Supabase SQL Editor כדי לבדוק מה המצב

-- 1. בדיקת טבלאות קיימות
-- -------------------------
SELECT '=== טבלאות קיימות ===' as info;
SELECT table_name, 
       (SELECT COUNT(*) FROM information_schema.columns 
        WHERE c.table_name = t.table_name) as column_count
FROM information_schema.tables t
WHERE table_schema = 'public' 
AND table_name IN ('user_parkings', 'parkings', 'parking_lots', 'parking_data')
ORDER BY table_name;

-- 2. בדיקת מבנה user_parkings
-- ----------------------------
SELECT '=== מבנה user_parkings ===' as info;
SELECT column_name, 
       data_type,
       CASE 
           WHEN data_type = 'character varying' THEN 'VARCHAR(' || character_maximum_length || ')'
           WHEN data_type = 'bigint' THEN 'BIGINT (INT8)'
           WHEN data_type = 'integer' THEN 'INTEGER (INT4)'
           ELSE data_type
       END as readable_type,
       is_nullable
FROM information_schema.columns
WHERE table_name = 'user_parkings' 
AND column_name IN ('user_id', 'project_number', 'company_list', 'permissions', 'password_hash')
ORDER BY ordinal_position;

-- 3. בדיקת מבנה parkings
-- -----------------------
SELECT '=== מבנה parkings ===' as info;
SELECT column_name, 
       data_type,
       CASE 
           WHEN data_type = 'character varying' THEN 'VARCHAR(' || character_maximum_length || ')'
           WHEN data_type = 'bigint' THEN 'BIGINT (INT8)'
           WHEN data_type = 'integer' THEN 'INTEGER (INT4)'
           ELSE data_type
       END as readable_type,
       is_nullable
FROM information_schema.columns
WHERE table_name = 'parkings'
AND column_name IN ('id', 'description', 'ip_address', 'port', 'name')
ORDER BY ordinal_position;

-- 4. בדיקת נתונים לדוגמה
-- ------------------------
SELECT '=== דוגמה מ-user_parkings ===' as info;
SELECT username, 
       project_number,
       CASE 
           WHEN project_number ~ '^[0-9]+$' THEN 'מספר בלבד - ניתן להמיר ל-BIGINT'
           ELSE 'מכיל תווים - בעיה בהמרה!'
       END as conversion_check
FROM user_parkings
LIMIT 3;

SELECT '=== דוגמה מ-parkings ===' as info;
SELECT name, 
       description,
       ip_address,
       port
FROM parkings
LIMIT 3;

-- 5. בדיקת התאמה בין הטבלאות
-- ----------------------------
SELECT '=== בדיקת קישור בין הטבלאות ===' as info;
SELECT 
    COUNT(DISTINCT u.project_number) as unique_user_projects,
    COUNT(DISTINCT p.description) as unique_parking_descriptions,
    COUNT(DISTINCT u.project_number) FILTER (
        WHERE EXISTS (
            SELECT 1 FROM parkings p2 
            WHERE p2.description::text = u.project_number::text
        )
    ) as matching_projects
FROM user_parkings u
CROSS JOIN parkings p
LIMIT 1;

-- 6. בדיקת אינדקסים קיימים
-- --------------------------
SELECT '=== אינדקסים קיימים ===' as info;
SELECT indexname, tablename, indexdef
FROM pg_indexes
WHERE schemaname = 'public'
AND tablename IN ('user_parkings', 'parkings')
ORDER BY tablename, indexname;

-- 7. בדיקת פונקציות RPC
-- -----------------------
SELECT '=== פונקציות RPC קיימות ===' as info;
SELECT routine_name
FROM information_schema.routines
WHERE routine_schema = 'public'
AND routine_name IN ('user_login', 'change_user_password', 'master_reset_password')
ORDER BY routine_name;

-- 8. סיכום והמלצות
-- -----------------
SELECT '=== סיכום ===' as info;
SELECT 
    'בדוק את התוצאות למעלה:' as message
UNION ALL
SELECT '1. אם project_number הוא VARCHAR וכל הערכים מספריים - אפשר להמיר ל-BIGINT'
UNION ALL
SELECT '2. אם description הוא VARCHAR וכל הערכים מספריים - אפשר להמיר ל-BIGINT'
UNION ALL
SELECT '3. אם יש התאמות בין project_number ל-description - הקישור יעבוד'
UNION ALL
SELECT '4. אם חסרים אינדקסים - כדאי להוסיף לביצועים טובים יותר';

