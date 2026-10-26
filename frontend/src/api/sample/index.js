/*
  Answers API requests from the sample world, for the parts the server
  doesn't have yet. Same addresses and shapes as FRONTEND_PROMPT.md, so
  the pages can't tell the difference (except for the "Sample data" pill
  the client adds). Changes are kept in memory until the page reloads.

  Only api/client.js calls this.
*/
import {
  addDays,
  allBusinesses,
  analyse,
  atIST,
  contentRun,
  draftReplyFor,
  funnelFor,
  growthRun,
  iso,
  istDay,
  leadRun,
  leadsBetween,
  makePost,
  makeReport,
  nextId,
  period,
  pillarStats,
  reasonFor,
  reportWhatsapp,
  reviewsRun,
  servicesFor,
  sourceStats,
  summaryFor,
  timingFor,
  trendFor,
  upcomingEvents,
  worldFor,
} from './world.js'

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms))
const jitter = (lo, hi) => lo + Math.random() * (hi - lo)
const clone = (value) => structuredClone(value)

function fail(status, message) {
  throw Object.assign(new Error(message), { status })
}

const OPEN = ['new', 'contacted', 'quoted']

// ------------------------------------------------------------- shaping
const LEAD_FIELDS = ['id', 'business_id', 'name', 'phone', 'source', 'first_message', 'car_model', 'service', 'status', 'job_value', 'created_at', 'first_response_at', 'analysis']

function leadOut(w, lead, { full = false } = {}) {
  const post = lead.source_post_id ? w.posts.find((p) => p.id === lead.source_post_id) : null
  return clone({
    ...Object.fromEntries(LEAD_FIELDS.map((key) => [key, lead[key]])),
    source_post: post
      ? { id: post.id, title: post.title, platform: post.platform, format: post.format, pillar: post.pillar, published_at: post.published_at }
      : null,
    ...(full ? { messages: lead.messages } : {}),
  })
}

function postOut(post) {
  return clone({ ...post, suggested_at: post.date ? iso(atIST(post.date, post.best_hour ?? 19)) : null })
}

const reviewOut = (r) => clone({ ...r, needs_attention: r.rating <= 3 && !r.reply_text })

function findOr404(list, id, what) {
  const item = list.find((x) => x.id === Number(id))
  if (!item) fail(404, `${what} ${id} not found`)
  return item
}

const daysOf = (params) => Math.min(730, Math.max(1, Number(params.days) || 30))
const sortTime = (p) => new Date(p.scheduled_at ?? p.published_at ?? atIST(p.date, p.best_hour ?? 19)).getTime()

// --------------------------------------------------------------- leads
function listLeads(w, params) {
  let list = w.leads
  if (params.source) list = list.filter((l) => l.source === params.source)
  if (params.status) list = list.filter((l) => l.status === params.status)
  if (params.priority) list = list.filter((l) => l.analysis?.priority === params.priority)
  if (params.sentiment) list = list.filter((l) => l.analysis?.sentiment === params.sentiment)
  if (params.min_score) list = list.filter((l) => (l.analysis?.score ?? 0) >= Number(params.min_score))
  if (params.search) {
    const q = params.search.toLowerCase()
    list = list.filter((l) => [l.name, l.phone, l.first_message, l.service, l.car_model].some((x) => x?.toLowerCase().includes(q)))
  }
  const newest = (a, b) => new Date(b.created_at) - new Date(a.created_at)
  const sorters = {
    newest,
    oldest: (a, b) => -newest(a, b),
    score: (a, b) => (b.analysis?.score ?? 0) - (a.analysis?.score ?? 0) || newest(a, b),
    value: (a, b) => (b.job_value ?? -1) - (a.job_value ?? -1) || newest(a, b),
  }
  list = [...list].sort(sorters[params.sort] ?? newest)
  const pageSize = Number(params.page_size ?? params.limit ?? 25)
  const page = Number(params.page ?? Math.floor(Number(params.offset ?? 0) / pageSize) + 1)
  return {
    items: list.slice((page - 1) * pageSize, page * pageSize).map((l) => leadOut(w, l)),
    total: list.length,
    page,
    page_size: pageSize,
  }
}

