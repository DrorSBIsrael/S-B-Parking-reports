-- סקריפט מיגרציה לעדכון בסיס הנתונים הקיים
-- ============================================

-- שים לב: הרץ סקריפט זה רק אם יש לך בסיס נתונים קיים!

-- 1. שינוי סוג העמודה project_number בטבלת user_parkings
ALTER TABLE user_parkings 
ALTER COLUMN project_number TYPE BIGINT USING project_number::BIGINT;

-- 2. שינוי שם הטבלה מ-parking_lots ל-parkings
ALTER TABLE parking_lots RENAME TO parkings;

-- 3. שינוי סוג העמודה description בטבלת parkings
ALTER TABLE parkings 
ALTER COLUMN description TYPE BIGINT USING description::BIGINT;

-- 4. עדכון האינדקסים
DROP INDEX IF EXISTS idx_parking_lots_name;
DROP INDEX IF EXISTS idx_parking_lots_description;

CREATE INDEX idx_parkings_name ON parkings(name);
CREATE INDEX idx_parkings_description ON parkings(description);

-- 5. הוספת Foreign Key Constraint (אופציונלי)
-- אם אתה רוצה לאכוף קשר בין הטבלאות
-- ALTER TABLE parkings 
-- ADD CONSTRAINT fk_parkings_project_number 
-- FOREIGN KEY (description) 
-- REFERENCES user_parkings(project_number);

-- 6. בדיקה שהמיגרציה הצליחה
DO $$
BEGIN
    -- בדיקת טבלת user_parkings
    IF EXISTS (SELECT 1 FROM information_schema.columns 
               WHERE table_name = 'user_parkings' 
               AND column_name = 'project_number' 
               AND data_type = 'bigint') THEN
        RAISE NOTICE '✅ user_parkings.project_number converted to BIGINT successfully';
    ELSE
        RAISE WARNING '⚠️ user_parkings.project_number type conversion failed';
    END IF;
    
    -- בדיקת טבלת parkings
    IF EXISTS (SELECT 1 FROM information_schema.tables 
               WHERE table_name = 'parkings') THEN
        RAISE NOTICE '✅ Table renamed to parkings successfully';
    ELSE
        RAISE WARNING '⚠️ Table rename to parkings failed';
    END IF;
    
    -- בדיקת עמודת description
    IF EXISTS (SELECT 1 FROM information_schema.columns 
               WHERE table_name = 'parkings' 
               AND column_name = 'description' 
               AND data_type = 'bigint') THEN
        RAISE NOTICE '✅ parkings.description converted to BIGINT successfully';
    ELSE
        RAISE WARNING '⚠️ parkings.description type conversion failed';
    END IF;
END $$;

