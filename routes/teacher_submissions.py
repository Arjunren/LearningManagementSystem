from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from utils.decorators import teacher_required
from services.course_service import course_db, enrollment_db, get_graded_procedures
from services.grade_service import grade_db, grade_attempt, get_student_assessments, get_grade
from services.auth_service import user_db
from services.teacher_service import is_teacher_assigned

bp = Blueprint('teacher_submissions', __name__, url_prefix='/teacher/submissions')

@bp.route('/')
@teacher_required
def index():
    from services.teacher_service import get_teacher_courses
    assigned_course_ids = get_teacher_courses(session['user_id'])
    courses = [course_db.get(cid) for cid in assigned_course_ids if course_db.get(cid)]
    course_stats = []
    for c in courses:
        enrolled = len(enrollment_db.find(course_id=c['id']))
        # Count pending reviews across all students
        pending = _count_pending_reviews(c)
        course_stats.append({'course': c, 'student_count': enrolled, 'pending_reviews': pending})
    return render_template('teacher/submissions.html', courses=course_stats)


def _count_pending_reviews(course):
    """Count assessments with REVIEW status across all enrolled students."""
    enrollments = enrollment_db.find(course_id=course['id'])
    graded_procs = get_graded_procedures(course)
    count = 0
    for enr in enrollments:
        grade = get_grade(enr['user_id'], course['id'])
        if not grade:
            continue
        assessments = grade.get('assessments', {})
        for proc in graded_procs:
            a = assessments.get(proc['id'], {})
            if a.get('current_status') == 'REVIEW':
                count += 1
    return count


@bp.route('/<course_id>', methods=['GET', 'POST'])
@teacher_required
def detail(course_id):
    if not is_teacher_assigned(session['user_id'], course_id):
        flash("You are not assigned to this course.", "danger")
        return redirect(url_for('teacher_submissions.index'))

    course = course_db.get(course_id)
    if not course:
        flash("Course not found.", "danger")
        return redirect(url_for('teacher_submissions.index'))

    graded_procedures = get_graded_procedures(course)

    if request.method == 'POST':
        user_id = request.form.get('user_id')
        if not user_id:
            flash("No student specified.", "danger")
            return redirect(url_for('teacher_submissions.detail', course_id=course_id))

        saved_count = 0
        
        # Iterate over all form fields to find scores
        # Field format: "score_{procedure_id}_{attempt_id}" or "score_{procedure_id}"
        
        for key, value in request.form.items():
            if key.startswith('score_') and value.strip() != '':
                key_content = key[len('score_'):]
                if '_att_' in key_content:
                    proc_id, attempt_part = key_content.split('_att_', 1)
                    attempt_id = 'att_' + attempt_part
                else:
                    proc_id = key_content
                    attempt_id = None
                    
                try:
                    score = float(value)
                    grade_id, status = grade_attempt(
                        user_id, course_id, proc_id, score,
                        graded_by=session['user_id'],
                        attempt_id=attempt_id
                    )
                    if grade_id:
                        saved_count += 1
                except ValueError:
                    flash(f"Invalid score format. Skipped.", "warning")

        if saved_count:
            flash(f"Grades saved ({saved_count} assessment(s) updated).", "success")
        return redirect(url_for('teacher_submissions.detail', course_id=course_id))

    enrollments = enrollment_db.find(course_id=course_id)
    students = []
    for enr in enrollments:
        user = user_db.get(enr['user_id'])
        if user:
            grade = get_grade(user['id'], course_id)
            assessments = get_student_assessments(grade, graded_procedures)
            students.append({
                'user': user,
                'enrollment': enr,
                'grade': grade,
                'assessments': assessments
            })

    # Sort: students with pending REVIEW items first
    def _sort_key(s):
        return -sum(1 for a in s['assessments'] if a.get('current_status') == 'REVIEW')

    students.sort(key=_sort_key)

    return render_template('teacher/submission_detail.html',
                           course=course,
                           students=students,
                           graded_procedures=graded_procedures)
