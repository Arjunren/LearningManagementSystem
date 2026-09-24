from services.json_database import JSONDatabase
import datetime
import uuid

grade_db = JSONDatabase('grades')

# ---------- helpers ----------

def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def _new_attempt_id():
    return f"att_{uuid.uuid4().hex[:10]}"

# ─────────────────────────────────────────────────────────────────────────────
# DATA MIGRATION: convert old flat {proc_id: {score, updated_at}} to new format
# ─────────────────────────────────────────────────────────────────────────────
def _migrate_grade_record(grade):
    """
    If a grade record still uses the old flat scores dict, migrate it in-place
    to the new attempt-based format. Idempotent.
    """
    if 'assessments' in grade:
        return grade  # already migrated

    old_scores = grade.get('scores', {})
    if not old_scores:
        grade['assessments'] = {}
        return grade

    # We need the course to look up passing scores
    from services.course_service import get_course
    course = get_course(grade.get('course_id', ''))
    proc_map = {}
    if course:
        for p in course.get('procedures', []):
            proc_map[p['id']] = p

    assessments = {}
    for proc_id, entry in old_scores.items():
        score = float(entry.get('score', 0))
        proc = proc_map.get(proc_id, {})
        max_score = float(proc.get('max_score', 100))
        passing_score = float(proc.get('passing_score', 0))
        status = 'PASSED' if score >= passing_score else 'FAILED'
        attempt = {
            'attempt_id': _new_attempt_id(),
            'attempt_number': 1,
            'score': score,
            'max_score': max_score,
            'passing_score': passing_score,
            'status': status,
            'graded_by': None,
            'submitted_at': entry.get('updated_at', _now()),
            'graded_at': entry.get('updated_at', _now()),
        }
        assessments[proc_id] = {
            'current_status': status,
            'retake_available': status == 'FAILED',
            'attempts': [attempt]
        }

    grade['assessments'] = assessments
    # Remove old key so we don't confuse things
    grade.pop('scores', None)
    grade_db.save(grade['id'], grade)
    return grade


# ─────────────────────────────────────────────────────────────────────────────
# RETRIEVAL
# ─────────────────────────────────────────────────────────────────────────────

def get_user_grades(user_id):
    grades = grade_db.find(user_id=user_id)
    return [_migrate_grade_record(g) for g in grades]

def get_grade(user_id, course_id):
    g = grade_db.find_one(user_id=user_id, course_id=course_id)
    if g:
        return _migrate_grade_record(g)
    return None

def _ensure_grade_record(user_id, course_id):
    """Get or create a grade record for the user+course."""
    existing = get_grade(user_id, course_id)
    if existing:
        return existing
    data = {
        'user_id': user_id,
        'course_id': course_id,
        'assessments': {},
        'final_grade': 0.0,
        'created_at': _now(),
        'updated_at': _now(),
    }
    grade_id = grade_db.create(data, prefix="grd")
    return grade_db.get(grade_id)


# ─────────────────────────────────────────────────────────────────────────────
# STATE MACHINE
# ─────────────────────────────────────────────────────────────────────────────

def submit_for_review(user_id, course_id, procedure_id, max_score=100, passing_score=0):
    """
    Student marks a graded assessment as ready for teacher review.
    Creates a pending (REVIEW) attempt if one doesn't already exist.
    Returns the grade_id.
    """
    grade = _ensure_grade_record(user_id, course_id)
    assessments = grade.get('assessments', {})
    existing = assessments.get(procedure_id, {})
    current_status = existing.get('current_status', 'NOT_STARTED')

    # Only allow submission if not already REVIEW or PASSED
    if current_status == 'PASSED':
        return grade['id']  # already passed, nothing to do

    # If FAILED and retake_available, start a retake (new attempt)
    attempts = existing.get('attempts', [])
    attempt_number = len(attempts) + 1

    new_attempt = {
        'attempt_id': _new_attempt_id(),
        'attempt_number': attempt_number,
        'score': None,
        'max_score': float(max_score),
        'passing_score': float(passing_score),
        'status': 'REVIEW',
        'graded_by': None,
        'submitted_at': _now(),
        'graded_at': None,
    }

    attempts.append(new_attempt)
    assessments[procedure_id] = {
        'current_status': 'REVIEW',
        'retake_available': False,
        'attempts': attempts,
    }

    grade_db.update(grade['id'], {
        'assessments': assessments,
        'updated_at': _now(),
    })
    return grade['id']


