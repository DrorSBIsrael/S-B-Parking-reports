import os
import requests
from dotenv import load_dotenv

load_dotenv()

GREEN_API_ID = os.getenv("GREEN_API_ID")
GREEN_API_TOKEN = os.getenv("GREEN_API_TOKEN")

def send_whatsapp_otp(phone_number, otp_code):
    """
    Sends an OTP message via WhatsApp using Green API.
    phone_number should be in format '972501234567'
    """
    if not GREEN_API_ID or not GREEN_API_TOKEN:
        print("❌ GreenAPI credentials not configured in .env")
        return False, "הגדרות וואטסאפ חסרות במערכת"
        
    # Clean phone number just in case
    clean_phone = ''.join(filter(str.isdigit, str(phone_number)))
    if clean_phone.startswith('0'):
        clean_phone = '972' + clean_phone[1:]
        
    chat_id = f"{clean_phone}@c.us"
    
    url = f"https://api.green-api.com/waInstance{GREEN_API_ID}/sendMessage/{GREEN_API_TOKEN}"
    
    message = (
        f"שלום! 👋\n\n"
        f"קוד ההתחברות שלך לאפליקציית ניהול החניונים הוא:\n"
        f"*{otp_code}*\n\n"
        f"הקוד בתוקף ל-5 דקות."
    )
    
    payload = {
        "chatId": chat_id,
        "message": message
    }
    
    headers = {
        'Content-Type': 'application/json'
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        
        if response.status_code == 200:
            print(f"✅ WhatsApp OTP sent successfully to {clean_phone}")
            return True, "הודעת ווטסאפ נשלחה בהצלחה"
        else:
            print(f"❌ Failed to send WhatsApp: {response.status_code} - {response.text}")
            return False, f"שגיאה בשליחת הודעה: {response.text}"
            
    except Exception as e:
        print(f"❌ Exception in send_whatsapp_otp: {str(e)}")
        return False, f"שגיאת תקשורת: {str(e)}"

# לטסט מהיר:
if __name__ == "__main__":
    # print(send_whatsapp_otp("972501234567", "123456"))
    pass
