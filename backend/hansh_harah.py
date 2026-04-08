"""
╔══════════════════════════════════════════════════════════╗
║   Монгол Валютын Ханш — FastAPI Backend                  ║
║   Монголбанк ханш + Claude AI зөвлөмж                    ║
╚══════════════════════════════════════════════════════════╝

Ажиллуулах:
    uvicorn main:app --reload --port 8000

API баримт бичиг:
    http://localhost:8000/docs      ← Swagger UI
    http://localhost:8000/redoc     ← ReDoc UI
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from datetime import date, datetime, timedelta
from typing import Optional
import os
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from anthropic import Anthropic
import logging

# ── Тохиргоо ──
load_dotenv()  # .env файл уншина

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── FastAPI апп ──
app = FastAPI(
    title="🏦 Монгол Валютын Ханш API",
    description="""
## Монголбанкны валютын ханш + Claude AI зөвлөмж

### Боломжит endpoint-ууд:
- **GET /rates/{date}** — Тухайн өдрийн бүх валютын ханш
- **GET /rates/{date}/{currency}** — Нэг валютын ханш
- **GET /history/{currency}** — Ханшийн түүх
- **POST /analyze** — Claude AI дүн шинжилгээ
- **GET /convert** — Валют хөрвүүлэх
- **GET /health** — Системийн байдал
    """,
    version="1.0.0",
    contact={"name": "Монгол Хөгжүүлэгч", "email": "dev@example.mn"},
)

# ── CORS — Streamlit frontend-тэй холбогдохын тулд ──
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # Production дээр зөвхөн өөрийн домэйн
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ══════════════════════════════════════════════
# PYDANTIC ЗАГВАРУУД (Request / Response)
# ══════════════════════════════════════════════

class RateResponse(BaseModel):
    """Ганц валютын ханшийн хариу"""
    date: str = Field(..., description="Огноо (YYYY-MM-DD)")
    currency: str = Field(..., description="Валютын код (USD, EUR...)")
    currency_name: str = Field(..., description="Валютын монгол нэр")
    rate: float = Field(..., description="Монгол төгрөгт харьцах ханш")
    unit: int = Field(1, description="Нэгж (1 эсвэл 100)")
    source: str = Field(..., description="Мэдээллийн эх сурвалж")
    is_demo: bool = Field(False, description="Demo өгөгдөл эсэх")


class AllRatesResponse(BaseModel):
    """Бүх валютын ханшийн хариу"""
    date: str
    rates: dict[str, float]
    source: str
    is_demo: bool
    fetched_at: str


class AnalyzeRequest(BaseModel):
    """Claude AI дүн шинжилгээний хүсэлт"""
    currency: str = Field(..., description="Валютын код", example="USD")
    date: str = Field(..., description="Огноо", example="2026-04-08")
    rate: float = Field(..., description="Одоогийн ханш", example=3570.0)
    history: Optional[list[dict]] = Field(
        None, description="Түүхийн өгөгдөл [{date, rate}, ...]"
    )
    question: Optional[str] = Field(
        None, description="Хэрэглэгчийн нэмэлт асуулт"
    )


class AnalyzeResponse(BaseModel):
    """Claude AI хариу"""
    analysis: str
    currency: str
    date: str
    rate: float
    model: str


class ConvertResponse(BaseModel):
    """Валют хөрвүүлэлтийн хариу"""
    from_currency: str
    to_currency: str
    amount: float
    result: float
    rate: float
    date: str


class HealthResponse(BaseModel):
    """Системийн байдлын хариу"""
    status: str
    mongolbank_api: str
    claude_api: str
    timestamp: str
    version: str


# ══════════════════════════════════════════════
# ВАЛЮТЫН МЭДЭЭЛЭЛ
# ══════════════════════════════════════════════

CURRENCY_INFO = {
    "USD": {"name": "Ам.доллар",          "flag": "🇺🇸", "unit": 1},
    "EUR": {"name": "Евро",               "flag": "🇪🇺", "unit": 1},
    "CNY": {"name": "Юань",               "flag": "🇨🇳", "unit": 1},
    "RUB": {"name": "Рубль",              "flag": "🇷🇺", "unit": 100},
    "KRW": {"name": "Вон",                "flag": "🇰🇷", "unit": 100},
    "JPY": {"name": "Иен",                "flag": "🇯🇵", "unit": 100},
    "GBP": {"name": "Фунт стерлинг",     "flag": "🇬🇧", "unit": 1},
    "HKD": {"name": "Хонконгийн доллар", "flag": "🇭🇰", "unit": 1},
    "AUD": {"name": "Австралийн доллар", "flag": "🇦🇺", "unit": 1},
    "CAD": {"name": "Канадын доллар",    "flag": "🇨🇦", "unit": 1},
    "CHF": {"name": "Швейцарийн франк",  "flag": "🇨🇭", "unit": 1},
    "SGD": {"name": "Сингапурын доллар", "flag": "🇸🇬", "unit": 1},
}

# Cache — API-г хэт олон дуудахгүйн тулд
_rate_cache: dict = {}
_cache_ttl = 3600  # 1 цаг


# ══════════════════════════════════════════════
# МОНГОЛБАНК ХАН ШИГ ТАТАХ ФУНКЦҮҮД
# ══════════════════════════════════════════════

def _get_cache_key(target_date: date) -> str:
    return target_date.strftime("%Y-%m-%d")


def _is_cache_valid(key: str) -> bool:
    if key not in _rate_cache:
        return False
    cached_at = _rate_cache[key].get("cached_at", 0)
    return (datetime.now().timestamp() - cached_at) < _cache_ttl


def fetch_from_mongolbank(target_date: date) -> dict:
    """
    mongolbank.mn-с ханш татах.
    HTML scraping аргаар ажилладаг.
    """
    cache_key = _get_cache_key(target_date)

    # Cache-с авах
    if _is_cache_valid(cache_key):
        logger.info(f"Cache-с авлаа: {cache_key}")
        return _rate_cache[cache_key]

    date_str = target_date.strftime("%Y-%m-%d")
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.9",
        "Accept-Language": "mn,en-US;q=0.9,en;q=0.8",
        "Referer": "https://www.mongolbank.mn/",
    }

    rates = {}

    # ── 1-р оролдлого: Mongolbank HTML хуудас ──
    try:
        url = "https://www.mongolbank.mn/mn/currency-rates"
        resp = requests.get(
            url, headers=headers,
            params={"date": date_str},
            timeout=12,
        )
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "lxml")
        table = soup.find("table")
        if table:
            for row in table.find_all("tr"):
                cols = row.find_all(["td", "th"])
                if len(cols) >= 3:
                    code = cols[0].get_text(strip=True).upper()
                    try:
                        val = float(
                            cols[-1].get_text(strip=True)
                            .replace(",", "").replace(" ", "")
                        )
                        if code in CURRENCY_INFO and val > 0:
                            rates[code] = val
                    except ValueError:
                        continue

        if rates:
            logger.info(f"Mongolbank-с татлаа: {len(rates)} валют")

    except Exception as e:
        logger.warning(f"Mongolbank HTML татахад алдаа: {e}")

    # ── 2-р оролдлого: Mongolbank JSON API ──
    if not rates:
        try:
            json_url = "https://www.mongolbank.mn/api/UserAPI/GetCurrencyList"
            resp2 = requests.get(
                json_url, headers=headers,
                params={"date": date_str},
                timeout=10,
            )
            if resp2.status_code == 200:
                for item in resp2.json():
                    code = item.get("CurrencyCode", "").upper()
                    rate = item.get("CloseRate") or item.get("Rate")
                    if code in CURRENCY_INFO and rate:
                        rates[code] = float(rate)
                logger.info(f"Mongolbank JSON-с татлаа: {len(rates)} валют")
        except Exception as e:
            logger.warning(f"Mongolbank JSON алдаа: {e}")

    if rates:
        result = {
            "rates": rates,
            "date": date_str,
            "source": "mongolbank.mn",
            "is_demo": False,
            "fetched_at": datetime.now().isoformat(),
            "cached_at": datetime.now().timestamp(),
        }
        _rate_cache[cache_key] = result
        return result

    # ── Fallback: Demo өгөгдөл ──
    logger.warning(f"Mongolbank-с татаж чадсангүй, demo ашиглана: {date_str}")
    return _get_demo_rates(target_date)


def _get_demo_rates(target_date: date) -> dict:
    """
    Demo/fallback өгөгдөл.
    mongolbank.mn хаагдсан үед ашиглана.
    """
    import random
    random.seed(target_date.toordinal())

    base = {
        "USD": 3570.0, "EUR": 3920.0, "CNY": 491.5,
        "RUB": 42.5,   "KRW": 258.0, "JPY": 238.0,
        "GBP": 4640.0, "HKD": 459.0, "AUD": 2260.0,
        "CAD": 2590.0, "CHF": 4050.0, "SGD": 2680.0,
    }
    days_diff = (target_date - date(2026, 4, 8)).days
    rates = {}
    for code, b in base.items():
        v = random.uniform(-0.006, 0.006)
        t = days_diff * 0.0002
        rates[code] = round(b * (1 + v + t), 2)

    return {
        "rates": rates,
        "date": target_date.strftime("%Y-%m-%d"),
        "source": "Demo (mongolbank.mn холбогдсонгүй)",
        "is_demo": True,
        "fetched_at": datetime.now().isoformat(),
        "cached_at": datetime.now().timestamp(),
    }


def fetch_history(currency: str, days: int = 30, demo: bool = False) -> list[dict]:
    """
    Ханшийн түүхийн өгөгдөл татах.
    """
    records = []
    today = date.today()

    if not demo:
        # Mongolbank ханшийн хөдөлгөөн хуудсаас татах
        try:
            url = "https://www.mongolbank.mn/mn/currency-rate-movement"
            headers = {
                "User-Agent": "Mozilla/5.0 Chrome/120.0",
                "Referer": "https://www.mongolbank.mn/",
            }
            params = {
                "startDate": (today - timedelta(days=days)).strftime("%Y-%m-%d"),
                "endDate": today.strftime("%Y-%m-%d"),
                "currencyCode": currency,
            }
            resp = requests.get(url, headers=headers, params=params, timeout=12)
            soup = BeautifulSoup(resp.text, "lxml")
            table = soup.find("table")
            if table:
                for row in table.find_all("tr")[1:]:
                    cols = row.find_all("td")
                    if len(cols) >= 2:
                        try:
                            d = cols[0].get_text(strip=True)
                            r = float(
                                cols[-1].get_text(strip=True)
                                .replace(",", "")
                            )
                            records.append({"date": d, "rate": r})
                        except ValueError:
                            continue
        except Exception as e:
            logger.warning(f"Түүх татахад алдаа: {e}")

    # Fallback: demo түүх
    if not records:
        import random
        base_rate = _get_demo_rates(today)["rates"].get(currency, 3570.0)
        for i in range(days, 0, -1):
            d = today - timedelta(days=i)
            if d.weekday() < 5:
                random.seed(d.toordinal() + hash(currency))
                v = random.uniform(-0.005, 0.005)
                records.append({
                    "date": d.strftime("%Y-%m-%d"),
                    "rate": round(base_rate * (1 + v + i * 0.0001), 2),
                })

    return sorted(records, key=lambda x: x["date"])


# ══════════════════════════════════════════════
# CLAUDE AI ФУНКЦ
# ══════════════════════════════════════════════

def get_claude_analysis(req: AnalyzeRequest) -> str:
    """Claude-аас ханшийн дүн шинжилгээ авах."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="ANTHROPIC_API_KEY тохируулаагүй байна. .env файлд нэмнэ үү.",
        )

    client = Anthropic(api_key=api_key)

    # Түүхийн хураангуй бэлдэх
    history_summary = ""
    if req.history:
        rates = [d["rate"] for d in req.history[-14:]]
        if rates:
            trend = "📈 өсөх чиглэлтэй" if rates[-1] > rates[0] else "📉 буурах чиглэлтэй"
            change_pct = (rates[-1] - rates[0]) / rates[0] * 100
            history_summary = (
                f"\nСүүлийн {len(rates)} ажлын өдрийн түүх:\n"
                f"- Хамгийн бага: {min(rates):,.2f}₮\n"
                f"- Хамгийн их: {max(rates):,.2f}₮\n"
                f"- Дундаж: {sum(rates)/len(rates):,.2f}₮\n"
                f"- Өөрчлөлт: {change_pct:+.2f}%\n"
                f"- Чиглэл: {trend}\n"
            )

    extra_q = f"\n\nНэмэлт асуулт: {req.question}" if req.question else ""
    info = CURRENCY_INFO.get(req.currency, {})
    cname = info.get("name", req.currency)
    flag = info.get("flag", "")

    prompt = f"""Та Монголын валютын зах зээлийн туршлагатай мэргэжилтэн юм.

📊 МЭДЭЭЛЭЛ:
- Огноо: {req.date}
- Валют: {flag} {req.currency} ({cname})
- Монголбанкны ханш: {req.rate:,.2f} төгрөг
{history_summary}{extra_q}

Дараах бүтэцтэйгээр хариулна уу (нийт 200-250 үг):

**📊 Ханшийн дүн шинжилгээ**
Одоогийн ханшийн байдлыг товч үнэлэх

**🔮 Богино хугацааны таамаглал**  
Ойрын 1-2 долоо хоногт ямар чиглэл барих магадлалтай

**💡 Практик зөвлөмж**
Валют худалдах/авах талаар тодорхой зөвлөгөө

**⚠️ Анхаарах зүйл**
Ханшид нөлөөлж болох гол эрсдэлүүд

Монгол хэлээр, ойлгомжтой, практик байдлаар бичнэ үү."""

    msg = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=700,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text


