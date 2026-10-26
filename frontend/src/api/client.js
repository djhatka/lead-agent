/*
  The ONE place that talks to the backend.

  Every page asks for data through `api.*` below (via TanStack Query hooks
  in src/hooks), never with fetch() directly, so the address, error
  handling and JSON parsing live in one spot.

  Errors become an ApiError with a readable message: FastAPI's "detail"
  (a sentence, or a list of field problems) is turned into text a shop
  owner can understand.

  Parts the server doesn't have yet
  ---------------------------------
  The functions follow the API in FRONTEND_PROMPT.md. If the server
  answers "Not Found" for a whole address (FastAPI's own reply for a
  route it doesn't have), we try, in order:
    1. the older route that holds the same data (e.g. /analytics/peak-times
       for /analytics/timing, /insights for /growth/reports), and
    2. built-in sample data (src/api/sample), so the page still works.
  Sample answers are counted per business and area, and the top bar shows
  a "Sample data" pill on any page that used them. Nothing done on sample
  data reaches the server. Set VITE_SAMPLE_FALLBACK=false to turn this off
  and see the real errors instead.

  An older server only knows one business. Its data is shown as demo
  business SERVER_BUSINESS_ID; the other demo businesses are all sample.
*/

const BASE = import.meta.env.DEV
  ? '/api' // Vite forwards /api/... to VITE_API_URL (see vite.config.js): no CORS trouble, live feed included
  : (import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000').replace(/\/$/, '')
const SAMPLE_FALLBACK = import.meta.env.VITE_SAMPLE_FALLBACK !== 'false'
export const SERVER_BUSINESS_ID = 2

export class ApiError extends Error {
  constructor(status, message, { missing = false } = {}) {
    super(message)
    this.status = status
    this.missing = missing // the server has no such address at all
  }
}

function readableDetail(detail) {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    // FastAPI validation errors: [{ loc: ["body", "phone"], msg: "..." }]
    return detail.map((d) => `${d.loc?.slice(1).join('.') || 'value'}: ${d.msg}`).join('; ')
  }
  return null
}

/** Build "?a=1&b=2", skipping empty values so filters can be left blank. */
function query(params = {}) {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') search.set(key, String(value))
  }
  const text = search.toString()
  return text ? `?${text}` : ''
}

// ------------------------------------------------------------- login
// The backend locks everything behind a login. After POST /auth/login we keep
// its token in this browser and send it with every request
// ("Authorization: Bearer <token>"). A 401 means the token is gone or
// expired: we forget it, and the app shows the login page again.
const TOKEN_KEY = 'lead-intel-token'
let token = (() => {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
})()
const authWatchers = new Set()

function setToken(value) {
  token = value
  try {
    if (value) localStorage.setItem(TOKEN_KEY, value)
    else localStorage.removeItem(TOKEN_KEY)
  } catch {
    // Not remembered after a reload, but works for this visit.
  }
  authWatchers.forEach((notify) => notify())
}

export const auth = {
  subscribe(notify) {
    authWatchers.add(notify)
    return () => authWatchers.delete(notify)
  },
  snapshot: () => token,
  async login(email, password) {
    const { data } = await http('POST', '/auth/login', { body: { email, password } })
    setToken(data.token)
    return data
  },
  /** A new owner: creates their account AND their business in one go, then logs them in. */
  async signup(details) {
    const { data } = await http('POST', '/auth/signup', { body: details })
    setToken(data.token)
    return data
  },
  async logout() {
    try {
      await http('POST', '/auth/logout')
    } catch {
      // Already logged out on the server: just forget it here.
    }
    setToken(null)
  },
}

async function http(method, path, { params, body } = {}) {
  let response
  try {
    const headers = {}
    if (body) headers['Content-Type'] = 'application/json'
    if (token) headers.Authorization = `Bearer ${token}`
    response = await fetch(`${BASE}${path}${query(params)}`, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
    })
  } catch {
    throw new ApiError(0, "Can't reach the server. Is the backend running?")
  }

  const data = response.status === 204 ? null : await response.json().catch(() => null)
  // In development, Vite's proxy answers 502/503/504 (with no JSON) when the backend isn't running.
  if ([502, 503, 504].includes(response.status) && !data?.detail) {
    throw new ApiError(response.status, "Can't reach the server. Is the backend running?")
  }
  if (response.status === 401 && token && path !== '/auth/login') setToken(null) // logged out: back to the login page
  if (!response.ok) {
    const missing = (response.status === 404 && data?.detail === 'Not Found') || response.status === 405
    const message = missing
      ? "This part isn't on the server yet."
      : (readableDetail(data?.detail) ?? `The server answered ${response.status}.`)
    throw new ApiError(response.status, message, { missing })
  }
  return { data, headers: response.headers }
}

const get = async (path, params) => (await http('GET', path, { params })).data
const post = async (path, body, params) => (await http('POST', path, { body, params })).data

// ------------------------------------------------- sample data bookkeeping
// { "1": ["content", "reviews"], ... }: which areas of which business came from sample data.
let sampleUsed = {}
const sampleWatchers = new Set()

function markSample(business, area) {
  const key = String(business ?? 'any')
  if (sampleUsed[key]?.includes(area)) return
  sampleUsed = { ...sampleUsed, [key]: [...(sampleUsed[key] ?? []), area] }
  sampleWatchers.forEach((notify) => notify())
}

export const sampleUsage = {
  subscribe(notify) {
    sampleWatchers.add(notify)
    return () => sampleWatchers.delete(notify)
  },
  snapshot: () => sampleUsed,
}

