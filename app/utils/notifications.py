from flask import current_app, render_template
from flask_mail import Message
from app import mail, scheduler, db
from app.models import Session, User, Skill, Notification
from datetime import datetime, timedelta
from apscheduler.jobstores.base import JobLookupError
import os

def send_email(to_email, subject, body_html, body_text=None):
    """Reusable function to send email."""
    msg = Message(subject, recipients=[to_email])
    msg.html = body_html
    if body_text:
        msg.body = body_text
    
    try:
        mail.send(msg)
        print(f"Email sent to {to_email}")
    except Exception as e:
        print(f"Error sending email: {e}")

def send_session_confirmation_email(session_id):
    with scheduler.app.app_context():
        session = Session.query.get(session_id)
        if not session:
            return

        mentor = User.query.get(session.mentor_id)
        learner = User.query.get(session.learner_id)
        skill = Skill.query.get(session.skill_id)

        # Ensure we have a link
        meeting_link = session.meeting_link or mentor.zoom_link or mentor.meet_link or "No Link Provided"
        
        # Prepare HTML content
        html_content = render_template('email/session_email.html',
                                       skill_name=skill.skill_name,
                                       mentor_name=mentor.name,
                                       learner_name=learner.name,
                                       scheduled_time=session.session_date.strftime('%Y-%m-%d %H:%M:%S UTC'),
                                       meeting_link=meeting_link,
                                       meeting_type=session.meeting_type)

        # Send to Learner
        send_email(learner.email, f"Scheduled Class: {skill.skill_name}", html_content)
        
        # Send to Mentor
        send_email(mentor.email, f"New Scheduled Class: {skill.skill_name}", html_content)

def send_session_reminder(session_id):
    with scheduler.app.app_context():
        session = Session.query.get(session_id)
        if not session or session.status != 'Scheduled':
            return

        mentor = User.query.get(session.mentor_id)
        learner = User.query.get(session.learner_id)
        skill = Skill.query.get(session.skill_id)

        # Idempotency guard: prevent duplicate reminder dispatch across workers or restarts
        existing_reminder = Notification.query.filter_by(
            user_id=learner.id,
            type='Session_Reminder',
            message=f"Reminder dispatched for Session #{session.id}"
        ).first()
        if existing_reminder:
            print(f"Session reminder for session {session_id} already dispatched. Skipping duplicate.")
            return

        # Record dispatch
        db.session.add(Notification(
            user_id=learner.id,
            type='Session_Reminder',
            message=f"Reminder dispatched for Session #{session.id}"
        ))
        db.session.commit()

        # Prepare HTML body for reminder
        html_content = f"<h3>Reminder: Your SkillXchange session is starting soon!</h3>" \
                       f"<p>The session for '{skill.skill_name}' starts in 30 minutes.</p>" \
                       f"<p><strong>Join here:</strong> <a href='{session.meeting_link}'>{session.meeting_link}</a></p>"

        # Send to both
        send_email(learner.email, f"Reminder: Upcoming Class for {skill.skill_name}", html_content)
        send_email(mentor.email, f"Reminder: Upcoming Class for {skill.skill_name}", html_content)

def schedule_reminder(session_id, session_date):
    # Schedule reminder 30 minutes before the session as requested
    reminder_time = session_date - timedelta(minutes=30)
    
    if reminder_time < datetime.utcnow():
        reminder_time = datetime.utcnow() + timedelta(seconds=10)

    job_id = f'session_reminder_{session_id}'
    try:
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)
    except JobLookupError:
        pass
    except Exception as e:
        try:
            from flask import current_app
            current_app.logger.error(f"Unexpected error removing existing scheduler job {job_id}: {e}")
        except Exception:
            print(f"Unexpected error removing existing scheduler job {job_id}: {e}")

    scheduler.add_job(
        id=job_id,
        func=send_session_reminder,
        args=[session_id],
        trigger='date',
        run_date=reminder_time,
        replace_existing=True
    )
    print(f"Reminder scheduled for session {session_id} at {reminder_time}")


