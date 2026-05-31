"""Open HTZone login in a browser and save Arbitrip session for the scraper."""

import argparse

import json

import sys

import time

from pathlib import Path



sys.path.insert(0, str(Path(__file__).resolve().parent.parent))



from playwright.sync_api import sync_playwright



from arbitrip_auth import START_URL, is_login_page, session_authenticated, session_status

from scraper_arbitrip import build_hotel_url


def _is_hotel_page(url: str) -> bool:
    return "htzone.arbitrip.com/hotel/" in url.lower()



OUT = Path(__file__).resolve().parent.parent / "logs" / "arbitrip_storage.json"

CONFIG = Path(__file__).resolve().parent.parent / "config.json"





def _hotel_verify_url(cli_url: str | None) -> str | None:

    if cli_url:

        return cli_url.strip()

    if not CONFIG.is_file():

        return None

    try:

        config = json.loads(CONFIG.read_text(encoding="utf-8"))

    except json.JSONDecodeError:

        return None

    for hotel in config.get("hotels") or []:

        if (hotel.get("chain") or "").lower() != "arbitrip":

            continue

        if hotel.get("booking_url"):

            return hotel["booking_url"].strip()

        try:

            return build_hotel_url(hotel)

        except ValueError:

            return None

    return None





def main() -> None:

    parser = argparse.ArgumentParser(description="Save HTZone/Arbitrip Playwright session")

    parser.add_argument("--wait-seconds", type=int, default=180)

    parser.add_argument(

        "--manual",

        action="store_true",

        help="Wait for Enter key, then verify auth before saving",

    )

    parser.add_argument(

        "--verify-url",

        metavar="URL",

        help="Arbitrip hotel URL with search_token (default: first arbitrip hotel in config.json)",

    )

    args = parser.parse_args()

    verify_url = _hotel_verify_url(args.verify_url)



    OUT.parent.mkdir(parents=True, exist_ok=True)

    print(f"Session will be saved to: {OUT}")

    print("Log in via HTZone in Chrome — leave the window open until this finishes.")

    if verify_url:

        print(f"After login, will open hotel page to capture Arbitrip session:\n  {verify_url[:100]}...")

    else:

        print(

            "Tip: add booking_url (full browser URL with search_token) for an arbitrip hotel "

            "in config.json so this script verifies the hotel page before saving."

        )



    with sync_playwright() as p:

        try:

            browser = p.chromium.launch(channel="chrome", headless=False)

        except Exception:

            browser = p.chromium.launch(headless=False)

        context = browser.new_context(locale="he-IL")

        page = context.new_page()

        page.goto(START_URL, wait_until="domcontentloaded", timeout=120000)



        if args.manual and sys.stdin.isatty():

            input("Press Enter when logged in... ")

        else:

            deadline = time.time() + args.wait_seconds

            print(f"Waiting up to {args.wait_seconds}s for authenticated session...")

            while time.time() < deadline:

                ok, detail = session_authenticated(context, page.url)

                if ok:

                    print("Login detected:", detail, f"({page.url[:70]})")

                    break

                time.sleep(2)

            else:

                browser.close()

                raise SystemExit(

                    f"Timed out after {args.wait_seconds}s — {session_status(context, page.url)}. "

                    "Complete HTZone login in Chrome, then run:\n"

                    "  python scripts/arbitrip_login.py --wait-seconds 120"

                )



        if verify_url:

            print("Opening hotel page (required for room rates)...")

            page.goto(verify_url, wait_until="networkidle", timeout=120000)

            page.wait_for_timeout(8000)

            if not _is_hotel_page(page.url):

                msg = session_status(context, page.url)

                browser.close()

                raise SystemExit(

                    "Could not reach Arbitrip hotel page — session not saved.\n"

                    f"Got: {page.url}\n({msg})\n"

                    "Paste your full browser URL (with search_token) as booking_url in config.json, "

                    "then run this script again."

                )

            print("Hotel page OK:", page.url[:90])

        else:

            print("Opening Arbitrip to capture session cookies...")

            page.goto(START_URL, wait_until="domcontentloaded", timeout=120000)

            page.wait_for_timeout(5000)



        if is_login_page(page.url):

            msg = session_status(context, page.url)

            browser.close()

            raise SystemExit(

                "Redirected to HTZone login — session not saved. "

                f"({msg})\n"

                "Run: python scripts/arbitrip_login.py --wait-seconds 120"

            )



        ok, detail = session_authenticated(context, page.url)

        if not ok:

            msg = session_status(context, page.url)

            browser.close()

            raise SystemExit(

                "Authentication not verified — session not saved. "

                f"({msg})\n"

                "Run: python scripts/arbitrip_login.py --wait-seconds 120"

            )



        print("Verified:", detail)

        context.storage_state(path=str(OUT))

        browser.close()



    size = OUT.stat().st_size

    print(f"Saved session -> {OUT} ({size} bytes)")

    if size < 1500:

        print("Warning: session file is small — if scraping fails, log in again and retry.")

    print("Next: .\\scripts\\setup_github_secrets.ps1")





if __name__ == "__main__":

    main()

