from datetime import datetime
import secrets
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import current_user, login_required
from app import db
from app.models import Skill, ContactRequest, Session, User, Rating, Badge
from app.utils.notifications import send_session_confirmation_email, schedule_reminder
from app.utils.sms_service import send_session_confirmation_sms, schedule_sms_reminder

mentorship = Blueprint('mentorship', __name__)


def generate_random_meeting_link(link_type='Google Meet'):
    if link_type == 'Zoom':
        return f"https://zoom.us/j/{secrets.token_hex(5)}"
    if link_type == 'Jitsi (In-App)':
        return f"ROOM_{secrets.token_hex(8)}"
    return f"https://meet.google.com/{secrets.token_hex(3)}-{secrets.token_hex(4)}-{secrets.token_hex(3)}"


def _parse_session_datetime(date_val, time_val=None):
    """Parse either YYYY-MM-DDTHH:MM (datetime-local) or separate date + time strings."""
    if not date_val:
        return None
    if 'T' in date_val and not time_val:
        return datetime.strptime(date_val[:16], '%Y-%m-%dT%H:%M')
    if time_val:
        return datetime.strptime(f"{date_val} {time_val[:5]}", '%Y-%m-%d %H:%M')
    return None


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
    sent = ContactRequest.query.filter_by(sender_id=current_user.id).order_by(ContactRequest.request_date.desc()).all()
    received = ContactRequest.query.filter_by(mentor_id=current_user.id).order_by(ContactRequest.request_date.desc()).all()
    sessions = Session.query.filter(
        (Session.learner_id == current_user.id) | (Session.mentor_id == current_user.id)
    ).order_by(Session.session_date.desc()).all()
    return render_template(
        'my_requests.html',
        sent=sent,
        received=received,
        sessions=sessions,
        now_date=datetime.utcnow().strftime('%Y-%m-%dT%H:%M')
    )


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
    if exchange_skill_id:
        req.exchange_skill_id = int(exchange_skill_id)
    req.status = 'Matched'
    db.session.commit()

    flash('Match confirmed! Now schedule your session.', 'success')
    return redirect(url_for('mentorship.my_requests'))


@mentorship.route('/schedule_session/<int:req_id>', methods=['POST'])
@login_required
def schedule_session(req_id):
    req = ContactRequest.query.get_or_404(req_id)
    if current_user.id not in [req.mentor_id, req.sender_id]:
        return redirect(url_for('index'))

    date_str = request.form.get('session_date', '').strip()
    time_str = request.form.get('session_time', '').strip()
    meeting_type = request.form.get('meeting_type', 'Google Meet')

    try:
        session_dt = _parse_session_datetime(date_str, time_str)
    except ValueError:
        session_dt = None

    if not session_dt:
        flash('Valid date and time are required.', 'danger')
        return redirect(url_for('mentorship.my_requests'))

    conflict = Session.query.filter(
        ((Session.mentor_id == req.mentor_id) | (Session.learner_id == req.sender_id)),
        Session.session_date == session_dt,
        Session.status == 'Scheduled'
    ).first()

    if conflict:
        flash('Conflict detected! One of the users already has a session at this time.', 'danger')
        return redirect(url_for('mentorship.my_requests'))

    meeting_link = request.form.get('meeting_link', '').strip()
    if meeting_type == 'Jitsi (In-App)':
        meeting_link = generate_random_meeting_link('Jitsi (In-App)')
    elif not meeting_link:
        if meeting_type == 'Zoom':
            meeting_link = current_user.zoom_link or generate_random_meeting_link('Zoom')
        else:
            meeting_link = current_user.meet_link or generate_random_meeting_link('Google Meet')

    if req.status != 'Matched':
        req.status = 'Matched'

    new_session = Session(
        mentor_id=req.mentor_id,
        learner_id=req.sender_id,
        skill_id=req.skill_id,
        meeting_link=meeting_link,
        meeting_type=meeting_type,
        session_date=session_dt,
        status='Scheduled'
    )
    db.session.add(new_session)
    db.session.commit()

    from app.socket_events import send_realtime_notification
    other_user_id = req.sender_id if current_user.id == req.mentor_id else req.mentor_id
    send_realtime_notification(other_user_id, 'Session', f"New session scheduled for {session_dt.strftime('%b %d at %H:%M')}")

    try:
        send_session_confirmation_email(new_session.id)
        schedule_reminder(new_session.id, new_session.session_date)
        send_session_confirmation_sms(new_session.id)
        schedule_sms_reminder(new_session.id, new_session.session_date)
    except Exception as e:
        print(f"Error in notifying: {e}")

    flash(f"Session scheduled for {session_dt.strftime('%b %d, %Y %H:%M')} via {meeting_type}!", "success")
    return redirect(url_for('mentorship.my_requests'))


