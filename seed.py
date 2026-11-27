from datetime import datetime, timedelta
from flask_bcrypt import generate_password_hash
from app import db
from app.models import User, Skill, WantedSkill, ContactRequest, Session, Rating, Badge, Message


def populate_sample_data():
    """Insert initial demo users, skills, requests, sessions, ratings, and badges."""
    hashed_pw = generate_password_hash('password123').decode('utf-8')

    admin = User(
        name="System Admin",
        email="admin@skillxchange.com",
        password_hash=hashed_pw,
        phone="1234567890",
        role="Admin"
    )

    users = [
        User(name="Rahul Sharma", email="rahul@example.com", password_hash=hashed_pw, phone="9876543210", preferred_mode="Zoom", zoom_link="https://zoom.us/j/rahul123", availability="Weekends 10AM-12PM"),
        User(name="Priya Patel", email="priya@example.com", password_hash=hashed_pw, phone="9876543211", preferred_mode="Google Meet", meet_link="https://meet.google.com/priya-abc", availability="Mon-Fri 6PM-8PM"),
        User(name="Amit Kumar", email="amit@example.com", password_hash=hashed_pw, phone="9876543212", preferred_mode="Zoom", zoom_link="https://zoom.us/j/amit456", availability="Weeknights 7PM-9PM"),
        User(name="Sneha Reddy", email="sneha@example.com", password_hash=hashed_pw, phone="9876543213", preferred_mode="Google Meet", availability="Flexible"),
        User(name="Rohan Mehta", email="rohan@example.com", password_hash=hashed_pw, phone="9876543214", availability="Saturdays"),
        User(name="Anjali Verma", email="anjali@example.com", password_hash=hashed_pw, phone="9876543215", availability="Evenings"),
        User(name="Vikas Singh", email="vikas@example.com", password_hash=hashed_pw, phone="9876543216", availability="Sundays"),
        User(name="Neha Gupta", email="neha@example.com", password_hash=hashed_pw, phone="9876543217", availability="Mornings"),
        User(name="Arjun Nair", email="arjun@example.com", password_hash=hashed_pw, phone="9876543218", availability="Weekends"),
        User(name="Pooja Kulkarni", email="pooja@example.com", password_hash=hashed_pw, phone="9876543219", availability="Flexible"),
    ]

    db.session.add(admin)
    db.session.add_all(users)
    db.session.commit()

    skills = [
        Skill(mentor_id=users[0].id, skill_name="Python Web Development", category="Programming", description="Learn to build REST APIs and full-stack web apps using Flask and SQLAlchemy.", verification_status="Approved", demo_video_path="demo1.mp4"),
        Skill(mentor_id=users[1].id, skill_name="Digital Marketing Basics", category="Marketing", description="A comprehensive guide to SEO, SEM, and practical content analytics.", verification_status="Approved", demo_video_path="demo2.mp4"),
        Skill(mentor_id=users[2].id, skill_name="UI/UX Prototyping", category="Design", description="Learn Figma component systems, wireframing, and rapid prototyping from scratch.", verification_status="Approved", demo_video_path="demo3.mp4"),
        Skill(mentor_id=users[3].id, skill_name="Data Science with Pandas", category="Data Science", description="Hands-on data manipulation, cleaning, and visualization techniques in Python.", verification_status="Approved", demo_video_path="demo1.mp4"),
        Skill(mentor_id=users[4].id, skill_name="Public Speaking", category="Business", description="Conquer stage fright and deliver persuasive technical and executive presentations.", verification_status="Pending"),
        Skill(mentor_id=users[5].id, skill_name="Machine Learning 101", category="Data Science", description="Practical introduction to supervised models and evaluation with Scikit-Learn.", verification_status="Approved", demo_video_path="demo2.mp4"),
        Skill(mentor_id=users[6].id, skill_name="Guitar Basics", category="Music", description="Learn your first open chords, rhythm strumming, and finger-picking patterns.", verification_status="Approved", demo_video_path="demo3.mp4"),
        Skill(mentor_id=users[7].id, skill_name="Conversational French", category="Languages", description="Essential everyday phrases, pronunciation, and travel dialogues for beginners.", verification_status="Pending"),
        Skill(mentor_id=users[8].id, skill_name="Stock Market Strategies", category="Business", description="Portfolio fundamentals, index allocation, and risk management frameworks.", verification_status="Approved"),
        Skill(mentor_id=users[0].id, skill_name="Advanced Javascript", category="Programming", description="Master ES6+ async patterns, closures, and modular browser architecture.", verification_status="Approved", demo_video_path="demo1.mp4"),
    ]
    db.session.add_all(skills)
    db.session.commit()

    wanted = [
        WantedSkill(user_id=users[0].id, skill_name="UI/UX Prototyping", category="Design"),
        WantedSkill(user_id=users[1].id, skill_name="Python Web Development", category="Programming"),
        WantedSkill(user_id=users[2].id, skill_name="Python Web Development", category="Programming"),
    ]
    db.session.add_all(wanted)
    db.session.commit()

    requests = [
        ContactRequest(sender_id=users[1].id, mentor_id=users[0].id, skill_id=skills[0].id, exchange_skill_id=skills[1].id, status="Matched"),
        ContactRequest(sender_id=users[2].id, mentor_id=users[1].id, skill_id=skills[1].id, exchange_skill_id=skills[2].id, status="Matched"),
        ContactRequest(sender_id=users[3].id, mentor_id=users[2].id, skill_id=skills[2].id, exchange_skill_id=skills[3].id, status="Completed"),
        ContactRequest(sender_id=users[4].id, mentor_id=users[0].id, skill_id=skills[9].id, status="Pending Mutual Approval"),
        ContactRequest(sender_id=users[7].id, mentor_id=users[6].id, skill_id=skills[6].id, status="Completed"),
    ]
    db.session.add_all(requests)
    db.session.commit()

    sessions = [
        Session(mentor_id=users[0].id, learner_id=users[1].id, skill_id=skills[0].id, meeting_link="https://zoom.us/j/rahul123", meeting_type="Zoom", session_date=datetime.utcnow() + timedelta(days=1), status="Scheduled"),
        Session(mentor_id=users[1].id, learner_id=users[2].id, skill_id=skills[1].id, meeting_link="https://meet.google.com/priya-abc", meeting_type="Google Meet", session_date=datetime.utcnow() + timedelta(days=2), status="Scheduled"),
        Session(mentor_id=users[2].id, learner_id=users[3].id, skill_id=skills[2].id, meeting_link="https://zoom.us/j/amit456", meeting_type="Zoom", session_date=datetime.utcnow() - timedelta(days=5), status="Completed"),
        Session(mentor_id=users[6].id, learner_id=users[7].id, skill_id=skills[6].id, meeting_link="https://meet.google.com/vikas-xyz", meeting_type="Google Meet", session_date=datetime.utcnow() - timedelta(days=2), status="Completed"),
    ]
    db.session.add_all(sessions)
    db.session.commit()

    ratings = [
        Rating(skill_id=skills[2].id, mentor_id=users[2].id, rater_id=users[3].id, rating_value=5, review="Amit is a fantastic UX mentor!"),
        Rating(skill_id=skills[6].id, mentor_id=users[6].id, rater_id=users[7].id, rating_value=4, review="Learned open chords very effectively."),
        Rating(skill_id=skills[0].id, mentor_id=users[0].id, rater_id=users[2].id, rating_value=5, review="Rahul perfectly breaks down Flask APIs."),
        Rating(skill_id=skills[0].id, mentor_id=users[0].id, rater_id=users[4].id, rating_value=5, review="Awesome mentor."),
        Rating(skill_id=skills[0].id, mentor_id=users[0].id, rater_id=users[5].id, rating_value=5, review="Extremely knowledgeable on Python."),
    ]
    db.session.add_all(ratings)
    db.session.commit()

    badges = [
        Badge(user_id=users[0].id, badge_name="Top Mentor"),
        Badge(user_id=users[2].id, badge_name="Rising Star"),
    ]
    db.session.add_all(badges)

    messages = [
        Message(sender_id=users[1].id, recipient_id=users[0].id, content="Hi Rahul! Looking forward to our Flask API session tomorrow."),
        Message(sender_id=users[0].id, recipient_id=users[1].id, content="Same here Priya! Feel free to bring any project endpoints you want to review."),
    ]
    db.session.add_all(messages)
    db.session.commit()


def seed_if_empty():
    """Seed sample data only if no users exist yet."""
    if User.query.count() == 0:
        populate_sample_data()


def seed_database():
    """Drop all tables, recreate schema, and seed fresh sample data."""
    from app import create_app
    app = create_app()
    with app.app_context():
        db.drop_all()
        db.create_all()
        populate_sample_data()
        print("Database seeded successfully with sample platform data!")


if __name__ == '__main__':
    seed_database()
