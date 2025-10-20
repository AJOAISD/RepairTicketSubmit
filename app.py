from flask import Flask, render_template, request, redirect, url_for, Response, session
import smtplib
from email.mime.text import MIMEText
import sqlite3
import os
import csv
from io import StringIO
from dotenv import load_dotenv
from functools import wraps

app = Flask(__name__)
load_dotenv()

app.secret_key = os.getenv("APP_SECRET_KEY", "changeme-secret")

DB_PATH = os.path.join(os.path.dirname(__file__), "tickets.db")


def init_db():
    """Initialize the SQLite database."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            asset_tag TEXT NOT NULL,
            loaner_tag TEXT,
            building TEXT NOT NULL,
            problem TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()


# --- Authentication decorator ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "logged_in" not in session:
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return decorated_function


# --- Main form route ---
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        name = request.form["name"].strip()
        email = request.form["email"].strip()
        asset_tag = request.form["asset_tag"].strip()
        loaner_tag = request.form["loaner_tag"].strip()
        building = request.form["building"].strip()
        problem = request.form["problem"].strip()

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            "INSERT INTO tickets (name, email, asset_tag, loaner_tag, building, problem) VALUES (?, ?, ?, ?, ?, ?)",
            (name, email, asset_tag, loaner_tag, building, problem),
        )
        conn.commit()
        ticket_id = c.lastrowid
        conn.close()

        send_ticket_email(name, email, asset_tag, loaner_tag, building, problem)

        return redirect(url_for("ticket", ticket_id=ticket_id))

    return render_template("form.html")


# --- Print view ---
@app.route("/ticket/<int:ticket_id>")
def ticket(ticket_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
    ticket = c.fetchone()
    conn.close()

    if not ticket:
        return "Ticket not found", 404

    return render_template("ticket.html", ticket=ticket)


# --- Admin login ---
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        admin_user = os.getenv("ADMIN_USER", "admin")
        admin_pass = os.getenv("ADMIN_PASS", "password")

        if username == admin_user and password == admin_pass:
            session["logged_in"] = True
            return redirect(url_for("admin_dashboard"))
        else:
            return render_template("admin_login.html", error="Invalid credentials")

    return render_template("admin_login.html")


@app.route("/admin/logout")
def admin_logout():
    session.pop("logged_in", None)
    return redirect(url_for("admin_login"))


# --- Admin dashboard ---
@app.route("/admin")
@login_required
def admin_dashboard():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM tickets ORDER BY id DESC")
    tickets = c.fetchall()
    conn.close()
    return render_template("admin_dashboard.html", tickets=tickets)


# --- CSV export ---
@app.route("/admin/export")
@login_required
def export_tickets():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM tickets ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()

    si = StringIO()
    cw = csv.writer(si)
    cw.writerow(["ID", "Name", "Email", "Asset Tag", "Loaner Tag", "Building", "Problem"])
    cw.writerows(rows)
    output = si.getvalue()

    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=tickets_export.csv"},
    )


def send_ticket_email(name, email, asset_tag, loaner_tag, building, problem):
    """Send a ticket email to KACE."""
    smtp_server = os.getenv("SMTP_SERVER")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")
    kace_email = os.getenv("KACE_EMAIL")

    subject = f"New Device Repair Request: {asset_tag}"
    body = f"""
    A new repair ticket has been submitted:

    Name: {name}
    Email: {email}
    Building: {building}
    Asset Tag: {asset_tag}
    Loaner Tag: {loaner_tag or 'None'}
    Problem Description:
    {problem}
    """

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = smtp_user
    msg["To"] = kace_email

    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
        print(f"Ticket email sent to {kace_email}")
    except Exception as e:
        print(f"Error sending email: {e}")


if __name__ == "__main__":
    if not os.path.exists(DB_PATH):
        init_db()
    app.run(host="0.0.0.0", port=5050, debug=True)
