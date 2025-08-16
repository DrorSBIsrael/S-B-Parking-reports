try:
    import imapclient
    print("✅ imapclient - OK")
except ImportError as e:
    print(f"❌ imapclient - {e}")

try:
    import email
    print("✅ email - OK (built-in)")
except ImportError as e:
    print(f"❌ email - {e}")

try:
    import pandas as pd
    print("✅ pandas - OK")
except ImportError as e:
    print(f"❌ pandas - {e}")

try:
    from datetime import datetime
    print("✅ datetime - OK (built-in)")
except ImportError as e:
    print(f"❌ datetime - {e}")