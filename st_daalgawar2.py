"""
╔══════════════════════════════════════════════════════╗
║   Монголбанкны Валютын Ханш + Claude AI Зөвлөмж     ║
╚══════════════════════════════════════════════════════╝
Ажиллуулах: streamlit run app.py
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import date, datetime, timedelta
import json
import os
from anthropic import Anthropic

# ── Хуудасны тохиргоо ──
st.set_page_config(
    page_title="Монгол Валютын Ханш",
    page_icon="💱",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ──
st.markdown("""
<style>
    .main { padding: 0rem 1rem; }
    .stMetric { background: #f8f9fa; padding: 1rem; border-radius: 10px; }
    .rate-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white; padding: 1.5rem; border-radius: 12px; margin: 0.5rem 0;
    }
    .ai-box {
        background: #f0f7ff; border-left: 4px solid #2563eb;
        padding: 1rem 1.2rem; border-radius: 8px; margin-top: 1rem;
    }
    .currency-flag { font-size: 1.5rem; }
    div[data-testid="stSidebarContent"] { background: #1e293b; color: white; }
</style>
""", unsafe_allow_html=True)


# ──────────────────────────────────────────────
# ӨГӨГДӨЛ: Монголбанкны ханш татах
# ──────────────────────────────────────────────

CURRENCY_INFO = {
    "USD": {"name": "Ам.доллар",     "flag": "🇺🇸", "unit": 1},
    "EUR": {"name": "Евро",           "flag": "🇪🇺", "unit": 1},
    "CNY": {"name": "Юань",           "flag": "🇨🇳", "unit": 1},
    "RUB": {"name": "Рубль",          "flag": "🇷🇺", "unit": 100},
    "KRW": {"name": "Вон",            "flag": "🇰🇷", "unit": 100},
    "JPY": {"name": "Иен",            "flag": "🇯🇵", "unit": 100},
    "GBP": {"name": "Фунт стерлинг", "flag": "🇬🇧", "unit": 1},
    "HKD": {"name": "Хонконгийн доллар", "flag": "🇭🇰", "unit": 1},
}


@st.cache_data(ttl=3600)  # 1 цагт нэг удаа шинэчлэх
def fetch_mongolbank_rates(target_date: date) -> dict:
    """
    Монголбанкны вэбсайтаас ханш татах.
    
    mongolbank.mn нь HTML хуудас ашигладаг тул
    requests + BeautifulSoup ашиглан скрэйп хийнэ.
    """
    import requests
    from bs4 import BeautifulSoup

    date_str = target_date.strftime("%Y-%m-%d")

    # Монголбанкны ханшийн хуудас URL
    url = "https://www.mongolbank.mn/mn/currency-rates"
    
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "mn,en-US;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Referer": "https://www.mongolbank.mn/",
    }

    try:
        # Тухайн өдрийн ханшийн POST хүсэлт
        # mongolbank.mn нь query parameter ашигладаг
        params = {"date": date_str}
        response = requests.get(url, headers=headers, params=params, timeout=15)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "lxml")

        # Ханшийн хүснэгт хайх
        rates = {}
        table = soup.find("table")
        
        if table:
            rows = table.find_all("tr")
            for row in rows:
                cols = row.find_all(["td", "th"])
                if len(cols) >= 3:
                    currency_code = cols[0].get_text(strip=True).upper()
                    try:
                        rate_text = cols[-1].get_text(strip=True)
                        rate_text = rate_text.replace(",", "").replace(" ", "")
                        rate = float(rate_text)
                        if currency_code in CURRENCY_INFO and rate > 0:
                            rates[currency_code] = rate
                    except (ValueError, IndexError):
                        continue

        if rates:
            return {"success": True, "rates": rates, "date": date_str, "source": "mongolbank.mn"}

        # Хүснэгтээс олдоогүй бол JSON endpoint туршиж үзэх
        json_url = "https://www.mongolbank.mn/api/UserAPI/GetCurrencyList"
        resp2 = requests.get(json_url, headers=headers, params=params, timeout=10)
        if resp2.status_code == 200:
            data = resp2.json()
            for item in data:
                code = item.get("CurrencyCode", "").upper()
                rate = item.get("CloseRate") or item.get("Rate")
                if code in CURRENCY_INFO and rate:
                    rates[code] = float(rate)
            if rates:
                return {"success": True, "rates": rates, "date": date_str, "source": "mongolbank API"}

        return {"success": False, "error": "Ханш олдсонгүй", "rates": {}}

    except requests.exceptions.ConnectionError:
        return {"success": False, "error": "Интернэт холболт алдаатай байна", "rates": {}}
    except requests.exceptions.Timeout:
        return {"success": False, "error": "Хүсэлтийн хугацаа дууслаа (timeout)", "rates": {}}
    except Exception as e:
        return {"success": False, "error": str(e), "rates": {}}


@st.cache_data(ttl=3600)
def fetch_rate_history(currency: str, days: int = 30) -> pd.DataFrame:
    """
    Өнгөрсөн N хоногийн ханшийн түүх татах.
    Монголбанкны ханшийн хөдөлгөөн хуудсаас татна.
    """
    import requests
    from bs4 import BeautifulSoup

    end_date = date.today()
    start_date = end_date - timedelta(days=days)

    url = "https://www.mongolbank.mn/mn/currency-rate-movement"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0",
        "Accept": "text/html,*/*",
        "Referer": "https://www.mongolbank.mn/",
    }
    params = {
        "startDate": start_date.strftime("%Y-%m-%d"),
        "endDate": end_date.strftime("%Y-%m-%d"),
        "currencyCode": currency,
    }

    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)
        soup = BeautifulSoup(response.text, "lxml")

        records = []
        table = soup.find("table")
        if table:
            rows = table.find_all("tr")[1:]  # Header алгасах
            for row in rows:
                cols = row.find_all("td")
                if len(cols) >= 2:
                    try:
                        date_val = pd.to_datetime(cols[0].get_text(strip=True))
                        rate_text = cols[-1].get_text(strip=True).replace(",", "")
                        rate_val = float(rate_text)
                        records.append({"date": date_val, "rate": rate_val})
                    except (ValueError, IndexError):
                        continue

        if records:
            df = pd.DataFrame(records).sort_values("date")
            return df

    except Exception:
        pass

    # Fallback: simulate historical data based on current known rates
    return pd.DataFrame()


def get_demo_rates(target_date: date) -> dict:
    """
    Demo өгөгдөл — API байхгүй үед ашиглах.
    2026 оны 4 сарын ойролцоо утгууд.
    """
    import random
    random.seed(target_date.toordinal())  # Тухайн өдөрт тогтмол

    base_rates = {
        "USD": 3570.0,
        "EUR": 3920.0,
        "CNY": 491.5,
        "RUB": 42.5,      # 100 рублийн ханш
        "KRW": 258.0,     # 100 вонны ханш
        "JPY": 238.0,     # 100 иений ханш
        "GBP": 4640.0,
        "HKD": 459.0,
    }

    # Хэдэн хоног ялгаа нэмэх (бодит хэлбэлзэл дуурайх)
    days_diff = (target_date - date(2026, 4, 8)).days
    
    rates = {}
    for code, base in base_rates.items():
        # Жижиг хэлбэлзэл нэмэх
        variation = random.uniform(-0.008, 0.008)
        trend = days_diff * 0.0002  # Аажим өөрчлөлт
        rates[code] = round(base * (1 + variation + trend), 2)

    return {"success": True, "rates": rates, "date": target_date.strftime("%Y-%m-%d"), "source": "Demo (API холбогдоогүй)"}


@st.cache_data(ttl=3600)
def get_rates_for_date(target_date: date) -> dict:
    """Тухайн өдрийн ханш авах (бодит + fallback)"""
    result = fetch_mongolbank_rates(target_date)
    if result["success"] and result["rates"]:
        return result
    # Fallback to demo
    return get_demo_rates(target_date)


# ──────────────────────────────────────────────
# CLAUDE AI ЗӨВЛӨМЖ
# ──────────────────────────────────────────────

def get_claude_analysis(
    currency: str,
    selected_date: date,
    current_rate: float,
    history_data: list,
    api_key: str,
) -> str:
    """
    Claude-аас ханшийн дүн шинжилгээ, зөвлөмж авах.
    """
    client = Anthropic(api_key=api_key)

    # Түүхийн мэдээллийг бэлдэх
    history_summary = ""
    if history_data:
        rates = [d["rate"] for d in history_data[-14:]]  # Сүүлийн 14 хоног
        min_r = min(rates)
        max_r = max(rates)
        avg_r = sum(rates) / len(rates)
        trend = "өссөн" if rates[-1] > rates[0] else "буурсан"
        history_summary = (
            f"Сүүлийн 14 хоногийн мэдээлэл:\n"
            f"- Хамгийн бага: {min_r:,.2f}₮\n"
            f"- Хамгийн их: {max_r:,.2f}₮\n"
            f"- Дундаж: {avg_r:,.2f}₮\n"
            f"- Чиглэл: {trend}\n"
        )

    currency_name = CURRENCY_INFO.get(currency, {}).get("name", currency)
    
    prompt = f"""Та Монголын валютын зах зээлийн мэргэжилтэн юм.

Доорх мэдээллийг үндэслэн товч, практик зөвлөмж өгнө үү:

📅 Огноо: {selected_date.strftime("%Y оны %m сарын %d")}
💱 Валют: {currency} ({currency_name})
💰 Монголбанкны ханш: {current_rate:,.2f} төгрөг

{history_summary}

Дараах зүйлсийг тусгана уу (нийт 200-250 үг):
1. Ханшийн одоогийн байдлын үнэлгээ
2. Чиглэлийн богино хугацааны таамаглал
3. Хэрэглэгчид практик зөвлөмж (худалдах уу? хүлээх үү?)
4. Ямар нөлөөлөх хүчин зүйлс анхаарах вэ?

Монгол хэлээр, тодорхой, ойлгомжтой бичнэ үү. Санхүүгийн мэргэжлийн нэр томьёог хялбаршуулж тайлбарлана уу."""

    try:
        message = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text
    except Exception as e:
        return f"⚠️ Claude API алдаа: {str(e)}\n\nAPI түлхүүрийг шалгаарай."


# ──────────────────────────────────────────────
# SIDEBAR — Тохиргоо
# ──────────────────────────────────────────────

with st.sidebar:
    st.markdown("## ⚙️ Тохиргоо")
    st.markdown("---")

    # API Key
    st.markdown("### 🔑 Claude API Key")
    api_key = st.text_input(
        "Anthropic API key оруулна уу",
        type="password",
        placeholder="sk-ant-...",
        help="https://console.anthropic.com/ дээрээс авна уу",
    )

    if not api_key:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")

    if api_key:
        st.success("✅ API key тохируулагдсан")
    else:
        st.warning("⚠️ API key оруулаагүй\n(Зөвлөмжийн хэсэг ажиллахгүй)")

    st.markdown("---")
    
    # Валют сонголт
    st.markdown("### 💱 Валют сонгох")
    selected_currency = st.selectbox(
        "Валют",
        list(CURRENCY_INFO.keys()),
        format_func=lambda c: f"{CURRENCY_INFO[c]['flag']} {c} — {CURRENCY_INFO[c]['name']}",
    )

    st.markdown("---")

    # Мэдээллийн эх сурвалж
    st.markdown("### 📡 Мэдээллийн эх сурвалж")
    data_source = st.radio(
        "Эх сурвалж",
        ["🏦 Монголбанк (бодит)", "🔧 Demo өгөгдөл"],
        help="Монголбанк: mongolbank.mn-с шууд татна\nDemo: Тест өгөгдөл",
    )
    use_demo = "Demo" in data_source

    st.markdown("---")
    
    # Хугацааны мужийн тохиргоо
    st.markdown("### 📈 График")
    history_days = st.slider("Өнгөрсөн хоног", 7, 90, 30)
    
    st.markdown("---")
    st.markdown("**Хийсэн:** Python + Streamlit + Claude AI")
    st.markdown("**Эх сурвалж:** mongolbank.mn")


# ──────────────────────────────────────────────
# ҮНДСЭН ХУУДАС
# ──────────────────────────────────────────────

st.title("💱 Монгол Валютын Ханш")
st.markdown("**Монголбанкны албан ёсны ханш • Claude AI зөвлөмж**")
st.markdown("---")

# Огноо сонгогч
col_date, col_info = st.columns([2, 3])

with col_date:
    st.markdown("### 📅 Огноо сонгох")
    selected_date = st.date_input(
        "Огноо",
        value=date.today(),
        min_value=date(2020, 1, 1),
        max_value=date.today(),
        label_visibility="collapsed",
    )

with col_info:
    st.markdown("### 📌 Чухал мэдээлэл")
    st.info(
        f"📅 Сонгосон огноо: **{selected_date.strftime('%Y оны %m сарын %d')}**\n\n"
        f"💱 Сонгосон валют: **{CURRENCY_INFO[selected_currency]['flag']} {selected_currency} — "
        f"{CURRENCY_INFO[selected_currency]['name']}**"
    )

st.markdown("---")

# ── Өгөгдөл татах ──
with st.spinner("Монголбанкны ханш татаж байна..."):
    if use_demo:
        rates_data = get_demo_rates(selected_date)
    else:
        rates_data = get_rates_for_date(selected_date)

# ── Эх сурвалжийн мэдэгдэл ──
source = rates_data.get("source", "Тодорхойгүй")
if "Demo" in source:
    st.warning(
        f"⚠️ **Demo өгөгдөл ашиглаж байна** — "
        f"mongolbank.mn руу холбогдох боломжгүй байна. "
        f"Аппыг өөрийн компьютер дээр ажиллуулахад бодит өгөгдөл татагдана."
    )
else:
    st.success(f"✅ Эх сурвалж: **{source}**")

# ── Үндсэн ханш карт ──
if rates_data["rates"]:
    selected_rate = rates_data["rates"].get(selected_currency, 0)
    unit = CURRENCY_INFO[selected_currency]["unit"]
    flag = CURRENCY_INFO[selected_currency]["flag"]
    cname = CURRENCY_INFO[selected_currency]["name"]

    # Том карт
    st.markdown(
        f"""<div class="rate-card">
        <h2>{flag} {selected_currency} → Монгол Төгрөг</h2>
        <h1 style="font-size:3rem; margin:0.5rem 0">
            {selected_rate:,.2f} ₮
        </h1>
        <p style="opacity:0.85; margin:0">
            {unit} {cname} = {selected_rate:,.2f} Монгол төгрөг
            <br>{selected_date.strftime("%Y.%m.%d")} — Монголбанкны ханш
        </p>
        </div>""",
        unsafe_allow_html=True,
    )

    # ── Бүх валютын хүснэгт ──
    st.markdown("### 📊 Бүх валютын ханш")

    rate_rows = []
    for code, info in CURRENCY_INFO.items():
        r = rates_data["rates"].get(code)
        if r:
            rate_rows.append({
                "Валют": f"{info['flag']} {code}",
                "Нэр": info["name"],
                "Нэгж": f"{info['unit']} {code}",
                "Ханш (₮)": f"{r:,.2f}",
                "1 ₮ → валют": f"{info['unit']/r:.6f}",
            })

    df_rates = pd.DataFrame(rate_rows)
    
    # Сонгосон валютыг тодруулах
    def highlight_selected(row):
        code = row["Валют"].split()[-1]
        if code == selected_currency:
            return ["background-color: #dbeafe"] * len(row)
        return [""] * len(row)

    st.dataframe(
        df_rates.style.apply(highlight_selected, axis=1),
        use_container_width=True,
        hide_index=True,
    )

    # ── Ханшийн график ──
    st.markdown("### 📈 Ханшийн хөдөлгөөн")

    # Demo мод дахь түүхэн өгөгдлийг бэлдэх
    history_records = []
    for i in range(history_days, 0, -1):
        hist_date = selected_date - timedelta(days=i)
        if hist_date.weekday() < 5:  # Ажлын өдрүүд
            if use_demo:
                hist_data = get_demo_rates(hist_date)
            else:
                hist_data = get_rates_for_date(hist_date)
            r = hist_data["rates"].get(selected_currency, 0)
            if r > 0:
                history_records.append({"date": hist_date, "rate": r})

    if history_records:
        df_hist = pd.DataFrame(history_records)

        # Plotly график
        fig = go.Figure()

        fig.add_trace(go.Scatter(
            x=df_hist["date"],
            y=df_hist["rate"],
            mode="lines+markers",
            name=f"{selected_currency}/MNT",
            line=dict(color="#2563eb", width=2.5),
            marker=dict(size=4),
            fill="tozeroy",
            fillcolor="rgba(37,99,235,0.08)",
        ))

        # Дундаж шугам
        avg = df_hist["rate"].mean()
        fig.add_hline(
            y=avg, line_dash="dash", line_color="orange",
            annotation_text=f"Дундаж: {avg:,.2f}₮",
            annotation_position="top right",
        )

        # Тухайн өдрийг тэмдэглэх
        sel_rows = df_hist[df_hist["date"] == selected_date]
        if not sel_rows.empty:
            fig.add_vline(
                x=selected_date, line_dash="dash", line_color="red",
                annotation_text="Сонгосон өдөр",
            )

        fig.update_layout(
            title=f"{flag} {selected_currency} — Сүүлийн {history_days} хоногийн ханш",
            xaxis_title="Огноо",
            yaxis_title="Ханш (₮)",
            hovermode="x unified",
            height=420,
            plot_bgcolor="white",
            paper_bgcolor="white",
            xaxis=dict(gridcolor="#f1f5f9"),
            yaxis=dict(gridcolor="#f1f5f9"),
        )

        st.plotly_chart(fig, use_container_width=True)

        # Статистик
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Хамгийн бага", f"{df_hist['rate'].min():,.2f}₮")
        with col2:
            st.metric("Хамгийн их", f"{df_hist['rate'].max():,.2f}₮")
        with col3:
            st.metric("Дундаж", f"{df_hist['rate'].mean():,.2f}₮")
        with col4:
            change = df_hist["rate"].iloc[-1] - df_hist["rate"].iloc[0]
            st.metric("Өөрчлөлт", f"{change:+,.2f}₮",
                      delta=f"{change/df_hist['rate'].iloc[0]*100:+.2f}%")

    # ── Тооцоолуур ──
    st.markdown("---")
    st.markdown("### 🧮 Валют тооцоолуур")

    col_calc1, col_calc2 = st.columns(2)
    with col_calc1:
        st.markdown(f"**{flag} {cname} → Төгрөг**")
        foreign_amount = st.number_input(
            f"{selected_currency} дүн", min_value=0.0, value=100.0, step=10.0,
            key="foreign_input",
        )
        if selected_rate > 0:
            togrog_result = foreign_amount * selected_rate / unit
            st.success(f"**{foreign_amount:,.2f} {selected_currency} = {togrog_result:,.2f} ₮**")

    with col_calc2:
        st.markdown(f"**Төгрөг → {flag} {cname}**")
        togrog_amount = st.number_input(
            "Төгрөг дүн", min_value=0.0, value=100000.0, step=1000.0,
            key="togrog_input",
        )
        if selected_rate > 0:
            foreign_result = togrog_amount / selected_rate * unit
            st.success(f"**{togrog_amount:,.0f} ₮ = {foreign_result:,.4f} {selected_currency}**")

    # ── CLAUDE AI ЗӨВЛӨМЖ ──
    st.markdown("---")
    st.markdown("### 🤖 Claude AI Зөвлөмж")

    if not api_key:
        st.warning(
            "🔑 Claude AI зөвлөмж авахын тулд зүүн дээд буланд **API key** оруулна уу.\n\n"
            "API key авах: [console.anthropic.com](https://console.anthropic.com/)"
        )
    else:
        analyze_btn = st.button(
            f"🤖 Claude-аас {selected_currency} ханшийн зөвлөмж авах",
            type="primary",
            use_container_width=True,
        )

        if analyze_btn:
            with st.spinner("Claude дүн шинжилгээ хийж байна..."):
                analysis = get_claude_analysis(
                    currency=selected_currency,
                    selected_date=selected_date,
                    current_rate=selected_rate,
                    history_data=history_records,
                    api_key=api_key,
                )

            st.markdown(
                f'<div class="ai-box"><strong>🤖 Claude AI дүн шинжилгээ — '
                f'{selected_date.strftime("%Y.%m.%d")} • {selected_currency}</strong>'
                f'<hr style="margin:0.5rem 0">{analysis.replace(chr(10), "<br>")}</div>',
                unsafe_allow_html=True,
            )

            # Татаж авах
            st.download_button(
                "📥 Зөвлөмжийг татаж авах (.txt)",
                data=f"Огноо: {selected_date}\nВалют: {selected_currency}\nХанш: {selected_rate:,.2f}₮\n\n{analysis}",
                file_name=f"hansh_zuwlumj_{selected_date}_{selected_currency}.txt",
                mime="text/plain",
            )

else:
    st.error(
        f"❌ **{selected_date} өдрийн ханш олдсонгүй.**\n\n"
        f"Боломжит шалтгаан:\n"
        f"- Амралтын өдөр (Монголбанк ажлын өдрүүдэд ханш зарладаг)\n"
        f"- Интернэт холболтын асуудал\n\n"
        f"Өөр огноо сонгоно уу эсвэл Demo горим ашиглана уу."
    )

# ── Footer ──
st.markdown("---")
st.markdown(
    "<div style='text-align:center; color:#94a3b8; font-size:0.85rem'>"
    "📊 Эх сурвалж: mongolbank.mn • 🤖 AI: Anthropic Claude • "
    "🛠 Хийсэн: Streamlit + Python"
    "</div>",
    unsafe_allow_html=True,
)