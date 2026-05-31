import json

from env_loader import load_dotenv

CONFIG_PATH = "config.json"

load_dotenv()


def load_config_local():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    config = load_config_local()
    provider = config.get("provider", "marriott").lower()
    mode = config.get("scraper_mode", "browser").lower()

    if provider == "marriott":
        if mode == "api":
            from scraper_api import scrape_prices_api

            scrape_prices_api(config)
        else:
            from scraper import scrape_prices

            scrape_prices(config)
    else:
        print(f"Provider '{provider}' not supported.")


if __name__ == "__main__":
    main()
