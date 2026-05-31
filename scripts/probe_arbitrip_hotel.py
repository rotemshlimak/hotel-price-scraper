"""Probe a specific Arbitrip hotel URL and capture api.arbitrip.com traffic."""
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

DEFAULT_URL = (
    "https://htzone.arbitrip.com/hotel/the-little-shore-khao-lak-by-katathani/658eb11866f44b0744e1b1df"
    "?hotel_id=658eb11866f44b0744e1b1df&check_in=270414&check_out=270418&guests=2&rooms=1"
    "&private_travel=true&search_token=ace8726c829906c45677-NjU4ZWIxMTg2NmY0NGIwNzQ0ZTFiMWRmfDI3MDQxNHwyNzA0MTh8Mnx8dHJ1ZXwxfA%3D%3D"
)


def main() -> None:
    target = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL
    captured = []

    def on_response(response):
        url = response.url
        if "api.arbitrip.com" not in url:
            return
        entry = {"url": url, "status": response.status, "method": response.request.method}
        if response.status == 200:
            ct = response.headers.get("content-type", "")
            if "json" in ct:
                try:
                    data = response.json()
                    entry["json"] = data
                    entry["sample"] = json.dumps(data)[:4000]
                except Exception as e:
                    entry["parse_error"] = str(e)
        captured.append(entry)

    storage = Path(__file__).resolve().parent.parent / "logs" / "arbitrip_storage.json"
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel="chrome", headless=True)
        except Exception:
            browser = p.chromium.launch(headless=True)
        context_kwargs = {"locale": "he-IL"}
        if storage.exists():
            context_kwargs["storage_state"] = str(storage)
        context = browser.new_context(**context_kwargs)
        page = context.new_page()
        page.on("response", on_response)
        page.goto(target, wait_until="domcontentloaded", timeout=120000)
        page.wait_for_timeout(15000)
        # try clicking "view rooms" if present
        for sel in ('text=לצפייה בחדרים', 'text=View rooms', '[data-testid*="room"]'):
            try:
                btn = page.locator(sel).first
                if btn.is_visible(timeout=2000):
                    btn.click()
                    page.wait_for_timeout(8000)
                    break
            except Exception:
                pass
        title = page.title().encode("ascii", "replace").decode()
        print("title:", title)
        print("url:", page.url)
        browser.close()

    out = Path(__file__).resolve().parent.parent / "logs" / "arbitrip_hotel_probe.json"
    out.write_text(json.dumps(captured, indent=2, default=str), encoding="utf-8")
    print(f"Captured {len(captured)} api.arbitrip.com responses -> {out}")
    for item in captured:
        print(item["status"], item["method"], item["url"][:120])


if __name__ == "__main__":
    main()
