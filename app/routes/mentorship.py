from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import current_user, login_required
from app import db
from app.models import Skill, ContactRequest, Session, User, Rating, Badge
from datetime import datetime, timedelta
from app.utils.notifications import send_session_confirmation_email, schedule_reminder, send_email
from app.utils.sms_service import send_session_confirmation_sms, schedule_sms_reminder
import secrets
import random



mentorship = Blueprint('mentorship', __name__)

def generate_random_meeting_link(m_type):
    if m_type == 'Zoom':
        return f"https://zoom.us/j/{secrets.token_hex(5)}"
    elif m_type == 'Jitsi (In-App)':
        return f"ROOM_{secrets.token_hex(8)}"
    return f"https://meet.google.com/{secrets.token_hex(4)}-{secrets.token_hex(4)}"

@mentorship.route('/send_request', methods=['POST'])
@login_required
def send_request():
    skill_id = request.form.get('skill_id')
    skill = Skill.query.get_or_404(skill_id)
    
    if skill.mentor_id == current_user.id:
        flash("You cannot request your own skill.", "danger")
        return redirect(url_for('skills.skill_detail', skill_id=skill.id))
        
    existing = ContactRequest.query.filter(
        ContactRequest.sender_id == current_user.id,
        ContactRequest.skill_id == skill.id,
        ContactRequest.status.in_(['Pending Mutual Approval', 'Pending Final Confirmation', 'Matched'])
    ).first()
    if existing:
        flash("You already have a pending or matched request for this skill.", "info")
        return redirect(url_for('skills.skill_detail', skill_id=skill.id))
        
    req = ContactRequest(
        sender_id=current_user.id,
        mentor_id=skill.mentor_id,
        skill_id=skill.id,
        status='Pending Mutual Approval'
    )
    db.session.add(req)
    db.session.commit()
    flash('Mentorship request sent!', 'success')
    return redirect(url_for('mentorship.my_requests'))

@mentorship.route('/my_requests')
@login_required
def my_requests():
    sent = ContactRequest.query.filter_by(sender_id=current_user.id).all()
    received = ContactRequest.query.filter_by(mentor_id=current_user.id).all()
    sessions = Session.query.filter((Session.learner_id == current_user.id) | (Session.mentor_id == current_user.id)).all()
    return render_template('my_requests.html', sent=sent, received=received, sessions=sessions, now_date=datetime.utcnow().strftime('%Y-%m-%d'))

def parse_session_datetime(date_val, time_val=None):
    """Parses date/time supporting ISO datetime-local ('YYYY-MM-DDTHH:MM') or separate date and time strings."""
    if not date_val:
        return None
    date_val = str(date_val).strip()
    try:
        if 'T' in date_val:
            return datetime.strptime(date_val[:16], '%Y-%m-%dT%H:%M')
        if time_val and str(time_val).strip():
            time_clean = str(time_val).strip()
            return datetime.strptime(f"{date_val} {time_clean}", '%Y-%m-%d %H:%M')
        if ' ' in date_val:
            return datetime.strptime(date_val[:16], '%Y-%m-%d %H:%M')
    except (ValueError, TypeError):
        return None
    return None

def generate_random_meeting_link(link_type='Google Meet'):
    if link_type == 'Zoom':
        return f"https://zoom.us/j/{secrets.token_hex(5)}"
    elif link_type == 'Jitsi (In-App)':
        return f"ROOM_{secrets.token_hex(8)}"
    return f"https://meet.google.com/{secrets.token_hex(3)}-{secrets.token_hex(4)}-{secrets.token_hex(3)}"

@mentorship.route('/accept_request/<int:req_id>', methods=['POST'])
@login_required
def accept_request(req_id):
    req = ContactRequest.query.get_or_404(req_id)
    if req.mentor_id != current_user.id:
        return redirect(url_for('index'))
    
    if req.status == 'Matched':
        flash('Request already accepted and match is active.', 'info')
        return redirect(url_for('mentorship.my_requests'))

    exchange_skill_id = request.form.get('exchange_skill_id')
    if exchange_skill_id and str(exchange_skill_id).isdigit():
        req.exchange_skill_id = int(exchange_skill_id)
        
    req.status = 'Matched'
    db.session.commit()
    
    flash('Match confirmed! Now please schedule your session.', 'success')
    return redirect(url_for('mentorship.my_requests'))

