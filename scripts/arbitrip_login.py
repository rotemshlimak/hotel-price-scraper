"""Open HTZone login in a browser and save Arbitrip session for the scraper."""
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent.parent / "logs" / "arbitrip_storage.json"
START_URL = "https://htzone.arbitrip.com/"


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    print("Log in via HTZone in the browser window.")
    print("After you reach the Arbitrip / TripZone home page, press Enter here to save the session.")
    print(f"Session will be saved to: {OUT}")

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel="chrome", headless=False)
        except Exception:
            browser = p.chromium.launch(headless=False)
        context = browser.new_context(locale="he-IL")
        page = context.new_page()
        page.goto(START_URL, wait_until="domcontentloaded", timeout=120000)
        input("Press Enter when logged in and Arbitrip is loaded... ")
        context.storage_state(path=str(OUT))
        browser.close()

    print(f"Saved session -> {OUT}")
    print("Add to .env (optional): ARBITRIP_STORAGE_STATE=logs/arbitrip_storage.json")


if __name__ == "__main__":
    main()