function updateLead(w, lead, body) {
  const status = body.status ?? lead.status
  if (body.job_value != null && status !== 'won') fail(422, 'A job value can only be added when the enquiry is marked Won.')
  if (status === 'won' && !(body.job_value ?? lead.job_value)) fail(422, "Add the job's value in ₹ to mark it Won.")
  for (const key of ['status', 'job_value', 'name', 'service', 'car_model']) if (key in body) lead[key] = body[key]
  if (lead.status !== 'won') lead.job_value = null
  if (!OPEN.includes(lead.status) && lead.analysis) lead.analysis.priority = 'normal'
  return leadOut(w, lead, { full: true })
}

// ------------------------------------------------------------- content
function writeCopy(w, post) {
  const template = w.profile.ideas.find((i) => i.title === post.title)
  const phone = w.business.phone.replace(/(\d{5})(\d{5})/, '$1 $2')
  Object.assign(post, {
    status: post.status === 'idea' || post.status === 'failed' ? 'draft' : post.status,
    caption: template?.caption ?? `${post.title} ✨\n\nWhatsApp us on ${phone} to book. ${w.business.area}, ${w.business.city}.`,
    hashtags: template?.hashtags ?? [`#${w.business.city}`, `#${w.business.area.replace(/\s/g, '')}`, `#${w.business.name.replace(/\s/g, '')}`],
    script: template?.script ?? (post.format === 'reel' ? `Hook (0–2s): ${post.title}.\nMiddle: 3 quick shots of real work.\nCTA: "WhatsApp us to book."` : ''),
    shot_list: template?.shots ?? ['Wide shot of the space', 'Close-up of the work', 'Team member smiling at the camera'],
    error: null,
  })
}

function weekPosts(w, start) {
  const end = addDays(start, 7)
  return w.posts.filter((p) => p.date >= start && p.date < end)
}

function planWeek(w, start) {
  const today = istDay(Date.now())
  const taken = weekPosts(w, start)
  const usedTitles = new Set(taken.map((p) => p.title))
  const fresh = w.profile.ideas.filter((i) => !usedTitles.has(i.title))
  const pool = fresh.length ? fresh : w.profile.ideas
  const created = []
  for (let d = 0; d < 7; d++) {
    const date = addDays(start, d)
    if (date < today || taken.some((p) => p.date === date && p.status !== 'failed')) continue
    const idea = pool[created.length % pool.length]
    const post = makePost(w, {
      platform: idea.platform, format: idea.format, pillar: idea.pillar, title: idea.title,
      date, best_hour: idea.hour, status: 'idea', created_by: 'ai',
      ai_reason: reasonFor(w, idea.pillar, idea.platform),
    })
    w.posts.push(post)
    created.push(post)
  }
  if (created.length) w.runs.unshift(contentRun(w, 'plan', new Date(), created))
  return created
}

