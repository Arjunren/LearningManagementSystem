from flask import Blueprint, render_template, session, request, flash, redirect, url_for, jsonify
from utils.decorators import student_required
from services.course_service import get_user_enrollments, get_course
from services.auth_service import user_db, get_user_by_id, verify_password, hash_password, update_student_username
from services.notification_service import get_user_notifications, mark_as_read, mark_all_as_read

bp = Blueprint('user', __name__, url_prefix='/user')

@bp.route('/dashboard')
@student_required
def dashboard():
    user = get_user_by_id(session['user_id'])
    enrollments = get_user_enrollments(session['user_id'])
    
    courses_in_progress = []
    completed_courses = []
    
    for enr in enrollments:
        course = get_course(enr['course_id'])
        if course:
            enr_data = {'enrollment': enr, 'course': course}
            if enr['status'] == 'completed':
                completed_courses.append(enr_data)
            else:
                courses_in_progress.append(enr_data)

    notifications = get_user_notifications(session['user_id'])
    unread_count = sum(1 for n in notifications if not n['read'])
                
    return render_template('user/dashboard.html', 
                           user=user, 
                           in_progress=courses_in_progress,
                           completed=completed_courses,
                           notifications=notifications,
                           unread_count=unread_count)

@bp.route('/notifications/read/<notif_id>', methods=['POST'])
@student_required
def read_notification(notif_id):
    success = mark_as_read(notif_id, session['user_id'])
    return jsonify({'success': success})

@bp.route('/notifications/read_all', methods=['POST'])
@student_required
def read_all_notifications():
    count = mark_all_as_read(session['user_id'])
    return jsonify({'success': True, 'count': count})


@bp.route('/profile', methods=['GET', 'POST'])
@student_required
def profile():
    """Authenticated students may update only their own username."""
    user = get_user_by_id(session['user_id'])
    if not user or user.get('role') != 'student':
        flash('You are not authorized to access this profile.', 'danger')
        return redirect(url_for('auth.login'))
    if request.method == 'POST':
        # Full name, email, student ID, and any forged fields are deliberately
        # ignored; this route has a narrow allow-list by design.
        success, message = update_student_username(user['id'], request.form.get('username'))
        flash(message, 'success' if success else 'danger')
        return redirect(url_for('user.profile'))
    from services.student_progress_service import get_student_progress
    progress = get_student_progress(user['id'])
    return render_template('user/profile.html', user=user, progress=progress)


@bp.route('/ranking')
@student_required
def ranking():
    from services.student_progress_service import get_leaderboard
    sort_by = request.args.get('sort', 'completed')
    try:
        page = int(request.args.get('page', 1))
    except ValueError:
        page = 1
    leaderboard = get_leaderboard(sort_by=sort_by, page=page, per_page=25)
    user = get_user_by_id(session['user_id'])
    return render_template('user/ranking.html', leaderboard=leaderboard,
                           current_student_id=user.get('student_id'))

@bp.route('/settings', methods=['GET', 'POST'])
@student_required
def settings():
    user = get_user_by_id(session['user_id'])
    
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'update_profile':
            # Legacy endpoint retained for compatibility, but no mutable
            # identity fields are accepted here.
            flash("Profile details are read-only. You may update your username from Profile.", "warning")
            
        elif action == 'change_password':
            current_pw = request.form.get('current_password')
            new_pw = request.form.get('new_password')
            confirm_pw = request.form.get('confirm_password')
            
            if not verify_password(current_pw, user['password_hash']):
                flash("Current password is incorrect.", "danger")
            elif new_pw != confirm_pw:
                flash("New passwords do not match.", "danger")
            elif len(new_pw or '') < 8:
                flash("New password must be at least 8 characters long.", "danger")
            else:
                user_db.update(user['id'], {'password_hash': hash_password(new_pw)})
                flash("Password changed successfully.", "success")
                
        return redirect(url_for('user.settings'))
        
    return render_template('user/settings.html', user=user)
