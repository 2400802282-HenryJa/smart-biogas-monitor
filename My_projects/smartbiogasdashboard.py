# ============================= 

# SECURITY FIX (SSL) 

# ============================= 

import ssl 

ssl._create_default_https_context = ssl._create_unverified_context 

 

# ============================= 

# IMPORTS 

# ============================= 

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

env_path = Path(__file__).resolve().parent / ".env" 
load_dotenv(dotenv_path=env_path, override=True) 

EMAIL_SENDER = os.getenv("EMAIL_SENDER") 
BREVO_API_KEY = os.getenv("BREVO_API_KEY") 
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") 
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID") 

conn = sqlite3.connect("subscribers.db", check_same_thread=False) 
c = conn.cursor() 
c.execute("""CREATE TABLE IF NOT EXISTS subscribers (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE)""") 
conn.commit() 

if "last_sent_time" not in st.session_state: 
    st.session_state.last_sent_time = {"feedstock": 0, "temperature": 0, "pressure": 0} 
if "alert_log" not in st.session_state: 
    st.session_state.alert_log = [] 
if "last_update_id" not in st.session_state: 
    st.session_state.last_update_id = None 
if "activity_feed" not in st.session_state:
    st.session_state.activity_feed = []

COOLDOWN = 60 

FEEDSTOCK_PROFILES = {
    "Starch-based": {"items": ["Corn", "Wheat", "Barley"], "defaults": {"moisture": 65, "cn_ratio": 28, "particle_size": 4, "volatile_solids": 88, "fixed_solids": 12, "energy_content": 17.5}, "factor": 1.0, "methane": 61},
    "Sugar-based": {"items": ["Sugarcane", "Sugarcane waste", "Sugar beet"], "defaults": {"moisture": 72, "cn_ratio": 24, "particle_size": 3, "volatile_solids": 90, "fixed_solids": 10, "energy_content": 16.8}, "factor": 1.08, "methane": 64},
    "Oil-based": {"items": ["Soybean", "Palm oil", "Used cooking oil"], "defaults": {"moisture": 12, "cn_ratio": 32, "particle_size": 2, "volatile_solids": 94, "fixed_solids": 6, "energy_content": 30.0}, "factor": 1.22, "methane": 68},
    "Residue / Waste": {"items": ["Agricultural residues", "Food waste", "Industrial byproducts"], "defaults": {"moisture": 70, "cn_ratio": 22, "particle_size": 5, "volatile_solids": 85, "fixed_solids": 15, "energy_content": 16.0}, "factor": 1.03, "methane": 62},
    "Lignocellulosic Biomass": {"items": ["Corn stover", "Wood chips", "Switchgrass"], "defaults": {"moisture": 20, "cn_ratio": 45, "particle_size": 8, "volatile_solids": 78, "fixed_solids": 22, "energy_content": 18.5}, "factor": 0.78, "methane": 52},
    "Algae": {"items": ["Microalgae species"], "defaults": {"moisture": 82, "cn_ratio": 10, "particle_size": 1, "volatile_solids": 86, "fixed_solids": 14, "energy_content": 19.0}, "factor": 1.12, "methane": 65},
    "Animal / Organic Waste": {
        "items": ["Cow dung", "Goat dung", "Pig dung", "Poultry droppings", "Human excreta", "Water hyacinth"],
        "defaults": {"moisture": 80, "cn_ratio": 18, "particle_size": 8, "volatile_solids": 75, "fixed_solids": 25, "energy_content": 15.0}, "factor": 0.85, "methane": 58,
        "item_profiles": {
            "Cow dung": {"moisture": 80, "cn_ratio": 18, "particle_size": 8, "volatile_solids": 75, "fixed_solids": 25, "energy_content": 15.0, "factor": 0.85, "methane": 58},
            "Goat dung": {"moisture": 72, "cn_ratio": 16, "particle_size": 8, "volatile_solids": 78, "fixed_solids": 22, "energy_content": 16.0, "factor": 0.9, "methane": 60},
            "Pig dung": {"moisture": 82, "cn_ratio": 14, "particle_size": 8, "volatile_solids": 80, "fixed_solids": 20, "energy_content": 16.5, "factor": 0.95, "methane": 61},
            "Poultry droppings": {"moisture": 65, "cn_ratio": 10, "particle_size": 5, "volatile_solids": 82, "fixed_solids": 18, "energy_content": 17.5, "factor": 1.1, "methane": 65},
            "Human excreta": {"moisture": 78, "cn_ratio": 8, "particle_size": 5, "volatile_solids": 70, "fixed_solids": 30, "energy_content": 14.5, "factor": 0.9, "methane": 57},
            "Water hyacinth": {"moisture": 90, "cn_ratio": 25, "particle_size": 8, "volatile_solids": 60, "fixed_solids": 40, "energy_content": 12.0, "factor": 0.65, "methane": 54},
        },
    },
}
def apply_feedstock_defaults():
    """Refresh editable property fields when the feedstock category changes."""
    category_profile = FEEDSTOCK_PROFILES[st.session_state.feedstock_category]
    subtype = st.session_state.get("feedstock_subtype")
    defaults = category_profile.get("item_profiles", {}).get(subtype, category_profile["defaults"])
    for property_name, value in defaults.items():
        st.session_state[f"feedstock_{property_name}"] = value


