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


def _rows_from_room_object(obj: dict, currency_fallback: str) -> list[dict]:
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
        total = per_night

    label = obj.get("rate_name") or obj.get("board") or obj.get("meal") or "Arbitrip"
    return [_rate_row(str(name), per_night, total, str(currency), str(label))]


def _walk_for_rates(node, currency_fallback: str, rows: list[dict], depth: int = 0) -> None:
    if depth > 12:
        return
    if isinstance(node, dict):
        if any(k in node for k in _NAME_KEYS) and any(k in node for k in _PRICE_KEYS):
            rows.extend(_rows_from_room_object(node, currency_fallback))
        for v in node.values():
            _walk_for_rates(v, currency_fallback, rows, depth + 1)
    elif isinstance(node, list):
        for item in node:
            _walk_for_rates(item, currency_fallback, rows, depth + 1)


def parse_api_payloads(payloads: list[dict], nights: int, currency_fallback: str = "ILS") -> list[dict]:
    rows: list[dict] = []
    for payload in payloads:
        _walk_for_rates(payload, currency_fallback, rows)

    deduped: dict[tuple, dict] = {}
    for row in rows:
        key = (row["room_name"], row["per_night"], row["rate_name"])
        if key not in deduped or row["per_night"] < deduped[key]["per_night"]:
            deduped[key] = row

    result = list(deduped.values())
    result.sort(key=lambda x: (x["per_night"], x["room_name"]))
    return result


def _parse_dom_rates(page, currency_fallback: str) -> list[dict]:
    """Fallback: scrape visible room cards when API JSON shape is unknown."""
    rows: list[dict] = []
    cards = page.locator("[class*='room'], [data-testid*='room'], article").all()
    for card in cards[:40]:
        try:
            text = card.inner_text(timeout=500)
        except Exception:
            continue
        if not text or len(text) < 8:
            continue
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if not lines:
            continue
        room_name = lines[0][:120]
        prices = []
        for ln in lines:
            if re.search(r"[\d,.]+\s*(?:₪|EUR|USD|THB|€|\$)", ln) or re.search(r"(?:₪|€|\$)\s*[\d,.]+", ln):
                val = _parse_money(ln)
                if val:
                    prices.append(val)
        if not prices:
            continue
        per_night = min(prices)
        currency = currency_fallback
        if "₪" in text:
            currency = "ILS"
        elif "€" in text or "EUR" in text:
            currency = "EUR"
        elif "THB" in text or "฿" in text:
            currency = "THB"
        elif "$" in text or "USD" in text:
            currency = "USD"
        rows.append(_rate_row(room_name, per_night, max(prices), currency, "Arbitrip"))

    deduped: dict[tuple, dict] = {}
    for row in rows:
        key = (row["room_name"], row["per_night"])
        deduped[key] = row
    result = list(deduped.values())
    result.sort(key=lambda x: x["per_night"])
    return result


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

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel="chrome", headless=True)
        except Exception:
            browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=str(storage), locale="he-IL")
        page = context.new_page()

        def on_response(response):
            if API_HOST not in response.url or response.status != 200:
                return
            ct = response.headers.get("content-type", "")
            if "json" not in ct:
                return
            try:
                api_payloads.append(response.json())
            except Exception:
                pass

        page.on("response", on_response)
        page.goto(url, wait_until="domcontentloaded", timeout=120000)
        page.wait_for_timeout(8000)

        if "htzone.co.il/login" in page.url:
            browser.close()
            raise RuntimeError(
                "Arbitrip session expired — redirected to HTZone login. "
                "Run: python scripts/arbitrip_login.py"
            )

        for sel in ("text=לצפייה בחדרים", "text=View rooms", "button:has-text('חדרים')"):
            try:
                btn = page.locator(sel).first
                if btn.is_visible(timeout=3000):
                    btn.click()
                    page.wait_for_timeout(10000)
                    break
            except Exception:
                pass

        rates = parse_api_payloads(api_payloads, nights=1, currency_fallback=currency)
        if not rates:
            rates = _parse_dom_rates(page, currency)

        debug_path = Path(__file__).resolve().parent / "logs" / "arbitrip_last_capture.json"
        debug_path.parent.mkdir(parents=True, exist_ok=True)
        debug_path.write_text(
            json.dumps({"url": url, "api_payloads": api_payloads, "rates": rates}, indent=2, default=str),
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
