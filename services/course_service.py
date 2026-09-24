from services.json_database import JSONDatabase
import datetime
from html import escape, unescape
from html.parser import HTMLParser

course_db = JSONDatabase('courses')
enrollment_db = JSONDatabase('enrollments')


class _HandoutHTMLSanitizer(HTMLParser):
    """Small allow-list sanitizer for teacher-authored handout HTML.

    Handouts are rendered in the student portal, so accepting arbitrary HTML here
    would turn a teacher input field into an XSS vector.  The editor only needs a
    deliberately small set of document-formatting tags.
    """
    allowed_tags = {'h1', 'h2', 'h3', 'h4', 'p', 'strong', 'b', 'em', 'i',
                    'ul', 'ol', 'li', 'a', 'br', 'blockquote', 'table',
                    'thead', 'tbody', 'tr', 'th', 'td'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag not in self.allowed_tags:
            return
        if tag == 'a':
            href = next((value for key, value in attrs if key.lower() == 'href'), '') or ''
            if href.startswith(('http://', 'https://', 'mailto:')):
                self.parts.append(f'<a href="{escape(href, quote=True)}" target="_blank" rel="noopener noreferrer">')
                return
            self.parts.append('<a>')
            return
        if tag in {'td', 'th'}:
            span_attrs = []
            for key, value in attrs:
                if key.lower() in {'colspan', 'rowspan'} and (value or '').isdigit():
                    span_attrs.append(f' {key.lower()}="{value}"')
            self.parts.append(f'<{tag}{"".join(span_attrs)}>')
            return
        self.parts.append(f'<{tag}>')

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in self.allowed_tags and tag not in {'br'}:
            self.parts.append(f'</{tag}>')

    def handle_data(self, data):
        self.parts.append(escape(data))


def sanitize_handout_html(value):
    """Return safe, readable HTML for a text handout, including legacy text."""
    # Older handouts may have been stored as ``&lt;p&gt;...``. Decode once
    # before allow-list sanitization so intended formatting renders, while the
    # sanitizer still removes dangerous tags and attributes.
    value = unescape((value or '').strip())
    if not value:
        return '<p>No handout content has been provided.</p>'

    # Legacy handouts stored pasted text in ``instructions``. Preserve its line
    # breaks as paragraphs instead of presenting it as a missing download.
    if '<' not in value or '>' not in value:
        paragraphs = [f'<p>{escape(part).replace(chr(10), "<br>")}</p>'
                      for part in value.replace('\r\n', '\n').split('\n\n') if part.strip()]
        return ''.join(paragraphs) or '<p>No handout content has been provided.</p>'

    parser = _HandoutHTMLSanitizer()
    parser.feed(value)
    parser.close()
    return ''.join(parser.parts) or '<p>No handout content has been provided.</p>'

def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def get_all_courses(published_only=True):
    courses = course_db.get_all()
    if published_only:
        return [c for c in courses if c.get('status') == 'published']
    return courses

def get_course(course_id):
    return course_db.get(course_id)

def get_user_enrollments(user_id):
    return enrollment_db.find(user_id=user_id)

def get_enrollment(enrollment_id):
    return enrollment_db.get(enrollment_id)

def enroll_user(user_id, course_id):
    existing = enrollment_db.find_one(user_id=user_id, course_id=course_id)
    if existing:
        return existing['id'], "Already enrolled"

    enrollment_data = {
        'user_id': user_id,
        'course_id': course_id,
        'progress': 0,
        'completed_procedures': [],
        'status': 'in_progress',
        'enrolled_at': _now(),
        'completed_at': None,
        'certificate_id': None,
        'certificate_filename': None,
        'celebration_shown': False,
        'cert_last_sent_at': None
    }

    enrollment_id = enrollment_db.create(enrollment_data, prefix="enr")
    return enrollment_id, "Successfully enrolled"

def get_graded_procedures(course):
    """Returns procedures that are graded (quiz/activity/project with graded=True)."""
    graded_types = {'quiz', 'activity', 'project'}
    return [
        p for p in course.get('procedures', [])
        if p.get('type') in graded_types and p.get('graded', False)
    ]

def get_required_procedures(course):
    """Returns procedures marked as required for completion."""
    return [p for p in course.get('procedures', []) if p.get('required', False)]

def check_course_completion(enrollment_id):
    """
    Checks if a course is truly completed based on progress AND assessment eligibility.
    Updates enrollment status. Returns (newly_completed).
    
    Progress = content/procedure completion
    Certificate eligibility = separate, handled by check_certificate_eligibility()
    
    A course is marked 'completed' only when:
      - All required procedures are content-completed
      - All required graded assessments are PASSED
    """
    enrollment = enrollment_db.get(enrollment_id)
    if not enrollment: return False

    course = get_course(enrollment['course_id'])
    if not course: return False

    completed_procs = set(enrollment.get('completed_procedures', []))
    required = get_required_procedures(course)

    # Calculate content progress
    if required:
        completed_required = [p for p in required if p['id'] in completed_procs]
        progress = int((len(completed_required) / len(required)) * 100)
    else:
        total = len(course.get('procedures', []))
        progress = int((len(completed_procs) / total) * 100) if total > 0 else 100

    progress = min(progress, 100)

    # Content complete — now check assessment eligibility
    is_completed = False
    if progress == 100:
        from services.grade_service import check_certificate_eligibility
        eligible, _ = check_certificate_eligibility(enrollment['user_id'], course['id'])
        is_completed = eligible

    was_completed = enrollment.get('status') == 'completed'
    status = 'completed' if is_completed else 'in_progress'
    newly_completed = (status == 'completed' and not was_completed)

    completed_at = _now() if newly_completed else enrollment.get('completed_at')

    enrollment_db.update(enrollment_id, {
        'progress': progress,
        'status': status,
        'completed_at': completed_at
    })

    if newly_completed:
        enrollment_db.update(enrollment_id, {'celebration_pending': True})

    return newly_completed

def update_progress(enrollment_id, procedure_id, is_graded=False, max_score=100, passing_score=0):
    """
    Mark a procedure complete and recalculate progress.
    For graded procedures, this only marks content as complete but does NOT
    set assessment status — submit_for_review() handles that separately.
    """
    enrollment = enrollment_db.get(enrollment_id)
    if not enrollment:
        return False, False

    completed_procs = set(enrollment.get('completed_procedures', []))
    completed_procs.add(procedure_id)

    enrollment_db.update(enrollment_id, {
        'completed_procedures': list(completed_procs)
    })

    newly_completed = check_course_completion(enrollment_id)
    return True, newly_completed

def reorder_procedures(course_id, ordered_ids):
    """Reorder procedures in a course according to the provided list of IDs."""
    course = course_db.get(course_id)
    if not course:
        return False
    proc_map = {p['id']: p for p in course.get('procedures', [])}
    new_order = [proc_map[pid] for pid in ordered_ids if pid in proc_map]
    existing_ids = set(ordered_ids)
    for p in course.get('procedures', []):
        if p['id'] not in existing_ids:
            new_order.append(p)
    course_db.update(course_id, {'procedures': new_order})
    return True


def delete_procedure_safely(course_id, procedure_id):
    """Delete course content while keeping enrollment progress consistent."""
    course = course_db.get(course_id)
    if not course or not any(p.get('id') == procedure_id for p in course.get('procedures', [])):
        return False

    course_db.update(course_id, {
        'procedures': [p for p in course.get('procedures', []) if p.get('id') != procedure_id]
    })
    for enrollment in enrollment_db.find(course_id=course_id):
        completed = [pid for pid in enrollment.get('completed_procedures', []) if pid != procedure_id]
        enrollment_db.update(enrollment['id'], {'completed_procedures': completed})
        # Recalculate after the course definition and the enrollment are in sync.
        check_course_completion(enrollment['id'])
    return True


def recalculate_course_enrollments(course_id):
    """Re-evaluate progress after a teacher changes the course requirements."""
    for enrollment in enrollment_db.find(course_id=course_id):
        check_course_completion(enrollment['id'])
