from flask import Flask
from flask_sock import Sock

app = Flask(__name__, template_folder='../templates')
sock = Sock(app)

from . import views      # noqa
