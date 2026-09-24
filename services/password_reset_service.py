import uuid
import datetime
from services.json_database import JSONDatabase
from services.email_service import send_email

reset_tokens_db = JSONDatabase('reset_tokens')

def _now():
    return datetime.datetime.now(datetime.timezone.utc)

def generate_reset_token(user_id):
    token = uuid.uuid4().hex
    expires_at = (_now() + datetime.timedelta(hours=1)).isoformat()
    data = {
        'id': token,
        'token': token,
        'user_id': user_id,
        'used': False,
        'expires_at': expires_at,
        'created_at': _now().isoformat()
    }
    reset_tokens_db.save(token, data)
    return token

def get_valid_token(token):
    data = reset_tokens_db.get(token)
    if not data:
        return None
    if data['used']:
        return None
    
    # Check expiration
    expires_at = datetime.datetime.fromisoformat(data['expires_at'])
    if _now() > expires_at:
        return None
    
    return data

def mark_token_used(token):
    data = reset_tokens_db.get(token)
    if data:
        data['used'] = True
        reset_tokens_db.save(token, data)

def send_reset_email(email, reset_url):
    html_content = f"""
    <div style="font-family: sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <h2 style="color: #1a56db;">BuildByte Academy</h2>
        <h3>Password Reset Request</h3>
        <p>We received a request to reset your BuildByte Academy password.</p>
        <div style="margin: 30px 0;">
            <a href="{reset_url}" style="background-color: #2563eb; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold;">Reset Password</a>
        </div>
        <p style="color: #6b7280; font-size: 14px;">This link expires in 1 hour.</p>
        <p style="color: #6b7280; font-size: 14px;">If you did not request this, you can safely ignore this email.</p>
    </div>
    """
    return send_email(email, "BuildByte Academy — Password Reset Request", html_content)
