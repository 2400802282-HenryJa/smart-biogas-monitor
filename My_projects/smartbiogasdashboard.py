# ============================================================
# 🌱 HEXNN SMART BIOGAS SYSTEM
# Visual monitoring dashboard — Streamlit Community Cloud
# ============================================================

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import os
import sqlite3
import time
from datetime import datetime
import requests
import sib_api_v3_sdk
from sib_api_v3_sdk.rest import ApiException


# ============================================================
# 🔐 STREAMLIT CLOUD SECRETS
# ============================================================
# Configure these once in:
# Streamlit Community Cloud → App → Settings → Secrets
#
# EMAIL_SENDER
# BREVO_API_KEY
# TELEGRAM_BOT_TOKEN
# TELEGRAM_CHAT_ID
#
# No .env file is required for the deployed application.
# ============================================================

def get_secret(name, default=None):
    try:
        value = st.secrets.get(name)
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
# ⚙️ PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="Hexnn Smart Biogas",
    page_icon="🌱",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# 🗄️ LOCAL APP DATA
# ============================================================
# This database is only used for subscriber records.
# Secrets are NOT stored here.
# ============================================================

conn = sqlite3.connect("subscribers.db", check_same_thread=False)
c = conn.cursor()

c.execute(
    """
    CREATE TABLE IF NOT EXISTS subscribers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE
    )
    """
)
conn.commit()


# ============================================================
# 🧠 SESSION STATE
# ============================================================

defaults = {
    "last_sent_time": {
        "feedstock": 0,
        "temperature": 0,
        "pressure": 0,
    },
    "alert_log": [],
    "activity_feed": [],
    "last_update_id": None,
    "history": [],
    "last_reading_signature": None,
    "feedstock_profile_signature": None,
}

for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value

COOLDOWN = 60


# ============================================================
# 🌾 FEEDSTOCK PROFILES
# ============================================================

FEEDSTOCK_PROFILES = {
    "Starch-based": {
        "items": ["Corn", "Wheat", "Barley"],
        "defaults": {
            "moisture": 65,
            "cn_ratio": 28,
            "particle_size": 4,
            "volatile_solids": 88,
            "fixed_solids": 12,
            "energy_content": 17.5,
        },
        "factor": 1.0,
        "methane": 61,
    },
    "Sugar-based": {
        "items": ["Sugarcane", "Sugarcane waste", "Sugar beet"],
        "defaults": {
            "moisture": 72,
            "cn_ratio": 24,
            "particle_size": 3,
            "volatile_solids": 90,
            "fixed_solids": 10,
            "energy_content": 16.8,
        },
        "factor": 1.08,
        "methane": 64,
    },
    "Oil-based": {
        "items": ["Soybean", "Palm oil", "Used cooking oil"],
        "defaults": {
            "moisture": 12,
            "cn_ratio": 32,
            "particle_size": 2,
            "volatile_solids": 94,
            "fixed_solids": 6,
            "energy_content": 30.0,
        },
        "factor": 1.22,
        "methane": 68,
    },
    "Residue / Waste": {
        "items": ["Agricultural residues", "Food waste", "Industrial byproducts"],
        "defaults": {
            "moisture": 70,
            "cn_ratio": 22,
            "particle_size": 5,
            "volatile_solids": 85,
            "fixed_solids": 15,
            "energy_content": 16.0,
        },
        "factor": 1.03,
        "methane": 62,
    },
    "Lignocellulosic Biomass": {
        "items": ["Corn stover", "Wood chips", "Switchgrass"],
        "defaults": {
            "moisture": 20,
            "cn_ratio": 45,
            "particle_size": 8,
            "volatile_solids": 78,
            "fixed_solids": 22,
            "energy_content": 18.5,
        },
        "factor": 0.78,
        "methane": 52,
    },
    "Algae": {
        "items": ["Microalgae species"],
        "defaults": {
            "moisture": 82,
            "cn_ratio": 10,
            "particle_size": 1,
            "volatile_solids": 86,
            "fixed_solids": 14,
            "energy_content": 19.0,
        },
        "factor": 1.12,
        "methane": 65,
    },
    "Animal / Organic Waste": {
        "items": [
            "Cow dung",
            "Goat dung",
            "Pig dung",
            "Poultry droppings",
            "Human excreta",
            "Water hyacinth",
        ],
        "defaults": {
            "moisture": 80,
            "cn_ratio": 18,
            "particle_size": 8,
            "volatile_solids": 75,
            "fixed_solids": 25,
            "energy_content": 15.0,
        },
        "factor": 0.85,
        "methane": 58,
        "item_profiles": {
            "Cow dung": {
                "moisture": 80, "cn_ratio": 18, "particle_size": 8,
                "volatile_solids": 75, "fixed_solids": 25,
                "energy_content": 15.0, "factor": 0.85, "methane": 58,
            },
            "Goat dung": {
                "moisture": 72, "cn_ratio": 16, "particle_size": 8,
                "volatile_solids": 78, "fixed_solids": 22,
                "energy_content": 16.0, "factor": 0.90, "methane": 60,
            },
            "Pig dung": {
                "moisture": 82, "cn_ratio": 14, "particle_size": 8,
                "volatile_solids": 80, "fixed_solids": 20,
                "energy_content": 16.5, "factor": 0.95, "methane": 61,
            },
            "Poultry droppings": {
                "moisture": 65, "cn_ratio": 10, "particle_size": 5,
                "volatile_solids": 82, "fixed_solids": 18,
                "energy_content": 17.5, "factor": 1.10, "methane": 65,
            },
            "Human excreta": {
                "moisture": 78, "cn_ratio": 8, "particle_size": 5,
                "volatile_solids": 70, "fixed_solids": 30,
                "energy_content": 14.5, "factor": 0.90, "methane": 57,
            },
            "Water hyacinth": {
                "moisture": 90, "cn_ratio": 25, "particle_size": 8,
                "volatile_solids": 60, "fixed_solids": 40,
                "energy_content": 12.0, "factor": 0.65, "methane": 54,
            },
        },
    },
}


