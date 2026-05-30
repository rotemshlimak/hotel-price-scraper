"""Scrape hotel prices via browser and email only when price drops."""
from daily_run import run_daily_check
from env_loader import load_dotenv
from scraper import load_config, scrape_prices

load_dotenv()


def main():
    config = load_config()
    results = scrape_prices(config)
    run_daily_check(results, config)


if __name__ == "__main__":
    main()
