from datetime import datetime
from app import db, login_manager
from flask_login import UserMixin

@login_manager.user_loader
def load_user(user_id):
    user = User.query.get(int(user_id))
    if user and not user.is_active:
        return None
    return user

class User(db.Model, UserMixin):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(20))
    availability = db.Column(db.String(255))
    preferred_mode = db.Column(db.String(50)) # Zoom, Google Meet, WhatsApp
    zoom_link = db.Column(db.String(255))
    meet_link = db.Column(db.String(255))
    role = db.Column(db.String(20), default='User') # Admin, User
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    skills = db.relationship('Skill', backref='mentor', lazy=True, cascade="all, delete-orphan")
    badges = db.relationship('Badge', backref='user', lazy=True, cascade="all, delete-orphan")
    notifications = db.relationship('Notification', backref='user', lazy=True, cascade="all, delete-orphan")
    wanted_skills = db.relationship('WantedSkill', backref='user', lazy=True, cascade="all, delete-orphan")
    bookmarks = db.relationship('Bookmark', backref='user', lazy=True, cascade="all, delete-orphan")
    ratings_received = db.relationship('Rating', foreign_keys='Rating.mentor_id', backref='target_mentor', lazy=True)

    # contact requests sent by this user
    sent_requests = db.relationship('ContactRequest', foreign_keys='ContactRequest.sender_id', backref='sender', lazy=True)
    # contact requests received by this user (as a mentor)
    received_requests = db.relationship('ContactRequest', foreign_keys='ContactRequest.mentor_id', backref='mentor', lazy=True)
    
    def __repr__(self):
        return f"User('{self.name}', '{self.email}', '{self.role}')"

class Skill(db.Model):
    __tablename__ = 'skills'
    id = db.Column(db.Integer, primary_key=True)
    mentor_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    skill_name = db.Column(db.String(100), nullable=False, index=True)
    category = db.Column(db.String(50), nullable=False, index=True)
    description = db.Column(db.Text)
    demo_video_path = db.Column(db.String(255))
    verification_status = db.Column(db.String(20), default='Pending', index=True) # Pending, Approved, Rejected
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    contact_requests = db.relationship('ContactRequest', foreign_keys='ContactRequest.skill_id', backref='skill', lazy=True)
    sessions = db.relationship('Session', backref='skill', lazy=True)
    ratings = db.relationship('Rating', backref='skill', lazy=True)
    wishlisted_by = db.relationship('Bookmark', backref='skill', lazy=True)

class WantedSkill(db.Model):
    __tablename__ = 'wanted_skills'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    skill_name = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class ContactRequest(db.Model):
    __tablename__ = 'contact_requests'
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    mentor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    skill_id = db.Column(db.Integer, db.ForeignKey('skills.id'), nullable=False)
    exchange_skill_id = db.Column(db.Integer, db.ForeignKey('skills.id'), nullable=True)
    status = db.Column(db.String(30), default='Pending Mutual Approval', index=True) # Pending Mutual Approval, Pending Final Confirmation, Matched, Rejected, Completed
    request_date = db.Column(db.DateTime, default=datetime.utcnow)

    exchange_skill = db.relationship('Skill', foreign_keys=[exchange_skill_id])

class Session(db.Model):
    __tablename__ = 'sessions'
    id = db.Column(db.Integer, primary_key=True)
    mentor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    learner_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    skill_id = db.Column(db.Integer, db.ForeignKey('skills.id'), nullable=False)
    meeting_link = db.Column(db.String(255), nullable=False)
    meeting_type = db.Column(db.String(50), default='Google Meet') # Google Meet, Zoom
    session_date = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), default='Scheduled') # Scheduled, Completed, Cancelled
    
    mentor = db.relationship('User', foreign_keys=[mentor_id])
    learner = db.relationship('User', foreign_keys=[learner_id])

class Message(db.Model):
    __tablename__ = 'messages'
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    recipient_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    is_read = db.Column(db.Boolean, default=False)

class Notification(db.Model):
    __tablename__ = 'notifications'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    type = db.Column(db.String(50), nullable=False) # 'Match', 'Session', 'Message', 'Reminder'
    message = db.Column(db.String(255), nullable=False)
    read_status = db.Column(db.Boolean, default=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Rating(db.Model):
    __tablename__ = 'ratings'
    id = db.Column(db.Integer, primary_key=True)
    skill_id = db.Column(db.Integer, db.ForeignKey('skills.id'), nullable=False)
    mentor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    rater_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    rating_value = db.Column(db.Integer, nullable=False)
    review = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    mentor = db.relationship('User', foreign_keys=[mentor_id])
    rater = db.relationship('User', foreign_keys=[rater_id])

class Badge(db.Model):
    __tablename__ = 'badges'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    badge_name = db.Column(db.String(50), nullable=False)
    earned_date = db.Column(db.DateTime, default=datetime.utcnow)

class Bookmark(db.Model):
    __tablename__ = 'bookmarks'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    skill_id = db.Column(db.Integer, db.ForeignKey('skills.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
