import ssl
ssl._create_default_https_context = ssl._create_unverified_context

import streamlit as st
import pandas as pd
import os
from dotenv import load_dotenv
from pathlib import Path
import sib_api_v3_sdk
from sib_api_v3_sdk.rest import ApiException
import sqlite3
import time
from datetime import datetime
import requests

# -----------------------------
# LOAD ENV VARIABLES
# -----------------------------
env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=env_path, override=True)

EMAIL_SENDER = os.getenv("EMAIL_SENDER")
BREVO_API_KEY = os.getenv("BREVO_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# -----------------------------
# DATABASE
# -----------------------------
conn = sqlite3.connect("subscribers.db", check_same_thread=False)
c = conn.cursor()

c.execute("""
CREATE TABLE IF NOT EXISTS subscribers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE
)
""")
conn.commit()

# -----------------------------
# SESSION STATE
# -----------------------------
if "last_sent_time" not in st.session_state:
    st.session_state.last_sent_time = {
        "feedstock": 0,
        "temperature": 0,
        "pressure": 0
    }

if "alert_log" not in st.session_state:
    st.session_state.alert_log = []

if "last_update_id" not in st.session_state:
    st.session_state.last_update_id = None

COOLDOWN = 60

# -----------------------------
# ALERT LOG
# -----------------------------
def log_alert(message):
    timestamp = datetime.now().strftime("%H:%M:%S")
    st.session_state.alert_log.append(f"{timestamp} - {message}")

# -----------------------------
# EMAIL FUNCTION
# -----------------------------
def send_email_alert(subject, body, receiver):
    try:
        configuration = sib_api_v3_sdk.Configuration()
        configuration.api_key['api-key'] = BREVO_API_KEY

        api_instance = sib_api_v3_sdk.TransactionalEmailsApi(
            sib_api_v3_sdk.ApiClient(configuration)
        )

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        email = sib_api_v3_sdk.SendSmtpEmail(
            to=[{"email": receiver}],
            subject=subject,
            html_content=f"""
            <html>
                <body>
                    <h3>{body}</h3>
                    <p><strong>Time:</strong> {timestamp}</p>
                </body>
            </html>
            """,
            sender={"email": EMAIL_SENDER}
        )

        api_instance.send_transac_email(email)
        print(f"✅ Email sent to {receiver}")

    except ApiException as e:
        print(f"❌ Email error: {e}")

# -----------------------------
# TELEGRAM SEND
# -----------------------------
def send_telegram_message(chat_id, message):
    if not TELEGRAM_BOT_TOKEN:
        print("❌ Telegram not configured")
        return

    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

        payload = {
            "chat_id": chat_id,
            "text": message
        }

        requests.post(url, data=payload)
        print("✅ Telegram message sent")

    except Exception as e:
        print(f"❌ Telegram error: {e}")

# -----------------------------
# TELEGRAM COMMAND READER
# -----------------------------
def check_telegram_commands():
    if not TELEGRAM_BOT_TOKEN:
        return

    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"

        params = {}
        if st.session_state.last_update_id:
            params["offset"] = st.session_state.last_update_id + 1

        response = requests.get(url, params=params).json()

        if response["ok"]:
            for update in response["result"]:
                st.session_state.last_update_id = update["update_id"]

                if "message" in update:
                    chat_id = update["message"]["chat"]["id"]
                    text = update["message"].get("text", "").lower()

                    if "status" in text:
                        reply = f"""
📊 BIOGAS SYSTEM STATUS

Feedstock: {feedstock}%
Temperature: {temperature}°C
Pressure: {pressure} kPa
"""
                        send_telegram_message(chat_id, reply)

                    elif "help" in text:
                        send_telegram_message(chat_id, "Send 'status' to get system readings.")

    except Exception as e:
        print("❌ Telegram read error:", e)

# -----------------------------
# STREAMLIT CONFIG
# -----------------------------
st.set_page_config(page_title="Smart Biogas Monitor", layout="centered")

# -----------------------------
# STYLING
# -----------------------------
st.markdown("""
<style>
body {background-color: #0E1117;}
.main {background-color: #0E1117; color: #FAFAFA;}
h1, h2, h3 {color: #00FFAA;}
.stMetric {
    background-color: #1E1E1E;
    padding: 15px;
    border-radius: 12px;
    border: 1px solid #00FFAA;
}
</style>
""", unsafe_allow_html=True)

# -----------------------------
# HEADER
# -----------------------------
st.title("🌱 Smart Biogas Monitoring Dashboard")
st.write("✅ System running...")

# -----------------------------
# SENSOR INPUTS
# -----------------------------
col1, col2, col3 = st.columns(3)

with col1:
    feedstock = st.slider("Feedstock (%)", 0, 100, 75)
    st.metric("Feedstock", f"{feedstock}%")

with col2:
    temperature = st.slider("Temperature (°C)", 20, 80, 37)
    st.metric("Temperature", f"{temperature}°C")

with col3:
    pressure = st.slider("Pressure (kPa)", 80, 200, 110)
    st.metric("Pressure", f"{pressure} kPa")

# 🔥 CHECK TELEGRAM AFTER VALUES EXIST
check_telegram_commands()

# -----------------------------
# DATA DISPLAY
# -----------------------------
st.subheader("📊 Current Readings")

data = pd.DataFrame({
    "Feedstock": [feedstock],
    "Temperature": [temperature],
    "Pressure": [pressure]
})

st.write(data)

# -----------------------------
# CHART
# -----------------------------
st.subheader("📈 Sensor Trends")
st.line_chart(data)

# -----------------------------
# SYSTEM STATUS
# -----------------------------
st.subheader("🧠 System Status")

if feedstock >= 20 and 25 <= temperature <= 65 and 90 <= pressure <= 180:
    st.success("🟢 SYSTEM STABLE")
else:
    st.error("🔴 ATTENTION REQUIRED")

# -----------------------------
# ALERT HISTORY
# -----------------------------
st.subheader("📜 Alert History")

if st.session_state.alert_log:
    for log in reversed(st.session_state.alert_log[-5:]):
        st.write(log)
else:
    st.write("No alerts yet.")

# -----------------------------
# ALERT HANDLER
# -----------------------------
def handle_alert(condition, key, subject, message):
    if condition:
        st.warning(f"⚠️ {subject}")

        current_time = time.time()

        if (current_time - st.session_state.last_sent_time[key]) > COOLDOWN:
            c.execute("SELECT DISTINCT email FROM subscribers")
            users = c.fetchall()

            for (email,) in users:
                send_email_alert(subject, message, email)

            # TELEGRAM ALERT
            send_telegram_message(TELEGRAM_CHAT_ID, f"{subject}\n{message}")

            log_alert(f"{subject} - {message}")
            st.session_state.last_sent_time[key] = current_time

# -----------------------------
# ALERT CONDITIONS
# -----------------------------
handle_alert(feedstock < 20, "feedstock",
             "Feedstock Alert", f"Feedstock low: {feedstock}%")

handle_alert(temperature < 25 or temperature > 65, "temperature",
             "Temperature Alert", f"Temp out of range: {temperature}°C")

handle_alert(pressure < 90 or pressure > 180, "pressure",
             "Pressure Alert", f"Pressure issue: {pressure} kPa")

# -----------------------------
# SUBSCRIBE
# -----------------------------
st.subheader("📩 Get Email Alerts")

email_input = st.text_input("Enter your email")

if st.button("Subscribe"):
    if email_input:
        c.execute("INSERT OR IGNORE INTO subscribers (email) VALUES (?)", (email_input,))
        conn.commit()
        st.success("✅ Subscribed!")
    else:
        st.error("Enter email")

# -----------------------------
# SIDEBAR
# -----------------------------
st.sidebar.title("⚙️ System Info")
st.sidebar.write("Project: Hexnn Smart Biogas System")
st.sidebar.write("Location: Uganda 🇺🇬")
st.sidebar.write("Status: Prototype Phase")
