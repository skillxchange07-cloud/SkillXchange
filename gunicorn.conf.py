import os

# Gunicorn configuration for SkillXchange (Flask + Flask-SocketIO + Flask-APScheduler)
bind = f"0.0.0.0:{os.environ.get('PORT', '5000')}"

# Single eventlet worker allows asynchronous WebSocket concurrency
# without requiring an external Redis message queue or causing duplicate scheduler runs
worker_class = "eventlet"
workers = 1
threads = 1

# Timeout and keepalive
timeout = 120
keepalive = 5

# Logging to standard output/error for cloud container log aggregators
accesslog = "-"
errorlog = "-"
loglevel = os.environ.get("LOG_LEVEL", "info")

# Process name
proc_name = "skillxchange"
