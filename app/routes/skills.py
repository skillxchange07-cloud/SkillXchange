import os
import secrets
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename
from app import db
from app.models import Skill, Rating, WantedSkill

skills = Blueprint('skills', __name__)

ALLOWED_VIDEO_EXTENSIONS = {'.mp4', '.mov', '.webm', '.m4v'}


def save_video(form_video):
    safe_name = secure_filename(form_video.filename)
    _, f_ext = os.path.splitext(safe_name)
    f_ext = f_ext.lower()
    if f_ext not in ALLOWED_VIDEO_EXTENSIONS:
        return None
    random_hex = secrets.token_hex(8)
    video_fn = random_hex + f_ext
    video_path = os.path.join(current_app.config['UPLOAD_FOLDER'], video_fn)
    form_video.save(video_path)
    return video_fn


@skills.route('/browse')
def browse_skills():
    category = request.args.get('category')
    query = request.args.get('q')

    skills_query = Skill.query.filter_by(verification_status='Approved')

    if category:
        skills_query = skills_query.filter_by(category=category)

    if query:
        skills_query = skills_query.filter(
            (Skill.skill_name.ilike(f'%{query}%')) |
            (Skill.description.ilike(f'%{query}%'))
        )

    skill_list = skills_query.order_by(Skill.created_at.desc()).all()
    categories = db.session.query(Skill.category).distinct().all()

    rating_rows = db.session.query(
        Rating.skill_id,
        db.func.avg(Rating.rating_value),
        db.func.count(Rating.id)
    ).group_by(Rating.skill_id).all()
    ratings_map = {row[0]: {'avg': round(row[1], 1), 'count': row[2]} for row in rating_rows}

    return render_template(
        'browse_skills.html',
        skills=skill_list,
        categories=[c[0] for c in categories],
        ratings_map=ratings_map
    )


@skills.route('/skill/<int:skill_id>')
def skill_detail(skill_id):
    skill = Skill.query.get_or_404(skill_id)
    ratings = Rating.query.filter_by(skill_id=skill.id).order_by(Rating.created_at.desc()).all()
    avg_rating = sum(r.rating_value for r in ratings) / len(ratings) if ratings else 0
    return render_template('skill_detail.html', skill=skill, ratings=ratings, avg_rating=round(avg_rating, 1))


@skills.route('/add_skill', methods=['GET', 'POST'])
@login_required
def add_skill():
    if request.method == 'POST':
        skill_name = (request.form.get('skill_name') or '').strip()
        category = (request.form.get('category') or '').strip()
        description = (request.form.get('description') or '').strip()
        demo_video = request.files.get('demo_video')

        video_filename = None
        if demo_video and demo_video.filename:
            video_filename = save_video(demo_video)
            if video_filename is None:
                flash('Invalid video format. Please upload .mp4, .mov, .webm, or .m4v.', 'danger')
                return redirect(url_for('skills.add_skill'))

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
        skill.skill_name = (request.form.get('skill_name') or skill.skill_name).strip()
        skill.category = (request.form.get('category') or skill.category).strip()
        skill.description = (request.form.get('description') or skill.description).strip()
        demo_video = request.files.get('demo_video')
        if demo_video and demo_video.filename:
            saved = save_video(demo_video)
            if saved is None:
                flash('Invalid video format. Please upload .mp4, .mov, .webm, or .m4v.', 'danger')
                return redirect(url_for('skills.edit_skill', skill_id=skill.id))
            skill.demo_video_path = saved
        skill.verification_status = 'Pending'
        db.session.commit()
        flash('Skill updated and sent for re-verification.', 'success')
        return redirect(url_for('auth.dashboard'))

    return render_template('edit_skill.html', skill=skill)


@skills.route('/add_wanted_skill', methods=['POST'])
@login_required
def add_wanted_skill():
    skill_name = (request.form.get('skill_name') or '').strip()
    category = (request.form.get('category') or '').strip()

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
