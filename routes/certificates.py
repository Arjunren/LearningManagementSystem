from flask import Blueprint, render_template, request, redirect, url_for, flash, send_from_directory, session, jsonify
from utils.decorators import student_required
from services.certificate_service import (generate_certificate, reserve_certificate_id,
                                          release_certificate_id, ensure_certificate_indexes)
from services.certificate_db_service import get_template, get_template_for_course
from services.course_service import get_enrollment, get_course, enrollment_db
from services.email_service import send_email_with_attachment
from services.auth_service import get_user_by_id
from config import Config
import os
import datetime

bp = Blueprint('certificates', __name__, url_prefix='/certificates')

CERT_RESEND_COOLDOWN_HOURS = 24

def _now():
    return datetime.datetime.now(datetime.timezone.utc)

def _can_resend(enrollment):
    last_sent = enrollment.get('cert_last_sent_at')
    if not last_sent:
        return True
    try:
        last = datetime.datetime.fromisoformat(last_sent)
        if last.tzinfo is None:
            last = last.replace(tzinfo=datetime.timezone.utc)
        diff = _now() - last
        return diff.total_seconds() > CERT_RESEND_COOLDOWN_HOURS * 3600
    except Exception:
        return True

@bp.route('/generate/<enrollment_id>', methods=['POST'])
@student_required
def generate(enrollment_id):
    enrollment = get_enrollment(enrollment_id)
    if not enrollment or enrollment['user_id'] != session['user_id']:
        flash("Unauthorized", "danger")
        return redirect(url_for('user.dashboard'))

    # Backend eligibility gate — never trust frontend
    from services.grade_service import check_certificate_eligibility
    eligible, reason = check_certificate_eligibility(session['user_id'], enrollment['course_id'])
    if not eligible:
        flash(f"Certificate not available: {reason}", "warning")
        return redirect(url_for('courses.learn', enrollment_id=enrollment_id))

    if enrollment.get('certificate_id'):
        return redirect(url_for('certificates.view', cert_id=enrollment['certificate_id'], enrollment_id=enrollment_id))

    course = get_course(enrollment['course_id'])
    user = get_user_by_id(session['user_id'])

    # Get template for this course
    template_config = None
    template_id = course.get('certificate_template_id')
    if template_id:
        template_config = get_template(template_id)
    if not template_config:
        template_config = get_template_for_course(course['id'])

    ensure_certificate_indexes()
    try:
        cert_id = reserve_certificate_id(enrollment_id)
        cert_id, cert_filename, pdf_generated = generate_certificate(
            student_name=user['full_name'],
            course_name=course['title'],
            template_config=template_config,
            cert_id=cert_id,
            instructor_name=course.get('instructor', ''),
            completion_date=enrollment.get('completed_at')
        )
    except (RuntimeError, ValueError):
        flash('Unable to issue a certificate right now. Please try again.', 'danger')
        return redirect(url_for('courses.learn', enrollment_id=enrollment_id))

    # Always save the certificate record regardless of PDF success
    update_data = {
        'certificate_id': cert_id,
        'status': 'completed',
        'completed_at': datetime.datetime.now(datetime.timezone.utc).isoformat()
    }
    if pdf_generated:
        update_data['certificate_filename'] = cert_filename

    if not enrollment_db.update(enrollment_id, update_data):
        release_certificate_id(cert_id, enrollment_id)
        flash('Unable to save the certificate. Please try again.', 'danger')
        return redirect(url_for('courses.learn', enrollment_id=enrollment_id))

    if not pdf_generated:
        # PDF failed — automatically send certificate details via email as fallback
        verify_url = f"https://buildbyteacademy.vercel.app/certificate.html?id={cert_id}"
        html_body = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <h2 style="color: #4f46e5;">🎓 Congratulations, {user['full_name']}!</h2>
            <p>You have successfully completed: <strong>{course['title']}</strong></p>
            <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 20px; margin: 20px 0;">
                <p style="margin: 4px 0;"><strong>Certificate ID:</strong> {cert_id}</p>
                <p style="margin: 4px 0;"><strong>Course:</strong> {course['title']}</p>
                <p style="margin: 4px 0;"><strong>Student:</strong> {user['full_name']}</p>
                <p style="margin: 4px 0;"><strong>Date:</strong> {datetime.datetime.now().strftime("%B %d, %Y")}</p>
            </div>
            <p>You can verify your certificate online:</p>
            <a href="{verify_url}" style="display: inline-block; background: #4f46e5; color: white; padding: 10px 24px; border-radius: 6px; text-decoration: none; font-weight: bold;">Verify Certificate</a>
            <p style="margin-top: 20px; color: #64748b; font-size: 13px;">Congratulations on completing your course at <strong>BuildByte Academy</strong>!</p>
        </div>
        """

        from services.email_service import send_email
        email_sent = send_email(
            to_email=user['email'],
            subject=f"BuildByte Academy — Certificate of Completion: {course['title']}",
            html_content=html_body
        )

        if email_sent:
            flash("Certificate created! PDF is temporarily unavailable, but certificate details have been sent to your email.", "success")
        else:
            flash("Certificate created! You can view it online. PDF download is temporarily unavailable.", "warning")
    else:
        flash("Certificate generated successfully!", "success")

    return redirect(url_for('certificates.view', cert_id=cert_id, enrollment_id=enrollment_id))


@bp.route('/eligibility/<enrollment_id>')
@student_required
def eligibility(enrollment_id):
    """JSON endpoint for student UI to check certificate eligibility."""
    enrollment = get_enrollment(enrollment_id)
    if not enrollment or enrollment['user_id'] != session['user_id']:
        from flask import jsonify
        return jsonify({'eligible': False, 'reason': 'Unauthorized'}), 403

    from services.grade_service import check_certificate_eligibility
    from flask import jsonify
    eligible, reason = check_certificate_eligibility(session['user_id'], enrollment['course_id'])
    return jsonify({'eligible': eligible, 'reason': reason})

@bp.route('/view/<cert_id>')
@bp.route('/view/<cert_id>/<enrollment_id>')
@student_required
def view(cert_id, enrollment_id=None):
    enrollments = enrollment_db.find(certificate_id=cert_id, user_id=session['user_id'])
    if enrollment_id:
        enrollments = [enrollment for enrollment in enrollments if enrollment['id'] == enrollment_id]
    if not enrollments:
        flash("Certificate not found or unauthorized.", "danger")
        return redirect(url_for('user.dashboard'))

    enrollment = enrollments[0]
    course = get_course(enrollment['course_id'])
    user = get_user_by_id(session['user_id'])
    can_resend = _can_resend(enrollment)

    # Get template for this course
    template_config = None
    template_id = course.get('certificate_template_id')
    if template_id:
        template_config = get_template(template_id)
    if not template_config:
        template_config = get_template_for_course(course['id'])

    return render_template('user/certificate.html',
                           enrollment=enrollment,
                           course=course,
                           user=user,
                           can_resend=can_resend,
                           template_config=template_config)

@bp.route('/verify/<cert_id>')
def verify(cert_id):
    """Public verification page."""
    ensure_certificate_indexes()
    enrollments = enrollment_db.find(certificate_id=cert_id)
    if len(enrollments) != 1:
        return render_template('public/verify_certificate.html', valid=False, cert_id=cert_id)
        
    enrollment = enrollments[0]
    course = get_course(enrollment['course_id'])
    student = get_user_by_id(enrollment['user_id'])
    
    if not course or not student:
        return render_template('public/verify_certificate.html', valid=False, cert_id=cert_id)
    return render_template('public/verify_certificate.html', 
                           valid=True, 
                           cert_id=cert_id,
                           enrollment=enrollment,
                           course=course,
                           student=student)

@bp.route('/api/verify/<cert_id>')
def api_verify(cert_id):
    """API endpoint for Vercel frontend verification."""
    ensure_certificate_indexes()
    enrollments = enrollment_db.find(certificate_id=cert_id)
    if len(enrollments) != 1:
        return jsonify({'valid': False, 'message': 'Certificate not found'}), 404
        
    enrollment = enrollments[0]
    course = get_course(enrollment['course_id'])
    student = get_user_by_id(enrollment['user_id'])
    if not course or not student:
        return jsonify({'valid': False, 'message': 'Certificate not found'}), 404
    
    template_config = None
    template_id = course.get('certificate_template_id')
    if template_id:
        template_config = get_template(template_id)
    if not template_config:
        template_config = get_template_for_course(course['id'])
        
    return jsonify({
        'valid': True,
        'cert_id': cert_id,
        'student_name': student['full_name'],
        'student_id': student.get('student_id'),
        'course_title': course['title'],
        'completed_at': enrollment.get('completed_at'),
        'template_config': template_config
    })

@bp.route('/send/<enrollment_id>', methods=['POST'])
@student_required
def send(enrollment_id):
    enrollment = get_enrollment(enrollment_id)
    if not enrollment or enrollment['user_id'] != session['user_id']:
        flash("Unauthorized", "danger")
        return redirect(url_for('user.dashboard'))

    if not enrollment.get('certificate_id'):
        flash("No certificate found for this course.", "warning")
        return redirect(url_for('user.dashboard'))

    if not _can_resend(enrollment):
        flash("Certificate already sent recently. Please wait 24 hours before resending.", "warning")
        return redirect(url_for('certificates.view', cert_id=enrollment['certificate_id'], enrollment_id=enrollment_id))

    cert_filename = enrollment.get('certificate_filename')
    cert_path = os.path.join(Config.CERTIFICATES_DIR, cert_filename) if cert_filename else None
    course = get_course(enrollment['course_id'])
    user = get_user_by_id(session['user_id'])

    html_body = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <h2 style="color: #4f46e5;">🎓 Congratulations, {user['full_name']}!</h2>
        <p>You have successfully completed: <strong>{course['title']}</strong></p>
        <p>Your certificate is attached to this email.</p>
        <p>Congratulations on completing your course at <strong>BuildByte Academy</strong>!</p>
    </div>
    """

    success = send_email_with_attachment(
        to_email=user['email'],
        subject=f"BuildByte Academy — Certificate of Completion: {course['title']}",
        html_content=html_body,
        attachment_path=cert_path,
        attachment_name=f"Certificate_{course['title'].replace(' ', '_')}.pdf"
    )

    if success:
        enrollment_db.update(enrollment_id, {'cert_last_sent_at': _now().isoformat()})
        flash("Certificate sent to your registered email!", "success")
    else:
        flash("Failed to send certificate email. Please check SMTP settings.", "danger")

    return redirect(url_for('certificates.view', cert_id=enrollment['certificate_id'], enrollment_id=enrollment_id))

@bp.route('/download/<filename>')
@student_required
def download(filename):
    if filename != os.path.basename(filename) or '..' in filename or filename.startswith('/'):
        return "Invalid filename", 400
    # Verify ownership
    enrollments = [enrollment for enrollment in enrollment_db.find(user_id=session['user_id'])
                   if enrollment.get('certificate_filename') == filename]
    if not enrollments:
        flash("Unauthorized", "danger")
        return redirect(url_for('user.dashboard'))
    return send_from_directory(Config.CERTIFICATES_DIR, filename, as_attachment=True)
