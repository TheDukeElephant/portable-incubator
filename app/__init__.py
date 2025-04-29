from flask import Flask
from flask_sock import Sock

# Initialize extensions but don't create the app instance here
sock = Sock()

def create_app():
    app = Flask(__name__, template_folder='../templates', static_folder='../static')
    sock.init_app(app)

    with app.app_context():
        # Import parts of our application
        from . import views  # noqa

        # Register Blueprints or routes here if needed in the future

    return app
