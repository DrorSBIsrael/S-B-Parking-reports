-- ================================================
-- בדיקת אלמנטים חסרים בבסיס הנתונים
-- ================================================

-- 1. בדיקת אינדקסים קיימים
-- --------------------------
SELECT '=== אינדקסים קיימים ===' as check_type;
SELECT 
    indexname,
    tablename,
    indexdef
FROM pg_indexes
WHERE schemaname = 'public'
AND tablename IN ('user_parkings', 'parkings')
ORDER BY tablename, indexname;

-- 2. בדיקת פונקציות RPC קיימות
-- -------------------------------
SELECT '=== פונקציות RPC ===' as check_type;
SELECT 
    routine_name,
    routine_type
FROM information_schema.routines
WHERE routine_schema = 'public'
ORDER BY routine_name;

-- 3. בדיקת Foreign Keys
-- ----------------------
SELECT '=== Foreign Keys ===' as check_type;
SELECT
    tc.table_name, 
    kcu.column_name, 
    ccu.table_name AS foreign_table_name,
    ccu.column_name AS foreign_column_name 
FROM 
    information_schema.table_constraints AS tc 
    JOIN information_schema.key_column_usage AS kcu
      ON tc.constraint_name = kcu.constraint_name
    JOIN information_schema.constraint_column_usage AS ccu
      ON ccu.constraint_name = tc.constraint_name
WHERE tc.constraint_type = 'FOREIGN KEY' 
AND tc.table_schema = 'public';

-- 4. בדיקת Extensions
-- --------------------
SELECT '=== Extensions ===' as check_type;
SELECT extname, extversion 
FROM pg_extension 
WHERE extname IN ('pgcrypto', 'uuid-ossp');

-- 5. ספירת רשומות
-- ---------------
SELECT '=== כמות רשומות ===' as check_type;
SELECT 'user_parkings' as table_name, COUNT(*) as count FROM user_parkings
UNION ALL
SELECT 'parkings', COUNT(*) FROM parkings
UNION ALL
SELECT 'parking_data', COUNT(*) FROM parking_data
UNION ALL
SELECT 'project_parking_mapping', COUNT(*) FROM project_parking_mapping;

-- 6. בדיקת התאמה בין הטבלאות
-- ---------------------------
SELECT '=== בדיקת קישור ===' as check_type;
WITH user_projects AS (
    SELECT DISTINCT project_number 
    FROM user_parkings 
    WHERE project_number IS NOT NULL
),
parking_descriptions AS (
    SELECT DISTINCT description 
    FROM parkings 
    WHERE description IS NOT NULL
)
SELECT 
    (SELECT COUNT(*) FROM user_projects) as unique_user_projects,
    (SELECT COUNT(*) FROM parking_descriptions) as unique_parking_descriptions,
    (SELECT COUNT(*) 
     FROM user_projects u 
     WHERE EXISTS (
         SELECT 1 FROM parking_descriptions p 
         WHERE p.description = u.project_number
     )) as matching_records;

