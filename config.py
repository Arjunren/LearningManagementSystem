import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key'
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'False').lower() in {'1', 'true', 'yes', 'on'}
    SESSION_COOKIE_SAMESITE = 'Lax'
    # Applies to handout uploads and all other request bodies. Override in the
    # deployment environment if larger course documents are intentionally used.
    MAX_CONTENT_LENGTH = int(os.environ.get('MAX_CONTENT_LENGTH', 16 * 1024 * 1024))
    
    # SMTP Settings
    SMTP_HOST = os.environ.get('SMTP_HOST', 'smtp.gmail.com')
    SMTP_PORT = int(os.environ.get('SMTP_PORT', 587))
    SMTP_EMAIL = os.environ.get('SMTP_EMAIL', '')
    SMTP_APP_PASSWORD = os.environ.get('SMTP_APP_PASSWORD', '')
    
    OTP_EXPIRATION_MINUTES = int(os.environ.get('OTP_EXPIRATION_MINUTES', 5))
    
    # Data directory
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    DATA_DIR = os.path.join(BASE_DIR, 'data')
    CERTIFICATES_DIR = os.path.join(BASE_DIR, 'certificates')
    UPLOADS_DIR = os.path.join(BASE_DIR, 'static', 'uploads')
    CERTIFICATE_FRONTEND_ORIGIN = os.environ.get('CERTIFICATE_FRONTEND_ORIGIN', 'https://buildbyteacademy.vercel.app')