def grade_attempt(user_id, course_id, procedure_id, score, graded_by, attempt_id=None):
    """
    Teacher/Admin grades an attempt. If attempt_id is provided, edits that specific attempt.
    Otherwise, finds the latest REVIEW attempt.
    Backend derives PASSED/FAILED from passing_score.
    Triggers notifications for the student.
    Returns (grade_id, status) where status is 'PASSED' or 'FAILED'.
    """
    grade = get_grade(user_id, course_id)
    if not grade:
        return None, None

    assessments = grade.get('assessments', {})
    assessment = assessments.get(procedure_id)
    if not assessment:
        return grade['id'], None

    attempts = assessment.get('attempts', [])
    
    target_idx = None
    if attempt_id:
        for i, a in enumerate(attempts):
            if a['attempt_id'] == attempt_id:
                target_idx = i
                break
    else:
        # Find the latest REVIEW attempt
        for i in reversed(range(len(attempts))):
            if attempts[i]['status'] == 'REVIEW':
                target_idx = i
                break

    if target_idx is None:
        return grade['id'], None  # nothing found to grade

    attempt = attempts[target_idx]
    score = float(score)
    passing_score = float(attempt.get('passing_score', 0))
    max_score = float(attempt.get('max_score', 100))

    status = 'PASSED' if score >= passing_score else 'FAILED'
    old_status = attempt.get('status')
    is_new_grade = old_status == 'REVIEW'

    attempts[target_idx] = {
        **attempt,
        'score': score,
        'status': status,
        'graded_by': graded_by,
        'graded_at': _now(),
    }

    # Only update current_status if we are grading the LATEST attempt.
    # Editing a historical attempt shouldn't change the current overall status
    # UNLESS it's the only attempt or it was previously the latest.
    if target_idx == len(attempts) - 1:
        assessments[procedure_id] = {
            'current_status': status,
            'retake_available': status == 'FAILED',
            'attempts': attempts,
        }
    else:
        assessments[procedure_id]['attempts'] = attempts

    # Recalculate final grade
    final_grade = _recalculate_final(assessments)

    grade_db.update(grade['id'], {
        'assessments': assessments,
        'final_grade': final_grade,
        'updated_at': _now(),
    })
    
    from services.notification_service import create_notification
    from services.course_service import get_course
    course = get_course(course_id)
    proc_title = next((p['title'] for p in course.get('procedures', []) if p['id'] == procedure_id), "Assessment")
    
    # Trigger notification
    if is_new_grade or old_status != status:
        if status == 'PASSED':
            create_notification(
                user_id, 'assessment_passed', 'Assessment Passed',
                f"You passed {proc_title} with a score of {score}/{max_score}.",
                course_id=course_id, procedure_id=procedure_id
            )
        else:
            create_notification(
                user_id, 'assessment_failed', 'Assessment Failed',
                f"You scored {score}/{max_score} on {proc_title}. A retake is available.",
                course_id=course_id, procedure_id=procedure_id
            )

    # After grading, re-check course completion
    _check_completion(user_id, course_id)

    return grade['id'], status


def start_retake(user_id, course_id, procedure_id):
    """
    Student initiates a retake for a failed assessment.
    Creates a new REVIEW attempt without touching previous attempts.
    """
    grade = get_grade(user_id, course_id)
    if not grade:
        return False

    assessments = grade.get('assessments', {})
    assessment = assessments.get(procedure_id)
    if not assessment:
        return False

    if not assessment.get('retake_available', False):
        return False

    # Get passing/max score from the last attempt
    attempts = assessment.get('attempts', [])
    if not attempts:
        return False
    last = attempts[-1]

    new_attempt = {
        'attempt_id': _new_attempt_id(),
        'attempt_number': len(attempts) + 1,
        'score': None,
        'max_score': last.get('max_score', 100),
        'passing_score': last.get('passing_score', 0),
        'status': 'REVIEW',
        'graded_by': None,
        'submitted_at': _now(),
        'graded_at': None,
    }

    attempts.append(new_attempt)
    assessments[procedure_id] = {
        'current_status': 'REVIEW',
        'retake_available': False,
        'attempts': attempts,
    }

    grade_db.update(grade['id'], {
        'assessments': assessments,
        'updated_at': _now(),
    })
    return True


# ─────────────────────────────────────────────────────────────────────────────
# ELIGIBILITY — Single Source of Truth
# ─────────────────────────────────────────────────────────────────────────────

def check_certificate_eligibility(user_id, course_id):
    """
    Authoritative backend function. Returns (eligible: bool, reason: str).
    
    Certificate eligible if:
      - All required procedures are completed in enrollment
      - All required GRADED procedures have current_status == 'PASSED'
    """
    from services.course_service import (
        enrollment_db, get_course, get_graded_procedures, get_required_procedures
    )

    enrollment = enrollment_db.find_one(user_id=user_id, course_id=course_id)
    if not enrollment:
        return False, "Enrollment not found"

    course = get_course(course_id)
    if not course:
        return False, "Course not found"

    completed_procs = set(enrollment.get('completed_procedures', []))
    required_procs = get_required_procedures(course)

    # Check all required content is marked complete
    for proc in required_procs:
        if proc['id'] not in completed_procs:
            return False, f"Procedure '{proc['title']}' has not been completed"

    # Check all required graded assessments are PASSED
    required_graded = [p for p in get_graded_procedures(course) if p.get('required', False)]
    if not required_graded:
        # No required graded assessments — content completion is enough
        if len(required_procs) == 0 or all(p['id'] in completed_procs for p in required_procs):
            return True, "Eligible"
        return False, "Not all required content is complete"

    grade = get_grade(user_id, course_id)
    assessments = grade.get('assessments', {}) if grade else {}

    for proc in required_graded:
        assessment = assessments.get(proc['id'])
        if not assessment:
            return False, f"Assessment '{proc['title']}' has not been submitted"
        status = assessment.get('current_status', 'NOT_STARTED')
        if status == 'REVIEW':
            return False, f"Assessment '{proc['title']}' is waiting for teacher grading"
        if status == 'FAILED':
            return False, f"Assessment '{proc['title']}' has not been passed"
        if status not in ('PASSED',):
            return False, f"Assessment '{proc['title']}' has not been completed"

    return True, "Eligible"


