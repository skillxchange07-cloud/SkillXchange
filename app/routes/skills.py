import os
import secrets
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename
from app import db
from app.models import Skill, Rating, WantedSkill, User

skills = Blueprint('skills', __name__)

ALLOWED_VIDEO_EXTENSIONS = {'mp4', 'mov', 'avi', 'webm', 'mkv'}

def is_allowed_video(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_VIDEO_EXTENSIONS

def save_video(form_video):
    if not form_video or not form_video.filename:
        return None
    _, f_ext = os.path.splitext(form_video.filename)
    f_ext = f_ext.lower()
    if f_ext.lstrip('.') not in ALLOWED_VIDEO_EXTENSIONS:
        return None
    random_hex = secrets.token_hex(8)
    video_fn = f"{random_hex}{f_ext}"
    upload_dir = os.path.join(current_app.root_path, 'static', 'uploads')
    os.makedirs(upload_dir, exist_ok=True)
    video_path = os.path.join(upload_dir, video_fn)
    form_video.save(video_path)
    return video_fn

@skills.route('/browse')
def browse_skills():
    category = request.args.get('category')
    query = request.args.get('q')
    
    skills_query = Skill.query.join(User, Skill.mentor_id == User.id).filter(
        User.is_active.is_(True),
        Skill.verification_status == 'Approved'
    )
    
    if category:
        skills_query = skills_query.filter(Skill.category == category)
    
    if query:
        skills_query = skills_query.filter(
            (Skill.skill_name.ilike(f'%{query}%')) | 
            (Skill.description.ilike(f'%{query}%'))
        )
        
    skills = skills_query.all()
    categories = db.session.query(Skill.category).join(User, Skill.mentor_id == User.id).filter(
        User.is_active.is_(True),
        Skill.verification_status == 'Approved'
    ).distinct().all()
    return render_template('browse_skills.html', 
                           skills=skills, 
                           categories=[c[0] for c in categories])

@skills.route('/skill/<int:skill_id>')
def skill_detail(skill_id):
    skill = Skill.query.get_or_404(skill_id)
    if not skill.mentor.is_active:
        flash('This mentor is currently inactive.', 'info')
        return redirect(url_for('skills.browse_skills'))
    ratings = Rating.query.filter_by(skill_id=skill.id).all()
    avg_rating = sum(r.rating_value for r in ratings) / len(ratings) if ratings else 0
    return render_template('skill_detail.html', skill=skill, ratings=ratings, avg_rating=round(avg_rating, 1))

@skills.route('/add_skill', methods=['GET', 'POST'])
@login_required
def add_skill():
    if request.method == 'POST':
        skill_name = request.form.get('skill_name')
        category = request.form.get('category')
        description = request.form.get('description')
        demo_video = request.files.get('demo_video')
        
        video_filename = None
        if demo_video and demo_video.filename:
            if not is_allowed_video(demo_video.filename):
                flash('Invalid video format. Allowed formats: MP4, MOV, AVI, WEBM, MKV.', 'danger')
                return render_template('add_skill.html')
            video_filename = save_video(demo_video)
            
        skill = Skill(
            mentor_id=current_user.id,
            skill_name=skill_name,
            category=category,
            description=description,
            demo_video_path=video_filename,
            verification_status='Pending'
        )
        db.session.add(skill)
        db.session.commit()
        flash('Skill added! It is currently pending admin verification.', 'success')
        return redirect(url_for('auth.dashboard'))
    return render_template('add_skill.html')

@skills.route('/edit_skill/<int:skill_id>', methods=['GET', 'POST'])
@login_required
def edit_skill(skill_id):
    skill = Skill.query.get_or_404(skill_id)
    if skill.mentor_id != current_user.id:
        flash('You cannot edit this skill.', 'danger')
        return redirect(url_for('skills.browse_skills'))
        
    if request.method == 'POST':
        skill.skill_name = request.form.get('skill_name')
        skill.category = request.form.get('category')
        skill.description = request.form.get('description')
        demo_video = request.files.get('demo_video')
        if demo_video and demo_video.filename:
            if not is_allowed_video(demo_video.filename):
                flash('Invalid video format. Allowed formats: MP4, MOV, AVI, WEBM, MKV.', 'danger')
                return render_template('edit_skill.html', skill=skill)
            skill.demo_video_path = save_video(demo_video)
        skill.verification_status = 'Pending' # Reset for re-verification
        db.session.commit()
        flash('Skill updated and sent for re-verification.', 'success')
        return redirect(url_for('auth.dashboard'))
        
    return render_template('edit_skill.html', skill=skill)

@skills.route('/add_wanted_skill', methods=['POST'])
@login_required
def add_wanted_skill():
    skill_name = request.form.get('skill_name')
    category = request.form.get('category')
    
    if skill_name:
        ws = WantedSkill(user_id=current_user.id, skill_name=skill_name, category=category)
        db.session.add(ws)
        db.session.commit()
        flash('Learning goal added!', 'success')
    return redirect(url_for('auth.dashboard'))

@skills.route('/remove_wanted_skill/<int:ws_id>', methods=['POST'])
@login_required
def remove_wanted_skill(ws_id):
    ws = WantedSkill.query.get_or_404(ws_id)
    if ws.user_id == current_user.id:
        db.session.delete(ws)
        db.session.commit()
        flash('Learning goal removed.', 'info')
    return redirect(url_for('auth.dashboard'))
