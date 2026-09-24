from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from utils.decorators import admin_required
from services.certificate_db_service import (cert_template_db, get_all_templates,
    get_template, create_template, update_template, delete_template)
from services.course_service import course_db
from config import Config
import os
import uuid

bp = Blueprint('admin_certificates', __name__, url_prefix='/admin/certificates')

CERT_UPLOAD_DIR = os.path.join(Config.BASE_DIR, 'static', 'uploads', 'certificates')

@bp.route('/')
@admin_required
def index():
    templates = get_all_templates()
    courses = course_db.get_all()
    course_map = {c['id']: c for c in courses}
    return render_template('admin/certificates.html', templates=templates, course_map=course_map)

@bp.route('/create', methods=['GET', 'POST'])
@admin_required
def create():
    courses = course_db.get_all()
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        course_id = request.form.get('course_id') or None
        
        template_id = create_template(name, course_id)
        flash("Certificate template created.", "success")
        return redirect(url_for('admin_certificates.index'))

    return render_template('admin/certificate_form.html', courses=courses, template=None)

@bp.route('/<template_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit(template_id):
    template = get_template(template_id)
    if not template:
        flash("Template not found.", "danger")
        return redirect(url_for('admin_certificates.index'))
    
    courses = course_db.get_all()
    
    if request.method == 'POST':
        updates = {
            'name': request.form.get('name', '').strip(),
            'course_id': request.form.get('course_id') or None,
            'signature_name': request.form.get('signature_name', '').strip(),
            'signature_title': request.form.get('signature_title', '').strip(),
            'font_size': request.form.get('font_size', '5.7'),
            'font_weight': int(request.form.get('font_weight', 400)),
            'name_x': request.form.get('name_x', '50'),
            'name_y': request.form.get('name_y', '40'),
            'signature_image_data': request.form.get('signature_image_data', '')
        }
        update_template(template_id, updates)
        flash("Certificate template updated.", "success")
        return redirect(url_for('admin_certificates.index'))
        
    return render_template('admin/certificate_form.html', courses=courses, template=template)

@bp.route('/<template_id>/api/save', methods=['POST'])
@admin_required
def api_save(template_id):
    template = get_template(template_id)
    if not template:
        return jsonify({'error': 'Template not found'}), 404
        
    data = request.json
    updates = {
        'name': data.get('name', template['name']),
        'course_id': data.get('course_id', template['course_id']),
        'bg_image_url': data.get('bg_image_url', template['bg_image_url']),
        'elements': data.get('elements', template.get('elements', []))
    }
    
    update_template(template_id, updates)
    return jsonify({'success': True})

@bp.route('/<template_id>/delete', methods=['POST'])
@admin_required
def delete(template_id):
    delete_template(template_id)
    flash("Template deleted.", "success")
    return redirect(url_for('admin_certificates.index'))
