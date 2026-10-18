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
from app.utils.notifications import recover_scheduled_reminders, schedule_reminder, reschedule_session_reminders
from app.utils.sms_service import schedule_sms_reminder
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

    # -------------------------------------------------------------------------
    # 6. Rescheduling updates both reminder jobs
    # -------------------------------------------------------------------------
    def test_06_rescheduling_updates_both_reminder_jobs(self):
        with self.app.app_context():
            initial_time = datetime.utcnow() + timedelta(days=2)
            sess = Session(
                mentor_id=self.mentor_id,
                learner_id=self.learner_id,
                skill_id=self.skill_id,
                meeting_link="https://meet.jit.si/skillxchange_test_6",
                meeting_type="Google Meet",
                session_date=initial_time,
                status="Scheduled"
            )
            db.session.add(sess)
            db.session.commit()
            sess_id = sess.id

            # Initial scheduling
            schedule_reminder(sess_id, initial_time)
            schedule_sms_reminder(sess_id, initial_time)

            email_job = scheduler.get_job(f'session_reminder_{sess_id}')
            sms_job = scheduler.get_job(f'sms_reminder_{sess_id}')
            self.assertIsNotNone(email_job)
            self.assertIsNotNone(sms_job)
            initial_email_run_date = email_job.trigger.run_date
            initial_sms_run_date = sms_job.trigger.run_date

            # Reschedule session to 5 days in future
            new_time = datetime.utcnow() + timedelta(days=5)
            reschedule_session_reminders(sess, new_time)

            # Check jobs updated
            updated_email_job = scheduler.get_job(f'session_reminder_{sess_id}')
            updated_sms_job = scheduler.get_job(f'sms_reminder_{sess_id}')
            self.assertIsNotNone(updated_email_job)
            self.assertIsNotNone(updated_sms_job)

            # Total jobs for this session must still be 2 (no duplicate jobs)
            session_jobs = [j for j in scheduler.get_jobs() if str(sess_id) in j.id]
            self.assertEqual(len(session_jobs), 2)

            # Verify run dates moved forward
            self.assertGreater(updated_email_job.trigger.run_date, initial_email_run_date)
            self.assertGreater(updated_sms_job.trigger.run_date, initial_sms_run_date)

            # Verify database was updated
            updated_sess = Session.query.get(sess_id)
            self.assertEqual(updated_sess.session_date, new_time)

    # -------------------------------------------------------------------------
    # 7. Old reminder record does not suppress new schedule's reminders
    # -------------------------------------------------------------------------
    def test_07_old_reminder_record_does_not_suppress_new_schedule(self):
        with self.app.app_context():
            old_time = datetime.utcnow() + timedelta(days=1)
            sess = Session(
                mentor_id=self.mentor_id,
                learner_id=self.learner_id,
                skill_id=self.skill_id,
                meeting_link="https://meet.jit.si/skillxchange_test_7",
                meeting_type="Google Meet",
                session_date=old_time,
                status="Scheduled"
            )
            db.session.add(sess)
            db.session.commit()
            sess_id = sess.id

            # Pre-record dispatch notifications for the old schedule
            old_email_notif = Notification(
                user_id=self.learner_id,
                type="Session_Reminder",
                message=f"Reminder dispatched for Session #{sess_id}"
            )
            old_sms_notif = Notification(
                user_id=self.learner_id,
                type="SMS_Reminder",
                message=f"SMS reminder dispatched for Session #{sess_id}"
            )
            db.session.add_all([old_email_notif, old_sms_notif])
            db.session.commit()

            # Reschedule session to 4 days in future
            new_time = datetime.utcnow() + timedelta(days=4)
            reschedule_session_reminders(sess, new_time)

            # Confirm old notifications were NOT deleted, but marked superseded
            notifs = Notification.query.filter_by(user_id=self.learner_id).all()
            self.assertEqual(len(notifs), 2)
            for n in notifs:
                self.assertIn("superseded", n.message)

            # Clear in-memory jobs to simulate process restart
            for job in scheduler.get_jobs():
                scheduler.remove_job(job.id)
            self.assertEqual(len(scheduler.get_jobs()), 0)

            # Run recovery: should successfully recover despite old notification history
            recovered = recover_scheduled_reminders(self.app)
            self.assertEqual(recovered, 1)

            # Verify jobs are scheduled for the new time
            email_job = scheduler.get_job(f'session_reminder_{sess_id}')
            sms_job = scheduler.get_job(f'sms_reminder_{sess_id}')
            self.assertIsNotNone(email_job)
            self.assertIsNotNone(sms_job)

    # -------------------------------------------------------------------------
    # 8. Failed rescheduling does not leave jobs inconsistent with database
    # -------------------------------------------------------------------------
    def test_08_failed_rescheduling_does_not_leave_jobs_inconsistent(self):
        with self.app.app_context():
            initial_time = datetime.utcnow() + timedelta(days=2)
            sess = Session(
                mentor_id=self.mentor_id,
                learner_id=self.learner_id,
                skill_id=self.skill_id,
                meeting_link="https://meet.jit.si/skillxchange_test_8",
                meeting_type="Google Meet",
                session_date=initial_time,
                status="Scheduled"
            )
            db.session.add(sess)
            db.session.commit()
            sess_id = sess.id

            # Initial reminder jobs
            schedule_reminder(sess_id, initial_time)
            schedule_sms_reminder(sess_id, initial_time)
            initial_email_job = scheduler.get_job(f'session_reminder_{sess_id}')
            initial_sms_job = scheduler.get_job(f'sms_reminder_{sess_id}')
            initial_email_run = initial_email_job.trigger.run_date
            initial_sms_run = initial_sms_job.trigger.run_date

            # Case A: Invalid date input via route
            client = self.app.test_client()
            with client.session_transaction() as flask_sess:
                flask_sess['_user_id'] = str(self.learner_id)
                flask_sess['_fresh'] = True

            res_invalid = client.post(f'/reschedule_session/{sess_id}', data={
                'session_date': 'invalid-date'
            }, follow_redirects=True)
            self.assertEqual(res_invalid.status_code, 200)

            # Verify DB session date is unchanged
            refreshed_sess = Session.query.get(sess_id)
            self.assertEqual(refreshed_sess.session_date, initial_time)

            # Verify scheduler jobs are untouched and consistent with DB
            email_job_after = scheduler.get_job(f'session_reminder_{sess_id}')
            sms_job_after = scheduler.get_job(f'sms_reminder_{sess_id}')
            self.assertEqual(email_job_after.trigger.run_date, initial_email_run)
            self.assertEqual(sms_job_after.trigger.run_date, initial_sms_run)

            # Case B: Database failure during commit in reschedule_session_reminders
            from unittest.mock import patch
            future_time = datetime.utcnow() + timedelta(days=6)
            with patch.object(db.session, 'commit', side_effect=Exception("Database lock error")):
                with self.assertRaises(Exception):
                    reschedule_session_reminders(refreshed_sess, future_time)

            # Verify DB was rolled back and jobs remain unchanged at original time
            db.session.rollback()
            sess_after_fail = Session.query.get(sess_id)
            self.assertEqual(sess_after_fail.session_date, initial_time)
            self.assertEqual(scheduler.get_job(f'session_reminder_{sess_id}').trigger.run_date, initial_email_run)
            self.assertEqual(scheduler.get_job(f'sms_reminder_{sess_id}').trigger.run_date, initial_sms_run)

    # -------------------------------------------------------------------------
    # 9. Rescheduling via route updates scheduler jobs
    # -------------------------------------------------------------------------
    def test_09_rescheduling_via_route_updates_scheduler_jobs(self):
        with self.app.app_context():
            initial_time = datetime.utcnow() + timedelta(days=2)
            sess = Session(
                mentor_id=self.mentor_id,
                learner_id=self.learner_id,
                skill_id=self.skill_id,
                meeting_link="https://meet.jit.si/skillxchange_test_9",
                meeting_type="Google Meet",
                session_date=initial_time,
                status="Scheduled"
            )
            db.session.add(sess)
            db.session.commit()
            sess_id = sess.id

            # Initial jobs
            schedule_reminder(sess_id, initial_time)
            schedule_sms_reminder(sess_id, initial_time)

            client = self.app.test_client()
            with client.session_transaction() as flask_sess:
                flask_sess['_user_id'] = str(self.learner_id)
                flask_sess['_fresh'] = True

            new_date_str = (datetime.utcnow() + timedelta(days=6)).strftime('%Y-%m-%dT15:00')
            res = client.post(f'/reschedule_session/{sess_id}', data={
                'session_date': new_date_str
            }, follow_redirects=True)
            self.assertEqual(res.status_code, 200)

            # Verify jobs updated to the new date
            email_job = scheduler.get_job(f'session_reminder_{sess_id}')
            sms_job = scheduler.get_job(f'sms_reminder_{sess_id}')
            self.assertIsNotNone(email_job)
            self.assertIsNotNone(sms_job)

            # Parsed new_dt
            expected_new_dt = datetime.strptime(new_date_str, '%Y-%m-%dT%H:%M')
            db_sess = Session.query.get(sess_id)
            self.assertEqual(db_sess.session_date, expected_new_dt)

            # Assert email job run date matches new session date minus 30 minutes
            expected_email_run = expected_new_dt - timedelta(minutes=30)
            email_run_date_naive = email_job.trigger.run_date.replace(tzinfo=None)
            self.assertEqual(email_run_date_naive, expected_email_run)

            # Assert SMS job run date matches new session date minus 1 hour
            expected_sms_run = expected_new_dt - timedelta(hours=1)
            sms_run_date_naive = sms_job.trigger.run_date.replace(tzinfo=None)
            self.assertEqual(sms_run_date_naive, expected_sms_run)

    # -------------------------------------------------------------------------
    # 10. Rescheduling does not modify notification records for overlapping IDs
    # -------------------------------------------------------------------------
    def test_10_rescheduling_does_not_affect_overlapping_session_ids(self):
        with self.app.app_context():
            # Create sessions with overlapping ID patterns (12 vs 123, and 1 vs 10)
            sess12 = Session(
                id=12,
                mentor_id=self.mentor_id,
                learner_id=self.learner_id,
                skill_id=self.skill_id,
                meeting_link="https://meet.jit.si/skillxchange_test_12",
                meeting_type="Google Meet",
                session_date=datetime.utcnow() + timedelta(days=2),
                status="Scheduled"
            )
            sess123 = Session(
                id=123,
                mentor_id=self.mentor_id,
                learner_id=self.learner_id,
                skill_id=self.skill_id,
                meeting_link="https://meet.jit.si/skillxchange_test_123",
                meeting_type="Google Meet",
                session_date=datetime.utcnow() + timedelta(days=3),
                status="Scheduled"
            )
            sess1 = Session(
                id=1,
                mentor_id=self.mentor_id,
                learner_id=self.learner_id,
                skill_id=self.skill_id,
                meeting_link="https://meet.jit.si/skillxchange_test_1",
                meeting_type="Google Meet",
                session_date=datetime.utcnow() + timedelta(days=2),
                status="Scheduled"
            )
            sess10 = Session(
                id=10,
                mentor_id=self.mentor_id,
                learner_id=self.learner_id,
                skill_id=self.skill_id,
                meeting_link="https://meet.jit.si/skillxchange_test_10",
                meeting_type="Google Meet",
                session_date=datetime.utcnow() + timedelta(days=3),
                status="Scheduled"
            )
            db.session.add_all([sess12, sess123, sess1, sess10])
            db.session.commit()

            # Pre-populate dispatch notifications for all 4 sessions
            notifs = [
                Notification(user_id=self.learner_id, type="Session_Reminder", message="Reminder dispatched for Session #12"),
                Notification(user_id=self.learner_id, type="SMS_Reminder", message="SMS reminder dispatched for Session #12"),
                Notification(user_id=self.learner_id, type="Session_Reminder", message="Reminder dispatched for Session #123"),
                Notification(user_id=self.learner_id, type="SMS_Reminder", message="SMS reminder dispatched for Session #123"),
                Notification(user_id=self.learner_id, type="Session_Reminder", message="Reminder dispatched for Session #1"),
                Notification(user_id=self.learner_id, type="SMS_Reminder", message="SMS reminder dispatched for Session #1"),
                Notification(user_id=self.learner_id, type="Session_Reminder", message="Reminder dispatched for Session #10"),
                Notification(user_id=self.learner_id, type="SMS_Reminder", message="SMS reminder dispatched for Session #10"),
            ]
            db.session.add_all(notifs)
            db.session.commit()

            # Reschedule session 12
            reschedule_session_reminders(sess12, datetime.utcnow() + timedelta(days=5))

            # Reschedule session 1
            reschedule_session_reminders(sess1, datetime.utcnow() + timedelta(days=5))

            all_notifs = Notification.query.filter_by(user_id=self.learner_id).all()
            messages = [n.message for n in all_notifs]

            # Verify session 12 notifications are superseded
            n12 = [m for m in messages if "Session #12 " in m or m.endswith("Session #12")]
            self.assertEqual(len(n12), 2)
            for m in n12:
                self.assertIn("superseded", m)

            # Verify session 1 notifications are superseded
            n1 = [m for m in messages if "Session #1 " in m or m.endswith("Session #1")]
            self.assertEqual(len(n1), 2)
            for m in n1:
                self.assertIn("superseded", m)

            # Verify session 123 notifications are COMPLETELY UNTOUCHED
            n123 = [m for m in messages if "Session #123" in m]
            self.assertEqual(len(n123), 2)
            self.assertIn("Reminder dispatched for Session #123", n123)
            self.assertIn("SMS reminder dispatched for Session #123", n123)
            for m in n123:
                self.assertNotIn("superseded", m)

            # Verify session 10 notifications are COMPLETELY UNTOUCHED
            n10 = [m for m in messages if "Session #10" in m]
            self.assertEqual(len(n10), 2)
            self.assertIn("Reminder dispatched for Session #10", n10)
            self.assertIn("SMS reminder dispatched for Session #10", n10)
            for m in n10:
                self.assertNotIn("superseded", m)

    # -------------------------------------------------------------------------
    # 11. Rollback on notification-query failure during reschedule
    # -------------------------------------------------------------------------
    def test_11_rollback_on_notification_query_failure(self):
        with self.app.app_context():
            initial_time = datetime.utcnow() + timedelta(days=2)
            sess = Session(
                mentor_id=self.mentor_id,
                learner_id=self.learner_id,
                skill_id=self.skill_id,
                meeting_link="https://meet.jit.si/skillxchange_test_11",
                meeting_type="Google Meet",
                session_date=initial_time,
                status="Scheduled"
            )
            db.session.add(sess)
            db.session.commit()
            sess_id = sess.id

            schedule_reminder(sess_id, initial_time)
            schedule_sms_reminder(sess_id, initial_time)
            initial_email_run = scheduler.get_job(f'session_reminder_{sess_id}').trigger.run_date

            from unittest.mock import patch, PropertyMock
            future_time = datetime.utcnow() + timedelta(days=7)

            # Simulate Notification query failure (e.g. database query error)
            with patch.object(Notification, 'query', new_callable=PropertyMock) as mock_query_prop:
                mock_query_prop.return_value.filter.side_effect = Exception("Notification query DB error")
                with self.assertRaises(Exception):
                    reschedule_session_reminders(sess, future_time)

            # Verify that session_date was rolled back to initial_time and scheduler jobs untouched
            refreshed_sess = Session.query.get(sess_id)
            self.assertEqual(refreshed_sess.session_date, initial_time)
            self.assertEqual(scheduler.get_job(f'session_reminder_{sess_id}').trigger.run_date, initial_email_run)

            # Also verify route level: client call handles error, rolls back scoped session, and flashes error
            client = self.app.test_client()
            with client.session_transaction() as flask_sess:
                flask_sess['_user_id'] = str(self.learner_id)
                flask_sess['_fresh'] = True

            with patch('app.routes.mentorship.reschedule_session_reminders', side_effect=Exception("Failed reschedule")):
                res_post = client.post(f'/reschedule_session/{sess_id}', data={
                    'session_date': (datetime.utcnow() + timedelta(days=8)).strftime('%Y-%m-%dT15:00')
                }, follow_redirects=True)
                self.assertEqual(res_post.status_code, 200)
                self.assertIn("An error occurred while rescheduling the session.", res_post.get_data(as_text=True))

            # Database and scheduler remain unchanged
            refreshed_sess2 = Session.query.get(sess_id)
            self.assertEqual(refreshed_sess2.session_date, initial_time)
            self.assertEqual(scheduler.get_job(f'session_reminder_{sess_id}').trigger.run_date, initial_email_run)

    # -------------------------------------------------------------------------
    # 12. Recovery restores missing jobs after post-commit scheduler failure
    # -------------------------------------------------------------------------
    def test_12_recovery_restores_jobs_after_scheduler_registration_failure(self):
        with self.app.app_context():
            old_time = datetime.utcnow() + timedelta(days=1)
            sess = Session(
                mentor_id=self.mentor_id,
                learner_id=self.learner_id,
                skill_id=self.skill_id,
                meeting_link="https://meet.jit.si/skillxchange_test_12",
                meeting_type="Google Meet",
                session_date=old_time,
                status="Scheduled"
            )
            db.session.add(sess)
            db.session.commit()
            sess_id = sess.id

            # Pre-record dispatch notifications for the old schedule
            old_email_notif = Notification(
                user_id=self.learner_id,
                type="Session_Reminder",
                message=f"Reminder dispatched for Session #{sess_id}"
            )
            old_sms_notif = Notification(
                user_id=self.learner_id,
                type="SMS_Reminder",
                message=f"SMS reminder dispatched for Session #{sess_id}"
            )
            db.session.add_all([old_email_notif, old_sms_notif])
            db.session.commit()

            # Reschedule session to 4 days in future, but simulate scheduler registration failure
            from unittest.mock import patch
            new_time = datetime.utcnow() + timedelta(days=4)
            with patch('app.utils.notifications.schedule_reminder', side_effect=RuntimeError("Scheduler registration failed")):
                with patch('app.utils.sms_service.schedule_sms_reminder', side_effect=RuntimeError("SMS scheduler registration failed")):
                    reschedule_session_reminders(sess, new_time)

            # 1. Verify DB committed: session_date is updated
            refreshed = Session.query.get(sess_id)
            self.assertEqual(refreshed.session_date, new_time)

            # 2. Verify notifications are superseded
            notifs = Notification.query.filter_by(user_id=self.learner_id).all()
            for n in notifs:
                self.assertIn("superseded", n.message)

            # 3. Verify jobs were NOT registered in scheduler due to the simulated failure
            self.assertIsNone(scheduler.get_job(f'session_reminder_{sess_id}'))
            self.assertIsNone(scheduler.get_job(f'sms_reminder_{sess_id}'))

            # 4. Run startup recovery: should successfully restore both jobs despite superseded history
            recovered = recover_scheduled_reminders(self.app)
            self.assertEqual(recovered, 1)

            # 5. Verify jobs are now present and properly timed
            email_job = scheduler.get_job(f'session_reminder_{sess_id}')
            sms_job = scheduler.get_job(f'sms_reminder_{sess_id}')
            self.assertIsNotNone(email_job)
            self.assertIsNotNone(sms_job)
            self.assertEqual(email_job.trigger.run_date.replace(tzinfo=None), new_time - timedelta(minutes=30))
            self.assertEqual(sms_job.trigger.run_date.replace(tzinfo=None), new_time - timedelta(hours=1))


if __name__ == '__main__':
    unittest.main()
