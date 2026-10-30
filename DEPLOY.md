# Going live (Railway)

## The picture
```
GitHub (private repo: your code)  ──push──▶  Railway builds backend/Dockerfile
                                              │
            Railway project ──────────────────┼──────────────────────────┐
            ├─ api        the backend (this code), 1 copy, health check /health
            │             disk "/data": photos, emails, nightly backups, secret key
            └─ Postgres   the database (Railway's PostgreSQL)
```
- **Updating the live site** = push new code to GitHub. Railway rebuilds, runs the migrations, checks `/health`, and only then switches over. If the new version doesn't start, the old one keeps running.
- **Exactly one copy of `api`**: the scheduler clock and the live feed live inside it. (Fine for hundreds of businesses; we can split them later.)
- **Cost:** Railway's Hobby plan is $5/month and includes $5 of usage. A small site with one database usually stays around that. Check *Usage* in Railway after the first week.

## One-time setup

### 1. Code on GitHub (you, 2 minutes)
github.com → **New repository** → name `lead-agent` → **Private** → don't add a README → Create. Then tell Claude the name (`djhatka/lead-agent`). Claude pushes the code.

### 2. Railway project (Claude, through the Railway connection)
Postgres + the `api` service from the repo (root folder `backend`), a 5 GB `/data` disk, `/health` check, restart on failure, a public `https://…up.railway.app` address, and these variables:

| Variable | Value |
|---|---|
| `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` (Railway fills it in) |
| `PUBLIC_API_URL`, `SITE_URL` | the https address Railway gives (later: your domain) |
| `FRONTEND_ORIGIN` | the dashboard's address once your friend deploys it |
| `COMPANY_NAME` … `GRIEVANCE_EMAIL` | your company details (legal pages) |

`ENVIRONMENT=production` is already set inside the Dockerfile. `SECRET_KEY` is created by the server itself on first start and kept on its private disk.

### 3. Your admin login (you, in Railway's dashboard, 1 minute)
`api` → **Variables** → add `BOOTSTRAP_ADMIN_EMAIL` (your email) and `BOOTSTRAP_ADMIN_PASSWORD` (a strong password, 12+ characters; type it yourself, never share it). After the next start the logs say "Admin … created". **Then delete both variables.**

### 4. Turn on database backups (you, 30 seconds)
`Postgres` → **Backups** → enable scheduled backups (if your plan offers them). The server also writes its own nightly backup at 3am India time to `/data/backups` (14 days kept). Download one now and then from `GET /admin/backups/{name}`.

## Launch version (no approvals needed)

With ENVIRONMENT=production the server runs in **light mode** (or set LAUNCH_MODE=light). It offers only what needs no
platform approval, and never pretends:

- Hidden until their keys exist: connecting Instagram/Facebook/Google/LinkedIn, WhatsApp alerts and auto-reply, call
  tracking, competitor watch. The dashboard asks `GET /features` and hides them.
- **Posts are posted by hand.** They stay "scheduled"; the owner copies the caption, posts it, then taps *Mark as posted* (`POST /posts/{id}/mark-posted`).
- **Plans are switched on by hand.** The owner pays by UPI or bank transfer; you (admin) call
  `POST /admin/billing/activate {"business_id": 2, "plan": "growth", "days": 30}`. Calling it again extends the plan.
  Online checkout stays closed until Razorpay keys are set.
- Taking real payments and signing platform agreements needs a legal owner: use a parent or guardian until you are 18.

## Later, as you get each account
| When you have… | Do this |
|---|---|
| **Your domain** (e.g. `leadintel.in`, about ₹500–1,000/year) | Claude adds it to Railway; you add the DNS records it shows at your domain seller; then update `PUBLIC_API_URL` / `SITE_URL` |
| **Email provider** (Brevo…) | `SMTP_*`, `EMAIL_FROM` (see `.env.example`) |
| **Razorpay live keys** | `RAZORPAY_*`; webhook URL `https://<api>/webhooks/razorpay` |
| **Meta / Instagram / Google apps** | their keys; webhook `https://<api>/webhooks/meta`; redirect URLs `https://<api>/connections/{instagram,facebook,google}/callback` |
| **Lead-email domain** | Cloudflare Email Routing + `deploy/cloudflare-email-worker.js` → `https://<api>/webhooks/email` |
| **Real AI** | `MOCK_AI=false`, `ANTHROPIC_API_KEY` |
| **Lead Intel's own WhatsApp number** (for owner alerts) | In your Meta app → WhatsApp → API setup: add your number, create the `hot_lead_alert` template (category Utility, body: `🔥 New hot lead for {{1}}: {{2}}. Reply quickly to win it: {{3}}`), wait for approval, then set `ALERTS_WHATSAPP_PHONE_ID` and `ALERTS_WHATSAPP_TOKEN` (a permanent system-user token). Until then alerts go from each business's connected WhatsApp, or run in practice mode |

The go-live checklist shows what's still missing: log in as admin → `GET /admin/launch-check` (also printed in the logs at every start).

## Safety rules built in
- The live server **refuses to start** with the demo secret key, without https, or with demo accounts in the database.
- `seed_data` and `simulate_traffic` refuse to run against the live site.
- `/docs` is hidden on the live site (`SHOW_DOCS=true` to show it temporarily).
- Every reply carries security headers (https-only, no framing, no type-guessing).

## If something goes wrong
- **Logs:** Railway → `api` → Deployments → View logs (or ask Claude to read them).
- **Roll back:** Railway → Deployments → an older one → Redeploy.
- **Restore data:** a Railway Postgres backup (Backups → Restore), or our nightly file into an empty database:
  `python -m seed.restore_backup /data/backups/backup-YYYY-MM-DD.jsonl.gz`
