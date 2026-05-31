"""Fetch Hilton room rates via consumer GraphQL (dx-res-ui / getShopAvail)."""
import json
import os
import re
from datetime import date
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

RES_APP = "dx-res-ui"
RES_APP_VERSION = os.environ.get("HILTON_APP_VERSION", "dx-res-ui:888446")
GRAPHQL_URL = "https://www.hilton.com/graphql/customer"
TOKEN_URL = "https://www.hilton.com/dx-customer/auth/applications/token"
HOME_URL = "https://www.hilton.com/en/"
QUERY_PATH = Path(__file__).resolve().parent / "hilton_shop_query.graphql"

GQL_OPERATION = "hotel_shopAvailOptions_shopPropAvail"
GQL_ORIGINAL_OP = "getShopAvail"

_HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
}

_NON_CASH_RATE = re.compile(
    r"points?|redemption|award|honors\s*point|free\s*night",
    re.IGNORECASE,
)

_SHOP_QUERY = QUERY_PATH.read_text(encoding="utf-8").strip()

_SPECIAL_RATES_TEMPLATE = {
    "aaa": False,
    "governmentMilitary": False,
    "hhonors": False,
    "lta": False,
    "senior": False,
    "teamMember": False,
    "owner": False,
    "ownerHGV": False,
    "familyAndFriends": False,
    "travelAgent": False,
    "smb": False,
    "specialOffer": False,
    "specialOfferName": None,
}


def _booking_page_url(hotel_config: dict) -> str:
    ctyhocn = hotel_config["property_id"]
    check_in = hotel_config["check_in_date"]
    check_out = hotel_config["check_out_date"]
    adults = hotel_config.get("adults", 2)
    corp = hotel_config.get("corporate_code", "")
    params = {
        "ctyhocn": ctyhocn,
        "arrivalDate": check_in,
        "departureDate": check_out,
        "room1NumAdults": str(adults),
    }
    if corp.strip():
        params["altCorporateId"] = corp.strip()
    return f"https://www.hilton.com/en/book/reservation/rooms/?{urlencode(params)}"


def _http_json(method: str, url: str, headers: dict | None = None, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = Request(url, data=data, headers={**_HEADERS, **(headers or {})}, method=method)
    try:
        with urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode())
    except HTTPError as e:
        err_body = e.read().decode(errors="replace")
        raise RuntimeError(f"Hilton HTTP {e.code}: {err_body[:500]}") from e
    except URLError as e:
        raise RuntimeError(f"Hilton network error: {e.reason}") from e


def _extract_app_id(html: str) -> str:
    for pat in (
        r'DX_AUTH_API_CUSTOMER_APP_ID["\']?\s*[:=]\s*["\']([0-9a-f-]{36})',
        r'"app_id"\s*:\s*"([0-9a-f-]{36})"',
    ):
        m = re.search(pat, html, re.I)
        if m:
            return m.group(1)
    raise RuntimeError("Could not find DX_AUTH_API_CUSTOMER_APP_ID on Hilton page.")


def _get_app_id(hotel_config: dict) -> str:
    override = os.environ.get("HILTON_APP_ID", "").strip()
    if override:
        return override

    for page_url in (_booking_page_url(hotel_config), HOME_URL):
        req = Request(page_url, headers={"User-Agent": _HEADERS["User-Agent"]})
        try:
            with urlopen(req, timeout=60) as resp:
                html = resp.read().decode(errors="replace")
        except HTTPError as e:
            if e.code == 403:
                continue
            raise
        if "Page Reference Code" not in html and "DX_AUTH_API_CUSTOMER_APP_ID" in html:
            return _extract_app_id(html)

    raise RuntimeError(
        "Hilton returned 403 or blocked page — cannot obtain app token. "
        "Set HILTON_APP_ID in .env if you captured it from DevTools."
    )


def _get_token(app_id: str) -> str:
    url = f"{TOKEN_URL}?{urlencode({'appName': RES_APP})}"
    data = _http_json("POST", url, headers={"x-dtpc": "ignore"}, body={"app_id": app_id})
    token = data.get("access_token")
    if not token:
        raise RuntimeError(f"Hilton auth failed: {json.dumps(data)[:300]}")
    return token


