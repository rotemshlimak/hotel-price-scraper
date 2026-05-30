import json
from datetime import datetime, timezone
from pathlib import Path

HISTORY_PATH = Path(__file__).resolve().parent / "logs" / "price_history.json"


def _hotel_key(result: dict) -> str:
    pid = result.get("property_id") or result.get("hotel", "")
    return f"{pid}|{result['check_in']}|{result['check_out']}"


def _rate_key(result: dict, rate: dict) -> str:
    code = rate.get("rate_plan_code") or rate.get("rate_name") or "unknown"
    room = rate.get("room_name") or "unknown"
    bed = rate.get("bed_type") or ""
    return f"{_hotel_key(result)}|{room}|{bed}|{code}"


def _hotel_prefix(result: dict) -> str:
    return f"{_hotel_key(result)}|"


def load_history() -> dict:
    if not HISTORY_PATH.is_file():
        return {}
    text = HISTORY_PATH.read_text(encoding="utf-8").strip()
    if not text:
        return {}
    return json.loads(text)


def save_history(history: dict) -> None:
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_PATH.write_text(json.dumps(history, indent=2), encoding="utf-8")


def _rate_entries(result: dict) -> list[dict]:
    if result.get("room_rates"):
        return result["room_rates"]
    if result.get("available") and result.get("per_night") is not None:
        return [
            {
                "room_name": result.get("room_name") or result.get("rate_name") or "Lowest rate",
                "bed_type": result.get("bed_type", ""),
                "per_night": result["per_night"],
                "total": result.get("total"),
                "currency": result.get("currency", "THB"),
                "rate_name": result.get("rate_name"),
                "rate_plan_code": result.get("rate_plan_code", ""),
            }
        ]
    return []


def _effective_all_time_low(prev: dict) -> dict | None:
    """Return stored ATL, or migrate from the last-run snapshot."""
    if prev.get("all_time_low"):
        return prev["all_time_low"]
    if prev.get("per_night") is not None:
        return {
            "per_night": prev["per_night"],
            "total": prev.get("total"),
            "checked_at": prev.get("checked_at"),
        }
    return None


def _update_all_time_low(prev: dict | None, rate: dict, now: str) -> dict:
    """Keep or replace all-time low for a room/rate entry."""
    current_pn = float(rate["per_night"])
    atl = _effective_all_time_low(prev) if prev else None
    if atl is None or current_pn < float(atl["per_night"]):
        entry = {"per_night": current_pn, "checked_at": now}
        if rate.get("total") is not None:
            entry["total"] = rate["total"]
        return entry
    return atl


def _attach_all_time_low_context(drop: dict, prev: dict, current: float) -> None:
    atl = _effective_all_time_low(prev)
    if not atl:
        return
    drop["all_time_low_per_night"] = float(atl["per_night"])
    if atl.get("total") is not None:
        drop["all_time_low_total"] = float(atl["total"])
    if atl.get("checked_at"):
        drop["all_time_low_at"] = atl["checked_at"]
    drop["is_new_all_time_low"] = current < float(atl["per_night"])
    drop["is_at_all_time_low"] = current <= float(atl["per_night"])


def detect_drops(results: list[dict], history: dict) -> list[dict]:
    """Return room/rate entries where per_night dropped vs last saved price."""
    drops = []
    for r in results:
        if not r.get("available"):
            continue
        for rate in _rate_entries(r):
            if rate.get("per_night") is None:
                continue
            key = _rate_key(r, rate)
            prev = history.get(key)
            if not prev or prev.get("per_night") is None:
                continue
            previous = float(prev["per_night"])
            current = float(rate["per_night"])
            if current < previous:
                savings = previous - current
                pct = (savings / previous) * 100 if previous else 0
                drop = {
                    "hotel": r["hotel"],
                    "property_id": r.get("property_id", ""),
                    "check_in": r["check_in"],
                    "check_out": r["check_out"],
                    "corporate_code": r.get("corporate_code", ""),
                    "currency": rate.get("currency", r.get("currency", "THB")),
                    "room_name": rate.get("room_name"),
                    "bed_type": rate.get("bed_type", ""),
                    "rate_name": rate.get("rate_name"),
                    "rate_plan_code": rate.get("rate_plan_code", ""),
                    "per_night": current,
                    "total": rate.get("total"),
                    "previous_per_night": previous,
                    "previous_total": prev.get("total"),
                    "previous_checked_at": prev.get("checked_at"),
                    "savings": savings,
                    "savings_pct": pct,
                }
                if drop["previous_total"] is not None:
                    drop["previous_total"] = float(drop["previous_total"])
                _attach_all_time_low_context(drop, prev, current)
                drops.append(drop)
    drops.sort(key=lambda d: (d["hotel"], d["per_night"], d.get("room_name") or ""))
    return drops


def update_history(results: list[dict], history: dict) -> dict:
    """Update history with latest prices for every tracked room/rate."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for r in results:
        if not r.get("available"):
            continue
        legacy_key = _hotel_key(r)
        if legacy_key in history:
            del history[legacy_key]
        for rate in _rate_entries(r):
            if rate.get("per_night") is None:
                continue
            key = _rate_key(r, rate)
            prev = history.get(key)
            entry = {
                "hotel": r["hotel"],
                "property_id": r.get("property_id", ""),
                "check_in": r["check_in"],
                "check_out": r["check_out"],
                "room_name": rate.get("room_name"),
                "bed_type": rate.get("bed_type", ""),
                "rate_name": rate.get("rate_name"),
                "rate_plan_code": rate.get("rate_plan_code", ""),
                "per_night": rate["per_night"],
                "currency": rate.get("currency", r.get("currency", "THB")),
                "checked_at": now,
            }
            if rate.get("total") is not None:
                entry["total"] = rate["total"]
            entry["all_time_low"] = _update_all_time_low(prev, rate, now)
            history[key] = entry
    return history


def annotate_rates_with_atl(result: dict, history: dict) -> list[dict]:
    """Attach all-time-low flags to each room/rate for email display."""
    annotated = []
    for rate in _rate_entries(result):
        entry = dict(rate)
        prev = history.get(_rate_key(result, rate))
        if not prev:
            annotated.append(entry)
            continue
        atl = _effective_all_time_low(prev)
        if not atl or rate.get("per_night") is None:
            annotated.append(entry)
            continue
        current = float(rate["per_night"])
        atl_pn = float(atl["per_night"])
        entry["all_time_low_per_night"] = atl_pn
        if atl.get("total") is not None:
            entry["all_time_low_total"] = float(atl["total"])
        if atl.get("checked_at"):
            entry["all_time_low_at"] = atl["checked_at"]
        entry["is_new_all_time_low"] = current < atl_pn
        entry["is_at_all_time_low"] = current <= atl_pn
        annotated.append(entry)
    return annotated


def is_first_run(history: dict, results: list[dict]) -> bool:
    """True if none of the current hotels have prior per-rate history."""
    for r in results:
        if not r.get("available"):
            continue
        prefix = _hotel_prefix(r)
        if any(k.startswith(prefix) for k in history):
            return False
        if _hotel_key(r) in history:
            return False
    return True
