from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_bcrypt import Bcrypt

app = Flask(__name__)

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///corex_real_final_sem_bug.db"
app.config["SECRET_KEY"] = "sua_chave_secreta"
app.config['UPLOAD_FOLDER'] = "static/fotos_posts"
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # limite de 5MB para uploads

database = SQLAlchemy(app)
bcrypt = Bcrypt(app)

login_manager = LoginManager(app)
login_manager.login_view = "site_login"

# 🔥 IMPORTANTE: deixar por último
from gerenciador import models
from gerenciador import routes