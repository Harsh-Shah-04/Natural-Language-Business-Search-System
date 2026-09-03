# Current deployment

Backend is **tunnelled from a local process**, not hosted. It is reachable only
while the machine is awake and both processes below are running. This was the
only free option left: Hugging Face now requires PRO for Docker Spaces, and the
Railway trial is spent. See `deploy/README.md` for the rejected alternatives.

| Piece | Where | Notes |
| --- | --- | --- |
| Frontend | Vercel — https://business-search-inky.vercel.app | Permanent URL, survives reboots |
| Backend | local uvicorn + Cloudflare quick tunnel | URL changes on every tunnel restart |
| Current tunnel | `https://tons-resolve-hydrogen-tramadol.trycloudflare.com` | Live as of 2026-09-02; dies if this machine sleeps |
| Database | existing MongoDB Atlas cluster | unchanged |
| LLM | DeepSeek via the OpenAI-compatible path | unchanged |

`backend/Dockerfile` and `backend/railway.toml` are committed and ready for a
real container host whenever one is available; nothing about the app needs to
change to use them.

## Restarting after a reboot

The tunnel URL is regenerated each time, and Vite inlines it at **build** time,
so the frontend must be rebuilt and redeployed whenever the tunnel restarts.

```bash
# 1. Backend. CORS_ALLOW_ORIGINS must name the Vercel origin.
cd backend
CORS_ALLOW_ORIGINS=https://<your>.vercel.app \
  .venv/Scripts/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# 2. Tunnel. Prints the new https://<random>.trycloudflare.com URL.
cloudflared tunnel --url http://localhost:8000

# 3. Point the frontend at the new URL and redeploy.
cd frontend
echo "VITE_API_BASE_URL=<new tunnel url>" > .env.production.local
npm run build
cd dist && vercel deploy --prod --yes --token=<token>
```

`.env.production.local` is gitignored (`*.local`) and outranks `.env.local` for
production builds, which is why it is the file used here.

## Readiness

`/health` answers immediately; the models load in background threads. Wait for
`/health/model` and `/health/reranker` to report `ready` (~10s) before searching,
and `/health/intent` to report a `provider`.

## Known limitations

- **Not durable.** Closing the laptop takes the backend down.
- **Unauthenticated.** `POST /api/businesses` is public, as it is locally. Anyone
  with the URL can write rows and spend LLM credits.
- **Cloudflare quick tunnels are rate-limited** and not intended for sustained
  production traffic.
