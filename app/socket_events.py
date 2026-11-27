from flask import request
from flask_socketio import emit, join_room, leave_room
from app import socketio, db
from app.models import User, Message, Notification
from flask_login import current_user

# Dictionary to keep track of online users: {user_id: [sid1, sid2, ...]}
online_users = {}

@socketio.on('connect')
def handle_connect():
    if current_user.is_authenticated:
        user_id = current_user.id
        sid = request.sid
        if user_id not in online_users:
            online_users[user_id] = []
        online_users[user_id].append(sid)
        join_room(f"user_{user_id}")
        emit('user_status', {'user_id': user_id, 'status': 'online'}, broadcast=True)
        print(f"User {user_id} connected with sid {sid}")

@socketio.on('disconnect')
def handle_disconnect():
    if current_user.is_authenticated:
        user_id = current_user.id
        sid = request.sid
        if user_id in online_users:
            if sid in online_users[user_id]:
                online_users[user_id].remove(sid)
            if not online_users[user_id]:
                del online_users[user_id]
                emit('user_status', {'user_id': user_id, 'status': 'offline'}, broadcast=True)
        print(f"User {user_id} disconnected")

@socketio.on('send_message')
def handle_send_message(data):
    recipient_id = data.get('recipient_id')
    content = data.get('content')
    
    if not recipient_id or not content:
        return
    
    # Save to database
    msg = Message(sender_id=current_user.id, recipient_id=recipient_id, content=content)
    db.session.add(msg)
    db.session.commit()
    
    # Emit to recipient room
    emit('receive_message', {
        'id': msg.id,
        'sender_id': current_user.id,
        'sender_name': current_user.name,
        'content': content,
        'timestamp': msg.timestamp.strftime('%Y-%m-%d %H:%M:%S')
    }, room=f"user_{recipient_id}")
    
    # Emit back to sender for confirmation
    emit('message_sent', {'status': 'success', 'msg_id': msg.id})

def send_realtime_notification(user_id, n_type, message):
    """Utility function to send real-time notification via socket"""
    # Save to database
    notif = Notification(user_id=user_id, type=n_type, message=message)
    db.session.add(notif)
    db.session.commit()
    
    # Emit to user room
    socketio.emit('new_notification', {
        'id': notif.id,
        'type': n_type,
        'message': message,
        'created_at': notif.created_at.strftime('%Y-%m-%d %H:%M:%S')
    }, room=f"user_{user_id}")