# ─────────────────────────────────────────────────────────────────────────────
# DISPLAY HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def get_assessment_status(grade, procedure_id):
    """Returns the current assessment dict for a procedure, or defaults."""
    if not grade:
        return {'current_status': 'NOT_STARTED', 'retake_available': False, 'attempts': []}
    assessments = grade.get('assessments', {})
    return assessments.get(procedure_id, {
        'current_status': 'NOT_STARTED',
        'retake_available': False,
        'attempts': []
    })


def get_student_assessments(grade, graded_procedures):
    """
    Returns a list of dicts for display, merging procedure config with assessment state.
    """
    assessments = {}
    if grade:
        assessments = grade.get('assessments', {})

    result = []
    for proc in graded_procedures:
        proc_id = proc['id']
        assessment = assessments.get(proc_id, {
            'current_status': 'NOT_STARTED',
            'retake_available': False,
            'attempts': []
        })
        attempts = assessment.get('attempts', [])
        current_status = assessment.get('current_status', 'NOT_STARTED')
        retake_available = assessment.get('retake_available', False)

        # Get the latest graded score for display
        latest_graded = next(
            (a for a in reversed(attempts) if a.get('score') is not None), None
        )
        score_val = latest_graded['score'] if latest_graded else None
        max_score = float(proc.get('max_score', 100))
        passing_score = float(proc.get('passing_score', 0))
        percentage = round((score_val / max_score) * 100, 1) if score_val is not None and max_score > 0 else None

        result.append({
            'id': proc_id,
            'title': proc['title'],
            'type': proc.get('type', ''),
            'max_score': max_score,
            'passing_score': passing_score,
            'score': score_val,
            'percentage': percentage,
            'current_status': current_status,
            'retake_available': retake_available,
            'attempts': attempts,
            # Legacy compat field
            'status': current_status,
        })
    return result


# ─────────────────────────────────────────────────────────────────────────────
# INTERNAL
# ─────────────────────────────────────────────────────────────────────────────

def _recalculate_final(assessments):
    """Recalculate weighted final from latest attempt score per procedure."""
    if not assessments:
        return 0.0
    total_weight = 0
    total_earned = 0.0
    for proc_id, assessment in assessments.items():
        attempts = assessment.get('attempts', [])
        latest = next((a for a in reversed(attempts) if a.get('score') is not None), None)
        if latest:
            max_score = float(latest.get('max_score', 100))
            score = float(latest.get('score', 0))
            total_earned += (score / max_score * 100) if max_score > 0 else 0
            total_weight += 1
    return round(total_earned / total_weight, 2) if total_weight > 0 else 0.0


def _check_completion(user_id, course_id):
    from services.course_service import enrollment_db, check_course_completion
    enrollment = enrollment_db.find_one(user_id=user_id, course_id=course_id)
    if enrollment:
        check_course_completion(enrollment['id'])


# Legacy shim — kept so any remaining callers don't break immediately
def update_single_score(user_id, course_id, procedure_id, score, graded_procedures):
    """
    DEPRECATED: Use grade_attempt() instead.
    This shim routes legacy calls through the new attempt-based grader.
    """
    proc = next((p for p in graded_procedures if p['id'] == procedure_id), {})
    passing_score = float(proc.get('passing_score', 0))
    max_score = float(proc.get('max_score', 100))

    grade = _ensure_grade_record(user_id, course_id)
    assessments = grade.get('assessments', {})
    existing = assessments.get(procedure_id, {})

    # If no REVIEW attempt exists, create one then grade it
    if existing.get('current_status') not in ('REVIEW',):
        submit_for_review(user_id, course_id, procedure_id, max_score, passing_score)

    grade_attempt(user_id, course_id, procedure_id, score, graded_by=None)
    return grade['id']


def get_passing_status(score, passing_score):
    """Returns 'PASSED' or 'FAILED'. Legacy helper."""
    try:
        return "PASSED" if float(score) >= float(passing_score) else "FAILED"
    except (TypeError, ValueError):
        return "N/A"