def _shop_variables(hotel_config: dict, cache_id: str) -> dict:
    corp = (hotel_config.get("corporate_code") or "").strip() or "Microsoft"
    children = hotel_config.get("children", 0)
    child_ages = hotel_config.get("children_ages")
    if not children:
        child_ages = None

    special_rates = {**_SPECIAL_RATES_TEMPLATE, "pnd": corp}
    currency = hotel_config.get("currency")

    return {
        "guestLocationCountry": hotel_config.get("guest_country")
        or os.environ.get("HILTON_GUEST_COUNTRY", "IL"),
        "arrivalDate": hotel_config["check_in_date"],
        "departureDate": hotel_config["check_out_date"],
        "numAdults": hotel_config.get("adults", 2),
        "numChildren": children,
        "numRooms": hotel_config.get("rooms", 1),
        "displayCurrency": currency or None,
        "ctyhocn": hotel_config["property_id"][:5],
        "language": "en",
        "guestId": None,
        "specialRates": special_rates,
        "rateCategoryTokens": None,
        "selectedRoomRateCodes": None,
        "ratePlanCodes": None,
        "pnd": corp,
        "cacheId": cache_id,
        "offerId": None,
        "knownGuest": False,
        "modifyingReservation": False,
        "currentlySelectedRoomTypeCode": None,
        "currentlySelectedRatePlanCode": None,
        "childAges": child_ages,
        "adjoiningRoomStay": False,
        "programAccountId": None,
        "roomTypeSortInput": [],
        "includeCUCEligibility": False,
    }


def _graphql_http(token: str, ctyhocn: str, variables: dict, hotel_config: dict) -> dict:
    url = _graphql_url(ctyhocn)
    referer = _booking_page_url(hotel_config)
    headers = {
        "Authorization": f"Bearer {token}",
        "Origin": "https://www.hilton.com",
        "Referer": referer,
        "Accept-Language": "en-US,en;q=0.9",
        "dx-platform": "web",
    }
    return _http_json("POST", url, headers=headers, body=_graphql_body(variables))


def _graphql(token: str, ctyhocn: str, variables: dict, hotel_config: dict) -> dict:
    try:
        return _graphql_http(token, ctyhocn, variables, hotel_config)
    except RuntimeError as e:
        if "403" not in str(e):
            raise
        raw = _capture_shop_via_playwright(hotel_config, expect_response=True)
        if not raw:
            raise RuntimeError(
                "Hilton GraphQL blocked (403) and Playwright capture failed. "
                "Run from your PC with Chrome installed."
            ) from e
        return raw


def _graphql_url(ctyhocn: str) -> str:
    qs = urlencode(
        {
            "appName": RES_APP,
            "appVersion": RES_APP_VERSION,
            "operationName": GQL_OPERATION,
            "originalOpName": GQL_ORIGINAL_OP,
            "bl": "en",
            "ctyhocn": ctyhocn[:5],  # URL uses short prefix per DevTools capture
        }
    )
    return f"{GRAPHQL_URL}?{qs}"


def _graphql_body(variables: dict) -> dict:
    return {
        "operationName": GQL_OPERATION,
        "variables": variables,
        "query": _SHOP_QUERY,
    }


def _capture_shop_via_playwright(hotel_config: dict, expect_response: bool = False) -> dict:
    """Load booking page in Chrome and capture getShopAvail request/response."""
    from playwright.sync_api import sync_playwright

    booking_url = _booking_page_url(hotel_config)
    captured_request: dict = {}
    captured_response: dict | None = None
    gql_pattern = re.compile(r"shopPropAvail|getShopAvail")

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel="chrome", headless=True)
        except Exception:
            browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            locale="en-US",
            user_agent=_HEADERS["User-Agent"],
        )
        page = context.new_page()

        def on_request(request):
            if not gql_pattern.search(request.url) or not request.post_data:
                return
            try:
                body = json.loads(request.post_data)
            except json.JSONDecodeError:
                return
            captured_request.update(body.get("variables") or {})

        page.on("request", on_request)

        try:
            with page.expect_response(
                lambda r: gql_pattern.search(r.url) and r.status == 200,
                timeout=90000,
            ) as resp_info:
                page.goto(booking_url, wait_until="networkidle", timeout=120000)
            if expect_response:
                captured_response = resp_info.value.json()
        except Exception:
            page.goto(booking_url, wait_until="domcontentloaded", timeout=120000)
            page.wait_for_timeout(25000)

        browser.close()

    if expect_response and captured_response:
        return captured_response
    return captured_request


def _get_token_for_hotel(hotel_config: dict, app_id: str) -> str:
    override = os.environ.get("HILTON_ACCESS_TOKEN", "").strip()
    if override:
        return override
    return _get_token(app_id)


def _parse_money(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).replace(",", "")
    m = re.search(r"\d+(?:\.\d+)?", text)
    return float(m.group(0)) if m else None


def _bed_label(num_beds: int | None) -> str:
    if not num_beds:
        return ""
    if num_beds == 1:
        return "1 bed"
    return f"{num_beds} beds"


