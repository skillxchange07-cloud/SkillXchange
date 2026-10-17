"""
Phase 2 Verification Test Suite
Tests all security hardening and workflow bug fixes implemented in Phase 2.
"""
import os
import sys
import unittest
import re
from io import BytesIO
from datetime import datetime

# Ensure workspace root is in python path
WORKSPACE = r"c:\Users\giris\Downloads\SkillXchange"
if WORKSPACE not in sys.path:
    sys.path.insert(0, WORKSPACE)

# Configure environment for testing
os.environ['FLASK_ENV'] = 'testing'
os.environ['SECRET_KEY'] = 'test-secret-key-for-verification-only'

from app import create_app, db
from app.models import User, Skill, ContactRequest, Session, Message, WantedSkill
from app.routes.mentorship import parse_session_datetime
from config import Config


class TestConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    SERVER_NAME = 'localhost'


class Phase2SecurityAndWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app(TestConfig)
        cls.client = cls.app.test_client()

        with cls.app.app_context():
            db.create_all()

    @classmethod
    def tearDownClass(cls):
        with cls.app.app_context():
            db.session.remove()
            db.drop_all()

    def setUp(self):
        with self.app.app_context():
            db.session.query(Session).delete()
            db.session.query(ContactRequest).delete()
            db.session.query(Message).delete()
            db.session.query(WantedSkill).delete()
            db.session.query(Skill).delete()
            db.session.query(User).delete()
            db.session.commit()

    def _extract_csrf_token(self, html_text):
        """Extract CSRF token from rendered HTML page."""
        match = re.search(r'name="csrf_token"\s+value="([^"]+)"', html_text)
        if match:
            return match.group(1)
        match_meta = re.search(r'<meta\s+name="csrf-token"\s+content="([^"]+)"', html_text)
        if match_meta:
            return match_meta.group(1)
        return None

    # =========================================================================
    # 1. SECRET_KEY HARDENING TESTS
    # =========================================================================
    def test_01_secret_key_production_enforcement(self):
        """Verify Config raises RuntimeError if SECRET_KEY is not set in production."""
        import importlib
        import config
        orig_flask_env = os.environ.get('FLASK_ENV')
        orig_secret_key = os.environ.get('SECRET_KEY')
        try:
            os.environ['FLASK_ENV'] = 'production'
            if 'SECRET_KEY' in os.environ:
                del os.environ['SECRET_KEY']

            with self.assertRaises(RuntimeError) as ctx:
                importlib.reload(config)
            self.assertIn("SECRET_KEY environment variable must be set in production", str(ctx.exception))
        finally:
            if orig_flask_env is not None:
                os.environ['FLASK_ENV'] = orig_flask_env
            else:
                os.environ.pop('FLASK_ENV', None)
            if orig_secret_key is not None:
                os.environ['SECRET_KEY'] = orig_secret_key
            importlib.reload(config)

    # =========================================================================
    # 2. CSRF PROTECTION TESTS
    # =========================================================================
    def test_02_csrf_tokens_present_on_pages(self):
        """Verify CSRF tokens are injected into forms and meta tags."""
        # Login page
        res = self.client.get('/login')
        self.assertEqual(res.status_code, 200)
        token = self._extract_csrf_token(res.get_data(as_text=True))
        self.assertIsNotNone(token, "CSRF token missing in login page")

        # Register page
        res = self.client.get('/register')
        self.assertEqual(res.status_code, 200)
        token = self._extract_csrf_token(res.get_data(as_text=True))
        self.assertIsNotNone(token, "CSRF token missing in register page")

    def test_03_csrf_blocks_unauthorized_post(self):
        """Verify POST without CSRF token is rejected with HTTP 400."""
        # Direct POST without CSRF token
        res = self.client.post('/login', data={'email': 'test@example.com', 'password': 'password123'})
        self.assertEqual(res.status_code, 400, "POST without CSRF token must return 400 Bad Request")
        self.assertIn("CSRF", res.get_data(as_text=True))

    def test_04_csrf_allows_valid_token_post(self):
        """Verify POST with valid CSRF token is processed."""
        res = self.client.get('/register')
        token = self._extract_csrf_token(res.get_data(as_text=True))
        self.assertIsNotNone(token)

        # POST registration with valid token
        res_post = self.client.post('/register', data={
            'csrf_token': token,
            'name': 'Test CSRF User',
            'email': 'csrf_user@example.com',
            'password': 'StrongPassword123!',
            'phone': '1234567890'
        }, follow_redirects=True)
        # Should succeed (redirect to login) with flash message, NOT 400
        self.assertEqual(res_post.status_code, 200)
        self.assertIn("Your account has been created!", res_post.get_data(as_text=True))

    # =========================================================================
    # 3. ADMIN BACKDOOR REMOVAL TEST
    # =========================================================================
    def test_05_admin_registration_backdoor_removed(self):
        """Verify registering with admin@skillxchange.com no longer grants Admin role."""
        res = self.client.get('/register')
        token = self._extract_csrf_token(res.get_data(as_text=True))

        res_post = self.client.post('/register', data={
            'csrf_token': token,
            'name': 'Backdoor Attacker',
            'email': 'admin@skillxchange.com',
            'password': 'AttackerPassword123!',
            'phone': '9876543210'
        }, follow_redirects=True)
        self.assertEqual(res_post.status_code, 200)

        with self.app.app_context():
            user = User.query.filter_by(email='admin@skillxchange.com').first()
            self.assertIsNotNone(user)
            self.assertEqual(user.role, 'User', f"CRITICAL: User was granted role '{user.role}' instead of 'User'!")

    # =========================================================================
    # 4. UNRESTRICTED FILE UPLOAD HARDENING TESTS
    # =========================================================================
    def test_06_video_upload_validation_rejects_disallowed_extensions(self):
        """Verify malicious or disallowed extensions (.exe, .php, .sh, .txt) are rejected."""
        with self.app.app_context():
            from werkzeug.security import generate_password_hash
            user = User(
                name="Skill Creator",
                email="creator@example.com",
                password_hash=generate_password_hash("Password123!"),
                role="User"
            )
            db.session.add(user)
            db.session.commit()
            uid = user.id

        with self.client.session_transaction() as sess:
            sess['_user_id'] = str(uid)
            sess['_fresh'] = True

        res = self.client.get('/add_skill')
        token = self._extract_csrf_token(res.get_data(as_text=True))

        # Attempt disallowed upload
        malicious_file = (BytesIO(b'MZ...fake executable content'), 'malware.exe')
        res_post = self.client.post('/add_skill', data={
            'csrf_token': token,
            'skill_name': 'Hacked Skill',
            'category': 'Technology',
            'description': 'Malicious skill upload test',
            'demo_video': malicious_file
        }, follow_redirects=True)

        self.assertEqual(res_post.status_code, 200)
        self.assertIn("Invalid video format", res_post.get_data(as_text=True))

        with self.app.app_context():
            skill = Skill.query.filter_by(skill_name='Hacked Skill').first()
            self.assertIsNone(skill, "Disallowed file upload must not create skill record")

    def test_07_video_upload_accepts_valid_video_format(self):
        """Verify legitimate video extension (.mp4) is accepted."""
        with self.app.app_context():
            from werkzeug.security import generate_password_hash
            user = User(
                name="Valid Creator",
                email="validcreator@example.com",
                password_hash=generate_password_hash("Password123!"),
                role="User"
            )
            db.session.add(user)
            db.session.commit()
            uid = user.id

        with self.client.session_transaction() as sess:
            sess['_user_id'] = str(uid)
            sess['_fresh'] = True

        res = self.client.get('/add_skill')
        token = self._extract_csrf_token(res.get_data(as_text=True))

        valid_video = (BytesIO(b'\x00\x00\x00\x18ftypmp42...fake mp4 bytes'), 'intro.mp4')
        res_post = self.client.post('/add_skill', data={
            'csrf_token': token,
            'skill_name': 'Valid Python Course',
            'category': 'Programming',
            'description': 'Valid skill upload test',
            'demo_video': valid_video
        }, follow_redirects=True)

        self.assertEqual(res_post.status_code, 200)
        self.assertIn("Skill added!", res_post.get_data(as_text=True))

        with self.app.app_context():
            skill = Skill.query.filter_by(skill_name='Valid Python Course').first()
            self.assertIsNotNone(skill)
            self.assertTrue(skill.demo_video_path.endswith('.mp4'))

    # =========================================================================
    # 5. SCHEDULING & RESCHEDULING TESTS
    # =========================================================================
    def test_08_parse_session_datetime_formats(self):
        """Verify parse_session_datetime handles ISO HTML5, separate, and combined formats."""
        # 1. HTML5 datetime-local format: YYYY-MM-DDTHH:MM
        dt1 = parse_session_datetime("2026-11-15T14:30")
        self.assertIsNotNone(dt1)
        self.assertEqual(dt1, datetime(2026, 11, 15, 14, 30))

        # 2. Separate date and time arguments
        dt2 = parse_session_datetime("2026-11-15", "16:45")
        self.assertIsNotNone(dt2)
        self.assertEqual(dt2, datetime(2026, 11, 15, 16, 45))

        # 3. Space-separated format
        dt3 = parse_session_datetime("2026-11-15 10:00")
        self.assertIsNotNone(dt3)
        self.assertEqual(dt3, datetime(2026, 11, 15, 10, 0))

        # 4. Invalid input handling
        dt_invalid = parse_session_datetime("invalid-date-string")
        self.assertIsNone(dt_invalid)

        dt_empty = parse_session_datetime("", "")
        self.assertIsNone(dt_empty)

    def test_09_rescheduling_detects_conflicts(self):
        """Verify rescheduling detects schedule conflicts for the mentor/learner."""
        with self.app.app_context():
            mentor = User(name="Mentor A", email="mentora@example.com", password_hash="hash")
            learner1 = User(name="Learner 1", email="learner1@example.com", password_hash="hash")
            learner2 = User(name="Learner 2", email="learner2@example.com", password_hash="hash")
            db.session.add_all([mentor, learner1, learner2])
            db.session.commit()

            skill = Skill(mentor_id=mentor.id, skill_name="React Tutoring", category="Web", description="Tutoring")
            db.session.add(skill)
            db.session.commit()

            dt_conflict = datetime(2026, 11, 20, 14, 0)
            session1 = Session(
                mentor_id=mentor.id,
                learner_id=learner1.id,
                skill_id=skill.id,
                meeting_link="https://meet.google.com/abc-defg-hij",
                session_date=dt_conflict,
                status='Scheduled'
            )
            session2 = Session(
                mentor_id=mentor.id,
                learner_id=learner2.id,
                skill_id=skill.id,
                meeting_link="https://meet.google.com/xyz-uvw-rst",
                session_date=datetime(2026, 11, 20, 18, 0),
                status='Scheduled'
            )
            db.session.add_all([session1, session2])
            db.session.commit()

            session2_id = session2.id
            learner2_id = learner2.id

        with self.client.session_transaction() as sess:
            sess['_user_id'] = str(learner2_id)
            sess['_fresh'] = True

        res = self.client.get('/my_requests')
        token = self._extract_csrf_token(res.get_data(as_text=True))

        # Try to reschedule session2 to exact time of session1
        res_post = self.client.post(f'/reschedule_session/{session2_id}', data={
            'csrf_token': token,
            'session_date': '2026-11-20T14:00'
        }, follow_redirects=True)

        self.assertEqual(res_post.status_code, 200)
        self.assertIn("Conflict detected", res_post.get_data(as_text=True))

    # =========================================================================
    # 6. MENTORSHIP ACCEPTANCE & MATCHING FLOW
    # =========================================================================
    def test_10_mentorship_acceptance_and_barter_matching(self):
        """Verify accepting a request updates status to 'Matched' and sets exchange skill."""
        with self.app.app_context():
            mentor = User(name="Mentor M", email="mentorm@example.com", password_hash="hash")
            learner = User(name="Learner L", email="learnerl@example.com", password_hash="hash")
            db.session.add_all([mentor, learner])
            db.session.commit()

            skill_m = Skill(mentor_id=mentor.id, skill_name="Python Mentoring", category="Coding", description="Desc")
            skill_l = Skill(mentor_id=learner.id, skill_name="Graphic Design", category="Design", description="Desc")
            db.session.add_all([skill_m, skill_l])
            db.session.commit()

            req = ContactRequest(
                sender_id=learner.id,
                mentor_id=mentor.id,
                skill_id=skill_m.id,
                status='Pending Mutual Approval'
            )
            db.session.add(req)
            db.session.commit()
            req_id = req.id
            exchange_id = skill_l.id
            mentor_id = mentor.id

        with self.client.session_transaction() as sess:
            sess['_user_id'] = str(mentor_id)
            sess['_fresh'] = True

        res = self.client.get('/my_requests')
        token = self._extract_csrf_token(res.get_data(as_text=True))

        res_post = self.client.post(f'/accept_request/{req_id}', data={
            'csrf_token': token,
            'exchange_skill_id': str(exchange_id)
        }, follow_redirects=True)

        self.assertEqual(res_post.status_code, 200)
        self.assertIn("Match confirmed!", res_post.get_data(as_text=True))

        with self.app.app_context():
            updated_req = ContactRequest.query.get(req_id)
            self.assertEqual(updated_req.status, 'Matched')
            self.assertEqual(updated_req.exchange_skill_id, exchange_id)

    # =========================================================================
    # 7. REAL-TIME CHAT MESSAGE RENDERING FIX
    # =========================================================================
    def test_11_chat_template_supports_content_and_message_fields(self):
        """Verify messages.html handles both data.content and data.message gracefully."""
        with open(os.path.join(WORKSPACE, 'app', 'templates', 'messages.html'), 'r', encoding='utf-8') as f:
            template_code = f.read()

        self.assertIn("data.content || data.message", template_code,
                      "messages.html must read data.content || data.message to prevent undefined display")

    # =========================================================================
    # 8. RATE LIMITING TESTS
    # =========================================================================
    def test_12_rate_limiter_registered_on_auth_routes(self):
        """Verify rate limits are configured on login and register endpoints."""
        with open(os.path.join(WORKSPACE, 'app', 'routes', 'auth.py'), 'r', encoding='utf-8') as f:
            auth_code = f.read()

        self.assertIn('@limiter.limit("10 per minute"', auth_code)
        self.assertIn('@limiter.limit("15 per hour"', auth_code)


if __name__ == '__main__':
    unittest.main(verbosity=2)