# ══════════════════════════════════════════════
# API ENDPOINT-УУД
# ══════════════════════════════════════════════

@app.get("/", tags=["Үндсэн"])
async def root():
    """API-н үндсэн хуудас"""
    return {
        "message": "🏦 Монгол Валютын Ханш API",
        "version": "1.0.0",
        "docs": "/docs",
        "endpoints": {
            "бүх ханш": "/rates/2026-04-08",
            "нэг валют": "/rates/2026-04-08/USD",
            "түүх": "/history/USD?days=30",
            "хөрвүүлэх": "/convert?from=USD&to=MNT&amount=100&date=2026-04-08",
            "AI зөвлөмж": "POST /analyze",
            "байдал": "/health",
        },
    }


@app.get(
    "/rates/{target_date}",
    response_model=AllRatesResponse,
    tags=["Ханш"],
    summary="Тухайн өдрийн бүх валютын ханш",
)
async def get_all_rates(
    target_date: str,
    demo: bool = Query(False, description="Demo өгөгдөл ашиглах эсэх"),
):
    """
    Монголбанкны тухайн өдрийн бүх валютын ханшийг буцаана.

    - **target_date**: Огноо (YYYY-MM-DD формат, жишээ: 2026-04-08)
    - **demo**: True бол demo өгөгдөл ашиглана
    """
    try:
        d = date.fromisoformat(target_date)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Огноо буруу формат. YYYY-MM-DD хэлбэрт байх ёстой (жишээ: 2026-04-08)",
        )

    if d > date.today():
        raise HTTPException(status_code=400, detail="Ирээдүйн огноо байж болохгүй")
    if d < date(2000, 1, 1):
        raise HTTPException(status_code=400, detail="Хэт хуучин огноо (2000 оноос эхлэнэ)")

    if demo:
        data = _get_demo_rates(d)
    else:
        data = fetch_from_mongolbank(d)

    return AllRatesResponse(
        date=data["date"],
        rates=data["rates"],
        source=data["source"],
        is_demo=data["is_demo"],
        fetched_at=data["fetched_at"],
    )