// null until GET /businesses has answered; false = an older single-business server
let serverKnowsBusinesses = null

/** True when the server doesn't know this business at all (everything about it is sample data). */
export function isSampleOnlyBusiness(business) {
  return SAMPLE_FALLBACK && serverKnowsBusinesses === false && Number(business) !== SERVER_BUSINESS_ID
}

async function fromSample(area, business, method, path, { params, body }) {
  const { handle } = await import('./sample/index.js') // only downloaded when needed
  try {
    const data = await handle(method, path, { params, body })
    markSample(business, area)
    return data
  } catch (error) {
    throw new ApiError(error.status ?? 500, error.message)
  }
}

/**
 * Ask the server; if it doesn't have this address, try `legacy` (an older
 * route with the same data), then sample data.
 */
async function call(area, method, path, { business, params, body, legacy } = {}) {
  const fullParams = business != null ? { business_id: business, ...params } : params

  if (business == null || !isSampleOnlyBusiness(business)) {
    try {
      return (await http(method, path, { params: fullParams, body })).data
    } catch (error) {
      if (!(error instanceof ApiError && error.missing)) throw error
      if (legacy) {
        try {
          return await legacy()
        } catch (legacyError) {
          if (!(legacyError instanceof ApiError && legacyError.missing)) throw legacyError
        }
      }
      if (!SAMPLE_FALLBACK) throw error
    }
  }
  return fromSample(area, business, method, path, { params: fullParams, body })
}

// ------------------------------------------------------ shape helpers
// Lists may come back as a page ({items, total}) or a plain array.
function asPage(data) {
  if (Array.isArray(data)) return { items: data, total: data.length }
  return { ...data, items: data?.items ?? [], total: data?.total ?? data?.items?.length ?? 0 }
}

const asList = (data) => (Array.isArray(data) ? data : (data?.items ?? []))

// Leads are paged with page/page_size by the current server and limit/offset in the brief: send both.
function paging({ page = 1, page_size = 25, ...rest } = {}) {
  return { ...rest, page, page_size, limit: page_size, offset: (page - 1) * page_size }
}

/** The content calendar as { start, days: [{ date, posts }] }, whatever shape it arrives in. */
function asCalendar(data, start, days) {
  if (data?.days) return data
  const posts = asList(data?.posts ?? data)
  const dayKeys = Array.from({ length: days }, (_, i) => {
    const d = new Date(`${start}T00:00:00Z`)
    d.setUTCDate(d.getUTCDate() + i)
    return d.toISOString().slice(0, 10)
  })
  const istDay = (iso) => new Date(iso).toLocaleDateString('en-CA', { timeZone: 'Asia/Kolkata' })
  return {
    start,
    days: dayKeys.map((date) => ({
      date,
      posts: posts.filter((p) => (p.date ?? istDay(p.scheduled_at ?? p.published_at ?? p.created_at)) === date),
    })),
  }
}

// --------------------------------------- the older server's weekly review
// /insights stores { report, top_actions: [text], weak_platforms }. Its run's
// steps hold the analyst's findings and the presence audit, so we read those
// too and shape everything like a /growth/reports report.
const IMPACT_STATUS = { high: 'missing', medium: 'warn', low: 'warn' }
const CHANNEL_NAMES = {
  whatsapp: 'WhatsApp', instagram: 'Instagram', website: 'Website', google: 'Google',
  indiamart: 'IndiaMART', justdial: 'Justdial', walkin: 'Walk-in',
}

/** "Rs 56,000" / "Rs. 2.1 lakh" → "₹56,000" / "₹2.1 lakh": money is always shown with ₹. */
const rupeeSign = (text) => (typeof text === 'string' ? text.replace(/\bRs\.? ?(?=\d)/g, '₹') : text)

async function legacyReport(raw, { withRun = true } = {}) {
  const strategy = { ...raw, report: rupeeSign(raw.report), top_actions: raw.top_actions.map(rupeeSign) }
  // Split at ". " + a new sentence, so "(6.7%)" and "Rs 56,000" stay whole.
  const sentences = strategy.report.split(/(?<=[.!?])\s+(?=[A-Z0-9₹])/).map((s) => s.trim()).filter(Boolean)
  let findings = strategy.weak_platforms.map((p) => ({
    kind: 'bad',
    title: `${CHANNEL_NAMES[p] ?? p} is not bringing customers`,
    detail: null,
  }))
  let presence = []
  if (withRun && strategy.run_id) {
    const run = await get(`/agent-runs/${strategy.run_id}`).catch(() => null)
    const step = (agent) => run?.steps.find((s) => s.agent === agent)?.output ?? {}
    const analystFindings = step('data_analyst').findings ?? []
    if (analystFindings.length) findings = analystFindings.map((text) => ({ kind: 'note', title: rupeeSign(text), detail: null }))
    presence = (step('presence_auditor').items ?? []).map((item) => ({
      platform: item.platform,
      item: rupeeSign(item.issue),
      status: IMPACT_STATUS[item.impact] ?? 'warn',
      detail: rupeeSign(item.fix),
    }))
  }
  return {
    id: strategy.id,
    run_id: strategy.run_id,
    created_at: strategy.created_at,
    period_start: strategy.period_start,
    period_end: strategy.period_end,
    headline: sentences[0],
    summary: sentences.slice(1).join(' '),
    findings,
    presence,
    actions: strategy.top_actions.map((title) => ({
      title,
      why: presence.find((p) => p.detail === title)?.item ?? null,
    })),
    content_plan: strategy.content_plan,
  }
}

