"""Capture Hilton booking GraphQL requests (local discovery helper)."""
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

    def on_request(request):
        url = request.url
        if "graphql" in url or "dx-customer/auth" in url:
            entry = {"url": url, "method": request.method}
            if request.post_data:
                try:
                    entry["body"] = json.loads(request.post_data)
                except json.JSONDecodeError:
                    entry["body_raw"] = request.post_data[:4000]
            captured.append(entry)

    def on_response(response):
        url = response.url
        if "graphql" in url and response.status == 200:
            try:
                data = response.json()
            except Exception:
                return
            captured.append(
                {
                    "url": url,
                    "response_keys": list(data.keys()),
                    "data_keys": list((data.get("data") or {}).keys()),
                    "sample": json.dumps(data)[:5000],
                }
            )

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.on("request", on_request)
        page.on("response", on_response)
        page.goto(BOOKING_URL, wait_until="domcontentloaded", timeout=120000)
        page.wait_for_timeout(15000)
        browser.close()

    out = Path(__file__).resolve().parent.parent / "logs" / "hilton_probe.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(captured, indent=2), encoding="utf-8")
    print(f"Captured {len(captured)} entries -> {out}")
    for item in captured:
        body = item.get("body") or {}
        if body.get("operationName"):
            print("op:", body["operationName"], item["url"][:120])


if __name__ == "__main__":
    main()
