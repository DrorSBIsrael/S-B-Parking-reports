-- סקריפט SQL לבדיקת מבנה בסיס הנתונים
-- =====================================
-- הרץ את השאילתות האלו ב-Supabase SQL Editor

-- 1. בדיקת טבלאות קיימות
SELECT table_name 
FROM information_schema.tables 
WHERE table_schema = 'public'
ORDER BY table_name;

-- 2. בדיקת מבנה טבלת user_parkings
SELECT 
    column_name,
    data_type,
    character_maximum_length,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_name = 'user_parkings'
ORDER BY ordinal_position;

-- 3. בדיקת מבנה טבלת parkings (אם קיימת)
SELECT 
    column_name,
    data_type,
    character_maximum_length,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_name = 'parkings'
ORDER BY ordinal_position;

-- 4. בדיקת מבנה טבלת parking_lots (אם קיימת)
SELECT 
    column_name,
    data_type,
    character_maximum_length,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_name = 'parking_lots'
ORDER BY ordinal_position;

-- 5. בדיקת אינדקסים קיימים
SELECT 
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'public'
ORDER BY tablename, indexname;

-- 6. בדיקת פונקציות קיימות
SELECT 
    routine_name,
    routine_type,
    data_type
FROM information_schema.routines
WHERE routine_schema = 'public'
ORDER BY routine_name;

-- 7. בדיקת Foreign Keys
SELECT
    tc.table_name, 
    kcu.column_name, 
    ccu.table_name AS foreign_table_name,
    ccu.column_name AS foreign_column_name 
FROM 
    information_schema.table_constraints AS tc 
    JOIN information_schema.key_column_usage AS kcu
      ON tc.constraint_name = kcu.constraint_name
      AND tc.table_schema = kcu.table_schema
    JOIN information_schema.constraint_column_usage AS ccu
      ON ccu.constraint_name = tc.constraint_name
      AND ccu.table_schema = tc.table_schema
WHERE tc.constraint_type = 'FOREIGN KEY' 
AND tc.table_schema = 'public';

-- 8. ספירת רשומות בטבלאות
SELECT 'user_parkings' as table_name, COUNT(*) as row_count FROM user_parkings
UNION ALL
SELECT 'parkings', COUNT(*) FROM parkings
UNION ALL
SELECT 'parking_lots', COUNT(*) FROM parking_lots;

