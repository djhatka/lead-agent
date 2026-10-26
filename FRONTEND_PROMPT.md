# Frontend brief: AI Growth Partner for local businesses

Paste this whole file into your AI coding assistant (or read it yourself) before starting.

## What we're building
A **subscription website** for small local businesses in India (gyms, clinics, salons, car detailing studios, restaurants…). The owner logs in and sees **one dashboard** that:
1. **Catches every enquiry** (WhatsApp, Instagram, website, Justdial, Google…). The AI scores each one 1–100, labels its tone (urgent / casual / frustrated) and flags 🔥 hot leads.
2. **Grows their social media.** The AI plans the week's posts, writes captions, hashtags and reel scripts, schedules them, and shows which posts brought **customers and ₹**, not just likes.
3. **Sends a weekly growth review**: what happened, what's missing, and the top 3 actions.
4. **Manages reputation**: Google reviews, AI-drafted replies, and automatic "please review us" requests.

**The backend is already built** (FastAPI + SQLite + LangGraph AI agents). Your job is only the frontend. Don't change the backend; ask Anmol if you need a new endpoint.

## Tech stack
React (Vite) · Tailwind CSS · React Router · TanStack Query (all data fetching + caching) · Recharts (charts) · Framer Motion (page and card animations) · GSAP (number count-ups, hero moments) · lucide-react (icons).
Put the code in the `frontend/` folder next to `backend/`.

## Connecting to the backend
- Start the backend: `cd backend` then `.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload`. Fill it with demo data: `.\.venv\Scripts\python.exe -m seed.seed_data --reset --analyze`
- API base URL: `http://127.0.0.1:8000` on your laptop; the live API's https address later (Anmol will share it). Keep it in `.env` as `VITE_API_URL`. Note: `/docs` is hidden on the live server; use your local backend for it.
- **Every endpoint is documented and testable at `http://127.0.0.1:8000/docs`.** The exact JSON shapes are at `/openapi.json`, so you can generate TypeScript types from it (e.g. `openapi-typescript`).
- CORS already allows `http://localhost:5173` (the Vite default port).
- All times come back in **UTC** (`...Z`). **Always show them in India time (IST)**, e.g. "Today, 7:30 pm".
- Money is in **₹, as whole rupees**. Format Indian style: ₹1,45,500.
- **Login is required** for everything except sign-up/login (see "Login and accounts" below). Every page takes `business_id`, which comes from the logged-in user's business.
- Show a small badge when the AI is in free **mock mode** (`GET /ai/status` → `mode`).

## Login and accounts
- **Demo logins** (the password is `demo1234`): `gym@demo.in` (business 1), `garage@demo.in` (2), `clinic@demo.in` (3), `staff@demo.in` (gym staff). The admin is `admin@demo.in` / `admin1234` and sees all businesses.
- `POST /auth/login` `{email, password}` → `{token, expires_at, user, business}`. `POST /auth/signup` `{name, email, password, business_name, industry, city, area?, phone?}` → the same shape (creates the business and the owner, already logged in).
- Keep the token in `localStorage`. Send it on **every** request: `Authorization: Bearer <token>`. Do it once, in `api/client.js`.
- **Any 401** → clear the token and go to `/login` (the token expired or the user logged out elsewhere).
- 404 on another business's data is normal (users only see their own). Show 403 (e.g. staff changing settings) as "Only the business owner can do this" (the backend's `detail`).
- On app start, call `GET /auth/me` → `{user, business}`. Use `business.id` as `business_id` everywhere. Show a **business switcher only if `user.role == "admin"`** (it lists `GET /businesses`).
- **Live feed:** `EventSource` can't send headers, so add the token to the address: `/live/stream?business_id=1&token=<token>`.
- `POST /auth/logout` (then clear the token); `POST /auth/change-password` `{current_password, new_password}`.
- **Roles:** `owner` can do everything for their business; `staff` can work leads, posts and reviews but can't edit Settings or Team (hide those buttons for staff).
- Pages: **Login**, **Sign up** (industry picker with gym, clinic, salon, car detailing, restaurant…), and a **Team** tab in Settings: `GET /team`, `POST /team` `{name, email}`, `DELETE /team/{user_id}`. The new staff member gets an email to choose their own password, so the password field is optional.
- **Forgot password** (link on the Login page): `POST /auth/forgot-password {email}` always answers the same message (show it as-is).
- **`/reset-password?token=…`** (the link in the email): a "new password" form → `POST /auth/reset-password {token, new_password}` → `{token, user, business}`. Save the token and go to the dashboard; the user is logged in. When the URL also has `welcome=1` (a staff invite), say "Welcome to the team! Choose your password". Show a 400 `detail` ("expired or already used") with a link back to Forgot password.
- Admin only: an **Emails** page: `GET /admin/emails` (log) and `GET /admin/emails/{id}/preview` (open in a new tab).

