# Deployment

LedgerGuard's UI and API are deployed as two separate services, because the project's Python
dependency set measures ~320 MB installed (scipy 113 + pandas 76 + sklearn 50 + numpy 45 +
matplotlib 36 MB), well past a serverless platform's ~250 MB limit — see `PROGRESS.md` for the
measurement. Cramming it into one serverless function isn't an option; running the real pipeline
on a container host is.

```
Vercel (static)  --HTTPS/JSON-->  Render (Docker, FastAPI)
   frontend/                          the real pipeline
```

## Backend — Render

1. New Web Service → connect this repo → **Runtime: Docker** (the existing root `Dockerfile`).
2. Environment variables (also listed in `render.yaml`):
   - `ALLOWED_ORIGINS` — comma-separated extra origins. Not required for Vercel or local dev:
     the API's CORS config already allow-lists any `https://*.vercel.app` origin and any
     `http://localhost:PORT` / `http://127.0.0.1:PORT` origin by regex.
   - `LEDGERGUARD_DB_PATH`, `LEDGERGUARD_AUDIT_PATH` — default to the OS temp dir if unset,
     which is correct on Render (its filesystem is ephemeral outside the container's own
     `/tmp`). Never point these at a path inside the repo.
3. Health check path: `/healthz`. It answers immediately without touching the pipeline, so it
   doesn't fail while the first request is still building the cached dataset.

**Verified, not assumed:**
- `pip install -e .` succeeds from a clean environment containing only `pyproject.toml` + `src/`
  — the exact layer order the Dockerfile uses — checked directly, not inferred from the file
  looking right.
- The container's assigned port: platforms like Render inject `$PORT` at runtime and health-check
  *that* port. The Dockerfile's `CMD` reads `${PORT:-8000}` (shell form, so the variable actually
  expands) rather than a hardcoded port — confirmed by starting the server with `PORT=54321` and
  hitting `54321` directly. The earlier hardcoded-port version would have started successfully
  and then failed every health check forever, since nothing would be listening on the port
  actually being probed.
- Peak resident memory building the full cached pipeline (fitting the calibrator, running L1
  over 300 records, everything the API needs at startup): **~172 MB**, comfortably under a
  512 MB free-tier limit — measured with `resource.getrusage`, not guessed from library sizes.
- `data/samples/` (what the API reads) is committed to git, so it's present via `COPY . .`.

**Free tier note:** the service sleeps after ~15 minutes idle; the next request can take up to
about a minute to wake it. Nothing in the frontend depends on this service being warm — see
"Cold starts" below.

**Not independently verifiable from this environment:** the exact current `render.yaml`
Blueprint-spec schema (key names like `runtime: docker` vs. an older `env: docker`) — Render's
own docs are blocked by this environment's network egress proxy, the same restriction this
project has hit against `razorpay.com` and `vercel.app` throughout (`BROKE.md`, Phase 0). If the
committed `render.yaml` doesn't parse as a Blueprint, the fallback that sidesteps this entirely:
skip it and create the Web Service by hand in Render's dashboard, pointing it at this repo with
Docker as the runtime — the Dockerfile itself is what's been verified, and Render's UI can use it
directly without a Blueprint file at all.

## Frontend — Vercel

1. Import this repo. **Set Root Directory to `frontend`.** This is the fix for the original
   "shows nothing" deploy: without it, Vercel's zero-config static detection was using the
   repo-root `public/` folder (which held one orphaned image) as the entire deployed output, and
   the unrelated legacy `index.html` and root `pyproject.toml` confused framework detection
   further. Setting Root Directory removes the repo root from Vercel's view entirely.
2. Framework preset: Vite (auto-detected once Root Directory is set; `frontend/vercel.json`
   pins it explicitly either way).
3. Environment variable: `VITE_API_BASE_URL` = the Render service's URL, no trailing slash.
4. Build command `npm run build`, output directory `dist` — both already in
   `frontend/vercel.json`.

**Verified, not assumed:**
- `npm ci` (the install Vercel actually runs when a lockfile is present) succeeds from a clean
  `node_modules` against the committed `package-lock.json`.
- `npm run build` (`tsc -b && vite build`) succeeds and produces `dist/index.html`,
  `dist/assets/*`, and `dist/snapshot.json` — the snapshot is written to `public/` specifically
  so Vite copies it into the build output as a static file rather than bundling it into the JS.
- Zero `npm audit` vulnerabilities (upgraded past the vite/esbuild dev-server advisories present
  in the versions first installed).
- The full page was rendered in a real headless browser (not just "the build didn't error") and
  screenshotted at each stage: initial load, the twin-case investigation, the evaluation charts
  in both light and dark mode, and a live `/execute` call end to end.

## Cold starts

Render's free tier sleeping is treated as the default case, not an edge case:

1. The page loads instantly against a committed snapshot (`frontend/public/snapshot.json`,
   `make snapshot` / `eval/snapshot.py`) — real output from a real pipeline run, never live.
2. `GET /healthz` fires immediately in parallel, with backoff retries.
3. Until it answers, the UI shows a "Snapshot · waking backend" badge — never a blank page,
   never data mislabeled as live.
4. Once the backend answers, data swaps to live and the badge flips to "Live API".

`tests/test_snapshot.py` fails the suite if the committed snapshot drifts from what the pipeline
currently produces, so a stale fallback can't silently ship.

## After deploying (needs a human)

- Confirm `<vercel-url>/` renders the dashboard, not a blank page.
- Confirm `<render-url>/healthz` returns JSON.
- If `/` is still blank after these changes, the cause is very likely the Vercel **Root
  Directory** project setting specifically — no file in this repo can set that from outside the
  dashboard.
- Update Render's `ALLOWED_ORIGINS` / re-check the CORS regex only if you deploy the frontend to
  a domain other than `*.vercel.app` or Render's own origin.
