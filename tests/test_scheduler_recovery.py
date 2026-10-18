"""
SkillXchange — Scheduler Recovery and Reliability Test Suite
Verifies that eligible pending session reminders are accurately reconstructed
upon application restart/wake-up, while preventing duplicate jobs, past session reminders,
and reminders for cancelled, completed, or already-dispatched sessions.
"""
import os
import sys
import unittest
from datetime import datetime, timedelta

WORKSPACE = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if WORKSPACE not in sys.path:
    sys.path.insert(0, WORKSPACE)

os.environ['FLASK_ENV'] = 'testing'
os.environ['SECRET_KEY'] = 'test-secret-key-for-scheduler-recovery'

from app import create_app, db, scheduler, bcrypt
from app.models import User, Skill, Session, Notification
from app.utils.notifications import recover_scheduled_reminders
from config import Config


class SchedulerRecoveryTestConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    SERVER_NAME = 'localhost'


class SchedulerRecoveryTestSuite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app(SchedulerRecoveryTestConfig)
        with cls.app.app_context():
            db.create_all()

    @classmethod
    def tearDownClass(cls):
        with cls.app.app_context():
            db.session.remove()
            db.drop_all()

    def setUp(self):
        # Clear database tables and clear scheduler jobs before each test
        with self.app.app_context():
            Notification.query.delete()
            Session.query.delete()
            Skill.query.delete()
            User.query.delete()
            db.session.commit()

            # Seed base users and skill
            mentor = User(
                name="Mentor User",
                email="mentor@test.com",
                password_hash=bcrypt.generate_password_hash("pass123").decode('utf-8'),
                phone="9876543210"
            )
            learner = User(
                name="Learner User",
                email="learner@test.com",
                password_hash=bcrypt.generate_password_hash("pass123").decode('utf-8'),
                phone="9876543211"
            )
            db.session.add_all([mentor, learner])
            db.session.commit()

            skill = Skill(
                mentor_id=mentor.id,
                skill_name="Python Mastery",
                category="Programming",
                verification_status="Approved"
            )
            db.session.add(skill)
            db.session.commit()

            self.mentor_id = mentor.id
            self.learner_id = learner.id
            self.skill_id = skill.id

        # Clean any scheduler jobs
        for job in scheduler.get_jobs():
            scheduler.remove_job(job.id)

    def tearDown(self):
        for job in scheduler.get_jobs():
            scheduler.remove_job(job.id)

    # -------------------------------------------------------------------------
    # 1. Recovery of eligible future scheduled sessions
    # -------------------------------------------------------------------------
    def test_01_recovery_of_eligible_future_session(self):
        with self.app.app_context():
            future_time = datetime.utcnow() + timedelta(days=2)
            sess = Session(
                mentor_id=self.mentor_id,
                learner_id=self.learner_id,
                skill_id=self.skill_id,
                meeting_link="https://meet.jit.si/skillxchange_test_1",
                meeting_type="Google Meet",
                session_date=future_time,
                status="Scheduled"
            )
            db.session.add(sess)
            db.session.commit()
            sess_id = sess.id

        # Prior to recovery, scheduler has 0 jobs
        self.assertEqual(len(scheduler.get_jobs()), 0)

        # Trigger recovery
        recovered = recover_scheduled_reminders(self.app)
        self.assertEqual(recovered, 1)

        # Confirm both email and SMS reminder jobs are now scheduled
        email_job = scheduler.get_job(f'session_reminder_{sess_id}')
        sms_job = scheduler.get_job(f'sms_reminder_{sess_id}')
        self.assertIsNotNone(email_job)
        self.assertIsNotNone(sms_job)

    # -------------------------------------------------------------------------
    # 2. Duplicate registration prevention
    # -------------------------------------------------------------------------
    def test_02_duplicate_recovery_prevention(self):
        with self.app.app_context():
            future_time = datetime.utcnow() + timedelta(days=3)
            sess = Session(
                mentor_id=self.mentor_id,
                learner_id=self.learner_id,
                skill_id=self.skill_id,
                meeting_link="https://meet.jit.si/skillxchange_test_2",
                meeting_type="Google Meet",
                session_date=future_time,
                status="Scheduled"
            )
            db.session.add(sess)
            db.session.commit()
            sess_id = sess.id

        # First recovery run
        recovered_first = recover_scheduled_reminders(self.app)
        self.assertEqual(recovered_first, 1)
        initial_job_count = len(scheduler.get_jobs())

        # Second recovery run (simulating another wake-up or request)
        recovered_second = recover_scheduled_reminders(self.app)
        self.assertEqual(recovered_second, 0)
        self.assertEqual(len(scheduler.get_jobs()), initial_job_count)

    # -------------------------------------------------------------------------
    # 3. Filtering past sessions
    # -------------------------------------------------------------------------
    def test_03_past_sessions_are_not_recovered(self):
        with self.app.app_context():
            past_time = datetime.utcnow() - timedelta(hours=2)
            sess = Session(
                mentor_id=self.mentor_id,
                learner_id=self.learner_id,
                skill_id=self.skill_id,
                meeting_link="https://meet.jit.si/skillxchange_test_3",
                meeting_type="Google Meet",
                session_date=past_time,
                status="Scheduled"
            )
            db.session.add(sess)
            db.session.commit()

        recovered = recover_scheduled_reminders(self.app)
        self.assertEqual(recovered, 0)
        self.assertEqual(len(scheduler.get_jobs()), 0)

    # -------------------------------------------------------------------------
    # 4. Filtering cancelled and completed sessions
    # -------------------------------------------------------------------------
    def test_04_cancelled_and_completed_sessions_are_not_recovered(self):
        with self.app.app_context():
            future_time = datetime.utcnow() + timedelta(days=2)
            sess_cancelled = Session(
                mentor_id=self.mentor_id,
                learner_id=self.learner_id,
                skill_id=self.skill_id,
                meeting_link="https://meet.jit.si/skillxchange_test_4a",
                meeting_type="Google Meet",
                session_date=future_time,
                status="Cancelled"
            )
            sess_completed = Session(
                mentor_id=self.mentor_id,
                learner_id=self.learner_id,
                skill_id=self.skill_id,
                meeting_link="https://meet.jit.si/skillxchange_test_4b",
                meeting_type="Google Meet",
                session_date=future_time,
                status="Completed"
            )
            db.session.add_all([sess_cancelled, sess_completed])
            db.session.commit()

        recovered = recover_scheduled_reminders(self.app)
        self.assertEqual(recovered, 0)
        self.assertEqual(len(scheduler.get_jobs()), 0)

    # -------------------------------------------------------------------------
    # 5. Filtering sessions whose reminders were already dispatched
    # -------------------------------------------------------------------------
    def test_05_already_dispatched_reminders_are_not_rescheduled(self):
        with self.app.app_context():
            future_time = datetime.utcnow() + timedelta(days=2)
            sess = Session(
                mentor_id=self.mentor_id,
                learner_id=self.learner_id,
                skill_id=self.skill_id,
                meeting_link="https://meet.jit.si/skillxchange_test_5",
                meeting_type="Google Meet",
                session_date=future_time,
                status="Scheduled"
            )
            db.session.add(sess)
            db.session.commit()
            sess_id = sess.id

            # Pre-record dispatch notifications for this session
            notif_email = Notification(
                user_id=self.learner_id,
                type="Session_Reminder",
                message=f"Reminder dispatched for Session #{sess_id}"
            )
            notif_sms = Notification(
                user_id=self.learner_id,
                type="SMS_Reminder",
                message=f"SMS reminder dispatched for Session #{sess_id}"
            )
            db.session.add_all([notif_email, notif_sms])
            db.session.commit()

        recovered = recover_scheduled_reminders(self.app)
        self.assertEqual(recovered, 0)
        self.assertEqual(len(scheduler.get_jobs()), 0)


if __name__ == '__main__':
    unittest.main()
