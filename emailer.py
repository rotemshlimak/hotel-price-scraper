import html
import os
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

CONFIG_PATH = "config.json"

# Inline styles for email client compatibility
_STYLE = {
    "body": "margin:0;padding:0;background:#f0f2f5;font-family:Segoe UI,Helvetica,Arial,sans-serif;color:#1a1a1a;",
    "wrap": "max-width:680px;margin:24px auto;background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.08);",
    "header": "background:linear-gradient(135deg,#1a1a2e 0%,#8b2332 100%);color:#ffffff;padding:28px 32px;",
    "header_h1": "margin:0 0 8px;font-size:22px;font-weight:600;letter-spacing:-0.3px;",
    "header_sub": "margin:0;font-size:14px;opacity:0.9;",
    "content": "padding:28px 32px;",
    "meta": "background:#f8f9fb;border-radius:8px;padding:12px 16px;margin-bottom:24px;font-size:13px;color:#555;",
    "hotel": "margin-bottom:32px;",
    "hotel_name": "margin:0 0 6px;font-size:18px;font-weight:600;color:#1a1a2e;",
    "dates": "margin:0 0 16px;font-size:13px;color:#666;",
    "best_rate": "background:#fff8f0;border-left:4px solid #8b2332;padding:14px 16px;border-radius:0 8px 8px 0;margin-bottom:16px;",
    "best_label": "font-size:11px;text-transform:uppercase;letter-spacing:0.5px;color:#8b2332;font-weight:600;margin-bottom:4px;",
    "best_price": "font-size:22px;font-weight:700;color:#1a1a2e;",
    "best_plan": "font-size:13px;color:#555;margin-top:4px;",
    "table": "width:100%;border-collapse:collapse;font-size:13px;",
    "th": "background:#f4f4f5;text-align:left;padding:10px 12px;font-weight:600;color:#444;border-bottom:2px solid #e5e5e5;",
    "td": "padding:10px 12px;border-bottom:1px solid #eee;vertical-align:top;",
    "td_price": "padding:10px 12px;border-bottom:1px solid #eee;vertical-align:top;white-space:nowrap;font-weight:600;",
    "footer": "padding:16px 32px;background:#f8f9fb;text-align:center;font-size:12px;color:#888;",
    "drop_card": "background:#f0fdf4;border:1px solid #bbf7d0;border-radius:10px;padding:16px 18px;margin-bottom:14px;",
    "drop_room": "font-size:16px;font-weight:600;margin:0 0 4px;",
    "drop_plan": "font-size:13px;color:#555;margin:0 0 12px;",
    "drop_row": "display:block;margin:4px 0;font-size:14px;",
    "was": "color:#888;text-decoration:line-through;",
    "now": "color:#15803d;font-weight:700;font-size:16px;",
    "saved": "color:#16a34a;font-weight:600;margin-top:8px;",
    "badge_new": "display:inline-block;background:#fef3c7;color:#92400e;font-size:10px;font-weight:700;padding:2px 8px;border-radius:999px;letter-spacing:0.3px;",
    "badge_atl": "display:inline-block;background:#d1fae5;color:#065f46;font-size:10px;font-weight:700;padding:2px 8px;border-radius:999px;letter-spacing:0.3px;",
}


def _e(text) -> str:
    return html.escape(str(text)) if text is not None else ""


def _fmt_money(amount: float, currency: str) -> str:
    return f"{amount:,.0f} {_e(currency)}"


def _atl_marker(rate: dict) -> str:
    if rate.get("is_new_all_time_low"):
        return " [NEW ALL-TIME LOW]"
    if rate.get("is_at_all_time_low"):
        return " [ALL-TIME LOW]"
    return ""


def _atl_badge_html(rate: dict) -> str:
    if rate.get("is_new_all_time_low"):
        return f'<span style="{_STYLE["badge_new"]}">NEW ALL-TIME LOW</span>'
    if rate.get("is_at_all_time_low"):
        return f'<span style="{_STYLE["badge_atl"]}">ALL-TIME LOW</span>'
    return ""