// --------------------------------------------------------------- routes
const routes = [
  // Businesses and settings
  ['GET', '/businesses', () => clone(allBusinesses())],
  ['GET', '/businesses/:id', ({ id }) => clone(worldFor(id).business)],
  ['PATCH', '/businesses/:id', ({ id }, { body }) => {
    const business = worldFor(id).business
    if (body.google_review_link && !/^https?:\/\//.test(body.google_review_link))
      fail(422, 'The Google review link should start with https://')
    if ('name' in body && !body.name?.trim()) fail(422, 'The business needs a name.')
    const allowed = ['name', 'city', 'area', 'phone', 'services', 'brand_voice', 'target_audience', 'google_review_link', 'opening_hours']
    for (const key of allowed) if (key in body) business[key] = body[key]
    return clone(business)
  }],
  ['GET', '/social/accounts', (_, { w }) => clone(w.social)],
  ['POST', '/social/accounts', (_, { w, body }) => {
    if (!body.platform) fail(422, 'Choose a platform.')
    if (w.social.some((a) => a.platform === body.platform)) fail(422, 'That platform is already added. Edit it instead.')
    const account = { id: nextId(w, 'social'), business_id: w.business.id, platform: body.platform, handle: body.handle ?? '', followers: null, status: 'connected', connected_at: iso(Date.now()) }
    w.social.push(account)
    return clone(account)
  }],
  ['PATCH', '/social/accounts/:id', ({ id }, { w, body }) => {
    const account = findOr404(w.social, id, 'Account')
    if ('handle' in body) account.handle = body.handle
    if ('status' in body) {
      account.status = body.status
      account.connected_at = body.status === 'connected' ? iso(Date.now()) : account.connected_at
    }
    return clone(account)
  }],

  // AI
  ['GET', '/ai/status', () => ({ mode: 'mock', model: null })],
  ['GET', '/agent-runs', (_, { w, params }) => {
    let list = w.runs
    if (params.workflow) list = list.filter((r) => r.workflow === params.workflow)
    if (params.status) list = list.filter((r) => r.status === params.status)
    if (params.lead_id) list = list.filter((r) => r.lead_id === Number(params.lead_id))
    const pageSize = Number(params.page_size ?? 25)
    const page = Number(params.page ?? 1)
    return { items: clone(list.slice((page - 1) * pageSize, page * pageSize)), total: list.length, page, page_size: pageSize }
  }],
  ['GET', '/agent-runs/:id', ({ id }, { w }) => clone(findOr404(w.runs, id, 'Run'))],
  ['GET', '/ai/lead-workflow', () => ({
    workflow: 'lead',
    name: 'Every new enquiry',
    trigger: 'Runs the moment a message arrives on any channel',
    steps: [
      { agent: 'intake', label: 'Intake', does: 'Reads the message: what they want, how soon, and whether they shared a number.' },
      { agent: 'sentiment', label: 'Tone reader', does: 'Labels the tone as urgent, casual or frustrated, and says why.' },
      { agent: 'scoring', label: 'Scorer', does: 'Scores 1–100 from fixed points, plus the AI\'s reading of the wording.' },
      { agent: 'priority_router', label: 'Hot-lead router', does: 'Flags 🔥 hot enquiries so you call them first.' },
    ],
  })],
  ['GET', '/growth/workflow', () => ({
    workflow: 'growth',
    name: 'Weekly growth review',
    trigger: 'Every Monday at 9 am, or when you press "Run review now"',
    steps: [
      { agent: 'data_analyst', label: 'Analyst', does: 'Compares this week with last week: enquiries, sales, reply speed, channels.' },
      { agent: 'presence_auditor', label: 'Presence checker', does: 'Checks Google, Instagram, WhatsApp and reviews against a simple checklist.' },
      { agent: 'strategy', label: 'Strategist', does: 'Picks what will bring the most customers this week.' },
      { agent: 'report_writer', label: 'Report writer', does: 'Writes the review in plain words with your 3 actions.' },
    ],
  })],

  // Numbers
  ['GET', '/analytics/summary', (_, { w, params }) => summaryFor(w, daysOf(params))],
  ['GET', '/analytics/sources', (_, { w, params }) => {
    const p = period(daysOf(params))
    return sourceStats(leadsBetween(w, p.since, p.until))
  }],
  ['GET', '/analytics/funnel', (_, { w, params }) => {
    const p = period(daysOf(params))
    return funnelFor(leadsBetween(w, p.since, p.until))
  }],
  ['GET', '/analytics/timing', (_, { w, params }) => {
    const p = period(daysOf(params))
    return timingFor(leadsBetween(w, p.since, p.until))
  }],
  ['GET', '/analytics/services', (_, { w, params }) => {
    const p = period(daysOf(params))
    return servicesFor(leadsBetween(w, p.since, p.until))
  }],
  ['GET', '/analytics/trend', (_, { w, params }) => {
    const p = period(daysOf(params))
    return trendFor(leadsBetween(w, p.since, p.until), p)
  }],

  // Enquiries
  ['GET', '/leads', (_, { w, params }) => listLeads(w, params)],
  ['GET', '/leads/:id', ({ id }, { w }) => leadOut(w, findOr404(w.leads, id, 'Lead'), { full: true })],
  ['PATCH', '/leads/:id', ({ id }, { w, body }) => updateLead(w, findOr404(w.leads, id, 'Lead'), body)],
  ['POST', '/leads/:id/messages', ({ id }, { w, body }) => {
    const lead = findOr404(w.leads, id, 'Lead')
    if (!body.text?.trim()) fail(422, 'text: the message is empty')
    const message = { id: nextId(w, 'message'), direction: body.direction, text: body.text.trim(), sent_at: iso(Date.now()) }
    lead.messages.push(message)
    if (body.direction === 'out') {
      lead.first_response_at ??= message.sent_at
      if (lead.status === 'new') lead.status = 'contacted'
    } else {
      lead.analysis = { ...analyse(w, lead), analyzed_at: iso(Date.now()) }
    }
    return clone(message)
  }],
  ['POST', '/leads/:id/analyze', async ({ id }, { w }) => {
    const lead = findOr404(w.leads, id, 'Lead')
    await wait(jitter(700, 1200))
    lead.analysis = { ...analyse(w, lead), analyzed_at: iso(Date.now()) }
    w.runs.unshift(leadRun(w, lead, w.t, lead.analysis.analyzed_at))
    return leadOut(w, lead, { full: true })
  }],

  // Content calendar
  ['GET', '/content/calendar', (_, { w, params }) => {
    const start = params.start ?? istDay(Date.now())
    const count = Number(params.days ?? 7)
    return {
      start,
      days: Array.from({ length: count }, (_, i) => {
        const date = addDays(start, i)
        return { date, posts: w.posts.filter((p) => p.date === date).sort((a, b) => sortTime(a) - sortTime(b)).map(postOut) }
      }),
    }
  }],
  ['POST', '/content/plan-week', async (_, { w, body }) => {
    await wait(jitter(1400, 2000))
    const created = planWeek(w, body.start ?? istDay(Date.now()))
    return { created: created.length, posts: created.map(postOut) }
  }],
  ['POST', '/content/write-week', async (_, { w, body }) => {
    await wait(jitter(1800, 2600))
    const today = istDay(Date.now())
    const ideas = weekPosts(w, body.start ?? today).filter((p) => p.status === 'idea' && p.date >= today)
    ideas.forEach((p) => writeCopy(w, p))
    if (ideas.length) w.runs.unshift(contentRun(w, 'write', new Date(), ideas))
    return { written: ideas.length, posts: ideas.map(postOut) }
  }],
  ['POST', '/content/write/:id', async ({ id }, { w }) => {
    const post = findOr404(w.posts, id, 'Post')
    if (post.status === 'published') fail(422, 'This post is already live.')
    await wait(jitter(1100, 1600))
    writeCopy(w, post)
    w.runs.unshift(contentRun(w, 'write', new Date(), [post]))
    return postOut(post)
  }],
  ['GET', '/posts', (_, { w, params }) => {
    let list = w.posts
    if (params.status) list = list.filter((p) => p.status === params.status)
    if (params.platform) list = list.filter((p) => p.platform === params.platform)
    if (params.pillar) list = list.filter((p) => p.pillar === params.pillar)
    list = [...list].sort((a, b) => sortTime(b) - sortTime(a))
    return list.slice(0, Number(params.limit ?? 100)).map(postOut)
  }],
  ['PATCH', '/posts/:id', ({ id }, { w, body }) => {
    const post = findOr404(w.posts, id, 'Post')
    if (post.status === 'published') fail(422, 'This post is already live. Edit it on the platform itself.')
    const allowed = ['title', 'caption', 'hashtags', 'script', 'shot_list', 'platform', 'format', 'pillar', 'date', 'best_hour']
    for (const key of allowed) if (key in body) post[key] = body[key]
    if (post.status === 'idea' && post.caption?.trim()) post.status = 'draft'
    post.edited = true
    return postOut(post)
  }],
  ['POST', '/posts/:id/schedule', ({ id }, { w, body }) => {
    const post = findOr404(w.posts, id, 'Post')
    if (post.status === 'published') fail(422, 'This post is already live.')
    if (!post.caption?.trim()) fail(422, 'Write a caption first, or press "Write with AI".')
    const at = new Date(body.scheduled_at ?? '')
    if (Number.isNaN(at.getTime())) fail(422, 'Pick a date and time to schedule it.')
    if (at.getTime() < Date.now() + 60_000) fail(422, 'Pick a time in the future.')
    Object.assign(post, { status: 'scheduled', scheduled_at: iso(at), date: istDay(at), best_hour: Number(new Date(at.getTime() + 330 * 60_000).getUTCHours()), error: null })
    return postOut(post)
  }],
  ['POST', '/posts/:id/unschedule', ({ id }, { w }) => {
    const post = findOr404(w.posts, id, 'Post')
    if (post.status !== 'scheduled') fail(422, 'Only scheduled posts can be unscheduled.')
    Object.assign(post, { status: 'draft', scheduled_at: null })
    return postOut(post)
  }],
  ['POST', '/posts/:id/publish-now', async ({ id }, { w }) => {
    const post = findOr404(w.posts, id, 'Post')
    if (post.status === 'published') fail(422, 'This post is already live.')
    if (!post.caption?.trim()) fail(422, 'Write a caption first, or press "Write with AI".')
    const account = w.social.find((a) => a.platform === post.platform)
    if (account?.status === 'expired') fail(422, `The ${post.platform === 'instagram' ? 'Instagram' : post.platform} login has expired. Reconnect it in Settings first.`)
    await wait(jitter(900, 1400))
    const now = Date.now()
    Object.assign(post, {
      status: 'published', published_at: iso(now), scheduled_at: iso(now), date: istDay(now), error: null,
      metrics: { reach: 0, likes: 0, comments: 0, saves: 0, shares: 0, engagement_pct: 0 },
      results: { enquiries: 0, customers: 0, revenue: 0 },
    })
    return postOut(post)
  }],
  ['DELETE', '/posts/:id', ({ id }, { w }) => {
    const post = findOr404(w.posts, id, 'Post')
    if (post.status === 'published') fail(422, 'Published posts stay here for the record.')
    w.posts = w.posts.filter((p) => p !== post)
    return null
  }],

  // Content performance
  ['GET', '/content/top-posts', (_, { w, params }) => {
    const value = {
      revenue: (p) => p.results?.revenue ?? 0,
      enquiries: (p) => p.results?.enquiries ?? 0,
      reach: (p) => p.metrics?.reach ?? 0,
      engagement: (p) => p.metrics?.engagement_pct ?? 0,
    }[params.by] ?? ((p) => p.results?.revenue ?? 0)
    return w.posts
      .filter((p) => p.status === 'published')
      .sort((a, b) => value(b) - value(a) || (b.results?.enquiries ?? 0) - (a.results?.enquiries ?? 0))
      .slice(0, Number(params.limit ?? 8))
      .map(postOut)
  }],
  ['GET', '/content/stats', (_, { w, params }) => {
    const days = Number(params.days) || 90
    const since = Date.now() - days * 86_400_000
    const posts = w.posts.filter((p) => p.status === 'published' && new Date(p.published_at).getTime() >= since)
    const sum = (f) => posts.reduce((s, p) => s + f(p), 0)
    const platforms = Object.entries(Object.groupBy(posts, (p) => p.platform)).map(([platform, list]) => ({
      platform,
      posts: list.length,
      reach: list.reduce((s, p) => s + (p.metrics?.reach ?? 0), 0),
      enquiries: list.reduce((s, p) => s + (p.results?.enquiries ?? 0), 0),
      revenue: list.reduce((s, p) => s + (p.results?.revenue ?? 0), 0),
    }))
    return {
      period_days: days,
      totals: {
        posts: posts.length,
        reach: sum((p) => p.metrics?.reach ?? 0),
        likes: sum((p) => p.metrics?.likes ?? 0),
        enquiries: sum((p) => p.results?.enquiries ?? 0),
        customers: sum((p) => p.results?.customers ?? 0),
        revenue: sum((p) => p.results?.revenue ?? 0),
      },
      pillars: pillarStats(posts).sort((a, b) => b.revenue - a.revenue || b.enquiries - a.enquiries),
      platforms,
    }
  }],
  ['GET', '/content/events', (_, { w }) => upcomingEvents(w)],

  // Weekly review
  ['GET', '/growth/reports', (_, { w, params }) =>
    clone([...w.reports].reverse().slice(0, Number(params.limit ?? 10)))],
  ['GET', '/growth/reports/:id', ({ id }, { w }) => clone(findOr404(w.reports, id, 'Report'))],
  ['POST', '/growth/review', async (_, { w }) => {
    await wait(jitter(2200, 3000))
    const report = makeReport(w, new Date())
    w.reports.push(report)
    w.runs.unshift(growthRun(w, report))
    return clone(report)
  }],
  ['GET', '/growth/reports/:id/whatsapp', ({ id }, { w }) => ({ text: reportWhatsapp(w, findOr404(w.reports, id, 'Report')) })],

  // Reputation
  ['GET', '/reviews/summary', (_, { w }) => {
    const reviews = w.reviews
    const stars = { 5: 0, 4: 0, 3: 0, 2: 0, 1: 0 }
    reviews.forEach((r) => stars[r.rating]++)
    const tally = (pick) => {
      const counts = {}
      reviews.forEach((r) => pick(r).forEach((topic) => (counts[topic] = (counts[topic] ?? 0) + 1)))
      return Object.entries(counts).map(([topic, count]) => ({ topic, count })).sort((a, b) => b.count - a.count).slice(0, 6)
    }
    const recent = reviews.filter((r) => Date.now() - new Date(r.created_at).getTime() < 30 * 86_400_000)
    const avg = (list) => (list.length ? Math.round((list.reduce((s, r) => s + r.rating, 0) / list.length) * 10) / 10 : null)
    return {
      average_rating: avg(reviews),
      total: reviews.length,
      stars,
      praised_for: tally((r) => r.praised),
      complaints: tally((r) => r.complaints),
      needs_attention: reviews.filter((r) => r.rating <= 3 && !r.reply_text).length,
      unreplied: reviews.filter((r) => !r.reply_text).length,
      replied_pct: Math.round((reviews.filter((r) => r.reply_text).length / reviews.length) * 100),
      last_30_days: { count: recent.length, average_rating: avg(recent) },
    }
  }],
  ['GET', '/reviews', (_, { w, params }) => {
    let list = w.reviews.map(reviewOut)
    if (params.rating) list = list.filter((r) => r.rating === Number(params.rating))
    if (params.status === 'unreplied') list = list.filter((r) => !r.reply_text)
    if (params.status === 'replied') list = list.filter((r) => r.reply_text)
    if (params.status === 'needs_attention') list = list.filter((r) => r.needs_attention)
    return list.sort((a, b) => b.needs_attention - a.needs_attention || new Date(b.created_at) - new Date(a.created_at))
  }],
  ['POST', '/reviews/draft-all', async (_, { w }) => {
    await wait(jitter(1500, 2200))
    const todo = w.reviews.filter((r) => !r.reply_text && !r.draft_reply)
    todo.forEach((r) => (r.draft_reply = draftReplyFor(w, r)))
    if (todo.length) w.runs.unshift(reviewsRun(w, new Date(), todo))
    return { drafted: todo.length }
  }],
  ['POST', '/reviews/:id/reply', ({ id }, { w, body }) => {
    const review = findOr404(w.reviews, id, 'Review')
    if (!body.text?.trim()) fail(422, 'The reply is empty.')
    Object.assign(review, { reply_text: body.text.trim(), replied_at: iso(Date.now()), draft_reply: null })
    return reviewOut(review)
  }],
  ['GET', '/review-requests', (_, { w, params }) => {
    let list = w.requests
    if (params.status) list = list.filter((r) => r.status === params.status)
    // Waiting to go out first (soonest first), then the rest (newest first).
    const when = (r) => new Date(r.reviewed_at ?? r.sent_at ?? r.send_at).getTime()
    const pending = list.filter((r) => r.status === 'pending').sort((a, b) => when(a) - when(b))
    const rest = list.filter((r) => r.status !== 'pending').sort((a, b) => when(b) - when(a))
    return clone([...pending, ...rest])
  }],
  ['POST', '/review-requests/:id/skip', ({ id }, { w }) => {
    const request = findOr404(w.requests, id, 'Review request')
    if (request.status !== 'pending') fail(422, "Only requests that haven't gone out yet can be skipped.")
    request.status = 'skipped'
    return clone(request)
  }],
]

// ------------------------------------------------------------- matching
function match(pattern, path) {
  const a = pattern.split('/')
  const b = path.split('/')
  if (a.length !== b.length) return null
  const found = {}
  for (let i = 0; i < a.length; i++) {
    if (a[i].startsWith(':')) found[a[i].slice(1)] = decodeURIComponent(b[i])
    else if (a[i] !== b[i]) return null
  }
  return found
}

export async function handle(method, path, { params = {}, body = {} } = {}) {
  for (const [m, pattern, handler] of routes) {
    if (m !== method) continue
    const found = match(pattern, path)
    if (!found) continue
    await wait(method === 'GET' ? jitter(120, 320) : jitter(250, 450))
    const w = worldFor(params.business_id ?? found.id ?? 1)
    return handler(found, { w, params, body: body ?? {} })
  }
  fail(404, "This part isn't available in the sample data.")
}
