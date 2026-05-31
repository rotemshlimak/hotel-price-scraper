"""Fetch hotel rates from HTZone / Arbitrip (htzone.arbitrip.com).

Requires a logged-in browser session — run scripts/arbitrip_login.py once to save cookies.
"""
from __future__ import annotations

import json
import os
import re
from datetime import date
from pathlib import Path
from urllib.parse import urlencode

from arbitrip_auth import is_login_page, session_authenticated, session_status

ARBITRIP_BASE = "https://htzone.arbitrip.com"
API_HOST = "api.arbitrip.com"
DEFAULT_STORAGE = Path(__file__).resolve().parent / "logs" / "arbitrip_storage.json"

_PRICE_KEYS = (
    "price",
    "total_price",
    "totalPrice",
    "amount",
    "rate",
    "per_night",
    "perNight",
    "nightly_rate",
    "nightlyRate",
    "display_price",
    "displayPrice",
)
_NAME_KEYS = ("room_name", "roomName", "name", "title", "room_type", "roomType")
_CURRENCY_KEYS = ("currency", "currency_code", "currencyCode", "curr")
_ROOM_NAME_RE = re.compile(
    r"\b(Suite|Room|Pool|Villa|King|Twin|Double|Bedroom|Studio|Seaview|Sea view|Apartment|Bungalow)\b",
    re.IGNORECASE,
)


def _storage_path() -> Path:
    override = os.environ.get("ARBITRIP_STORAGE_STATE", "").strip()
    return Path(override) if override else DEFAULT_STORAGE


def to_arbitrip_date(iso_date: str) -> str:
    """Convert 2027-04-14 → 270414 (YYMMDD)."""
    d = date.fromisoformat(iso_date)
    return f"{d.year % 100:02d}{d.month:02d}{d.day:02d}"


def from_arbitrip_date(value: str) -> date:
    """Convert 270414 → 2027-04-14."""
    yy, mm, dd = int(value[0:2]), int(value[2:4]), int(value[4:6])
    return date(2000 + yy, mm, dd)


def build_hotel_url(hotel_config: dict) -> str:
    if hotel_config.get("booking_url"):
        return hotel_config["booking_url"].strip()

    slug = (hotel_config.get("hotel_slug") or "").strip()
    property_id = hotel_config["property_id"]
    if not slug:
        slug = re.sub(r"[^a-z0-9]+", "-", hotel_config["hotel_id"].lower()).strip("-")

    params = {
        "hotel_id": property_id,
        "check_in": to_arbitrip_date(hotel_config["check_in_date"]),
        "check_out": to_arbitrip_date(hotel_config["check_out_date"]),
        "guests": hotel_config.get("adults", 2),
        "rooms": hotel_config.get("rooms", 1),
        "private_travel": str(hotel_config.get("private_travel", True)).lower(),
    }
    token = (hotel_config.get("search_token") or os.environ.get("ARBITRIP_SEARCH_TOKEN", "")).strip()
    if token:
        params["search_token"] = token
    elif hotel_config.get("chain") == "arbitrip" or hotel_config.get("property_id"):
        raise ValueError(
            "Arbitrip needs search_token or booking_url from your browser. "
            "While logged in, open the hotel on htzone.arbitrip.com, copy the full address bar URL "
            "(includes search_token=...), and set booking_url or search_token in config.json."
        )

    return f"{ARBITRIP_BASE}/hotel/{slug}/{property_id}?{urlencode(params)}"


def _parse_money(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).replace(",", "").replace("₪", "").replace("€", "").replace("$", "")
    m = re.search(r"\d+(?:\.\d+)?", text)
    return float(m.group(0)) if m else None


def _first_key(obj: dict, keys: tuple[str, ...]):
    for k in keys:
        if k in obj and obj[k] not in (None, ""):
            return obj[k]
    return None