def _html_document(title: str, header_sub: str, inner: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="{_STYLE["body"]}">
<div style="{_STYLE["wrap"]}">
  <div style="{_STYLE["header"]}">
    <h1 style="{_STYLE["header_h1"]}">{_e(title)}</h1>
    <p style="{_STYLE["header_sub"]}">{_e(header_sub)}</p>
  </div>
  <div style="{_STYLE["content"]}">
    {inner}
  </div>
  <div style="{_STYLE["footer"]}">Sent by hotel-price-scraper</div>
</div>
</body>
</html>"""


def _room_rates_table_html(room_rates: list[dict], currency: str) -> str:
    if not room_rates:
        return ""
    rows = []
    for rr in room_rates:
        cur = rr.get("currency", currency)
        room = _e(rr["room_name"])
        if rr.get("bed_type"):
            room += f'<br><span style="color:#888;font-size:12px;">{_e(rr["bed_type"])}</span>'
        per_night = _fmt_money(rr["per_night"], cur)
        total = _fmt_money(rr["total"], cur) if rr.get("total") is not None else "—"
        plan = _e(rr.get("rate_name") or "—")
        badge = _atl_badge_html(rr)
        badge_cell = f" {badge}" if badge else ""
        rows.append(
            f'<tr>'
            f'<td style="{_STYLE["td"]}">{room}</td>'
            f'<td style="{_STYLE["td"]}">{plan}{badge_cell}</td>'
            f'<td style="{_STYLE["td_price"]}">{per_night}</td>'
            f'<td style="{_STYLE["td_price"]}">{total}</td>'
            f"</tr>"
        )
    return f"""
    <table style="{_STYLE["table"]}" role="presentation">
      <thead>
        <tr>
          <th style="{_STYLE["th"]}">Room</th>
          <th style="{_STYLE["th"]}">Rate plan</th>
          <th style="{_STYLE["th"]}">Per night</th>
          <th style="{_STYLE["th"]}">Stay total</th>
        </tr>
      </thead>
      <tbody>{"".join(rows)}</tbody>
    </table>"""


def _format_room_rate_lines(room_rates: list[dict], currency: str) -> list[str]:
    if not room_rates:
        return []
    lines = ["  All cash rates:"]
    for rr in room_rates:
        cur = rr.get("currency", currency)
        room = rr["room_name"]
        if rr.get("bed_type"):
            room += f" ({rr['bed_type']})"
        line = f"    {room}: {rr['per_night']:,.0f} {cur}/night"
        if rr.get("total") is not None:
            line += f", {rr['total']:,.0f} {cur} total"
        if rr.get("rate_name"):
            line += f" ({rr['rate_name']})"
        line += _atl_marker(rr)
        lines.append(line)
    return lines


def _format_rate_drop_line(d: dict, currency: str) -> list[str]:
    lines = []
    room = d.get("room_name") or "Room"
    if d.get("bed_type"):
        room += f" ({d['bed_type']})"
    lines.append(f"  {room}")
    if d.get("rate_name"):
        lines.append(f"    Rate plan: {d['rate_name']}")
    was = f"    Was: {d['previous_per_night']:,.0f} {currency}/night"
    if d.get("previous_total") is not None:
        was += f", {d['previous_total']:,.0f} {currency} total"
    if d.get("previous_checked_at"):
        was += f" ({d['previous_checked_at']})"
    lines.append(was)
    now = f"    Now: {d['per_night']:,.0f} {currency}/night"
    if d.get("total") is not None:
        now += f", {d['total']:,.0f} {currency} total"
    now += _atl_marker(d)
    lines.append(now)
    saved = f"    Saved: {d['savings']:,.0f} {currency}/night ({d['savings_pct']:.1f}%)"
    if d.get("total") is not None and d.get("previous_total") is not None:
        total_saved = d["previous_total"] - d["total"]
        if total_saved > 0:
            saved += f", {total_saved:,.0f} {currency} total"
    lines.append(saved)
    atl_line = _format_all_time_low_line(d, currency)
    if atl_line:
        lines.append(atl_line)
    return lines


def _format_drop_card_html(d: dict, currency: str) -> str:
    room = _e(d.get("room_name") or "Room")
    if d.get("bed_type"):
        room += f' <span style="color:#888;font-weight:400;">({_e(d["bed_type"])})</span>'
    badge = _atl_badge_html(d)
    badge_html = f" {badge}" if badge else ""

    was = f'{_fmt_money(d["previous_per_night"], currency)}/night'
    if d.get("previous_total") is not None:
        was += f', {_fmt_money(d["previous_total"], currency)} total'

    now = f'{_fmt_money(d["per_night"], currency)}/night'
    if d.get("total") is not None:
        now += f', {_fmt_money(d["total"], currency)} total'

    saved = f'Saved {_fmt_money(d["savings"], currency)}/night ({d["savings_pct"]:.1f}%)'
    if d.get("total") is not None and d.get("previous_total") is not None:
        total_saved = d["previous_total"] - d["total"]
        if total_saved > 0:
            saved += f', {_fmt_money(total_saved, currency)} total'

    atl_html = ""
    atl_line = _format_all_time_low_line(d, currency)
    if atl_line:
        atl_html = f'<div style="font-size:13px;color:#555;margin-top:8px;">{_e(atl_line.strip())}</div>'

    return f"""
    <div style="{_STYLE["drop_card"]}">
      <p style="{_STYLE["drop_room"]}">{room}{badge_html}</p>
      <p style="{_STYLE["drop_plan"]}">{_e(d.get("rate_name") or "")}</p>
      <span style="{_STYLE["drop_row"]} {_STYLE["was"]}">Was: {was}</span>
      <span style="{_STYLE["drop_row"]} {_STYLE["now"]}">Now: {now}</span>
      <div style="{_STYLE["saved"]}">{saved}</div>
      {atl_html}
    </div>"""


def _format_all_time_low_line(d: dict, currency: str) -> str | None:
    if d.get("is_new_all_time_low") and d.get("all_time_low_per_night") is not None:
        line = (
            f"    New all-time low! Previous best: "
            f"{d['all_time_low_per_night']:,.0f} {currency}/night"
        )
        if d.get("all_time_low_at"):
            line += f" ({d['all_time_low_at'][:10]})"
        return line
    if d.get("all_time_low_per_night") is not None:
        line = f"    All-time low: {d['all_time_low_per_night']:,.0f} {currency}/night"
        if d.get("all_time_low_total") is not None:
            line += f", {d['all_time_low_total']:,.0f} {currency} total"
        if d.get("all_time_low_at"):
            line += f" (since {d['all_time_low_at'][:10]})"
        return line
    return None


def _email_recipients(email_cfg: dict) -> list[str]:
    if email_cfg.get("recipients"):
        return [r.strip() for r in email_cfg["recipients"] if r and str(r).strip()]
    if email_cfg.get("recipient"):
        return [email_cfg["recipient"].strip()]
    return []


def load_config():
    import json

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _report_label(results: list[dict]) -> str:
    chains = {r.get("source", "") for r in results}
    if chains == {"stayapi"}:
        return "Marriott"
    if chains == {"hilton_graphql"}:
        return "Hilton"
    return "Hotel"


def format_results_email(
    results: list[dict], config: dict, history: dict | None = None
) -> tuple[str, str, str]:
    from price_tracker import annotate_rates_with_atl

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    corp = config.get("corporate_code", "")
    label = _report_label(results)
    subject = f"{label} prices ({len(results)} hotels) — {now}"

    lines = [f"{label} price report — {now}", ""]
    html_hotels = []

    source = results[0].get("source") if results else None
    meta_parts = []
    if source == "stayapi":
        if corp:
            meta_parts.append(f"StayAPI · corporate code {corp}")
            lines.append(f"Source: StayAPI (corporate code: {corp})")
        else:
            meta_parts.append("StayAPI · public/member rates")
            lines.append("Source: StayAPI (public/member rates)")
        lines.append("")
    elif source == "hilton_graphql":
        meta_parts.append("Hilton GraphQL")
        lines.append("Source: Hilton GraphQL")
        lines.append("")
    if corp:
        lines.append(f"Corporate code: {corp}")
        lines.append("")

    for r in results:
        lines.append(r["hotel"])
        lines.append(f"  Dates: {r['check_in']} to {r['check_out']}")
        currency = r.get("currency", "THB")
        hotel_html = [
            f'<div style="{_STYLE["hotel"]}">',
            f'<h2 style="{_STYLE["hotel_name"]}">{_e(r["hotel"])}</h2>',
            f'<p style="{_STYLE["dates"]}">{_e(r["check_in"])} → {_e(r["check_out"])}</p>',
        ]
        if r.get("available"):
            lines.append(f"  Rate: {r.get('rate', 'N/A')}")
            if r.get("total") is not None:
                lines.append(f"  Total: {r['total']:,.0f} {currency}")
            if r.get("per_night") is not None:
                hotel_html.append(
                    f'<div style="{_STYLE["best_rate"]}">'
                    f'<div style="{_STYLE["best_label"]}">Lowest cash rate</div>'
                    f'<div style="{_STYLE["best_price"]}">{_fmt_money(r["per_night"], currency)} <span style="font-size:14px;font-weight:400;">/ night</span></div>'
                )
                if r.get("total") is not None:
                    hotel_html.append(
                        f'<div style="font-size:14px;color:#555;margin-top:4px;">'
                        f'{_fmt_money(r["total"], currency)} total stay</div>'
                    )
                if r.get("rate_name"):
                    hotel_html.append(f'<div style="{_STYLE["best_plan"]}">{_e(r["rate_name"])}</div>')
                hotel_html.append("</div>")
            room_rates = r.get("room_rates", [])
            if history is not None:
                room_rates = annotate_rates_with_atl(r, history)
            lines.extend(_format_room_rate_lines(room_rates, currency))
            hotel_html.append(_room_rates_table_html(room_rates, currency))
        else:
            lines.append(f"  Rate: {r.get('rate') or 'Unavailable'}")
            hotel_html.append(f'<p style="color:#888;">Rate unavailable</p>')
        lines.append("")
        hotel_html.append("</div>")
        html_hotels.append("".join(hotel_html))

    lines.append("—")
    lines.append("Sent by hotel-price-scraper")

    meta_html = ""
    if meta_parts:
        meta_html = f'<div style="{_STYLE["meta"]}">{_e(" · ".join(meta_parts))}</div>'

    html_body = _html_document(
        f"{label} Price Report",
        now,
        meta_html + "".join(html_hotels),
    )
    return subject, "\n".join(lines), html_body


def format_drop_alert_email(drops: list[dict], config: dict) -> tuple[str, str, str]:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    corp = config.get("corporate_code", "")

    if len(drops) == 1:
        d = drops[0]
        currency = d.get("currency", "THB")
        room = d.get("room_name") or "Room"
        subject = (
            f"Price drop: {d['hotel']} — {room} — "
            f"{d['per_night']:,.0f} {currency} (was {d['previous_per_night']:,.0f})"
        )
        if d.get("is_new_all_time_low"):
            subject += " — NEW ALL-TIME LOW"
    else:
        hotels = len({d["hotel"] for d in drops})
        new_atl = sum(1 for d in drops if d.get("is_new_all_time_low"))
        subject = f"Price drop alert — {len(drops)} rate(s), {hotels} hotel(s) — {now}"
        if new_atl:
            subject += f" ({new_atl} new all-time low)"

    label = _report_label([d for d in drops]) if drops else "Hotel"
    lines = [f"{label} price drop alert — {now}", ""]
    html_parts = []
    if corp:
        lines.append(f"Corporate code: {corp}")
        lines.append("")
        html_parts.append(f'<div style="{_STYLE["meta"]}">Corporate code: {_e(corp)}</div>')

    current_hotel = None
    for d in drops:
        if d["hotel"] != current_hotel:
            if current_hotel is not None:
                html_parts.append("</div>")
            current_hotel = d["hotel"]
            lines.append(current_hotel)
            lines.append(f"  Dates: {d['check_in']} to {d['check_out']}")
            html_parts.append(
                f'<div style="{_STYLE["hotel"]}">'
                f'<h2 style="{_STYLE["hotel_name"]}">{_e(d["hotel"])}</h2>'
                f'<p style="{_STYLE["dates"]}">{_e(d["check_in"])} → {_e(d["check_out"])}</p>'
            )
        currency = d.get("currency", "THB")
        lines.extend(_format_rate_drop_line(d, currency))
        lines.append("")
        html_parts.append(_format_drop_card_html(d, currency))

    if current_hotel is not None:
        html_parts.append("</div>")

    lines.append("—")
    lines.append("Sent by hotel-price-scraper")

    html_body = _html_document("Price Drop Alert", now, "".join(html_parts))
    return subject, "\n".join(lines), html_body


def send_email(subject: str, body: str, config: dict, html_body: str | None = None):
    email_cfg = config["email"]
    password = email_cfg.get("password") or os.environ.get("GMAIL_APP_PASSWORD", "")
    recipients = _email_recipients(email_cfg)
    required = ("smtp_server", "username")
    missing = [k for k in required if not email_cfg.get(k)]
    if missing:
        raise ValueError(f"Missing email config: {', '.join(missing)}")
    if not recipients:
        raise ValueError(
            "Missing email recipients. Set email.recipients (list) or email.recipient in config.json."
        )
    if not password:
        raise ValueError(
            "Missing email password. Set email.password in config.json "
            "or the GMAIL_APP_PASSWORD environment variable."
        )

    msg = MIMEMultipart("alternative")
    msg["From"] = email_cfg["username"]
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))
    if html_body:
        msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP(email_cfg["smtp_server"], email_cfg.get("smtp_port", 587)) as server:
        server.starttls()
        server.login(email_cfg["username"], password)
        server.send_message(msg, to_addrs=recipients)


def send_drop_alert_if_needed(drops: list[dict], config: dict) -> bool:
    if not drops:
        return False
    subject, body, html_body = format_drop_alert_email(drops, config)
    send_email(subject, body, config, html_body)
    hotels = len({d["hotel"] for d in drops})
    recipients = ", ".join(_email_recipients(config["email"]))
    print(
        f"Drop alert sent to {recipients} "
        f"({len(drops)} rate(s), {hotels} hotel(s))"
    )
    return True


def send_results_email(results: list[dict], config: dict, history: dict | None = None):
    subject, body, html_body = format_results_email(results, config, history)
    send_email(subject, body, config, html_body)
    print(f"Email sent to {', '.join(_email_recipients(config['email']))}")


def main():
    config = load_config()
    send_email(
        "Hotel Price Scraper — test",
        "If you received this, email settings in config.json are working.",
        config,
        "<p>If you received this, email settings in <strong>config.json</strong> are working.</p>",
    )
    print(f"Test email sent to {', '.join(_email_recipients(config['email']))}")


if __name__ == "__main__":
    main()
