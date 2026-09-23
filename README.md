# 🌱 Hexnn Smart Biogas System

### AI-Powered • IoT-Ready • Sustainable Biogas Monitoring & Intelligence Platform

Hexnn Smart Biogas System is a smart monitoring and decision-support platform designed to improve the visibility, management, and optimization of biogas production.

The platform combines real-time operational monitoring, feedstock intelligence, predictive analytics, alerts, and a future-ready IoT architecture into one system.

It is being developed as part of the broader **Hexnn Energy Solutions** ecosystem, with a focus on affordable and sustainable energy solutions for Uganda and East Africa.

---

## 🚀 Project Vision

Hexnn aims to develop an intelligent biogas ecosystem that connects:

**Organic Waste → Feedstock Intelligence → Anaerobic Digestion → Biogas → Energy → Data & Optimization**

The long-term vision is to combine software, IoT sensors, AI, analytics, and digital-twin technologies to make biogas systems easier to monitor, understand, and optimize.

---

## 🎯 The Problem

Biogas systems can be difficult to monitor consistently, particularly where operators rely on manual observations.

Important operating conditions such as:

- Feedstock availability
- Temperature
- Pressure
- Gas production
- Methane concentration
- Historical performance

can change over time.

Without centralized monitoring and historical data, identifying abnormal conditions and understanding system performance becomes more difficult.

Hexnn Smart Biogas is being developed to provide a digital monitoring and intelligence layer around the biogas system.

---

# 💡 Core Features

## 📊 Real-Time Monitoring

The dashboard provides monitoring of key operational parameters including:

- Feedstock level
- Digester temperature
- Gas pressure
- Estimated biogas production

The interface is designed to provide a quick operational overview.

---

## 🧠 AI / Predictive Analytics

The current prototype includes production forecasting and analytical insights based on system inputs.

Current prototype analytics include:

- Estimated daily biogas production
- Monthly production projection
- Energy-value estimation
- CO₂-reduction estimation
- Operational efficiency indicators
- System-health interpretation
- AI-generated recommendations

> **Important:** Current predictive calculations are prototype models and have not yet been validated against field measurements. Future versions will incorporate calibrated engineering models and real sensor data.

---

## 🌾 Feedstock Intelligence

Different organic feedstocks can behave differently in anaerobic digestion.

The platform therefore supports feedstock classification and characteristics such as:

- Feedstock category
- Feedstock subtype
- Moisture
- C/N ratio
- Particle size
- Volatile solids
- Fixed solids
- Energy content
- Methane-content assumptions
- Feedstock suitability indicators

The system is being expanded to better represent feedstocks relevant to Uganda and East Africa, including:

- Cow dung
- Goat dung
- Pig manure
- Poultry waste
- Food waste
- Agricultural residues
- Crop residues
- Water hyacinth
- Other organic wastes

Prototype values are used for development and demonstration and should not be interpreted as laboratory-validated feedstock characteristics.

---

# ⚙️ Digester Profiles

The prototype supports different digester-scale profiles, including:

| Scale | Prototype Volume Range |
|---|---|
| Small scale | 2–4 m³ |
| Medium | 5–10 m³ |
| Farm scale | 15–25 m³ |
| Community farm | 30–50 m³ |
| Industrial | 100+ m³ |

These profiles are currently used for software prototyping and will be refined using engineering design calculations and field data.

---

# 🚨 Smart Alerts

The system can monitor operating conditions and generate alerts when configured thresholds are exceeded.

Current alert areas include:

### Feedstock
Low feedstock conditions.

### Temperature
Temperature outside the configured operating range.

### Pressure
Pressure outside the configured monitoring range.

Alerts can be delivered through:

- 📧 Email
- 📱 Telegram

Alert cooldown mechanisms are included to reduce repeated notifications.

---

# 📧 Email Notifications

Email notifications are integrated using **Brevo's transactional email API**.

Credentials are NOT stored in the GitHub repository.

For deployment, sensitive configuration is stored through **Streamlit Community Cloud Secrets**.

Expected secret variables include:

```text
EMAIL_SENDER
BREVO_API_KEY
TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID
