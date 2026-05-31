"""Scrape hotel prices and email only when price drops."""
from daily_run import run_daily_check
from env_loader import load_dotenv
from scraper import load_config

load_dotenv()


def scrape_prices(config: dict) -> list:
    provider = config.get("provider", "marriott").lower()
    if provider == "mixed":
        from scraper_mixed import scrape_prices_mixed

        return scrape_prices_mixed(config)
    if provider == "arbitrip":
        from scraper_arbitrip import scrape_prices_arbitrip

        return scrape_prices_arbitrip(config)
    from scraper_api import scrape_prices_api

    return scrape_prices_api(config)


def main():
    config = load_config()
    results = scrape_prices(config)
    run_daily_check(results, config)


if __name__ == "__main__":
    main()