def _rate_rows_from_slot(
    room: dict, slot: dict | None, currency: str, nights: int, label: str
) -> dict | None:
    if not slot or not slot.get("rateAmount"):
        return None
    if slot.get("pointDetails"):
        return None
    name = (slot.get("ratePlan") or {}).get("ratePlanName") or slot.get("ratePlanCode") or label
    code = slot.get("ratePlanCode") or ""
    if _NON_CASH_RATE.search(name) or _NON_CASH_RATE.search(code):
        return None
    per_night = float(slot["rateAmount"])
    total = _parse_money(slot.get("fullAmountAfterTax")) or (per_night * nights)
    return {
        "room_name": room.get("roomTypeName") or room.get("roomTypeCode") or "Unknown",
        "bed_type": _bed_label(room.get("numBeds")),
        "per_night": per_night,
        "total": total,
        "currency": currency,
        "rate_name": name,
        "rate_plan_code": code,
    }


def parse_shop_response(data: dict, nights: int, currency_fallback: str = "EUR") -> dict:
    """Parse getShopAvail GraphQL response into normalized shop dict."""
    hotel = (data.get("data") or {}).get("hotel") or data.get("hotel") or data
    shop = hotel.get("shopAvail") or {}
    currency = shop.get("currencyCode") or currency_fallback
    rows: list[dict] = []

    for room in shop.get("roomTypes") or []:
        if room.get("redemptionRoomRates"):
            continue
        for slot_name in ("quickBookRate", "moreRatesFromRate"):
            row = _rate_rows_from_slot(room, room.get(slot_name), currency, nights, slot_name)
            if row:
                rows.append(row)

    rows.sort(key=lambda x: (x["per_night"], x["room_name"], x["rate_name"]))
    return {"currencyCode": currency, "roomTypes": shop.get("roomTypes") or [], "rates": rows}


def all_room_cash_rates(shop: dict, nights: int) -> list[dict]:
    if "rates" in shop:
        return shop["rates"]
    return parse_shop_response({"hotel": shop}, nights).get("rates", [])


def lowest_cash_rate(shop: dict, nights: int) -> dict | None:
    rates = all_room_cash_rates(shop, nights)
    return rates[0] if rates else None


def fetch_rooms(hotel_config: dict) -> dict:
    cache_id = os.environ.get("HILTON_CACHE_ID", "").strip()
    raw: dict | None = None

    if cache_id:
        app_id = _get_app_id(hotel_config)
        token = _get_token_for_hotel(hotel_config, app_id)
        variables = _shop_variables(hotel_config, cache_id)
        try:
            raw = _graphql(token, hotel_config["property_id"], variables, hotel_config)
        except RuntimeError:
            raw = None

    if raw is None:
        raw = _capture_shop_via_playwright(hotel_config, expect_response=True)
        if not raw:
            raise RuntimeError(
                "Could not fetch Hilton rates via HTTP or Playwright. "
                "Ensure Chrome is installed and the booking page loads in browser."
            )
    if raw.get("errors"):
        raise RuntimeError(f"Hilton GraphQL errors: {json.dumps(raw['errors'])[:800]}")
    hotel = (raw.get("data") or {}).get("hotel")
    if not hotel or not hotel.get("shopAvail"):
        raise RuntimeError(f"Unexpected Hilton GraphQL response: {json.dumps(raw)[:800]}")
    nights = max(
        (date.fromisoformat(hotel_config["check_out_date"]) - date.fromisoformat(hotel_config["check_in_date"])).days,
        1,
    )
    parsed = parse_shop_response(raw, nights, hotel_config.get("currency", "EUR"))
    parsed["roomTypes"] = hotel["shopAvail"].get("roomTypes") or []
    return parsed


def scrape_hotel_hilton(hotel_config: dict) -> dict:
    property_id = hotel_config.get("property_id")
    if not property_id:
        raise ValueError(f"property_id (ctyhocn) required for {hotel_config.get('hotel_id')}")

    currency = hotel_config.get("currency", "EUR")
    check_in = hotel_config["check_in_date"]
    check_out = hotel_config["check_out_date"]
    nights = max((date.fromisoformat(check_out) - date.fromisoformat(check_in)).days, 1)

    shop = fetch_rooms(hotel_config)
    best = lowest_cash_rate(shop, nights)
    room_rates = all_room_cash_rates(shop, nights)

    base = {
        "hotel": hotel_config["hotel_id"],
        "property_id": property_id,
        "check_in": check_in,
        "check_out": check_out,
        "rooms": hotel_config.get("rooms", 1),
        "adults": hotel_config.get("adults", 2),
        "children": hotel_config.get("children", 0),
        "corporate_code": hotel_config.get("corporate_code", ""),
        "source": "hilton_graphql",
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
            "room_types": len(shop.get("roomTypes") or []),
            "room_rates": room_rates,
        }

    return {
        **base,
        "available": False,
        "rate": "Rate Unavailable",
        "per_night": None,
    }
