import json
import re
from datetime import datetime
from urllib.parse import urlencode

from playwright.sync_api import sync_playwright

CONFIG_PATH = "config.json"
SEARCH_BASE = "https://www.marriott.com/search/findHotels.mi"

SHARED_KEYS = ("provider", "hotels", "email")


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def hotel_configs(config: dict) -> list[dict]:
    defaults = {k: v for k, v in config.items() if k not in SHARED_KEYS}
    if "hotels" in config:
        return [{**defaults, **hotel} for hotel in config["hotels"]]
    return [config]


def _marriott_date(iso_date: str) -> str:
    return datetime.strptime(iso_date, "%Y-%m-%d").strftime("%m/%d/%Y")


def build_search_url(hotel_config: dict) -> str:
    """Build a Marriott findHotels.mi URL from a hotel entry (same format as the browser)."""
    if hotel_config.get("search_url"):
        return hotel_config["search_url"]

    check_in = hotel_config["check_in_date"]
    check_out = hotel_config["check_out_date"]
    from_date = _marriott_date(check_in)
    to_date = _marriott_date(check_out)
    nights = (
        datetime.strptime(check_out, "%Y-%m-%d") - datetime.strptime(check_in, "%Y-%m-%d")
    ).days

    rooms = hotel_config.get("rooms", 1)
    adults = hotel_config.get("adults", 2)
    children = hotel_config.get("children", 0)
    corporate_code = hotel_config.get("corporate_code", "").strip()
    dest = hotel_config["destination"]

    params = {
        "fromToDate_submit": to_date,
        "fromDate": from_date,
        "toDate": to_date,
        "toDateDefaultFormat": to_date,
        "fromDateDefaultFormat": from_date,
        "flexibleDateSearch": "false",
        "t-start": from_date,
        "t-end": to_date,
        "lengthOfStay": str(nights),
        "childrenCountBox": f"{children} Children Per Room",
        "childrenCount": str(children),
        "clusterCode": "corp" if corporate_code else "none",
        "useRewardsPoints": "false",
        "isAdvanceSearch": "false",
        "isNGSF": "false",
        "recordsPerPage": "20",
        "destinationAddress.type": "Hotel Name",
        "destinationAddress.latitude": str(dest["latitude"]),
        "destinationAddress.longitude": str(dest["longitude"]),
        "destinationAddress.placeId": dest["place_id"],
        "destinationAddress.mainText": dest["main_text"],
        "destinationAddress.destination": dest["destination"],
        "destinationAddress.city": dest["city"],
        "destinationAddress.country": dest["country"],
        "destinationAddress.address": dest["address"],
        "destinationAddress.secondaryText": dest["secondary_text"],
        "destinationAddress.stateProvince": dest.get("state_province", ""),
        "destinationAddress.stateProvinceDisplayName": dest.get("state_province", ""),
        "countryName": dest.get("country_name", dest["country"]),
        "isInternalSearch": "true",
        "vsInitialRequest": "false",
        "searchType": "InCity",
        "searchRadius": "50",
        "singleSearchAutoSuggest": "Unmatched",
        "for-hotels-nearme": "Near",
        "collapseAccordian": "is-hidden",
        "singleSearch": "true",
        "isTransient": "true",
        "initialRequest": "false",
        "flexibleDateSearchRateDisplay": "false",
        "isSearch": "true",
        "isRateCalendar": "false",
        "isHideFlexibleDateCalendar": "false",
        "roomCountBox": f"{rooms} Room" if rooms == 1 else f"{rooms} Rooms",
        "roomCount": str(rooms),
        "guestCountBox": f"{adults} Adult Per Room" if adults == 1 else f"{adults} Adults Per Room",
        "numAdultsPerRoom": str(adults),
        "deviceType": "desktop-web",
        "view": "list",
    }

    if corporate_code:
        params["corporateCode"] = corporate_code

    return f"{SEARCH_BASE}?{urlencode(params)}#/0/"


def accept_cookies(page):
    for sel in ("#onetrust-accept-btn-handler", 'button:has-text("Accept All")'):
        btn = page.locator(sel)
        if btn.count() and btn.first.is_visible():
            btn.first.click(force=True)
            page.wait_for_timeout(1500)
            return


def extract_hotel_rate(page, hotel_name: str) -> dict:
    page.wait_for_timeout(3000)
    body = page.inner_text("body")

    short_name = hotel_name.split("&")[0].strip()
    pattern = re.compile(
        rf"{re.escape(short_name)}.*?(?:([\d,]+)\s*THB\s*/?\s*Night|Rate Unavailable)",
        re.IGNORECASE | re.DOTALL,
    )
    match = pattern.search(body)
    if match:
        if match.group(1):
            per_night = float(match.group(1).replace(",", ""))
            return {
                "available": True,
                "rate": f"{match.group(1)} THB / Night",
                "per_night": per_night,
                "currency": "THB",
            }
        return {"available": False, "rate": "Rate Unavailable", "per_night": None}

    rates = re.findall(r"([\d,]+)\s*THB\s*/?\s*Night", body, re.IGNORECASE)
    if rates:
        per_night = float(rates[0].replace(",", ""))
        return {
            "available": True,
            "rate": f"{rates[0]} THB / Night",
            "per_night": per_night,
            "currency": "THB",
        }

    return {"available": False, "rate": None, "per_night": None}


def scrape_hotel(page, hotel_config: dict) -> dict:
    hotel = hotel_config["hotel_id"]
    page.wait_for_timeout(10000)
    rate_info = extract_hotel_rate(page, hotel)
    return {
        "hotel": hotel,
        "property_id": hotel_config.get("property_id", ""),
        "check_in": hotel_config["check_in_date"],
        "check_out": hotel_config["check_out_date"],
        "rooms": hotel_config.get("rooms", 1),
        "adults": hotel_config.get("adults", 2),
        "children": hotel_config.get("children", 0),
        "corporate_code": hotel_config.get("corporate_code", ""),
        "source": "browser",
        "url": page.url,
        **rate_info,
    }


def scrape_prices(config):
    """Scrape one or more hotels. Reuses a single browser session."""
    hotels = hotel_configs(config)
    results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=False)
        page = browser.new_page(viewport={"width": 1920, "height": 1080})
        cookies_accepted = False

        for hotel_config in hotels:
            page.goto(build_search_url(hotel_config), wait_until="domcontentloaded", timeout=120000)
            if not cookies_accepted:
                accept_cookies(page)
                cookies_accepted = True
            results.append(scrape_hotel(page, hotel_config))

        browser.close()

    print(json.dumps(results, indent=2))
    return results


def main():
    config = load_config()
    scrape_prices(config)


if __name__ == "__main__":
    main()
