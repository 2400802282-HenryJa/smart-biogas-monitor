
import os
import time
import sqlite3
from datetime import datetime

import pandas as pd
import requests
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
from dotenv import load_dotenv


# ============================================================
# HEXNN SMART BIOGAS MONITORING DASHBOARD
# ============================================================

st.set_page_config(
    page_title="Hexnn Smart Biogas",
    page_icon="🌱",
    layout="wide",
    initial_sidebar_state="expanded",
)

load_dotenv()


# ============================================================
# SECRETS
# Streamlit Cloud: Settings -> Secrets
# Local development: optional .env fallback
# ============================================================

def get_secret(name, default=""):
    try:
        value = st.secrets.get(name, default)
        if value:
            return value
    except Exception:
        pass
    return os.getenv(name, default)


EMAIL_SENDER = get_secret("EMAIL_SENDER")
BREVO_API_KEY = get_secret("BREVO_API_KEY")
TELEGRAM_BOT_TOKEN = get_secret("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = get_secret("TELEGRAM_CHAT_ID")


# ============================================================
# SESSION STATE
# ============================================================

if "last_sent_time" not in st.session_state:
    st.session_state.last_sent_time = {}

if "alert_log" not in st.session_state:
    st.session_state.alert_log = []

if "activity_feed" not in st.session_state:
    st.session_state.activity_feed = []


# ============================================================
# DATABASE
# ============================================================

DB_PATH = "subscribers.db"


def get_connection():
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def init_database():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS subscribers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL
        )
        """
    )

    conn.commit()
    conn.close()


def add_subscriber(email):
    email = email.strip().lower()

    if not email:
        return False, "Enter an email address."

    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            "INSERT INTO subscribers (email) VALUES (?)",
            (email,),
        )
        conn.commit()
        return True, "Subscription added."
    except sqlite3.IntegrityError:
        return False, "That email is already subscribed."
    finally:
        conn.close()


def get_subscribers():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT email FROM subscribers ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()
    return [row[0] for row in rows]


init_database()


# ============================================================
# FEEDSTOCK PROFILES
# Prototype assumptions — replace with validated project data
# ============================================================

FEEDSTOCK_PROFILES = {
    "Starch-based": {
        "factor": 1.00,
        "moisture": 0.70,
        "volatile_solids": 0.80,
        "cn_ratio": 25,
        "methane": 55,
    },
    "Sugar-based": {
        "factor": 1.05,
        "moisture": 0.75,
        "volatile_solids": 0.82,
        "cn_ratio": 25,
        "methane": 58,
    },
    "Oil-based": {
        "factor": 1.10,
        "moisture": 0.65,
        "volatile_solids": 0.88,
        "cn_ratio": 30,
        "methane": 62,
    },
    "Residue/Waste": {
        "factor": 0.90,
        "moisture": 0.65,
        "volatile_solids": 0.70,
        "cn_ratio": 30,
        "methane": 52,
    },
    "Lignocellulosic Biomass": {
        "factor": 0.75,
        "moisture": 0.60,
        "volatile_solids": 0.65,
        "cn_ratio": 60,
        "methane": 48,
    },
    "Algae": {
        "factor": 0.95,
        "moisture": 0.85,
        "volatile_solids": 0.75,
        "cn_ratio": 12,
        "methane": 58,
    },
    "Animal/Organic Waste": {
        "factor": 0.85,
        "moisture": 0.78,
        "volatile_solids": 0.72,
        "cn_ratio": 22,
        "methane": 55,
    },
}


DIGESTER_PROFILES = {
    "Small scale": {
        "size": 4,
        "range": "2–4 m³",
        "expected": "0.8–1.5 m³/day",
    },
    "Medium": {
        "size": 10,
        "range": "5–10 m³",
        "expected": "2–3 m³/day",
    },
    "Farm scale": {
        "size": 25,
        "range": "15–25 m³",
        "expected": "5–8 m³/day",
    },
    "Community farm": {
        "size": 50,
        "range": "30–50 m³",
        "expected": "10–25 m³/day",
    },
    "Industrial": {
        "size": 100,
        "range": "100+ m³",
        "expected": "40–80 m³/day",
    },
}


def get_feedstock_profile(feedstock_type):
    profile = FEEDSTOCK_PROFILES.get(
        feedstock_type,
        FEEDSTOCK_PROFILES["Animal/Organic Waste"],
    )

    normalized = {
        "moisture": profile["moisture"],
        "volatile_solids": profile["volatile_solids"],
        "cn_ratio": min(max(profile["cn_ratio"] / 30, 0), 1),
    }

    return {
        **profile,
        "normalized": normalized,
    }


# ============================================================
# FORECASTING / METRICS
# Prototype model — not a validated engineering model
# ============================================================

def predict_biogas(
    feedstock,
    temperature,
    feedstock_profile=None,
    digester_profile=None,
    pressure=None,
):
    efficiency = 0.80 if 30 <= temperature <= 40 else 0.50
    base_prediction = feedstock * efficiency

    if feedstock_profile is None:
        return max(base_prediction, 0)

    moisture_factor = (
        1 - abs(feedstock_profile["normalized"]["moisture"] - 0.70) * 0.18
    )

    solids_factor = (
        0.85
        + feedstock_profile["normalized"]["volatile_solids"] * 0.20
    )

    forecast = (
        base_prediction
        * feedstock_profile["factor"]
        * moisture_factor
        * solids_factor
    )

    if digester_profile is not None:
        forecast *= digester_profile["size"] / 100

    if pressure is not None:
        forecast *= max(
            0.75,
            1 - abs(110 - pressure) * 0.002,
        )

    return max(forecast, 0)


def calculate_metrics(
    feedstock,
    temperature,
    pressure,
    feedstock_profile,
    digester_profile,
):
    daily_output = predict_biogas(
        feedstock=feedstock,
        temperature=temperature,
        feedstock_profile=feedstock_profile,
        digester_profile=digester_profile,
        pressure=pressure,
    )

    monthly_output = daily_output * 30
    methane_percentage = feedstock_profile["methane"]
    co2_reduction = monthly_output * 1.8
    energy_value = daily_output * 6.0

    temperature_score = max(
        0,
        100 - abs(37 - temperature) * 5,
    )

    pressure_score = max(
        0,
        100 - abs(110 - pressure) * 1.2,
    )

    efficiency_score = (
        temperature_score * 0.6
        + pressure_score * 0.4
    )

    return {
        "daily_output": daily_output,
        "monthly_output": monthly_output,
        "co2_reduction": co2_reduction,
        "energy_value": energy_value,
        "methane_percentage": methane_percentage,
        "efficiency_score": efficiency_score,
    }


# ============================================================
# ALERTS
# ============================================================

COOLDOWN = 60


def log_activity(message):
    st.session_state.activity_feed.insert(
        0,
        {
            "time": datetime.now().strftime("%H:%M:%S"),
            "message": message,
        },
    )

    st.session_state.activity_feed = (
        st.session_state.activity_feed[:20]
    )


def send_email_alert(subject, body, receiver):
    """
    Send a transactional email through Brevo REST API.
    """

    if not BREVO_API_KEY:
        return False, "BREVO_API_KEY is missing."

    if not EMAIL_SENDER:
        return False, "EMAIL_SENDER is missing."

    if not receiver:
        return False, "Recipient email is missing."

    url = "https://api.brevo.com/v3/smtp/email"

    headers = {
        "accept": "application/json",
        "api-key": BREVO_API_KEY,
        "content-type": "application/json",
    }

    payload = {
        "sender": {
            "name": "Hexnn Smart Biogas",
            "email": EMAIL_SENDER,
        },
        "to": [
            {
                "email": receiver,
            }
        ],
        "subject": subject,
        "htmlContent": f"""
            <html>
                <body>
                    <h2>🌱 Hexnn Smart Biogas Alert</h2>

                    <p>{body}</p>

                    <hr>

                    <p>
                        <strong>Hexnn Energy Solutions</strong><br>
                        Smart Biogas Monitoring Platform
                    </p>
                </body>
            </html>
        """,
    }

    try:
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=20,
        )

        if response.status_code == 201:
            try:
                result = response.json()
                message_id = result.get("messageId", "unknown")

                return True, (
                    f"Email dispatched successfully. "
                    f"Message ID: {message_id}"
                )

            except ValueError:
                return True, "Email dispatched successfully."

        else:
            return False, (
                f"Brevo API error "
                f"{response.status_code}: "
                f"{response.text}"
            )

    except requests.RequestException as e:
        return False, f"Network request failed: {str(e)}"

    except Exception as e:
        return False, f"Unexpected email error: {str(e)}"


def send_telegram_message(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False, "Telegram configuration is missing."

    url = (
        f"https://api.telegram.org/bot"
        f"{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
    }

    try:
        response = requests.post(
            url,
            data=payload,
            timeout=20,
        )

        if response.ok:
            return True, "Telegram sent."

        return False, f"Telegram HTTP {response.status_code}"

    except requests.RequestException as exc:
        return False, f"Telegram request failed: {exc}"


def handle_alert(alert_key, subject, body):
    now = time.time()

    last_time = st.session_state.last_sent_time.get(
        alert_key,
        0,
    )

    if now - last_time < COOLDOWN:
        return

    st.session_state.last_sent_time[alert_key] = now

    recipients = get_subscribers()

    for email in recipients:
        send_email_alert(
            subject=subject,
            body=body,
            receiver=email,
        )

    send_telegram_message(
        f"🌱 HEXNN SMART BIOGAS ALERT\n\n"
        f"{subject}\n\n"
        f"{body}"
    )

    st.session_state.alert_log.insert(
        0,
        {
            "time": datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
            "subject": subject,
            "body": body,
        },
    )

    st.session_state.alert_log = (
        st.session_state.alert_log[:20]
    )

    log_activity(subject)


# ============================================================
# SYSTEM STATUS
# ============================================================

def get_system_status(feedstock, temperature, pressure):
    problems = []

    if feedstock < 20:
        problems.append("Low feedstock")

    if temperature < 25 or temperature > 65:
        problems.append("Temperature outside alert range")

    if pressure < 90 or pressure > 180:
        problems.append("Pressure outside alert range")

    if not problems:
        return "OPTIMAL", "System operating within prototype thresholds."

    if len(problems) == 1:
        return "ATTENTION", problems[0]

    return "ALERT", " | ".join(problems)


# ============================================================
# VISUAL STYLE
# ============================================================

st.markdown(
    """
    <style>
    .stApp {
        background:
            radial-gradient(
                circle at top right,
                rgba(0, 120, 90, 0.18),
                transparent 35%
            ),
            #07130f;
        color: #eaf7f1;
    }

    section[data-testid="stSidebar"] {
        background: #071a14;
        border-right: 1px solid rgba(80, 180, 140, 0.18);
    }

    .block-container {
        padding-top: 1rem;
        padding-bottom: 2rem;
        max-width: 1500px;
    }

    .hero {
        padding: 18px 20px;
        border-radius: 18px;
        background: rgba(12, 37, 29, 0.82);
        border: 1px solid rgba(88, 190, 150, 0.18);
        margin-bottom: 14px;
    }

    .hero h1 {
        margin: 0;
        font-size: 30px;
    }

    .hero p {
        margin: 5px 0 0;
        color: #8fb7a8;
    }

    .metric-card {
        padding: 16px;
        border-radius: 16px;
        background: rgba(12, 35, 28, 0.90);
        border: 1px solid rgba(95, 190, 150, 0.16);
        min-height: 125px;
    }

    .metric-label {
        color: #8eb4a5;
        font-size: 13px;
    }

    .metric-value {
        font-size: 28px;
        font-weight: 700;
        margin-top: 6px;
    }

    .metric-sub {
        color: #6fa58f;
        font-size: 12px;
        margin-top: 4px;
    }

    .panel {
        padding: 14px 16px;
        border-radius: 16px;
        background: rgba(10, 31, 24, 0.82);
        border: 1px solid rgba(95, 190, 150, 0.13);
        margin-bottom: 14px;
    }

    div[data-testid="stMetric"] {
        background: rgba(12, 35, 28, 0.90);
        border: 1px solid rgba(95, 190, 150, 0.16);
        padding: 12px;
        border-radius: 16px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# SIDEBAR CONTROLS
# ============================================================

with st.sidebar:
    st.markdown("## 🌱 HEXNN")
    st.caption("Smart Biogas Monitoring")

    st.markdown("---")

    feedstock_type = st.selectbox(
        "Feedstock",
        list(FEEDSTOCK_PROFILES.keys()),
        index=6,
    )

    digester_type = st.selectbox(
        "Digester profile",
        list(DIGESTER_PROFILES.keys()),
        index=1,
    )

    st.markdown("---")

    feedstock = st.slider(
        "Feedstock level (%)",
        min_value=0,
        max_value=100,
        value=75,
    )

    temperature = st.slider(
        "Temperature (°C)",
        min_value=0,
        max_value=80,
        value=37,
    )

    pressure = st.slider(
        "Gas pressure (kPa)",
        min_value=0,
        max_value=250,
        value=110,
    )

    st.markdown("---")
    st.caption(
        "Prototype monitoring controls. "
        "Connect validated sensors before operational use."
    )
    with st.sidebar:

    st.markdown("---")
    st.subheader("📧 Email Test")

    test_email = st.text_input(
        "Test recipient",
        placeholder="your@email.com",
    )

    if st.button("Send Test Email", use_container_width=True):

        if not test_email:
            st.warning("Enter a test email address.")

        else:
            success, message = send_email_alert(
                subject="🌱 Hexnn Smart Biogas Test",
                body=(
                    "This is a test email from the "
                    "Hexnn Smart Biogas Monitoring Dashboard."
                ),
                receiver=test_email,
            )

            if success:
                st.success(message)
            else:
                st.error(message)


# ============================================================
# CALCULATIONS
# ============================================================

feedstock_profile = get_feedstock_profile(feedstock_type)
digester_profile = DIGESTER_PROFILES[digester_type]

metrics = calculate_metrics(
    feedstock=feedstock,
    temperature=temperature,
    pressure=pressure,
    feedstock_profile=feedstock_profile,
    digester_profile=digester_profile,
)

status, status_message = get_system_status(
    feedstock,
    temperature,
    pressure,
)


# ============================================================
# AUTOMATIC ALERTS
# ============================================================

if feedstock < 20:
    handle_alert(
        "low_feedstock",
        "Low Feedstock Level",
        f"Feedstock level is {feedstock}%.",
    )

if temperature < 25 or temperature > 65:
    handle_alert(
        "temperature_alert",
        "Temperature Alert",
        f"Digester temperature is {temperature} °C.",
    )

if pressure < 90 or pressure > 180:
    handle_alert(
        "pressure_alert",
        "Gas Pressure Alert",
        f"Gas pressure is {pressure} kPa.",
    )


# ============================================================
# HEADER
# ============================================================

st.markdown(
    f"""
    <div class="hero">
        <h1>🌱 Hexnn Smart Biogas Monitoring</h1>
        <p>
            Real-time prototype monitoring · AI-assisted forecasting ·
            Feedstock intelligence
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# KPI CARDS
# ============================================================

k1, k2, k3, k4, k5 = st.columns(5)

with k1:
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-label">SYSTEM STATUS</div>
            <div class="metric-value">{status}</div>
            <div class="metric-sub">{status_message}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with k2:
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-label">CH₄ ESTIMATE</div>
            <div class="metric-value">
                {metrics["methane_percentage"]:.0f}%
            </div>
            <div class="metric-sub">
                prototype feedstock estimate
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with k3:
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-label">TEMPERATURE</div>
            <div class="metric-value">{temperature} °C</div>
            <div class="metric-sub">
                target reference ≈ 37 °C
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with k4:
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-label">GAS PRESSURE</div>
            <div class="metric-value">{pressure} kPa</div>
            <div class="metric-sub">
                current prototype reading
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with k5:
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-label">FORECAST</div>
            <div class="metric-value">
                {metrics["daily_output"]:.2f}
            </div>
            <div class="metric-sub">
                m³/day prototype estimate
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ============================================================
# MAIN MONITORING VISUALS
# ============================================================

left, right = st.columns([1.45, 1])

with left:
    st.markdown("### Live Process Monitor")

    temperature_fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=temperature,
            title={"text": "Temperature °C"},
            gauge={
                "axis": {"range": [0, 80]},
                "bar": {"color": "#39c98a"},
                "steps": [
                    {"range": [0, 25], "color": "#2b3a34"},
                    {"range": [25, 65], "color": "#163c2e"},
                    {"range": [65, 80], "color": "#2b3a34"},
                ],
            },
        )
    )

    temperature_fig.update_layout(
        height=270,
        margin=dict(l=20, r=20, t=45, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#dff5ea"),
    )

    st.plotly_chart(
        temperature_fig,
        use_container_width=True,
    )

    p1, p2 = st.columns(2)

    with p1:
        st.markdown("#### Feedstock Level")

        feed_fig = go.Figure(
            go.Indicator(
                mode="gauge+number",
                value=feedstock,
                number={"suffix": "%"},
                gauge={
                    "axis": {"range": [0, 100]},
                    "bar": {"color": "#48d597"},
                },
            )
        )

        feed_fig.update_layout(
            height=220,
            margin=dict(l=20, r=20, t=20, b=20),
            paper_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#dff5ea"),
        )

        st.plotly_chart(
            feed_fig,
            use_container_width=True,
        )

    with p2:
        st.markdown("#### Gas Pressure")

        pressure_fig = go.Figure(
            go.Indicator(
                mode="gauge+number",
                value=pressure,
                number={"suffix": " kPa"},
                gauge={
                    "axis": {"range": [0, 250]},
                    "bar": {"color": "#59b6ff"},
                },
            )
        )

        pressure_fig.update_layout(
            height=220,
            margin=dict(l=20, r=20, t=20, b=20),
            paper_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#dff5ea"),
        )

        st.plotly_chart(
            pressure_fig,
            use_container_width=True,
        )


with right:
    st.markdown("### System Intelligence")

    efficiency = metrics["efficiency_score"]

    efficiency_fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=efficiency,
            number={"suffix": "%"},
            title={"text": "Operational Stability"},
            gauge={
                "axis": {"range": [0, 100]},
                "bar": {"color": "#4ee09c"},
                "steps": [
                    {"range": [0, 50], "color": "#3a2929"},
                    {"range": [50, 75], "color": "#3a3625"},
                    {"range": [75, 100], "color": "#173a2d"},
                ],
            },
        )
    )

    efficiency_fig.update_layout(
        height=260,
        margin=dict(l=20, r=20, t=40, b=20),
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#dff5ea"),
    )

    st.plotly_chart(
        efficiency_fig,
        use_container_width=True,
    )

    st.markdown(
        f"""
        <div class="panel">
            <b>Feedstock Intelligence</b><br><br>
            Type: <b>{feedstock_type}</b><br>
            C/N reference: <b>{feedstock_profile["cn_ratio"]}</b><br>
            Volatile solids:
            <b>{feedstock_profile["volatile_solids"]:.0%}</b><br>
            Estimated methane:
            <b>{feedstock_profile["methane"]}%</b>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        f"""
        <div class="panel">
            <b>Digester Profile</b><br><br>
            Class: <b>{digester_type}</b><br>
            Nominal size:
            <b>{digester_profile["range"]}</b><br>
            Reference output:
            <b>{digester_profile["expected"]}</b>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ============================================================
# PRODUCTION & IMPACT
# ============================================================

st.markdown("### Production & Impact")

a, b, c, d = st.columns(4)

with a:
    st.metric(
        "Daily biogas",
        f'{metrics["daily_output"]:.2f} m³',
    )

with b:
    st.metric(
        "30-day projection",
        f'{metrics["monthly_output"]:.1f} m³',
    )

with c:
    st.metric(
        "Energy estimate",
        f'{metrics["energy_value"]:.1f} kWh/day',
    )

with d:
    st.metric(
        "CO₂ reduction estimate",
        f'{metrics["co2_reduction"]:.1f} kg/month',
    )


# ============================================================
# PROCESS TREND
# ============================================================

st.markdown("### Process Trend")

trend = pd.DataFrame(
    {
        "Day": list(range(1, 8)),
        "Temperature": [
            max(0, temperature - 2),
            max(0, temperature - 1),
            temperature,
            temperature + 1,
            temperature,
            max(0, temperature - 1),
            temperature,
        ],
        "Pressure": [
            max(0, pressure - 8),
            max(0, pressure - 3),
            pressure,
            pressure + 4,
            max(0, pressure - 2),
            pressure + 2,
            pressure,
        ],
        "Feedstock": [
            max(0, feedstock - 9),
            max(0, feedstock - 7),
            max(0, feedstock - 5),
            max(0, feedstock - 3),
            max(0, feedstock - 2),
            max(0, feedstock - 1),
            feedstock,
        ],
    }
)

trend_fig = px.line(
    trend,
    x="Day",
    y=["Temperature", "Pressure", "Feedstock"],
    markers=True,
)

trend_fig.update_layout(
    height=360,
    margin=dict(l=20, r=20, t=20, b=20),
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#dff5ea"),
    legend_title_text="",
)

trend_fig.update_xaxes(
    gridcolor="rgba(120,180,150,0.10)"
)

trend_fig.update_yaxes(
    gridcolor="rgba(120,180,150,0.10)"
)

st.plotly_chart(
    trend_fig,
    use_container_width=True,
)


# ============================================================
# ALERT CENTER & SUBSCRIPTIONS
# ============================================================

left_alert, right_alert = st.columns([1.2, 1])

with left_alert:
    st.markdown("### Alert Center")

    if st.session_state.alert_log:
        alert_df = pd.DataFrame(
            st.session_state.alert_log
        )

        st.dataframe(
            alert_df,
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.success(
            "No alerts recorded in this session."
        )

with right_alert:
    st.markdown("### Notifications")

    with st.form("subscribe_form"):
        email = st.text_input(
            "Email address",
            placeholder="you@example.com",
        )

        submitted = st.form_submit_button(
            "Subscribe to alerts"
        )

        if submitted:
            success, message = add_subscriber(email)

            if success:
                st.success(message)
                log_activity(
                    "New alert subscriber added."
                )
            else:
                st.warning(message)

    st.caption(
        f"{len(get_subscribers())} email subscriber(s)"
    )


# ============================================================
# ACTIVITY / TELEGRAM
# ============================================================

st.markdown("### Activity")

activity_col, telegram_col = st.columns(2)

with activity_col:
    if st.session_state.activity_feed:
        for item in st.session_state.activity_feed[:10]:
            st.write(
                f"**{item['time']}** — "
                f"{item['message']}"
            )
    else:
        st.caption("No activity yet.")

with telegram_col:
    st.markdown(
        """
        <div class="panel">
            <b>Telegram monitoring channel</b><br><br>
            Configured Telegram alerts can receive
            system notifications from this dashboard.
        </div>
        """,
        unsafe_allow_html=True,
    )


# ============================================================
# FOOTER
# ============================================================

st.markdown("---")

st.caption(
    "Hexnn Energy Solutions · Smart Biogas Platform · "
    "Prototype monitoring environment"
)
