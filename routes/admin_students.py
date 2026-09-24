from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from utils.decorators import admin_required
from services.course_service import course_db, enrollment_db, get_graded_procedures
from services.grade_service import grade_db, grade_attempt, get_student_assessments, get_grade
from services.auth_service import user_db

bp = Blueprint('admin_students', __name__, url_prefix='/admin/submissions')


@bp.route('/')
@admin_required
def index():
    courses = course_db.get_all()
    course_stats = []
    for c in courses:
        enrolled = len(enrollment_db.find(course_id=c['id']))
        pending = _count_pending_reviews(c)
        course_stats.append({'course': c, 'student_count': enrolled, 'pending_reviews': pending})
    return render_template('admin/submissions.html', courses=course_stats)


def _count_pending_reviews(course):
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
@admin_required
def detail(course_id):
    course = course_db.get(course_id)
    if not course:
        flash("Course not found.", "danger")
        return redirect(url_for('admin_students.index'))

    graded_procedures = get_graded_procedures(course)

    if request.method == 'POST':
        user_id = request.form.get('user_id')
        if not user_id:
            flash("No student specified.", "danger")
            return redirect(url_for('admin_students.detail', course_id=course_id))

        saved_count = 0
        for proc in graded_procedures:
            field_name = f"score_{proc['id']}"
            raw = request.form.get(field_name)
            if raw is not None and raw.strip() != '':
                try:
                    score = float(raw)
                    grade_id, status = grade_attempt(
                        user_id, course_id, proc['id'], score,
                        graded_by=session['user_id']
                    )
                    if grade_id:
                        saved_count += 1
                except ValueError:
                    flash(f"Invalid score for '{proc['title']}'. Skipped.", "warning")

        flash(f"Grades saved ({saved_count} assessment(s) updated).", "success")
        return redirect(url_for('admin_students.detail', course_id=course_id))

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

    def _sort_key(s):
        return -sum(1 for a in s['assessments'] if a.get('current_status') == 'REVIEW')

    students.sort(key=_sort_key)

    return render_template('admin/submission_detail.html',
                           course=course,
                           students=students,
                           graded_procedures=graded_procedures)
