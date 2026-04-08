"""
╔══════════════════════════════════════════════════════════╗
║   Монгол Валютын Ханш — Streamlit Frontend               ║
║   FastAPI backend-тай холбогдсон хувилбар                ║
╚══════════════════════════════════════════════════════════╝
Ажиллуулах:
    # Эхлээд backend:
    uvicorn main:app --reload --port 8000

    # Дараа нь frontend:
    streamlit run app.py
"""

import subprocess, sys

_pkgs = {"streamlit": "streamlit", "requests": "requests",
         "pandas": "pandas", "plotly": "plotly"}
for mod, pkg in _pkgs.items():
    try:
        __import__(mod)
   
import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
from datetime import date, timedelta
import os

# ── Тохиргоо ──
st.set_page_config(
    page_title="Монгол Валютын Ханш",
    page_icon="💱",
    layout="wide",
    initial_sidebar_state="expanded",
)

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

# ── Backend URL ──
DEFAULT_BACKEND = "http://localhost:8000"

CURRENCY_INFO = {
    "USD": {"name": "Ам.доллар",          "flag": "🇺🇸"},
    "EUR": {"name": "Евро",               "flag": "🇪🇺"},
    "CNY": {"name": "Юань",               "flag": "🇨🇳"},
    "RUB": {"name": "Рубль",              "flag": "🇷🇺"},
    "KRW": {"name": "Вон",                "flag": "🇰🇷"},
    "JPY": {"name": "Иен",                "flag": "🇯🇵"},
    "GBP": {"name": "Фунт стерлинг",     "flag": "🇬🇧"},
    "HKD": {"name": "Хонконгийн доллар", "flag": "🇭🇰"},
}


# ══════════════════════════════════════════════
# BACKEND API ДУУДАХ ФУНКЦҮҮД
# ══════════════════════════════════════════════

def api_get(endpoint: str, backend_url: str, params: dict = None) -> dict | None:
    """Backend API-г дуудах ерөнхий функц"""
    try:
        r = requests.get(
            f"{backend_url}{endpoint}",
            params=params or {},
            timeout=15,
        )
        r.raise_for_status()
        return r.json()
    except requests.exceptions.ConnectionError:
        st.error(
            f"❌ **Backend холбогдсонгүй!**\n\n"
            f"Backend ажиллуулна уу:\n```\nuvicorn main:app --reload --port 8000\n```"
        )
        return None
    except requests.exceptions.HTTPError as e:
        detail = ""
        try:
            detail = e.response.json().get("detail", "")
        except Exception:
            pass
        st.warning(f"⚠️ API алдаа: {detail or str(e)}")
        return None
    except Exception as e:
        st.error(f"❌ Тодорхойгүй алдаа: {e}")
        return None


def api_post(endpoint: str, backend_url: str, payload: dict) -> dict | None:
    """Backend POST хүсэлт"""
    try:
        r = requests.post(
            f"{backend_url}{endpoint}",
            json=payload,
            timeout=30,
        )
        r.raise_for_status()
        return r.json()
    except requests.exceptions.ConnectionError:
        st.error("❌ Backend холбогдсонгүй. `uvicorn main:app --reload` ажиллуулна уу.")
        return None
    except requests.exceptions.HTTPError as e:
        detail = ""
        try:
            detail = e.response.json().get("detail", "")
        except Exception:
            pass
        st.warning(f"⚠️ {detail or str(e)}")
        return None
    except Exception as e:
        st.error(f"❌ {e}")
        return None


# ══════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════

with st.sidebar:
    st.markdown("## ⚙️ Тохиргоо")

    # Backend URL
    backend_url = st.text_input(
        "🔌 Backend URL",
        value=DEFAULT_BACKEND,
        help="FastAPI backend-ийн хаяг",
    )

    # Health check
    if st.button("🩺 Backend шалгах", use_container_width=True):
        h = api_get("/health", backend_url)
        if h:
            st.success(f"✅ Backend ажиллаж байна\n\n"
                       f"Mongolbank: {h.get('mongolbank_api','?')}\n\n"
                       f"Claude: {h.get('claude_api','?')}")

    st.markdown("---")

    # Валют сонголт
    st.markdown("### 💱 Валют")
    selected_currency = st.selectbox(
        "Валют сонгох",
        list(CURRENCY_INFO.keys()),
        format_func=lambda c: f"{CURRENCY_INFO[c]['flag']} {c} — {CURRENCY_INFO[c]['name']}",
        label_visibility="collapsed",
    )

    st.markdown("---")

    # Demo горим
    use_demo = st.toggle("🔧 Demo өгөгдөл", value=False,
                         help="Backend монголбанк.mn-д хүрч чадахгүй бол идэвхжүүлнэ")

    # Графикийн хоног
    st.markdown("### 📈 График")
    history_days = st.slider("Хоногийн тоо", 7, 90, 30)

    st.markdown("---")
    st.caption("🏦 Эх сурвалж: mongolbank.mn\n🤖 AI: Claude claude-opus-4-5\n🛠 FastAPI + Streamlit")


