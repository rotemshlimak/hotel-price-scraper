"""Multi-chain hotel price scraping (Marriott StayAPI + Hilton GraphQL)."""
import json
import traceback

from scraper_api import hotel_configs, scrape_hotel_api
from scraper_hilton_api import scrape_hotel_hilton


def scrape_hotel(hotel_config: dict, defaults: dict) -> dict:
    merged = {**defaults, **hotel_config}
    chain = (hotel_config.get("chain") or defaults.get("provider") or "marriott").lower()
    try:
        if chain == "hilton":
            return scrape_hotel_hilton(merged)
        return scrape_hotel_api(merged)
    except Exception as e:
        return {
            "hotel": merged.get("hotel_id", "Unknown"),
            "property_id": merged.get("property_id", ""),
            "check_in": merged.get("check_in_date", ""),
            "check_out": merged.get("check_out_date", ""),
            "source": "hilton_graphql" if chain == "hilton" else "stayapi",
            "available": False,
            "rate": f"Error: {e}",
            "per_night": None,
            "currency": merged.get("currency", "EUR"),
            "error": str(e),
        }


def scrape_prices_mixed(config: dict) -> list[dict]:
    defaults = {k: v for k, v in config.items() if k not in ("provider", "hotels", "email", "scraper_mode")}
    results = []
    for h in hotel_configs(config):
        chain = (h.get("chain") or defaults.get("provider") or "marriott").lower()
        try:
            results.append(scrape_hotel(h, defaults))
        except Exception:
            traceback.print_exc()
            results.append(
                {
                    "hotel": h.get("hotel_id", "Unknown"),
                    "property_id": h.get("property_id", ""),
                    "check_in": h.get("check_in_date", ""),
                    "check_out": h.get("check_out_date", ""),
                    "source": "hilton_graphql" if chain == "hilton" else "stayapi",
                    "available": False,
                    "rate": "Error: scrape failed",
                    "per_night": None,
                    "currency": h.get("currency", "EUR"),
                }
            )
    print(json.dumps(results, indent=2))
    return results