@mentorship.route('/schedule_session/<int:req_id>', methods=['POST'])
@login_required
def schedule_session(req_id):
    req = ContactRequest.query.get_or_404(req_id)
    if current_user.id not in [req.mentor_id, req.sender_id]:
        return redirect(url_for('index'))
        
    date_str = request.form.get('session_date')
    time_str = request.form.get('session_time')
    meeting_type = request.form.get('meeting_type', 'Google Meet')
    
    session_dt = parse_session_datetime(date_str, time_str)
    if not session_dt:
        flash('A valid Date and Time are required.', 'danger')
        return redirect(url_for('mentorship.my_requests'))
        
    # CONFLICT CHECK
    conflict = Session.query.filter(
        (Session.mentor_id == req.mentor_id) | (Session.learner_id == req.sender_id),
        Session.session_date == session_dt,
        Session.status == 'Scheduled'
    ).first()
    
    if conflict:
        flash('Conflict detected! One of the users already has a session at this time.', 'danger')
        return redirect(url_for('mentorship.my_requests'))

    meeting_link = request.form.get('meeting_link')
    if meeting_type == 'Jitsi (In-App)':
        meeting_link = generate_random_meeting_link('Jitsi (In-App)')
    elif not meeting_link:
        if meeting_type == 'Zoom':
            meeting_link = current_user.zoom_link or generate_random_meeting_link('Zoom')
        else:
            meeting_link = current_user.meet_link or generate_random_meeting_link('Google Meet')
        
    new_session = Session(
        mentor_id=req.mentor_id,
        learner_id=req.sender_id,
        skill_id=req.skill_id,
        meeting_link=meeting_link,
        meeting_type=meeting_type,
        session_date=session_dt,
        status='Scheduled'
    )
    
    # Mark request as Matched and record exchange skill if selected
    if req.status != 'Completed':
        req.status = 'Matched'
    exchange_id = request.form.get('exchange_skill_id')
    if exchange_id and str(exchange_id).isdigit():
        req.exchange_skill_id = int(exchange_id)

    db.session.add(new_session)
    db.session.commit()
    
    # Real-time Notification
    from app.socket_events import send_realtime_notification
    other_user_id = req.sender_id if current_user.id == req.mentor_id else req.mentor_id
    send_realtime_notification(other_user_id, 'Session', f"New session scheduled for {session_dt}")

    try:
        send_session_confirmation_email(new_session.id)
        schedule_reminder(new_session.id, new_session.session_date)
        send_session_confirmation_sms(new_session.id)
        schedule_sms_reminder(new_session.id, new_session.session_date)
    except Exception as e:
        print(f"Error in notifying: {e}")
        
    flash(f"Session Scheduled for {session_dt} via {meeting_type}!", "success")
    return redirect(url_for('mentorship.my_requests'))

@mentorship.route('/reschedule_session/<int:session_id>', methods=['POST'])
@login_required
def reschedule_session(session_id):
    sess = Session.query.get_or_404(session_id)
    if current_user.id not in [sess.mentor_id, sess.learner_id]:
        return redirect(url_for('index'))
        
    date_str = request.form.get('session_date') or request.form.get('new_date')
    time_str = request.form.get('session_time')
    
    new_dt = parse_session_datetime(date_str, time_str)
    if not new_dt:
        flash('Valid Date and Time are required for rescheduling.', 'danger')
        return redirect(url_for('mentorship.my_requests'))
        
    # Check for conflict
    conflict = Session.query.filter(
        (Session.mentor_id == sess.mentor_id) | (Session.learner_id == sess.learner_id),
        Session.session_date == new_dt,
        Session.status == 'Scheduled',
        Session.id != sess.id
    ).first()
    if conflict:
        flash('Conflict detected! One of the users already has a session at this time.', 'danger')
        return redirect(url_for('mentorship.my_requests'))

    sess.session_date = new_dt
    sess.status = 'Scheduled'
    db.session.commit()
    
    flash('Session rescheduled successfully!', 'success')
    return redirect(url_for('mentorship.my_requests'))

@mentorship.route('/cancel_session/<int:session_id>', methods=['POST'])
@login_required
def cancel_session(session_id):
    sess = Session.query.get_or_404(session_id)
    if current_user.id not in [sess.mentor_id, sess.learner_id]:
        return redirect(url_for('index'))
        
    sess.status = 'Cancelled'
    db.session.commit()
    flash('Session has been cancelled.', 'info')
    return redirect(url_for('mentorship.my_requests'))

@mentorship.route('/confirm_match/<int:req_id>', methods=['POST'])
@login_required
def confirm_match(req_id):
    # This route is now redundant if accept_request matches directly,
    # but we'll leave it to handle any legacy cases or direct confirms.
    req = ContactRequest.query.get_or_404(req_id)
    if req.sender_id != current_user.id:
        return redirect(url_for('index'))
    
    if req.status != 'Matched':
        req.status = 'Matched'
        db.session.commit()
        
    flash('Match confirmed!', 'success')
    return redirect(url_for('mentorship.my_requests'))


@mentorship.route('/reject_request/<int:req_id>', methods=['POST'])
@login_required
def reject_request(req_id):
    req = ContactRequest.query.get_or_404(req_id)
    if current_user.id not in [req.mentor_id, req.sender_id]:
        return redirect(url_for('index'))
    req.status = 'Rejected'
    db.session.commit()
    flash('Request rejected.', 'info')
    return redirect(url_for('mentorship.my_requests'))

