"""
SkillXchange — Account Deactivation & History Preservation Test Suite
Tests all behaviors for user deactivation, session invalidation, public catalog filtering,
and exchange history preservation.
"""
import os
import sys
import unittest
import re
from datetime import datetime, timedelta

WORKSPACE = r"c:\Users\giris\Downloads\SkillXchange"
if WORKSPACE not in sys.path:
    sys.path.insert(0, WORKSPACE)

os.environ['FLASK_ENV'] = 'testing'
os.environ['SECRET_KEY'] = 'test-secret-key-for-deactivation-suite'

from app import create_app, db, bcrypt
from app.models import User, Skill, ContactRequest, Session, Message, Rating, WantedSkill, Badge
from config import Config


class DeactivationTestConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    SERVER_NAME = 'localhost'


class AccountDeactivationTestSuite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app(DeactivationTestConfig)
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
            db.session.query(Rating).delete()
            db.session.query(Session).delete()
            db.session.query(ContactRequest).delete()
            db.session.query(Message).delete()
            db.session.query(WantedSkill).delete()
            db.session.query(Badge).delete()
            db.session.query(Skill).delete()
            db.session.query(User).delete()
            db.session.commit()

    def _extract_csrf_token(self, html_text):
        match = re.search(r'name="csrf_token"\s+value="([^"]+)"', html_text)
        if match:
            return match.group(1)
        match_meta = re.search(r'<meta\s+name="csrf-token"\s+content="([^"]+)"', html_text)
        if match_meta:
            return match_meta.group(1)
        return None

    def _create_user(self, name, email, password="Password123!", role="User", is_active=True):
        hashed = bcrypt.generate_password_hash(password).decode('utf-8')
        user = User(
            name=name,
            email=email,
            password_hash=hashed,
            role=role,
            is_active=is_active
        )
        db.session.add(user)
        db.session.commit()
        return user.id

    # =========================================================================
    # 1. LOGIN BLOCKING & SESSION INVALIDATION
    # =========================================================================
    def test_01_active_user_can_login_deactivated_user_blocked(self):
        """Active user can log in; deactivated account is rejected with warning."""
        with self.app.app_context():
            active_id = self._create_user("Active User", "active@example.com", is_active=True)
            inactive_id = self._create_user("Inactive User", "inactive@example.com", is_active=False)

        # 1. Active user login
        res_page = self.client.get('/login')
        token = self._extract_csrf_token(res_page.get_data(as_text=True))
        res_login = self.client.post('/login', data={
            'csrf_token': token,
            'email': 'active@example.com',
            'password': 'Password123!'
        }, follow_redirects=True)
        self.assertEqual(res_login.status_code, 200)
        self.assertIn("dashboard", res_login.request.path.lower())

        # Logout
        self.client.get('/logout')

        # 2. Deactivated user login attempt
        res_page = self.client.get('/login')
        token = self._extract_csrf_token(res_page.get_data(as_text=True))
        res_inactive = self.client.post('/login', data={
            'csrf_token': token,
            'email': 'inactive@example.com',
            'password': 'Password123!'
        }, follow_redirects=True)
        self.assertEqual(res_inactive.status_code, 200)
        self.assertIn("deactivated", res_inactive.get_data(as_text=True).lower())

    def test_02_existing_session_invalidated_when_user_deactivated(self):
        """Deactivating a user invalidates their active cookie session on subsequent requests."""
        with self.app.app_context():
            uid = self._create_user("Session User", "sess@example.com", is_active=True)

        # Set session cookie
        with self.client.session_transaction() as sess:
            sess['_user_id'] = str(uid)
            sess['_fresh'] = True

        # Verify access when active
        res = self.client.get('/dashboard', follow_redirects=False)
        self.assertEqual(res.status_code, 200)

        # Deactivate user in database
        with self.app.app_context():
            user = db.session.get(User, uid)
            user.is_active = False
            db.session.commit()

        # Subsequent request with existing cookie must be rejected (redirected to login)
        res_after = self.client.get('/dashboard', follow_redirects=False)
        self.assertEqual(res_after.status_code, 302)
        self.assertIn("login", res_after.headers.get('Location', '').lower())

    # =========================================================================
    # 2. ADMIN DEACTIVATION / REACTIVATION WORKFLOW
    # =========================================================================
    def test_03_admin_can_toggle_deactivation_and_reactivation(self):
        """Admin toggles active status back and forth without deleting records."""
        with self.app.app_context():
            admin_id = self._create_user("Admin User", "admin@example.com", role="Admin")
            target_id = self._create_user("Target User", "target@example.com", role="User", is_active=True)

        with self.client.session_transaction() as sess:
            sess['_user_id'] = str(admin_id)
            sess['_fresh'] = True

        # Fetch CSRF token from admin users page
        res = self.client.get('/admin/users')
        token = self._extract_csrf_token(res.get_data(as_text=True))

        # 1. Deactivate
        res_deact = self.client.post(f'/admin/toggle_user_status/{target_id}', data={
            'csrf_token': token
        }, follow_redirects=True)
        self.assertEqual(res_deact.status_code, 200)
        self.assertIn("deactivated", res_deact.get_data(as_text=True).lower())

        with self.app.app_context():
            target = db.session.get(User, target_id)
            self.assertFalse(target.is_active)

        # 2. Reactivate
        token = self._extract_csrf_token(res_deact.get_data(as_text=True))
        res_react = self.client.post(f'/admin/toggle_user_status/{target_id}', data={
            'csrf_token': token
        }, follow_redirects=True)
        self.assertEqual(res_react.status_code, 200)
        self.assertIn("activated", res_react.get_data(as_text=True).lower())

        with self.app.app_context():
            target = db.session.get(User, target_id)
            self.assertTrue(target.is_active)

    def test_04_admin_cannot_deactivate_own_account(self):
        """Admin cannot deactivate their own account."""
        with self.app.app_context():
            admin_id = self._create_user("Self Admin", "selfadmin@example.com", role="Admin")

        with self.client.session_transaction() as sess:
            sess['_user_id'] = str(admin_id)
            sess['_fresh'] = True

        res = self.client.get('/admin/users')
        token = self._extract_csrf_token(res.get_data(as_text=True))

        res_post = self.client.post(f'/admin/toggle_user_status/{admin_id}', data={
            'csrf_token': token
        }, follow_redirects=True)
        self.assertEqual(res_post.status_code, 200)
        self.assertIn("cannot change the active status of your own account", res_post.get_data(as_text=True).lower())

        with self.app.app_context():
            admin = db.session.get(User, admin_id)
            self.assertTrue(admin.is_active)

    # =========================================================================
    # 3. CATALOG & PUBLIC BROWSING FILTERING
    # =========================================================================
    def test_05_inactive_mentor_skills_hidden_from_browse(self):
        """Skills of deactivated mentors do not appear in /browse and redirect from /skill/<id>."""
        with self.app.app_context():
            mentor1_id = self._create_user("Active Mentor", "mentor1@example.com", is_active=True)
            mentor2_id = self._create_user("Inactive Mentor", "mentor2@example.com", is_active=False)

            skill1 = Skill(
                mentor_id=mentor1_id,
                skill_name="Python Programming",
                category="Technology",
                description="Learn Python",
                verification_status="Approved"
            )
            skill2 = Skill(
                mentor_id=mentor2_id,
                skill_name="Guitar Basics",
                category="Music",
                description="Learn Guitar",
                verification_status="Approved"
            )
            db.session.add_all([skill1, skill2])
            db.session.commit()
            s1_id = skill1.id
            s2_id = skill2.id

        # 1. /browse must include skill1 but exclude skill2
        res_browse = self.client.get('/browse')
        self.assertEqual(res_browse.status_code, 200)
        html = res_browse.get_data(as_text=True)
        self.assertIn("Python Programming", html)
        self.assertNotIn("Guitar Basics", html)

        # 2. Accessing skill2 directly must redirect to /browse
        res_detail2 = self.client.get(f'/skill/{s2_id}', follow_redirects=False)
        self.assertEqual(res_detail2.status_code, 302)
        self.assertIn("/browse", res_detail2.headers.get('Location', ''))

        # 3. Accessing skill1 directly must succeed
        res_detail1 = self.client.get(f'/skill/{s1_id}', follow_redirects=False)
        self.assertEqual(res_detail1.status_code, 200)

    # =========================================================================
    # 4. HISTORY PRESERVATION UPON DEACTIVATION
    # =========================================================================
    def test_06_deactivation_preserves_messages_ratings_sessions(self):
        """Deactivating an account leaves messages, ratings, sessions, and requests intact."""
        with self.app.app_context():
            m_id = self._create_user("Mentor User", "m_hist@example.com", is_active=True)
            l_id = self._create_user("Learner User", "l_hist@example.com", is_active=True)

            skill = Skill(
                mentor_id=m_id,
                skill_name="Advanced SQL",
                category="Technology",
                verification_status="Approved"
            )
            db.session.add(skill)
            db.session.commit()

            # Message
            msg = Message(sender_id=l_id, recipient_id=m_id, content="Hi Mentor!")
            # Contact request
            req = ContactRequest(sender_id=l_id, mentor_id=m_id, skill_id=skill.id, status="Matched")
            # Session
            sess = Session(
                mentor_id=m_id,
                learner_id=l_id,
                skill_id=skill.id,
                meeting_link="https://meet.google.com/abc-defg-hij",
                session_date=datetime.utcnow() + timedelta(days=1),
                status="Scheduled"
            )
            # Rating
            rating = Rating(skill_id=skill.id, mentor_id=m_id, rater_id=l_id, rating_value=5, review="Great session!")
            db.session.add_all([msg, req, sess, rating])
            db.session.commit()

            skill_id = skill.id
            msg_id = msg.id
            req_id = req.id
            sess_id = sess.id
            rating_id = rating.id

        # Deactivate mentor
        with self.app.app_context():
            mentor = db.session.get(User, m_id)
            mentor.is_active = False
            db.session.commit()

        # Verify all history records are still in the database
        with self.app.app_context():
            self.assertIsNotNone(db.session.get(Message, msg_id), "Message must not be deleted")
            self.assertIsNotNone(db.session.get(ContactRequest, req_id), "Contact request must not be deleted")
            self.assertIsNotNone(db.session.get(Session, sess_id), "Session must not be deleted")
            self.assertIsNotNone(db.session.get(Rating, rating_id), "Rating must not be deleted")
            self.assertIsNotNone(db.session.get(Skill, skill_id), "Skill record must not be deleted")


if __name__ == '__main__':
    unittest.main()
