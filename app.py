# Standard library
import enum
import hashlib
import json
import os
import random
import re
import secrets
import string
from datetime import datetime, timedelta, timezone
from hashlib import md5

# Third-party packages
import jwt
from dotenv import load_dotenv
from flask import Flask, flash, redirect, render_template, request, url_for
from flask_admin import Admin, AdminIndexView
from flask_admin.contrib.sqla import ModelView
from flask_admin.menu import MenuLink
from flask_cors import CORS
from flask_login import (
    LoginManager,
    UserMixin,
    current_user,
    login_required,
    login_user,
    logout_user,
)
from flask_mail import Mail, Message
from flask_migrate import Migrate
from flask_socketio import SocketIO, emit, join_room
from flask_sqlalchemy import SQLAlchemy
from wtforms import SelectField, TextAreaField

# Load environment variables
load_dotenv()

app = Flask(__name__)

CORS(app)

app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY")
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('SQLALCHEMY_DATABASE_URI')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
login = LoginManager(app)
login.login_view = 'signin'
migrate = Migrate(app,db)

# ======= Email Setup ==========


app.config["MAIL_SERVER"] = "smtp.gmail.com"
app.config["MAIL_PORT"] = 587
app.config["MAIL_USE_TLS"] = True
app.config["MAIL_USE_SSL"] = False

app.config["MAIL_USERNAME"] = os.getenv("MAIL_USER")
app.config["MAIL_PASSWORD"] = os.getenv("MAIL_PASS")

app.config["MAIL_DEFAULT_SENDER"] = os.getenv("MAIL_USER")

mail = Mail(app)

socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")

def verify_log(token, game_log):
    calculated_score = 0
    print(game_log)

    previous_timestamp = None

    for entry in game_log:
        # Recompute expected hash
        expected_hash = hashlib.sha256(
            f"{entry['actionType']}:{entry['word']}:{entry['timestamp']}:{token}".encode()
        ).hexdigest()

        if expected_hash != entry['hash']:
            raise ValueError("Tampered log detected!")

        # Check timestamp order and minimum reaction time
        ts = entry['timestamp']
        if previous_timestamp is not None:
            delta = ts - previous_timestamp
            if delta < MIN_REACTION_MS:
                flash(f"Impossible reaction time detected! Δ={delta}ms")
                raise ValueError(f"Impossible timing detected! Δ={delta}ms")
            if delta < 0:
                flash("Timestamps out of order detected!")
                raise ValueError("Timestamps out of order!")

        previous_timestamp = ts

        # Count scores
        if entry['actionType'] == "score":
            calculated_score += 1

    return calculated_score

active_games = {}  # runtime-only game state

def generate_random_token(length=32):
    return secrets.token_urlsafe(length)

def generate_room_pin():
    return ''.join(random.choices(string.digits, k=6))

MIN_REACTION_MS = 120

import random
import time

def game_loop(pin):
    game = active_games[pin]

    while game["wave"] <= game["max_waves"]:
        # prepare wave queue
        queue = game["vocab"].copy()
        random.shuffle(queue)

        # fill columns initially
        for col in game["active_words"]:
            if queue:
                word = queue.pop(0)
                game["active_words"][col] = word
                socketio.emit("spawn_word", {
                    "column": col,
                    "word": word
                }, room=pin)

        # keep wave running
        while queue or any(game["active_words"].values()):
            socketio.sleep(0.05)

            for col, word in game["active_words"].items():
                if word is None and queue:
                    next_word = queue.pop(0)
                    game["active_words"][col] = next_word

                    socketio.emit("spawn_word", {
                        "column": col,
                        "word": next_word
                    }, room=pin)

        socketio.emit("wave_update", {
            "wave": game["wave"]
        }, room=pin)

        game["wave"] += 1

    end_game(pin)



def end_game(pin):
    game = active_games[pin]
    game["ended"] = True

    leaderboard = sorted(
        [
            {"name": game["players"][uid], "score": score}
            for uid, score in game["scores"].items()
        ],
        key=lambda x: x["score"],
        reverse=True
    )

    socketio.emit("game_over", {
        "leaderboard": leaderboard
    }, room=pin)



@login.user_loader
def load_user(id):
    return db.session.get(User, int(id))



# ================ db ==========================
from flask_login import UserMixin
from werkzeug.security import check_password_hash,generate_password_hash
from hashlib import md5
import json