def _rate_row(room_name: str, per_night: float, total: float | None, currency: str, label: str) -> dict:
    return {
        "room_name": room_name or "Unknown",
        "bed_type": "",
        "per_night": per_night,
        "total": total,
        "currency": currency,
        "rate_name": label or "Arbitrip",
        "rate_plan_code": "",
    }


def _rows_from_room_object(obj: dict, currency_fallback: str, nights: int = 1) -> list[dict]:
    name = _first_key(obj, _NAME_KEYS) or "Unknown"
    currency = _first_key(obj, _CURRENCY_KEYS) or currency_fallback

    per_night = None
    for k in _PRICE_KEYS:
        if k in obj:
            per_night = _parse_money(obj[k])
            if per_night:
                break

    total = _parse_money(obj.get("total") or obj.get("total_price") or obj.get("totalPrice"))
    if not per_night:
        return []

    if total is None:
        total = per_night * max(nights, 1)
    elif nights > 1 and total == per_night:
        total = per_night * nights

    label = obj.get("rate_name") or obj.get("board") or obj.get("meal") or "Arbitrip"
    return [_rate_row(str(name), per_night, total, str(currency), str(label))]


def _walk_for_rates(node, currency_fallback: str, rows: list[dict], nights: int = 1, depth: int = 0) -> None:
    if depth > 12:
        return
    if isinstance(node, dict):
        if any(k in node for k in _NAME_KEYS) and any(k in node for k in _PRICE_KEYS):
            rows.extend(_rows_from_room_object(node, currency_fallback, nights))
        for v in node.values():
            _walk_for_rates(v, currency_fallback, rows, nights, depth + 1)
    elif isinstance(node, list):
        for item in node:
            _walk_for_rates(item, currency_fallback, rows, nights, depth + 1)


def parse_api_payloads(payloads: list[dict], nights: int, currency_fallback: str = "ILS") -> list[dict]:
    rows: list[dict] = []
    for payload in payloads:
        _walk_for_rates(payload, currency_fallback, rows, nights)

    deduped: dict[tuple, dict] = {}
    for row in rows:
        key = (row["room_name"], row["per_night"], row["rate_name"])
        if key not in deduped or row["per_night"] < deduped[key]["per_night"]:
            deduped[key] = row

    result = list(deduped.values())
    result.sort(key=lambda x: (x["per_night"], x["room_name"]))
    return result


def _parse_dom_rates(page, currency_fallback: str, nights: int = 1) -> list[dict]:
    """Scrape room rate rows from the Arbitrip hotel rooms section."""
    rows: list[dict] = []

    for selector in ("h3", "h4", "[class*='room' i]", "[class*='Room' i]"):
        for el in page.locator(selector).all()[:60]:
            try:
                name = el.inner_text(timeout=500).strip().split("\n")[0].strip()
            except Exception:
                continue
            if not _is_hotel_room_name(name):
                continue

            container_text = name
            try:
                container_text = el.locator("xpath=ancestor::div[1]").first.inner_text(timeout=500)
            except Exception:
                pass

            prices = []
            for ln in container_text.splitlines():
                if re.search(r"[\d,.]+\s*(?:USD|EUR|THB|₪|€|\$)", ln) or re.search(
                    r"(?:USD|EUR|THB|₪|€|\$)\s*[\d,.]+", ln
                ):
                    val = _parse_money(ln)
                    if val and val > 50:
                        prices.append(val)
            if not prices:
                continue

            per_night = min(prices)
            total = max(prices) if len(prices) > 1 else per_night * max(nights, 1)
            if nights > 1 and total == per_night:
                total = per_night * nights

            currency = currency_fallback
            blob = container_text + name
            if "€" in blob or "EUR" in blob:
                currency = "EUR"
            elif "$" in blob or "USD" in blob:
                currency = "USD"
            elif "₪" in blob:
                currency = "ILS"
            elif "THB" in blob or "฿" in blob:
                currency = "THB"

            rows.append(_rate_row(name[:120], per_night, total, currency, "Arbitrip"))

    deduped: dict[tuple, dict] = {}
    for row in rows:
        key = (row["room_name"], row["per_night"])
        deduped[key] = row
    result = list(deduped.values())
    result.sort(key=lambda x: x["per_night"])
    return result


