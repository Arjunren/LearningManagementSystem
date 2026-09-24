from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
from utils.decorators import admin_required
from services.auth_service import user_db, admin_db, hash_password
from services.teacher_service import set_teacher_courses, get_teacher_courses
from services.course_service import course_db
import datetime

bp = Blueprint('admin_users', __name__, url_prefix='/admin/users')

def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

@bp.route('/')
@admin_required
def index():
    all_users = user_db.get_all()
    admins = admin_db.get_all()
    students = [u for u in all_users if u.get('role') == 'student']
    teachers = [u for u in all_users if u.get('role') == 'teacher']
    all_courses = course_db.get_all()
    teacher_course_ids = {teacher['id']: get_teacher_courses(teacher['id']) for teacher in teachers}
    return render_template('admin/users.html',
                           students=students,
                           teachers=teachers,
                           admins=admins,
                           all_courses=all_courses,
                           teacher_course_ids=teacher_course_ids)

@bp.route('/create-teacher', methods=['POST'])
@admin_required
def create_teacher():
    full_name = request.form.get('full_name', '').strip()
    email = request.form.get('email', '').strip()
    password = request.form.get('password', '').strip()
    assigned_course_ids = request.form.getlist('course_ids')
    valid_course_ids = {course['id'] for course in course_db.get_all()}
    assigned_course_ids = [course_id for course_id in assigned_course_ids if course_id in valid_course_ids]

    if not full_name or not email or not password:
        flash("All fields are required.", "danger")
        return redirect(url_for('admin_users.index'))

    if user_db.find_one(email=email) or admin_db.find_one(email=email):
        flash("Email already in use.", "danger")
        return redirect(url_for('admin_users.index'))

    teacher_data = {
        'full_name': full_name,
        'email': email,
        'password_hash': hash_password(password),
        'email_verified': True,
        'role': 'teacher',
        'created_at': _now(),
        'updated_at': _now()
    }
    teacher_id = user_db.create(teacher_data, prefix="usr")
    set_teacher_courses(teacher_id, assigned_course_ids)

    flash(f"Teacher '{full_name}' created successfully.", "success")
    return redirect(url_for('admin_users.index'))

@bp.route('/<user_id>/edit-teacher', methods=['POST'])
@admin_required
def edit_teacher(user_id):
    user = user_db.get(user_id)
    if not user or user.get('role') != 'teacher':
        flash("Teacher not found.", "danger")
        return redirect(url_for('admin_users.index'))

    valid_course_ids = {course['id'] for course in course_db.get_all()}
    assigned_course_ids = [course_id for course_id in request.form.getlist('course_ids') if course_id in valid_course_ids]
    set_teacher_courses(user_id, assigned_course_ids)
    flash("Teacher course assignments updated.", "success")
    return redirect(url_for('admin_users.index'))


@bp.route('/students/<student_user_id>')
@admin_required
def student_detail(student_user_id):
    student = user_db.get(student_user_id)
    if not student or student.get('role') != 'student':
        flash('Student not found.', 'danger')
        return redirect(url_for('admin_users.index'))
    from services.student_progress_service import get_student_progress
    progress = get_student_progress(student_user_id)
    # Explicit projection keeps password hashes and authentication metadata out
    # of the view layer.
    student_view = {
        'full_name': student.get('full_name'),
        'username': student.get('username'),
        'email': student.get('email'),
        'student_id': student.get('student_id'),
        'created_at': student.get('created_at'),
    }
    return render_template('admin/student_detail.html', student=student_view, progress=progress)

@bp.route('/<user_id>/delete', methods=['POST'])
@admin_required
def delete(user_id):
    if user_db.delete(user_id):
        flash("User deleted.", "success")
    else:
        flash("User not found.", "danger")
    return redirect(url_for('admin_users.index'))
