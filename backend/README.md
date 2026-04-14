# Crypto Sniper — FastAPI Backend

Real-time crypto signal intelligence API. Powers the crypto.guru PWA.

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET`  | `/` | Health check |
| `POST` | `/analyse` | Full V/P/R/T signal analysis + agent debate |
| `GET`  | `/analyse/{symbol}?interval=1h` | GET convenience variant |
| `POST` | `/kronos` | Kronos-mini AI forecast (24 candles forward) |
| `GET`  | `/kronos/{symbol}?interval=1h&pred_len=24` | GET convenience variant |
| `GET`  | `/docs` | Interactive Swagger UI |

## Quick start (local)

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload
```

Then open http://localhost:8000/docs

## Example requests

```bash
# Signal analysis
curl http://localhost:8000/analyse/BTC?interval=1h

# Kronos forecast
curl http://localhost:8000/kronos/ETH?interval=4h&pred_len=24
```

## Deploy on Render

1. Push this repo to GitHub
2. New Web Service → connect `subroh75/crypto-sniper`
3. Root directory: `backend`
4. Build command: `pip install -r requirements.txt`
5. Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
6. Set env var `ALLOWED_ORIGINS=https://crypto.guru`

Or use the `render.yaml` at the repo root for one-click deploy.

## Enabling Kronos

Kronos requires ~1.5 GB RAM. Uncomment `torch` and `kronos-ts` in
`requirements.txt` and upgrade to a Render Standard instance.
The model loads on first `/kronos` request and stays warm in memory.

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ALLOWED_ORIGINS` | `*` | Comma-separated CORS origins |
| `PORT` | `8000` | Set automatically by Render |
