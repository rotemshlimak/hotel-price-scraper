"""List all room types and cash rates from StayAPI for hotels in config.json."""
from env_loader import load_dotenv
from scraper import load_config
from scraper_api import _is_cash_rate, fetch_rooms, hotel_configs

load_dotenv()


def main():
    config = load_config()
    for h in hotel_configs(config):
        print("=" * 70)
        print(h["hotel_id"])
        print(
            f"Dates: {h['check_in_date']} to {h['check_out_date']}  "
            f"| Corp: {h.get('corporate_code', '-')}"
        )
        data = fetch_rooms(
            h["property_id"],
            h["check_in_date"],
            h["check_out_date"],
            adults=h.get("adults", 2),
            rooms=h.get("rooms", 1),
            currency=h.get("currency", "THB"),
            corporate_code=h.get("corporate_code", ""),
        )
        for i, room in enumerate(data.get("room_types", []), 1):
            print()
            print(f"{i}. {room.get('name')}")
            if room.get("bed_type"):
                print(f"   Bed: {room['bed_type']}")
            if room.get("view"):
                print(f"   View: {room['view']}")
            if room.get("category"):
                print(f"   Category: {room['category']}")
            if room.get("available_rooms") is not None:
                print(f"   Available: {room['available_rooms']}")
            cash = [r for r in room.get("rates", []) if _is_cash_rate(r)]
            if cash:
                print("   Cash rates:")
                for r in sorted(cash, key=lambda x: x["per_night"]):
                    print(f"     - {r['per_night']:,.0f} THB/night  ({r.get('name')})")
            else:
                print("   (no cash rates)")
        total = data.get("total", len(data.get("room_types", [])))
        print(f"\nTotal room types: {total}\n")


if __name__ == "__main__":
    main()