# ============================================================
# 🏭 DIGESTER PROFILES
# ============================================================

DIGESTER_PROFILES = {
    "Small scale": {
        "range": "2–4 m³",
        "size": 3,
        "minimum": 0.8,
        "maximum": 1.5,
    },
    "Medium": {
        "range": "5–10 m³",
        "size": 7.5,
        "minimum": 2.0,
        "maximum": 3.0,
    },
    "Farm scale": {
        "range": "15–25 m³",
        "size": 20,
        "minimum": 5.0,
        "maximum": 8.0,
    },
    "Community farm": {
        "range": "30–50 m³",
        "size": 40,
        "minimum": 10.0,
        "maximum": 25.0,
    },
    "Industrial": {
        "range": "100+ m³",
        "size": 100,
        "minimum": 40.0,
        "maximum": 80.0,
    },
}


# ============================================================
# 🔧 HELPERS
# ============================================================

def log_alert(message):
    timestamp = datetime.now().strftime("%H:%M:%S")
    st.session_state.alert_log.append(f"{timestamp} — {message}")
    st.session_state.alert_log = st.session_state.alert_log[-20:]


def log_activity(message):
    timestamp = datetime.now().strftime("%H:%M:%S")
    st.session_state.activity_feed.append(f"{timestamp}  |  {message}")
    st.session_state.activity_feed = st.session_state.activity_feed[-12:]


def apply_feedstock_defaults():
    category = st.session_state.get("feedstock_category", "Residue / Waste")
    profile = FEEDSTOCK_PROFILES[category]
    subtype = st.session_state.get("feedstock_subtype")

    defaults_for_type = profile.get("item_profiles", {}).get(
        subtype,
        profile["defaults"],
    )

    for property_name, value in defaults_for_type.items():
        if property_name not in {"factor", "methane"}:
            st.session_state[f"feedstock_{property_name}"] = value


def get_feedstock_profile(category, subtype, properties):
    category_profile = FEEDSTOCK_PROFILES[category]

    profile = category_profile.get("item_profiles", {}).get(
        subtype,
        category_profile,
    )

    normalized = {
        "moisture": max(0, min(100, properties["moisture"])) / 100,
        "cn_ratio": max(0, min(60, properties["cn_ratio"])) / 60,
        "particle_size": max(0, min(20, properties["particle_size"])) / 20,
        "volatile_solids": max(0, min(100, properties["volatile_solids"])) / 100,
        "fixed_solids": max(0, min(100, properties["fixed_solids"])) / 100,
        "energy_content": max(0, min(40, properties["energy_content"])) / 40,
    }

    category_encoding = {
        name: int(name == category)
        for name in FEEDSTOCK_PROFILES
    }

    suitability = round(
        max(
            0,
            min(
                100,
                (normalized["volatile_solids"] * 45)
                + (normalized["energy_content"] * 25)
                + ((1 - abs(normalized["cn_ratio"] - 0.37)) * 30),
            ),
        )
    )

    return {
        "category": category,
        "subtype": subtype,
        "category_encoding": category_encoding,
        "normalized": normalized,
        "suitability": suitability,
        "factor": profile["factor"],
        "methane": profile["methane"],
    }


def get_digester_metrics(digester_category, prediction):
    profile = DIGESTER_PROFILES[digester_category]

    utilization = round((prediction / profile["maximum"]) * 100)

    return {
        "category": digester_category,
        "range": profile["range"],
        "minimum": profile["minimum"],
        "maximum": profile["maximum"],
        "size": profile["size"],
        "utilization": max(0, utilization),
        "within_range": profile["minimum"] <= prediction <= profile["maximum"],
    }


