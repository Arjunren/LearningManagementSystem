from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from utils.decorators import login_required
from services.auth_service import authenticate, create_user, hash_password, validate_username, username_index, ensure_identity_indexes
from services.registration_service import save_pending_registration, get_pending_registration, delete_pending_registration
from services.otp_service import generate_otp, verify_otp
from services.email_service import send_email

bp = Blueprint('auth', __name__)

@bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        user = authenticate(email, password)
        if user and user.get('role') == 'student':
            session['user_id'] = user['id']
            session['user_name'] = user['full_name']
            session['role'] = user['role']
            flash('Login successful!', 'success')
            return redirect(url_for('user.dashboard'))
        else:
            flash('Invalid email or password. Teachers must use the teacher login portal.', 'danger')

    return render_template('auth/login.html')

@bp.route('/loginteacher', methods=['GET', 'POST'])
def loginteacher():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        user = authenticate(email, password)
        if user and user.get('role') == 'teacher':
            session['user_id'] = user['id']
            session['user_name'] = user['full_name']
            session['role'] = user['role']
            flash('Teacher login successful!', 'success')
            return redirect(url_for('teacher.dashboard'))
        else:
            flash('Invalid teacher credentials.', 'danger')

    return render_template('auth/loginteacher.html')

@bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        username, username_error = validate_username(request.form.get('username'))
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password')

        if not full_name or not email:
            flash('Full name and email are required.', 'danger')
            return render_template('auth/register.html')
        if username_error:
            flash(username_error, 'danger')
            return render_template('auth/register.html')
        ensure_identity_indexes()
        if username_index.get(username):
            flash('Username is already taken.', 'danger')
            return render_template('auth/register.html')
        if len(password) < 8:
            flash('Password must be at least 8 characters long.', 'danger')
            return render_template('auth/register.html')
        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return render_template('auth/register.html')

        save_pending_registration(full_name, username, email, hash_password(password))
        # Flask's default session is signed but not encrypted, so retain only
        # the non-sensitive lookup key in it.
        session['reg_email'] = email

        otp = generate_otp(email)
        html_content = render_template('email/otp_email.html', otp=otp)
        if send_email(email, "BuildByte Academy — Your Verification Code", html_content):
            flash('An OTP has been sent to your email.', 'info')
        else:
            print(f"DEV MODE OTP for {email}: {otp}")
            flash('OTP generated. Check server console if email is not configured.', 'warning')

        return redirect(url_for('auth.verify_otp_route'))

    return render_template('auth/register.html')

@bp.route('/verify-otp', methods=['GET', 'POST'])
def verify_otp_route():
    email = session.get('reg_email')
    registration = get_pending_registration(email) if email else None
    if not registration:
        flash('Session expired. Please register again.', 'warning')
        return redirect(url_for('auth.register'))

    if request.method == 'POST':
        code = "".join([request.form.get(f'digit{i}', '') for i in range(1, 7)])
        is_valid, msg = verify_otp(email, code)
        if is_valid:
            reg_data = registration
            user_id, create_msg = create_user(
                full_name=reg_data['full_name'],
                username=reg_data['username'],
                email=reg_data['email'],
                password_hash_value=reg_data['password_hash']
            )
            if user_id:
                delete_pending_registration(reg_data)
                session.pop('reg_email', None)
                session['user_id'] = user_id
                session['user_name'] = reg_data['full_name']
                session['role'] = 'student'
                flash('Registration successful! Welcome to BuildByte Academy.', 'success')
                return redirect(url_for('user.dashboard'))
            else:
                flash(create_msg, 'danger')
                return redirect(url_for('auth.register'))
        else:
            flash(msg, 'danger')

    return render_template('auth/verify_otp.html', email=email)

@bp.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))

@bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    return _forgot_password_for_role('student')


@bp.route('/teacher/forgot-password', methods=['GET', 'POST'])
def teacher_forgot_password():
    return _forgot_password_for_role('teacher')


def _forgot_password_for_role(role):
    """Use the same reset-token and email flow for student and teacher users."""
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        from services.auth_service import user_db
        user = user_db.find_one(email=email)
        
        # Always return the same message to avoid account enumeration
        flash('If an account exists for this email, a password reset link has been sent.', 'info')
        
        if user and user.get('role') == role:
            from services.password_reset_service import generate_reset_token, send_reset_email
            token = generate_reset_token(user['id'])
            reset_url = url_for('auth.reset_password', token=token, _external=True)
            send_reset_email(email, reset_url)
            
        return redirect(url_for('auth.loginteacher' if role == 'teacher' else 'auth.login'))
        
    return render_template(
        'auth/forgot_password.html',
        forgot_endpoint='auth.teacher_forgot_password' if role == 'teacher' else 'auth.forgot_password',
        login_endpoint='auth.loginteacher' if role == 'teacher' else 'auth.login',
        portal_label='Teacher Portal' if role == 'teacher' else 'Student Portal'
    )

@bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    from services.password_reset_service import get_valid_token, mark_token_used
    
    valid_token = get_valid_token(token)
    if not valid_token:
        flash('Invalid or expired reset token.', 'danger')
        return redirect(url_for('auth.login'))
        
    if request.method == 'POST':
        new_password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        if not new_password or new_password != confirm_password:
            flash('Passwords do not match or are empty.', 'danger')
            return render_template('auth/reset_password.html', token=token)
        if len(new_password) < 8:
            flash('Password must be at least 8 characters long.', 'danger')
            return render_template('auth/reset_password.html', token=token)
            
        from services.auth_service import hash_password, user_db
        user_id = valid_token['user_id']
        user = user_db.get(user_id)
        if user:
            user['password_hash'] = hash_password(new_password)
            user_db.save(user_id, user)
            mark_token_used(token)
            flash('Password successfully reset. You can now login.', 'success')
            return redirect(url_for('auth.loginteacher' if user.get('role') == 'teacher' else 'auth.login'))
        else:
            flash('User not found.', 'danger')
            return redirect(url_for('auth.login'))

    return render_template('auth/reset_password.html', token=token)
