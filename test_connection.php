<?php
require_once 'config.php';

echo "<h1>🔧 בדיקת חיבור ל-Supabase</h1>";
echo "<style>
body { font-family: Arial; direction: rtl; background: #f5f5f5; margin: 20px; }
.success { background: #d4edda; color: #155724; padding: 15px; margin: 10px 0; border-radius: 5px; }
.error { background: #f8d7da; color: #721c24; padding: 15px; margin: 10px 0; border-radius: 5px; }
.info { background: #d1ecf1; color: #0c5460; padding: 15px; margin: 10px 0; border-radius: 5px; }
table { width: 100%; border-collapse: collapse; background: white; margin: 10px 0; }
th, td { padding: 10px; border: 1px solid #ddd; text-align: right; }
th { background: #f8f9fa; }
</style>";

// בדיקה 1: חיבור לבסיס הנתונים
echo "<h2>📊 בדיקה 1: חיבור לבסיס הנתונים</h2>";

try {
    $connectionTest = testSupabaseConnection();
    
    if ($connectionTest['success']) {
        echo "<div class='success'>✅ חיבור לבסיס הנתונים הצליח!</div>";
        echo "<div class='info'>
        📋 <strong>פרטי החיבור:</strong><br>
        • בסיס נתונים: {$connectionTest['database']}<br>
        • גרסה: " . substr($connectionTest['version'], 0, 100) . "...
        </div>";
    } else {
        echo "<div class='error'>❌ חיבור לבסיס הנתונים נכשל: {$connectionTest['error']}</div>";
        echo "<div class='info'>💡 בדוק את הסיסמה ופרטי החיבור בקובץ config.php</div>";
    }
    
} catch (Exception $e) {
    echo "<div class='error'>❌ שגיאה: " . $e->getMessage() . "</div>";
}

// בדיקה 2: בדיקת טבלאות
echo "<h2>🗂️ בדיקה 2: בדיקת טבלאות קיימות</h2>";

try {
    $pdo = getSupabaseDB();
    
    // רשימת טבלאות שאנחנו מצפים למצוא
    $expectedTables = ['users', 'parking_data', 'parkings', 'user_parkings'];
    
    foreach ($expectedTables as $table) {
        $stmt = $pdo->prepare("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_schema = 'public' AND table_name = ?)");
        $stmt->execute([$table]);
        $exists = $stmt->fetchColumn();
        
        if ($exists) {
            echo "<div class='success'>✅ טבלה '$table' קיימת</div>";
            
            // ספירת רשומות
            $countStmt = $pdo->prepare("SELECT COUNT(*) FROM $table");
            $countStmt->execute();
            $count = $countStmt->fetchColumn();
            echo "<div class='info'>📊 מספר רשומות בטבלה: $count</div>";
            
        } else {
            echo "<div class='error'>❌ טבלה '$table' לא נמצאה</div>";
        }
    }
    
} catch (Exception $e) {
    echo "<div class='error'>❌ שגיאה בבדיקת טבלאות: " . $e->getMessage() . "</div>";
}

// בדיקה 3: בדיקת מבנה טבלת users
echo "<h2>👥 בדיקה 3: מבנה טבלת users</h2>";

try {
    $pdo = getSupabaseDB();
    
    $stmt = $pdo->query("
        SELECT column_name, data_type, is_nullable, column_default
        FROM information_schema.columns 
        WHERE table_name = 'users' 
        ORDER BY ordinal_position
    ");
    
    $columns = $stmt->fetchAll(PDO::FETCH_ASSOC);
    
    if ($columns) {
        echo "<div class='success'>✅ מבנה טבלת users נמצא</div>";
        echo "<table>";
        echo "<tr><th>שם עמודה</th><th>סוג נתונים</th><th>NULL מותר</th><th>ברירת מחדל</th></tr>";
        
        foreach ($columns as $col) {
            echo "<tr>";
            echo "<td><strong>{$col['column_name']}</strong></td>";
            echo "<td>{$col['data_type']}</td>";
            echo "<td>" . ($col['is_nullable'] === 'YES' ? '✅' : '❌') . "</td>";
            echo "<td>" . ($col['column_default'] ?: '-') . "</td>";
            echo "</tr>";
        }
        echo "</table>";
        
        // בדיקת עמודות חיוניות
        $requiredColumns = ['user_id', 'username', 'email'];
        $foundColumns = array_column($columns, 'column_name');
        
        echo "<h3>🔍 בדיקת עמודות חיוניות:</h3>";
        foreach ($requiredColumns as $reqCol) {
            if (in_array($reqCol, $foundColumns)) {
                echo "<div class='success'>✅ עמודה '$reqCol' קיימת</div>";
            } else {
                echo "<div class='error'>❌ עמודה '$reqCol' חסרה</div>";
            }
        }
        
    } else {
        echo "<div class='error'>❌ לא ניתן לקרוא מבנה טבלת users</div>";
    }
    
} catch (Exception $e) {
    echo "<div class='error'>❌ שגיאה בבדיקת מבנה טבלת users: " . $e->getMessage() . "</div>";
}

// בדיקה 4: בדיקת נתונים לדוגמה
echo "<h2>📋 בדיקה 4: דוגמת נתונים</h2>";

try {
    $pdo = getSupabaseDB();
    
    // בדיקת משתמשים
    $stmt = $pdo->query("SELECT user_id, username, email FROM users LIMIT 3");
    $users = $stmt->fetchAll(PDO::FETCH_ASSOC);
    
    if ($users) {
        echo "<div class='success'>✅ נמצאו " . count($users) . " משתמשים לדוגמה</div>";
        echo "<h4>👤 משתמשים קיימים:</h4>";
        echo "<table>";
        echo "<tr><th>ID</th><th>שם משתמש</th><th>מייל</th></tr>";
        
        foreach ($users as $user) {
            echo "<tr>";
            echo "<td>{$user['user_id']}</td>";
            echo "<td><strong>{$user['username']}</strong></td>";
            echo "<td>{$user['email']}</td>";
            echo "</tr>";
        }
        echo "</table>";
    } else {
        echo "<div class='error'>❌ לא נמצאו משתמשים בטבלה</div>";
        echo "<div class='info'>💡 תצטרך להוסיף משתמש ראשון כדי לבדוק את המערכת</div>";
    }
    
    // בדיקת נתוני חניונים
    $stmt = $pdo->query("SELECT COUNT(*) FROM parking_data");
    $parkingCount = $stmt->fetchColumn();
    
    if ($parkingCount > 0) {
        echo "<div class='success'>✅ נמצאו $parkingCount רשומות נתוני חניונים</div>";
        
        // דוגמה של רשומה אחת
        $stmt = $pdo->query("SELECT * FROM parking_data LIMIT 1");
        $sampleData = $stmt->fetch(PDO::FETCH_ASSOC);
        
        if ($sampleData) {
            echo "<h4>🚗 דוגמת נתוני חניון:</h4>";
            echo "<table>";
            foreach ($sampleData as $key => $value) {
                echo "<tr><td><strong>$key</strong></td><td>" . substr($value, 0, 100) . "</td></tr>";
            }
            echo "</table>";
        }
    } else {
        echo "<div class='error'>❌ לא נמצאו נתוני חניונים</div>";
    }
    
} catch (Exception $e) {
    echo "<div class='error'>❌ שגיאה בבדיקת נתונים: " . $e->getMessage() . "</div>";
}

echo "<hr>";
echo "<h2>🎯 סיכום</h2>";
echo "<div class='info'>
<strong>מה לעשות עכשיו:</strong><br>
1. ✅ אם כל הבדיקות הצליחו - המערכת מוכנה!<br>
2. ❌ אם יש שגיאות - בדוק את הסיסמה בקובץ config.php<br>
3. 📝 אם אין משתמשים - תצטרך להוסיף משתמש ראשון<br>
4. 🚀 השלב הבא: דף כניסה עם זיהוי כפול
</div>";
?>
