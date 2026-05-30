import json
from playwright.sync_api import sync_playwright

CONFIG_PATH = 'config.json'

def load_config():
    with open(CONFIG_PATH, 'r') as f:
        return json.load(f)

def scrape_prices_hilton(config):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        # Example: go to Hilton.com and fill in search
        page.goto('https://www.hilton.com/')
        # Add logic to fill in hotel, dates, guests, etc. using config
        print('Hilton scraping logic to be implemented')
        browser.close()

def main():
    config = load_config()
    scrape_prices_hilton(config)

if __name__ == '__main__':
    main()
