from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
from utils.decorators import admin_required, teacher_or_admin_required
from services.course_service import (course_db, reorder_procedures, delete_procedure_safely,
                                     sanitize_handout_html, recalculate_course_enrollments)
from werkzeug.utils import secure_filename
from config import Config
import datetime
import uuid
import os

bp = Blueprint('admin_courses', __name__, url_prefix='/admin/courses')

HANDOUT_UPLOAD_DIR = os.path.join(Config.UPLOADS_DIR, 'handouts')
ALLOWED_HANDOUT_EXTENSIONS = {
    'pdf', 'doc', 'docx', 'ppt', 'pptx', 'xls', 'xlsx', 'txt', 'csv', 'zip'
}

def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _teacher_can_manage(course_id):
    """Use a single server-side authorization check for every content action."""
    if session.get('role') != 'teacher':
        return True
    from services.teacher_service import is_teacher_assigned
    return is_teacher_assigned(session.get('user_id'), course_id)


def _content_redirect(course_id):
    if session.get('role') == 'teacher':
        return redirect(url_for('teacher.my_courses'))
    return redirect(url_for('admin_courses.index'))


def _save_handout_upload(upload):
    if not upload or not upload.filename:
        return None, 'Please choose a document to upload.'
    original_name = secure_filename(upload.filename)
    if not original_name or '.' not in original_name:
        return None, 'Please upload a supported document file.'
    extension = original_name.rsplit('.', 1)[1].lower()
    if extension not in ALLOWED_HANDOUT_EXTENSIONS:
        return None, 'Unsupported handout format.'
    os.makedirs(HANDOUT_UPLOAD_DIR, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex}_{original_name}"
    upload.save(os.path.join(HANDOUT_UPLOAD_DIR, stored_name))
    return f'handouts/{stored_name}', None


def _procedure_from_form(existing=None):
    """Validate and normalize a procedure without mutating the course yet."""
    proc_type = request.form.get('type', '').strip()
    if proc_type not in {'video', 'quiz', 'activity', 'project', 'handout'}:
        return None, 'Choose a valid content type.'
    title = request.form.get('title', '').strip()
    if not title:
        return None, 'A procedure title is required.'

    graded = proc_type in ('quiz', 'activity', 'project')
    try:
        max_score = float(request.form.get('max_score', 100)) if graded else None
        passing_score = float(request.form.get('passing_score', 0)) if graded else None
    except ValueError:
        return None, 'Scores must be valid numbers.'
    if graded and (max_score <= 0 or passing_score < 0 or passing_score > max_score):
        return None, 'Passing score must be between 0 and the maximum score.'

    procedure = {
        'id': existing.get('id') if existing else f"proc_{uuid.uuid4().hex[:8]}",
        'title': title,
        'type': proc_type,
        'required': request.form.get('required') == 'on',
        'graded': graded,
        'max_score': max_score,
        'passing_score': passing_score,
    }
    if proc_type == 'video':
        procedure['youtube_url'] = request.form.get('youtube_url', '').strip()
    elif proc_type == 'quiz':
        procedure['google_form_url'] = request.form.get('google_form_url', '').strip()
    elif proc_type == 'handout':
        mode = request.form.get('handout_mode', 'text')
        if mode == 'upload':
            file_url, error = _save_handout_upload(request.files.get('handout_file'))
            # On edit, an unchanged existing uploaded document remains valid.
            if error and existing and (existing.get('handout_mode') == 'upload' or existing.get('file_url')) and existing.get('file_url'):
                file_url, error = existing['file_url'], None
            if error:
                return None, error
            procedure.update({
                'handout_mode': 'upload',
                'file_url': file_url,
                'original_filename': request.files.get('handout_file').filename if request.files.get('handout_file') and request.files.get('handout_file').filename else existing.get('original_filename', '') if existing else ''
            })
        elif mode == 'text':
            content_html = sanitize_handout_html(request.form.get('handout_content', ''))
            procedure.update({'handout_mode': 'text', 'content_html': content_html})
        else:
            return None, 'Choose either document upload or text content for this handout.'
    else:
        procedure['instructions'] = request.form.get('instructions', '').strip()
    return procedure, None

@bp.route('/')
@admin_required
def index():
    courses = course_db.get_all()
    return render_template('admin/courses.html', courses=courses)

@bp.route('/create', methods=['GET', 'POST'])
@admin_required
def create():
    if request.method == 'POST':
        course_data = {
            'title': request.form.get('title'),
            'description': request.form.get('description'),
            'instructor': request.form.get('instructor'),
            'difficulty': request.form.get('difficulty'),
            'status': request.form.get('status'),
            'thumbnail': request.form.get('thumbnail'),
            'certificate_template_id': request.form.get('certificate_template_id') or None,
            'require_passing_grades': request.form.get('require_passing_grades') == 'on',
            'procedures': [],
            'syllabus': '',
            'created_at': _now()
        }
        course_db.create(course_data, prefix="crs")
        flash("Course created successfully.", "success")
        return redirect(url_for('admin_courses.index'))

    from services.certificate_db_service import cert_template_db
    templates = cert_template_db.get_all()
    return render_template('admin/course_form.html', course=None, cert_templates=templates)

