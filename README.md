# Broken Link Checker

A Python-based tool that crawls websites and automatically detects broken links. It checks both internal and external URLs, validates them efficiently, and presents results through an interactive dashboard.

## Features
- Crawl a website starting from a root URL
- Check internal and external links
- Concurrent HTTP validation
- CSV export for broken links
- Interactive Streamlit dashboard for visualization
- Docker support for easy setup and execution

## Run locally with Docker

```bash
docker compose up --build
```

Then open:

```text
http://localhost:8501
```

## Run locally without Docker

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app/dashboard.py
```

## Notes
- This app uses `HEAD` first, then falls back to `GET` if needed.
- Some websites block crawlers or rate-limit requests.
- For true production at scale, add:
  - persistent storage
  - background jobs / queue
  - retries with central logging
  - robots.txt handling
  - authentication for dashboard access
  - distributed crawling
