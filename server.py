from flask import Flask, request, redirect
import sqlite3
import hashlib
import secrets
import os
from datetime import datetime

app = Flask(__name__)

DB = "minicalendar.db"

# ---------- DB ----------
def get_db():
    return sqlite3.connect(DB, timeout=10, check_same_thread=False)

def init_db():
    with get_db() as db:
        c = db.cursor()

        c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE,
            password TEXT,
            approved INTEGER DEFAULT 0,
            activation_key TEXT
        )
        """)

        c.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            event_date TEXT,
            description TEXT
        )
        """)

# ---------- UTIL ----------
def sanitize(text):
    return text.replace("<", "").replace(">", "")

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def generate_key():
    return secrets.token_hex(16)

# ---------- USERS ----------
def create_user(url, password):
    key = generate_key()

    with get_db() as db:
        c = db.cursor()
        c.execute(
            "INSERT INTO users (url, password, activation_key) VALUES (?, ?, ?)",
            (url, hash_password(password), key)
        )
        user_id = c.lastrowid

    link = f"http://127.0.0.1:5000/activate/{user_id}/{key}"

    with open("approve.txt", "a") as f:
        f.write(f"{url}|||{link}\n")

def check_user(url, password):
    with get_db() as db:
        c = db.cursor()
        c.execute("SELECT id, password, approved FROM users WHERE url=?", (url,))
        row = c.fetchone()

    if row:
        if row[1] != hash_password(password):
            return "wrong_pass", None
        if row[2] == 0:
            return "not_approved", None
        return "ok", row[0]

    return "not_exist", None

# ---------- EVENTS ----------
def clean_old_events(user_id):
    today = datetime.now().strftime("%Y-%m-%d")

    with get_db() as db:
        c = db.cursor()
        c.execute(
            "DELETE FROM events WHERE user_id=? AND event_date < ?",
            (user_id, today)
        )

def add_event(user_id, date, text):
    with get_db() as db:
        c = db.cursor()
        c.execute(
            "INSERT INTO events (user_id, event_date, description) VALUES (?, ?, ?)",
            (user_id, date, text)
        )

def get_events(user_id):
    with get_db() as db:
        c = db.cursor()
        c.execute(
            "SELECT event_date, description FROM events WHERE user_id=? ORDER BY event_date ASC",
            (user_id,)
        )
        return c.fetchall()

# ---------- ROUTES ----------

# HOME (login)
@app.route("/", methods=["GET", "POST"])
def home():
    error = ""

    if request.method == "POST":
        url = sanitize(request.form.get("url"))
        password = request.form.get("password")

        res, uid = check_user(url, password)

        if res == "ok":
            return redirect(f"/user/{uid}")
        else:
            error = "Erro login"

    return f"""
    <body style="background:#0f0f0f;color:white;font-family:sans-serif;">
    <h1>MiniCalendar 📅</h1>

    <form method="POST">
        <input name="url" placeholder="user"><br>
        <input type="password" name="password" placeholder="password"><br>
        <button>Login</button>
    </form>

    <a href="/register">➕ Registar</a>
    <p>{error}</p>
    </body>
    """

# REGISTER
@app.route("/register", methods=["GET", "POST"])
def register():
    msg = ""

    if request.method == "POST":
        url = sanitize(request.form.get("url"))
        password = request.form.get("password")

        if url and password:
            try:
                create_user(url, password)
                msg = "Criado! Aguarda aprovação."
            except:
                msg = "Já existe"

    return f"""
    <body style="background:#0f0f0f;color:white;">
    <h2>Registar</h2>
    <form method="POST">
        <input name="url"><br>
        <input type="password" name="password"><br>
        <button>Registar</button>
    </form>
    <p>{msg}</p>
    </body>
    """

# ACTIVATE
@app.route("/activate/<int:user_id>/<key>")
def activate(user_id, key):
    with get_db() as db:
        c = db.cursor()
        c.execute("SELECT activation_key FROM users WHERE id=?", (user_id,))
        row = c.fetchone()

        if row and row[0] == key:
            c.execute("UPDATE users SET approved=1 WHERE id=?", (user_id,))
            db.commit()
            return "Conta ativada!"

    return "Link inválido"

# USER PAGE (agenda)
@app.route("/user/<int:user_id>", methods=["GET", "POST"])
def user_page(user_id):
    error = ""

    # 🔥 limpar eventos antigos ao entrar
    clean_old_events(user_id)

    if request.method == "POST":
        url = sanitize(request.form.get("url"))
        password = request.form.get("password")
        date = request.form.get("date")
        text = sanitize(request.form.get("text"))

        res, uid = check_user(url, password)

        if res == "ok" and uid == user_id:
            if date and text:
                add_event(user_id, date, text)
                return redirect(f"/user/{user_id}")
        else:
            error = "Erro autenticação"

    events = get_events(user_id)

    html = f"""
    <body style="background:#0f0f0f;color:white;font-family:sans-serif;">
    <h2>Agenda #{user_id}</h2>

    <form method="POST">
        <input name="url" placeholder="user"><br>
        <input type="password" name="password"><br>
        <input type="date" name="date"><br>
        <input name="text" placeholder="evento"><br>
        <button>Adicionar</button>
    </form>

    <p>{error}</p>
    <hr>
    """

    for d, t in events:
        html += f"<p>📅 {d} → {t}</p>"

    html += "</body>"
    return html

# ---------- START ----------
if __name__ == "__main__":
    init_db()
    app.run(debug=True, use_reloader=False)