multiplayer_game_players = db.Table(
    'multiplayer_game_players',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('game_id', db.Integer, db.ForeignKey('multiplayer_game.id'), primary_key=True)
)


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), nullable=False)
    chinese_name = db.Column(db.String(64), nullable=True)
    email = db.Column(db.String(128), nullable=False)
    verified = db.Column(db.Boolean())
    admin = db.Column(db.Boolean())
    games = db.relationship("Game", back_populates="player", lazy=True)
    multiplayer_games_owned = db.relationship("MultiplayerGame", back_populates="owner", lazy=True)
    multiplayer_games_joined = db.relationship(
        "MultiplayerGame",
        secondary=multiplayer_game_players,
        back_populates="players",
        lazy=True
    )

    def avatar(self, size=128):
        digest = md5(self.email.lower().encode('utf-8')).hexdigest()
        return f'https://www.gravatar.com/avatar/{digest}?d=identicon&s={size}'
    
    def __repr__(self):
        return self.name

class Game(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    vocab_list = db.Column(db.String(128), nullable=False)
    player_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    score = db.Column(db.Integer(), nullable=True)
    deaths = db.Column(db.Integer(), nullable=True)
    date_time_start = db.Column(db.String(), nullable=True)
    date_time_end = db.Column(db.String(), nullable=True)
    token = db.Column(db.String())
    player = db.relationship("User", back_populates="games")

    @property
    def player_name(self):
        return self.player.name if self.player else None
    
    def __repr__(self):
        return f"<Game {self.vocab_list} by {self.player.name}>"
    

class VocabListDifficulty(enum.Enum):
    cme1 = "Level 1"
    cme2 = "Level 2"
    cme3 = "Level 3"
    cme4 = "Level 4"
    cme5 = "Level 5"

class VocabList(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    _words = db.Column("words", db.Text, nullable=False)
    level = db.Column(
        db.Enum(VocabListDifficulty, name="level"),
        nullable=True
    )

    @property
    def words(self):
        if not self._words:
            return []

        try:
            return json.loads(self._words)
        except json.JSONDecodeError:
            return self._words.replace("，", ",").split(",")


    @words.setter
    def words(self, value):
        self._words = json.dumps(value, ensure_ascii=False)

    def __str__(self):
        return self.name
    

class MultiplayerGame(db.Model):
    __tablename__ = "multiplayer_game"

    id = db.Column(db.Integer, primary_key=True)

    # Owner
    owner_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    owner = db.relationship("User", back_populates="multiplayer_games_owned")

    # Players
    players = db.relationship("User",secondary=multiplayer_game_players,back_populates="multiplayer_games_joined", lazy="subquery")

    # Game info
    game_code = db.Column(db.Integer)
    vocab_list_id = db.Column(db.Integer, db.ForeignKey("vocab_list.id"), nullable=False)
    game_board_state = db.Column(db.JSON)
    scoreboard = db.Column(db.JSON)
    settings = db.Column(db.JSON)

    def __str__(self):
        return f"MultiplayerGame {self.id}"



# ====================== Admin ======================

DIVISION_CHAR = "， " 

class VocabListAdmin(ModelView):
    column_list = ('id', 'name', 'words', 'level')
    form_columns = ('name', 'words_input', 'level')

    form_extra_fields = {
        'words_input': TextAreaField('Chinese Words (comma separated)'),
        'level': SelectField(
            'Level',
            choices=[
                ('cme1', 'CME 1'),
                ('cme2', 'CME 2'),
                ('cme3', 'CME 3'),
                ('cme4', 'CME 4'),
                ('cme5', 'CME 5'),
            ]
        )
    }

    def on_form_prefill(self, form, id):
        vocab_list = self.session.get(self.model, id)
        if vocab_list:
            form.words_input.data = DIVISION_CHAR.join(vocab_list.words)

    def on_model_change(self, form, model, is_created):
        word_list = [
            w.strip()
            for w in re.split(r', |,|， |，', form.words_input.data or "")
            if w.strip()
        ]
        model._words = json.dumps(word_list)

    def is_accessible(self):
        return current_user.is_authenticated and current_user.admin

    def inaccessible_callback(self, name, **kwargs):
        flash("No permission")
        return redirect("/")


class UserListAdmin(ModelView):
    column_list = ('id','name','chinese_name','email','admin')
    form_columns = ('name','chinese_name','email','admin')


    def is_accessible(self):
        return current_user.is_authenticated and current_user.admin

    def inaccessible_callback(self, name, **kwargs):
        flash("No permission")
        return redirect("/")
    
class GameListAdmin(ModelView):
    column_list = ('id','vocab_list','score','deaths','date_time_start','date_time_end','player_name')
    can_create = False
    column_default_sort = ('date_time_end', True)
    column_formatters = {'player_name': lambda v,c,m,p: m.player.name if m.player else "—"}

    def is_accessible(self):
        return current_user.is_authenticated and current_user.admin

    def inaccessible_callback(self, name, **kwargs):
        flash("No permission")
        return redirect("/")
    
class MyAdminIndexView(AdminIndexView):
    def is_accessible(self):
        return current_user.is_authenticated and current_user.admin

    def inaccessible_callback(self, name, **kwargs):
        flash("No permission")
        return redirect("/")

admin = Admin(app, name="Typing Cat Dashboard", index_view=MyAdminIndexView())
admin.add_view(VocabListAdmin(VocabList, db.session))
admin.add_view(UserListAdmin(User, db.session))
admin.add_view(GameListAdmin(Game, db.session))
admin.add_link(MenuLink(name='🏠 Back to Main Site', url='/'))

# ====================== Routes ======================
@app.route("/")
def index():
    selected_level = request.args.get("level")
    query = VocabList.query
    if selected_level:
        query = query.filter(VocabList.level == VocabListDifficulty(selected_level))

    lists = query.all()

    return render_template(
        "index.html",
        lists=lists,
        levels=VocabListDifficulty,
        selected_level=selected_level
    )

@app.route("/game/<int:list_id>")
@login_required
def game(list_id):
    if current_user.verified:
        vocab_list = VocabList.query.get_or_404(list_id)
        words = vocab_list.words
        token = generate_random_token()
        game = Game(vocab_list=vocab_list.name, player_id=current_user.id, token=token, date_time_start=datetime.now())
        db.session.add(game)
        db.session.commit()
        return render_template("game.html", words=words, list_name=vocab_list.name, token=token)
    flash("Please click the link in your email verify your email and then try again.")
    return redirect("/")


@app.route("/game/submit", methods=["POST"])
@login_required
def submit_game():
    data = request.get_json()
    gametoken = data["token"]
    game = Game.query.filter_by(player_id=current_user.id).order_by(Game.date_time_start.desc()).first()
    if game.token == gametoken:
        game.score = verify_log(gametoken, data["gamelog"])
        game.deaths = data["deaths"]
        game.date_time_end = datetime.now()
        db.session.commit()
        return {"status":"ok"}
    return {"status":"error"}


# ====================== Auth ======================
def send_magic_link(action, email):
    token = jwt.encode({"action": action, "email": email, "iat": datetime.now(timezone.utc), "exp": datetime.now(timezone.utc) + timedelta(minutes=15)}, app.config["SECRET_KEY"], algorithm="HS256")
    print(f"sending auth token to user: {email}\ntoken: {token}")

    link = url_for(
        "receive_magic_link",
        token=token,
        _external=True
    )

    msg = Message(subject="Typing Cat Login", recipients=[email])

    msg.body = f"Hello User, please click this link to log into your Typing Cat account:\n{link}"
    msg.html = f"""
    <h1>Log in to your Typing Cat account</h1>
    <p>Hello User, to log into your Typing Cat account, please click this link:</p>
    <a href="{link}">
        {link}
    </a>
    """

    mail.send(msg)

def verify_magic_link(token):
    payload = jwt.decode(token, app.config["SECRET_KEY"], algorithms=["HS256"])

    user = User.query.filter_by(email=payload['email']).first_or_404()

    if payload['action'] == "login":
        login_user(user, True)
        return True
    if payload['action'] == "verify":
        user.verified = True
        db.session.commit()
        login_user(user, True)
        return True
    return False


@app.route('/login', methods=["GET","POST"])
def signin():
    if current_user.is_authenticated:
        return redirect('/')
    if request.method == "POST":
        email = request.form.get('email')
        send_magic_link(action="login", email=email)
        flash("Please click the link that was sent to your email to login.")
    return render_template('login.html')

@app.route('/register', methods=["GET","POST"])
def register():
    if current_user.is_authenticated:
        return redirect('/')
    if request.method == "POST":
        name = request.form.get('name')
        chinese_name = request.form.get('chinese_name')
        email = request.form.get('email')
        user = User(name=name,chinese_name=chinese_name,email=email,admin=False,verified=False)
        db.session.add(user)
        db.session.commit()
        send_magic_link(action="verify",email=email)
        flash("Please click the link that was sent to your email to verify your account.")
        return redirect('/')
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect('/login')

@app.route('/magic_link')
def receive_magic_link():
    data = request.args
    token = data['token']
    if verify_magic_link(token):
        return redirect('/')
    else:
        return 404



@app.route('/profile/<email>')
def profile(email):
    if current_user.verified:
        user = User.query.filter_by(email=email).first_or_404()
        games = []
        if current_user.admin or user.email == email:
            games = Game.query.filter_by(player_id=user.id).order_by(Game.date_time_start.desc()).all()
        return render_template('profile.html', user=user, games=games)
    flash("Please click the link in your email verify your email and then try again.")
    return redirect("/")

# =========================== Multiplayer Socket Definitions =============================

@socketio.on("join_room")
def join_room_handler(data):
    pin = data["pin"]

    if pin not in active_games:
        emit("error", {"msg": "Invalid game PIN"})
        return

    join_room(pin)
    game = active_games[pin]

    game["scores"].setdefault(current_user.id, 0)
    game["players"][current_user.id] = current_user.name

    emit("player_joined", {
        "name": current_user.name
    }, room=pin)


@socketio.on("start_game")
def start_game(data):
    pin = data["pin"]
    max_waves = int(data.get("max_waves", 5))

    print("START GAME RECEIVED", pin, max_waves)

    game = active_games.get(pin)
    if not game:
        print("NO GAME FOUND")
        return

    if game["started"]:
        print("GAME ALREADY STARTED")
        return

    game["max_waves"] = max_waves
    game["started"] = True

    print("STARTING GAME LOOP")
    socketio.start_background_task(game_loop, pin)


@socketio.on("submit_word")
def submit_word(data):
    pin = data["pin"]
    typed = data["word"]

    game = active_games.get(pin)
    if not game or game["ended"]:
        return

    for col, word in game["active_words"].items():
        if word == typed:
            game["active_words"][col] = None
            game["scores"][current_user.id] += 1

            socketio.emit("word_cleared", {
                "column": col,
                "scores": game["scores"]
            }, room=pin)
            return



# ===================== Multiplayer Route Definitions ===================

@app.route("/multiplayer/create/<int:list_id>")
@login_required
def create_multiplayer_room(list_id):
    if not current_user.admin:
        return "Teachers only", 403

    vocab_list = VocabList.query.get_or_404(list_id)
    pin = generate_room_pin()

    active_games[pin] = {
        "pin": pin,
        "vocab": vocab_list.words,   # ✅ SELECTED HERE
        "wave": 1,
        "max_waves": 5,
        "active_words": {f"col{i}": None for i in range(1, 5)},
        "scores": {},
        "players": {},
        "started": False,
        "ended": False
    }

    return render_template(
        "multiplayer_teacher.html",
        pin=pin,
        vocab_name=vocab_list.name
    )

@app.route("/multiplayer/join", methods=["GET", "POST"])
@login_required
def multiplayer_join():
    if request.method == "POST":
        pin = request.form.get("pin")

        if pin not in active_games:
            flash("Invalid game PIN")
            return redirect("/multiplayer/join")

        return redirect(f"/multiplayer/{pin}/player")

    return render_template("multiplayer_join.html")


@app.route("/multiplayer/<pin>/player")
@login_required
def multiplayer_player(pin):
    if pin not in active_games:
        flash("Game not found")
        return redirect("/")

    return render_template(
        "multiplayer_player.html",
        pin=pin
    )


@app.route('/api/word_list/<list_id>')
def api_get_word_list(list_id):
    vocab_list = VocabList.query.get_or_404(list_id)
    return vocab_list._words



# ========== ERROR HANDLING ===========

@app.errorhandler(jwt.ExpiredSignatureError)
def handle_expired_token(e):
    return {"error": "Token expired"}, 401

@app.errorhandler(jwt.InvalidTokenError)
def handle_invalid_token(e):
    return {"error": "Invalid token"}, 401

# ====================== Run ======================
if __name__ == "__main__":
    #socketio.run(app, debug=True, host='0.0.0.0')
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8080))
    )