@app.get(
    "/rates/{target_date}/{currency}",
    response_model=RateResponse,
    tags=["Ханш"],
    summary="Тухайн өдрийн нэг валютын ханш",
)
async def get_single_rate(
    target_date: str,
    currency: str,
    demo: bool = Query(False),
):
    """
    Монголбанкны тухайн өдрийн тодорхой валютын ханшийг буцаана.

    - **target_date**: Огноо (YYYY-MM-DD)
    - **currency**: Валютын код (USD, EUR, CNY, RUB, KRW, JPY, GBP, HKD)
    """
    currency = currency.upper()
    if currency not in CURRENCY_INFO:
        raise HTTPException(
            status_code=404,
            detail=f"'{currency}' валют олдсонгүй. Дэмжигдэх валютууд: {list(CURRENCY_INFO.keys())}",
        )

    try:
        d = date.fromisoformat(target_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Огноо буруу формат (YYYY-MM-DD)")

    data = _get_demo_rates(d) if demo else fetch_from_mongolbank(d)
    rate = data["rates"].get(currency)

    if not rate:
        raise HTTPException(
            status_code=404,
            detail=f"{target_date} өдрийн {currency} ханш олдсонгүй. "
                   "Амралтын өдөр байж болно.",
        )

    info = CURRENCY_INFO[currency]
    return RateResponse(
        date=data["date"],
        currency=currency,
        currency_name=info["name"],
        rate=rate,
        unit=info["unit"],
        source=data["source"],
        is_demo=data["is_demo"],
    )


@app.get(
    "/history/{currency}",
    tags=["Ханш"],
    summary="Валютын ханшийн түүх",
)
async def get_history(
    currency: str,
    days: int = Query(30, ge=7, le=365, description="Хэдэн хоногийн түүх (7-365)"),
    demo: bool = Query(False),
):
    """
    Сонгосон валютын ханшийн түүхийг буцаана.

    - **currency**: Валютын код (USD, EUR, CNY...)
    - **days**: Хэдэн хоногийн түүх (7-365, default: 30)
    """
    currency = currency.upper()
    if currency not in CURRENCY_INFO:
        raise HTTPException(
            status_code=404,
            detail=f"'{currency}' валют дэмжигдэхгүй байна.",
        )

    records = fetch_history(currency, days=days, demo=demo)
    if not records:
        raise HTTPException(status_code=404, detail="Түүхийн өгөгдөл олдсонгүй")

    rates = [r["rate"] for r in records]
    return {
        "currency": currency,
        "currency_name": CURRENCY_INFO[currency]["name"],
        "days": days,
        "count": len(records),
        "min": min(rates),
        "max": max(rates),
        "average": round(sum(rates) / len(rates), 2),
        "change": round(rates[-1] - rates[0], 2),
        "change_pct": round((rates[-1] - rates[0]) / rates[0] * 100, 2),
        "records": records,
    }


@app.get(
    "/convert",
    response_model=ConvertResponse,
    tags=["Хэрэгсэл"],
    summary="Валют хөрвүүлэх",
)
async def convert_currency(
    amount: float = Query(..., gt=0, description="Хөрвүүлэх дүн"),
    from_currency: str = Query(..., alias="from", description="Эх валют (USD, MNT...)"),
    to_currency: str = Query(..., alias="to", description="Зорилтот валют"),
    target_date: str = Query(
        default=date.today().isoformat(), alias="date",
        description="Огноо (YYYY-MM-DD)"
    ),
    demo: bool = Query(False),
):
    """
    Валютыг тухайн өдрийн ханшаар хөрвүүлнэ.

    Жишээ: 100 USD → MNT, 50000 MNT → CNY
    """
    from_currency = from_currency.upper()
    to_currency = to_currency.upper()

    try:
        d = date.fromisoformat(target_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Огноо буруу формат")

    data = _get_demo_rates(d) if demo else fetch_from_mongolbank(d)
    rates = data["rates"]

    def to_mnt(currency: str, amount: float) -> float:
        """Дурын валютыг MNT болгох"""
        if currency == "MNT":
            return amount
        r = rates.get(currency)
        if not r:
            raise HTTPException(status_code=404, detail=f"{currency} ханш олдсонгүй")
        unit = CURRENCY_INFO.get(currency, {}).get("unit", 1)
        return amount * r / unit

    def from_mnt(currency: str, mnt_amount: float) -> float:
        """MNT-г дурын валют болгох"""
        if currency == "MNT":
            return mnt_amount
        r = rates.get(currency)
        if not r:
            raise HTTPException(status_code=404, detail=f"{currency} ханш олдсонгүй")
        unit = CURRENCY_INFO.get(currency, {}).get("unit", 1)
        return mnt_amount / r * unit

    # Хөрвүүлэлт: from → MNT → to
    mnt_amount = to_mnt(from_currency, amount)
    result = from_mnt(to_currency, mnt_amount)

    # Харьцааны ханш
    if from_currency == "MNT":
        effective_rate = rates.get(to_currency, 1)
    elif to_currency == "MNT":
        effective_rate = rates.get(from_currency, 1)
    else:
        effective_rate = round(result / amount, 6)

    return ConvertResponse(
        from_currency=from_currency,
        to_currency=to_currency,
        amount=amount,
        result=round(result, 4),
        rate=effective_rate,
        date=target_date,
    )


@app.post(
    "/analyze",
    response_model=AnalyzeResponse,
    tags=["Claude AI"],
    summary="Claude AI ханшийн дүн шинжилгээ",
)
async def analyze_rate(req: AnalyzeRequest):
    """
    Claude AI-аас тухайн валютын ханшийн дүн шинжилгээ, зөвлөмж авна.

    **Шаардлага:** ANTHROPIC_API_KEY .env файлд тохируулсан байх ёстой.
    """
    currency = req.currency.upper()
    if currency not in CURRENCY_INFO:
        raise HTTPException(
            status_code=404,
            detail=f"'{currency}' валют олдсонгүй",
        )

    try:
        analysis = get_claude_analysis(req)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Claude API алдаа: {str(e)}")

    return AnalyzeResponse(
        analysis=analysis,
        currency=currency,
        date=req.date,
        rate=req.rate,
        model="claude-opus-4-5",
    )


@app.get(
    "/analyze/quick/{currency}",
    tags=["Claude AI"],
    summary="Хурдан AI зөвлөмж (огноо автоматаар)",
)
async def quick_analyze(
    currency: str,
    target_date: str = Query(default=date.today().isoformat(), alias="date"),
    demo: bool = Query(False),
):
    """
    Нэмэлт параметр шаардлагагүй — валют сонгоход л бүгд автоматаар хийгдэнэ.
    """
    currency = currency.upper()
    if currency not in CURRENCY_INFO:
        raise HTTPException(status_code=404, detail=f"'{currency}' валют олдсонгүй")

    try:
        d = date.fromisoformat(target_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Огноо буруу формат")

    data = _get_demo_rates(d) if demo else fetch_from_mongolbank(d)
    rate = data["rates"].get(currency)
    if not rate:
        raise HTTPException(status_code=404, detail=f"{target_date} өдрийн ханш олдсонгүй")

    history = fetch_history(currency, days=14, demo=demo)

    req = AnalyzeRequest(
        currency=currency,
        date=target_date,
        rate=rate,
        history=history,
    )
    analysis = get_claude_analysis(req)

    return {
        "currency": currency,
        "currency_name": CURRENCY_INFO[currency]["name"],
        "date": target_date,
        "rate": rate,
        "analysis": analysis,
        "model": "claude-opus-4-5",
    }


@app.get(
    "/health",
    response_model=HealthResponse,
    tags=["Систем"],
    summary="Системийн байдал шалгах",
)
async def health_check():
    """API болон гадаад үйлчилгээнүүдийн байдлыг шалгана."""

    # Mongolbank шалгах
    mongolbank_status = "✅ Ажиллаж байна"
    try:
        r = requests.get(
            "https://www.mongolbank.mn/mn/currency-rates",
            timeout=5,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        if r.status_code != 200:
            mongolbank_status = f"⚠️ HTTP {r.status_code}"
    except Exception as e:
        mongolbank_status = f"❌ Холбогдсонгүй: {str(e)[:50]}"

    # Claude API шалгах
    claude_status = "✅ API key тохируулсан"
    if not os.environ.get("ANTHROPIC_API_KEY"):
        claude_status = "⚠️ API key тохируулаагүй"

    return HealthResponse(
        status="✅ Ажиллаж байна",
        mongolbank_api=mongolbank_status,
        claude_api=claude_status,
        timestamp=datetime.now().isoformat(),
        version="1.0.0",
    )


@app.get("/currencies", tags=["Хэрэгсэл"], summary="Дэмжигдэх валютуудын жагсаалт")
async def get_currencies():
    """Бүх дэмжигдэх валютуудын мэдээлэл"""
    return {
        "currencies": [
            {
                "code": code,
                "name": info["name"],
                "flag": info["flag"],
                "unit": info["unit"],
            }
            for code, info in CURRENCY_INFO.items()
        ],
        "total": len(CURRENCY_INFO),
    }


# ══════════════════════════════════════════════
# АЖИЛЛУУЛАХ
# ══════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    print("🚀 Backend эхэлж байна...")
    print("📖 Swagger UI: http://localhost:8000/docs")
    print("📖 ReDoc:      http://localhost:8000/redoc")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)