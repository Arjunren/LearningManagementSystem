from flask import Flask, redirect, url_for
from flask_wtf.csrf import CSRFProtect
from flask_cors import CORS
from config import Config

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    from services.course_service import sanitize_handout_html
    app.jinja_env.filters['safe_handout_html'] = sanitize_handout_html

    # The public verification frontend only needs this read-only endpoint.
    # Avoid granting arbitrary websites CORS access to every application route.
    CORS(app, resources={r"/certificates/api/*": {"origins": app.config['CERTIFICATE_FRONTEND_ORIGIN']}})
    csrf = CSRFProtect(app)

    from routes import auth, user, courses, gradebook, certificates, admin, admin_courses, admin_users, admin_students, admin_certificates, teacher, teacher_submissions, playground

    app.register_blueprint(auth.bp)
    app.register_blueprint(user.bp)
    app.register_blueprint(courses.bp)
    app.register_blueprint(gradebook.bp)
    app.register_blueprint(certificates.bp)
    app.register_blueprint(admin.bp)
    app.register_blueprint(admin_courses.bp)
    app.register_blueprint(admin_users.bp)
    app.register_blueprint(admin_students.bp)
    app.register_blueprint(admin_certificates.bp)
    app.register_blueprint(teacher.bp)
    app.register_blueprint(teacher_submissions.bp)
    app.register_blueprint(playground.bp)

    @app.route('/')
    def index():
        return redirect(url_for('auth.login'))

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)