# ══════════════════════════════════════════════
# ҮНДСЭН ХУУДАС
# ══════════════════════════════════════════════

st.title("💱 Монгол Валютын Ханш")
st.markdown("**Монголбанкны албан ёсны ханш · Claude AI зөвлөмж · FastAPI Backend**")

# Огноо сонгогч
col_a, col_b = st.columns([1, 2])
with col_a:
    selected_date = st.date_input(
        "📅 Огноо сонгох",
        value=date.today(),
        min_value=date(2020, 1, 1),
        max_value=date.today(),
    )

date_str = selected_date.strftime("%Y-%m-%d")
flag = CURRENCY_INFO[selected_currency]["flag"]
cname = CURRENCY_INFO[selected_currency]["name"]

# ── Бүх ханш татах ──
with st.spinner("Ханш татаж байна..."):
    all_rates_data = api_get(
        f"/rates/{date_str}",
        backend_url,
        params={"demo": str(use_demo).lower()},
    )

if not all_rates_data:
    st.stop()

rates = all_rates_data.get("rates", {})
source = all_rates_data.get("source", "")
is_demo = all_rates_data.get("is_demo", False)

# Эх сурвалж
if is_demo:
    st.warning(f"⚠️ Demo өгөгдөл — эх сурвалж: {source}")
else:
    st.success(f"✅ {source}")

# ── Үндсэн ханш карт ──
selected_rate = rates.get(selected_currency, 0)

if selected_rate:
    st.markdown(
        f"""<div class="rate-card">
        <div style="font-size:1.1rem;opacity:.85">{flag} {selected_currency} → Монгол Төгрөг</div>
        <div style="font-size:3rem;font-weight:700;margin:0.3rem 0;letter-spacing:-1px">
            {selected_rate:,.2f} ₮
        </div>
        <div style="opacity:.8;font-size:.95rem">
            Монголбанкны ханш · {selected_date.strftime("%Y.%m.%d")}
        </div>
        </div>""",
        unsafe_allow_html=True,
    )

st.markdown("---")

# ── Табууд ──
tab1, tab2, tab3, tab4 = st.tabs([
    "📊 Бүх ханш", "📈 График", "🧮 Тооцоолуур", "🤖 Claude AI"
])


# ─── ТАБ 1: Бүх ханш ───
with tab1:
    st.markdown("### 📊 Монголбанкны ханш")
    rows = []
    for code, info in CURRENCY_INFO.items():
        r = rates.get(code)
        if r:
            rows.append({
                "Валют": f"{info['flag']} {code}",
                "Нэр": info["name"],
                "Ханш (₮)": f"{r:,.2f}",
            })

    df = pd.DataFrame(rows)

    def highlight(row):
        code = row["Валют"].split()[-1]
        return ["background-color:#dbeafe; font-weight:600"] * len(row) \
            if code == selected_currency else [""] * len(row)

    st.dataframe(
        df.style.apply(highlight, axis=1),
        use_container_width=True,
        hide_index=True,
    )

    # Endpoint харуулах
    st.markdown(
        f'<span class="endpoint-badge">GET {backend_url}/rates/{date_str}</span>',
        unsafe_allow_html=True,
    )


# ─── ТАБ 2: График ───
with tab2:
    st.markdown(f"### 📈 {flag} {selected_currency} — Сүүлийн {history_days} хоног")

    with st.spinner("Түүх татаж байна..."):
        hist_data = api_get(
            f"/history/{selected_currency}",
            backend_url,
            params={"days": history_days, "demo": str(use_demo).lower()},
        )

    if hist_data and hist_data.get("records"):
        records = hist_data["records"]
        df_hist = pd.DataFrame(records)
        df_hist["date"] = pd.to_datetime(df_hist["date"])

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df_hist["date"], y=df_hist["rate"],
            mode="lines+markers",
            name=f"{selected_currency}/MNT",
            line=dict(color="#2563eb", width=2.5),
            marker=dict(size=4, color="#1d4ed8"),
            fill="tozeroy",
            fillcolor="rgba(37,99,235,0.07)",
            hovertemplate="%{x|%Y.%m.%d}<br><b>%{y:,.2f} ₮</b><extra></extra>",
        ))

        avg = hist_data["average"]
        fig.add_hline(
            y=avg, line_dash="dash", line_color="#f59e0b",
            annotation_text=f"Дундаж: {avg:,.2f}₮",
            annotation_position="top right",
        )

        fig.update_layout(
            xaxis_title="Огноо", yaxis_title="Ханш (₮)",
            hovermode="x unified", height=420,
            plot_bgcolor="white", paper_bgcolor="white",
            xaxis=dict(gridcolor="#f1f5f9"),
            yaxis=dict(gridcolor="#f1f5f9"),
            showlegend=False,
        )
        st.plotly_chart(fig, use_container_width=True)

        # Статистик
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Хамгийн бага", f"{hist_data['min']:,.2f}₮")
        c2.metric("Хамгийн их", f"{hist_data['max']:,.2f}₮")
        c3.metric("Дундаж", f"{hist_data['average']:,.2f}₮")
        change = hist_data["change"]
        pct = hist_data["change_pct"]
        c4.metric("Өөрчлөлт", f"{change:+,.2f}₮", delta=f"{pct:+.2f}%")
    else:
        st.info("Графикийн өгөгдөл олдсонгүй.")

    st.markdown(
        f'<span class="endpoint-badge">GET {backend_url}/history/{selected_currency}?days={history_days}</span>',
        unsafe_allow_html=True,
    )


