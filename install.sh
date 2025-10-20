#!/bin/bash
# Flask Ticket App Smart Installer (GitHub, Nginx, Email, Multi-App)
# Usage: sudo bash install.sh

APP_NAME="flask_ticket_app"
BASE_DIR="/opt"
APP_DIR="${BASE_DIR}/${APP_NAME}"
VENV_DIR="${APP_DIR}/venv"
SERVICE_FILE="/etc/systemd/system/${APP_NAME}.service"
ENV_FILE="${APP_DIR}/.env"
BASE_PORT=5050

echo "=== Flask Ticket App Installer ==="

# --- Prompt for GitHub repo ---
read -rp "Enter GitHub repository URL (e.g. https://github.com/YourOrg/flask_ticket_app.git): " GIT_REPO
if [ -z "$GIT_REPO" ]; then
  echo "❌ No repository provided. Exiting."
  exit 1
fi

# --- Helper: find next free port ---
find_next_port() {
  local port=$BASE_PORT
  while ss -tuln | grep -q ":$port "; do
    port=$((port + 1))
  done
  echo "$port"
}

# --- Helper: detect existing Flask apps ---
check_other_flask_apps() {
  if systemctl list-units --type=service | grep -q gunicorn; then
    return 0
  elif pgrep -f gunicorn >/dev/null 2>&1 || pgrep -f flask >/dev/null 2>&1; then
    return 0
  else
    return 1
  fi
}

# --- 1. Install dependencies ---
echo "[1/9] Installing required packages..."
apt-get update -y
apt-get install -y python3 python3-venv git nginx

# --- 2. Clone or update GitHub repo ---
echo "[2/9] Cloning or updating repository..."
if [ -d "$APP_DIR/.git" ]; then
  echo "Repository exists — pulling latest changes..."
  cd "$APP_DIR" || exit 1
  git pull
else
  git clone "$GIT_REPO" "$APP_DIR"
fi
cd "$APP_DIR" || exit 1

# --- 3. Create Python virtual environment ---
echo "[3/9] Setting up virtual environment..."
python3 -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"

# --- 4. Install required Python packages ---
echo "[4/9] Installing Python dependencies..."
pip install --upgrade pip
pip install flask gunicorn flask-mail python-dotenv

# --- 5. Prompt for email configuration ---
echo "[5/9] Configuring email (Flask-Mail)..."
read -rp "SMTP Server: " MAIL_SERVER
read -rp "SMTP Port (default 587): " MAIL_PORT
MAIL_PORT=${MAIL_PORT:-587}
read -rp "Use TLS? (y/n, default y): " USE_TLS
USE_TLS=${USE_TLS:-y}
if [[ "$USE_TLS" =~ ^[Yy]$ ]]; then
  MAIL_USE_TLS=True
else
  MAIL_USE_TLS=False
fi
read -rp "SMTP Username: " MAIL_USERNAME
read -rsp "SMTP Password: " MAIL_PASSWORD
echo
read -rp "Sender email address (e.g. helpdesk@yourdomain.com): " MAIL_DEFAULT_SENDER
read -rp "KACE ticket email address: " KACE_EMAIL

# --- 6. Create .env file ---
cat <<EOF > "$ENV_FILE"
MAIL_SERVER=${MAIL_SERVER}
MAIL_PORT=${MAIL_PORT}
MAIL_USE_TLS=${MAIL_USE_TLS}
MAIL_USERNAME=${MAIL_USERNAME}
MAIL_PASSWORD=${MAIL_PASSWORD}
MAIL_DEFAULT_SENDER=${MAIL_DEFAULT_SENDER}
KACE_EMAIL=${KACE_EMAIL}
EOF

chmod 600 "$ENV_FILE"
echo "✅ Email configuration saved to ${ENV_FILE}"

# --- 7. Initialize database ---
echo "[7/9] Initializing database..."
python3 - <<'EOF'
import sqlite3, os
DB_FILE = "tickets.db"
if not os.path.exists(DB_FILE):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_name TEXT,
            asset_tag TEXT,
            loaner_tag TEXT,
            problem TEXT,
            building TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()
    print("✅ Database initialized.")
else:
    print("Database already exists — skipped initialization.")
EOF

# --- 8. Configure Nginx and port ---
if check_other_flask_apps; then
  echo "[8/9] Other Flask apps detected."
  PORT=$(find_next_port)
  echo "Assigned next available port: $PORT"
else
  echo "[8/9] No other Flask apps detected — installing Nginx config..."
  PORT=$BASE_PORT
  cat <<EOF > /etc/nginx/sites-available/${APP_NAME}
server {
    listen 80;
    server_name _;

    location / {
        proxy_pass http://127.0.0.1:${PORT};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
    }
}
EOF
  ln -sf /etc/nginx/sites-available/${APP_NAME} /etc/nginx/sites-enabled/${APP_NAME}
  nginx -t && systemctl restart nginx
fi

# --- 9. Create and enable systemd service ---
echo "[9/9] Creating systemd service..."
cat <<EOF > "$SERVICE_FILE"
[Unit]
Description=Flask Ticket Intake App
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=${APP_DIR}
Environment="PATH=${VENV_DIR}/bin"
ExecStart=${VENV_DIR}/bin/gunicorn -w 2 -b 127.0.0.1:${PORT} app:app
Restart=always

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable ${APP_NAME}.service
systemctl restart ${APP_NAME}.service

echo "------------------------------------------"
echo "✅ Installation Complete!"
echo "App Directory: ${APP_DIR}"
echo "Port: ${PORT}"
if [ "$PORT" = "$BASE_PORT" ]; then
  echo "Accessible at: http://<server-ip>/"
else
  echo "Accessible at: http://<server-ip>:${PORT}/"
fi
echo "------------------------------------------"
echo "Manage service with:"
echo "  sudo systemctl [start|stop|restart|status] ${APP_NAME}.service"