DIGESTER_PROFILES = {
    "Small scale": {"range": "2-4 m³", "size": 3, "minimum": 0.8, "maximum": 1.5},
    "Medium": {"range": "5-10 m³", "size": 7.5, "minimum": 2.0, "maximum": 3.0},
    "Farm scale": {"range": "15-25 m³", "size": 20, "minimum": 5.0, "maximum": 8.0},
    "Community farm": {"range": "30-50 m³", "size": 40, "minimum": 10.0, "maximum": 25.0},
    "Industrial": {"range": "100+ m³", "size": 100, "minimum": 40.0, "maximum": 80.0},
}


def get_feedstock_profile(category, subtype, properties):
    """Build normalized categorical and biochemical features for the prototype model."""
    profile = FEEDSTOCK_PROFILES[category].get("item_profiles", {}).get(subtype, FEEDSTOCK_PROFILES[category])
    normalized = {
        "moisture": max(0, min(100, properties["moisture"])) / 100,
        "cn_ratio": max(0, min(60, properties["cn_ratio"])) / 60,
        "particle_size": max(0, min(20, properties["particle_size"])) / 20,
        "volatile_solids": max(0, min(100, properties["volatile_solids"])) / 100,
        "fixed_solids": max(0, min(100, properties["fixed_solids"])) / 100,
        "energy_content": max(0, min(40, properties["energy_content"])) / 40,
    }
    category_encoding = {name: int(name == category) for name in FEEDSTOCK_PROFILES}
    suitability = round(max(0, min(100, (normalized["volatile_solids"] * 45) + (normalized["energy_content"] * 25) + ((1 - abs(normalized["cn_ratio"] - .37)) * 30))))
    return {"category": category, "subtype": subtype, "category_encoding": category_encoding, "normalized": normalized, "suitability": suitability, "factor": profile["factor"], "methane": profile["methane"]}


def get_digester_metrics(digester_category, prediction):
    """Compare the forecast with a realistic output range for plant capacity."""
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

 

# ============================= 

# 🔧 HELPERS SECTION (IMPORTANT) 

# ============================= 

 

def log_alert(message): 

    """Store alert history""" 

    timestamp = datetime.now().strftime("%H:%M:%S") 

    st.session_state.alert_log.append(f"{timestamp} - {message}") 


