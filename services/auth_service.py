from werkzeug.security import generate_password_hash, check_password_hash
from services.json_database import JSONDatabase, UniqueIndex
import datetime
import re
import secrets

user_db = JSONDatabase('users')
admin_db = JSONDatabase('admins')
username_index = UniqueIndex('username')
student_id_index = UniqueIndex('student_id')

USERNAME_RE = re.compile(r'^[a-zA-Z0-9_.-]{3,32}$')


def hash_password(password):
    return generate_password_hash(password)


def verify_password(password, hashed_password):
    return check_password_hash(hashed_password, password)


def normalize_username(username):
    return (username or '').strip().lower()


def validate_username(username):
    username = normalize_username(username)
    if not USERNAME_RE.fullmatch(username):
        return None, 'Please provide a valid username (3–32 letters, numbers, dots, hyphens, or underscores).'
    return username, None


def _new_student_id():
    return f"BB-{datetime.datetime.now().year}-{secrets.token_hex(4).upper()}"


def _reserve_generated_student_id(owner_id):
    for _ in range(20):
        student_id = _new_student_id()
        if student_id_index.reserve(student_id, owner_id):
            return student_id
    raise RuntimeError('Unable to generate a unique student ID.')


def _legacy_username(user):
    return f"student-{user['id'].split('_')[-1][:12]}"


def ensure_identity_indexes():
    """Backfill legacy students without overwriting valid existing identities."""
    for user in user_db.get_all():
        if user.get('role') != 'student':
            continue
        updates = {}
        username, error = validate_username(user.get('username'))
        if error or not username_index.reserve(username, user['id']):
            base = _legacy_username(user)
            username = base
            for _ in range(20):
                if username_index.reserve(username, user['id']):
                    break
                username = f"{base[:23]}-{secrets.token_hex(3)}"
            else:
                raise RuntimeError('Unable to migrate a unique username.')
        if user.get('username') != username:
            updates['username'] = username

        student_id = user.get('student_id')
        if not student_id or not student_id_index.reserve(student_id, user['id']):
            student_id = _reserve_generated_student_id(user['id'])
            updates['student_id'] = student_id
        if updates:
            updates['updated_at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            user_db.update(user['id'], updates)


def create_user(full_name, email, password=None, role='student', username=None, password_hash_value=None):
    email = (email or '').strip().lower()
    full_name = (full_name or '').strip()
    if not full_name or not email or (not password and not password_hash_value):
        return None, 'All required fields must be provided.'
    if user_db.find_one(email=email) or admin_db.find_one(email=email):
        return None, 'Email already exists.'

    user_id = user_db.generate_id('user')
    reserved_username = None
    reserved_student_id = None
    if role == 'student':
        ensure_identity_indexes()
        reserved_username, error = validate_username(username)
        if error:
            return None, error
        if not username_index.reserve(reserved_username, user_id):
            return None, 'Username is already taken.'
        try:
            reserved_student_id = _reserve_generated_student_id(user_id)
        except RuntimeError:
            username_index.release(reserved_username, user_id)
            return None, 'Unable to create a student ID. Please try again.'

    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    user_data = {
        'full_name': full_name,
        'email': email,
        'password_hash': password_hash_value or hash_password(password),
        'email_verified': True,
        'role': role,
        'created_at': now,
        'updated_at': now,
    }
    if role == 'student':
        user_data.update(username=reserved_username, student_id=reserved_student_id)
    try:
        user_db.create(user_data, record_id=user_id)
    except Exception:
        if reserved_username:
            username_index.release(reserved_username, user_id)
        if reserved_student_id:
            student_id_index.release(reserved_student_id, user_id)
        raise
    return user_id, 'User created successfully.'


def update_student_username(user_id, submitted_username):
    user = user_db.get(user_id)
    if not user or user.get('role') != 'student':
        return False, 'You are not authorized to modify this information.'
    ensure_identity_indexes()
    username, error = validate_username(submitted_username)
    if error:
        return False, error
    old_username = normalize_username(user.get('username'))
    if username == old_username:
        return True, 'Username is unchanged.'
    if not username_index.reserve(username, user_id):
        return False, 'Username is already taken.'
    try:
        user_db.update(user_id, {'username': username, 'updated_at': datetime.datetime.now(datetime.timezone.utc).isoformat()})
    except Exception:
        username_index.release(username, user_id)
        raise
    if old_username:
        username_index.release(old_username, user_id)
    return True, 'Username updated successfully.'


def authenticate(email, password, is_admin=False):
    db = admin_db if is_admin else user_db
    user = db.find_one(email=(email or '').strip().lower())
    if user and verify_password(password, user['password_hash']):
        return user
    return None


def get_user_by_id(user_id, is_admin=False):
    db = admin_db if is_admin else user_db
    user = db.get(user_id)
    if user and not is_admin and user.get('role') == 'student':
        ensure_identity_indexes()
        user = db.get(user_id)
    return user
