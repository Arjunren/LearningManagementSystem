from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from utils.decorators import admin_required
from services.auth_service import authenticate, admin_db, user_db
from services.course_service import course_db, enrollment_db
from services.grade_service import grade_db
from services.email_service import test_smtp
import datetime

bp = Blueprint('admin', __name__)

@bp.route('/loginadmin', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        admin = authenticate(email, password, is_admin=True)
        if admin:
            session['admin_id'] = admin['id']
            session['admin_name'] = admin['full_name']
            session['role'] = 'admin'
            flash('Admin login successful!', 'success')
            return redirect(url_for('admin.dashboard'))
        else:
            flash('Invalid admin credentials.', 'danger')
    return render_template('admin/login.html')

@bp.route('/admin/logout')
def logout():
    session.pop('admin_id', None)
    session.pop('admin_name', None)
    session.pop('role', None)
    flash('Admin logged out.', 'info')
    return redirect(url_for('admin.login'))

@bp.route('/admin/dashboard')
@admin_required
def dashboard():
    users = user_db.get_all()
    courses = course_db.get_all()
    enrollments = enrollment_db.get_all()
    stats = {
        'total_students': len([u for u in users if u.get('role') == 'student']),
        'total_teachers': len([u for u in users if u.get('role') == 'teacher']),
        'total_courses': len(courses),
        'published_courses': len([c for c in courses if c.get('status') == 'published']),
        'total_enrollments': len(enrollments),
        'completed_courses': len([e for e in enrollments if e.get('status') == 'completed'])
    }
    return render_template('admin/dashboard.html', stats=stats)

@bp.route('/admin/settings', methods=['GET', 'POST'])
@admin_required
def settings():
    from services.json_database import JSONDatabase
    settings_db = JSONDatabase('settings')
    smtp_settings = settings_db.find_one(type='smtp') or {}

    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'save_smtp':
            new_settings = {
                'type': 'smtp',
                'host': request.form.get('smtp_host'),
                'port': request.form.get('smtp_port'),
                'email': request.form.get('smtp_email'),
                'app_password': request.form.get('smtp_app_password')
            }
            if smtp_settings and 'id' in smtp_settings:
                settings_db.update(smtp_settings['id'], new_settings)
            else:
                settings_db.create(new_settings, prefix="set")
            flash("SMTP Settings updated successfully.", "success")
        return redirect(url_for('admin.settings'))

    return render_template('admin/settings.html', smtp=smtp_settings)

@bp.route('/admin/settings/test-email', methods=['POST'])
@admin_required
def test_email():
    """AJAX endpoint: send a real test email using current SMTP config."""
    data = request.get_json()
    recipient = (data or {}).get('recipient', '').strip()
    if not recipient:
        return jsonify({'success': False, 'message': 'Recipient email is required.'})

    from services.json_database import JSONDatabase
    settings_db = JSONDatabase('settings')
    smtp_rec = settings_db.find_one(type='smtp') or {}
    smtp_config = {
        'host': smtp_rec.get('host', ''),
        'port': int(smtp_rec.get('port', 587)),
        'email': smtp_rec.get('email', ''),
        'password': smtp_rec.get('app_password', '')
    }

    success, message = test_smtp(smtp_config, recipient)
    return jsonify({'success': success, 'message': message})
