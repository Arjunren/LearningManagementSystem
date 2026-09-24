from services.json_database import JSONDatabase

teacher_assignment_db = JSONDatabase('teacher_assignments')

def assign_teacher(teacher_id, course_id):
    """Assign a teacher to a course. No-op if already assigned."""
    existing = teacher_assignment_db.find_one(teacher_id=teacher_id, course_id=course_id)
    if existing:
        return existing['id']
    import datetime
    data = {
        'teacher_id': teacher_id,
        'course_id': course_id,
        'assigned_at': datetime.datetime.now(datetime.timezone.utc).isoformat()
    }
    return teacher_assignment_db.create(data, prefix="ta")

def unassign_teacher(teacher_id, course_id):
    record = teacher_assignment_db.find_one(teacher_id=teacher_id, course_id=course_id)
    if record:
        teacher_assignment_db.delete(record['id'])
        return True
    return False

def get_teacher_courses(teacher_id):
    """Returns list of course_ids assigned to the teacher."""
    assignments = teacher_assignment_db.find(teacher_id=teacher_id)
    return [a['course_id'] for a in assignments]

def get_course_teachers(course_id):
    assignments = teacher_assignment_db.find(course_id=course_id)
    return [a['teacher_id'] for a in assignments]

def is_teacher_assigned(teacher_id, course_id):
    return teacher_assignment_db.find_one(teacher_id=teacher_id, course_id=course_id) is not None

def set_teacher_courses(teacher_id, course_ids):
    """Replace all course assignments for a teacher with a new list."""
    # De-duplicate form values so a malformed request cannot create duplicate
    # relationship records.
    course_ids = list(dict.fromkeys(course_ids or []))
    old = teacher_assignment_db.find(teacher_id=teacher_id)
    for a in old:
        teacher_assignment_db.delete(a['id'])
    for cid in course_ids:
        assign_teacher(teacher_id, cid)
