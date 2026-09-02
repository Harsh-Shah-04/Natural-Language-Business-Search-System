# Start the public demo: backend -> Cloudflare tunnel -> rebuild frontend -> redeploy.
#
# Run from anywhere:  powershell -ExecutionPolicy Bypass -File deploy\start-demo.ps1
#
# The tunnel URL is regenerated on every start, and Vite inlines it at BUILD
# time, so the frontend must be rebuilt and redeployed each run. That is the
# whole reason this script exists -- skipping the rebuild leaves the live site
# pointing at yesterday's dead tunnel.
#
# Needs the Vercel token in deploy\.vercel-token (gitignored) or $env:VERCEL_TOKEN.

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$VercelUrl = "https://business-search-inky.vercel.app"

function Step($n, $msg) { Write-Host "`n[$n/6] $msg" -ForegroundColor Cyan }
function Ok($msg)       { Write-Host "      OK  $msg" -ForegroundColor Green }
function Die($msg)      { Write-Host "`nFAILED: $msg" -ForegroundColor Red; exit 1 }

# --- token -------------------------------------------------------------------
# Kept OUT of the repo on purpose: a token in the working tree is one
# `git add -A` away from being published. Home directory, or the environment.
$TokenFile = Join-Path $env:USERPROFILE ".business-search-vercel-token"
if ($env:VERCEL_TOKEN) {
  $Token = $env:VERCEL_TOKEN
} elseif (Test-Path $TokenFile) {
  $Token = (Get-Content $TokenFile -Raw).Trim()
} else {
  Die @"
No Vercel token found. Save it once with:

  '<your-token>' | Out-File -Encoding ascii "$TokenFile"

Get a token at https://vercel.com/account/tokens
"@
}

# --- 1. clean slate ----------------------------------------------------------
Step 1 "Stopping anything still running"
Get-Process -Name cloudflared -ErrorAction SilentlyContinue | Stop-Process -Force
Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue |
  ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 2
Ok "clean"

