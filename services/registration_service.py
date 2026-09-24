"""Server-side pending-registration storage; never put passwords in sessions."""
import datetime
from services.json_database import JSONDatabase

pending_registration_db = JSONDatabase('pending_registrations')


def save_pending_registration(full_name, username, email, password_hash):
    existing = pending_registration_db.find_one(email=email)
    data = {
        'full_name': full_name,
        'username': username,
        'email': email,
        'password_hash': password_hash,
        'expires_at': (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=15)).isoformat(),
        'updated_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    if existing:
        pending_registration_db.update(existing['id'], data)
        return existing['id']
    return pending_registration_db.create(data, prefix='preg')


def get_pending_registration(email):
    registration = pending_registration_db.find_one(email=email)
    if not registration:
        return None
    try:
        if datetime.datetime.now(datetime.timezone.utc) > datetime.datetime.fromisoformat(registration['expires_at']):
            pending_registration_db.delete(registration['id'])
            return None
    except (KeyError, ValueError):
        return None
    return registration


def delete_pending_registration(registration):
    if registration:
        pending_registration_db.delete(registration['id'])
