import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from config import Config

def _get_smtp_config():
    """Get SMTP settings, preferring DB settings over env config."""
    try:
        from services.json_database import JSONDatabase
        settings_db = JSONDatabase('settings')
        smtp = settings_db.find_one(type='smtp')
        if smtp and smtp.get('email') and smtp.get('app_password'):
            return {
                'host': smtp.get('host', Config.SMTP_HOST),
                'port': int(smtp.get('port', Config.SMTP_PORT)),
                'email': smtp['email'],
                'password': smtp['app_password']
            }
    except Exception:
        pass
    return {
        'host': Config.SMTP_HOST,
        'port': Config.SMTP_PORT,
        'email': Config.SMTP_EMAIL,
        'password': Config.SMTP_APP_PASSWORD
    }

def send_email(to_email, subject, html_content, smtp_override=None):
    cfg = smtp_override or _get_smtp_config()
    if not cfg['email'] or not cfg['password']:
        print(f"SMTP not configured. Would have sent '{subject}' to {to_email}")
        return False

    try:
        msg = MIMEMultipart('mixed')
        msg['Subject'] = subject
        msg['From'] = f"BuildByte Academy <{cfg['email']}>"
        msg['To'] = to_email

        alt = MIMEMultipart('alternative')
        alt.attach(MIMEText(html_content, 'html'))
        msg.attach(alt)

        with smtplib.SMTP(cfg['host'], cfg['port']) as server:
            server.starttls()
            server.login(cfg['email'], cfg['password'])
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"Failed to send email: {type(e).__name__}")
        return False

def send_email_with_attachment(to_email, subject, html_content, attachment_path, attachment_name=None, smtp_override=None):
    """Send email with a file attachment (e.g., certificate PDF)."""
    cfg = smtp_override or _get_smtp_config()
    if not cfg['email'] or not cfg['password']:
        print(f"SMTP not configured. Would have sent '{subject}' to {to_email}")
        return False

    try:
        msg = MIMEMultipart('mixed')
        msg['Subject'] = subject
        msg['From'] = f"BuildByte Academy <{cfg['email']}>"
        msg['To'] = to_email

        alt = MIMEMultipart('alternative')
        alt.attach(MIMEText(html_content, 'html'))
        msg.attach(alt)

        if attachment_path and os.path.exists(attachment_path):
            fname = attachment_name or os.path.basename(attachment_path)
            with open(attachment_path, 'rb') as f:
                part = MIMEApplication(f.read(), Name=fname)
            part['Content-Disposition'] = f'attachment; filename="{fname}"'
            msg.attach(part)

        with smtplib.SMTP(cfg['host'], cfg['port']) as server:
            server.starttls()
            server.login(cfg['email'], cfg['password'])
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"Failed to send email with attachment: {type(e).__name__}")
        return False

def test_smtp(smtp_config, recipient):
    """Send a test email with provided SMTP config. Returns (success, message)."""
    html = "<h2>SMTP Test</h2><p>Your BuildByte Academy SMTP configuration is working correctly.</p>"
    try:
        result = send_email(recipient, "BuildByte Academy — SMTP Test", html, smtp_override=smtp_config)
        if result:
            return True, "Test email sent successfully."
        return False, "Unable to send. Check SMTP credentials and server settings."
    except Exception as e:
        return False, f"Error: {type(e).__name__}"