def _is_hotel_room_name(name: str) -> bool:
    """Reject TripZone homepage deal cards (Hebrew) — keep English room type names."""
    text = (name or "").strip()
    if len(text) < 4 or len(text) > 150:
        return False
    hebrew = len(re.findall(r"[\u0590-\u05FF]", text))
    latin = len(re.findall(r"[A-Za-z]", text))
    if hebrew > latin:
        return False
    return bool(_ROOM_NAME_RE.search(text)) or (latin >= 8 and hebrew == 0)


def _is_hotel_page_url(url: str) -> bool:
    return "htzone.arbitrip.com/hotel/" in url.lower()


TRIPZONE_HOME = "https://tripzone.co.il/home.html"


def _warm_session(page) -> None:
    """Load TripZone home so SSO cookies are active before the Arbitrip deep link."""
    page.goto(TRIPZONE_HOME, wait_until="domcontentloaded", timeout=90000)
    page.wait_for_timeout(2000)


def _open_hotel_page(page, url: str) -> None:
    if "search_token=" not in url:
        raise RuntimeError(
            "Arbitrip hotel URL is missing search_token. "
            "Copy the full URL from your browser while logged in and set booking_url in config.json."
        )

    page.context.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
    )

    _warm_session(page)

    for attempt in range(2):
        page.set_extra_http_headers({"Referer": TRIPZONE_HOME})
        page.goto(url, wait_until="networkidle", timeout=120000)
        page.wait_for_timeout(5000)
        if _is_hotel_page_url(page.url):
            return
        if attempt == 0:
            _warm_session(page)

    if not _is_hotel_page_url(page.url):
        raise RuntimeError(
            f"Expected Arbitrip hotel page but got: {page.url[:120]}. "
            "Re-run login after adding booking_url to config: python scripts/arbitrip_login.py"
        )


def _open_rooms_section(page) -> None:
    for sel in (
        "text=לצפייה בחדרים",
        "text=View rooms",
        "button:has-text('חדרים')",
        "button:has-text('rooms')",
    ):
        try:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=5000):
                btn.click()
                break
        except Exception:
            pass

    for sel in ("text=בחירת סוג החדר", "text=Room type", "text=Pool Suite", "text=Suite With"):
        try:
            page.wait_for_selector(sel, timeout=45000)
            return
        except Exception:
            continue

    page.wait_for_timeout(8000)


def _ensure_storage() -> Path:
    path = _storage_path()
    if not path.is_file():
        raise RuntimeError(
            f"Missing Arbitrip login session at {path}. "
            "Run: python scripts/arbitrip_login.py"
        )
    return path


