# Lead Agent: AI growth partner for local businesses

A subscription website for local businesses (gyms, clinics, salons, car detailing, restaurants…):
**lead manager + AI social media growth + weekly growth review + reputation**, with a live feed.

- `backend/`: FastAPI + SQLite + LangGraph AI agents ✅ **built and tested** (440 automatic checks, on SQLite and PostgreSQL)
- `frontend/`: React (being built from `FRONTEND_PROMPT.md`)

---

## First-time setup (Windows, PowerShell, inside VS Code)
1. Install Python 3.12 (tick **"Add python.exe to PATH"**).
2. Open this folder in VS Code (**File → Open Folder**) and open a terminal (**Terminal → New Terminal**).
3. Run once:
   ```powershell
   cd backend
   python -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   .\.venv\Scripts\python.exe -m seed.seed_data --reset --analyze
   ```
   The last line fills the database with 3 demo businesses: 1 = Iron Pulse Fitness (gym), 2 = Gloss Garage Detailing, 3 = SmileCare Dental Clinic. They come with 300 leads, about 170 posts and 60 reviews, all already scored by the AI.

## Demo logins
Almost every address needs a login. On http://127.0.0.1:8000/docs: open `POST /auth/login`, log in, copy the `token`, click **Authorize** (top right) and paste it.

