from services.json_database import JSONDatabase
import datetime

cert_template_db = JSONDatabase('certificate_templates')

def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def get_all_templates():
    return cert_template_db.get_all()

def get_template(template_id):
    return cert_template_db.get(template_id)

def get_template_for_course(course_id):
    """Get the certificate template assigned to a course."""
    return cert_template_db.find_one(course_id=course_id)

def create_template(name, course_id=None, bg_image_url='', elements=None):
    if elements is None:
        elements = [
            {"id": "element-name", "type": "text", "content": "{{student_name}}", "x": 50, "y": 40, "fontSize": 5.7, "fontFamily": "Inter", "fontWeight": 800, "color": "#0f172a"},
            {"id": "element-course", "type": "text", "content": "{{course_name}}", "x": 50, "y": 64, "fontSize": 2.5, "fontFamily": "Inter", "fontWeight": 700, "color": "#0284c7"},
            {"id": "element-date", "type": "text", "content": "{{issue_date}}", "x": 20, "y": 80, "fontSize": 1.4, "fontFamily": "Inter", "fontWeight": 600, "color": "#0f172a"},
            {"id": "element-cert-id", "type": "text", "content": "{{cert_id}}", "x": 80, "y": 80, "fontSize": 1.4, "fontFamily": "monospace", "fontWeight": 600, "color": "#d97706"},
            {"id": "element-qr", "type": "qr", "content": "{{qr_url}}", "x": 80, "y": 88, "width": 7, "height": 7}
        ]
        
    data = {
        'name': name,
        'course_id': course_id,
        'bg_image_url': bg_image_url,
        'elements': elements,
        'signature_name': 'ARJUNREN VON',
        'signature_title': 'CLOUD ENGINEER',
        'signature_image_data': '',
        'font_size': 5.7,
        'font_weight': 800,
        'name_x': 50,
        'name_y': 40,
        'created_at': _now(),
        'updated_at': _now()
    }
    return cert_template_db.create(data, prefix="ctpl")

def update_template(template_id, updates):
    updates['updated_at'] = _now()
    return cert_template_db.update(template_id, updates)

def delete_template(template_id):
    return cert_template_db.delete(template_id)
