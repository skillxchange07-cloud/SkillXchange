from app import create_app, db, socketio
import app.socket_events  # Import to register handlers

app = create_app()

if __name__ == '__main__':
    with app.app_context():
        # Create database tables if they do not exist
        db.create_all()
    # Run the application with socketio
    socketio.run(app, debug=True, port=5000)