/** The weekly review as a WhatsApp message (for servers that can't write one). */
export function reportAsWhatsapp(report, businessName) {
  const lines = [`*Weekly review${businessName ? ` · ${businessName}` : ''}*`, '', report.headline]
  if (report.summary) lines.push('', report.summary)
  if (report.actions?.length) {
    lines.push('', '*This week, do these 3 things:*')
    report.actions.forEach((a, i) => lines.push(`${i + 1}. ${a.title}`))
  }
  return lines.join('\n')
}

// ------------------------------------------- translating the backend's answers
// The pages were built from FRONTEND_PROMPT.md; the backend names some things
// differently. These small functions turn each backend answer into the shape
// the pages expect, so no page needs to know. Nothing is invented: every
// number comes from the backend, or is counted here from its own leads.
const round1 = (n) => (n == null || Number.isNaN(n) ? null : Math.round(n * 10) / 10)
const pct = (part, whole) => (whole ? round1((part / whole) * 100) : 0)
const changePct = (now, before) => (before ? round1(((now - before) / before) * 100) : null)
const istDay = (iso) => new Date(iso).toLocaleDateString('en-CA', { timeZone: 'Asia/Kolkata' })
const istHour = (iso) => Number(new Date(iso).toLocaleString('en-GB', { timeZone: 'Asia/Kolkata', hour: '2-digit', hourCycle: 'h23' }))

// Channel keys: the backend writes "walk_in", the dashboard "walkin".
const SOURCE_IN = { walk_in: 'walkin' }
const SOURCE_OUT = { walkin: 'walk_in' }
const sourceIn = (s) => SOURCE_IN[s] ?? s
const sourceOut = (s) => SOURCE_OUT[s] ?? s

/** "+919810012345" → "9810012345": the dashboard adds +91 itself (call / WhatsApp buttons). */
const phoneIn = (p) => (typeof p === 'string' && /^\+91\d{10}$/.test(p) ? p.slice(3) : p)

function leadIn(lead) {
  if (!lead) return lead
  return {
    ...lead,
    source: sourceIn(lead.source),
    phone: phoneIn(lead.phone),
    car_model: lead.car_model ?? lead.details?.car_model ?? null,
    source_post: lead.source_post ?? null,
    messages: lead.messages?.map((m) => ({ ...m, direction: m.direction === 'outbound' ? 'out' : 'in' })),
  }
}

// Post types: the backend has photo / video / text too.
const KIND_IN = { photo: 'post', text: 'post', video: 'reel' }
const KIND_OUT = { post: 'photo' }

function postIn(p) {
  if (!p) return p
  const when = p.scheduled_for ?? p.published_at ?? null
  const done = p.status === 'published'
  return {
    ...p,
    format: KIND_IN[p.kind] ?? p.kind,
    scheduled_at: p.scheduled_for ?? null,
    error: p.publish_error || null,
    shot_list: p.media_note ? p.media_note.split('\n').filter(Boolean) : [],
    date: when ? istDay(when) : null,
    best_hour: when ? istHour(when) : null,
    suggested_at: when,
    metrics: done ? { reach: p.reach, likes: p.likes, comments: p.comments, saves: p.saves, shares: p.shares } : null,
    results: done ? { enquiries: p.enquiries ?? 0, customers: p.sales ?? 0, revenue: p.revenue ?? 0 } : null,
  }
}

function postOut(changes) {
  const out = { ...changes }
  if ('format' in out) {
    out.kind = KIND_OUT[out.format] ?? out.format
    delete out.format
  }
  if ('shot_list' in out) {
    out.media_note = (out.shot_list ?? []).join('\n')
    delete out.shot_list
  }
  for (const key of ['scheduled_at', 'date', 'best_hour', 'suggested_at', 'metrics', 'results', 'error']) delete out[key]
  return out
}

const RUN_STATUS_IN = { success: 'done' }
const runIn = (run) => run && { ...run, status: RUN_STATUS_IN[run.status] ?? run.status }

const industryLabel = (i) => (i ? i.replaceAll('_', ' ').replace(/^\w/, (c) => c.toUpperCase()) : null)
const businessIn = (b) =>
  b && { ...b, phone: phoneIn(b.phone), category: b.industry, category_label: industryLabel(b.industry), opening_hours: b.opening_hours ?? null }

function businessOut(changes) {
  const out = { ...changes }
  if ('category' in out) {
    out.industry = out.category
    delete out.category
  }
  delete out.category_label
  delete out.opening_hours // the backend doesn't store opening hours yet
  return out
}

const topicIn = (t) => ({ topic: t.replaceAll('_', ' ').replace(/^\w/, (c) => c.toUpperCase()), count: '' })

function reviewIn(r) {
  return {
    ...r,
    author: r.author_name,
    created_at: r.reviewed_at,
    praised: r.sentiment === 'positive' ? r.topics ?? [] : [],
    complaints: r.sentiment === 'negative' ? r.topics ?? [] : [],
    reply_text: r.reply_status === 'posted' ? r.reply_text : null,
    draft_reply: r.reply_status === 'drafted' ? r.reply_text : null,
  }
}

/**
 * Every lead of the period, for the numbers the backend doesn't send directly
 * (reply within 5 minutes, open/lost per channel, enquiries per day...).
 * Fetched in pages of 200, shared for a few seconds between the cards of one page.
 */