@mentorship.route('/reschedule_session/<int:session_id>', methods=['POST'])
@login_required
def reschedule_session(session_id):
    sess = Session.query.get_or_404(session_id)
    if current_user.id not in [sess.mentor_id, sess.learner_id]:
        return redirect(url_for('index'))

    new_date = request.form.get('new_date', '').strip()
    date_str = request.form.get('session_date', '').strip() or new_date
    time_str = request.form.get('session_time', '').strip()

    try:
        new_dt = _parse_session_datetime(date_str, time_str)
    except ValueError:
        new_dt = None

    if not new_dt:
        flash('New date and time are required.', 'danger')
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

    cr = ContactRequest.query.filter_by(
        sender_id=sess.learner_id,
        mentor_id=sess.mentor_id,
        skill_id=sess.skill_id,
        status='Matched'
    ).first()
    if cr:
        cr.status = 'Completed'

    db.session.commit()
    flash('Session marked as completed!', 'success')
    return redirect(url_for('mentorship.my_requests'))


@mentorship.route('/submit_rating', methods=['POST'])
@login_required
def submit_rating():
    skill_id = request.form.get('skill_id', type=int)
    mentor_id = request.form.get('mentor_id', type=int)
    rating_val = request.form.get('rating_value', type=int)
    review = request.form.get('review', '').strip()

    skill = Skill.query.get_or_404(skill_id)
    if skill.mentor_id == current_user.id:
        flash('You cannot rate your own skill.', 'danger')
        return redirect(url_for('skills.skill_detail', skill_id=skill.id))

    if not rating_val or rating_val < 1 or rating_val > 5:
        flash('Please provide a valid star rating (1–5).', 'danger')
        return redirect(url_for('skills.skill_detail', skill_id=skill.id))

    rating = Rating(
        skill_id=skill.id,
        mentor_id=mentor_id or skill.mentor_id,
        rater_id=current_user.id,
        rating_value=rating_val,
        review=review
    )
    db.session.add(rating)
    db.session.flush()

    target_mentor_id = mentor_id or skill.mentor_id
    five_star_count = Rating.query.filter_by(mentor_id=target_mentor_id, rating_value=5).count()
    if five_star_count >= 3 and not Badge.query.filter_by(user_id=target_mentor_id, badge_name='Top Mentor').first():
        db.session.add(Badge(user_id=target_mentor_id, badge_name='Top Mentor'))

    db.session.commit()
    flash('Rating submitted! Thank you.', 'success')
    return redirect(url_for('skills.skill_detail', skill_id=skill.id))


@mentorship.route('/api/matches/suggestions')
@login_required
def suggested_matches():
    offered_names = [s.skill_name.lower() for s in current_user.skills]
    wanted_names = [s.skill_name.lower() for s in current_user.wanted_skills]

    if not wanted_names:
        return {"suggestions": []}

    potential_mentors = User.query.join(Skill).filter(
        db.func.lower(Skill.skill_name).in_(wanted_names),
        User.id != current_user.id,
        Skill.verification_status == 'Approved'
    ).all()

    suggestions = []
    for user in potential_mentors:
        their_wants = [s.skill_name.lower() for s in user.wanted_skills]
        matching_my_offers = set(offered_names).intersection(set(their_wants))

        if matching_my_offers or offered_names:
            skills_they_have = [s.skill_name for s in user.skills if s.skill_name.lower() in wanted_names]
            if skills_they_have:
                suggestions.append({
                    'user_id': user.id,
                    'name': user.name,
                    'skills_offered': skills_they_have,
                    'skills_they_want': list(matching_my_offers)
                })

    return {"suggestions": suggestions[:5]}


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
    history = Session.query.filter(
        (Session.learner_id == current_user.id) | (Session.mentor_id == current_user.id)
    ).order_by(Session.session_date.desc()).all()
    return render_template('session_history.html', history=history)


@mentorship.route('/leaderboard')
def leaderboard():
    mentors = db.session.query(
        User.id,
        User.name,
        db.func.avg(Rating.rating_value).label('avg_rating'),
        db.func.count(Rating.id).label('rating_count')
    ).join(Rating, Rating.mentor_id == User.id) \
     .group_by(User.id).order_by(db.desc('avg_rating')).all()

    return render_template('leaderboard.html', mentors=mentors)