| Email | Password | Sees |
|---|---|---|
| gym@demo.in | demo1234 | Iron Pulse Fitness (owner) |
| garage@demo.in | demo1234 | Gloss Garage Detailing (owner) |
| clinic@demo.in | demo1234 | SmileCare Dental Clinic (owner) |
| staff@demo.in | demo1234 | the gym, as staff (can't change settings) |
| admin@demo.in | admin1234 | every business (you, the platform owner) |

Demo plans: the gym pays for **Growth**, the garage is on a **free trial** (9 days left), the clinic pays for **Pro**.

For the real website, make your own admin: `.\.venv\Scripts\python.exe -m seed.create_admin you@mail.com "Your Name"`

## Start the server (every time)
```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```
- http://127.0.0.1:8000/docs: **try every feature here**
- http://127.0.0.1:8000/health → `"status": "ok"`
- Stop with **Ctrl + C**

## Demo: watch it work live
In a **second terminal** (server still running):
```powershell
cd backend
.\.venv\Scripts\python.exe -m seed.simulate_traffic --every 3
```
Fake customers now message the demo businesses on WhatsApp and Instagram. Log in, then open
http://127.0.0.1:8000/live/stream?business_id=1&token=YOUR_TOKEN in a browser to watch new leads, AI scores and 🔥 hot alerts arrive live.

## Subscriptions (plans and payments)
| Plan | ₹/month | Includes |
|---|---|---|
| Starter | 999 | lead inbox + AI scoring, AI posts, review replies · 1 staff, 2 social accounts, 1 GB media |
| Growth | 2,499 | + weekly AI growth review, automatic review requests · 3 staff, 6 accounts, 5 GB media (14-day free trial) |
| Pro | 4,999 | everything · 10 staff, 20 accounts, 20 GB media |

Change prices/limits in `backend/app/plans.py`. Payments are **mock** (pretend) until you put Razorpay keys in `.env` (steps in `.env.example`).
When a trial or plan ends, the dashboard answers **402** ("choose a plan"), but enquiries keep being saved.

## Connecting the real platforms
Owners click **Connect** in Settings. Until you add app keys to `.env`, every platform runs in free **mock** mode.

| Platform | What it does once connected | What YOU set up once (for all businesses) |
|---|---|---|
| **WhatsApp** | enquiries arrive by themselves, replies send from their number, automatic review requests (template) | Meta app → add **WhatsApp** + **Facebook Login for Business** → a WhatsApp *Embedded Signup* configuration → `META_WHATSAPP_CONFIG_ID`. Become a **Tech Provider** and finish **Business Verification** |
| **Instagram** | DMs arrive, replies send, posts publish (needs a photo/video link), real numbers | Same Meta app → Instagram → *API setup with Instagram login* → `INSTAGRAM_APP_ID/SECRET`; redirect URL `PUBLIC_API_URL/connections/instagram/callback` |
| **Facebook Page** | Messenger enquiries + replies, posts publish, numbers | Meta app → Facebook Login → redirect URL `PUBLIC_API_URL/connections/facebook/callback` |
| **Google Business Profile** | reviews arrive every 30 min, replies post on Google, Updates posts | Google Cloud project → enable the Business Profile APIs → **request API access** (form) → OAuth client with redirect `PUBLIC_API_URL/connections/google/callback` |

- **Meta doorbell:** in the Meta app's Webhooks, set the callback to `PUBLIC_API_URL/webhooks/meta` and the verify token to `WEBHOOK_VERIFY_TOKEN`. Subscribe to `messages` for WhatsApp, Instagram and Page.
- Meta's **App Review** must approve each permission before *other* businesses can connect (you and your test users can try right away). Plan **2–4 weeks** for verification and review.
- Meta and Google need a public **https** address, so this works for real once the server is online. To test from your laptop before that, use a tunnel such as ngrok.
- Keys are stored **encrypted** with `SECRET_KEY`. Set a long random one before going live.

## Emails
Forgot password, welcome, team invites, "trial ends in 3 days" / "trial ended", payment receipts and "payment failed".
**Mock mode** (no `SMTP_HOST`): every email is saved in `backend/data/outbox/`. Double-click a file to see it in your browser.
Admin log: `GET /admin/emails`. For real sending, add any SMTP provider in `.env` (Brevo has a free plan; steps in `.env.example`).

## Leads from email + importing old customers
- **Lead emails** (Justdial, Sulekha, Practo, IndiaMART, 99acres…): each business gets a private address (`GET /email-leads`).
  The owner tells Gmail to forward those platforms' emails there. Every email becomes a lead with the name, phone, requirement and area read from it.
  Try it: `POST /email-leads/test`. Going live: Cloudflare Email Routing + `deploy/cloudflare-email-worker.js` (free).
  Tip: forward one real lead email from each platform you use, so the reader can be fine-tuned to its exact layout.
- **Excel / CSV import**: `POST /leads/import?dry_run=true` previews (nothing saved), `dry_run=false` imports.
  Column names, ₹ amounts, Indian dates and statuses are understood. Customers already in the system are skipped.

## Public website and legal pages
Open http://127.0.0.1:8000/ for the home page, plus `/pricing`, `/about`, `/contact`, `/terms`, `/privacy`, `/refunds`, `/shipping` and `/data-deletion`.
Prices come straight from `app/plans.py`. Fill in your company details in `.env` (`COMPANY_NAME`, `COMPANY_ADDRESS`, `SUPPORT_EMAIL`, `SUPPORT_PHONE`, `GRIEVANCE_OFFICER`, `GRIEVANCE_EMAIL`); anything missing shows highlighted in yellow.
**Before launch: have a lawyer review the Terms, Privacy and Refund pages** (they're a careful starting template, not legal advice).
Data rights: `GET /account/export` (download everything), `POST /account/delete`. Go-live checklist: `GET /admin/launch-check`.
To-do before May 2027 (DPDP Rules): automatically email and then delete businesses inactive for 12+ months.

## Going live
See **DEPLOY.md**: Railway (backend + PostgreSQL + a `/data` disk), migrations, backups, your admin login, and what to add as you get each account.

## Run the automatic checks
```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests -q
```
To run them on PostgreSQL too: set `TEST_DATABASE_URL=postgresql://user@host/testdb` first.

## Changing the database tables (migrations)
After changing `app/models.py`:
```powershell
.\.venv\Scripts\python.exe -m alembic revision --autogenerate -m "what changed"
```
Check the new file in `backend/migrations/versions/`, then commit it. Every server start applies new migrations automatically, without touching existing data. A test fails if you forget.

## Switching on the real AI (optional, costs money)
In `backend/.env` set `MOCK_AI=false` and `ANTHROPIC_API_KEY=your-key`, then restart.
Check with http://127.0.0.1:8000/ai/status. Until then, every agent runs in free **mock mode** with sensible rule-based answers.

---

## What's inside

### The AI team
| Workflow | Agents | When it runs |
|---|---|---|
| **1. New lead** (LangGraph) | Intake → Tone → Scoring → Priority → 🔥 alert / normal queue → save | Every new message, in the background |
| **Content** | Content Planner (7-day plan) → Writer (captions, hashtags, reel scripts in the brand voice) | "Plan my week" / "Write all" |
| **2. Weekly growth review** (LangGraph) | Facts → Growth Analyst + Presence Auditor (in parallel) → Strategist → Report Writer | Mondays 9am, or on demand |
| **Reputation** | Review Reply agent (drafts; owner approves) | Every new review |
| **Instant first reply** | First Reply agent (brand voice, customer's language, never prices); plain code checks it | A new WhatsApp / Instagram / Facebook enquiry, if the owner turned it on |
| **Follow-up reminders** | Follow-up agent writes the ready message (owner edits and sends it); plain code decides who's due | An enquiry quiet for 2 days (owner's choice), opened from Home or the lead |
| **Payments and dues** | No AI: plain-code messages (money is a fact). Payment page pays the owner's own UPI ID | "Request payment" in an enquiry, or "Add payment" on the Payments page |
| **Renewal reminders** | Renewal agent writes the ready "your plan ends soon" message; plain code decides who's due and adds any price | A membership / service nears its expiry date (owner's choice of days before) |
| **Fill your empty hours** | Offer agent writes a friendly invite for a slow time slot; plain code finds the slow hours and which past customers to invite | Owner opens "Fill your empty hours" |
| **Local SEO checklist** | No AI: a plain-code checklist (profile completeness, Google connection, posts, reviews, reply rate), each item explaining why it affects ranking and how to fix it | Owner opens "SEO checklist" |

Rule everywhere: **plain code calculates the numbers, the AI only explains them**, and **nothing is posted or sent without the owner**.
(The instant first reply is off until the owner turns it on and can preview it first; it never mentions prices,
discounts or links, and the lead stays "new" until the owner replies for real.)

### Background jobs (every minute, inside the server)
Publish scheduled posts · refresh post numbers · send "please review us" WhatsApps (10am–8pm only) · Monday growth reviews · monthly results report (1st of the month, 9am) · daily follow-up note (after 10am) · payment reminders (10am–8pm, if turned on).

### API map (full details at /docs)
| Area | Addresses |
|---|---|
| Billing | `/billing/plans`, `/billing/status`, `/billing/subscribe`, `/billing/verify`, `/billing/mock-pay`, `/billing/cancel`, `/billing/payments`, `/admin/billing`, `/webhooks/razorpay` |
| Media library | `POST /media` (upload), `GET /media`, `DELETE /media/{id}`, public files at `/files/...`; put one on a post with `PATCH /posts/{id} {"media_id": …}` |
| Connections | `/connections`, `/connections/setup`, `/connections/{platform}/start`, `/connections/whatsapp`, `/connections/{id}/sync`, `DELETE /connections/{id}`, `/webhooks/meta` (the real Meta doorbell) |
| Emails (admin) | `/admin/emails`, `/admin/emails/{id}/preview` |
| Leads from email / import | `/email-leads`, `/email-leads/test`, `/email-leads/rotate`, `/webhooks/email`, `/leads/import`, `/leads/import/template` |
| Your data / launch | `/account/export`, `/account/delete`, `/admin/launch-check` |
| Accounts | `/auth/signup`, `/auth/forgot-password`, `/auth/reset-password`, `/auth/login`, `/auth/logout`, `/auth/me`, `/auth/change-password`, `/team` |
| Businesses | `/businesses` |
| Leads | `/leads`, `/leads/{id}`, `/leads/{id}/messages`, `/leads/{id}/analyze` |
| Doorbells (webhooks) | `/webhooks/whatsapp`, `/instagram`, `/website`, `/universal` (any of 36 platforms), `/meta` |
| Analytics | `/analytics/summary`, `/overview`, `/sources`, `/funnel`, `/timing`, `/services`, `/trend` |
| Social media | `/social/accounts`, `/posts`, `/posts/{id}`, `/posts/{id}/stats`, `/schedule`, `/unschedule`, `/publish-now` |
| Content planning | `/content/plan-week`, `/write-week`, `/write/{id}`, `/calendar`, `/stats`, `/events`, `/top-posts` |
| Growth review | `/growth/review`, `/growth/reports`, `/growth/reports/{id}/whatsapp` |
| Phone alerts | `/alerts/settings` (GET, PUT), `/alerts/test` |
| Instant first reply | `/auto-reply/settings` (GET, PUT), `/auto-reply/preview` |
| Payments and dues | `/dues`, `/dues/summary`, `/dues/settings` (GET, PUT), `/dues/{id}`, `/dues/{id}/send`, `/paid`, `/cancel`, `/reopen`; customer page `/pay/{token}` |
| Renewal reminders | `/renewals` (GET, POST), `/renewals/settings` (GET, PUT), `/renewals/{id}`, `/renewals/{id}/send`, `/snooze`, `/stop`, `/resume`, `/renewed` |
| Fill your empty hours | `/slow-hours`, `/slow-hours/settings` (GET, PUT), `/slow-hours/{lead_id}`, `/slow-hours/{lead_id}/send`, `/skip` |
| Local SEO checklist | `GET /seo?business_id=1` (score + the checklist) |
| Follow-up reminders | `/followups`, `/followups/settings` (GET, PUT), `/followups/{lead_id}`, `/followups/{lead_id}/send`, `/snooze`, `/stop`, `/resume` |
| Monthly results | `/roi`, `/roi/reports`, `/roi/reports/{id}`, `/roi/reports/{id}/whatsapp`, `POST /roi/reports` |
| Reputation | `/reviews`, `/reviews/summary`, `/reviews/draft-all`, `/reviews/{id}/reply`, `/review-requests` |
| Live feed | `/live/stream` (SSE), `/live/recent`, `/live/test`, `/live/types` |
| AI | `/ai/status`, `/ai/read-message`, `/ai/analyze-all`, `/agent-runs`, `/ai/lead-workflow`, `/growth/workflow` |
| System | `/health`, `/scheduler/status`, `/scheduler/run`, `/platforms`, `/admin/backups` |

### Folder map
```
backend/app/
  main.py            starts everything (routers, scheduler clock, live feed)
  config.py          settings (.env)
  database.py        connection to data/leads.db
  models.py          the tables          schemas.py   the data rules
  platforms.py       36 platforms        festivals.py India festival calendar
  plans.py           the price list (Starter / Growth / Pro) and what each includes
  auth/              passwords.py (scrambling), access.py (the guard: login + own-business check),
                     paywall.py (402 when the plan/trial has ended), vault.py (locks keys, signs links)
  integrations/      meta.py (WhatsApp + Facebook), instagram.py, google.py: the real platform calls
  emails/            templates.py: the words and look of every email
  site/              the public website: routes.py, templates/ (home, pricing, legal pages), static/site.css
  routers/           the addresses (one file per area)
  services/          the work: leads, analytics, social, planner, writer, scheduler,
                     publishers, growth, reputation, messenger, event_bus,
                     billing_service + payment_gateway (Razorpay, or mock),
                     connection_service (Connect + keys + Google reviews), outbox (sends replies),
                     media_service (checks + cleans uploads), storage (where files live),
                     email_service (queue, send, retry, reminders) + mailer (SMTP, or mock),
                     email_leads (reads Justdial/Sulekha/Practo lead emails), lead_import (Excel/CSV),
                     account_service (export / delete my data), launch_check (go-live checklist),
                     followup_service, dues_service, renewal_service, slow_hours_service, seo_checklist
  agents/            llm.py (AI connector + mock mode), lead_graph.py, growth_graph.py, state.py
  agents/nodes/      one file per agent
backend/seed/        demo data, traffic simulator, create_admin, restore_backup
backend/migrations/  numbered database changes (Alembic)
backend/Dockerfile   how Railway builds the live server
deploy/              cloudflare-email-worker.js (passes lead emails to the server)
backend/tests/       440 automatic checks
```

## Progress
- [x] Tasks 1–18: backend complete (setup, database, rules, demo data, lead API, webhooks for any platform,
      AI connector, intake/tone/scoring agents, lead workflow, analytics, social accounts & posts,
      content planner, writer, scheduler & performance tracker, weekly growth review, reputation, live feed)
- [x] Task 19: login and accounts (sign up, owners/staff/admin, each business sees only its own data)
- [x] Task 20: subscriptions (14-day trial, 3 plans, Razorpay payments + renewals, paywall, plan limits, admin money page)
- [x] Task 21: real platform connections (WhatsApp, Instagram, Facebook, Google Business Profile), encrypted keys,
      one Meta doorbell for all businesses, real replies / posts / review replies, 24-hour rule
- [x] Task 22: photo & video uploads (media library, files checked by content, photos cleaned: JPEG, upright,
      location data removed, Instagram-ready 4:5 crops), storage per plan
- [x] Task 23: forgot password + emails (welcome, staff invites, trial reminders, receipts, payment failed),
      sent through any SMTP provider with retries, admin email log
- [x] Task 24: lead emails from Justdial / Sulekha / Practo / IndiaMART… (private address per business, Gmail
      confirmation handled), Excel/CSV import with preview, column guessing and duplicate skipping
- [x] Task 25: public website (home, pricing, about, contact) + Terms, Privacy (DPDP), Refunds, Shipping and data-deletion
      pages; download / delete my data; contact form; go-live checklist
- [x] Task 26: production-ready: PostgreSQL (all checks pass on it), migrations, nightly backups + tested restore,
      refuses unsafe settings, security headers, Dockerfile, deployment guide (DEPLOY.md)
- [x] Frontend (React) joined to the backend: login, sign up (account → business → connect apps), Connected apps page
- [x] Task 27: monthly ROI report ("what Lead Intel did for you"): Your results page, email on the 1st of every month,
      WhatsApp-ready text; sales counted in the month they're won, imported old customers never counted
- [x] Task 28: hot-lead alerts on the owner's own WhatsApp (Settings → Phone alerts): once per lead, optional quiet
      hours (10pm–8am), test button, 3 retries; sent from Lead Intel's own number, the business's WhatsApp, or practice mode
- [x] Task 29: instant AI first reply to new WhatsApp / Instagram / Facebook enquiries (Settings → Instant first
      reply): off / always / only after hours, opening times and closed days, optional note, preview; in the
      customer's language and the brand voice, never prices or links (plain-code check), once per enquiry
- [x] Task 30: follow-up reminders for enquiries that went quiet ("Follow up today" on Home, and in each lead):
      a ready message in the customer's language, sent in one tap (from the dashboard within WhatsApp's 24 hours,
      otherwise "Open WhatsApp" on your phone); remind me tomorrow / in 3 days / stop; at most 2 follow-ups, then
      we stop; daily "📋 3 enquiries need a follow-up" note on the live feed (Settings → Follow-up reminders)
