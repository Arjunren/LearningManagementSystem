import random
import datetime
from services.json_database import JSONDatabase
from config import Config

otp_db = JSONDatabase('otps')

def generate_otp(email):
    # Invalidate previous OTPs for this email
    existing = otp_db.find(email=email)
    for record in existing:
        otp_db.delete(record['id'])

    code = f"{random.randint(100000, 999999)}"
    expires_at = (datetime.datetime.utcnow() + datetime.timedelta(minutes=Config.OTP_EXPIRATION_MINUTES)).isoformat()
    
    otp_data = {
        'email': email,
        'code': code, # In production, hash this instead of storing plain text
        'expires_at': expires_at,
        'attempts': 0
    }
    
    otp_db.create(otp_data, prefix="otp")
    return code

def verify_otp(email, code):
    otps = otp_db.find(email=email)
    if not otps:
        return False, "No OTP found."
        
    otp_record = otps[0]
    
    if otp_record['attempts'] >= 3:
        otp_db.delete(otp_record['id'])
        return False, "Too many failed attempts. Request a new OTP."
        
    expires_at = datetime.datetime.fromisoformat(otp_record['expires_at'])
    if datetime.datetime.utcnow() > expires_at:
        otp_db.delete(otp_record['id'])
        return False, "OTP has expired."
        
    if str(otp_record['code']) == str(code):
        otp_db.delete(otp_record['id'])
        return True, "Success"
        
    otp_db.update(otp_record['id'], {'attempts': otp_record['attempts'] + 1})
    return False, "Invalid OTP."
