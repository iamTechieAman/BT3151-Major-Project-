from app import app, socketio

if __name__ == '__main__':
    # use_reloader=False is critical to prevent double scheduler execution
    socketio.run(app, debug=True, host='0.0.0.0', port=5000, use_reloader=False)
