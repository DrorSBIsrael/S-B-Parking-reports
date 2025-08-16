-- ================================================
-- הוספת אינדקסים חסרים בלבד - לשיפור ביצועים
-- ================================================
-- הרץ רק אם אתה חווה בעיות ביצועים

-- 1. אינדקסים חסרים לטבלת parkings (חשובים!)
-- ---------------------------------------------
-- אינדקס על description - חשוב לקישור עם user_parkings
CREATE INDEX IF NOT EXISTS idx_parkings_description 
ON parkings(description);

-- אינדקס על name - לחיפוש מהיר לפי שם חניון
CREATE INDEX IF NOT EXISTS idx_parkings_name 
ON parkings(name);

-- אינדקס על is_active - לסינון חניונים פעילים
CREATE INDEX IF NOT EXISTS idx_parkings_is_active 
ON parkings(is_active);

-- אינדקס משולב לחיפושים נפוצים
CREATE INDEX IF NOT EXISTS idx_parkings_active_description 
ON parkings(is_active, description) 
WHERE is_active = true;

-- 2. אינדקסים נוספים לטבלת user_parkings (אופציונלי)
-- ---------------------------------------------------
-- אינדקס על company_type - אם מחפשים הרבה לפי חברה
CREATE INDEX IF NOT EXISTS idx_user_parkings_company_type 
ON user_parkings(company_type);

-- אינדקס על access_level - לסינון לפי רמת גישה
CREATE INDEX IF NOT EXISTS idx_user_parkings_access_level 
ON user_parkings(access_level);

-- אינדקס משולב לבדיקות הרשאה
CREATE INDEX IF NOT EXISTS idx_user_parkings_access_project 
ON user_parkings(access_level, project_number);

-- 3. אינדקסים לטבלת parking_data (אם משתמשים בה הרבה)
-- ------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_parking_data_project_number 
ON parking_data(project_number);

CREATE INDEX IF NOT EXISTS idx_parking_data_transaction_date 
ON parking_data(transaction_date);

CREATE INDEX IF NOT EXISTS idx_parking_data_parking_id 
ON parking_data(parking_id);

-- אינדקס משולב לדוחות
CREATE INDEX IF NOT EXISTS idx_parking_data_project_date 
ON parking_data(project_number, transaction_date);

-- 4. בדיקה שהאינדקסים נוצרו
-- --------------------------
SELECT 
    'אינדקסים חדשים שנוספו:' as status,
    COUNT(*) as new_indexes_count
FROM pg_indexes 
WHERE schemaname = 'public' 
AND tablename IN ('user_parkings', 'parkings', 'parking_data')
AND indexname LIKE 'idx_%';