## Plans and payments (Razorpay)
- **Plans:** `GET /billing/plans` is public. Use it for the **Pricing** section of the landing page and for a "Choose a plan" page. Starter is ₹999, Growth ₹2,499 (has the 14-day free trial) and Pro ₹4,999, all per month.
- **Every page:** call `GET /billing/status` → `{state, usable, plan_name, message, days_left, limits, used, payments_mode}`. Show `message` in a slim banner when `state` is `trial` (with days left), `cancelling` or `payment_failed` (red).
- **Any 402 response** means the trial or plan has ended. Send the user to the **Choose a plan** page and show the `detail` text. Billing pages still work.
- **Paying** (owner only; hide the buttons for staff):
  1. `POST /billing/subscribe {plan}` returns `{mode, key_id, subscription_id, amount, ...}`.
  2. If `mode == "real"`: load `https://checkout.razorpay.com/v1/checkout.js` and open `new Razorpay({key: key_id, subscription_id, name: "<your brand>", handler: (r) => POST /billing/verify {razorpay_payment_id, razorpay_subscription_id, razorpay_signature}}).open()`.
  3. If `mode == "mock"`: show a "Pretend to pay" button that calls `POST /billing/mock-pay`.
  4. Afterwards, re-fetch `/billing/status` and celebrate 🎉.
- **Billing page:** current plan and renewal date, "Change plan" and "Cancel" (`POST /billing/cancel`, confirm first) buttons, usage bars (`used` vs `limits`), and the payment history from `GET /billing/payments` (₹, date, plan).
- **403 with "Upgrade to …"** (e.g. adding a 2nd staff member on Starter): show it as an upgrade prompt with a button to the plans page, not as an error.
- **Admin only:** a **Money** page using `GET /admin/billing`. It shows monthly recurring revenue, payments in the last 30 days, businesses per state and plan, and a table of every business.
- Live events `billing.paid` and `billing.problem` should show as toasts.

## Connections (Settings → Connections)
Owners connect their real **WhatsApp, Instagram, Facebook Page and Google Business Profile** here. Show one card per platform with its status: connected (green), `needs_reconnect` (red, show `problem` and a "Reconnect" button), or not connected.
- `GET /connections/setup` returns each platform's `mode` (`mock` or `real`) and the details Meta's WhatsApp popup needs. In mock mode every Connect button works instantly with a pretend account, so you can build the whole page now.
- **Instagram / Facebook / Google:** call `POST /connections/{platform}/start` → `{url}`, then `window.location = url`. The owner approves on that platform and comes back to `/settings/connections?platform=...&connected=...` or `&error=...`. Show a success or error toast, then refetch `GET /connections`.
- **WhatsApp:**
  - **mock:** `POST /connections/whatsapp {"code":"mock"}`.
  - **real:** Meta's Embedded Signup popup:
    1. Load `https://connect.facebook.net/en_US/sdk.js`.
    2. `FB.init({appId: setup.whatsapp_signup.app_id, version: setup.whatsapp_signup.graph_version, xfbml: true})`.
    3. Listen to `window` `message` events from `*.facebook.com` with `data.type === "WA_EMBEDDED_SIGNUP"`, and keep `data.data.waba_id` and `data.data.phone_number_id` when `data.event` starts with `FINISH`.
    4. Call `FB.login(cb, {config_id: setup.whatsapp_signup.config_id, response_type: "code", override_default_response_type: true, extras: {setup: {}}})`. In `cb`, send `POST /connections/whatsapp {code: response.authResponse.code, waba_id, phone_number_id}`.
    5. Send it **straight away**: the code expires in 30 seconds.
