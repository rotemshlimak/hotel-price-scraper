"""Debug Hilton booking page network activity."""
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

BOOKING_URL = (
    "https://www.hilton.com/en/book/reservation/rooms/"
    "?ctyhocn=ATHADQQ&arrivalDate=2027-02-03&departureDate=2027-02-07"
    "&room1NumAdults=2&altCorporateId=Microsoft"
)


def main() -> None:
    captured = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
        )

        def on_request(request):
            url = request.url
            if any(x in url for x in ("hilton.com", "hilton.io", "graphql", "auth")):
                entry = {"url": url[:300], "method": request.method, "resource": request.resource_type}
                if request.post_data and len(request.post_data) < 8000:
                    entry["post"] = request.post_data[:8000]
                captured.append(entry)

        def on_response(response):
            url = response.url
            if "graphql" in url or "dx-customer/auth" in url:
                entry = {"url": url[:300], "status": response.status}
                try:
                    entry["json"] = response.json()
                except Exception:
                    pass
                captured.append(entry)

        page.on("request", on_request)
        page.on("response", on_response)
        resp = page.goto(BOOKING_URL, wait_until="domcontentloaded", timeout=120000)
        print("goto status", resp.status if resp else None)
        page.wait_for_timeout(20000)
        title = page.title()
        html = page.content()
        browser.close()

    out = Path(__file__).resolve().parent.parent / "logs" / "hilton_debug.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "title": title,
        "html_len": len(html),
        "has_app_id": "DX_AUTH_API_CUSTOMER_APP_ID" in html,
        "has_graphql": "graphql" in html.lower(),
        "requests": captured,
    }
    out.write_text(json.dumps(payload, indent=2)[:200000], encoding="utf-8")
    print("saved", out, "requests", len(captured), "title", title)
    for item in captured:
        if "graphql" in item.get("url", "") or "auth" in item.get("url", ""):
            print(item.get("url", "")[:120], item.get("status"), item.get("method"))


if __name__ == "__main__":
    main()
