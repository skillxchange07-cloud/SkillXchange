import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from config import Config


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    AUTO_SEED = True


def run_smoke_tests():
    from app import create_app, db
    from app.models import User, Skill, ContactRequest, Session, Rating

    app = create_app(TestConfig)
    client = app.test_client()

    # 1. Public endpoints
    for path in ['/', '/health', '/browse', '/leaderboard', '/login', '/register']:
        resp = client.get(path)
        assert resp.status_code == 200, f"GET {path} returned {resp.status_code}"

    # 2. Verify seed populated users and skills
    with app.app_context():
        assert User.query.count() >= 10
        assert Skill.query.filter_by(verification_status='Approved').count() >= 7

    # 3. Register a new learner & log in
    resp = client.post('/register', data={
        'name': 'Smoke Tester',
        'email': 'smoke@example.com',
        'phone': '9998887776',
        'password': 'password123'
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert b'Your account has been created' in resp.data

    resp = client.post('/login', data={
        'email': 'smoke@example.com',
        'password': 'password123'
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert b'Smoke Tester' in resp.data

    # 4. Authenticated pages
    for path in ['/dashboard', '/my_requests', '/messages', '/session_history', '/add_skill', '/edit_profile']:
        resp = client.get(path)
        assert resp.status_code == 200, f"Auth GET {path} returned {resp.status_code}"

    # 5. Send mentorship request to skill 1 & submit rating
    resp = client.post('/send_request', data={'skill_id': '1'}, follow_redirects=True)
    assert resp.status_code == 200
    assert b'Mentorship request sent' in resp.data

    resp = client.post('/submit_rating', data={
        'skill_id': '1',
        'mentor_id': '2',
        'rating_value': '5',
        'review': 'Great Flask walkthrough!'
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert b'Great Flask walkthrough!' in resp.data

    # 6. Log in as Rahul (mentor) and schedule the pending request via datetime-local
    client.get('/logout', follow_redirects=True)
    client.post('/login', data={'email': 'rahul@example.com', 'password': 'password123'}, follow_redirects=True)

    with app.app_context():
        smoke_user = User.query.filter_by(email='smoke@example.com').first()
        pending = ContactRequest.query.filter_by(sender_id=smoke_user.id, status='Pending Mutual Approval').first()
        assert pending is not None
        pending_id = pending.id

    resp = client.post(f'/schedule_session/{pending_id}', data={
        'meeting_type': 'Jitsi (In-App)',
        'meeting_link': '',
        'session_date': '2026-12-20T15:30'
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert b'Session scheduled' in resp.data

    with app.app_context():
        updated_req = ContactRequest.query.get(pending_id)
        assert updated_req.status == 'Matched'
        created_sess = Session.query.filter_by(learner_id=smoke_user.id, mentor_id=updated_req.mentor_id).first()
        assert created_sess is not None
        sess_id = created_sess.id

    # 7. Reschedule session via new_date
    resp = client.post(f'/reschedule_session/{sess_id}', data={
        'new_date': '2026-12-21T16:00'
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert b'Session rescheduled successfully' in resp.data

    # 8. Admin login & dashboard
    client.get('/logout', follow_redirects=True)
    resp = client.post('/login', data={'email': 'admin@skillxchange.com', 'password': 'password123'}, follow_redirects=True)
    assert resp.status_code == 200
    assert b'Admin Control Panel' in resp.data
    assert client.get('/api/admin/stats').status_code == 200
    assert client.get('/admin/users').status_code == 200

    print("ALL SMOKE TESTS PASSED")


if __name__ == '__main__':
    run_smoke_tests()
