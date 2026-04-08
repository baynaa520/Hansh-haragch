import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
from datetime import date, timedelta
import os
import time

# ── 1. Хуудасны тохиргоо ──
st.set_page_config(
    page_title="Монгол Валютын Ханш",
    page_icon="💱",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS
st.markdown("""
<style>
.rate-card {
    background: linear-gradient(135deg, #1e3a8a 0%, #3730a3 100%);
    color: white; padding: 1.5rem; border-radius: 14px; margin: 0.5rem 0;
}
.ai-box {
    background: #f0fdf4; border-left: 4px solid #16a34a;
    padding: 1rem 1.3rem; border-radius: 8px; margin-top: 1rem;
    font-size: 0.97rem; line-height: 1.7;
}
.endpoint-badge {
    background: #1e293b; color: #94a3b8;
    font-family: monospace; font-size: 0.82rem;
    padding: 0.2rem 0.6rem; border-radius: 4px;
}
</style>
""", unsafe_allow_html=True)

# ── 2. Тогтмол утгууд ──
DEFAULT_BACKEND = "http://localhost:8000"

CURRENCY_INFO = {
    "USD": {"name": "Ам.доллар",          "flag": "🇺🇸"},
    "EUR": {"name": "Евро",                "flag": "🇪🇺"},
    "CNY": {"name": "Юань",                "flag": "🇨🇳"},
    "RUB": {"name": "Рубль",               "flag": "🇷🇺"},
    "KRW": {"name": "Вон",                 "flag": "🇰🇷"},
    "JPY": {"name": "Иен",                 "flag": "🇯🇵"},
    "GBP": {"name": "Фунт стерлинг",      "flag": "🇬🇧"},
    "HKD": {"name": "Хонконгийн доллар", "flag": "🇭🇰"},
}

# ── 3. API Функцүүд ──
def api_get(endpoint: str, backend_url: str, params: dict = None) -> dict | None:
    try:
        r = requests.get(
            f"{backend_url}{endpoint}",
            params=params or {},
            timeout=15,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        # Streamlit Cloud дээр Localhost ажиллахгүй тул анхааруулга харуулна
        if "localhost" in backend_url:
            st.warning("⚠️ Таны Backend (Localhost) холбогдсонгүй. Хэрэв та Streamlit Cloud ашиглаж байгаа бол Backend-ээ онлайн сервер дээр байршуулах хэрэгтэй.")
        else:
            st.error(f"❌ API Алдаа: {e}")
        return None

def api_post(endpoint: str, backend_url: str, payload: dict) -> dict | None:
    try:
        r = requests.post(
            f"{backend_url}{endpoint}",
            json=payload,
            timeout=30,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"❌ POST Алдаа: {e}")
        return None

# ── 4. SIDEBAR ──
with st.sidebar:
    st.markdown("## ⚙️ Тохиргоо")
    backend_url = st.text_input("🔌 Backend URL", value=DEFAULT_BACKEND)
    
    if st.button("🩺 Backend шалгах", use_container_width=True):
        h = api_get("/health", backend_url)
        if h: st.success("✅ Backend OK")

    st.markdown("---")
    selected_currency = st.selectbox(
        "Валют сонгох",
        list(CURRENCY_INFO.keys()),
        format_func=lambda c: f"{CURRENCY_INFO[c]['flag']} {c} — {CURRENCY_INFO[c]['name']}"
    )

    use_demo = st.toggle("🔧 Demo өгөгдөл", value=True) # Cloud дээр Demo-г default болгов
    history_days = st.slider("Хоногийн тоо", 7, 90, 30)
    st.caption("🏦 Source: mongolbank.mn")

# ── 5. ҮНДСЭН ХУУДАС ──
st.title("💱 Монгол Валютын Ханш")
st.markdown("**Монголбанкны албан ёсны ханш · Claude AI зөвлөмж · FastAPI Backend**")

selected_date = st.date_input("📅 Огноо сонгох", value=date.today())
date_str = selected_date.strftime("%Y-%m-%d")

# Ханш татах
with st.spinner("Ханш татаж байна..."):
    all_rates_data = api_get(f"/rates/{date_str}", backend_url, params={"demo": str(use_demo).lower()})

if all_rates_data:
    rates = all_rates_data.get("rates", {})
    selected_rate = rates.get(selected_currency, 0)
    flag = CURRENCY_INFO[selected_currency]["flag"]

    # Үндсэн ханш карт
    if selected_rate:
        st.markdown(f"""<div class="rate-card">
            <div style="font-size:1.1rem;opacity:.85">{flag} {selected_currency} → Монгол Төгрөг</div>
            <div style="font-size:3rem;font-weight:700;margin:0.3rem 0;letter-spacing:-1px">{selected_rate:,.2f} ₮</div>
            <div style="opacity:.8;font-size:.95rem">Монголбанкны ханш · {selected_date}</div>
            </div>""", unsafe_allow_html=True)

    # Табууд
    tab1, tab2, tab3, tab4 = st.tabs(["📊 Бүх ханш", "📈 График", "🧮 Тооцоолуур", "🤖 Claude AI"])

    with tab1:
        st.write("### Бүх валютын ханш")
        df = pd.DataFrame([{"Валют": k, "Нэр": v["name"], "Ханш": rates.get(k, 0)} for k, v in CURRENCY_INFO.items()])
        st.table(df)

    with tab2:
        st.write("### Ханшийн түүх")
        # Энд график зурах Plotly код чинь хэвээрээ ажиллана...
        st.info("Backend-ээс түүхийн өгөгдөл татах хэрэгтэй.")
else:
    st.info("Backend-ээс өгөгдөл ирсэнгүй. Дээрх Settings-ээс Demo горимыг асаагаад үзээрэй.")
