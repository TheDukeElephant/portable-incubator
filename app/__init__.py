from flask import Flask
from flask_sock import Sock

# Initialize extensions but don't create the app instance here
sock = Sock()

def create_app():
    app = Flask(__name__, template_folder='../templates', static_folder='../static')
    sock.init_app(app)

    # Import and register Blueprints within the app context
    with app.app_context():
        from . import views
        app.register_blueprint(views.main_bp)

        # Import other parts or register other blueprints if needed

    return app
