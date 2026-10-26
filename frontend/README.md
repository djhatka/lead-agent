# Growth Partner: frontend

The owner's dashboard for the AI Growth Partner: catch every enquiry, grow on
social media, read the weekly review, and look after Google reviews. Built
from `FRONTEND_PROMPT.md`.

React 19 + Vite · Tailwind CSS 4 · React Router · TanStack Query · Recharts ·
Motion (Framer Motion) · GSAP · lucide-react.

## Run it

```bash
# 1. the backend (from the project root)
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload

# 2. the dashboard (second terminal)
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>. The port matters: the backend's CORS setting allows exactly that address.

`.env` settings:

| Setting | What it does |
|---|---|
| `VITE_API_URL` | Where the backend runs (default `http://127.0.0.1:8000`). In development the dashboard calls `/api/...` and Vite forwards it there; a production build calls it directly. |
| `VITE_SAMPLE_FALLBACK` | `true`: parts of the API the server doesn't have yet show built-in sample data, with a **Sample data** pill in the top bar. `false`: show the server's error instead. |

## Pages

| Page | Address | Endpoints |
|---|---|---|
| Home | `/` | `/analytics/summary`, `/leads?priority=hot&sort=score`, `/growth/reports?limit=1` |
| Enquiries + detail drawer | `/leads`, `/leads/:id` | `/leads`, `/leads/{id}` (GET, PATCH), `/leads/{id}/messages`, `/leads/{id}/analyze` |
| Where customers come from | `/sources` | `/analytics/sources`, `/funnel`, `/timing`, `/services`, `/trend` |
| Content calendar | `/content` | `/content/calendar`, `/content/plan-week`, `/content/write-week`, `/content/write/{id}`, `/posts/{id}` (PATCH, DELETE), `/posts/{id}/schedule`, `/unschedule`, `/publish-now` |
| What's working | `/content/performance` | `/content/top-posts?by=`, `/content/stats`, `/content/events` |
| Weekly review | `/weekly-review` | `/growth/reports`, `/growth/reports/{id}`, `/growth/review`, `/growth/reports/{id}/whatsapp` |
| Reviews | `/reviews` | `/reviews/summary`, `/reviews`, `/reviews/draft-all`, `/reviews/{id}/reply`, `/review-requests`, `/review-requests/{id}/skip` |
| AI team | `/ai-team` | `/agent-runs`, `/agent-runs/{id}`, `/ai/lead-workflow`, `/growth/workflow` |
| Settings | `/settings` | `/businesses/{id}` (GET, PATCH), `/social/accounts` (GET, POST, PATCH) |

Every request carries `?business_id=`. The business switcher in the top bar uses `GET /businesses`.
Times are always shown in India time; money as `₹1,45,500` (lakhs and crores are shortened only where space is tight: `₹10.9 L`).

## Where the data comes from today

All API calls live in `src/api/client.js`. For each call it asks the server first. If the
server answers FastAPI's own `404 Not Found` (or `405`) for the whole address, it tries:

