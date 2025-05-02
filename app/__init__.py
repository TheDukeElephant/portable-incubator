import logging # <-- Import logging
from flask import Flask
from flask_sock import Sock

# Initialize extensions but don't create the app instance here
sock = Sock()

def create_app():
    app = Flask(__name__, template_folder='../templates', static_folder='../static')
    sock.init_app(app)

    # --- Configure Logging ---
    # Set the root logger level to INFO to capture messages from all modules
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    # You might want to adjust the format or add file handlers later
    # -------------------------

    # Import and register Blueprints within the app context
    with app.app_context():
        from . import views
        app.register_blueprint(views.main_bp)

        # Import other parts or register other blueprints if needed

    return app
