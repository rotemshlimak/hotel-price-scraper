import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

STAYAPI_BASE = "https://api.stayapi.com/v1/marriott/bonvoy"
SHARED_KEYS = ("provider", "hotels", "email", "scraper_mode")

_HEADERS = {
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (compatible; hotel-price-scraper/1.0)",
}


def _api_key() -> str:
    key = os.environ.get("STAYAPI_API_KEY", "").strip()
    if not key:
        raise ValueError(
            "Missing STAYAPI_API_KEY. Add it to .env or set a Windows user environment variable."
        )
    return key


def _request_headers() -> dict:
    return {**_HEADERS, "X-API-Key": _api_key()}


def hotel_configs(config: dict) -> list[dict]:
    defaults = {k: v for k, v in config.items() if k not in SHARED_KEYS}
    if "hotels" in config:
        return [{**defaults, **hotel} for hotel in config["hotels"]]
    return [config]


def _explain_error(status: int, body: str) -> str:
    if "1010" in body or status == 403:
        return (
            f"StayAPI returned {status} (Cloudflare blocked the request).\n"
            "Try:\n"
            "  1. Regenerate your API key at stayapi.com → Dashboard\n"
            "  2. Test the same hotel in StayAPI Playground (browser)\n"
            "  3. Confirm you have credits remaining\n"
            "  4. Use browser mode for now: set \"scraper_mode\": \"browser\" in config.json\n"
            f"Response: {body[:200]}"
        )
    if status == 401:
        return f"StayAPI returned 401 (invalid API key). Regenerate the key in your dashboard.\n{body[:200]}"
    return f"StayAPI error {status}: {body[:500]}"


def _get(path: str, params: dict) -> dict:
    url = f"{STAYAPI_BASE}/{path}?{urlencode(params)}"
    req = Request(url, headers=_request_headers())
    try:
        with urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode())
    except HTTPError as e:
        body = e.read().decode(errors="replace")
        raise RuntimeError(_explain_error(e.code, body)) from e
    except URLError as e:
        raise RuntimeError(f"Network error calling StayAPI: {e.reason}") from e


def test_connection(property_id: str = "HKTKL") -> dict:
    """One cheap API call to verify the key works."""
    return fetch_rooms(
        property_id=property_id,
        check_in="2027-04-14",
        check_out="2027-04-18",
        adults=2,
        currency="THB",
    )


def fetch_rooms(
    property_id: str,
    check_in: str,
    check_out: str,
    adults: int = 2,
    rooms: int = 1,
    currency: str = "THB",
    corporate_code: str = "",
) -> dict:
    params = {
        "property_id": property_id,
        "check_in": check_in,
        "check_out": check_out,
        "adults": adults,
        "rooms": rooms,
        "currency": currency,
    }
    if corporate_code.strip():
        params["corporate_code"] = corporate_code.strip()
    return _get("rooms", params)


_NON_CASH_RATE = re.compile(
    r"points?|redemption|award|bonvoy\s*point|free\s*night",
    re.IGNORECASE,
)


def _is_cash_rate(rate: dict) -> bool:
    """Exclude points-only, cash+points, and award redemption plans."""
    if rate.get("points"):
        return False
    name = rate.get("name") or ""
    code = rate.get("rate_plan_code") or ""
    if _NON_CASH_RATE.search(name) or _NON_CASH_RATE.search(code):
        return False
    per_night = rate.get("per_night")
    return per_night is not None and per_night > 0


def _rate_entry(room: dict, rate: dict) -> dict:
    return {
        "room_name": room.get("name") or "Unknown",
        "bed_type": room.get("bed_type") or "",
        "per_night": rate["per_night"],
        "total": rate.get("total"),
        "currency": rate.get("currency", "THB"),
        "rate_name": rate.get("name"),
        "rate_plan_code": rate.get("rate_plan_code") or "",
    }


def all_room_cash_rates(data: dict) -> list[dict]:
    """Every cash rate for every room type, sorted by per_night."""
    rows = []
    for room in data.get("room_types", []):
        for rate in room.get("rates", []):
            if not _is_cash_rate(rate):
                continue
            rows.append(_rate_entry(room, rate))
    rows.sort(key=lambda x: (x["per_night"], x["room_name"], x["rate_name"] or ""))
    return rows


def room_cash_rates(data: dict) -> list[dict]:
    """Lowest cash rate per room type, sorted by per_night."""
    best_by_room: dict[tuple[str, str], dict] = {}
    for room in data.get("room_types", []):
        for rate in room.get("rates", []):
            if not _is_cash_rate(rate):
                continue
            entry = _rate_entry(room, rate)
            key = (entry["room_name"], entry["bed_type"])
            if key not in best_by_room or entry["per_night"] < best_by_room[key]["per_night"]:
                best_by_room[key] = entry
    rows = list(best_by_room.values())
    rows.sort(key=lambda x: x["per_night"])
    return rows


def lowest_cash_rate(data: dict) -> dict | None:
    rates = all_room_cash_rates(data)
    return rates[0] if rates else None


def lowest_rate(data: dict) -> dict | None:
    return lowest_cash_rate(data)


def scrape_hotel_api(hotel_config: dict) -> dict:
    property_id = hotel_config.get("property_id")
    if not property_id:
        raise ValueError(f"property_id required for {hotel_config['hotel_id']}")

    currency = hotel_config.get("currency", "THB")
    corporate_code = hotel_config.get("corporate_code", "")
    data = fetch_rooms(
        property_id=property_id,
        check_in=hotel_config["check_in_date"],
        check_out=hotel_config["check_out_date"],
        adults=hotel_config.get("adults", 2),
        rooms=hotel_config.get("rooms", 1),
        currency=currency,
        corporate_code=corporate_code,
    )

    best = lowest_rate(data)
    if best:
        rate_str = f"{best['per_night']:,.0f} {best['currency']} / Night"
        if best.get("rate_name"):
            rate_str += f" ({best['rate_name']})"
        return {
            "hotel": hotel_config["hotel_id"],
            "property_id": property_id,
            "check_in": hotel_config["check_in_date"],
            "check_out": hotel_config["check_out_date"],
            "rooms": hotel_config.get("rooms", 1),
            "adults": hotel_config.get("adults", 2),
            "children": hotel_config.get("children", 0),
            "corporate_code": hotel_config.get("corporate_code", ""),
            "source": "stayapi",
            "available": True,
            "rate": rate_str,
            "per_night": best["per_night"],
            "total": best.get("total"),
            "rate_name": best.get("rate_name"),
            "currency": best["currency"],
            "room_types": data.get("total", 0),
            "room_rates": all_room_cash_rates(data),
        }

    return {
        "hotel": hotel_config["hotel_id"],
        "property_id": property_id,
        "check_in": hotel_config["check_in_date"],
        "check_out": hotel_config["check_out_date"],
        "source": "stayapi",
        "available": False,
        "rate": "Rate Unavailable",
        "per_night": None,
        "currency": currency,
    }


def scrape_prices_api(config: dict) -> list[dict]:
    results = [scrape_hotel_api(h) for h in hotel_configs(config)]
    print(json.dumps(results, indent=2))
    return results


def main():
    from env_loader import load_dotenv
    from scraper import load_config

    load_dotenv()
    if os.environ.get("STAYAPI_TEST"):
        print(json.dumps(test_connection(), indent=2)[:2000])
        return
    scrape_prices_api(load_config())


if __name__ == "__main__":
    main()
