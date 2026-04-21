# Broken Link Checker

Production-style broken link checker built with Python, Docker, and Streamlit.

## Features
- Crawl a website starting from a root URL
- Check internal and external links
- Concurrent HTTP validation
- CSV export for broken links
- Streamlit dashboard
- Dockerized deployment

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