- Disconnect: `DELETE /connections/{id}` (confirm first). Google card: a "Fetch reviews now" button → `POST /connections/{id}/sync`.
- **Replies now really send.** On the lead drawer, the reply box posts `POST /leads/{id}/messages {direction:"outbound", text}`. Show each reply's `delivery`:
  - ✓ `sent`
  - ⚠ `failed`, with the `delivery_error` text. It explains the WhatsApp/Instagram **24-hour rule** in plain words.
  - 📝 `logged`, meaning noted only.
  
  Add a small "I already replied from my phone" toggle that sends `send: false`.
- **Posts need photos for Instagram:** use the Media library below (`media_id`). A pasted public https link in `media_url` also works. Facebook and Google can post text only. Show a warning on Instagram posts that have no photo or video.
- Live event `connection.problem`: show a red toast with a link to Settings → Connections.

## Media library (photos and videos)
- **Upload:** `POST /media` with `FormData` holding one field, `file` (don't set Content-Type yourself; the browser does it). It accepts JPEG/PNG/WEBP photos up to 15 MB and MP4/MOV videos up to 100 MB. It returns `{id, kind, url, thumbnail_url, instagram_url, width, height, size_kb, warnings}`.
  - Show an upload progress bar (axios `onUploadProgress`, or XHR) and allow several files at once (one request per file).
  - On mobile, `<input type="file" accept="image/*,video/mp4,video/quicktime" multiple>` opens the camera roll.
- **Library page / picker:** `GET /media` → `{items, used_mb, limit_mb}`. Show a grid of `thumbnail_url` (videos: a `<video>` preview of `url`) and a storage bar "used of limit". Delete: `DELETE /media/{id}`. A 400 means it's used by a scheduled post; show the `detail`.
- **On a post:** a "Choose photo/video" button opens the library as a picker → `PATCH /posts/{id} {"media_id": 12}` (send `null` to remove it). Reels need a video and photo posts need a photo; the backend's 400 `detail` explains this.
- **Show `warnings` kindly.** Most phone photos are 3:4, and Instagram's feed needs 4:5, so the backend makes an **Instagram-ready crop** (`instagram_url`). Show both previews side by side: "Instagram feed" (the crop) and "Facebook / Google / Stories" (the full photo).
- 403 "media library is full" → show the upgrade prompt. 413 → "too big" with the `detail`.
- The `/files/...` links are public and need no token, so `<img src={url}>` works directly.

## More ways leads come in
- **Settings → Leads from email:** `GET /email-leads` → `{address, gmail_steps, platforms, gmail_confirmation_code, gmail_confirmation_link, recent}`.
  - Show the address big, with a **Copy** button, and the 4 Gmail steps as a checklist.
  - When `gmail_confirmation_code` exists, show it prominently ("Paste this in Gmail to finish"), with the link as a button.
  - Under it, list "Recent emails" with a status chip: `lead` / `added` / `duplicate` / `unparsed` (amber, "check this one") / `confirmation`.
  - Buttons: "Send me a test lead" (`POST /email-leads/test`) and "Get a new address" (`POST /email-leads/rotate`; confirm first, owner only).
  - Live event `email.confirm`: toast with the code.
- **Import customers (Leads page → Import):** a 3-step modal.
  1. Upload an .xlsx or .csv: `POST /leads/import?dry_run=true` with FormData `file`. There's also a "Download template" link: `GET /leads/import/template`.
  2. Preview: show `columns` as "Your column → we'll use it as" with a dropdown per column (name, phone, email, source, service, message, status, value, date, area, skip). On change, re-send with the form field `columns` = JSON `{"Mob": "phone"}`. Also show `preview` rows, `duplicates` ("already in your leads"), `problems` (row number + reason) and `notes`.
  3. "Import N customers": the same call with `dry_run=false`, then a success screen and a link to the Leads page.

## Public website (already built, in the backend)
The home, pricing, about, contact and legal pages (`/terms`, `/privacy`, `/refunds`, `/shipping`, `/data-deletion`) are plain HTML pages served by the backend, so you don't build them. Their buttons link to your app's routes, so make sure these exist:
- `/signup` (it may receive `?plan=growth`; preselect that plan for after the trial) and `/login`.
- On **Sign up**, under the button: "By signing up you agree to our [Terms](SITE/terms) and [Privacy policy](SITE/privacy)." This is the consent the privacy law needs.
- **Settings → Your data:** "Download my data" (`GET /account/export`, a .zip) and a red **Delete account** area. Deleting needs a modal asking for the password and the word DELETE, then `POST /account/delete {password, confirm}`. Afterwards, clear the token and go to the public home page.
- Footer links in the app: Terms, Privacy, Refunds, Contact (all on the public site).

## Pages and the endpoints they use

| Page | What the owner sees | Endpoints |
|---|---|---|
| **Home** | Leads, sales, ₹ revenue and reply time this period (count-up numbers); 🔥 hot leads to call; plain-English highlights; latest weekly review's 3 actions | `GET /analytics/summary`, `GET /leads?priority=hot&sort=score`, `GET /growth/reports?limit=1` |
| **Leads inbox** | Live updates (see Live feed below); table sorted by score; filters for status, source, priority and search; score ring + tone chip per row | `GET /leads` (filters: `status, source, priority, search, sort, limit, offset`) |
| **Lead detail** (side drawer) | Conversation thread; **why** this score (the `score_breakdown` as +/- bars) and tone reason; change status (new→contacted→quoted→booked→won/lost; won needs a ₹ value); reply box; which post brought them | `GET/PATCH /leads/{id}`, `POST /leads/{id}/messages`, `POST /leads/{id}/analyze` |
| **Sources** | Per platform: enquiries vs sales vs ₹ (the key insight: "Instagram brings enquiries, Google brings money"); funnel; busiest hours/days; "fast replies win" chart | `GET /analytics/sources`, `/funnel`, `/timing`, `/services`, `/trend` |
| **Media library** | Grid of uploaded photos/videos, upload button (drag & drop on desktop), storage bar, delete; also opens as a picker from a post | `POST /media`, `GET /media`, `DELETE /media/{id}` |
| **Content calendar** | 7-day calendar of posts as cards (idea / draft / scheduled / published / failed); "✨ Plan my week" and "✍️ Write all" buttons; click a post to edit caption, hashtags, script and shot list, then schedule it; each AI idea shows its `ai_reason` | `GET /content/calendar`, `POST /content/plan-week`, `POST /content/write-week`, `POST /content/write/{id}`, `PATCH /posts/{id}`, `POST /posts/{id}/schedule`, `/unschedule`, `/publish-now`, `DELETE /posts/{id}` |
| **Content performance** | Top posts by ₹ / enquiries / reach / engagement (tabs); what works per pillar (offer, testimonial, trend…); upcoming festivals | `GET /content/top-posts?by=`, `GET /content/stats`, `GET /content/events`, `GET /posts` |
| **Weekly review** | The latest report: headline, findings (good/bad), presence checklist (ok / warn / missing), 3 actions; "Run review now"; a "Copy WhatsApp message" button | `GET /growth/reports`, `GET /growth/reports/{id}`, `POST /growth/review`, `GET /growth/reports/{id}/whatsapp` |
| **Reviews** | Rating summary, star bars, praised for / complaints; review list with **unhappy ones first**; each shows the AI draft reply → edit → "Post reply"; review requests list (pending / sent / reviewed, with skip) | `GET /reviews/summary`, `GET /reviews`, `POST /reviews/draft-all`, `POST /reviews/{id}/reply`, `GET /review-requests`, `POST /review-requests/{id}/skip` |
| **AI team** | Timeline of AI runs; click one to replay its steps (agent name, mock/real, time taken, what it decided) as an animated flow | `GET /agent-runs`, `GET /agent-runs/{id}`, `GET /ai/lead-workflow`, `GET /growth/workflow` |
| **Settings** | Business profile (services, brand voice, target audience, Google review link); **Connections**; social accounts; Team (owner only); change password | `GET/PATCH /businesses/{id}`, `/connections…` (see above), `GET/POST/PATCH /social/accounts`, `GET/POST/DELETE /team`, `POST /auth/change-password` |

## Live feed (new leads and alerts appear instantly)
The backend pushes events with **Server-Sent Events**. No library is needed, because `EventSource` is built into browsers:
```js
const feed = new EventSource(`${API}/live/stream?business_id=${id}&token=${token}`);
feed.addEventListener("lead.hot", (e) => {
  const ev = JSON.parse(e.data);   // {id, type, business_id, at, title, message, data: {lead_id, score}}
  toast(ev.title, ev.message);     // + invalidate the TanStack Query "leads" cache
});
```
- Event types (`GET /live/types`): `lead.new`, `lead.message`, `lead.analyzed`, `lead.hot`, `post.published`, `post.failed`, `review.new`, `review.unhappy`, `report.ready`, `billing.paid`, `billing.problem`, `connection.problem`, `test`.
- On each event, **invalidate the matching queries** (leads / posts / reviews / growth), so lists refresh by themselves.
- Show `lead.hot` and `review.unhappy` as prominent toasts with a soft sound (the owner can mute it); show the rest in a small "Live" activity panel.
- The browser reconnects by itself, and missed events are re-sent (the backend keeps the last 100 per business).
- Test it: `POST /live/test?business_id=1` sends an event. For a realistic demo, run `python -m seed.simulate_traffic --every 3` in the backend folder: fake customers message every 3 seconds.

## Design direction
- **Audience:** busy, non-technical shop owners, **often on a phone**. It must work perfectly at 375px wide (bottom nav on mobile, sidebar on desktop).
- **Feel:** premium, calm and confident, not a cluttered admin template. Generous spacing, clear hierarchy, one accent colour. Light and dark themes.
- **Money and customers first, likes second.** Wherever a post shows reach or likes, also show enquiries and ₹.
- **Every AI decision shows its "why"**: score breakdown, tone reason, `ai_reason` on planned posts, `why` on actions. This builds trust.
- **Plain words**, never jargon ("Enquiries", not "Leads pipeline objects").
- **Motion with purpose:** numbers count up, cards stagger in, the hot-lead badge pulses gently, page transitions are smooth. Keep it subtle and fast (200–400ms), and respect `prefers-reduced-motion`.
- Every list needs **loading skeletons, empty states** ("No reviews yet: they'll appear here") and **friendly error messages**. The backend's `detail` field is already human-readable, so show it.

## Rules
- **Nothing gets posted or sent without the owner's click.** AI drafts look like drafts (a dashed border, a "Draft by AI" label).
- Unhappy reviews (`needs_attention: true`) and 🔥 hot leads always stand out.
- Use TanStack Query for all API calls, from one `api/client.js` file. Don't call `fetch` all over the code.
- Build page by page in this order: setup + layout → Login / Sign up → Choose a plan + Billing → Home → Leads + detail → Content calendar → Reviews → Weekly review → Sources → Content performance → AI team → Settings.
