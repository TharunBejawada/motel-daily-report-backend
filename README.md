# Motel Daily Report Backend

FastAPI backend that fetches daily reports from Gmail (whitelisted senders), parses PDF attachments, stores normalized data in Postgres, and exposes APIs to list, view, and export reports as PDF/DOCX.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Put your real Gmail OAuth creds into credentials.json, run once to create token.json
uvicorn main:app --reload
```

## Endpoints

- `GET /reports/fetch?mode=recent&limit=10` or `mode=all&pages=2&after=YYYY/MM/DD&before=YYYY/MM/DD`
- `GET /reports` list (with pagination)
- `GET /reports/{id}` detail
- `GET /reports/{id}/export.pdf`
- `GET /reports/{id}/export.docx`
