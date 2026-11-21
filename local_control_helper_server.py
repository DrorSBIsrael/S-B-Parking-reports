import os
import sys
sys.path.insert(0, r'C:\S-B-Parking-reports')
from flask import Flask
from dotenv import load_dotenv
load_dotenv(r'C:\S-B-Parking-reports\.env')

supabase = None
try:
    from supabase import create_client
    u = os.getenv('SUPABASE_URL')
    k = os.getenv('SUPABASE_KEY')
    if u and k:
        supabase = create_client(u, k)
except Exception:
    supabase = None

import parking_control_system
from parking_control_system import parking_control_bp

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'local-dev-secret')
sys.modules['__main__'].supabase = supabase
app.register_blueprint(parking_control_bp)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5055, debug=False)
