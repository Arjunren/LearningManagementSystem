from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from utils.decorators import teacher_required
from services.course_service import course_db, enrollment_db
from services.teacher_service import get_teacher_courses
from services.auth_service import get_user_by_id, verify_password, hash_password, user_db

bp = Blueprint('teacher', __name__, url_prefix='/teacher')

@bp.route('/dashboard')
@teacher_required
def dashboard():
    user = get_user_by_id(session['user_id'])
    assigned_course_ids = get_teacher_courses(session['user_id'])
    courses = [course_db.get(cid) for cid in assigned_course_ids if course_db.get(cid)]

    total_students = 0
    for c in courses:
        total_students += len(enrollment_db.find(course_id=c['id']))

    return render_template('teacher/dashboard.html',
                           user=user,
                           courses=courses,
                           total_students=total_students)

@bp.route('/courses')
@teacher_required
def my_courses():
    assigned_course_ids = get_teacher_courses(session['user_id'])
    courses = [course_db.get(cid) for cid in assigned_course_ids if course_db.get(cid)]
    return render_template('teacher/my_courses.html', courses=courses)


@bp.route('/settings', methods=['GET', 'POST'])
@teacher_required
def settings():
    user = get_user_by_id(session['user_id'])
    if request.method == 'POST':
        current_password = request.form.get('current_password', '')
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')
        if not verify_password(current_password, user['password_hash']):
            flash('Current password is incorrect.', 'danger')
        elif len(new_password) < 8:
            flash('New password must be at least 8 characters long.', 'danger')
        elif new_password != confirm_password:
            flash('New passwords do not match.', 'danger')
        else:
            user_db.update(user['id'], {'password_hash': hash_password(new_password)})
            flash('Password changed successfully.', 'success')
        return redirect(url_for('teacher.settings'))
    return render_template('teacher/settings.html', user=user)
