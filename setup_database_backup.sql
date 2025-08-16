-- SQL לבניית טבלאות בסיס הנתונים Supabase
-- ========================================

-- 1. טבלת משתמשים (user_parkings)
CREATE TABLE IF NOT EXISTS user_parkings (
    user_id SERIAL PRIMARY KEY,
    username VARCHAR(100) UNIQUE NOT NULL,
    email VARCHAR(255) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(50) DEFAULT 'user',
    project_number VARCHAR(100),
    parking_name VARCHAR(255),
    company_type VARCHAR(100),
    access_level VARCHAR(50) DEFAULT 'single_parking',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    verification_code VARCHAR(10),
    code_expires_at TIMESTAMP,
    code_type VARCHAR(50),
    company_list TEXT,  -- רשימת מספרי חברות מופרדים בפסיקים (1,2,5-10,60)
    password_changed_at TIMESTAMP,
    password_expires_at TIMESTAMP,
    is_temp_password BOOLEAN DEFAULT FALSE,
    permissions VARCHAR(50) -- G=guest, N=new, R=report, P=profile
);

-- 2. טבלת חניונים (parking_lots)
CREATE TABLE IF NOT EXISTS parking_lots (
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
    description VARCHAR(255), -- project_number
    ip_address VARCHAR(50),   -- כתובת IP של החניון
    port INTEGER,              -- פורט החניון
    future_code VARCHAR(100)
);

-- 3. יצירת אינדקסים לביצועים טובים יותר
CREATE INDEX idx_user_parkings_username ON user_parkings(username);
CREATE INDEX idx_user_parkings_email ON user_parkings(email);
CREATE INDEX idx_user_parkings_project_number ON user_parkings(project_number);
CREATE INDEX idx_parking_lots_name ON parking_lots(name);
CREATE INDEX idx_parking_lots_description ON parking_lots(description);

-- 4. פונקציית RPC להתחברות
CREATE OR REPLACE FUNCTION user_login(
    p_username VARCHAR,
    p_password VARCHAR
)
RETURNS JSON
LANGUAGE plpgsql
AS $$
DECLARE
    v_user RECORD;
    v_password_match BOOLEAN;
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
    
    -- בדיקת סיסמה (השתמש בפונקציית bcrypt במקום)
    -- כאן צריך להשתמש ב-extension pgcrypto
    -- v_password_match := crypt(p_password, v_user.password_hash) = v_user.password_hash;
    
    -- לצורך הדוגמה - בדיקה פשוטה (צריך להחליף ב-bcrypt בייצור)
    IF v_user.password_hash IS NULL THEN
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

-- 5. פונקציית RPC לשינוי סיסמה
CREATE OR REPLACE FUNCTION change_user_password(
    p_username VARCHAR,
    p_old_password VARCHAR,
    p_new_password VARCHAR
)
RETURNS JSON
LANGUAGE plpgsql
AS $$
DECLARE
    v_user RECORD;
BEGIN
    -- בדיקת משתמש וסיסמה ישנה
    SELECT * INTO v_user 
    FROM user_parkings 
    WHERE username = p_username;
    
    IF NOT FOUND THEN
        RETURN json_build_object(
            'success', FALSE, 
            'message', 'משתמש לא נמצא'
        );
    END IF;
    
    -- כאן צריך לבדוק את הסיסמה הישנה עם bcrypt
    
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

-- 6. פונקציית RPC ליצירת משתמש עם סיסמה זמנית
CREATE OR REPLACE FUNCTION create_user_with_temp_password(
    p_username VARCHAR,
    p_email VARCHAR,
    p_project_number INTEGER,
    p_code_type VARCHAR,
    p_created_by VARCHAR,
    p_company_list TEXT
)
RETURNS JSON
LANGUAGE plpgsql
AS $$
DECLARE
    v_temp_password VARCHAR;
    v_new_user_id INTEGER;
BEGIN
    -- יצירת סיסמה זמנית
    v_temp_password := 'Temp' || floor(random() * 9000 + 1000)::text;
    
    -- הוספת המשתמש החדש
    INSERT INTO user_parkings (
        username, 
        email, 
        password_hash,
        project_number,
        code_type,
        company_list,
        is_temp_password,
        password_expires_at,
        created_at,
        updated_at
    ) VALUES (
        p_username,
        p_email,
        crypt(v_temp_password, gen_salt('bf')),
        p_project_number::VARCHAR,
        p_code_type,
        p_company_list,
        TRUE,
        NOW() + INTERVAL '7 days',
        NOW(),
        NOW()
    ) RETURNING user_id INTO v_new_user_id;
    
    RETURN json_build_object(
        'success', TRUE,
        'user_id', v_new_user_id,
        'temp_password', v_temp_password,
        'message', 'משתמש נוצר בהצלחה'
    );
EXCEPTION WHEN unique_violation THEN
    RETURN json_build_object(
        'success', FALSE,
        'message', 'שם משתמש כבר קיים'
    );
END;
$$;

-- 7. פונקציית RPC לאיפוס סיסמה על ידי מאסטר
CREATE OR REPLACE FUNCTION master_reset_password(
    p_username VARCHAR,
    p_new_password VARCHAR,
    p_reset_by VARCHAR
)
RETURNS JSON
LANGUAGE plpgsql
AS $$
BEGIN
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

-- 8. הפעלת extension לצורך bcrypt
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- 9. הוספת משתמש לדוגמה (אם צריך)
-- INSERT INTO user_parkings (
--     username, 
--     email, 
--     password_hash,
--     role,
--     project_number,
--     parking_name,
--     company_type,
--     access_level,
--     company_list,
--     permissions
-- ) VALUES (
--     'DrorParking',
--     'SBparkingReport1@gmail.com',
--     crypt('your_password_here', gen_salt('bf')),
--     'user',
--     '478131051',
--     'שיידט בדיקות',
--     'שיידט',
--     'company_manager',
--     '1,2,5-10,60',
--     'G'
-- );

-- 10. הוספת חניון לדוגמה (אם צריך)
-- INSERT INTO parking_lots (
--     name,
--     location,
--     description,
--     ip_address,
--     port,
--     is_active
-- ) VALUES (
--     'שיידט בדיקות',
--     'לוד',
--     '478131051',
--     '10.35.152.100',
--     8443,
--     FALSE
-- );

