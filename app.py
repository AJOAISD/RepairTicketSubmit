from flask import Flask, render_template, request, redirect, url_for
import smtplib
from email.mime.text import MIMEText
import sqlite3
import os
from dotenv import load_dotenv

app = Flask(__name__)
load_dotenv()

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


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        name = request.form["name"].strip()
        email = request.form["email"].strip()
        asset_tag = request.form["asset_tag"].strip()
        loaner_tag = request.form["loaner_tag"].strip()
        building = request.form["building"].strip()
        problem = request.form["problem"].strip()

        # Save to database
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            "INSERT INTO tickets (name, email, asset_tag, loaner_tag, building, problem) VALUES (?, ?, ?, ?, ?, ?)",
            (name, email, asset_tag, loaner_tag, building, problem),
        )
        conn.commit()
        ticket_id = c.lastrowid
        conn.close()

        # Send email to KACE
        send_ticket_email(name, email, asset_tag, loaner_tag, building, problem)

        # Redirect to print page
        return redirect(url_for("ticket", ticket_id=ticket_id))

    return render_template("form.html")


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
