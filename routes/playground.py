from flask import Blueprint, render_template, session
from utils.decorators import login_required
from services.auth_service import get_user_by_id

bp = Blueprint('playground', __name__, url_prefix='/playground')

@bp.route('/')
@login_required
def index():
    user = get_user_by_id(session['user_id'])
    return render_template('user/playground.html', user=user)
