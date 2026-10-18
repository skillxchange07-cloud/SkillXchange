from flask import current_app, render_template
from flask_mail import Message
from app import mail, scheduler, db
from app.models import Session, User, Skill, Notification
from datetime import datetime, timedelta
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

    scheduler.add_job(
        id=f'session_reminder_{session_id}',
        func=send_session_reminder,
        args=[session_id],
        trigger='date',
        run_date=reminder_time,
        replace_existing=True
    )
    print(f"Reminder scheduled for session {session_id} at {reminder_time}")


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
                    recovered_count += 1

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

        print(f"Startup reminder recovery complete: {recovered_count} session reminders scheduled.")
        return recovered_count
