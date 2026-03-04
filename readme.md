# find-a-rent

A self-hosted rental monitoring bot that scrapes for new listings and pushes notifications to a Discord channel via webhook. New listings are also recorded in a Google Sheet for deduplication.

## How It Works

1. A POST request hits `/trigger` (e.g. from a cron job)
2. The server waits a random delay (0–120 s) to avoid bot detection
3. It scrapes listings matching your configured search queries
4. New listings (not yet in the Google Sheet) are pushed to Discord as embeds
5. The new listings are appended to the Google Sheet

## Prerequisites

- Python 3.12+
- Node.js (LTS) — used internally to parse `window.__NUXT__` data from page
- A Google Cloud service account with access to the target Google Sheet (save the key as `service_account.json` in the project root)
- A Discord webhook URL
- A Google Sheet shared with the service account

## Environment Variables

Create a `.env` file in the project root:

```env
# Discord
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...

# Google Sheets
GOOGLE_SHEET_ID=your_sheet_id
GCP_SERVICE_ACCOUNT_FILE=service_account.json
SHEET_NAME=houses

# Search Queries (pre-built query strings)
# Example: region=1&section=10&price=20000_30000&layout=1,2&other=lift,balcony_1&shape=2
QUERY_1=
QUERY_2=

# Logging
LOG_LEVEL=INFO
```

> `QUERY_1` and `QUERY_2` are raw query strings taken directly from the search URL. Leave unused ones empty.

## Running Locally

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Start the server
uvicorn main:app --reload --port 8000

# 4. Trigger a crawl
curl -X POST http://localhost:8000/trigger
```

The API docs are available at [http://localhost:8000/docs](http://localhost:8000/docs).

## Running with Docker

```bash
# Build
docker build -t find-a-rent .

# Run
docker run --env-file .env -p 8000:8000 find-a-rent
```

## Deploying to Render

The included `render.yaml` defines a Docker-based web service. Push the repo to GitHub, connect it to [Render](https://render.com), and set the following environment variables in the Render dashboard:

| Key | Description |
|-----|-------------|
| `DISCORD_WEBHOOK_URL` | Your Discord webhook URL |
| `GOOGLE_SHEET_ID` | Target Google Sheet ID |

All other variables can be left at their defaults or overridden as needed.

To trigger the crawl on a schedule, add an external cron service (e.g. [cron-job.org](https://cron-job.org)) that sends a POST request to `https://<your-render-url>/trigger`.

## Project Structure

```
.
├── main.py               # FastAPI app & crawl pipeline
├── requirements.txt
├── Dockerfile
├── render.yaml
├── service_account.json  # GCP credentials (not committed)
└── app/
    ├── config.py         # Pydantic settings (reads .env)
    ├── crawler.py        # scraper
    ├── gsheet.py         # Google Sheets read/write
    ├── line_notify.py    # Discord webhook notifications
    └── models.py         # HouseItem data model
```