# --- 2. backend --------------------------------------------------------------
# CORS_ALLOW_ORIGINS must name the Vercel origin or the browser blocks every
# API call. It is read from the process environment at import time.
Step 2 "Starting backend on :8000"
$py = Join-Path $Root "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) { Die "No venv at $py. Run 'uv sync' in backend\ first." }
$env:CORS_ALLOW_ORIGINS = $VercelUrl
$logDir = Join-Path $env:TEMP "business-search"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
Start-Process -FilePath $py `
  -ArgumentList "-m","uvicorn","app.main:app","--host","127.0.0.1","--port","8000" `
  -WorkingDirectory (Join-Path $Root "backend") `
  -RedirectStandardOutput "$logDir\backend.out.log" `
  -RedirectStandardError  "$logDir\backend.err.log" `
  -WindowStyle Hidden | Out-Null

# /health answers as soon as uvicorn binds; the models load in background
# threads, so readiness is /health/model. ~10-30s from cold.
$ready = $false
foreach ($i in 1..60) {
  Start-Sleep -Seconds 2
  try {
    $h = Invoke-RestMethod "http://127.0.0.1:8000/health/model" -TimeoutSec 5
    if ($h.status -eq "ready") { $ready = $true; break }
    if ($h.status -eq "error") { Die "Embedder failed to load: $($h.detail)" }
  } catch { }
}
if (-not $ready) { Die "Backend did not become ready. See $logDir\backend.err.log" }
Ok "models loaded"

# --- 3. tunnel ---------------------------------------------------------------
Step 3 "Opening Cloudflare tunnel"
$cf = "C:\Program Files (x86)\cloudflared\cloudflared.exe"
if (-not (Test-Path $cf)) { $cf = "C:\Program Files\cloudflared\cloudflared.exe" }
if (-not (Test-Path $cf)) { Die "cloudflared not found. Install: winget install Cloudflare.cloudflared" }
Remove-Item "$logDir\cf.log" -ErrorAction SilentlyContinue
Start-Process -FilePath $cf `
  -ArgumentList "tunnel","--url","http://localhost:8000","--no-autoupdate" `
  -RedirectStandardOutput "$logDir\cf.out.log" `
  -RedirectStandardError  "$logDir\cf.log" `
  -WindowStyle Hidden | Out-Null

$TunnelUrl = $null
foreach ($i in 1..45) {
  Start-Sleep -Seconds 2
  foreach ($f in @("$logDir\cf.log","$logDir\cf.out.log")) {
    if (Test-Path $f) {
      $m = Select-String -Path $f -Pattern "https://[a-z0-9-]+\.trycloudflare\.com" -ErrorAction SilentlyContinue
      if ($m) { $TunnelUrl = $m.Matches[0].Value; break }
    }
  }
  if ($TunnelUrl) { break }
}
if (-not $TunnelUrl) { Die "Tunnel did not come up. See $logDir\cf.log" }
Ok $TunnelUrl

# --- 4. rebuild frontend against the new tunnel ------------------------------
# .env.production.local is the highest-priority production env file, so it
# outranks .env.local (which points at localhost for dev). Gitignored via *.local.
Step 4 "Rebuilding frontend against the new tunnel URL"
$fe = Join-Path $Root "frontend"
"VITE_API_BASE_URL=$TunnelUrl" | Out-File (Join-Path $fe ".env.production.local") -Encoding ascii
Push-Location $fe
$prevEAP = $ErrorActionPreference
$ErrorActionPreference = "Continue"   # same 5.1 stderr trap as the vercel call
& npm run build
$buildCode = $LASTEXITCODE
$ErrorActionPreference = $prevEAP
Pop-Location
if ($buildCode -ne 0) { Die "Frontend build failed (exit $buildCode)" }
$bundle = Get-ChildItem (Join-Path $fe "dist\assets\*.js") | Select-Object -First 1
if (-not (Select-String -Path $bundle.FullName -Pattern ([regex]::Escape($TunnelUrl)) -Quiet)) {
  Die "Built bundle does not contain the tunnel URL"
}
Ok "tunnel URL baked into bundle"

# --- 5. redeploy -------------------------------------------------------------
# Deploy the built dist as static files, carrying .vercel so it lands on the
# existing project and keeps the business-search-inky URL.
Step 5 "Redeploying to Vercel"
$stage = Join-Path $env:TEMP "business-search-deploy"
Remove-Item $stage -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $stage | Out-Null
Copy-Item (Join-Path $fe "dist\*") $stage -Recurse
Copy-Item (Join-Path $fe "vercel.json") $stage
Copy-Item (Join-Path $fe ".vercel") $stage -Recurse
Push-Location $stage
# No 2>&1, and EAP relaxed: PowerShell 5.1 wraps a native exe's stderr in an
# ErrorRecord (NativeCommandError) and trips ErrorActionPreference='Stop' even
# when the exe exits 0. vercel writes its progress to stderr. Trust the exit
# code instead, then confirm for real in step 6.
$prevEAP = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& vercel deploy --prod --yes --token $Token
$deployCode = $LASTEXITCODE
$ErrorActionPreference = $prevEAP
Pop-Location
if ($deployCode -ne 0) { Die "Vercel deploy failed (exit $deployCode)" }
Ok "deployed"

# --- 6. verify ---------------------------------------------------------------
Step 6 "Verifying end to end"
$body = @{ query = "Teach my staff to spot fake emails and scams"; limit = 2 } | ConvertTo-Json
try {
  $r = Invoke-RestMethod -Method Post -Uri "$TunnelUrl/api/search" `
       -ContentType "application/json" -Headers @{ Origin = $VercelUrl } -Body $body -TimeoutSec 90
} catch { Die "Search request failed: $_" }
if (-not $r.results -or $r.results.Count -eq 0) { Die "Search returned no results" }
if ($r.intent) { Ok "intent: $($r.intent.underlying_need)  [source: $($r.intent.source)]" }
else { Write-Host "      WARN  intent was null on the check query" -ForegroundColor Yellow }
Ok "top result: $($r.results[0].business_name) ($($r.results[0].sub_category))"

Write-Host "`n============================================" -ForegroundColor Green
Write-Host " READY - share this link:" -ForegroundColor Green
Write-Host " $VercelUrl" -ForegroundColor White
Write-Host "============================================" -ForegroundColor Green
Write-Host " Backend tunnel: $TunnelUrl"
Write-Host " Keep this laptop AWAKE. Sleep kills the tunnel."
Write-Host " Logs: $logDir`n"
