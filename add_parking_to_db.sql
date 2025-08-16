-- הוספת החניון לטבלת parkings
-- ============================================

-- 1. בדיקה אם החניון כבר קיים
SELECT * FROM parkings WHERE description = 478131051;

-- 2. אם לא קיים, הוסף את החניון
INSERT INTO parkings (
    id,
    name,
    location,
    address,
    description,  -- זה ה-project_number (478131051)
    ip_address,
    port,
    is_active,
    created_at,
    updated_at
) VALUES (
    gen_random_uuid(),
    'שיידט בדיקות',
    'תל אביב',
    'רחוב הבדיקות 1',
    478131051,  -- BIGINT - מספר הפרויקט
    '10.35.240.100',
    8240,
    true,
    NOW(),
    NOW()
) ON CONFLICT DO NOTHING;

-- 3. אימות שהחניון נוסף
SELECT 
    id,
    name,
    description as project_number,
    ip_address,
    port,
    is_active
FROM parkings 
WHERE description = 478131051;

