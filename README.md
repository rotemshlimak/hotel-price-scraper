# Marriott Price Scraper

This project automates price retrieval from marriott.com for a specific hotel, date, and corporate code, sending results via email every 6 hours.

## Configuration
Edit `config.json` with your details:
- `hotel_id`: Hotel name (e.g., "JW Marriott Khao Lak Resort")
- `check_in_date`, `check_out_date`: Dates in `YYYY-MM-DD` format
- `corporate_code`: Your corporate code
- `rooms`, `adults`, `children`: Number of rooms, adults, and children
- `email`: SMTP settings and recipient

## Usage
1. Install dependencies:
   ```
   python -m venv venv
   venv\Scripts\activate
   pip install -r requirements.txt
   playwright install
   ```
2. Run the scraper:
   ```
   python scraper.py
   ```
3. Send results via email:
   ```
   python emailer.py
   ```

## Scheduling
Use Task Scheduler (Windows) or cron (Linux/Mac) to run every 6 hours.
