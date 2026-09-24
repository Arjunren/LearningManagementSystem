from services.json_database import JSONDatabase
import datetime
import uuid

notification_db = JSONDatabase('notifications')

def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def create_notification(user_id, notif_type, title, message, course_id=None, procedure_id=None, assessment_id=None, attempt_id=None):
    notif_id = f"notif_{uuid.uuid4().hex[:12]}"
    data = {
        'id': notif_id,
        'notification_id': notif_id,
        'user_id': user_id,
        'type': notif_type,
        'title': title,
        'message': message,
        'course_id': course_id,
        'procedure_id': procedure_id,
        'assessment_id': assessment_id,
        'attempt_id': attempt_id,
        'read': False,
        'created_at': _now()
    }
    notification_db.save(notif_id, data)
    return notif_id

def get_user_notifications(user_id):
    notifs = notification_db.find(user_id=user_id)
    # Sort by created_at descending
    notifs.sort(key=lambda x: x.get('created_at', ''), reverse=True)
    return notifs

def mark_as_read(notif_id, user_id):
    notif = notification_db.get(notif_id)
    if notif and notif.get('user_id') == user_id:
        notif['read'] = True
        notification_db.save(notif_id, notif)
        return True
    return False

def mark_all_as_read(user_id):
    notifs = notification_db.find(user_id=user_id, read=False)
    for n in notifs:
        n['read'] = True
        notification_db.save(n['id'], n)
    return len(notifs)
