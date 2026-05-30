import json
from scraper import scrape_prices as scrape_marriott
from scraper_hilton import scrape_prices_hilton

CONFIG_PATH = 'config.json'

def load_config():
    with open(CONFIG_PATH, 'r') as f:
        return json.load(f)

def main():
    config = load_config()
    provider = config.get('provider', 'marriott').lower()
    if provider == 'marriott':
        scrape_marriott(config)
    elif provider == 'hilton':
        scrape_prices_hilton(config)
    else:
        print(f"Provider '{provider}' not supported.")

if __name__ == '__main__':
    main()