const leadCache = new Map()
function periodLeads(b, days) {
  const key = `${b}:${days}`
  const hit = leadCache.get(key)
  if (hit && Date.now() - hit.at < 15_000) return hit.promise
  const promise = (async () => {
    const since = Date.now() - days * 86_400_000
    const all = []
    for (let offset = 0; offset < 5000; offset += 200) {
      const page = await get('/leads', { business_id: b, limit: 200, offset })
      const items = asList(page)
      all.push(...items)
      const oldest = items.at(-1)
      if (items.length < 200 || (oldest && new Date(oldest.created_at).getTime() < since)) break
    }
    return all.filter((l) => new Date(l.created_at).getTime() >= since)
  })()
  promise.catch(() => leadCache.delete(key))
  leadCache.set(key, { at: Date.now(), promise })
  return promise
}

const repliedWithin = (lead, mins) =>
  lead.first_response_at && new Date(lead.first_response_at) - new Date(lead.created_at) <= mins * 60_000

async function summaryIn(b, days) {
  const [now, both, leads] = await Promise.all([
    get('/analytics/summary', { business_id: b, days }),
    get('/analytics/overview', { business_id: b, days: days * 2 }),
    periodLeads(b, days),
  ])
  const o = now.overview
  const prev = { leads: both.leads - o.leads, won: both.won - o.won, revenue: both.revenue - o.revenue }
  return {
    period: { days },
    leads: o.leads,
    won: o.won,
    conversion_pct: o.conversion_rate,
    revenue: o.revenue,
    avg_job_value: o.avg_sale,
    median_reply_minutes: o.median_reply_minutes,
    replied_within_5_min_pct: pct(leads.filter((l) => repliedWithin(l, 5)).length, leads.length),
    unanswered: o.never_replied,
    open_hot_leads: o.hot_open,
    previous_leads: prev.leads,
    previous_won: prev.won,
    previous_revenue: prev.revenue,
    leads_change_pct: changePct(o.leads, prev.leads),
    revenue_change_pct: changePct(o.revenue, prev.revenue),
    highlights: now.highlights,
  }
}

async function sourcesIn(b, days) {
  const [rows, leads] = await Promise.all([get('/analytics/sources', { business_id: b, days }), periodLeads(b, days)])
  return rows.map((s) => {
    const mine = leads.filter((l) => l.source === s.source)
    return {
      source: sourceIn(s.source),
      leads: s.leads,
      won: s.won,
      lost: mine.filter((l) => l.status === 'lost').length,
      open: mine.filter((l) => !['won', 'lost'].includes(l.status)).length,
      conversion_pct: s.conversion_rate,
      revenue: s.revenue,
      avg_job_value: s.won ? Math.round(s.revenue / s.won) : null,
      revenue_per_lead: s.leads ? Math.round(s.revenue / s.leads) : 0,
      lead_share_pct: s.share_of_leads,
      revenue_share_pct: s.share_of_revenue,
      median_reply_minutes: s.median_reply_minutes,
      unanswered: mine.filter((l) => !l.first_response_at).length,
    }
  })
}

async function funnelIn(b, days) {
  const leads = await periodLeads(b, days)
  const by_status = { new: 0, contacted: 0, quoted: 0, booked: 0, won: 0, lost: 0 }
  leads.forEach((l) => (by_status[l.status] = (by_status[l.status] ?? 0) + 1))
  return {
    received: leads.length,
    replied: leads.filter((l) => l.first_response_at).length,
    won: by_status.won,
    by_status,
  }
}

async function trendIn(b, days) {
  const leads = await periodLeads(b, days)
  const out = []
  for (let i = days - 1; i >= 0; i--) {
    const date = istDay(Date.now() - i * 86_400_000)
    const that = leads.filter((l) => istDay(l.created_at) === date)
    out.push({ date, leads: that.length, won: that.filter((l) => l.status === 'won').length })
  }
  return out
}

const WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
function timingIn(t) {
  const hours = Array.from({ length: 24 }, (_, hour) => ({ hour, leads: t.leads_by_hour?.[hour] ?? 0 }))
  return {
    hours,
    weekdays: WEEKDAYS.map((d) => ({ day: d.slice(0, 3), leads: t.leads_by_day?.[d] ?? 0 })),
    busiest_hours: [...hours].filter((h) => h.leads).sort((a, b) => b.leads - a.leads).slice(0, 3).map((h) => h.hour),
    reply_speed: (t.conversion_by_reply_speed ?? []).map((r) => ({
      bucket: r.reply_speed,
      leads: r.leads,
      won: r.won,
      win_rate_pct: r.conversion_rate,
    })),
  }
}

function contentStatsIn(s) {
  const sum = (rows, f) => rows.reduce((n, r) => n + (f(r) ?? 0), 0)
  const platforms = s.by_platform ?? []
  return {
    period_days: s.days,
    totals: {
      posts: s.published_posts,
      reach: sum(platforms, (r) => r.avg_reach * r.posts),
      likes: null, // the backend doesn't total likes yet
      enquiries: sum(platforms, (r) => r.enquiries),
      customers: sum(platforms, (r) => r.sales),
      revenue: sum(platforms, (r) => r.revenue),
    },
    pillars: (s.by_pillar ?? []).map((r) => ({
      pillar: r.name,
      posts: r.posts,
      reach: r.avg_reach * r.posts,
      avg_reach: r.avg_reach,
      likes: null,
      engagement_pct: r.avg_engagement,
      enquiries: r.enquiries,
      customers: r.sales,
      revenue: r.revenue,
      enquiries_per_post: r.enquiries_per_post,
      revenue_per_post: r.revenue_per_post,
    })),
    platforms: platforms.map((r) => ({
      platform: r.name,
      posts: r.posts,
      reach: r.avg_reach * r.posts,
      enquiries: r.enquiries,
      revenue: r.revenue,
    })),
    findings: s.findings,
  }
}

