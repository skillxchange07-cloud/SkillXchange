from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, current_user, logout_user, login_required
from app import db, bcrypt
from app.models import User, ContactRequest, Notification, Message, Session, Rating

auth = Blueprint('auth', __name__)


@auth.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        name = (request.form.get('name') or '').strip()
        email = (request.form.get('email') or '').strip().lower()
        password = request.form.get('password') or ''
        phone = (request.form.get('phone') or '').strip()

        if not name or not email or len(password) < 6:
            flash('Please provide a name, valid email, and a password of at least 6 characters.', 'danger')
            return redirect(url_for('auth.register'))

        user = User.query.filter_by(email=email).first()
        if user:
            flash('Email already registered! Please login.', 'danger')
            return redirect(url_for('auth.register'))

        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        role = 'Admin' if email == 'admin@skillxchange.com' else 'User'

        new_user = User(name=name, email=email, password_hash=hashed_password, phone=phone, role=role)
        db.session.add(new_user)
        db.session.commit()
        flash('Your account has been created! You can now login.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/register.html')


@auth.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        email = (request.form.get('email') or '').strip().lower()
        password = request.form.get('password') or ''

        user = User.query.filter_by(email=email).first()
        if user and bcrypt.check_password_hash(user.password_hash, password):
            login_user(user, remember=bool(request.form.get('remember')))
            next_page = request.args.get('next')
            if user.role == 'Admin':
                return redirect(next_page) if next_page else redirect(url_for('admin.dashboard'))
            return redirect(next_page) if next_page else redirect(url_for('auth.dashboard'))
        flash('Login unsuccessful. Please check email and password.', 'danger')

    return render_template('auth/login.html')


DEMO_ACCOUNTS = {
    'mentor': 'rahul@example.com',
    'learner': 'priya@example.com',
    'admin': 'admin@skillxchange.com',
}


@auth.route('/demo_login', methods=['POST'])
@auth.route('/demo_login/<role>', methods=['POST'])
def demo_login(role='mentor'):
    target_role = (request.form.get('role') or role or 'mentor').strip().lower()
    email = DEMO_ACCOUNTS.get(target_role, DEMO_ACCOUNTS['mentor'])
    user = User.query.filter_by(email=email).first()
    if not user:
        flash('Demo account is not available yet.', 'warning')
        return redirect(url_for('auth.login'))

    login_user(user, remember=True)
    flash(f'Signed in to demo account as {user.name} ({user.role}).', 'success')
    if user.role == 'Admin':
        return redirect(url_for('admin.dashboard'))
    return redirect(url_for('auth.dashboard'))


@auth.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('index'))


@auth.route('/edit_profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
    if request.method == 'POST':
        current_user.name = (request.form.get('name') or current_user.name).strip()
        current_user.phone = (request.form.get('phone') or '').strip()
        current_user.availability = (request.form.get('availability') or '').strip()
        current_user.preferred_mode = (request.form.get('preferred_mode') or '').strip()
        current_user.zoom_link = (request.form.get('zoom_link') or '').strip()
        current_user.meet_link = (request.form.get('meet_link') or '').strip()
        db.session.commit()
        flash('Profile updated successfully!', 'success')
        return redirect(url_for('auth.mentor_profile', user_id=current_user.id))

    return render_template('auth/edit_profile.html')


@auth.route('/dashboard')
@login_required
def dashboard():
    if current_user.role == 'Admin':
        return redirect(url_for('admin.dashboard'))

    matches_count = ContactRequest.query.filter(
        ((ContactRequest.sender_id == current_user.id) | (ContactRequest.mentor_id == current_user.id)),
        ContactRequest.status == 'Matched'
    ).count()

    active_sessions = Session.query.filter(
        ((Session.learner_id == current_user.id) | (Session.mentor_id == current_user.id)),
        Session.status == 'Scheduled'
    ).count()

    skills_learned = Session.query.filter_by(learner_id=current_user.id, status='Completed').count()
    avg_rating = db.session.query(db.func.avg(Rating.rating_value)).filter_by(mentor_id=current_user.id).scalar() or 0

    return render_template(
        'dashboard.html',
        matches_count=matches_count,
        active_sessions=active_sessions,
        skills_learned=skills_learned,
        avg_rating=round(avg_rating, 1)
    )


@auth.route('/api/messages/history/<int:user_id>')
@login_required
def message_history(user_id):
    msgs = Message.query.filter(
        ((Message.sender_id == current_user.id) & (Message.recipient_id == user_id)) |
        ((Message.sender_id == user_id) & (Message.recipient_id == current_user.id))
    ).order_by(Message.timestamp.asc()).all()

    return {
        "messages": [
            {
                "content": m.content,
                "sender_id": m.sender_id,
                "timestamp": m.timestamp.strftime('%Y-%m-%d %H:%M:%S')
            } for m in msgs
        ]
    }


@auth.route('/api/notifications')
@login_required
def get_notifications():
    notifs = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.created_at.desc()).limit(10).all()
    return {
        "notifications": [
            {
                "id": n.id,
                "type": n.type,
                "message": n.message,
                "read_status": n.read_status,
                "created_at": n.created_at.strftime('%Y-%m-%d %H:%M:%S')
            } for n in notifs
        ]
    }


@auth.route('/api/notifications/read', methods=['POST'])
@login_required
def mark_notifs_read():
    Notification.query.filter_by(user_id=current_user.id, read_status=False).update({Notification.read_status: True})
    db.session.commit()
    return {"status": "success"}


@auth.route('/messages')
@login_required
def messages():
    sent = db.session.query(User).join(Message, Message.recipient_id == User.id).filter(Message.sender_id == current_user.id).all()
    received = db.session.query(User).join(Message, Message.sender_id == User.id).filter(Message.recipient_id == current_user.id).all()
    matched_sent = db.session.query(User).join(ContactRequest, ContactRequest.mentor_id == User.id).filter(ContactRequest.sender_id == current_user.id).all()
    matched_recv = db.session.query(User).join(ContactRequest, ContactRequest.sender_id == User.id).filter(ContactRequest.mentor_id == current_user.id).all()

    contacts_map = {u.id: u for u in (sent + received + matched_sent + matched_recv) if u.id != current_user.id}

    to_user_id = request.args.get('to', type=int)
    active_contact = None
    if to_user_id and to_user_id != current_user.id:
        target = User.query.get(to_user_id)
        if target:
            contacts_map[target.id] = target
            active_contact = target

    contacts = sorted(contacts_map.values(), key=lambda u: u.name.lower())
    return render_template('messages.html', contacts=contacts, active_contact=active_contact)


@auth.route('/mentor_profile/<int:user_id>')
def mentor_profile(user_id):
    user = User.query.get_or_404(user_id)
    is_matched = False

    if current_user.is_authenticated and current_user.id != user.id:
        cr = ContactRequest.query.filter(
            ((ContactRequest.sender_id == current_user.id) & (ContactRequest.mentor_id == user.id)) |
            ((ContactRequest.sender_id == user.id) & (ContactRequest.mentor_id == current_user.id))
        ).filter_by(status='Matched').first()
        if cr:
            is_matched = True

    students_count = Session.query.filter_by(mentor_id=user.id).with_entities(Session.learner_id).distinct().count()
    return render_template('mentor_profile.html', user=user, is_matched=is_matched, students_count=students_count)
