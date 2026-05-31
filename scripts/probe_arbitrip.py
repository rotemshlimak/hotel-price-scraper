"""Capture network requests from htzone.arbitrip.com (discovery helper)."""
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE_URL = "https://htzone.arbitrip.com/"


def main() -> None:
    captured = []

    def on_request(request):
        url = request.url
        if "arbitrip" not in url and "htzone" not in url:
            return
        if any(x in url for x in (".js", ".css", ".png", ".jpg", ".woff", ".svg", "google", "analytics")):
            return
        entry = {"url": url, "method": request.method}
        if request.post_data:
            try:
                entry["body"] = json.loads(request.post_data)
            except json.JSONDecodeError:
                entry["body_raw"] = request.post_data[:2000]
        captured.append(entry)

    def on_response(response):
        url = response.url
        if "arbitrip" not in url:
            return
        if response.status != 200:
            return
        ct = response.headers.get("content-type", "")
        if "json" not in ct:
            return
        try:
            data = response.json()
        except Exception:
            return
        captured.append(
            {
                "url": url,
                "response_keys": list(data.keys()) if isinstance(data, dict) else type(data).__name__,
                "sample": json.dumps(data)[:3000],
            }
        )

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel="chrome", headless=True)
        except Exception:
            browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.on("request", on_request)
        page.on("response", on_response)
        page.goto(BASE_URL, wait_until="networkidle", timeout=120000)
        page.wait_for_timeout(5000)
        title = page.title()
        print("title:", title.encode("ascii", "replace").decode())
        print("url:", page.url)
        browser.close()

    out = Path(__file__).resolve().parent.parent / "logs" / "arbitrip_probe.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(captured, indent=2), encoding="utf-8")
    print(f"Captured {len(captured)} entries -> {out}")
    for item in captured[:20]:
        print(item.get("method", "GET"), item["url"][:100])


if __name__ == "__main__":
    main()