def log_activity(message):
    """Keep a lightweight, session-only activity stream for the dashboard."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    st.session_state.activity_feed.append(f"{timestamp}  |  {message}")
    st.session_state.activity_feed = st.session_state.activity_feed[-12:]


def calculate_dashboard_metrics(feedstock, temperature, pressure, prediction, feedstock_profile=None):
    """Calculate prototype investor metrics from the live sensor values."""
    temperature_stability = max(0, 100 - abs(37 - temperature) * 4)
    pressure_stability = max(0, 100 - abs(110 - pressure) * 0.8)
    suitability = feedstock_profile["suitability"] if feedstock_profile else 75
    efficiency_score = round((temperature_stability * 0.55) + (pressure_stability * 0.3) + (suitability * 0.15))
    operational_stability = round((temperature_stability + pressure_stability + feedstock) / 3)
    return {
        "daily_output": prediction,
        "monthly_output": prediction * 30,
        "co2_reduction": prediction * 1.8,
        "energy_savings": prediction * 0.6,
        "efficiency_score": min(100, efficiency_score),
        "operational_stability": min(100, round(operational_stability)),
        "methane_percentage": feedstock_profile["methane"] if feedstock_profile else 60,
        "feedstock_suitability": suitability,
    }


def get_ai_insight(feedstock, temperature, pressure, metrics, feedstock_profile=None):
    """Return a simple explainable insight based on the current readings."""
    if feedstock < 20:
        return "LOW", "Substrate levels may reduce gas yield within 24 hours.", "Add feedstock soon"
    if temperature < 30 or temperature > 40:
        return "MEDIUM", "Temperature drift detected. Recommend heat stabilization.", "Stabilize digester heat"
    if pressure < 90 or pressure > 180:
        return "MEDIUM", "Pressure instability detected. Inspect gas handling pathways.", "Inspect pressure controls"
    if feedstock_profile and feedstock_profile["category"] == "Oil-based":
        return "LOW", "Oil-rich feedstock detected. Higher methane potential expected.", "Monitor loading rate"
    if metrics["efficiency_score"] >= 85:
        return "LOW", "System operating in optimal methane generation range.", "Continue current operation"
    return "MEDIUM", "Operating conditions are usable, but efficiency can be improved.", "Monitor next refresh"

 

 

def send_email_alert(subject, body, receiver): 

    """Send email via Brevo""" 

    try: 

        configuration = sib_api_v3_sdk.Configuration() 

        configuration.api_key['api-key'] = BREVO_API_KEY 

 

        api_instance = sib_api_v3_sdk.TransactionalEmailsApi( 

            sib_api_v3_sdk.ApiClient(configuration) 

        ) 

 

        email = sib_api_v3_sdk.SendSmtpEmail( 

            to=[{"email": receiver}], 

            subject=subject, 

            html_content=f"<h3>{body}</h3>", 

            sender={"email": EMAIL_SENDER} 

        ) 

 

        api_instance.send_transac_email(email) 

 

    except ApiException as e: 

        print("Email error:", e) 

 

 

def send_telegram_message(chat_id, message): 

    """Send Telegram message""" 

    if not TELEGRAM_BOT_TOKEN: 

        return 

 

    try: 

        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage" 

        requests.post(url, data={"chat_id": chat_id, "text": message}) 

    except Exception as e: 

        print("Telegram error:", e) 

 

 

def check_telegram_commands(feedstock, temperature, pressure): 

    """ 

    Read Telegram messages and respond 

    """ 

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

 

                    # 📊 STATUS COMMAND 

                    if "status" in text: 
                        log_activity("Telegram status command received")

                        reply = f""" 

📊 BIOGAS SYSTEM STATUS 

 

Feedstock: {feedstock}% 

Temperature: {temperature}°C 

Pressure: {pressure} kPa 

