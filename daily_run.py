"""Shared daily run: scrape, track prices, email only on drop."""
from emailer import send_drop_alert_if_needed, send_results_email
from price_tracker import detect_drops, is_first_run, load_history, save_history, update_history


def run_daily_check(results: list[dict], config: dict) -> None:
    history = load_history()
    first = is_first_run(history, results)
    drops = detect_drops(results, history)
    history = update_history(results, history)
    save_history(history)

    if drops:
        send_drop_alert_if_needed(drops, config)
        return

    if first:
        send_results_email(results, config, history)
        print("First run — baseline email sent.")
        return

    print("No price drops — no email sent.")
