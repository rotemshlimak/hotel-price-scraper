# Hotel Price Scraper

Scrapes Marriott hotel rates daily and **emails only when a price drops** vs the previous run.

Two modes:

| Mode | Config | Best for |
|------|--------|----------|
| **`api`** | `"scraper_mode": "api"` | Cloud, no browser — [StayAPI](https://stayapi.com/docs/endpoints/marriott-bonvoy/rooms) (supports `corporate_code`) |
| **`browser`** | `"scraper_mode": "browser"` | Edge + Playwright (fallback if API unavailable) |

## How alerts work

1. **First run** — saves baseline to `logs/price_history.json` and **emails all current prices**
2. **Daily runs** — compares every cash room/rate to the previous run
3. **Email sent** — only when any room/rate price **decreases** vs the last run
4. **No change / price up** — last-run prices updated, no email
5. **All-time low** — each room/rate also stores its best-ever price in `price_history.json` (shown in drop emails for context)

Set multiple recipients in `config.json`:

```json
"email": {
  "recipients": ["you@gmail.com", "partner@gmail.com"]
}
```

## Setup

```powershell
cd C:\Repos\hotel-price-scraper
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium   # only needed for browser mode
```

## Secrets (never commit)

Copy `.env.example` to `.env` (gitignored) or set Windows user environment variables:

| Variable | Purpose |
|----------|---------|
| `STAYAPI_API_KEY` | StayAPI dashboard → API Key Management |
| `GMAIL_APP_PASSWORD` | Gmail app password (16 chars, no spaces) |

## Configuration

Edit `config.json` (copy from `config.example.json`):

- **`scraper_mode`**: `"api"` or `"browser"`
- **`corporate_code`**: e.g. `MCO` — passed to StayAPI (undocumented but works)
- **`alert_on_first_run`**: deprecated — first run always emails baseline prices
- **`email.recipients`**: list of addresses to receive alerts (or use single **`email.recipient`**)
- **`hotels`**: each needs `hotel_id`, `property_id`, dates
- **`email`**: Gmail SMTP settings

## Usage

```powershell
python scraper_generic.py   # scrape only, print JSON
python list_rooms.py        # list all room types and rates
python run_api.py           # daily check (API mode) — email on drop only
python run.py               # daily check (browser mode)
python emailer.py           # test SMTP
```

## Scheduled task (Windows)

Daily at 8:00 AM (uses `run_api.bat`):

```powershell
.\setup_task.ps1
.\setup_task.ps1 -StartTime "09:30"          # custom time
.\setup_task.ps1 -IntervalHours 6            # optional: every 6 hours instead
```

Logs: `logs/run_api.log`, price history: `logs/price_history.json`

## GitHub Actions (cloud, no PC required)

Runs **daily at 06:00 UTC (GMT)** via [`.github/workflows/daily.yml`](.github/workflows/daily.yml). Also runnable manually from the Actions tab (**Run workflow**).

### One-time setup

1. Push this repo to GitHub (private repo recommended — config is in secrets, not git).
2. Add **Actions secrets** (Settings → Secrets and variables → Actions):

| Secret | Value |
|--------|--------|
| `CONFIG_JSON` | Full contents of your local `config.json` |
| `STAYAPI_API_KEY` | From `.env` |
| `GMAIL_APP_PASSWORD` | From `.env` |

Or use the helper script (requires [GitHub CLI](https://cli.github.com/)):

```powershell
.\scripts\setup_github_secrets.ps1
```

3. Trigger a test run:

```powershell
gh workflow run daily.yml
```

Or use **Actions → Daily price check → Run workflow** in the GitHub UI.

### Notes

- **Price history** is stored in GitHub Actions cache (`price-history-v1`) between runs — not in the repo.
- The **first Actions run** sends a baseline email (same as local first run). Your local `logs/price_history.json` is not uploaded automatically.
- **2 StayAPI calls** per run (one per hotel in config), same as local.
- Scheduled time is **06:00 UTC**. To change it, edit the `cron` line in `daily.yml`.

## StayAPI credits

Daily run = 2 API calls (one per hotel) ≈ **60/month** — within 100 free credits.