""" 

                        send_telegram_message(chat_id, reply) 

 

                    # 🤖 AI FORECAST COMMAND 

                    elif "predict" in text: 
                        log_activity("Telegram forecast command received")

                        predicted = predict_biogas(feedstock, temperature) 

                        reply = f"🔮 Predicted Biogas Output: {predicted:.2f} m³/day" 

                        send_telegram_message(chat_id, reply) 

 

                    elif "help" in text: 
                        log_activity("Telegram help command received")

                        send_telegram_message( 

                            chat_id, 

                            "Commands:\n- status\n- predict\n- help" 

                        ) 

 

    except Exception as e: 

        print("Telegram read error:", e) 

 

 

# ============================= 

# 🤖 SIMPLE AI MODEL (PROTOTYPE) 

# ============================= 

def predict_biogas(feedstock, temperature, feedstock_profile=None, digester_profile=None, pressure=None): 

    """ 

    Simple AI logic (can be upgraded later) 

    """ 

    efficiency = 0.8 if 30 <= temperature <= 40 else 0.5 

    base_prediction = feedstock * efficiency
    if feedstock_profile is None:
        return base_prediction
    moisture_factor = 1 - abs(feedstock_profile["normalized"]["moisture"] - .7) * .18
    solids_factor = .85 + (feedstock_profile["normalized"]["volatile_solids"] * .2)
    forecast = base_prediction * feedstock_profile["factor"] * moisture_factor * solids_factor
    if digester_profile is not None:
        forecast *= digester_profile["size"] / 100
    if pressure is not None:
        forecast *= max(0.75, 1 - abs(110 - pressure) * 0.002)
    return forecast

 

 

# ============================= 

# 🚨 ALERT HANDLER 

# ============================= 

def handle_alert(condition, key, subject, message): 

    if condition: 

        st.warning(f"⚠️ {subject}") 

 

        current_time = time.time() 

 

        if (current_time - st.session_state.last_sent_time[key]) > COOLDOWN: 

            c.execute("SELECT DISTINCT email FROM subscribers") 

 

            for (email,) in c.fetchall(): 

                send_email_alert(subject, message, email) 

 

            send_telegram_message(TELEGRAM_CHAT_ID, f"{subject}\n{message}") 

            log_alert(f"{subject} - {message}") 
            log_activity(f"Alert triggered: {subject}")

 

            st.session_state.last_sent_time[key] = current_time 

 

 

# ============================= 

# 🎨 STREAMLIT UI CONFIG 

# ============================= 

st.set_page_config(page_title="Smart Biogas Monitor", layout="centered") 

st.markdown("""
<style>
.stApp {background: radial-gradient(circle at 15% 0%, #123f35 0, #071311 38%, #050908 100%); color: #e8fff8;}
.main .block-container {max-width: 1240px; padding-top: 2.5rem;}
[data-testid="stMetric"] {background: rgba(13, 45, 39, .72); border: 1px solid rgba(68, 255, 194, .28); border-radius: 8px; padding: 1rem; box-shadow: 0 0 24px rgba(25, 224, 163, .08); transition: transform .2s ease, border-color .2s ease, box-shadow .2s ease; animation: fade-in .55s ease both;}
[data-testid="stMetric"]:hover {transform: translateY(-4px); border-color: #4dffc5; box-shadow: 0 0 26px rgba(25, 224, 163, .24);}
[data-testid="stMetricLabel"] {color: #8cb8ad;}
[data-testid="stMetricValue"] {color: #effff9;}
.glass-panel {background: linear-gradient(135deg, rgba(17, 61, 51, .78), rgba(5, 22, 19, .72)); border: 1px solid rgba(68, 255, 194, .3); border-radius: 8px; padding: 1.15rem 1.3rem; margin: .6rem 0 1.2rem; box-shadow: inset 0 0 24px rgba(68, 255, 194, .035), 0 10px 35px rgba(0, 0, 0, .2); animation: fade-in .6s ease both;}
.panel-kicker {color: #60e8bd; font-size: .73rem; letter-spacing: .12em; text-transform: uppercase; font-weight: 700;}
.section-label {color: #b5e8d8; font-size: .82rem; font-weight: 700; margin: 1.1rem 0 .45rem; padding-left: .2rem; border-left: 2px solid #47f5bb;}
.ai-terminal {border-left: 3px solid #47f5bb; font-family: Consolas, monospace; color: #bdfbe8;}
.ai-commentary {background: rgba(0, 15, 12, .6); border: 1px solid rgba(71, 245, 187, .2); border-radius: 5px; padding: .75rem; margin-top: .8rem; color: #e8fff8;}
.activity-feed {max-height: 180px; overflow-y: auto; color: #a5d6c7; font: .8rem Consolas, monospace; line-height: 1.8;}
.pulse {display: inline-block; width: 9px; height: 9px; border-radius: 50%; background: #49f5b9; box-shadow: 0 0 0 rgba(73, 245, 185, .7); animation: pulse 1.8s infinite; margin-right: .45rem;}
.footer-mark {border-top: 1px solid rgba(68, 255, 194, .2); margin-top: 2.5rem; padding: 1.2rem 0; color: #7fb5a5; text-align: center; letter-spacing: .08em; font-size: .78rem;}
.stExpander {background: rgba(13, 45, 39, .42); border: 1px solid rgba(68, 255, 194, .22); border-radius: 8px; transition: border-color .2s ease, box-shadow .2s ease;}
.stExpander:hover {border-color: rgba(68, 255, 194, .55); box-shadow: 0 0 22px rgba(25, 224, 163, .1);}
@keyframes pulse {0% {box-shadow: 0 0 0 0 rgba(73, 245, 185, .55);} 70% {box-shadow: 0 0 0 8px rgba(73, 245, 185, 0);} 100% {box-shadow: 0 0 0 0 rgba(73, 245, 185, 0);}}
@keyframes fade-in {from {opacity: 0; transform: translateY(7px);} to {opacity: 1; transform: translateY(0);}}
@media (max-width: 700px) {.main .block-container {padding: 1.2rem .8rem;} .glass-panel {padding: .9rem;}}
</style>
""", unsafe_allow_html=True)

 

st.markdown(""" 

<style> 

body {background-color: #0E1117;} 

.main {color: #FAFAFA;} 

h1, h2, h3 {color: #00FFAA;} 

</style> 

""", unsafe_allow_html=True) 

 

# ============================= 

# 🏷️ HEADER 

# ============================= 

st.title("🌱 Smart Biogas Monitoring Dashboard") 

st.write("✅ System running...") 

 

# ============================= 

# 🎛️ SENSOR INPUTS 

# ============================= 

col1, col2, col3 = st.columns(3) 

 

with col1: 

    feedstock = st.slider("Feedstock (%)", 0, 100, 75) 

with col2: 

    temperature = st.slider("Temperature (°C)", 20, 80, 37) 

 

with col3: 

    pressure = st.slider("Pressure (kPa)", 80, 200, 110) 

# =============================
# FEEDSTOCK INTELLIGENCE INPUTS
# =============================
if "feedstock_category" not in st.session_state:
    st.session_state.feedstock_category = "Residue / Waste"
    apply_feedstock_defaults()

st.markdown('<div class="panel-kicker">Advanced AI settings / substrate profile</div>', unsafe_allow_html=True)
with st.expander("Feedstock Intelligence Module", expanded=False):
    category = st.selectbox("Feedstock category", list(FEEDSTOCK_PROFILES), key="feedstock_category", on_change=apply_feedstock_defaults)
    subtype = st.selectbox("Feedstock type", FEEDSTOCK_PROFILES[category]["items"], key="feedstock_subtype", on_change=apply_feedstock_defaults)
    profile_signature = (category, subtype)
    if st.session_state.get("feedstock_profile_signature") != profile_signature:
        selected_defaults = FEEDSTOCK_PROFILES[category].get("item_profiles", {}).get(subtype, FEEDSTOCK_PROFILES[category]["defaults"])
        for property_name, value in selected_defaults.items():
            if property_name in {"factor", "methane"}:
                continue
            st.session_state[f"feedstock_{property_name}"] = value
        st.session_state.feedstock_profile_signature = profile_signature
    st.caption("Recommended values are loaded automatically and can be overridden for lab or field measurements.")
    property_columns = st.columns(3)
    with property_columns[0]:
        moisture = st.number_input("Moisture content (%)", 0.0, 100.0, key="feedstock_moisture")
        cn_ratio = st.number_input("Carbon / Nitrogen ratio", 1.0, 100.0, key="feedstock_cn_ratio")
    with property_columns[1]:
        particle_size = st.number_input("Particle size (mm)", 0.1, 50.0, key="feedstock_particle_size")
        volatile_solids = st.number_input("Volatile solids (%)", 0.0, 100.0, key="feedstock_volatile_solids")
    with property_columns[2]:
        fixed_solids = st.number_input("Fixed solids (%)", 0.0, 100.0, key="feedstock_fixed_solids")
        energy_content = st.number_input("Energy content (MJ/kg HHV/LHV)", 0.0, 50.0, key="feedstock_energy_content")
    if category == "Oil-based":
        st.text_input("Fatty acid composition", "Oleic 45% / Linoleic 35% / Other 20%")

feedstock_properties = {
    "moisture": moisture,
    "cn_ratio": cn_ratio,
    "particle_size": particle_size,
    "volatile_solids": volatile_solids,
    "fixed_solids": fixed_solids,
    "energy_content": energy_content,
}
feedstock_profile = get_feedstock_profile(category, subtype, feedstock_properties)

# =============================
# BIODIGESTER SIZE INTELLIGENCE
# =============================
st.markdown('<div class="panel-kicker">Plant intelligence / capacity model</div>', unsafe_allow_html=True)
with st.expander("Biodigester Size Intelligence", expanded=False):
    digester_category = st.selectbox("Biodigester capacity class", list(DIGESTER_PROFILES), key="digester_category")
    digester_profile = DIGESTER_PROFILES[digester_category]
    st.caption(f"Typical capacity: {digester_profile['range']} | Expected output: {digester_profile['minimum']:.1f}-{digester_profile['maximum']:.1f} m³/day")
feedstock_profile["feature_vector"] = list(feedstock_profile["category_encoding"].values()) + list(feedstock_profile["normalized"].values()) + [digester_profile["size"] / 100, temperature / 80, pressure / 200, feedstock / 100]

 

# 🔥 TELEGRAM CHECK (AFTER VALUES EXIST) 

check_telegram_commands(feedstock, temperature, pressure) 

 

# ============================= 

# 📊 DATA DISPLAY 

# ============================= 

st.subheader("📊 Current Readings") 

 

data = pd.DataFrame({ 

    "Feedstock": [feedstock], 

    "Temperature": [temperature], 

    "Pressure": [pressure] 

}) 

 

st.write(data) 

st.line_chart(data) 

 

# ============================= 

# 🤖 AI FORECAST DISPLAY 
prediction = predict_biogas(feedstock, temperature, feedstock_profile, digester_profile, pressure)
digester_metrics = get_digester_metrics(digester_category, prediction)
metrics = calculate_dashboard_metrics(feedstock, temperature, pressure, prediction, feedstock_profile)
reading_signature = (feedstock, temperature, pressure)
if st.session_state.get("last_reading_signature") != reading_signature:
    log_activity("Prediction refreshed from live sensor readings")
    st.session_state.last_reading_signature = reading_signature

# =============================
# INVESTOR SUMMARY KPI PANEL
# =============================
st.markdown('<div class="panel-kicker">Investor summary / live model output</div>', unsafe_allow_html=True)
st.markdown('<div class="section-label">Production outlook</div>', unsafe_allow_html=True)
production_columns = st.columns(2)
with production_columns[0]:
    st.metric("🔥 Estimated daily gas", f"{metrics['daily_output']:.1f} m³", "live forecast")
with production_columns[1]:
    st.metric("📦 Estimated monthly output", f"{metrics['monthly_output']:.0f} m³", "30-day projection")
st.markdown('<div class="section-label">Environmental and economic impact</div>', unsafe_allow_html=True)
impact_columns = st.columns(2)
impact_kpis = [
    ("🌍 CO₂ reduction", f"{metrics['co2_reduction']:.1f} kg", "equivalent estimate"),
    ("⚡ Energy savings", f"{metrics['energy_savings']:.1f} kWh", "recovery estimate"),
]
for impact_column, (label, value, help_text) in zip(impact_columns, impact_kpis):
    with impact_column:
        st.metric(label, value, help_text)

st.markdown('<div class="section-label">System quality and stability</div>', unsafe_allow_html=True)
quality_columns = st.columns(3)
quality_kpis = [
    ("◈ Efficiency score", f"{metrics['efficiency_score']} / 100", "thermal + feedstock"),
    ("◉ Operational stability", f"{metrics['operational_stability']}%", "live confidence"),
    ("🫧 Methane quality", f"{metrics['methane_percentage']}%", "profile estimate"),
]
for quality_column, (label, value, help_text) in zip(quality_columns, quality_kpis):
    with quality_column:
        st.metric(label, value, help_text)

st.markdown(
    f'<div class="glass-panel"><div class="panel-kicker">Feedstock intelligence profile</div>'
    f'<strong>{feedstock_profile["category"]} / {feedstock_profile["subtype"]}</strong>'
    f'<br><span>Biochemical suitability: {feedstock_profile["suitability"]}%</span>'
    f'<br><span>Feature encoding: {len(feedstock_profile["category_encoding"])} category vectors + 6 normalized properties</span>'
    f'<br><span class="panel-kicker">Feedstock efficiency: {"HIGH" if feedstock_profile["suitability"] >= 75 else "MEDIUM" if feedstock_profile["suitability"] >= 50 else "LOW"}</span></div>',
    unsafe_allow_html=True,
)

capacity_state = "within optimal range" if digester_metrics["within_range"] else "above typical range"
capacity_message = "System operating within optimal biodigester capacity range." if digester_metrics["within_range"] else "Projected yield exceeds typical output range for selected biodigester capacity."
capacity_column, regional_column = st.columns(2)
with capacity_column:
    st.markdown(
        f'<div class="glass-panel"><div class="panel-kicker">Biodigester capacity</div>'
        f'<strong>{digester_metrics["category"]} / {digester_metrics["range"]}</strong>'
        f'<br>Expected output: {digester_metrics["minimum"]:.1f}-{digester_metrics["maximum"]:.1f} m³/day'
        f'<br>Current utilization: {digester_metrics["utilization"]}% ({capacity_state})</div>',
        unsafe_allow_html=True,
    )
with regional_column:
    regional_message = "Water hyacinth utilization contributes to invasive species reduction and renewable energy generation." if feedstock_profile["subtype"] == "Water hyacinth" else "Locally available organic feedstock supports resilient renewable energy generation."
    st.markdown(f'<div class="glass-panel"><div class="panel-kicker">Regional sustainability insight</div>{regional_message}</div>', unsafe_allow_html=True)

st.markdown(
    f'<div class="glass-panel"><div class="panel-kicker">AI capacity insight</div>'
    f'{"System operating within optimal biodigester capacity range." if digester_metrics["within_range"] else "Projected yield exceeds typical output range for selected biodigester capacity."}'
    f'<br>Forecast realism: {digester_metrics["utilization"]}% of the selected capacity ceiling.</div>',
    unsafe_allow_html=True,
)

# =============================
# AI FORECAST INSIGHT PANEL
# =============================
risk_level, commentary, recommended_action = get_ai_insight(feedstock, temperature, pressure, metrics, feedstock_profile)
health_rating = "OPTIMAL" if metrics["efficiency_score"] >= 85 else "MONITOR"
confidence = min(99, max(42, round(metrics["operational_stability"] * .92)))
st.markdown('<div class="glass-panel ai-terminal"><div class="panel-kicker">◉ AI forecast console</div><h3>Digester intelligence layer</h3>', unsafe_allow_html=True)
insight_columns = st.columns(4)
with insight_columns[0]:
    st.write(f"**Forecast confidence**  \n{confidence}%")
with insight_columns[1]:
    st.write(f"**Digester health**  \n{health_rating}")
with insight_columns[2]:
    st.write(f"**Recommended action**  \n{recommended_action}")
with insight_columns[3]:
    st.write(f"**Predicted risk**  \n{risk_level}")
st.markdown(f'<div class="ai-commentary">&gt; AI COMMENTARY: {commentary}</div></div>', unsafe_allow_html=True)

# =============================
# LIVE SYSTEM ACTIVITY FEED
# =============================
activity_column, status_column = st.columns([1.5, 1])
with activity_column:
    st.markdown('<div class="glass-panel"><div class="panel-kicker">Live system activity</div>', unsafe_allow_html=True)
    activity_html = "<div class='activity-feed'>" + "<br>".join(reversed(st.session_state.activity_feed or ["Awaiting system events..."])) + "</div>"
    st.markdown(activity_html + "</div>", unsafe_allow_html=True)
with status_column:
    ai_health = "HEALTHY" if metrics["efficiency_score"] >= 70 and risk_level == "LOW" else "MONITORING"
    st.markdown(f'<div class="glass-panel"><div class="panel-kicker">Live AI system health</div><h3><span class="pulse"></span>{ai_health}</h3><div>Efficiency: {metrics["efficiency_score"]}%</div><div>Forecast: {metrics["daily_output"]:.1f} m³/day</div><div>Last refresh: {datetime.now().strftime("%H:%M:%S")}</div></div>', unsafe_allow_html=True)

# ============================= 

st.subheader("🔮 AI Biogas Prediction") 

 

st.success(f"Estimated Production: {prediction:.2f} m³/day") 

 

# ============================= 

# 🧠 SYSTEM STATUS 

# ============================= 

if feedstock >= 20 and 25 <= temperature <= 65 and 90 <= pressure <= 180: 

    st.success("🟢 SYSTEM STABLE") 

elif feedstock >= 20 and 25 <= temperature <= 65 and (pressure < 90 or pressure > 180):

    st.warning("🟠 PRESSURE ALERT SENT") 

else: 

    st.error("🔴 ATTENTION REQUIRED") 

 

# ============================= 

# 📜 ALERT HISTORY 

# ============================= 

st.subheader("📜 Alert History") 

 

if st.session_state.alert_log: 

    for log in reversed(st.session_state.alert_log[-5:]): 

        st.write(log) 

else: 

    st.write("No alerts yet.") 

 

# ============================= 

# 🚨 ALERT CONDITIONS 

# ============================= 

handle_alert(feedstock < 20, "feedstock", "Feedstock Alert", f"Low: {feedstock}%") 

handle_alert(temperature < 25 or temperature > 65, "temperature", "Temp Alert", f"{temperature}°C") 

handle_alert(pressure < 90 or pressure > 180, "pressure", "Pressure Alert", f"{pressure} kPa") 

 

# ============================= 

# 📩 SUBSCRIBE 

# ============================= 

st.subheader("📩 Get Email Alerts") 

 

email_input = st.text_input("Enter your email") 

 

if st.button("Subscribe"): 

    if email_input: 

        c.execute("INSERT OR IGNORE INTO subscribers (email) VALUES (?)", (email_input,)) 

        conn.commit() 

        log_activity("New email alert subscription")
        st.success("✅ Subscribed!") 

    else: 

        st.error("Enter email") 

 

# ============================= 

# 📌 SIDEBAR 

# ============================= 

st.sidebar.title("⚙️ System Info") 
st.sidebar.write("Project: Hexnn Smart Biogas System") 

st.sidebar.write("Location: Uganda 🇺🇬") 

st.sidebar.write("Status: Prototype Phase") 
st.markdown('<div class="footer-mark">POWERED BY HEXNN ENERGY SOLUTIONS &nbsp;•&nbsp; CLEAN ENERGY INTELLIGENCE</div>', unsafe_allow_html=True)

 
