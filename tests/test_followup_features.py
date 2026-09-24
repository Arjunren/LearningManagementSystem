import io
import unittest
from pathlib import Path
from unittest.mock import patch

from app import create_app
from services.course_service import sanitize_handout_html
from services.student_progress_service import get_leaderboard, stars_for_completed_course


class FollowUpFeatureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False, SECRET_KEY='test-only')

    def setUp(self):
        self.client = self.app.test_client()

    def login_student(self, user_id='student-1'):
        with self.client.session_transaction() as session:
            session.update(user_id=user_id, user_name='Student One', role='student')

    def login_teacher(self, user_id='teacher-1'):
        with self.client.session_transaction() as session:
            session.update(user_id=user_id, user_name='Teacher One', role='teacher')

    def login_admin(self):
        with self.client.session_transaction() as session:
            session['admin_id'] = 'admin-1'

    def test_star_thresholds_and_incomplete_guard(self):
        complete = {'status': 'completed'}
        self.assertEqual(stars_for_completed_course(complete, {'final_grade': 95}), 5)
        self.assertEqual(stars_for_completed_course(complete, {'final_grade': 90}), 4)
        self.assertEqual(stars_for_completed_course(complete, {'final_grade': 85}), 3)
        self.assertEqual(stars_for_completed_course(complete, {'final_grade': 80}), 2)
        self.assertEqual(stars_for_completed_course(complete, {'final_grade': 79}), 1)
        self.assertEqual(stars_for_completed_course(complete, None), 0)
        self.assertEqual(stars_for_completed_course({'status': 'in_progress'}, {'final_grade': 100}), 0)

    def test_leaderboard_sorting_tie_breakers_and_pagination(self):
        users = [
            {'id': 'u1', 'role': 'student', 'student_id': 'STU-002', 'full_name': 'Two Courses'},
            {'id': 'u2', 'role': 'student', 'student_id': 'STU-001', 'full_name': 'Top Score'},
            {'id': 'u3', 'role': 'teacher', 'student_id': 'NOPE', 'full_name': 'Teacher'},
        ]
        courses = [{'id': 'c1', 'title': 'One'}, {'id': 'c2', 'title': 'Two'}]
        enrollments = [
            {'id': 'e1', 'user_id': 'u1', 'course_id': 'c1', 'status': 'completed'},
            {'id': 'e2', 'user_id': 'u1', 'course_id': 'c2', 'status': 'completed'},
            {'id': 'e3', 'user_id': 'u2', 'course_id': 'c1', 'status': 'completed'},
        ]
        grades = [
            {'user_id': 'u1', 'course_id': 'c1', 'final_grade': 80},
            {'user_id': 'u1', 'course_id': 'c2', 'final_grade': 80},
            {'user_id': 'u2', 'course_id': 'c1', 'final_grade': 100},
        ]
        with patch('services.student_progress_service.user_db.get_all', return_value=users), \
             patch('services.student_progress_service.course_db.get_all', return_value=courses), \
             patch('services.student_progress_service.enrollment_db.get_all', return_value=enrollments), \
             patch('services.student_progress_service.grade_db.get_all', return_value=grades):
            completed = get_leaderboard('completed', page=1, per_page=1)
            stars = get_leaderboard('stars', page=1, per_page=25)

        self.assertEqual(completed['rows'][0]['student_id'], 'STU-002')
        self.assertEqual(completed['page_count'], 2)
        self.assertEqual(stars['rows'][0]['student_id'], 'STU-001')
        self.assertEqual([row['rank'] for row in stars['rows']], [1, 2])

    def test_student_ranking_is_role_protected(self):
        response = self.client.get('/user/ranking')
        self.assertEqual(response.status_code, 302)
        self.login_teacher()
        response = self.client.get('/user/ranking')
        self.assertEqual(response.status_code, 302)

    def test_student_profile_renders_progress_without_cross_user_input(self):
        self.login_student('student-1')
        user = {
            'id': 'student-1', 'role': 'student', 'full_name': 'Student One',
            'email': 'one@example.test', 'student_id': 'STU-001', 'username': 'one',
            'created_at': '2026-01-01T00:00:00+00:00'
        }
        progress = {'enrolled_count': 1, 'completed_count': 1, 'total_stars': 5,
                    'completed_courses': []}
        with patch('routes.user.get_user_by_id', return_value=user), \
             patch('services.student_progress_service.get_student_progress', return_value=progress):
            response = self.client.get('/user/profile?user_id=someone-else')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'STU-001', response.data)
        self.assertNotIn(b'someone-else', response.data)

    def test_admin_student_detail_is_admin_only_and_projects_safe_fields(self):
        student = {
            'id': 'student-1', 'role': 'student', 'full_name': 'Student One',
            'username': 'student.one', 'email': 'one@example.test',
            'student_id': 'STU-001', 'created_at': '2026-01-01T00:00:00+00:00',
            'password_hash': 'DO-NOT-RENDER'
        }
        progress = {'courses': [], 'completed_count': 0, 'enrolled_count': 0, 'total_stars': 0}
        self.assertEqual(self.client.get('/admin/users/students/student-1').status_code, 302)
        self.login_admin()
        with patch('routes.admin_users.user_db.get', return_value=student), \
             patch('services.student_progress_service.get_student_progress', return_value=progress):
            response = self.client.get('/admin/users/students/student-1')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'STU-001', response.data)
        self.assertNotIn(b'DO-NOT-RENDER', response.data)

    def test_text_handout_preserves_formatting_and_removes_active_html(self):
        cleaned = sanitize_handout_html(
            '<h2>Guide</h2><p><strong>Read</strong> this.</p>'
            '<script>alert(1)</script><a href="javascript:alert(2)">unsafe</a>'
        )
        self.assertIn('<h2>Guide</h2>', cleaned)
        self.assertIn('<strong>Read</strong>', cleaned)
        self.assertNotIn('<script', cleaned)
        self.assertNotIn('javascript:', cleaned)

    def test_assigned_teacher_can_add_text_and_upload_handouts(self):
        self.login_teacher()
        course = {'id': 'course-1', 'title': 'Course', 'procedures': []}
        updates = []

        def capture_update(_course_id, data):
            updates.append(data)
            return True

        common = {
            'action': 'add_procedure', 'type': 'handout', 'title': 'Reading',
            'required': 'on', 'handout_mode': 'text',
            'handout_content': '<h2>Heading</h2><p><b>Body</b></p>'
        }
        with patch('routes.admin_courses.course_db.get', return_value=course), \
             patch('routes.admin_courses.course_db.update', side_effect=capture_update), \
             patch('routes.admin_courses._teacher_can_manage', return_value=True), \
             patch('routes.admin_courses.recalculate_course_enrollments'):
            response = self.client.post('/admin/courses/course-1/content', data=common)
        self.assertEqual(response.status_code, 302)
        text_handout = updates[-1]['procedures'][-1]
        self.assertEqual(text_handout['handout_mode'], 'text')
        self.assertIn('<h2>Heading</h2>', text_handout['content_html'])

        upload_data = {
            'action': 'add_procedure', 'type': 'handout', 'title': 'Document',
            'required': 'on', 'handout_mode': 'upload',
            'handout_file': (io.BytesIO(b'document'), 'guide.pdf')
        }
        updates.clear()
        with patch('routes.admin_courses.course_db.get', return_value=course), \
             patch('routes.admin_courses.course_db.update', side_effect=capture_update), \
             patch('routes.admin_courses._teacher_can_manage', return_value=True), \
             patch('routes.admin_courses._save_handout_upload', return_value=('handouts/safe.pdf', None)), \
             patch('routes.admin_courses.recalculate_course_enrollments'):
            response = self.client.post('/admin/courses/course-1/content', data=upload_data,
                                        content_type='multipart/form-data')
        self.assertEqual(response.status_code, 302)
        uploaded = updates[-1]['procedures'][-1]
        self.assertEqual(uploaded['handout_mode'], 'upload')
        self.assertEqual(uploaded['file_url'], 'handouts/safe.pdf')

    def test_unassigned_teacher_cannot_manage_or_reorder_course(self):
        self.login_teacher()
        course = {'id': 'course-2', 'title': 'Unauthorized', 'procedures': []}
        with patch('routes.admin_courses.course_db.get', return_value=course), \
             patch('services.teacher_service.is_teacher_assigned', return_value=False):
            response = self.client.get('/admin/courses/course-2/content')
            reorder = self.client.post('/admin/courses/course-2/content/reorder', json={'order': []})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(reorder.status_code, 403)

    def test_delete_content_calls_safe_recalculation_and_ui_confirms(self):
        self.login_teacher()
        course = {'id': 'course-1', 'title': 'Course', 'procedures': [{'id': 'p1'}]}
        with patch('routes.admin_courses.course_db.get', return_value=course), \
             patch('routes.admin_courses._teacher_can_manage', return_value=True), \
             patch('routes.admin_courses.delete_procedure_safely', return_value=True) as delete_safe:
            response = self.client.post('/admin/courses/course-1/content', data={
                'action': 'delete_procedure', 'procedure_id': 'p1'
            })
        self.assertEqual(response.status_code, 302)
        delete_safe.assert_called_once_with('course-1', 'p1')
        template = Path('templates/admin/course_content.html').read_text(encoding='utf-8')
        self.assertIn("confirm('Are you sure you want to delete this procedure?')", template)

    def test_teacher_assignment_form_loads_and_posts_database_relationship(self):
        self.login_admin()
        teacher = {'id': 'teacher-1', 'role': 'teacher', 'full_name': 'Teacher One',
                   'email': 't@example.test', 'created_at': '2026-01-01T00:00:00+00:00'}
        course = {'id': 'course-A', 'title': 'Course A'}
        with patch('routes.admin_users.user_db.get_all', return_value=[teacher]), \
             patch('routes.admin_users.admin_db.get_all', return_value=[]), \
             patch('routes.admin_users.course_db.get_all', return_value=[course]), \
             patch('routes.admin_users.get_teacher_courses', return_value=['course-A']):
            response = self.client.get('/admin/users/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'"teacher-1": ["course-A"]', response.data)

        with patch('routes.admin_users.user_db.get', return_value=teacher), \
             patch('routes.admin_users.course_db.get_all', return_value=[course]), \
             patch('routes.admin_users.set_teacher_courses') as save_assignments:
            self.client.post('/admin/users/teacher-1/edit-teacher', data={'course_ids': 'course-A'})
            save_assignments.assert_called_with('teacher-1', ['course-A'])
            self.client.post('/admin/users/teacher-1/edit-teacher', data={})
            save_assignments.assert_called_with('teacher-1', [])

    def test_teacher_forgot_reset_and_change_password_flows(self):
        teacher = {'id': 'teacher-1', 'role': 'teacher', 'full_name': 'Teacher One',
                   'email': 'teacher@example.test', 'password_hash': 'old-hash'}
        with patch('services.auth_service.user_db.find_one', return_value=teacher), \
             patch('services.password_reset_service.generate_reset_token', return_value='token-1') as generate, \
             patch('services.password_reset_service.send_reset_email', return_value=True) as send:
            response = self.client.post('/teacher/forgot-password', data={'email': teacher['email']})
        self.assertEqual(response.status_code, 302)
        generate.assert_called_once_with('teacher-1')
        send.assert_called_once()

        with patch('services.password_reset_service.get_valid_token', return_value={'user_id': 'teacher-1'}), \
             patch('services.password_reset_service.mark_token_used') as mark_used, \
             patch('services.auth_service.user_db.get', return_value=teacher), \
             patch('services.auth_service.user_db.save') as save_user, \
             patch('services.auth_service.hash_password', return_value='new-hash'):
            response = self.client.post('/reset-password/token-1', data={
                'password': 'new-password', 'confirm_password': 'new-password'
            })
        self.assertEqual(response.status_code, 302)
        self.assertIn('/loginteacher', response.location)
        self.assertEqual(teacher['password_hash'], 'new-hash')
        save_user.assert_called_once()
        mark_used.assert_called_once_with('token-1')

        self.login_teacher()
        teacher['password_hash'] = 'old-hash'
        with patch('routes.teacher.get_user_by_id', return_value=teacher), \
             patch('routes.teacher.verify_password', return_value=False), \
             patch('routes.teacher.user_db.update') as rejected_update:
            response = self.client.post('/teacher/settings', data={
                'current_password': 'wrong', 'new_password': 'changed-password',
                'confirm_password': 'changed-password'
            }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Current password is incorrect', response.data)
        rejected_update.assert_not_called()

        with patch('routes.teacher.get_user_by_id', return_value=teacher), \
             patch('routes.teacher.verify_password', return_value=True), \
             patch('routes.teacher.hash_password', return_value='changed-hash'), \
             patch('routes.teacher.user_db.update') as update:
            response = self.client.post('/teacher/settings', data={
                'current_password': 'correct', 'new_password': 'changed-password',
                'confirm_password': 'changed-password'
            })
        self.assertEqual(response.status_code, 302)
        update.assert_called_once_with('teacher-1', {'password_hash': 'changed-hash'})

    def test_certificate_api_returns_only_required_identity_fields(self):
        enrollment = {'id': 'e1', 'user_id': 'student-1', 'course_id': 'course-1',
                      'certificate_id': 'BBC-2026-UNIQUE', 'completed_at': '2026-09-22T00:00:00+00:00'}
        student = {'id': 'student-1', 'full_name': 'Student One', 'student_id': 'STU-001',
                   'username': 'private-username', 'password_hash': 'private-hash'}
        course = {'id': 'course-1', 'title': 'Secure Course'}
        with patch('routes.certificates.ensure_certificate_indexes'), \
             patch('routes.certificates.enrollment_db.find', return_value=[enrollment]), \
             patch('routes.certificates.get_course', return_value=course), \
             patch('routes.certificates.get_user_by_id', return_value=student), \
             patch('routes.certificates.get_template_for_course', return_value=None):
            response = self.client.get('/certificates/api/verify/BBC-2026-UNIQUE')
        payload = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload['student_id'], 'STU-001')
        self.assertNotIn('username', payload)
        self.assertNotIn('password_hash', payload)

        with patch('routes.certificates.ensure_certificate_indexes'), \
             patch('routes.certificates.enrollment_db.find', return_value=[]):
            missing = self.client.get('/certificates/api/verify/DOES-NOT-EXIST')
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(missing.get_json()['valid'], False)

    def test_certificate_view_blocks_idor(self):
        self.login_student('student-1')
        with patch('routes.certificates.enrollment_db.find', return_value=[]):
            response = self.client.get('/certificates/view/OTHER-STUDENT-CERT')
        self.assertEqual(response.status_code, 302)

    def test_signature_image_and_line_persist_after_save(self):
        self.login_admin()
        template = {'id': 'ctpl-1', 'name': 'Certificate', 'course_id': None}
        with patch('routes.admin_certificates.get_template', return_value=template), \
             patch('routes.admin_certificates.course_db.get_all', return_value=[]), \
             patch('routes.admin_certificates.update_template') as update:
            response = self.client.post('/admin/certificates/ctpl-1/edit', data={
                'name': 'Certificate', 'signature_name': 'Instructor',
                'signature_title': 'Course Instructor',
                'signature_image_data': 'data:image/png;base64,abc123',
                'font_size': '5.7', 'font_weight': '800', 'name_x': '50', 'name_y': '40'
            })
        self.assertEqual(response.status_code, 302)
        updates = update.call_args.args[1]
        self.assertEqual(updates['signature_image_data'], 'data:image/png;base64,abc123')
        self.assertEqual(updates['signature_name'], 'Instructor')
        shared = Path('templates/shared/certificate_layout.html').read_text(encoding='utf-8')
        generated = Path('templates/shared/dynamic_certificate_layout.html').read_text(encoding='utf-8')
        self.assertIn('cert-sig-line', shared)
        self.assertIn('cert-signature-line', generated)

    def test_certificate_print_css_is_a4_landscape_and_isolated(self):
        for relative in ['FrontEnd/Certificate.html', 'vercel_frontend/certificate.html',
                         'templates/user/certificate.html']:
            source = Path(relative).read_text(encoding='utf-8')
            self.assertIn('size: A4 landscape', source)
            self.assertIn('297mm', source)
            self.assertIn('210mm', source)
            self.assertIn('overflow: hidden', source)


if __name__ == '__main__':
    unittest.main()
