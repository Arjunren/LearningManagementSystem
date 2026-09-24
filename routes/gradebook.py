from flask import Blueprint, render_template, session
from utils.decorators import student_required
from services.grade_service import get_user_grades, get_student_assessments
from services.course_service import get_course, get_graded_procedures

bp = Blueprint('gradebook', __name__, url_prefix='/gradebook')

@bp.route('/')
@student_required
def index():
    grades = get_user_grades(session['user_id'])
    from services.course_service import get_user_enrollments
    enrollments = get_user_enrollments(session['user_id'])

    gradebook_data = []
    for enr in enrollments:
        course = get_course(enr['course_id'])
        if not course:
            continue
        grade = next((g for g in grades if g['course_id'] == enr['course_id']), None)
        graded_procs = get_graded_procedures(course)
        assessments = get_student_assessments(grade, graded_procs)

        gradebook_data.append({
            'enrollment': enr,
            'course': course,
            'grade': grade,
            'assessments': assessments
        })

    return render_template('user/gradebook.html', gradebook=gradebook_data)
