# Render keepalive — how it works

## The problem

Render's **free tier** spins web services down after about **15 minutes** of inactivity. The first request after spin-down takes 30–60 seconds to return — which means during a live demo, the page either hangs or shows `BACKEND UNREACHABLE`.

## The fix

A GitHub Actions workflow ([`.github/workflows/keepalive.yml`](../.github/workflows/keepalive.yml)) pings `https://quill-sr8l.onrender.com/health` every 10 minutes from GitHub's runners.

That stays comfortably inside Render's 15-minute idle window. The service never sleeps.

## Cost

**$0.** GitHub Actions scheduled workflows on public + free private repos are free up to 2,000 minutes/month. Our keepalive uses about 15 seconds × 144 runs/day ≈ **65 minutes/month**.

## To stop it

Either:

- **Disable from GitHub UI:** Repo → Actions tab → "Keep Render deploy warm" → ⋯ → Disable workflow
- **Delete the file:** `git rm .github/workflows/keepalive.yml` and push

## To wake the service manually

Repo → Actions tab → "Keep Render deploy warm" → **Run workflow** → Run workflow. Or:

```bash
curl https://quill-sr8l.onrender.com/health
```

## Why GitHub Actions and not UptimeRobot / cron-job.org

- **No third-party signup.** Lives in your repo, visible alongside the code.
- **Logs are in GitHub Actions.** No separate dashboard to remember the password to.
- **Free.** Same as the alternatives, no rate-limit surprises.
- **Stops automatically** when the repo is archived or the workflow is deleted.

The trade-off: GitHub Actions schedules can drift 5–15 minutes under cluster load. We picked a 10-minute interval (not 14) so even with worst-case drift we stay inside the 15-minute window.

## When to retire this

Whenever you upgrade Render to **Starter plan ($7/mo)** or move to a host that doesn't spin down. At that point delete this workflow and the smart-banner cold-start retry logic becomes dead code (the [Banner UX section in app.js](../desktop/web/app.js) — search for `_coldStartRetrying`).

## Related

- The frontend has a **smart cold-start retry** (`refreshHealth` in `desktop/web/app.js`). It auto-retries `/health` for ~2 minutes when it sees a 502/503/504, so even during the warm-up gap the user sees `Server starting up…` instead of a broken page.
- HTTP Basic Auth is set via `QUILL_BASIC_AUTH_USER` + `QUILL_BASIC_AUTH_PASSWORD` env vars on Render. `/health` is intentionally outside the auth gate so this keepalive doesn't need credentials.