# ─── ТАБ 3: Тооцоолуур ───
with tab3:
    st.markdown("### 🧮 Валют хөрвүүлэх")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"**{flag} {cname} → Төгрөг**")
        foreign_amt = st.number_input(
            f"{selected_currency} дүн", min_value=0.0, value=100.0, step=10.0, key="f2m"
        )
        if st.button("Хөрвүүлэх →", key="btn_f2m", use_container_width=True):
            res = api_get("/convert", backend_url, params={
                "from": selected_currency, "to": "MNT",
                "amount": foreign_amt, "date": date_str,
                "demo": str(use_demo).lower(),
            })
            if res:
                st.success(
                    f"**{foreign_amt:,.2f} {selected_currency} "
                    f"= {res['result']:,.2f} ₮**"
                )
                st.caption(f"Ханш: {res['rate']:,.2f} ₮/{selected_currency}")

    with col2:
        st.markdown(f"**Төгрөг → {flag} {cname}**")
        togrog_amt = st.number_input(
            "Төгрөг дүн", min_value=0.0, value=100000.0, step=1000.0, key="m2f"
        )
        if st.button("← Хөрвүүлэх", key="btn_m2f", use_container_width=True):
            res = api_get("/convert", backend_url, params={
                "from": "MNT", "to": selected_currency,
                "amount": togrog_amt, "date": date_str,
                "demo": str(use_demo).lower(),
            })
            if res:
                st.success(
                    f"**{togrog_amt:,.0f} ₮ "
                    f"= {res['result']:,.4f} {selected_currency}**"
                )

    st.markdown(
        f'<span class="endpoint-badge">GET {backend_url}/convert?from=USD&to=MNT&amount=100&date={date_str}</span>',
        unsafe_allow_html=True,
    )


# ─── ТАБ 4: Claude AI ───
with tab4:
    st.markdown("### 🤖 Claude AI Ханшийн Зөвлөмж")
    st.info(
        "Claude AI тухайн өдрийн ханш болон түүхийн өгөгдөлд үндэслэн "
        "дүн шинжилгээ, практик зөвлөмж гаргана.\n\n"
        "**Шаардлага:** Backend-д `ANTHROPIC_API_KEY` тохируулсан байх ёстой."
    )

    user_question = st.text_input(
        "Нэмэлт асуулт (заавал биш)",
        placeholder="Жишээ: Долларыг одоо авах уу, эсвэл хүлээх үү?",
    )

    if st.button(
        f"🤖 {flag} {selected_currency} ханшийн зөвлөмж авах",
        type="primary",
        use_container_width=True,
    ):
        # Түүхийн өгөгдөл авах
        hist_raw = api_get(
            f"/history/{selected_currency}",
            backend_url,
            params={"days": 14, "demo": str(use_demo).lower()},
        )
        history_records = hist_raw.get("records", []) if hist_raw else []

        payload = {
            "currency": selected_currency,
            "date": date_str,
            "rate": selected_rate,
            "history": history_records,
            "question": user_question or None,
        }

        with st.spinner("Claude дүн шинжилгээ хийж байна..."):
            result = api_post("/analyze", backend_url, payload)

        if result:
            st.markdown(
                f'<div class="ai-box">'
                f'<strong>🤖 Claude AI · {selected_date.strftime("%Y.%m.%d")} · '
                f'{flag} {selected_currency} ({selected_rate:,.2f}₮)</strong>'
                f'<hr style="margin:0.6rem 0;border-color:#bbf7d0">'
                f'{result["analysis"].replace(chr(10), "<br>")}'
                f'</div>',
                unsafe_allow_html=True,
            )

            st.download_button(
                "📥 Зөвлөмжийг татах (.txt)",
                data=(
                    f"Огноо: {selected_date}\n"
                    f"Валют: {selected_currency} ({cname})\n"
                    f"Ханш: {selected_rate:,.2f}₮\n"
                    f"{'='*40}\n\n"
                    f"{result['analysis']}"
                ),
                file_name=f"zuwlumj_{date_str}_{selected_currency}.txt",
                mime="text/plain",
            )

    st.markdown(
        f'<span class="endpoint-badge">POST {backend_url}/analyze</span>',
        unsafe_allow_html=True,
    )

# ── Footer ──
st.markdown("---")
st.markdown(
    "<div style='text-align:center;color:#94a3b8;font-size:.83rem'>"
    f"Backend: <code>{backend_url}</code> · "
    "🏦 mongolbank.mn · 🤖 Anthropic Claude · 🛠 FastAPI + Streamlit"
    "</div>",
    unsafe_allow_html=True,
)
