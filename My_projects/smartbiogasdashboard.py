import streamlit as st
import pandas as pd
import os
from dotenv import load_dotenv
import sib_api_v3_sdk
from sib_api_v3_sdk.rest import ApiException
import sqlite3
import time

# Load env
load_dotenv()
EMAIL_SENDER = os.getenv("EMAIL_SENDER")

# Database
conn = sqlite3.connect("subscribers.db", check_same_thread=False)
c = conn.cursor()

c.execute("""
CREATE TABLE IF NOT EXISTS subscribers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT,
    phone TEXT
)
""")
conn.commit()

# -----------------------------
# ALERT STATE INITIALIZATION
# -----------------------------
if "alerts_sent" not in st.session_state:
    st.session_state.alerts_sent = {
        "feedstock": False,
        "temperature": False,
        "pressure": False
    }

    # -----------------------------
# COOLDOWN TIMER INITIALIZATION
# -----------------------------
if "last_sent_time" not in st.session_state:
    st.session_state.last_sent_time = {
        "feedstock": 0,
        "temperature": 0,
        "pressure": 0
    }

COOLDOWN = 60  # seconds
# -----------------------------
# ALERT FUNCTIONS
# -----------------------------
def send_email_alert(subject, body, receiver):
    try:
        configuration = sib_api_v3_sdk.Configuration()
        configuration.api_key['api-key'] = os.getenv("BREVO_API_KEY")

        api_instance = sib_api_v3_sdk.TransactionalEmailsApi(
            sib_api_v3_sdk.ApiClient(configuration)
        )

        email = sib_api_v3_sdk.SendSmtpEmail(
            to=[{"email": receiver}],
            subject=subject,
            html_content=f"<html><body><h3>{body}</h3></body></html>",
            sender={"email": EMAIL_SENDER}
        )

        api_instance.send_transac_email(email)

        print(f"✅ Brevo email sent to {receiver}")

    except ApiException as e:
        print(f"❌ Brevo error: {e}")

# -----------------------------
# STREAMLIT DASHBOARD UI
# -----------------------------
st.set_page_config(page_title="Smart Biogas Monitor", layout="centered")

st.title("🌱 Hexnn Smart Biogas Monitoring Dashboard")

st.markdown("Monitor feedstock, temperature, and pressure in real-time.")

# -----------------------------
# SIMULATED SENSOR INPUTS
# -----------------------------
feedstock = st.slider("Feedstock Level (%)", 0, 100, 75)
temperature = st.slider("Temperature (°C)", 20, 80, 37)
pressure = st.slider("Pressure (kPa)", 80, 200, 110)

# -----------------------------
# DISPLAY CURRENT VALUES
# -----------------------------
data = pd.DataFrame({
    "Feedstock (%)": [feedstock],
    "Temperature (°C)": [temperature],
    "Pressure (kPa)": [pressure]
})

st.subheader("📊 Current Readings")
st.write(data)

# -----------------------------
# VISUALIZATION
# -----------------------------
st.subheader("📈 Live Trends (Simulated)")
st.line_chart(data)

# -----------------------------
# ALERT CONDITIONS
# -----------------------------
if feedstock < 20:
    st.error("⚠️ Feedstock level critically low!")

    current_time = time.time()

    if (current_time - st.session_state.last_sent_time["feedstock"]) > COOLDOWN:
        c.execute("SELECT email, phone FROM subscribers")
        users = c.fetchall()

        for email, phone in users:
            send_email_alert(
                "Feedstock Alert",
                "Feedstock level is critically low!",
                email
            )

        st.session_state.last_sent_time["feedstock"] = current_time
        


if temperature < 25 or temperature > 65:
    st.warning("⚠️ Temperature out of safe range!")

    current_time = time.time()

    if (current_time - st.session_state.last_sent_time["temperature"]) > COOLDOWN:
        c.execute("SELECT email, phone FROM subscribers")
        users = c.fetchall()

        for email, phone in users:
            send_email_alert(
                "Temperature Alert",
                "Temperature out of range!",
                email
            )

        st.session_state.last_sent_time["temperature"] = current_time

if pressure < 90 or pressure > 180:
    st.warning("⚠️ Pressure out of safe range!")

    current_time = time.time()

    if (current_time - st.session_state.last_sent_time["pressure"]) > COOLDOWN:
        c.execute("SELECT email, phone FROM subscribers")
        users = c.fetchall()

        for email, phone in users:
            send_email_alert(
                "Pressure Alert",
                "Pressure out of range!",
                email
            )

        st.session_state.last_sent_time["pressure"] = current_time

 #------------------------------
# SUBSCRIBE SECTION
#-------------------------------
st.subheader("📩 Get System Alerts")

email_input = st.text_input("Enter your email")
phone_input = st.text_input("Enter your phone (+256...)")

if st.button("Subscribe"):
    if email_input and phone_input:
        c.execute(
            "INSERT INTO subscribers (email, phone) VALUES (?, ?)",
            (email_input, phone_input)
        )
        conn.commit()

        st.success("✅ Subscribed successfully!")
    else:
        st.error("Please enter both email and phone.")
    
        