1. **an older route with the same data**: `/analytics/peak-times` + `/analytics/response-times` for `/analytics/timing`;
   `/analytics/top` for `/analytics/services`; `/insights` (+ the run's agent steps) for the weekly review;
   `/health` for `/ai/status`;
2. **built-in sample data** (`src/api/sample/`), marked with the **Sample data** pill. Changes made to sample data
   stay in the browser and reset on reload. Nothing is sent anywhere.

The current backend (`Lead Intel`) knows one business, so:

- **Business 2 (Shine Auto Studio)** shows the server's real enquiries, numbers, AI runs, weekly reviews and live feed.
  Content, reviews, settings and workflows are sample data until the server has those routes.
- **Business 1 (gym) and 3 (dental clinic)** are entirely sample data.

Once the backend serves `GET /businesses`, every business goes to the server first.

## JSON the frontend expects from the endpoints not built yet

These are the shapes the sample data uses. If the backend sends something different, adapt it in
`src/api/client.js` (one place). Times are UTC ISO strings, money is whole rupees.

```jsonc
// GET /businesses → [Business];  GET/PATCH /businesses/{id} → Business
{ "id": 1, "name": "Pulse Fitness Studio", "category": "gym", "category_label": "Gym & fitness studio",
  "city": "Pune", "area": "Baner", "phone": "9000011111", "opening_hours": "5:30 am – 10:30 pm",
  "services": ["Monthly membership", "Personal training"], "brand_voice": "…", "target_audience": "…",
  "google_review_link": "https://g.page/r/…/review" }

// GET /ai/status
{ "mode": "mock" }                                  // or "real"

// GET /analytics/summary: the current summary, plus optionally:
{ "highlights": ["Instagram brought the most enquiries (22), but Google brought the most money: …"] }

// GET /analytics/timing
{ "hours": [{ "hour": 0, "leads": 0 }], "weekdays": [{ "day": "Mon", "leads": 9 }], "busiest_hours": [18, 19, 20],
  "reply_speed": [{ "bucket": "under 5 min", "leads": 18, "won": 5, "win_rate_pct": 27.8 }] }

// GET /analytics/services
{ "services": [{ "name": "Personal training", "leads": 9, "won": 3, "revenue": 36000 }] }

// Lead (GET /leads, /leads/{id}): the current LeadOut, plus optionally:
{ "source_post": { "id": 1012, "title": "…", "platform": "instagram", "format": "reel", "pillar": "offer",
                   "published_at": "…" } }

// Post (GET /posts, /content/top-posts, PATCH /posts/{id}, …)
{ "id": 1012, "platform": "instagram", "format": "reel",            // reel | post | story | carousel
  "pillar": "offer",            // offer | testimonial | educational | trend | behind_the_scenes | festival
  "status": "idea",             // idea | draft | scheduled | published | failed
  "title": "…", "ai_reason": "Offer posts brought 9 enquiries…", "caption": "…", "hashtags": ["#PuneGym"],
  "script": "…", "shot_list": ["…"], "date": "2026-10-20",          // the planned day, India time
  "suggested_at": "…", "scheduled_at": null, "published_at": null, "error": null,
  "created_by": "ai", "edited": false,
  "metrics": { "reach": 3808, "likes": 210, "comments": 9, "saves": 14, "shares": 6, "engagement_pct": 6.3 },
  "results": { "enquiries": 3, "customers": 1, "revenue": 6500 } }

// GET /content/calendar?start=YYYY-MM-DD&days=7      (a plain list of posts also works)
{ "start": "2026-10-18", "days": [{ "date": "2026-10-18", "posts": [Post] }] }
// POST /content/plan-week {start} → { "created": 4, "posts": [Post] }
// POST /content/write-week {start} → { "written": 4, "posts": [Post] }
// POST /posts/{id}/schedule { "scheduled_at": "…" } → Post

// GET /content/stats?days=90
{ "period_days": 90, "totals": { "posts": 37, "reach": 150656, "likes": 9000, "enquiries": 41, "customers": 9, "revenue": 44900 },
  "pillars": [{ "pillar": "offer", "posts": 12, "avg_reach": 3853, "engagement_pct": 6.1, "enquiries": 23,
                "customers": 6, "revenue": 44900, "enquiries_per_post": 1.9, "revenue_per_post": 3742 }] }

// GET /content/events
[{ "date": "2026-11-08", "name": "Diwali", "kind": "festival", "days_away": 21, "idea": "…" }]

// GET /growth/reports?limit= → [Report];  GET /growth/reports/{id} → Report;  POST /growth/review → Report (or { "run_id" } to follow)
{ "id": 103, "created_at": "…", "period_start": "…", "period_end": "…", "run_id": 10123,
  "headline": "18 enquiries and ₹8,200 in sales this week, up 39% on last week.", "summary": "…",
  "findings": [{ "kind": "good", "title": "…", "detail": "…" }],              // good | bad | note
  "presence": [{ "platform": "google", "item": "A Google post every week", "status": "warn", "detail": "…" }],  // ok | warn | missing
  "actions": [{ "title": "Reply to the 3 unhappy reviews today", "why": "…", "link": "/reviews" }] }
// GET /growth/reports/{id}/whatsapp → { "text": "*Weekly review …*" }

// GET /reviews/summary
{ "average_rating": 4.2, "total": 38, "stars": { "5": 25, "4": 5, "3": 1, "2": 4, "1": 3 },
  "praised_for": [{ "topic": "Trainers", "count": 4 }], "complaints": [{ "topic": "AC", "count": 1 }],
  "needs_attention": 5, "unreplied": 14, "replied_pct": 58, "last_30_days": { "count": 8, "average_rating": 3.5 } }

// GET /reviews → unhappy unanswered first
[{ "id": 1031, "platform": "google", "author": "Simran J.", "rating": 2, "text": "…", "created_at": "…",
   "needs_attention": true, "draft_reply": "…", "reply_text": null, "replied_at": null,
   "praised": [], "complaints": ["AC"] }]
// POST /reviews/draft-all → { "drafted": 12 };  POST /reviews/{id}/reply { "text" } → Review

// GET /review-requests
[{ "id": 1005, "lead_id": 1180, "customer_name": "…", "phone": "…", "service": "…", "channel": "whatsapp",
   "status": "pending", "send_at": "…", "sent_at": null, "reviewed_at": null, "rating": null }]   // pending | sent | reviewed | skipped

// GET /ai/lead-workflow, /growth/workflow
{ "name": "Every new enquiry", "trigger": "…", "steps": [{ "agent": "intake", "label": "Intake", "does": "…" }] }

// GET/POST/PATCH /social/accounts
[{ "id": 11, "platform": "instagram", "handle": "@pulsefitness.baner", "followers": 3840,
   "status": "connected", "connected_at": "…" }]                      // connected | expired | disconnected
```

## Folders

```
src/
  api/client.js        every API call (and the fallback rules above)
  api/sample/          sample data for routes the server doesn't have yet
  hooks/               TanStack Query hooks per area; they pick up the current business themselves
  pages/               one file per page
  components/layout/   sidebar, phone bottom bar, top bar, business switcher, page header
  components/ui/       buttons, cards, badges, drawer, toasts, empty/error states, "Draft by AI" frame
  components/charts/   bar lists, share bars, trend chart, hour columns, stat tiles
  styles/index.css     colour tokens (light and dark)
  styles/tokens.js     labels, icons, India-time and ₹ formatting
```

## Rules the UI keeps

- Nothing is posted or sent without the owner's click. Post now and Delete ask "Sure?" first.
- Anything the AI wrote and nobody approved yet has a dashed border and a "Draft by AI" label.
- Every AI decision shows its why: score breakdown, tone reason, `ai_reason` on ideas, `why` on actions.
- 🔥 hot enquiries pulse gently and unhappy reviews are red and listed first.
- Wherever a post shows reach or likes, it also shows enquiries and ₹.
- Lists and numbers refresh every 30 s, and instantly over the live feed (`/live/stream`) where the server has it.
- Works at 375 px wide (bottom bar on phones, sidebar on big screens), in light and dark, and respects "reduce motion".

`npm run build` makes the production files in `dist/`; `npm run lint` checks the code.
