from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import current_user, login_required
from app import db
from app.models import User, Skill, ContactRequest, Session
from functools import wraps

admin = Blueprint('admin', __name__)

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'Admin':
            flash('Admin access strictly required.', 'danger')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

@admin.route('/admin/dashboard')
@login_required
@admin_required
def dashboard():
    pending_skills = Skill.query.filter_by(verification_status='Pending').all()
    users_count = User.query.count()
    skills_count = Skill.query.count()
    return render_template('admin/dashboard.html', 
                            pending_skills=pending_skills, 
                            users_count=users_count, 
                            skills_count=skills_count)

@admin.route('/api/admin/stats')
@login_required
@admin_required
def get_stats():
    total_users = User.query.count()
    total_skills = Skill.query.count()
    total_matches = ContactRequest.query.filter_by(status='Matched').count()
    sessions_completed = Session.query.filter_by(status='Completed').count()
    
    # Simple active users logic (registered in last 30 days)
    from datetime import datetime, timedelta
    active_users = User.query.filter(User.created_at > datetime.utcnow() - timedelta(days=30)).count()
    
    return {
        "users": total_users,
        "skills": total_skills,
        "matches": total_matches,
        "sessions": sessions_completed,
        "active": active_users
    }

@admin.route('/admin/verify_skill/<int:skill_id>', methods=['POST'])
@login_required
@admin_required
def verify_skill(skill_id):
    skill = Skill.query.get_or_404(skill_id)
    action = request.form.get('action') # 'Approve' or 'Reject'
    
    if action == 'Approve':
        skill.verification_status = 'Approved'
        flash(f'Skill {skill.skill_name} approved.', 'success')
    elif action == 'Reject':
        skill.verification_status = 'Rejected'
        flash(f'Skill {skill.skill_name} rejected.', 'warning')
        
    db.session.commit()
    return redirect(url_for('admin.dashboard'))

@admin.route('/admin/users')
@login_required
@admin_required
def users():
    users_list = User.query.all()
    return render_template('admin/users.html', users=users_list)

@admin.route('/admin/toggle_user_status/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def toggle_user_status(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash('You cannot change the active status of your own account.', 'danger')
        return redirect(url_for('admin.users'))
        
    user.is_active = not user.is_active
    db.session.commit()
    status_str = "activated" if user.is_active else "deactivated"
    flash(f'Account for {user.name} has been {status_str}.', 'success')
    return redirect(url_for('admin.users'))

@admin.route('/admin/delete_user/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def delete_user(user_id):
    """Safely deactivates user account instead of permanent physical deletion to preserve barter history."""
    return toggle_user_status(user_id)

@admin.route('/admin/toggle_admin/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def toggle_admin(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash('You cannot change your own role.', 'danger')
        return redirect(url_for('admin.users'))
        
    user.role = 'Admin' if user.role == 'User' else 'User'
    db.session.commit()
    flash(f'Role for {user.name} updated to {user.role}.', 'success')
    return redirect(url_for('admin.users'))
