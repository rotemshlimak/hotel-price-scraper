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

Runs **daily at 07:15 Israel time (IDT)** — **04:15 UTC** — via [`.github/workflows/daily.yml`](.github/workflows/daily.yml). Also runnable manually from the Actions tab (**Run workflow**).

### One-time setup

1. Push this repo to GitHub (private repo recommended — config is in secrets, not git).
2. Add **Actions secrets** (Settings → Secrets and variables → Actions):

| Secret | Value |
|--------|--------|
| `CONFIG_JSON` | Full contents of your local `config.json` |
| `STAYAPI_API_KEY` | From `.env` |
| `GMAIL_APP_PASSWORD` | From `.env` |
| `ARBITRIP_STORAGE_STATE_B64` | Auto-set by `setup_github_secrets.ps1` after `arbitrip_login.py` |
| `ARBITRIP_SEARCH_TOKEN` | Optional — from Arbitrip hotel URL |

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
- **StayAPI**: 1 call per Marriott hotel in config.
- **Arbitrip (HTZone)**: requires Playwright + a saved login session (see below).
- Scheduled time is **04:15 UTC** (**07:15 Israel, IDT**). In winter (IST, UTC+2) that is **06:15 Israel** unless you adjust the `cron` line in `daily.yml`.

### Arbitrip on GitHub Actions

Arbitrip ([htzone.arbitrip.com](https://htzone.arbitrip.com/)) uses HTZone SSO — GHA runs headless Chromium with cookies exported from your PC.

1. **Log in locally** and save session:
   ```powershell
   python scripts/arbitrip_login.py
   ```
2. **Push secrets** (includes base64 session if `logs/arbitrip_storage.json` exists):
   ```powershell
   .\scripts\setup_github_secrets.ps1
   ```
3. Set **`CONFIG_JSON`** with `"provider": "mixed"` and Arbitrip hotels using `"chain": "arbitrip"` (see `config.example.json`).

| Secret | Purpose |
|--------|---------|
| `ARBITRIP_STORAGE_STATE_B64` | Playwright cookies/localStorage from login (refresh when session expires) |
| `ARBITRIP_SEARCH_TOKEN` | Optional — `search_token` from hotel URL if rates fail without it |

**Session expiry:** When Arbitrip runs fail with “redirected to HTZone login”, re-run `arbitrip_login.py` and `setup_github_secrets.ps1`.

**If GHA IP is blocked:** HTZone/Cloudflare may reject datacenter IPs even with valid cookies. Use a [self-hosted runner](https://docs.github.com/en/actions/hosting-your-own-runners) on your home network and set `runs-on: self-hosted` in `daily.yml`.

## StayAPI credits

Daily run = 2 API calls (one per hotel) ≈ **60/month** — within 100 free credits.
