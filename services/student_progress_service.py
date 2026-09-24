"""Read-only student progress, star, and leaderboard aggregation.

The service loads each JSON collection once and joins it in memory. This avoids
per-student/per-course database lookups and keeps enrollment status as the sole
authoritative definition of course completion.
"""
import math
from services.auth_service import user_db
from services.course_service import course_db, enrollment_db
from services.grade_service import grade_db


def stars_for_completed_course(enrollment, grade):
    if enrollment.get('status') != 'completed' or not grade:
        return 0
    try:
        final_grade = float(grade.get('final_grade'))
    except (TypeError, ValueError):
        return 0
    if final_grade >= 95:
        return 5
    if final_grade >= 90:
        return 4
    if final_grade >= 85:
        return 3
    if final_grade >= 80:
        return 2
    # Completion is awarded only after all required assessments pass, so a
    # completed graded course below 80 still earns the passing-tier star.
    return 1


def star_display(stars):
    stars = max(0, min(5, int(stars)))
    return '★' * stars + '☆' * (5 - stars)


def _latest_key(record, field):
    return record.get(field) or ''


def _aggregate():
    users = {u['id']: u for u in user_db.get_all() if u.get('role') == 'student'}
    courses = {c['id']: c for c in course_db.get_all()}

    # Collapse accidental duplicate enrollment records by student/course. A
    # completed record wins; otherwise retain the newest enrollment.
    enrollment_map = {}
    for enrollment in enrollment_db.get_all():
        key = (enrollment.get('user_id'), enrollment.get('course_id'))
        if key[0] not in users or key[1] not in courses:
            continue
        current = enrollment_map.get(key)
        candidate_key = (enrollment.get('status') == 'completed', _latest_key(enrollment, 'enrolled_at'))
        current_key = ((current or {}).get('status') == 'completed', _latest_key(current or {}, 'enrolled_at'))
        if current is None or candidate_key > current_key:
            enrollment_map[key] = enrollment

    grade_map = {}
    for grade in grade_db.get_all():
        key = (grade.get('user_id'), grade.get('course_id'))
        current = grade_map.get(key)
        if current is None or _latest_key(grade, 'updated_at') > _latest_key(current, 'updated_at'):
            grade_map[key] = grade
    return users, courses, enrollment_map, grade_map


def _course_row(enrollment, course, grade):
    completed = enrollment.get('status') == 'completed'
    final_grade = grade.get('final_grade') if grade else None
    stars = stars_for_completed_course(enrollment, grade)
    return {
        'course_id': course['id'],
        'course_title': course.get('title', 'Untitled course'),
        'enrollment_id': enrollment['id'],
        'enrolled_at': enrollment.get('enrolled_at'),
        'progress': enrollment.get('progress', 0),
        'status': enrollment.get('status', 'in_progress'),
        'completed': completed,
        'completed_at': enrollment.get('completed_at'),
        'final_grade': final_grade,
        'stars': stars,
        'stars_display': star_display(stars),
        'certificate_id': enrollment.get('certificate_id'),
        'certificate_filename': enrollment.get('certificate_filename'),
    }


def get_student_progress(user_id):
    users, courses, enrollment_map, grade_map = _aggregate()
    user = users.get(user_id)
    if not user:
        return None
    course_rows = []
    for (student_id, course_id), enrollment in enrollment_map.items():
        if student_id == user_id:
            course_rows.append(_course_row(enrollment, courses[course_id], grade_map.get((student_id, course_id))))
    course_rows.sort(key=lambda row: (row.get('completed_at') or row.get('enrolled_at') or '', row['course_title']), reverse=True)
    completed = [row for row in course_rows if row['completed']]
    return {
        'courses': course_rows,
        'completed_courses': completed,
        'enrolled_count': len(course_rows),
        'completed_count': len(completed),
        'total_stars': sum(row['stars'] for row in completed),
    }


def get_leaderboard(sort_by='completed', page=1, per_page=25):
    users, courses, enrollment_map, grade_map = _aggregate()
    totals = {uid: {'completed_courses': 0, 'total_stars': 0} for uid in users}
    for (user_id, course_id), enrollment in enrollment_map.items():
        if enrollment.get('status') != 'completed':
            continue
        totals[user_id]['completed_courses'] += 1
        totals[user_id]['total_stars'] += stars_for_completed_course(enrollment, grade_map.get((user_id, course_id)))

    rows = []
    for user_id, user in users.items():
        rows.append({
            'student_id': user.get('student_id', ''),
            'display_name': user.get('full_name', 'Student'),
            **totals[user_id],
        })
    if sort_by == 'stars':
        rows.sort(key=lambda row: (-row['total_stars'], -row['completed_courses'], row['student_id']))
    else:
        sort_by = 'completed'
        rows.sort(key=lambda row: (-row['completed_courses'], -row['total_stars'], row['student_id']))
    for position, row in enumerate(rows, 1):
        row['rank'] = position

    per_page = max(1, min(int(per_page), 50))
    page_count = max(1, math.ceil(len(rows) / per_page))
    page = max(1, min(int(page), page_count))
    start = (page - 1) * per_page
    return {
        'rows': rows[start:start + per_page],
        'sort_by': sort_by,
        'page': page,
        'page_count': page_count,
        'total': len(rows),
    }