const reviewSummaryIn = (s) => ({
  ...s,
  total: s.reviews,
  stars: s.by_stars,
  praised_for: (s.praised_for ?? []).map(topicIn),
  complaints: (s.complaints_about ?? []).map(topicIn),
  replied_pct: s.reply_rate,
  last_30_days: { count: s.reviews_30_days, average_rating: s.average_rating_30_days },
})

/**
 * The backend describes a workflow as a Mermaid flowchart (text). The page
 * wants a list of steps, so we read the step names from that text, in order,
 * and add a plain sentence about each one.
 */
const WORKFLOW_STEPS = {
  intake: ['intake', 'Intake', 'Reads the message: who it is, what they want, area and details.'],
  tone: ['sentiment', 'Tone reader', 'Reads how they feel: urgent, frustrated or casual.'],
  scoring: ['scoring', 'Scorer', 'Scores 1 to 100: how likely they are to buy, with every point explained.'],
  priority: ['priority_router', 'Hot-lead router', 'Plain rules decide: call now, or the normal queue.'],
  hot_alert: ['hot_lead', 'Hot alert', 'Flags the lead 🔥 and alerts the dashboard straight away.'],
  normal_queue: ['normal_lead', 'Normal queue', 'Adds the lead to the normal follow-up list.'],
  save: ['save', 'Save', 'Saves the result, so you can see what each helper decided.'],
  collect: ['collect_facts', 'Facts', "Plain code counts this week's numbers and the 90-day picture."],
  analyst: ['data_analyst', 'Analyst', 'Picks the 3 to 6 findings that matter most.'],
  presence: ['presence_auditor', 'Presence checker', 'Ticks a checklist: posting, replies, listings, reviews.'],
  strategist: ['strategy', 'Strategist', 'Chooses the 3 actions that bring the most customers for the least effort.'],
  writer: ['report_writer', 'Report writer', 'Writes one short message you can read on WhatsApp.'],
}
const WORKFLOW_INFO = {
  lead: ['Every new enquiry', 'Runs the moment a message arrives on any channel'],
  growth: ['Weekly growth review', 'Runs every Monday at 9am, or when you ask'],
}

