from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from utils.decorators import student_required
from services.course_service import (
    get_all_courses, get_course, enroll_user, get_enrollment,
    update_progress, get_graded_procedures, enrollment_db
)
from services.grade_service import (
    submit_for_review, start_retake, check_certificate_eligibility,
    get_assessment_status, get_grade
)

bp = Blueprint('courses', __name__, url_prefix='/courses')

@bp.route('/')
@student_required
def index():
    courses = get_all_courses()
    from services.course_service import get_user_enrollments
    enrollments = get_user_enrollments(session['user_id'])
    enrolled_course_ids = [e['course_id'] for e in enrollments]
    return render_template('user/courses.html', courses=courses, enrolled_course_ids=enrolled_course_ids)

@bp.route('/<course_id>')
@student_required
def detail(course_id):
    course = get_course(course_id)
    if not course:
        flash("Course not found.", "danger")
        return redirect(url_for('courses.index'))

    from services.course_service import get_user_enrollments
    enrollments = get_user_enrollments(session['user_id'])
    enrolled = any(e['course_id'] == course_id for e in enrollments)
    return render_template('user/course_detail.html', course=course, enrolled=enrolled)

@bp.route('/<course_id>/enroll', methods=['POST'])
@student_required
def enroll(course_id):
    enrollment_id, msg = enroll_user(session['user_id'], course_id)
    flash(msg, "success" if "Success" in msg else "info")
    return redirect(url_for('user.dashboard'))

@bp.route('/learn/<enrollment_id>')
@student_required
def learn(enrollment_id):
    enrollment = get_enrollment(enrollment_id)
    if not enrollment or enrollment['user_id'] != session['user_id']:
        flash("Unauthorized", "danger")
        return redirect(url_for('user.dashboard'))

    course = get_course(enrollment['course_id'])

    # Build assessment status map for all graded procedures
    user_id = session['user_id']
    grade = get_grade(user_id, enrollment['course_id'])
    graded_procs = get_graded_procedures(course)
    assessment_status_map = {}
    for proc in graded_procs:
        assessment_status_map[proc['id']] = get_assessment_status(grade, proc['id'])

    # Check certificate eligibility
    cert_eligible, cert_reason = check_certificate_eligibility(user_id, enrollment['course_id'])

    # Check if celebration should show (and clear the flag)
    show_celebration = enrollment.get('celebration_pending', False)
    if show_celebration:
        enrollment_db.update(enrollment_id, {'celebration_pending': False})

    return render_template('user/course_learn.html',
                           course=course,
                           enrollment=enrollment,
                           show_celebration=show_celebration,
                           assessment_status_map=assessment_status_map,
                           cert_eligible=cert_eligible,
                           cert_reason=cert_reason)


@bp.route('/complete_procedure/<enrollment_id>/<procedure_id>', methods=['POST'])
@student_required
def complete_procedure(enrollment_id, procedure_id):
    enrollment = get_enrollment(enrollment_id)
    if not enrollment or enrollment['user_id'] != session['user_id']:
        flash("Unauthorized", "danger")
        return redirect(url_for('user.dashboard'))

    course = get_course(enrollment['course_id'])
    if not course:
        return redirect(url_for('user.dashboard'))

    # Find the procedure definition
    proc = next((p for p in course.get('procedures', []) if p['id'] == procedure_id), None)
    if not proc:
        flash("Procedure not found.", "danger")
        return redirect(url_for('courses.learn', enrollment_id=enrollment_id))

    is_graded = proc.get('graded', False) and proc.get('type') in ('quiz', 'activity', 'project')

    # Always mark content as complete in enrollment
    update_progress(enrollment_id, procedure_id)

    if is_graded:
        # For graded procedures: submit for review (do NOT auto-pass)
        max_score = float(proc.get('max_score', 100))
        passing_score = float(proc.get('passing_score', 0))
        submit_for_review(
            session['user_id'],
            enrollment['course_id'],
            procedure_id,
            max_score=max_score,
            passing_score=passing_score
        )
        flash("Work submitted for teacher review. Your grade will be posted once reviewed.", "info")
    else:
        flash("Procedure marked as completed!", "success")

    return redirect(url_for('courses.learn', enrollment_id=enrollment_id))


@bp.route('/retake/<enrollment_id>/<procedure_id>', methods=['POST'])
@student_required
def retake_procedure(enrollment_id, procedure_id):
    """Student initiates a retake for a failed assessment."""
    enrollment = get_enrollment(enrollment_id)
    if not enrollment or enrollment['user_id'] != session['user_id']:
        flash("Unauthorized", "danger")
        return redirect(url_for('user.dashboard'))

    success = start_retake(session['user_id'], enrollment['course_id'], procedure_id)
    if success:
        flash("Retake submitted for teacher review. Your new attempt is now pending grading.", "info")
    else:
        flash("Retake not available for this assessment.", "warning")

    return redirect(url_for('courses.learn', enrollment_id=enrollment_id))