def fetch_rooms(hotel_config: dict) -> dict:
    from playwright.sync_api import sync_playwright

    storage = _ensure_storage()
    url = build_hotel_url(hotel_config)
    api_payloads: list[dict] = []
    currency = hotel_config.get("currency", "ILS")
    nights = max(
        (
            date.fromisoformat(hotel_config["check_out_date"])
            - date.fromisoformat(hotel_config["check_in_date"])
        ).days,
        1,
    )

    headed = os.environ.get("ARBITRIP_HEADED", "").strip().lower() in ("1", "true", "yes")

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(
                channel="chrome",
                headless=not headed,
                args=["--disable-blink-features=AutomationControlled"],
            )
        except Exception:
            browser = p.chromium.launch(headless=not headed)
        context = browser.new_context(
            storage_state=str(storage),
            locale="en-US",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()

        ok, detail = session_authenticated(context)
        if not ok:
            browser.close()
            raise RuntimeError(
                f"Arbitrip session invalid — {detail}. "
                "Run: python scripts/arbitrip_login.py"
            )

        def on_response(response):
            if response.status != 200:
                return
            host = response.url
            if API_HOST not in host and "htzone.arbitrip.com" not in host:
                return
            ct = response.headers.get("content-type", "")
            if "json" not in ct:
                return
            try:
                api_payloads.append(response.json())
            except Exception:
                pass

        page.on("response", on_response)
        _open_hotel_page(page, url)

        if is_login_page(page.url):
            msg = session_status(context, page.url)
            browser.close()
            raise RuntimeError(
                f"Arbitrip session expired — redirected to HTZone login. ({msg}) "
                "Run: python scripts/arbitrip_login.py"
            )

        ok, detail = session_authenticated(context, page.url)
        if not ok:
            msg = session_status(context, page.url)
            browser.close()
            raise RuntimeError(
                f"Arbitrip session expired — {msg}. "
                "Run: python scripts/arbitrip_login.py"
            )

        _open_rooms_section(page)

        if not _is_hotel_page_url(page.url):
            browser.close()
            raise RuntimeError(
                f"Lost Arbitrip hotel page before room scrape (got {page.url[:120]})"
            )

        rates = parse_api_payloads(api_payloads, nights=nights, currency_fallback=currency)
        if not rates:
            rates = _parse_dom_rates(page, currency, nights)
        rates = [r for r in rates if _is_hotel_room_name(r["room_name"])]

        debug_path = Path(__file__).resolve().parent / "logs" / "arbitrip_last_capture.json"
        debug_path.parent.mkdir(parents=True, exist_ok=True)
        debug_path.write_text(
            json.dumps(
                {
                    "url": url,
                    "final_url": page.url,
                    "api_payloads": api_payloads,
                    "rates": rates,
                },
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )
        browser.close()

    if not rates:
        raise RuntimeError(
            "No room rates found on Arbitrip page. "
            f"Check logs/arbitrip_last_capture.json — URL: {url}"
        )

    return {"currencyCode": rates[0]["currency"], "rates": rates, "room_types": []}


def lowest_cash_rate(shop: dict) -> dict | None:
    rates = shop.get("rates") or []
    return rates[0] if rates else None


def scrape_hotel_arbitrip(hotel_config: dict) -> dict:
    property_id = hotel_config.get("property_id")
    if not property_id:
        raise ValueError(f"property_id (Arbitrip hotel_id) required for {hotel_config.get('hotel_id')}")

    check_in = hotel_config["check_in_date"]
    check_out = hotel_config["check_out_date"]
    currency = hotel_config.get("currency", "ILS")

    shop = fetch_rooms(hotel_config)
    best = lowest_cash_rate(shop)
    room_rates = shop.get("rates") or []

    base = {
        "hotel": hotel_config["hotel_id"],
        "property_id": property_id,
        "check_in": check_in,
        "check_out": check_out,
        "rooms": hotel_config.get("rooms", 1),
        "adults": hotel_config.get("adults", 2),
        "children": hotel_config.get("children", 0),
        "source": "arbitrip",
        "currency": shop.get("currencyCode") or currency,
    }

    if best:
        rate_str = f"{best['per_night']:,.0f} {best['currency']} / Night"
        if best.get("rate_name"):
            rate_str += f" ({best['rate_name']})"
        return {
            **base,
            "available": True,
            "rate": rate_str,
            "per_night": best["per_night"],
            "total": best.get("total"),
            "rate_name": best.get("rate_name"),
            "room_types": len(room_rates),
            "room_rates": room_rates,
        }

    return {**base, "available": False, "rate": "Rate Unavailable", "per_night": None}


def scrape_prices_arbitrip(config: dict) -> list[dict]:
    from scraper_api import hotel_configs

    defaults = {k: v for k, v in config.items() if k not in ("provider", "hotels", "email", "scraper_mode")}
    results = [scrape_hotel_arbitrip({**defaults, **h}) for h in hotel_configs(config)]
    print(json.dumps(results, indent=2))
    return results