async function workflowIn(path, b, name) {
  const response = await fetch(`${BASE}${path}${query({ business_id: b })}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (response.status === 401) setToken(null)
  if (!response.ok) throw new ApiError(response.status, `The server answered ${response.status}.`)
  const text = await response.text()
  try {
    const data = JSON.parse(text)
    if (data?.steps) return data // a server that already sends the list
  } catch {
    // Not JSON: the Mermaid flowchart, read below.
  }
  const names = [...text.matchAll(/^\s*([a-z_]+)\(\1\)\s*$/gm)].map((m) => m[1])
  const steps = names
    .filter((n) => n !== 'save')
    .map((n) => {
      const [agent, label, does] = WORKFLOW_STEPS[n] ?? [n, n.replaceAll('_', ' '), '']
      return { agent, label, does }
    })
  return { workflow: name, name: WORKFLOW_INFO[name][0], trigger: WORKFLOW_INFO[name][1], steps }
}

/** A weekly report as the Weekly review page expects it (headline, findings, checklist, 3 actions). */
function reportIn(r) {
  if (!r || r.headline) return r // already in the page's shape
  const stats = r.stats ?? {}
  const end = r.week_start ? new Date(`${r.week_start}T00:00:00Z`) : null
  if (end) end.setUTCDate(end.getUTCDate() + 6)
  return {
    id: r.id,
    run_id: r.agent_run_id,
    created_at: r.created_at,
    period_start: r.week_start,
    period_end: end ? end.toISOString().slice(0, 10) : null,
    headline: stats.headline ?? r.summary?.split('\n')[0],
    summary: null, // the full message is under "Copy WhatsApp message"
    whatsapp: r.summary,
    findings: (stats.findings ?? []).map((f) => ({ kind: f.impact === 'neutral' ? 'note' : f.impact, title: f.title, detail: f.detail })),
    presence: (r.presence_audit ?? []).map((p) => ({ item: p.item, status: p.status, detail: p.tip })),
    actions: (r.top_actions ?? []).map((a) => ({ title: a.action, why: a.why, effort: a.effort })),
    content_plan: r.content_plan,
  }
}

/** Live-feed event names: the backend's "lead.hot" etc. → the dashboard's names. */
export const LIVE_TYPES = {
  'lead.new': 'lead_created',
  'lead.message': 'message_added',
  'lead.analyzed': 'lead_analyzed',
  'lead.hot': 'hot_lead',
  'lead.auto_reply': 'message_added', // the AI's instant first reply: refresh the conversation
  'followup.due': 'followup_due', // the daily "3 enquiries need a follow-up today" note
  'payment.received': 'payment_received',
  'payment.claimed': 'payment_claimed', // a customer pressed "I've paid" on their payment page
  'report.ready': 'insights_ready',
  'renewal.due': 'renewal_due',
}
export function liveEventIn(event) {
  return { ...event, type: LIVE_TYPES[event.type] ?? event.type, data: { ...event.data, business_id: event.business_id } }
}

// ------------------------------------------------------------------ the API
// `b` is the business id. Every call sends it as ?business_id=.
export const api = {
  health: () => get('/health'),

  /** { mode: 'mock' | 'real', model? } */
  aiStatus: () =>
    call('ai', 'GET', '/ai/status', {
      legacy: async () => ({ mode: (await get('/health')).ai_mode ?? 'mock' }),
    }),

  // Businesses (no login yet: the top bar switches between them)
  businesses: async () => {
    try {
      const list = await get('/businesses')
      serverKnowsBusinesses = true
      return asList(list).map(businessIn)
    } catch (error) {
      if (!(error instanceof ApiError && error.missing) || !SAMPLE_FALLBACK) throw error
      serverKnowsBusinesses = false
      return asList(await fromSample('businesses', 'any', 'GET', '/businesses', {}))
    }
  },
  business: async (b) => businessIn(await call('settings', 'GET', `/businesses/${b}`, { business: b })),
  updateBusiness: async (b, changes) =>
    businessIn(await call('settings', 'PATCH', `/businesses/${b}`, { business: b, body: businessOut(changes) })),

  // Numbers (plain maths on the backend, never the AI). `days` = the period.
  summary: (b, days) => summaryIn(b, days),
  sources: (b, days) => sourcesIn(b, days),
  funnel: (b, days) => funnelIn(b, days),
  trend: (b, days) => trendIn(b, days),
  /** { hours, weekdays, busiest_hours, reply_speed: [{ bucket, leads, won, win_rate_pct }] } */
  timing: async (b, days) =>
    timingIn(await call('analytics', 'GET', '/analytics/timing', {
      business: b,
      params: { days },
      legacy: async () => {
        const [peak, speed] = await Promise.all([
          get('/analytics/peak-times', { days }),
          get('/analytics/response-times', { days }),
        ])
        return { ...peak, reply_speed: speed }
      },
    })),
  /** { services: [{ name, leads, won, revenue }], car_models? } */
  services: async (b, days) => ({
    services: asList(await call('analytics', 'GET', '/analytics/services', { business: b, params: { days } })).map((s) => ({
      name: s.service,
      leads: s.leads,
      won: s.won,
      revenue: s.revenue,
    })),
  }),

  // Enquiries
  leads: async (b, filters = {}) => {
    const page_size = Math.min(filters.page_size ?? 25, 200)
    const params = paging({ ...filters, page_size, source: filters.source && sourceOut(filters.source) })
    const data = asPage(await call('leads', 'GET', '/leads', { business: b, params }))
    return { ...data, items: data.items.map(leadIn), page: params.page, page_size }
  },
  lead: async (b, id) => leadIn(await call('leads', 'GET', `/leads/${id}`, { business: b })),
  updateLead: async (b, id, changes) => leadIn(await call('leads', 'PATCH', `/leads/${id}`, { business: b, body: changes })),
  addMessage: (b, id, message) =>
    call('leads', 'POST', `/leads/${id}/messages`, {
      business: b,
      body: { ...message, direction: message.direction === 'out' ? 'outbound' : 'inbound' },
    }),
  analyzeLead: (b, id) => call('leads', 'POST', `/leads/${id}/analyze`, { business: b }),

  // Social media: the week's posts
  calendar: async (b, start, days = 7) => {
    const data = await call('content', 'GET', '/content/calendar', { business: b, params: { start, days } })
    if (!Array.isArray(data)) return asCalendar(data, start, days)
    return { start, days: data.map((d) => ({ date: d.date, posts: asList(d.posts).map(postIn) })) }
  },
  // The backend takes the start day in the address (?start=), not in the body.
  planWeek: (b, start) => call('content', 'POST', '/content/plan-week', { business: b, params: { start } }),
  writeWeek: (b, start) => call('content', 'POST', '/content/write-week', { business: b, params: { start } }),
  writePost: (b, id) => call('content', 'POST', `/content/write/${id}`, { business: b }),
  updatePost: async (b, id, changes) =>
    postIn(await call('content', 'PATCH', `/posts/${id}`, { business: b, body: postOut(changes) })),
  schedulePost: async (b, id, scheduledAt) =>
    postIn(await call('content', 'POST', `/posts/${id}/schedule`, { business: b, body: { scheduled_for: scheduledAt } })),
  unschedulePost: async (b, id) => postIn(await call('content', 'POST', `/posts/${id}/unschedule`, { business: b })),
  publishNow: async (b, id) => postIn(await call('content', 'POST', `/posts/${id}/publish-now`, { business: b })),
  deletePost: (b, id) => call('content', 'DELETE', `/posts/${id}`, { business: b }),
  posts: async (b, filters) =>
    asList(await call('content', 'GET', '/posts', { business: b, params: { limit: 200, ...filters } })).map(postIn),
  topPosts: async (b, by, limit = 8) =>
    asList(await call('content', 'GET', '/content/top-posts', { business: b, params: { by, limit } })).map(postIn),
  contentStats: async (b, days) => contentStatsIn(await call('content', 'GET', '/content/stats', { business: b, params: { days } })),
  events: async (b) =>
    asList(await call('content', 'GET', '/content/events', { business: b })).map((e) => ({
      ...e,
      kind: e.kind ?? 'festival',
      idea: e.idea ?? e.angle,
    })),

  // Weekly review
  growthReports: async (b, limit = 10) =>
    asList(
      await call('growth', 'GET', '/growth/reports', {
        business: b,
        params: { limit },
        legacy: async () => {
          const list = await get('/insights', { page_size: limit })
          return Promise.all(list.map((s, i) => legacyReport(s, { withRun: i === 0 })))
        },
      }),
    ).map(reportIn),
  growthReport: async (b, id) =>
    reportIn(
      await call('growth', 'GET', `/growth/reports/${id}`, {
        business: b,
        legacy: async () => legacyReport(await get(`/insights/${id}`)),
      }),
    ),
  /** Starts a review. May answer with the report, or with { run_id } to follow. */
  runGrowthReview: async (b, days = 7) => {
    const result = await call('growth', 'POST', '/growth/review', {
      business: b,
      params: { days },
      legacy: () => post('/insights/run', undefined, { days }),
    })
    return result?.report ? { ...result, report: reportIn(result.report) } : result
  },
  /** { text }: the review as a WhatsApp message. Built here if the server can't write one. */
  reportWhatsapp: (b, report, businessName) =>
    call('growth', 'GET', `/growth/reports/${report.id}/whatsapp`, {
      business: b,
      legacy: async () => ({ text: report.whatsapp ?? reportAsWhatsapp(report, businessName) }),
    }).then((r) => (typeof r === 'string' ? { text: r } : { ...r, text: r.text ?? r.message ?? report.whatsapp })),

  // Reputation
  reviewSummary: async (b) => reviewSummaryIn(await call('reviews', 'GET', '/reviews/summary', { business: b })),
  reviews: async (b, filters) =>
    asList(await call('reviews', 'GET', '/reviews', { business: b, params: filters })).map(reviewIn),
  draftAllReplies: (b) => call('reviews', 'POST', '/reviews/draft-all', { business: b }),
  postReply: async (b, id, text) =>
    reviewIn(await call('reviews', 'POST', `/reviews/${id}/reply`, { business: b, body: { text } })),
  reviewRequests: async (b, filters) =>
    asList(await call('reviews', 'GET', '/review-requests', { business: b, params: filters })),
  skipReviewRequest: (b, id) => call('reviews', 'POST', `/review-requests/${id}/skip`, { business: b }),

  // The AI team's diary
  agentRuns: async (b, filters) => {
    const params = paging(filters)
    const data = asPage(await call('ai', 'GET', '/agent-runs', { business: b, params }))
    // The backend sends one page as a plain list: if it's full, there may be another page.
    const full = data.items.length === params.limit
    return {
      ...data,
      items: data.items.map(runIn),
      page: params.page,
      page_size: params.page_size,
      total: data.total > data.items.length ? data.total : params.offset + data.items.length + (full ? 1 : 0),
    }
  },
  agentRun: async (b, id) => runIn(await call('ai', 'GET', `/agent-runs/${id}`, { business: b })),
  leadWorkflow: (b) => workflowIn('/ai/lead-workflow', b, 'lead'),
  growthWorkflow: (b) => workflowIn('/growth/workflow', b, 'growth'),

  // Social accounts
  socialAccounts: async (b) =>
    asList(await call('settings', 'GET', '/social/accounts', { business: b })).map((a) => ({
      ...a,
      status: a.status ?? (a.connected ? 'connected' : 'disconnected'),
      connected_at: a.connected_at ?? (a.connected ? a.created_at : null),
    })),
  addSocialAccount: (b, account) => call('settings', 'POST', '/social/accounts', { business: b, body: account }),
  updateSocialAccount: (b, id, changes) => {
    // Connecting for real goes through Meta's / Google's own login page (the backend's /connections).
    if ('status' in changes)
      return Promise.reject(new ApiError(400, 'Connect or disconnect apps on the "Connected apps" page (in the menu).'))
    return call('settings', 'PATCH', `/social/accounts/${id}`, { business: b, body: changes })
  },

  // Phone alerts to the owner's own WhatsApp (Task 28)
  /** { phone, hot_leads, quiet_hours, sender: 'lead_intel'|'business'|'practice', recent: [alerts] } */
  alertSettings: (b) => get('/alerts/settings', { business_id: b }),
  updateAlertSettings: async (b, changes) => (await http('PUT', '/alerts/settings', { body: changes, params: { business_id: b } })).data,
  testAlert: (b) => post('/alerts/test', undefined, { business_id: b }),

  // Instant AI first reply to new WhatsApp / Instagram / Facebook enquiries (Task 29)
  /** { mode: 'off'|'always'|'after_hours', opens, closes, closed_days, note, open_now, back_at, channels, ai_mode, recent } */
  autoReplySettings: (b) => get('/auto-reply/settings', { business_id: b }),
  updateAutoReplySettings: async (b, changes) =>
    (await http('PUT', '/auto-reply/settings', { body: changes, params: { business_id: b } })).data,
  /** The reply the AI WOULD send to `message` (nothing is sent): { reply, open_now, back_at, ai_mode, check } */
  previewAutoReply: (b, message) => post('/auto-reply/preview', { message }, { business_id: b }),

  // Follow-up reminders for enquiries that have gone quiet (Task 30)
  /** { settings: { enabled, after_days }, count, items: [{ lead_id, customer, source, service, kind, reason, days, … }] } */
  followups: async (b) => {
    const data = await get('/followups', { business_id: b })
    return { ...data, items: data.items.map((r) => ({ ...r, source: sourceIn(r.source) })) }
  },
  /** One lead: { due, reminder, snoozed_until, stopped, draft: { text, how, link, note, nth, ai_mode, check } } */
  followup: (b, leadId) => get(`/followups/${leadId}`, { business_id: b }),
  /** via 'app' = send through the connected WhatsApp/Instagram/Facebook; 'phone' = I sent it from my phone */
  sendFollowup: (b, leadId, text, via) => post(`/followups/${leadId}/send`, { text, via }, { business_id: b }),
  snoozeFollowup: (b, leadId, days) => post(`/followups/${leadId}/snooze`, { days }, { business_id: b }),
  stopFollowup: (b, leadId) => post(`/followups/${leadId}/stop`, undefined, { business_id: b }),
  resumeFollowup: (b, leadId) => post(`/followups/${leadId}/resume`, undefined, { business_id: b }),
  followupSettings: (b) => get('/followups/settings', { business_id: b }),
  updateFollowupSettings: async (b, changes) =>
    (await http('PUT', '/followups/settings', { body: changes, params: { business_id: b } })).data,

  // Payments and dues: customers pay the owner's own UPI ID through a payment page (Task 31)
  /** { upi_id, payee_name, auto_reminders, ready, reminders_mode: 'real' | 'practice' } */
  dueSettings: (b) => get('/dues/settings', { business_id: b }),
  updateDueSettings: async (b, changes) => (await http('PUT', '/dues/settings', { body: changes, params: { business_id: b } })).data,
  /** { recovered_this_month, paid_this_month, recovered_last_month, waiting, open, overdue, overdue_count, says_paid } */
  dueSummary: (b) => get('/dues/summary', { business_id: b }),
  /** status: open / paid / cancelled / all; leadId: only one enquiry's payments */
  dues: (b, status = 'open', leadId) => get('/dues', { business_id: b, status, lead_id: leadId }),
  /** { due, ready: { request, reminder, how, link, note } } */
  due: (b, id) => get(`/dues/${id}`, { business_id: b }),
  createDue: (b, body) => post('/dues', body, { business_id: b }),
  sendDue: (b, id, text, via, kind) => post(`/dues/${id}/send`, { text, via, kind }, { business_id: b }),
  markDuePaid: (b, id, via) => post(`/dues/${id}/paid`, { via }, { business_id: b }),
  cancelDue: (b, id) => post(`/dues/${id}/cancel`, undefined, { business_id: b }),
  reopenDue: (b, id) => post(`/dues/${id}/reopen`, undefined, { business_id: b }),

  // Renewal reminders: memberships and services about to expire (Task 32)
  /** { settings: { enabled, remind_days_before }, count, items: [{ id, customer, service, kind, days_until, reason, … }] } */
  renewals: (b) => get('/renewals', { business_id: b }),
  /** One renewal: { id, customer_name, service, expiry_date, status, draft: { text, kind, how, link, note } } */
  renewal: (b, id) => get(`/renewals/${id}`, { business_id: b }),
  createRenewal: (b, body) => post('/renewals', body, { business_id: b }),
  sendRenewal: (b, id) => post(`/renewals/${id}/send`, undefined, { business_id: b }),
  snoozeRenewal: (b, id, days) => post(`/renewals/${id}/snooze`, { days }, { business_id: b }),
  stopRenewal: (b, id) => post(`/renewals/${id}/stop`, undefined, { business_id: b }),
  resumeRenewal: (b, id) => post(`/renewals/${id}/resume`, undefined, { business_id: b }),
  markRenewed: (b, id) => post(`/renewals/${id}/renewed`, undefined, { business_id: b }),
  renewalSettings: (b) => get('/renewals/settings', { business_id: b }),
  updateRenewalSettings: async (b, changes) =>
    (await http('PUT', '/renewals/settings', { body: changes, params: { business_id: b } })).data,

  // Monthly results ("what Lead Intel did for you", Task 27)
  /** { month, stats, message }: any month, counted now (default: this month so far) */
  roi: (b, month) => get('/roi', { business_id: b, month }),
  roiReports: async (b) => asList(await get('/roi/reports', { business_id: b })),
  /** Save a finished month's report and email it to the owners (default: last month). */
  sendRoiReport: (b, month) => post('/roi/reports', undefined, { business_id: b, month }),

  // Connected apps: Instagram, Facebook, WhatsApp, Google (the owner logs in on each platform's own page)
  /** Who is logged in, and their business: { user: { role, business_id… }, business } */
  me: () => get('/auth/me'),
  connections: async (b) => asList(await get('/connections', { business_id: b })),
  /** { platforms: { instagram: { label, mode: 'real' | 'mock' }… }, whatsapp_signup: { app_id, config_id, graph_version } } */
  connectionSetup: () => get('/connections/setup'),
  /** The address of the platform's login page. The browser goes there; the platform sends the owner back. */
  startConnection: async (b, platformKey) => (await post(`/connections/${platformKey}/start`, undefined, { business_id: b })).url,
  connectWhatsapp: (b, answer) => post('/connections/whatsapp', answer, { business_id: b }),
  disconnect: (id) => http('DELETE', `/connections/${id}`),

  // Live feed (the stream itself is opened in hooks/useLiveFeed.js)
  liveRecent: async (b, limit = 50) => (await get('/live/recent', { business_id: b })).slice(-limit).map(liveEventIn),
  /** The stream can't send a header, so the login token rides in the address (?token=). */
  liveStreamUrl: (b, afterId = 0) => `${BASE}/live/stream${query({ business_id: b, after_id: afterId, token })}`,
}
