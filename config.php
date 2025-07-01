<?php
// קובץ חיבור ל-Supabase
class SupabaseConfig {
    
    // **הפרטים שלך מ-Supabase - מעודכן!**
    private $supabase_url = 'https://tbfebkuyhxlchjdamtkx.supabase.co';  // URL של הפרויקט
    private $supabase_anon_key = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InRiZmVia3V5aHhsY2hqZGFtdGt4Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTExMTI0MDgsImV4cCI6MjA2NjY4ODQwOH0.uxy-EnrvGvBCjtdzn8kPS7bmJT22qhu4ao5rXD4azA8';              // Anon Key
    private $supabase_service_key = 'YOUR_SERVICE_KEY_HERE';        // Service Role Key (לא חובה עכשיו)
    
    // פרטי חיבור ישיר לבסיס הנתונים (PostgreSQL)
    private $db_host = 'db.tbfebkuyhxlchjdamtkx.supabase.co';    // DB Host
    private $db_name = 'postgres';                               // שם בסיס הנתונים
    private $db_user = 'postgres';                               // שם משתמש
    private $db_password = 'tbfebkuyhxlchjdamtkx';               // סיסמת בסיס הנתונים
    private $db_port = 5432;                                // פורט PostgreSQL
    
    private $pdo = null;
    
    // התחברות לבסיס הנתונים
    public function getConnection() {
        if ($this->pdo === null) {
            try {
                $dsn = "pgsql:host={$this->db_host};port={$this->db_port};dbname={$this->db_name}";
                $this->pdo = new PDO($dsn, $this->db_user, $this->db_password);
                $this->pdo->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
                $this->pdo->exec("SET NAMES UTF8");
            } catch (PDOException $e) {
                die("שגיאה בחיבור לבסיס הנתונים: " . $e->getMessage());
            }
        }
        return $this->pdo;
    }
    
    // קריאה לטבלה עם Supabase API
    public function queryTable($table, $select = '*', $where = '', $limit = 100) {
        $url = $this->supabase_url . "/rest/v1/" . $table;
        
        // הוספת פרמטרים
        $params = [];
        $params['select'] = $select;
        if ($where) $params['where'] = $where;
        $params['limit'] = $limit;
        
        $url .= '?' . http_build_query($params);
        
        $headers = [
            'apikey: ' . $this->supabase_anon_key,
            'Authorization: Bearer ' . $this->supabase_anon_key,
            'Content-Type: application/json'
        ];
        
        $ch = curl_init();
        curl_setopt($ch, CURLOPT_URL, $url);
        curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
        curl_setopt($ch, CURLOPT_HTTPHEADER, $headers);
        
        $response = curl_exec($ch);
        $httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
        curl_close($ch);
        
        if ($httpCode === 200) {
            return json_decode($response, true);
        } else {
            throw new Exception("שגיאה בקריאה מ-Supabase: HTTP $httpCode - $response");
        }
    }
    
    // בדיקת חיבור
    public function testConnection() {
        try {
            $pdo = $this->getConnection();
            $stmt = $pdo->query("SELECT current_database(), version()");
            $result = $stmt->fetch(PDO::FETCH_ASSOC);
            return [
                'success' => true,
                'database' => $result['current_database'],
                'version' => $result['version']
            ];
        } catch (Exception $e) {
            return [
                'success' => false,
                'error' => $e->getMessage()
            ];
        }
    }
}

// פונקציות עזר
function getSupabaseDB() {
    static $supabase = null;
    if ($supabase === null) {
        $supabase = new SupabaseConfig();
    }
    return $supabase->getConnection();
}

function testSupabaseConnection() {
    $supabase = new SupabaseConfig();
    return $supabase->testConnection();
}
?>

<!-- 
הוראות להגדרה:

1. עבור לפרויקט Supabase שלך
2. עבור ל-Settings > API
3. העתק את הערכים הבאים:

   - Project URL: העתק ל-supabase_url
   - anon public key: העתק ל-supabase_anon_key  
   - service_role key: העתק ל-supabase_service_key

4. עבור ל-Settings > Database
5. העתק את פרטי החיבור:
   
   - Host: db.YOUR_PROJECT_ID.supabase.co
   - Database name: postgres
   - Username: postgres  
   - Password: הסיסמה שיצרת
   - Port: 5432

6. החלף את כל הערכים בקובץ הזה

דוגמה:
$supabase_url = 'https://abcdefghijklmnop.supabase.co';
$supabase_anon_key = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...';
$db_host = 'db.abcdefghijklmnop.supabase.co';
$db_password = 'your_actual_password_here';
-->
