import requests
import os
from flask import current_app
from app import scheduler, db
from app.models import Session, User, Skill
from datetime import datetime, timedelta

def send_sms(number, message):
    """
    Sends an SMS using Fast2SMS API.
    """
    url = "https://www.fast2sms.com/dev/bulkV2"
    api_key = os.getenv("FAST2SMS_API_KEY")
    
    if not api_key:
        print("Fast2SMS API Key not found in environment variables.")
        return False

    querystring = {
        "authorization": api_key,
        "message": message,
        "language": "english",
        "route": "q",
        "numbers": number
    }

    headers = {
        'cache-control': "no-cache"
    }

    try:
        response = requests.request("GET", url, headers=headers, params=querystring)
        print(f"SMS Response: {response.text}")
        return response.status_code == 200
    except Exception as e:
        print(f"Error sending SMS: {e}")
        return False

def send_session_confirmation_sms(session_id):
    """
    Sends an SMS confirmation to both mentor and learner.
    """
    with scheduler.app.app_context():
        session = Session.query.get(session_id)
        if not session:
            return

        mentor = User.query.get(session.mentor_id)
        learner = User.query.get(session.learner_id)
        skill = Skill.query.get(session.skill_id)

        # Build message
        message = f"SkillXchange: Match confirmed! Skill: {skill.skill_name}. Session on {session.session_date.strftime('%Y-%m-%d %H:%M')} via {session.meeting_type}. Happy Learning!"

        # Send to both (assuming mentor and learner have phone numbers)
        if mentor.phone:
            send_sms(mentor.phone, message)
        if learner.phone:
            send_sms(learner.phone, message)

def send_sms_reminder_job(session_id):
    """
    Job function to send a reminder SMS before the session.
    """
    with scheduler.app.app_context():
        session = Session.query.get(session_id)
        if not session or session.status != 'Scheduled':
            return

        skill = Skill.query.get(session.skill_id)
        mentor = User.query.get(session.mentor_id)
        learner = User.query.get(session.learner_id)

        msg = f"SkillXchange Reminder: Your session for '{skill.skill_name}' starts in 1 hour. See you there!"

        if mentor.phone:
            send_sms(mentor.phone, msg)
        if learner.phone:
            send_sms(learner.phone, msg)

def schedule_sms_reminder(session_id, session_date):
    """
    Schedules an SMS reminder 1 hour before the session.
    """
    reminder_time = session_date - timedelta(hours=1)
    
    # If the session is within an hour, schedule it for 10 seconds from now
    if reminder_time < datetime.utcnow():
        reminder_time = datetime.utcnow() + timedelta(seconds=10)

    scheduler.add_job(
        id=f'sms_reminder_{session_id}',
        func=send_sms_reminder_job,
        args=[session_id],
        trigger='date',
        run_date=reminder_time,
        replace_existing=True
    )
    print(f"SMS Reminder scheduled for session {session_id} at {reminder_time}")