def reschedule_session_reminders(session, new_date=None):
    """
    Safely updates email and SMS reminder jobs for a rescheduled session.
    Marks prior reminder dispatch records as superseded so they do not suppress
    reminders for the new schedule, commits changes to the database, and re-registers
    the scheduler jobs with the new date.
    """
    try:
        if new_date:
            session.session_date = new_date

        # Exact matching for the two known dispatch messages for this specific session
        expected_messages = [
            f"Reminder dispatched for Session #{session.id}",
            f"SMS reminder dispatched for Session #{session.id}"
        ]
        prior_notifs = Notification.query.filter(
            Notification.user_id.in_([session.learner_id, session.mentor_id]),
            Notification.type.in_(['Session_Reminder', 'SMS_Reminder']),
            Notification.message.in_(expected_messages)
        ).all()
        for n in prior_notifs:
            n.message = f"{n.message} (superseded by reschedule to {session.session_date.strftime('%Y-%m-%d %H:%M')})"

        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    # Only after the database commit succeeds, update reminder jobs.
    # Isolate email and SMS updates and log failures to avoid split-brain inconsistency.
    schedule_errors = []
    try:
        schedule_reminder(session.id, session.session_date)
    except Exception as e:
        schedule_errors.append(f"email: {e}")

    try:
        from app.utils.sms_service import schedule_sms_reminder
        schedule_sms_reminder(session.id, session.session_date)
    except Exception as e:
        schedule_errors.append(f"sms: {e}")

    if schedule_errors:
        err_msg = "; ".join(schedule_errors)
        try:
            from flask import current_app
            current_app.logger.error(
                f"Failed to schedule reminder jobs for session {session.id} after reschedule: {err_msg}"
            )
        except Exception:
            print(f"Failed to schedule reminder jobs for session {session.id} after reschedule: {err_msg}")


def recover_scheduled_reminders(app=None):
    """
    Recovers eligible pending session reminders from the database after an application restart or wake-up.
    Only schedules reminders for sessions that:
      1. Have status == 'Scheduled'
      2. Have session_date in the future (session_date > now)
      3. Have not already had reminders dispatched (verified via Notification records)
      4. Are not already active in the scheduler
    """
    active_app = app or getattr(scheduler, 'app', None)
    if not active_app:
        try:
            from flask import current_app
            active_app = current_app._get_current_object()
        except Exception:
            return 0

    with active_app.app_context():
        now = datetime.utcnow()
        try:
            upcoming_sessions = Session.query.filter(
                Session.status == 'Scheduled',
                Session.session_date > now
            ).all()
        except Exception as e:
            # Table might not exist yet (e.g. prior to initial schema execution) or DB unavailable
            print(f"Skipping reminder recovery (database not ready or table missing): {e}")
            return 0

        recovered_count = 0
        for sess in upcoming_sessions:
            try:
                session_recovered = False
                # 1. Email reminder recovery
                email_job_id = f'session_reminder_{sess.id}'
                if scheduler.get_job(email_job_id) is None:
                    already_sent_email = Notification.query.filter_by(
                        user_id=sess.learner_id,
                        type='Session_Reminder',
                        message=f"Reminder dispatched for Session #{sess.id}"
                    ).first()
                    if not already_sent_email:
                        schedule_reminder(sess.id, sess.session_date)
                        session_recovered = True

                # 2. SMS reminder recovery
                sms_job_id = f'sms_reminder_{sess.id}'
                if scheduler.get_job(sms_job_id) is None:
                    already_sent_sms = Notification.query.filter_by(
                        user_id=sess.learner_id,
                        type='SMS_Reminder',
                        message=f"SMS reminder dispatched for Session #{sess.id}"
                    ).first()
                    if not already_sent_sms:
                        from app.utils.sms_service import schedule_sms_reminder
                        schedule_sms_reminder(sess.id, sess.session_date)
                        session_recovered = True

                if session_recovered:
                    recovered_count += 1
            except Exception as sess_err:
                print(f"Error recovering reminders for session {sess.id}: {sess_err}")

        print(f"Startup reminder recovery complete: {recovered_count} session reminders scheduled.")
        return recovered_count
