-- ================================================
-- תיקון בעיית ההתאמה בין company_list ל-parkings
-- ================================================

-- הבעיה: 
-- company_list = '2,1000'
-- אבל description בחניון = 478131051
-- לכן אין התאמה!

-- ================================================
-- פתרון 1: עדכון company_list כך שיכלול את החניון
-- ================================================
UPDATE user_parkings
SET company_list = '2,1000,478131051'  -- מוסיף את מספר הפרויקט
WHERE username = 'DrorParking';

-- או אם רוצים גישה לכל החניונים:
-- UPDATE user_parkings
-- SET company_list = '1-500000000'  -- טווח ענק שיכלול הכל
-- WHERE username = 'DrorParking';

-- ================================================
-- פתרון 2 (חלופי): שינוי description של החניון
-- ================================================
-- UPDATE parkings
-- SET description = 1000  -- משנה למספר שכבר ב-company_list
-- WHERE name = 'שיידט בדיקות';

-- ================================================
-- בדיקה שהתיקון עובד
-- ================================================
SELECT 
    u.username,
    u.company_list,
    u.project_number as user_project,
    p.name as parking_name,
    p.description as parking_project,
    CASE 
        WHEN p.description::text = '2' 
          OR p.description::text = '1000' 
          OR p.description::text = '478131051'
        THEN '✅ יש גישה'
        ELSE '❌ אין גישה'
    END as access_status
FROM user_parkings u
CROSS JOIN parkings p
WHERE u.username = 'DrorParking';

