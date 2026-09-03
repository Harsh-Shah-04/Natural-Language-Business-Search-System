# Demo runbook

**Your link (permanent, never changes):**

## https://business-search-inky.vercel.app

---

## Tomorrow morning: one command

Open **PowerShell**, paste this, press Enter:

```powershell
powershell -ExecutionPolicy Bypass -File D:\Intern_assignment\deploy\start-demo.ps1
```

Takes about **90 seconds**. When it prints `READY`, the link works. Do this
**10 minutes before** the call, not during it.

You should see:

```
[1/6] Stopping anything still running        OK  clean
[2/6] Starting backend on :8000              OK  models loaded
[3/6] Opening Cloudflare tunnel              OK  https://....trycloudflare.com
[4/6] Rebuilding frontend                    OK  tunnel URL baked into bundle
[5/6] Redeploying to Vercel                  OK  deployed
[6/6] Verifying end to end                   OK  intent: ...  [source: llm]

 READY - share this link:
 https://business-search-inky.vercel.app
```

**If it does not say `READY`, the link is not working.** Do not share it until
it does.

### One-time setup (do this tonight, not tomorrow)

The script needs your Vercel token saved once:

```powershell
'<paste-your-vercel-token>' | Out-File -Encoding ascii "$env:USERPROFILE\.business-search-vercel-token"
```

Get a token at <https://vercel.com/account/tokens>. It is stored in your home
directory, outside the repo, so it can never be committed by accident.

---

## The one rule

**Keep the laptop awake and on wifi.** The backend runs on *this machine* and is
exposed through a tunnel. Sleep, hibernate, or losing wifi kills it and the link
goes dead.

Before the call:

```powershell
powercfg /change standby-timeout-ac 0
powercfg /change monitor-timeout-ac 30
```

Closing the lid still sleeps it. Leave it open.

---

## Why a rebuild is needed every time

The tunnel URL is random and **changes on every restart**. Vite bakes
`VITE_API_BASE_URL` into the JavaScript at **build** time, not at run time, so a
new tunnel means a new build and a new deploy. The script does all of it.

What is permanent and never needs redoing:

| | |
| --- | --- |
| The `business-search-inky.vercel.app` URL | permanent |
| The Vercel project | permanent |
| MongoDB Atlas data and indexes | permanent |
| Python venv, `node_modules`, cloudflared | permanent |

Only the **backend process**, the **tunnel**, and the **rebuild+redeploy** repeat.

> There is a second Vercel project (`frontend-liard-beta-97...`) from an earlier
> mistaken deploy. **Ignore it.** It is not your link. Delete it later if you want.

---

## Queries that demo well

These all have matching businesses. Verified working on the live site.

| Type this | You should get |
| --- | --- |
| `Our site crashes when a big sale sends huge traffic` | Cloud Services |
| `Teach my staff to spot fake emails and scams` | Corporate Training |
| `I don't want cybersecurity companies. I need someone to train my employees to recognize phishing emails.` | Corporate Training, **Excluding: Cybersecurity** |
| `Received a notice from the tax department, need help` | GST Consultants |
| `Fruit rots before reaching the market, need chilled transport` | Cold Chain |
| `Our factory machines keep breaking down and production stops` | Industrial Automation |

None of these name the category. That is the point — show the **"I understood
you need"** panel above the results.

### Do NOT demo these

There are no businesses in these categories, so the panel stays blank and you
get an amber *"No strong match"* banner:

- office wifi / networking / IT support
- washing powder, soap, detergent, any consumer product
- restaurant hygiene or food-safety inspections
- random words or your own name

This is correct behaviour — the system refuses to invent a category it has no
businesses for — but it does not demo well. If asked, that is the honest answer.

---

## If something breaks

**Link loads but every search says "Could not reach the search service"**
The tunnel died (laptop slept). Re-run the script.

**Script says "No Vercel token found"**
Do the one-time setup above.

**Script says "Backend did not become ready"**
Check `C:\Users\Harsh\AppData\Local\Temp\business-search\backend.err.log`.
Usually MongoDB Atlas is unreachable — confirm Network Access still allows
`0.0.0.0/0` and that you have internet.

**Script says "cloudflared not found"**

```powershell
winget install Cloudflare.cloudflared
```

**Everything is broken and you need the original code back**

```powershell
git checkout feat/contextual-intent-search
```

That is the pre-deployment state (commit `4ebf1de`, also tagged
`pre-deployment-restore-point`). No deployment work touched `backend/app/`.

---

## Health checks

The script prints the tunnel URL. Append these to it:

| Endpoint | Healthy response |
| --- | --- |
| `/health` | `{"status":"ok"}` |
| `/health/model` | `{"status":"ready"}` |
| `/health/reranker` | `{"status":"ready"}` |
| `/health/intent` | `{"status":"ready","provider":"auto",...}` |

`/health/intent` is **sticky** — it reports the last outcome, not current state.
One unsupported query (wifi, detergent) flips it to `error` and it stays there
until the next good query. Do not panic at that; run a known-good query and
check the panel appears instead.

---

## Honest limitations, if asked

- **Not hosted.** It runs on this laptop behind a tunnel. Free tiers with enough
  RAM for the embedder plus the cross-encoder do not exist any more (Hugging
  Face now requires PRO for Docker Spaces; the Railway trial is used up).
  `backend/Dockerfile` and `backend/railway.toml` are committed and ready for a
  real host the moment there is a budget.
- **No authentication.** Anyone with the link can register a business.
- **Vector search has no relevance floor** — it always returns the 10 nearest
  entries even when nothing is close. The amber banner flags the obvious cases,
  but gibberish that the classifier still maps to a category slips through.