@mentorship.route('/complete_request/<int:session_id>', methods=['POST'])
@login_required
def complete_request(session_id):
    sess = Session.query.get_or_404(session_id)
    if current_user.id not in [sess.mentor_id, sess.learner_id]:
        return redirect(url_for('index'))
        
    sess.status = 'Completed'
    
    # Update Contact request status to completed
    cr = ContactRequest.query.filter_by(sender_id=sess.learner_id, mentor_id=sess.mentor_id, skill_id=sess.skill_id, status='Matched').first()
    if cr:
        cr.status = 'Completed'
        
    db.session.commit()
    flash('Session marked as completed!', 'success')
    return redirect(url_for('mentorship.my_requests'))

@mentorship.route('/submit_rating', methods=['POST'])
@login_required
def submit_rating():
    skill_id = request.form.get('skill_id')
    mentor_id = request.form.get('mentor_id')
    rating_val = int(request.form.get('rating_value'))
    review = request.form.get('review')
    
    rating = Rating(
        skill_id=skill_id,
        mentor_id=mentor_id,
        rater_id=current_user.id,
        rating_value=rating_val,
        review=review
    )
    db.session.add(rating)
    
    # Simple Badge logic: If a mentor gets 3 or more 5-star ratings
    mentor_ratings = Rating.query.filter_by(mentor_id=mentor_id, rating_value=5).count()
    if mentor_ratings + 1 == 3: # including this one
        b = Badge(user_id=mentor_id, badge_name='Top Mentor')
        db.session.add(b)
        
    db.session.commit()
    flash('Rating submitted! Thank you.', 'success')
    return redirect(url_for('skills.skill_detail', skill_id=skill_id))

@mentorship.route('/api/matches/suggestions')
@login_required
def suggested_matches():
    # Get user's offered skills names
    offered_names = [s.skill_name.lower() for s in current_user.skills]
    # Get user's wanted skills names
    wanted_names = [s.skill_name.lower() for s in current_user.wanted_skills]
    
    if not wanted_names:
        return {"suggestions": []}

    # Find users who HAVE what I WANT
    potential_mentors = User.query.join(Skill).filter(
        db.func.lower(Skill.skill_name).in_(wanted_names),
        User.id != current_user.id,
        User.is_active.is_(True),
        Skill.verification_status == 'Approved'
    ).all()
    
    suggestions = []
    for user in potential_mentors:
        # Check if they WANT what I HAVE
        their_wants = [s.skill_name.lower() for s in user.wanted_skills]
        # Intersection
        matching_my_offers = set(offered_names).intersection(set(their_wants))
        
        if matching_my_offers:
            # This is a strong match!
            skills_they_have = [s.skill_name for s in user.skills if s.skill_name.lower() in wanted_names]
            suggestions.append({
                'user_id': user.id,
                'name': user.name,
                'skills_offered': skills_they_have,
                'skills_they_want': list(matching_my_offers)
            })
            
    return {"suggestions": suggestions[:5]} # Limit to top 5

@mentorship.route('/video_call/<int:session_id>')
@login_required
def video_call(session_id):
    sess = Session.query.get_or_404(session_id)
    if current_user.id not in [sess.mentor_id, sess.learner_id]:
        return redirect(url_for('index'))
    return render_template('video_call.html', session=sess)

@mentorship.route('/bookmark_skill/<int:skill_id>', methods=['POST'])
@login_required
def bookmark_skill(skill_id):
    from app.models import Bookmark
    existing = Bookmark.query.filter_by(user_id=current_user.id, skill_id=skill_id).first()
    if not existing:
        b = Bookmark(user_id=current_user.id, skill_id=skill_id)
        db.session.add(b)
        db.session.commit()
        flash('Skill bookmarked!', 'success')
    else:
        db.session.delete(existing)
        db.session.commit()
        flash('Bookmark removed.', 'info')
    return redirect(request.referrer or url_for('skills.browse_skills'))

@mentorship.route('/session_history')
@login_required
def session_history():
    history = Session.query.filter((Session.learner_id == current_user.id) | (Session.mentor_id == current_user.id)).order_by(Session.session_date.desc()).all()
    return render_template('session_history.html', history=history)

@mentorship.route('/leaderboard')
def leaderboard():
    # Gather mentors and average ratings for active users
    mentors = db.session.query(
        User.id, 
        User.name, 
        db.func.avg(Rating.rating_value).label('avg_rating'),
        db.func.count(Rating.id).label('rating_count')
    ).join(Rating, Rating.mentor_id == User.id)\
     .filter(User.is_active.is_(True))\
     .group_by(User.id, User.name)\
     .order_by(db.desc('avg_rating')).all()
    
    return render_template('leaderboard.html', mentors=mentors)
