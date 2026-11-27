# SkillXchange

A peer-to-peer knowledge bartering and mentorship platform built with **Flask**, **Flask-SocketIO**, **SQLAlchemy**, and **Bootstrap 5**. Users can showcase skills with demo videos, set learning goals for mutual skill matching, schedule live video sessions (Jitsi In-App, Google Meet, or Zoom), chat in real time, earn badges, and rate mentors.

## Key Features

- **Authentication & Profiles**: Registration, login, role-based Admin panel, and editable mentor profiles with preferred mode, availability, and meeting links.
- **Skill Marketplace**: Browse approved skills by search query or category, preview uploaded demo videos, bookmark skills, and read/submit student reviews.
- **Mutual Matching & Scheduling**: Send mentorship requests, accept & schedule sessions (with conflict detection), reschedule, cancel, and complete sessions.
- **Real-Time Chat & Notifications**: Socket.IO-powered messaging (`/messages`) and live session notifications.
- **In-App Video Calls**: Integrated Jitsi Meet room (`/video_call/<session_id>`).
- **Admin Moderation**: Approve/reject submitted skills, view platform analytics charts, and manage user roles.

## Demo Accounts (Pre-Seeded on Empty DB)

- **Mentor:** `rahul@example.com` / `password123`
- **Learner:** `priya@example.com` / `password123`
- **Admin:** `admin@skillxchange.com` / `password123`

## Local Setup

```bash
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
python run.py
```

## Production Deployment

Includes a `Dockerfile`, `Procfile`, and `railway.json` configured for `gunicorn --worker-class eventlet -w 1` with `/health` healthcheck support and automatic `DATABASE_URL` / SQLite fallback.
