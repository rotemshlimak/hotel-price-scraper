"""Capture Hilton booking GraphQL — tries multiple browser strategies."""
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BOOKING_URL = (
    "https://www.hilton.com/en/book/reservation/rooms/"
    "?ctyhocn=ATHADQQ&arrivalDate=2027-02-03&departureDate=2027-02-07"
    "&room1NumAdults=2&altCorporateId=Microsoft"
)
HOME_URL = "https://www.hilton.com/en/"


def capture(launch_kwargs: dict, label: str) -> tuple[list, str, int | None]:
    captured: list = []

    with sync_playwright() as p:
        browser = p.chromium.launch(**launch_kwargs)
        context = browser.new_context(
            locale="en-US",
            timezone_id="Europe/Athens",
            viewport={"width": 1366, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()
        page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
        )

        def on_request(request):
            url = request.url
            if "graphql" in url or "dx-customer/auth" in url:
                entry = {"url": url, "method": request.method, "strategy": label}
                if request.post_data:
                    try:
                        entry["body"] = json.loads(request.post_data)
                    except json.JSONDecodeError:
                        entry["body_raw"] = request.post_data[:8000]
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
                        "status": response.status,
                        "strategy": label,
                        "response_data_keys": list((data.get("data") or {}).keys()),
                        "errors": data.get("errors"),
                        "sample": json.dumps(data)[:8000],
                    }
                )

        page.on("request", on_request)
        page.on("response", on_response)

        # Warm up session on homepage first
        home = page.goto(HOME_URL, wait_until="domcontentloaded", timeout=90000)
        page.wait_for_timeout(3000)
        booking = page.goto(BOOKING_URL, wait_until="domcontentloaded", timeout=90000)
        page.wait_for_timeout(25000)

        title = page.title()
        status = booking.status if booking else None
        html_snip = page.content()[:500]
        browser.close()

    return captured, title, status


def main() -> None:
    strategies = [
        ({"channel": "msedge", "headless": False}, "msedge_headed"),
        ({"channel": "chrome", "headless": False}, "chrome_headed"),
        ({"headless": True}, "chromium_headless"),
    ]

    all_captured: list = []
    report = []

    for launch_kwargs, label in strategies:
        print(f"\n--- Trying {label} ---")
        try:
            captured, title, status = capture(launch_kwargs, label)
            print(f"status={status} title={title!r} captured={len(captured)}")
            report.append({"strategy": label, "status": status, "title": title, "count": len(captured)})
            all_captured.extend(captured)
            if any("graphql" in c.get("url", "") and c.get("body") for c in captured):
                print(f"Success with {label}")
                break
        except Exception as e:
            print(f"Failed {label}: {e}")
            report.append({"strategy": label, "error": str(e)})

    out = Path(__file__).resolve().parent.parent / "logs" / "hilton_probe.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {"report": report, "captured": all_captured}
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nSaved -> {out}")

    for item in all_captured:
        body = item.get("body") or {}
        op = body.get("operationName")
        if op:
            print(f"  operationName={op}")
            vars_preview = json.dumps(body.get("variables", {}))[:200]
            print(f"  variables={vars_preview}")

    if not any(item.get("body", {}).get("operationName") for item in all_captured):
        print("\nNo GraphQL shop calls captured. Hilton likely blocked this session (403/Akamai).")
        print("Try manually in Chrome DevTools and paste the graphql/customer request body.")
        sys.exit(1)


if __name__ == "__main__":
    main()