- [x] Task 31: payments and dues (Payments page, "Request payment" in each enquiry, Settings → Payments): a payment
      page per due with a "Pay with any UPI app" button and QR code that pays the owner's own UPI ID (Lead Intel
      never holds money), "I've paid" button for the customer, one-tap "Confirm paid", "₹ recovered this month",
      polite automatic WhatsApp reminders (due date, +3, +7 days; off by default). Razorpay automatic links: after
      the Razorpay Partner approval (go-live guide)
- [x] Task 32: renewal reminders (Renewals page, Settings → Renewal reminders): add a customer's membership or
      service with its expiry date; a ready renewal message in the customer's language a few days before it ends;
      sent / remind me later / stop / "Renewed"; plain code decides who's due and writes any price
- [x] Task 33: fill your empty hours ("Fill your empty hours" page, Settings): plain code finds the business's slow
      time slots from past enquiries and picks past customers who haven't come back for a while; the AI writes a
      friendly invite for that slot (never invents prices); sent / skip, so nobody is invited too often
- [x] Task 34: local SEO checklist ("SEO checklist" page): a 0-100 score and a plain-code checklist covering
      NAP consistency (name/address/phone match everywhere), a complete Google profile, an active connection,
      recent Google posts, review count/rating, and reply rate — each item explains WHY it affects Google Maps
      ranking and HOW to fix it, no AI involved
- [ ] Tasks 35–40: see the "Lead Intel: Roadmap, Go-Live and Approvals" guide

## Next (Part C: the business side)
- Your domain, real accounts (Razorpay, email, Meta, Google), and the frontend: see DEPLOY.md