@bp.route('/<course_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit(course_id):
    course = course_db.get(course_id)
    if not course:
        flash("Course not found.", "danger")
        return redirect(url_for('admin_courses.index'))

    if request.method == 'POST':
        course_db.update(course_id, {
            'title': request.form.get('title'),
            'description': request.form.get('description'),
            'instructor': request.form.get('instructor'),
            'difficulty': request.form.get('difficulty'),
            'status': request.form.get('status'),
            'thumbnail': request.form.get('thumbnail'),
            'certificate_template_id': request.form.get('certificate_template_id') or None,
            'require_passing_grades': request.form.get('require_passing_grades') == 'on',
        })
        flash("Course updated.", "success")
        return redirect(url_for('admin_courses.index'))

    from services.certificate_db_service import cert_template_db
    templates = cert_template_db.get_all()
    return render_template('admin/course_form.html', course=course, cert_templates=templates)

@bp.route('/<course_id>/content', methods=['GET', 'POST'])
@teacher_or_admin_required
def content(course_id):
    course = course_db.get(course_id)
    if not course:
        flash("Course not found.", "danger")
        return _content_redirect(course_id)

    # If teacher, verify assignment
    if not _teacher_can_manage(course_id):
            flash("You are not assigned to this course.", "danger")
            return redirect(url_for('teacher.dashboard'))

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'add_procedure':
            procedure, error = _procedure_from_form()
            if error:
                flash(error, 'danger')
            else:
                procedures = course.get('procedures', [])
                procedures.append(procedure)
                course_db.update(course_id, {'procedures': procedures})
                recalculate_course_enrollments(course_id)
                flash("Procedure added.", "success")

        elif action == 'edit_procedure':
            proc_id = request.form.get('procedure_id')
            procedures = course.get('procedures', [])
            existing = next((p for p in procedures if p.get('id') == proc_id), None)
            if not existing:
                flash('Procedure not found.', 'danger')
            else:
                procedure, error = _procedure_from_form(existing)
                if error:
                    flash(error, 'danger')
                else:
                    course_db.update(course_id, {'procedures': [procedure if p.get('id') == proc_id else p for p in procedures]})
                    recalculate_course_enrollments(course_id)
                    flash("Procedure updated.", "success")

        elif action == 'delete_procedure':
            proc_id = request.form.get('procedure_id')
            if delete_procedure_safely(course_id, proc_id):
                flash("Procedure removed and student progress recalculated.", "success")
            else:
                flash("Procedure not found.", "danger")

        elif action == 'save_syllabus':
            syllabus_text = request.form.get('syllabus', '')
            course_db.update(course_id, {'syllabus': syllabus_text})
            flash("Syllabus saved.", "success")

        return redirect(url_for('admin_courses.content', course_id=course_id))

    return render_template('admin/course_content.html', course=course)


@bp.route('/<course_id>/content/<procedure_id>/edit', methods=['GET', 'POST'])
@teacher_or_admin_required
def edit_procedure(course_id, procedure_id):
    """Dedicated edit page keeps content editing usable for both roles."""
    course = course_db.get(course_id)
    if not course:
        flash('Course not found.', 'danger')
        return _content_redirect(course_id)
    if not _teacher_can_manage(course_id):
        flash('You are not assigned to this course.', 'danger')
        return redirect(url_for('teacher.dashboard'))
    procedure = next((p for p in course.get('procedures', []) if p.get('id') == procedure_id), None)
    if not procedure:
        flash('Procedure not found.', 'danger')
        return redirect(url_for('admin_courses.content', course_id=course_id))
    if request.method == 'POST':
        updated, error = _procedure_from_form(procedure)
        if error:
            flash(error, 'danger')
        else:
            course_db.update(course_id, {'procedures': [updated if p.get('id') == procedure_id else p for p in course.get('procedures', [])]})
            recalculate_course_enrollments(course_id)
            flash('Procedure updated.', 'success')
            return redirect(url_for('admin_courses.content', course_id=course_id))
    return render_template('admin/procedure_form.html', course=course, procedure=procedure)

@bp.route('/<course_id>/content/reorder', methods=['POST'])
@teacher_or_admin_required
def reorder(course_id):
    # If teacher, verify assignment
    if not _teacher_can_manage(course_id):
            return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    """AJAX endpoint: receive ordered list of procedure IDs and save new order."""
    data = request.get_json()
    if not data or 'order' not in data:
        return jsonify({'success': False, 'error': 'No order provided'}), 400
    success = reorder_procedures(course_id, data['order'])
    return jsonify({'success': success})
