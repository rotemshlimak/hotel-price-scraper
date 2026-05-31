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
    if provider == "hilton":
        from scraper_hilton_api import scrape_hotel_hilton
        from scraper_api import hotel_configs
        import json

        defaults = {k: v for k, v in config.items() if k not in ("provider", "hotels", "email", "scraper_mode")}
        results = [scrape_hotel_hilton({**defaults, **h}) for h in hotel_configs(config)]
        print(json.dumps(results, indent=2))
        return results
    from scraper_api import scrape_prices_api

    return scrape_prices_api(config)


def main():
    config = load_config()
    results = scrape_prices(config)
    run_daily_check(results, config)


if __name__ == "__main__":
    main()
