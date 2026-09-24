import os
import uuid
import secrets
import datetime
import base64
import io
import logging
from urllib.parse import quote

logger = logging.getLogger(__name__)

try:
    from weasyprint import HTML, CSS
    WEASYPRINT_AVAILABLE = True
except (ImportError, OSError) as e:
    logger.warning(f"WeasyPrint is not available ({e}). Certificate generation will fail gracefully.")
    WEASYPRINT_AVAILABLE = False

try:
    import qrcode
    QR_AVAILABLE = True
except ImportError:
    logger.warning("qrcode library not available. QR codes will be skipped.")
    QR_AVAILABLE = False

from jinja2 import Environment, FileSystemLoader
from config import Config
from services.json_database import UniqueIndex

certificate_id_index = UniqueIndex('certificate_id')


def reserve_certificate_id(enrollment_id):
    """Generate and atomically reserve an opaque globally unique ID."""
    for _ in range(20):
        cert_id = f"BBC-{datetime.datetime.now().year}-{secrets.token_urlsafe(12).rstrip('=')}"
        if certificate_id_index.reserve(cert_id, enrollment_id):
            return cert_id
    raise RuntimeError('Unable to generate a unique certificate ID.')


def release_certificate_id(cert_id, enrollment_id):
    certificate_id_index.release(cert_id, enrollment_id)


def ensure_certificate_indexes():
    """Backfill the persistent unique certificate-ID index for legacy records."""
    from services.course_service import enrollment_db
    for enrollment in enrollment_db.get_all():
        cert_id = enrollment.get('certificate_id')
        if not cert_id:
            continue
        if not certificate_id_index.reserve(cert_id, enrollment['id']):
            # Duplicate legacy IDs are inherently ambiguous. Keep the first
            # issued record stable and replace subsequent duplicates securely.
            replacement = reserve_certificate_id(enrollment['id'])
            enrollment_db.update(enrollment['id'], {'certificate_id': replacement})


def _generate_qr_base64(data):
    """Generate a QR code as a base64-encoded PNG data URI (no external API needed)."""
    if not QR_AVAILABLE:
        return ""
    try:
        qr = qrcode.QRCode(version=1, box_size=6, border=2)
        qr.add_data(data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        encoded = base64.b64encode(buffer.read()).decode('utf-8')
        return f"data:image/png;base64,{encoded}"
    except Exception as e:
        logger.warning(f"QR code generation failed: {e}")
        return ""


def generate_certificate(student_name, course_name, template_config=None, cert_id=None, instructor_name=None, completion_date=None):
    """
    Generate a dynamic PDF certificate using WeasyPrint to render the HTML/CSS template.
    
    Returns:
        tuple: (cert_id, cert_filename, pdf_generated)
            - cert_id: The unique certificate ID
            - cert_filename: The PDF filename
            - pdf_generated: True if PDF was created, False if generation failed
    """
    if not cert_id:
        raise ValueError('Certificate ID must be reserved before generation.')
    
    cert_filename = f"{cert_id}_{uuid.uuid4().hex[:12]}.pdf"
    cert_path = os.path.join(Config.CERTIFICATES_DIR, cert_filename)
    os.makedirs(Config.CERTIFICATES_DIR, exist_ok=True)

    try:
        issue_date = datetime.datetime.fromisoformat(completion_date).strftime("%B %d, %Y") if completion_date else datetime.datetime.now().strftime("%B %d, %Y")
    except (TypeError, ValueError):
        issue_date = datetime.datetime.now().strftime("%B %d, %Y")
    qr_url = f"https://buildbyteacademy.vercel.app/certificate.html?id={cert_id}"

    # Generate QR code locally instead of using external API
    qr_data_uri = _generate_qr_base64(qr_url)

    # Load the Jinja template manually outside of app context
    templates_dir = os.path.join(Config.BASE_DIR, 'templates')
    env = Environment(loader=FileSystemLoader(templates_dir))

    # IMPORTANT: Do NOT use external Google Fonts links or CSS transforms.
    # PythonAnywhere free accounts block outbound requests, and WeasyPrint
    # on PythonAnywhere does not support CSS transforms.
    html_template = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            @page {
                size: A4 landscape;
                margin: 0;
            }
            body {
                margin: 0;
                padding: 0;
                width: 297mm;
                height: 210mm;
                background: white;
                font-family: 'DejaVu Sans', 'Liberation Sans', Arial, Helvetica, sans-serif;
            }
        </style>
    </head>
    <body>
        {% include "shared/dynamic_certificate_layout.html" %}
    </body>
    </html>
    """

    template = env.from_string(html_template)

    rendered_html = template.render(
        student_name=student_name,
        course_name=course_name,
        issue_date=issue_date,
        cert_id=cert_id,
        qr_url=qr_url,
        qr_data_uri=qr_data_uri,
        template_config=template_config,
        instructor_name=instructor_name or ''
    )

    # WeasyPrint: base_url tells it where to resolve relative file paths (e.g. images)
    pdf_generated = False
    if WEASYPRINT_AVAILABLE:
        try:
            HTML(
                string=rendered_html,
                base_url=Config.BASE_DIR
            ).write_pdf(cert_path)
            pdf_generated = True
            logger.info(f"Certificate PDF generated successfully: {cert_id}")
        except Exception as e:
            logger.error(f"WeasyPrint PDF generation failed for {cert_id}: {e}")
    else:
        logger.warning(f"Skipping PDF generation for {cert_id} because WeasyPrint is unavailable.")

    return cert_id, cert_filename, pdf_generated