def predict_biogas(
    feedstock,
    temperature,
    feedstock_profile=None,
    digester_profile=None,
    pressure=None,
):
    efficiency = 0.8 if 30 <= temperature <= 40 else 0.5
    base_prediction = feedstock * efficiency

    if feedstock_profile is None:
        return base_prediction

    moisture_factor = (
        1 - abs(feedstock_profile["normalized"]["moisture"] - 0.7) * 0.18
    )

    solids_factor = (
        0.85 + (feedstock_profile["normalized"]["volatile_solids"] * 0.2)
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

    return forecast


def calculate_dashboard_metrics(
    feedstock,
    temperature,
    pressure,
    prediction,
    feedstock_profile=None,
):
    temperature_stability = max(
        0,
        100 - abs(37 - temperature) * 4,
    )

    pressure_stability = max(
        0,
        100 - abs(110 - pressure) * 0.8,
    )

    suitability = (
        feedstock_profile["suitability"]
        if feedstock_profile
        else 75
    )

    efficiency_score = round(
        (temperature_stability * 0.55)
        + (pressure_stability * 0.3)
        + (suitability * 0.15)
    )

    operational_stability = round(
        (temperature_stability + pressure_stability + feedstock) / 3
    )

    return {
        "daily_output": prediction,
        "monthly_output": prediction * 30,
        "co2_reduction": prediction * 1.8,
        "energy_savings": prediction * 0.6,
        "efficiency_score": min(100, efficiency_score),
        "operational_stability": min(
            100,
            round(operational_stability),
        ),
        "methane_percentage": (
            feedstock_profile["methane"]
            if feedstock_profile
            else 60
        ),
        "feedstock_suitability": suitability,
    }


def get_ai_insight(
    feedstock,
    temperature,
    pressure,
    metrics,
    feedstock_profile=None,
):
    if feedstock < 20:
        return (
            "HIGH",
            "Low substrate availability detected.",
            "Review feedstock supply",
        )

    if temperature < 30 or temperature > 40:
        return (
            "MEDIUM",
            "Temperature drift detected.",
            "Monitor thermal stability",
        )

    if pressure < 90 or pressure > 180:
        return (
            "MEDIUM",
            "Pressure outside the configured monitoring range.",
            "Review pressure conditions",
        )

    if feedstock_profile and feedstock_profile["category"] == "Oil-based":
        return (
            "LOW",
            "Oil-rich feedstock profile selected.",
            "Monitor loading conditions",
        )

    if metrics["efficiency_score"] >= 85:
        return (
            "LOW",
            "Current monitored conditions are stable.",
            "Continue monitoring",
        )

    return (
        "MEDIUM",
        "Operating conditions are usable but should be monitored.",
        "Monitor next refresh",
    )


# ============================================================
# 📧 BREVO
# ============================================================

def send_email_alert(subject, body, receiver):
    if not BREVO_API_KEY or not EMAIL_SENDER:
        return False

    try:
        configuration = sib_api_v3_sdk.Configuration()
        configuration.api_key["api-key"] = BREVO_API_KEY

        api_instance = sib_api_v3_sdk.TransactionalEmailsApi(
            sib_api_v3_sdk.ApiClient(configuration)
        )

        email = sib_api_v3_sdk.SendSmtpEmail(
            to=[{"email": receiver}],
            subject=subject,
            html_content=f"""
                <html>
                    <body style="font-family:Arial,sans-serif;">
                        <h2>🌱 Hexnn Smart Biogas Alert</h2>
                        <h3>{subject}</h3>
                        <p>{body}</p>
                        <hr>
                        <small>Hexnn Energy Solutions</small>
                    </body>
                </html>
            """,
            sender={"email": EMAIL_SENDER},
        )

        api_instance.send_transac_email(email)
        return True

    except ApiException as exc:
        print("Brevo error:", exc)
        return False

    except Exception as exc:
        print("Email error:", exc)
        return False


# ============================================================
# 📱 TELEGRAM
# ============================================================

def send_telegram_message(chat_id, message):
    if not TELEGRAM_BOT_TOKEN or not chat_id:
        return False

    try:
        url = (
            f"https://api.telegram.org/bot"
            f"{TELEGRAM_BOT_TOKEN}/sendMessage"
        )

        response = requests.post(
            url,
            data={
                "chat_id": chat_id,
                "text": message,
            },
            timeout=10,
        )

        response.raise_for_status()
        return True

    except Exception as exc:
        print("Telegram error:", exc)
        return False


def check_telegram_commands(feedstock, temperature, pressure):
    if not TELEGRAM_BOT_TOKEN:
        return

    try:
        url = (
            f"https://api.telegram.org/bot"
            f"{TELEGRAM_BOT_TOKEN}/getUpdates"
        )

        params = {}

        if st.session_state.last_update_id is not None:
            params["offset"] = (
                st.session_state.last_update_id + 1
            )

        response = requests.get(
            url,
            params=params,
            timeout=10,
        ).json()

        if response.get("ok"):
            for update in response.get("result", []):
                st.session_state.last_update_id = update["update_id"]

                if "message" not in update:
                    continue

                chat_id = update["message"]["chat"]["id"]

                text = update["message"].get(
                    "text",
                    "",
                ).lower().strip()

                if "status" in text:
                    log_activity(
                        "Telegram status command received"
                    )

                    reply = (
                        "📊 HEXNN SMART BIOGAS STATUS\n\n"
                        f"Feedstock: {feedstock}%\n"
                        f"Temperature: {temperature}°C\n"
                        f"Pressure: {pressure} kPa"
                    )

                    send_telegram_message(
                        chat_id,
                        reply,
                    )

                elif "predict" in text:
                    log_activity(
                        "Telegram forecast command received"
                    )

                    predicted = predict_biogas(
                        feedstock,
                        temperature,
                    )

                    send_telegram_message(
                        chat_id,
                        f"🔮 Prototype forecast: "
                        f"{predicted:.2f} m³/day",
                    )

                elif "help" in text:
                    log_activity(
                        "Telegram help command received"
                    )

                    send_telegram_message(
                        chat_id,
                        "Commands:\n"
                        "• status\n"
                        "• predict\n"
                        "• help",
                    )

    except Exception as exc:
        print("Telegram read error:", exc)


# ============================================================
# 🚨 ALERTS
# ============================================================

def handle_alert(condition, key, subject, message):
    if not condition:
        return

    current_time = time.time()

    if (
        current_time
        - st.session_state.last_sent_time[key]
        > COOLDOWN
    ):
        c.execute(
            "SELECT DISTINCT email FROM subscribers"
        )

        for (email,) in c.fetchall():
            send_email_alert(
                subject,
                message,
                email,
            )

        send_telegram_message(
            TELEGRAM_CHAT_ID,
            f"{subject}\n{message}",
        )

        log_alert(
            f"{subject} — {message}"
        )

        log_activity(
            f"Alert triggered: {subject}"
        )

        st.session_state.last_sent_time[key] = current_time


# ============================================================
# 🎨 VISUAL SYSTEM
# ============================================================

st.markdown(
    """
    <style>
    .stApp {
        background:
            radial-gradient(circle at 10% 0%, #164f40 0%, transparent 28%),
            radial-gradient(circle at 90% 15%, #0b4437 0%, transparent 25%),
            linear-gradient(145deg, #06130f 0%, #071a15 48%, #04100d 100%);
        color: #ecfff8;
    }

    [data-testid="stHeader"] {
        background: rgba(0,0,0,0);
    }

    .main .block-container {
        max-width: 1450px;
        padding-top: 1.4rem;
        padding-bottom: 2rem;
    }

    [data-testid="stSidebar"] {
        background:
            linear-gradient(180deg, #0a2d25 0%, #061914 100%);
        border-right: 1px solid rgba(93,255,194,.15);
    }

    [data-testid="stSidebar"] * {
        color: #d8f8ed;
    }

    .topbar {
        display:flex;
        justify-content:space-between;
        align-items:center;
        padding:.55rem 1rem;
        margin-bottom:1rem;
        border-bottom:1px solid rgba(100,255,200,.14);
        color:#dffcf1;
        font-weight:700;
    }

    .brand {
        color:#70efbd;
        font-size:1rem;
        letter-spacing:.02em;
    }

    .dashboard-title {
        font-size:1.55rem;
        font-weight:800;
        color:#f0fff9;
        margin:.2rem 0 .15rem;
    }

    .dashboard-subtitle {
        color:#83b7aa;
        font-size:.8rem;
        margin-bottom:1rem;
    }

    .metric-card {
        min-height:108px;
        padding:1rem 1.05rem;
        border-radius:10px;
        border:1px solid rgba(101,255,197,.18);
        background:
            linear-gradient(145deg,
            rgba(23,83,67,.82),
            rgba(5,31,25,.88));
        box-shadow:
            inset 0 1px 0 rgba(255,255,255,.025),
            0 10px 30px rgba(0,0,0,.18);
    }

    .metric-card.alert {
        background:
            linear-gradient(145deg,
            rgba(135,38,55,.94),
            rgba(74,18,29,.92));
        border-color:rgba(255,103,124,.38);
    }

    .metric-card.warning {
        background:
            linear-gradient(145deg,
            rgba(137,104,19,.95),
            rgba(75,53,8,.92));
        border-color:rgba(255,205,73,.4);
    }

    .metric-label {
        color:#86b7aa;
        font-size:.72rem;
        font-weight:700;
        margin-bottom:.4rem;
    }

    .metric-value {
        color:#f4fffb;
        font-size:1.55rem;
        line-height:1;
        font-weight:800;
    }

    .metric-caption {
        color:#6fa798;
        font-size:.66rem;
        margin-top:.45rem;
    }

    .section-title {
        color:#dffcf2;
        font-size:.82rem;
        font-weight:800;
        letter-spacing:.06em;
        text-transform:uppercase;
        margin:1.15rem 0 .55rem;
    }

    .chart-panel {
        background:
            linear-gradient(145deg,
            rgba(15,61,49,.78),
            rgba(4,24,19,.82));
        border:1px solid rgba(89,255,194,.15);
        border-radius:10px;
        padding:.5rem .7rem .1rem;
        box-shadow:0 12px 35px rgba(0,0,0,.16);
    }

    .mini-card {
        background:rgba(11,45,37,.7);
        border:1px solid rgba(90,255,194,.15);
        border-radius:9px;
        padding:.8rem;
        margin-bottom:.55rem;
    }

    .mini-label {
        color:#78ad9e;
        font-size:.68rem;
        text-transform:uppercase;
        letter-spacing:.05em;
    }

    .mini-value {
        color:#effff9;
        font-size:1.05rem;
        font-weight:800;
        margin-top:.2rem;
    }

    .status-online {
        color:#58f0b5;
        font-weight:800;
    }

    .status-monitor {
        color:#ffd75d;
        font-weight:800;
    }

    .status-danger {
        color:#ff7185;
        font-weight:800;
    }

    .activity {
        max-height:145px;
        overflow-y:auto;
        font-family:Consolas,monospace;
        color:#9bcbbd;
        font-size:.72rem;
        line-height:1.9;
    }

    .footer-mark {
        text-align:center;
        color:#547f73;
        font-size:.68rem;
        letter-spacing:.08em;
        padding:1.5rem 0 .5rem;
    }

    div[data-testid="stMetric"] {
        background:rgba(10,47,38,.7);
        border:1px solid rgba(83,255,193,.16);
        border-radius:9px;
    }

    .stButton > button {
        border-radius:7px;
    }

    @media (max-width: 900px) {
        .dashboard-title {
            font-size:1.25rem;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# 🧭 SIDEBAR
# ============================================================

with st.sidebar:
    st.markdown(
        """
        <div style="
            font-size:1.05rem;
            font-weight:800;
            color:#7af0bf;
            margin-bottom:1.2rem;">
            🌱 HEXNN
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("### SYSTEM")
    st.caption("● Online monitoring")
    st.caption("● AI forecast layer")
    st.caption("● Alert services")

    st.markdown("### NAVIGATION")
    page = st.radio(
        "",
        [
            "Dashboard",
            "Controls",
            "Alerts & Subscribe",
        ],
        label_visibility="collapsed",
    )

    st.divider()

    st.caption("HEXNN ENERGY SOLUTIONS")
    st.caption("Smart Biogas System")
    st.caption("Uganda 🇺🇬")


# ============================================================
# 🎛️ INPUTS
# ============================================================

if "feedstock_category" not in st.session_state:
    st.session_state.feedstock_category = "Residue / Waste"

if "feedstock_subtype" not in st.session_state:
    st.session_state.feedstock_subtype = (
        FEEDSTOCK_PROFILES["Residue / Waste"]["items"][0]
    )

apply_feedstock_defaults()

if page == "Controls":
    st.markdown(
        '<div class="dashboard-title">System Controls</div>',
        unsafe_allow_html=True,
    )

    feedstock = st.slider(
        "Feedstock level (%)",
        0,
        100,
        75,
        key="feedstock_control",
    )

    temperature = st.slider(
        "Temperature (°C)",
        20,
        80,
        37,
        key="temperature_control",
    )

    pressure = st.slider(
        "Pressure (kPa)",
        80,
        200,
        110,
        key="pressure_control",
    )

else:
    feedstock = st.slider(
        "Feedstock level (%)",
        0,
        100,
        75,
        key="feedstock_dashboard",
        label_visibility="collapsed",
    )

    temperature = st.slider(
        "Temperature (°C)",
        20,
        80,
        37,
        key="temperature_dashboard",
        label_visibility="collapsed",
    )

    pressure = st.slider(
        "Pressure (kPa)",
        80,
        200,
        110,
        key="pressure_dashboard",
        label_visibility="collapsed",
    )


# ============================================================
# 🌾 FEEDSTOCK PROFILE
# ============================================================

category = st.session_state.feedstock_category
subtype = st.session_state.feedstock_subtype

with st.expander("🌾 Feedstock Intelligence", expanded=False):
    category = st.selectbox(
        "Feedstock category",
        list(FEEDSTOCK_PROFILES),
        key="feedstock_category",
        on_change=apply_feedstock_defaults,
    )

    subtype = st.selectbox(
        "Feedstock type",
        FEEDSTOCK_PROFILES[category]["items"],
        key="feedstock_subtype",
        on_change=apply_feedstock_defaults,
    )

    signature = (category, subtype)

    if st.session_state.feedstock_profile_signature != signature:
        apply_feedstock_defaults()
        st.session_state.feedstock_profile_signature = signature

    cols = st.columns(3)

    with cols[0]:
        moisture = st.number_input(
            "Moisture (%)",
            0.0,
            100.0,
            key="feedstock_moisture",
        )

        cn_ratio = st.number_input(
            "C/N ratio",
            1.0,
            100.0,
            key="feedstock_cn_ratio",
        )

    with cols[1]:
        particle_size = st.number_input(
            "Particle size (mm)",
            0.1,
            50.0,
            key="feedstock_particle_size",
        )

        volatile_solids = st.number_input(
            "Volatile solids (%)",
            0.0,
            100.0,
            key="feedstock_volatile_solids",
        )

    with cols[2]:
        fixed_solids = st.number_input(
            "Fixed solids (%)",
            0.0,
            100.0,
            key="feedstock_fixed_solids",
        )

        energy_content = st.number_input(
            "Energy content",
            0.0,
            50.0,
            key="feedstock_energy_content",
        )

feedstock_properties = {
    "moisture": moisture,
    "cn_ratio": cn_ratio,
    "particle_size": particle_size,
    "volatile_solids": volatile_solids,
    "fixed_solids": fixed_solids,
    "energy_content": energy_content,
}

feedstock_profile = get_feedstock_profile(
    category,
    subtype,
    feedstock_properties,
)


# ============================================================
# 🏭 DIGESTER
# ============================================================

with st.expander("🏭 Biodigester Capacity Intelligence", expanded=False):
    digester_category = st.selectbox(
        "Capacity class",
        list(DIGESTER_PROFILES),
        key="digester_category",
    )

    digester_profile = DIGESTER_PROFILES[digester_category]

    st.caption(
        f"{digester_profile['range']} • "
        f"{digester_profile['minimum']:.1f}–"
        f"{digester_profile['maximum']:.1f} m³/day prototype range"
    )

if "digester_category" not in st.session_state:
    digester_category = "Small scale"
    digester_profile = DIGESTER_PROFILES[digester_category]
else:
    digester_category = st.session_state.digester_category
    digester_profile = DIGESTER_PROFILES[digester_category]


# ============================================================
# 🤖 CALCULATIONS
# ============================================================

prediction = predict_biogas(
    feedstock,
    temperature,
    feedstock_profile,
    digester_profile,
    pressure,
)

digester_metrics = get_digester_metrics(
    digester_category,
    prediction,
)

metrics = calculate_dashboard_metrics(
    feedstock,
    temperature,
    pressure,
    prediction,
    feedstock_profile,
)

risk_level, commentary, recommended_action = get_ai_insight(
    feedstock,
    temperature,
    pressure,
    metrics,
    feedstock_profile,
)

system_stable = (
    feedstock >= 20
    and 25 <= temperature <= 65
    and 90 <= pressure <= 180
)

ai_health = (
    "HEALTHY"
    if metrics["efficiency_score"] >= 70
    and risk_level == "LOW"
    else "MONITORING"
)

reading_signature = (
    feedstock,
    temperature,
    pressure,
    subtype,
    digester_category,
)

if (
    st.session_state.last_reading_signature
    != reading_signature
):
    log_activity(
        "Monitoring values refreshed"
    )
    st.session_state.last_reading_signature = reading_signature


# ============================================================
# 📡 TELEGRAM
# ============================================================

check_telegram_commands(
    feedstock,
    temperature,
    pressure,
)


# ============================================================
# 🚨 ALERTS
# ============================================================

handle_alert(
    feedstock < 20,
    "feedstock",
    "Feedstock Alert",
    f"Low feedstock level: {feedstock}%",
)

handle_alert(
    temperature < 25 or temperature > 65,
    "temperature",
    "Temperature Alert",
    f"Temperature: {temperature}°C",
)

handle_alert(
    pressure < 90 or pressure > 180,
    "pressure",
    "Pressure Alert",
    f"Pressure: {pressure} kPa",
)


# ============================================================
# 📊 DASHBOARD
# ============================================================

if page == "Dashboard":

    st.markdown(
        """
        <div class="topbar">
            <div class="brand">🌱 Hexnn Smart Biogas</div>
            <div>● LIVE MONITORING</div>
        </div>

        <div class="dashboard-title">
            Biogas Monitoring System
        </div>

        <div class="dashboard-subtitle">
            Real-time operational intelligence • Feedstock • Digester • Energy
        </div>
        """,
        unsafe_allow_html=True,
    )

    # -------------------------
    # TOP STATUS CARDS
    # -------------------------

    top = st.columns(4)

    with top[0]:
        st.markdown(
            f"""
            <div class="metric-card {'alert' if metrics['methane_percentage'] < 50 else ''}">
                <div class="metric-label">METHANE PROFILE</div>
                <div class="metric-value">
                    {metrics['methane_percentage']}%
                </div>
                <div class="metric-caption">CH₄ concentration estimate</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with top[1]:
        ph_proxy = max(
            5.5,
            min(
                8.5,
                7.0
                + ((temperature - 37) * 0.025),
            ),
        )

        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-label">DIGESTER CONDITION</div>
                <div class="metric-value">
                    {ph_proxy:.2f}
                </div>
                <div class="metric-caption">
                    indicative dashboard index
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with top[2]:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-label">TEMPERATURE</div>
                <div class="metric-value">
                    {temperature:.1f}°C
                </div>
                <div class="metric-caption">current reading</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with top[3]:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-label">FEEDSTOCK LEVEL</div>
                <div class="metric-value">
                    {feedstock}%
                </div>
                <div class="metric-caption">{subtype}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # -------------------------
    # SECONDARY METRICS
    # -------------------------

    left, right = st.columns([1, 1.65])

    with left:

        st.markdown(
            '<div class="section-title">Live sensor intelligence</div>',
            unsafe_allow_html=True,
        )

        sensor_cards = [
            (
                "🔥 CH₄",
                f"{metrics['methane_percentage']}%",
                "methane profile",
            ),
            (
                "🌡 Temperature",
                f"{temperature:.1f}°C",
                "reactor temperature",
            ),
            (
                "💨 Pressure",
                f"{pressure:.0f} kPa",
                "gas pressure",
            ),
            (
                "📦 Feedstock",
                f"{feedstock}%",
                "available level",
            ),
        ]

        for icon, value, label in sensor_cards:
            st.markdown(
                f"""
                <div class="mini-card">
                    <div class="mini-label">{icon} {label}</div>
                    <div class="mini-value">{value}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    with right:

        st.markdown(
            '<div class="section-title">Production outlook</div>',
            unsafe_allow_html=True,
        )

        # Build lightweight visual history for the current session.
        if not st.session_state.history:
            for i in range(7):
                simulated = max(
                    0.1,
                    prediction * (
                        0.88
                        + (i * 0.018)
                    ),
                )
                st.session_state.history.append(
                    {
                        "period": i,
                        "output": simulated,
                        "temperature": temperature,
                        "pressure": pressure,
                    }
                )

        current_history = st.session_state.history[-7:]

        chart_df = pd.DataFrame(current_history)

        fig = go.Figure()

        fig.add_trace(
            go.Bar(
                x=[
                    "−6",
                    "−5",
                    "−4",
                    "−3",
                    "−2",
                    "−1",
                    "Now",
                ][-len(chart_df):],
                y=chart_df["output"],
                name="Gas output",
                marker_color="#effff8",
                opacity=0.95,
            )
        )

        fig.update_layout(
            height=245,
            margin=dict(l=20, r=15, t=15, b=20),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#9ac5b8", size=10),
            showlegend=False,
            xaxis=dict(
                showgrid=False,
                zeroline=False,
            ),
            yaxis=dict(
                showgrid=True,
                gridcolor="rgba(100,255,200,.08)",
                zeroline=False,
                title="m³/day",
            ),
        )

        st.plotly_chart(
            fig,
            use_container_width=True,
            config={"displayModeBar": False},
        )

    # -------------------------
    # TREND PANEL
    # -------------------------

    st.markdown(
        '<div class="section-title">Operational trends</div>',
        unsafe_allow_html=True,
    )

    trend_col, health_col = st.columns([1.65, 1])

    with trend_col:

        trend_df = pd.DataFrame(
            {
                "Reading": [
                    "−6",
                    "−5",
                    "−4",
                    "−3",
                    "−2",
                    "−1",
                    "Now",
                ],
                "Temperature": [
                    temperature - 1.8,
                    temperature - 1.2,
                    temperature - 1.4,
                    temperature - .4,
                    temperature + .2,
                    temperature + .7,
                    temperature,
                ],
                "Pressure": [
                    pressure + 12,
                    pressure + 17,
                    pressure + 9,
                    pressure + 3,
                    pressure - 5,
                    pressure - 12,
                    pressure,
                ],
            }
        )

        fig2 = go.Figure()

        fig2.add_trace(
            go.Scatter(
                x=trend_df["Reading"],
                y=trend_df["Temperature"],
                name="Temperature",
                mode="lines+markers",
                line=dict(
                    color="#65e7b8",
                    width=2,
                ),
                marker=dict(size=5),
            )
        )

        fig2.add_trace(
            go.Scatter(
                x=trend_df["Reading"],
                y=trend_df["Pressure"],
                name="Pressure",
                mode="lines+markers",
                line=dict(
                    color="#c8d8d2",
                    width=2,
                ),
                marker=dict(size=5),
                yaxis="y2",
            )
        )

        fig2.update_layout(
            height=245,
            margin=dict(l=20, r=20, t=15, b=20),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#9ac5b8", size=10),
            legend=dict(
                orientation="h",
                y=1.12,
                x=0,
            ),
            xaxis=dict(
                showgrid=False,
                zeroline=False,
            ),
            yaxis=dict(
                title="°C",
                showgrid=True,
                gridcolor="rgba(100,255,200,.07)",
            ),
            yaxis2=dict(
                title="kPa",
                overlaying="y",
                side="right",
                showgrid=False,
            ),
        )

        st.plotly_chart(
            fig2,
            use_container_width=True,
            config={"displayModeBar": False},
        )

    with health_col:

        health_class = (
            "status-online"
            if ai_health == "HEALTHY"
            else "status-monitor"
        )

        st.markdown(
            f"""
            <div class="chart-panel">
                <div class="section-title">AI system health</div>

                <div style="
                    font-size:1.35rem;
                    font-weight:800;
                    margin-bottom:.8rem;">
                    <span class="{health_class}">
                        ● {ai_health}
                    </span>
                </div>

                <div class="mini-card">
                    <div class="mini-label">EFFICIENCY</div>
                    <div class="mini-value">
                        {metrics['efficiency_score']}%
                    </div>
                </div>

                <div class="mini-card">
                    <div class="mini-label">FORECAST</div>
                    <div class="mini-value">
                        {prediction:.2f} m³/day
                    </div>
                </div>

                <div class="mini-card">
                    <div class="mini-label">FEEDSTOCK SUITABILITY</div>
                    <div class="mini-value">
                        {metrics['feedstock_suitability']}%
                    </div>
                </div>

                <div class="mini-card">
                    <div class="mini-label">RISK</div>
                    <div class="mini-value">
                        {risk_level}
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # -------------------------
    # BOTTOM KPI STRIP
    # -------------------------

    st.markdown(
        '<div class="section-title">Energy intelligence</div>',
        unsafe_allow_html=True,
    )

    k1, k2, k3, k4 = st.columns(4)

    with k1:
        st.metric(
            "Daily gas",
            f"{metrics['daily_output']:.1f} m³",
        )

    with k2:
        st.metric(
            "Monthly projection",
            f"{metrics['monthly_output']:.0f} m³",
        )

    with k3:
        st.metric(
            "CO₂ estimate",
            f"{metrics['co2_reduction']:.1f} kg",
        )

    with k4:
        st.metric(
            "Energy estimate",
            f"{metrics['energy_savings']:.1f} kWh",
        )

    # -------------------------
    # ACTIVITY
    # -------------------------

    activity_col, status_col = st.columns([1.4, 1])

    with activity_col:
        activity_html = "<br>".join(
            reversed(
                st.session_state.activity_feed
                or ["Awaiting system events..."]
            )
        )

        st.markdown(
            f"""
            <div class="chart-panel">
                <div class="section-title">Live activity</div>
                <div class="activity">
                    {activity_html}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with status_col:
        st.markdown(
            f"""
            <div class="chart-panel">
                <div class="section-title">Current profile</div>

                <div class="mini-label">FEEDSTOCK</div>
                <div class="mini-value">{subtype}</div>

                <div class="mini-label" style="margin-top:.7rem;">
                    DIGESTER
                </div>
                <div class="mini-value">
                    {digester_category}
                </div>

                <div class="mini-label" style="margin-top:.7rem;">
                    LAST REFRESH
                </div>
                <div class="mini-value">
                    {datetime.now().strftime("%H:%M:%S")}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown(
        '<div class="footer-mark">HEXNN ENERGY SOLUTIONS • CLEAN ENERGY INTELLIGENCE</div>',
        unsafe_allow_html=True,
    )


# ============================================================
# 🎛️ CONTROLS PAGE
# ============================================================

elif page == "Controls":

    st.markdown(
        '<div class="dashboard-title">System Controls</div>',
        unsafe_allow_html=True,
    )

    st.info(
        "Prototype control interface. Physical control outputs are "
        "not connected in this software-only deployment."
    )

    st.markdown(
        '<div class="section-title">Feedstock intelligence</div>',
        unsafe_allow_html=True,
    )

    st.write(
        f"**{subtype}** • {category}"
    )

    st.metric(
        "Biochemical suitability",
        f"{feedstock_profile['suitability']}%",
    )

    st.markdown(
        '<div class="section-title">Digester capacity</div>',
        unsafe_allow_html=True,
    )

    st.write(
        f"**{digester_category}** • "
        f"{digester_profile['range']}"
    )

    st.metric(
        "Prototype daily forecast",
        f"{prediction:.2f} m³/day",
    )


# ============================================================
# 🚨 ALERTS & SUBSCRIBE
# ============================================================

elif page == "Alerts & Subscribe":

    st.markdown(
        '<div class="dashboard-title">Alerts & Notifications</div>',
        unsafe_allow_html=True,
    )

    alert_status = (
        "Configured"
        if BREVO_API_KEY and TELEGRAM_BOT_TOKEN
        else "Needs configuration"
    )

    st.metric(
        "Notification services",
        alert_status,
    )

    st.markdown(
        '<div class="section-title">Email subscription</div>',
        unsafe_allow_html=True,
    )

    email_input = st.text_input(
        "Email address",
        placeholder="you@example.com",
    )

    if st.button(
        "Subscribe to alerts",
        use_container_width=True,
    ):
        if email_input and "@" in email_input:
            try:
                c.execute(
                    "INSERT OR IGNORE INTO subscribers (email) VALUES (?)",
                    (email_input.strip(),),
                )
                conn.commit()

                log_activity(
                    "New email alert subscription"
                )

                st.success(
                    "✅ Email alerts enabled."
                )

            except sqlite3.Error as exc:
                st.error(
                    f"Subscription error: {exc}"
                )
        else:
            st.error(
                "Enter a valid email address."
            )

    st.markdown(
        '<div class="section-title">Recent alerts</div>',
        unsafe_allow_html=True,
    )

    if st.session_state.alert_log:
        for log in reversed(
            st.session_state.alert_log[-10:]
        ):
            st.write(log)
    else:
        st.caption("No alerts recorded in this session.")

    st.markdown(
        '<div class="section-title">Service configuration</div>',
        unsafe_allow_html=True,
    )

    st.write(
        f"Brevo: {'● configured' if BREVO_API_KEY else '○ missing'}"
    )

    st.write(
        f"Telegram: {'● configured' if TELEGRAM_BOT_TOKEN else '○ missing'}"
    )

    st.caption(
        "API keys and bot credentials are read from Streamlit "
        "Community Cloud Secrets and are never displayed here."
    )
