# Lumen Orders — Web Application (CSV → Images & Reports)

**New:** Includes UI controls for max threads, order prefix filter, retry/backoff, timeouts, CSV toggles, and custom ZIP name.

## Run locally

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Mac/Linux:
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --reload
```
Open http://127.0.0.1:8000

## Deploy on Render
1. Create a new Web Service on https://render.com
2. Connect this repo or upload the ZIP.
3. Render uses `render.yaml` to start the app.
4. You’ll get a public URL like `https://your-app.onrender.com`.

## API
- `POST /api/process` (multipart/form-data): fields include `file` (CSV), `order_prefix`, `max_threads`, `retry_total`, `backoff_factor`, `timeout_sec`, `include_per_product_csv`, `include_back_messages_csv`, `zip_name`.
- `GET /api/status/{job_id}`
- `GET /api/download/{job_id}`
