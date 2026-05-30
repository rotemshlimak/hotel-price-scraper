import json
import re
from datetime import datetime

from playwright.sync_api import sync_playwright

CONFIG_PATH = "config.json"


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def accept_cookies(page):
    page.wait_for_timeout(1500)
    for sel in (
        "#onetrust-accept-btn-handler",
        'button:has-text("Accept All")',
        'button:has-text("Allow All")',
    ):
        btn = page.locator(sel)
        for i in range(btn.count()):
            try:
                if btn.nth(i).is_visible():
                    btn.nth(i).click(force=True)
                    page.wait_for_timeout(1500)
                    return
            except Exception:
                continue


def fill_destination(page, hotel_name: str):
    dest = page.locator('input[name="input-text-Destination"][placeholder="Where can we take you?"]')
    if dest.count() == 0:
        dest = page.locator('input[name="input-text-Destination"]').first
    dest.click(force=True)
    dest.fill("")
    dest.type(hotel_name, delay=40)
    page.wait_for_timeout(2500)
    option = page.locator('[role="option"]').filter(has_text=re.compile(r"Khao Lak|Marriott", re.I)).first
    option.wait_for(state="visible", timeout=15000)
    option.click(force=True)
    page.wait_for_timeout(800)


def _day_label(dt: datetime) -> str:
    return dt.strftime("%a %b %d %Y")


def _click_day(page, dt: datetime):
    label = _day_label(dt)
    day = page.locator(f'[aria-label="{label}"]:not(.DayPicker-Day--disabled)')
    for _ in range(24):
        if day.count() and day.first.is_visible():
            day.first.click()
            return
        page.locator(".DayPicker-NavButton--next").click()
        page.wait_for_timeout(350)
    raise RuntimeError(f"Could not select date {label}")


def set_dates(page, check_in: str, check_out: str):
    accept_cookies(page)
    check_in_dt = datetime.strptime(check_in, "%Y-%m-%d")
    check_out_dt = datetime.strptime(check_out, "%Y-%m-%d")

    page.locator('input[aria-label="date-picker"]').click(force=True)
    page.wait_for_timeout(1200)
    _click_day(page, check_in_dt)
    page.wait_for_timeout(400)
    _click_day(page, check_out_dt)
    page.wait_for_timeout(400)


def set_guests(page, rooms: int, adults: int, children: int, child_ages: list):
    accept_cookies(page)
    page.locator('[custom_click_track_value*="Rooms and Guests"]').click(force=True)
    page.wait_for_timeout(1200)

    targets = {
        "Rooms": rooms,
        "Adults": adults,
        "Children": children,
    }
    for i, age in enumerate(child_ages[:children], start=1):
        targets[f"Child {i}: Age"] = age

    page.evaluate(
        """(targets) => {
            const adjust = (label, target) => {
                const matches = Array.from(document.querySelectorAll("*"))
                    .filter((el) => el.childElementCount === 0 && el.textContent.trim() === label);
                const labelEl = matches[matches.length - 1];
                if (!labelEl) return;
                let row = labelEl.parentElement;
                while (row && row.querySelectorAll("button").length < 2) row = row.parentElement;
                if (!row) return;
                const buttons = Array.from(row.querySelectorAll("button"));
                const minus = buttons.find((b) => /^-$/.test((b.textContent || "").trim()));
                const plus = buttons.find((b) => /^\\+$/.test((b.textContent || "").trim()));
                const read = () => {
                    const nums = (row.textContent || "").match(/\\b\\d{1,2}\\b/g) || [];
                    return nums.length ? parseInt(nums[nums.length - 1], 10) : null;
                };
                for (let i = 0; i < 15; i++) {
                    const current = read();
                    if (current === null || current === target) return;
                    (current < target ? plus : minus)?.click();
                }
            };
            for (const [label, target] of Object.entries(targets)) adjust(label, target);
        }""",
        targets,
    )
    page.wait_for_timeout(800)
    page.locator('[custom_click_track_value*="Rooms and Guests"]').click(force=True)
    page.wait_for_timeout(500)


def extract_prices(page) -> list[str]:
    page.wait_for_timeout(5000)
    texts = page.locator('[class*="price"], [data-testid*="price"], [class*="rate"]').all_inner_texts()
    prices = []
    for text in texts:
        prices.extend(re.findall(r"(?:[\$€£]|USD|THB|฿)\s*[\d,]+(?:\.\d{2})?", text))
    if not prices:
        body = page.inner_text("body")
        prices = re.findall(r"(?:[\$€£]|USD|THB|฿)\s*[\d,]+(?:\.\d{2})?", body)
    return list(dict.fromkeys(prices))


def scrape_prices(config):
    hotel = config["hotel_id"]
    check_in = config["check_in_date"]
    check_out = config["check_out_date"]
    rooms = config.get("rooms", 1)
    adults = config.get("adults", 2)
    children = config.get("children", 0)
    child_ages = config.get("children_ages", [])

    with sync_playwright() as p:
        # Akamai blocks bundled Chromium; Edge/Chrome in headed mode works on Windows.
        browser = p.chromium.launch(channel="msedge", headless=False)
        page = browser.new_page(viewport={"width": 1920, "height": 1080})
        page.goto("https://www.marriott.com/default.mi", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000)
        accept_cookies(page)

        fill_destination(page, hotel)
        set_dates(page, check_in, check_out)
        set_guests(page, rooms, adults, children, child_ages)

        page.locator('button:has-text("Find Hotels")').click()
        page.wait_for_load_state("networkidle", timeout=120000)
        page.wait_for_timeout(3000)

        # Open the hotel listing if we're on search results.
        hotel_link = page.locator("a").filter(has_text=re.compile(re.escape(hotel.split()[0]), re.I)).first
        if hotel_link.count():
            hotel_link.click()
            page.wait_for_load_state("domcontentloaded", timeout=90000)
            page.wait_for_timeout(5000)

        prices = extract_prices(page)
        result = {
            "hotel": hotel,
            "check_in": check_in,
            "check_out": check_out,
            "rooms": rooms,
            "adults": adults,
            "children": children,
            "url": page.url,
            "prices": prices[:20],
        }
        print(json.dumps(result, indent=2))
        browser.close()
        return result


def main():
    config = load_config()
    scrape_prices(config)


if __name__ == "__main__":
    main()
