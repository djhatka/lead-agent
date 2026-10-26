/*
  Builds the sample "world" for each demo business: three months of
  enquiries with chats and AI scores, social posts with their results,
  Google reviews, review requests, weekly reviews and the AI team's diary.

  It is generated from a fixed seed, so it looks the same on every reload,
  and dated relative to today, so it always looks fresh. Changes made in
  the dashboard live in memory until the page is reloaded.

  The numbers follow the stories the dashboard is built to show:
  Instagram brings many enquiries but few customers, Google brings the
  money, fast replies win, offer and testimonial posts bring customers
  while trend reels bring likes.
*/
import { EVENT_IDEAS, EVENTS, FIRST_NAMES, LAST_NAMES, PAST_TITLES, PROFILES } from './profiles.js'

const MINUTE = 60_000
const HOUR = 60 * MINUTE
const DAY = 24 * HOUR
const IST = 330 * MINUTE

// ------------------------------------------------------------------ random
function seeded(seed) {
  // mulberry32: tiny, fast, good enough for sample data
  let a = seed >>> 0
  return () => {
    a = (a + 0x6d2b79f5) | 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

function tools(seed) {
  const r = seeded(seed)
  const t = {
    r,
    between: (a, b) => a + r() * (b - a),
    int: (a, b) => Math.floor(a + r() * (b - a + 1)),
    pick: (list) => list[Math.floor(r() * list.length)],
    chance: (p) => r() < p,
    weighted(entries) {
      const total = entries.reduce((sum, [, w]) => sum + w, 0)
      let x = r() * total
      for (const [value, w] of entries) if ((x -= w) < 0) return value
      return entries.at(-1)[0]
    },
    shuffle(list) {
      const copy = [...list]
      for (let i = copy.length - 1; i > 0; i--) {
        const j = Math.floor(r() * (i + 1))
        ;[copy[i], copy[j]] = [copy[j], copy[i]]
      }
      return copy
    },
  }
  return t
}

// ------------------------------------------------------------ India time
export const istDay = (date) => new Date(new Date(date).getTime() + IST).toISOString().slice(0, 10)
export const istHour = (date) => new Date(new Date(date).getTime() + IST).getUTCHours()
export const istWeekday = (date) => (new Date(new Date(date).getTime() + IST).getUTCDay() + 6) % 7 // Mon = 0

/** The moment `day` ('YYYY-MM-DD', India) at hour:minute India time. */
export function atIST(day, hour = 0, minute = 0) {
  return new Date(Date.parse(`${day}T00:00:00Z`) + (hour * 60 + minute) * MINUTE - IST)
}

export function addDays(day, n) {
  const d = new Date(`${day}T00:00:00Z`)
  d.setUTCDate(d.getUTCDate() + n)
  return d.toISOString().slice(0, 10)
}

export function mondayOf(day) {
  return addDays(day, -((new Date(`${day}T00:00:00Z`).getUTCDay() + 6) % 7))
}

export const iso = (date) => new Date(date).toISOString()
const ms = (value) => new Date(value).getTime()
const round1 = (n) => Math.round(n * 10) / 10
const pct = (part, whole) => (whole ? round1((part / whole) * 100) : 0)
const fill = (text, vars) => text.replace(/\{(\w+)\}/g, (_, key) => vars[key] ?? '')
export const rupees = (n) => `₹${Math.round(n).toLocaleString('en-IN')}`

export const CHANNEL_NAMES = {
  whatsapp: 'WhatsApp', instagram: 'Instagram', website: 'Website', google: 'Google',
  indiamart: 'IndiaMART', justdial: 'Justdial', walkin: 'Walk-in', facebook: 'Facebook',
}
const channelName = (key) => CHANNEL_NAMES[key] ?? key

export const PILLAR_NAMES = {
  offer: 'Offer', testimonial: 'Customer story', educational: 'Tips', trend: 'Trend',
  behind_the_scenes: 'Behind the scenes', festival: 'Festival',
}

const SCORE_LABELS = {
  base: 'new enquiry', wants_soon: 'wants it soon', phone_shared: 'phone number shared',
  service_named: 'knows the service', car_named: 'car model given', two_messages: 'replied again',
  three_plus_messages: 'long conversation', urgent_tone: 'urgent tone', frustrated_tone: 'frustrated tone',
  price_only: 'only asked the price', ai_adjustment: 'wording',
}

const SOURCE_POINTS = { google: 16, walkin: 18, website: 14, whatsapp: 12, indiamart: 12, justdial: 10, instagram: 8 }
// Which kind of post an enquiry came from, and how likely that enquiry is to buy:
// offers and customer stories bring buyers; trend reels bring likes and browsers.
const PILLAR_PULL = { offer: 2.2, testimonial: 1.6, festival: 1.4, educational: 1.2, behind_the_scenes: 0.8, trend: 1.6 }
const PILLAR_BUYS = { offer: 2.4, testimonial: 2.1, festival: 1.2, educational: 0.9, behind_the_scenes: 0.8, trend: 0.3 }
const OPEN = ['new', 'contacted', 'quoted', 'booked']

// --------------------------------------------------------------- building
let worlds = null

export function worldFor(businessId) {
  worlds ??= Object.fromEntries(PROFILES.map((p) => [p.business.id, build(p)]))
  const w = worlds[Number(businessId) || 1]
  if (!w) throw Object.assign(new Error(`Business ${businessId} not found`), { status: 404 })
  return w
}

export const allBusinesses = () => PROFILES.map((p) => worldFor(p.business.id).business)

export function nextId(w, kind) {
  w.ids[kind] += 1
  return w.ids[kind]
}

function build(profile) {
  const b = profile.business.id
  const t = tools(b * 7919)
  const now = Date.now()
  const today = istDay(now)
  const w = {
    profile,
    t,
    business: {
      ...profile.business,
      services: profile.services.filter((s) => s.price[1] > 0).map((s) => s.name),
      created_at: iso(now - 400 * DAY),
    },
    leads: [],
    posts: [],
    reviews: [],
    requests: [],
    reports: [],
    runs: [],
    social: [],
    ids: { lead: b * 1000, message: b * 100000, post: b * 1000, review: b * 1000, request: b * 1000, report: b * 100, run: b * 10000, social: b * 10 },
  }

  buildPastPosts(w, t, today)
  buildThisWeek(w, t, today, now)
  buildLeads(w, t, now)
  countPostResults(w)
  buildReviews(w, t, now)
  buildRequests(w, t, now)
  w.social = profile.social.map((s) => ({
    id: nextId(w, 'social'),
    business_id: b,
    ...s,
    connected_at: s.status === 'disconnected' ? null : iso(now - t.int(60, 300) * DAY),
  }))

  // Weekly reviews: every Monday 9 am for the last 3 weeks
  let monday = mondayOf(today)
  if (ms(atIST(monday, 9)) > now) monday = addDays(monday, -7)
  for (const weeksAgo of [2, 1, 0]) {
    const at = atIST(addDays(monday, -7 * weeksAgo), 9, 0)
    const report = makeReport(w, at)
    w.reports.push(report)
    w.runs.push(growthRun(w, report))
  }
  buildLeadRuns(w, t, now)
  w.runs.push(contentRun(w, 'plan', atIST(monday, 9, 2), w.posts.filter((p) => p.date >= monday).slice(0, 5)))
  w.runs.sort((a, b2) => ms(b2.started_at) - ms(a.started_at))
  return w
}

// ------------------------------------------------------------------ posts
function metricsFor(t, post) {
  const ranges = { reel: [1800, 9000], carousel: [700, 2600], post: [400, 1800], story: [250, 900] }
  let reach = t.int(...(ranges[post.format] ?? ranges.post))
  if (post.pillar === 'trend') reach = Math.round(reach * 1.7)
  if (post.platform === 'google') reach = t.int(150, 700)
  const likes = Math.round(reach * t.between(0.035, 0.085) * (post.pillar === 'trend' ? 1.3 : 1))
  const comments = Math.round(likes * t.between(0.03, 0.12))
  const saves = Math.round(likes * (post.pillar === 'educational' ? t.between(0.25, 0.45) : t.between(0.03, 0.12)))
  const shares = Math.round(likes * t.between(0.02, 0.1))
  return { reach, likes, comments, saves, shares, engagement_pct: pct(likes + comments + saves + shares, reach) }
}

export function makePost(w, fields) {
  return {
    id: nextId(w, 'post'),
    business_id: w.business.id,
    platform: 'instagram',
    format: 'post',
    pillar: 'offer',
    status: 'idea',
    title: '',
    ai_reason: null,
    caption: '',
    hashtags: [],
    script: '',
    shot_list: [],
    date: null,
    best_hour: 19,
    scheduled_at: null,
    published_at: null,
    error: null,
    created_by: 'ai',
    created_at: iso(Date.now()),
    metrics: null,
    results: null,
    ...fields,
  }
}

const FORMAT_FOR = { offer: 'reel', testimonial: 'reel', educational: 'carousel', trend: 'reel', behind_the_scenes: 'story', festival: 'post' }

function buildPastPosts(w, t, today) {
  const titles = PAST_TITLES[w.business.category]
  const used = Object.fromEntries(Object.keys(titles).map((k) => [k, 0]))
  for (let week = 9; week >= 1; week--) {
    const start = addDays(today, -6 - 7 * week) // up to a week ago; the last few days come from buildThisWeek
    const pillars = t.shuffle(['offer', 'testimonial', 'educational', 'trend', 'behind_the_scenes', 'offer', 'festival']).slice(0, t.int(3, 5))
    const days = t.shuffle([0, 1, 2, 3, 4, 5, 6])
    pillars.forEach((pillar, i) => {
      const list = titles[pillar]
      const title = list[used[pillar]++ % list.length]
      const google = pillar === 'offer' && t.chance(0.3)
      const day = addDays(start, days[i])
      const hour = pillar === 'behind_the_scenes' ? 8 : pillar === 'educational' ? 13 : 19
      const at = atIST(day, hour, t.int(0, 3) * 15)
      const post = makePost(w, {
        platform: google ? 'google' : 'instagram',
        format: google ? 'post' : FORMAT_FOR[pillar],
        pillar,
        status: 'published',
        title,
        caption: `${title}. Book now: WhatsApp ${w.business.phone.replace(/(\d{5})(\d{5})/, '$1 $2')}.`,
        date: day,
        best_hour: hour,
        scheduled_at: iso(at),
        published_at: iso(at),
        created_at: iso(ms(at) - 3 * DAY),
      })
      post.metrics = metricsFor(t, post)
      w.posts.push(post)
    })
  }
}

/** Around today: recent days are published, today is scheduled, then a draft, an idea and empty days to plan. */
function buildThisWeek(w, t, today, now) {
  const ideas = w.profile.ideas
  const instagramExpired = w.profile.social.some((s) => s.platform === 'instagram' && s.status === 'expired')
  let next = 0
  for (let ahead = -5; ahead <= 6; ahead++) {
    const day = addDays(today, ahead)
    const idea = ideas[next % ideas.length]
    const copy = {
      platform: idea.platform, format: idea.format, pillar: idea.pillar, title: idea.title, date: day,
      best_hour: idea.hour, ai_reason: reasonFor(w, idea.pillar, idea.platform),
    }
    const written = { caption: idea.caption, hashtags: idea.hashtags, script: idea.script, shot_list: idea.shots }
    if (ahead < 0) {
      if (ahead % 2 === 0) continue // not every past day had a post
      const at = atIST(day, idea.hour, 0)
      const post = makePost(w, {
        ...copy, ...written,
        status: 'published',
        scheduled_at: iso(at),
        published_at: iso(at),
        created_at: iso(ms(at) - 2 * DAY),
      })
      post.metrics = metricsFor(t, post)
      w.posts.push(post)
    } else if (ahead === 0) {
      const at = atIST(day, idea.hour, 0)
      const done = ms(at) <= now
      const post = makePost(w, {
        ...copy, ...written,
        status: done ? 'published' : 'scheduled',
        scheduled_at: iso(at),
        published_at: done ? iso(at) : null,
        created_at: iso(now - DAY),
      })
      if (done) post.metrics = metricsFor(t, post)
      w.posts.push(post)
    } else if (ahead === 1) {
      w.posts.push(makePost(w, { ...copy, ...written, status: 'draft', created_at: iso(now - DAY) }))
    } else if (ahead === 2) {
      w.posts.push(makePost(w, { ...copy, status: 'idea', created_at: iso(now - DAY) }))
    } else {
      continue
    }
    next++
  }

  // A business whose Instagram login expired has a post that couldn't go out.
  if (instagramExpired) {
    const missed = w.posts.findLast((p) => p.date >= addDays(today, -3) && p.status === 'published' && p.platform === 'instagram')
    if (missed) Object.assign(missed, {
      status: 'failed',
      published_at: null,
      metrics: null,
      error: 'Instagram says the login has expired. Reconnect Instagram in Settings, then try again.',
    })
  }
}

function countPostResults(w) {
  for (const post of w.posts) {
    if (post.status !== 'published') continue
    const leads = w.leads.filter((l) => l.source_post_id === post.id)
    const won = leads.filter((l) => l.status === 'won')
    post.results = { enquiries: leads.length, customers: won.length, revenue: won.reduce((s, l) => s + (l.job_value ?? 0), 0) }
  }
}

/** Why the AI suggests this kind of post, from how such posts did in the last 30 days. */
export function reasonFor(w, pillar, platform) {
  const since = Date.now() - 30 * DAY
  const stats = pillarStats(w.posts.filter((p) => p.status === 'published' && ms(p.published_at) >= since))
  const mine = stats.find((s) => s.pillar === pillar)
  const best = [...stats].sort((a, b) => b.revenue - a.revenue)[0]
  const name = PILLAR_NAMES[pillar]
  if (pillar === 'festival') {
    const event = upcomingEvents(w)[0]
    if (!event) return "A festive post keeps you in people's minds before the season."
    return mine?.enquiries
      ? `${event.name} is ${event.days_away} days away. Festival posts brought ${plural(mine.enquiries, 'enquiry', 'enquiries')} last month.`
      : `${event.name} is ${event.days_away} days away. People search and share more around festivals.`
  }
  if (platform === 'google') return 'You have not posted on Google this week. Weekly Google posts help you show up in "near me" searches.'
  if (!mine?.posts) return `You haven't tried a ${name.toLowerCase()} post recently. Worth testing once this week.`
  if (best && best.pillar === pillar && mine.revenue > 0)
    return `${name} posts brought ${plural(mine.enquiries, 'enquiry', 'enquiries')} and ${rupees(mine.revenue)} in the last 30 days, the most of any type.`
  if (pillar === 'trend')
    return `Trend reels get the most reach (${Math.round(mine.reach / mine.posts).toLocaleString('en-IN')} a post) and keep new people finding you, though they bring fewer customers.`
  if (pillar === 'educational') return 'Tips posts get saved and shared the most, so more people see your name.'
  return mine.enquiries
    ? `${name} posts brought ${plural(mine.enquiries, 'enquiry', 'enquiries')} and ${plural(mine.customers, 'customer', 'customers')} in the last 30 days.`
    : `${name} posts build trust before people enquire. Worth one this week.`
}

const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`

// ------------------------------------------------------------------ leads
function scoreReason(score, breakdown) {
  const parts = Object.entries(breakdown).map(([key, pts]) => {
    const label = key.startsWith('source_') ? `came via ${channelName(key.slice(7))}` : (SCORE_LABELS[key] ?? key)
    return `${label} ${pts > 0 ? '+' : ''}${pts}`
  })
  return `Score ${score}: ${parts.join(', ')}.`
}

export function analyse(w, lead, t = w.t) {
  const inCount = lead.messages.filter((m) => m.direction === 'in').length
  const text = lead.messages.map((m) => m.text).join(' ').toLowerCase()
  const soon = /\b(today|aaj|abhi|kal|tomorrow|this week|asap|jaldi)\b/.exec(text)
  const breakdown = { base: 20, [`source_${lead.source}`]: SOURCE_POINTS[lead.source] ?? 10 }
  if (soon || lead.sentiment === 'urgent') breakdown.wants_soon = 15
  if (lead.phone) breakdown.phone_shared = 10
  if (lead.service) breakdown.service_named = 6
  if (lead.car_model) breakdown.car_named = 6
  if (inCount === 2) breakdown.two_messages = 5
  if (inCount >= 3) breakdown.three_plus_messages = 8
  if (lead.sentiment === 'urgent') breakdown.urgent_tone = 6
  if (lead.sentiment === 'frustrated') breakdown.frustrated_tone = -4
  if (/\b(price|rate|charges?|kitna|cost|fees)\b/.test(text) && inCount === 1 && !soon) breakdown.price_only = -8
  breakdown.ai_adjustment = t.int(-6, 10)
  const score = Math.max(3, Math.min(100, Object.values(breakdown).reduce((s, n) => s + n, 0)))
  const fresh = Date.now() - ms(lead.created_at) < 14 * DAY // an old open enquiry has gone cold
  const hot = score >= 70 && fresh && ['new', 'contacted', 'quoted'].includes(lead.status)
  const reasons = {
    urgent: `Wants it soon: "${soon?.[0] ?? 'today'}".`,
    casual: 'Asking about price and timing, no rush.',
    frustrated: 'Annoyed about a slow or missing reply, but still wants to come.',
  }
  return {
    sentiment: lead.sentiment,
    sentiment_reason: reasons[lead.sentiment],
    score,
    score_reason: scoreReason(score, breakdown),
    score_breakdown: breakdown,
    priority: hot ? 'hot' : 'normal',
    analyzed_at: iso(ms(lead.created_at) + 40_000),
  }
}

function buildLeads(w, t, now) {
  const p = w.profile
  const sources = Object.entries(p.sources)
  const services = p.services.map((s) => [s, s.weight])
  const hours = p.hours.map((weight, h) => [h, weight]).filter(([, weight]) => weight > 0)
  const today = istDay(now)
  const made = []

  for (let i = 0; i < 190; i++) {
    const daysAgo = Math.floor(Math.pow(t.r(), 1.12) * 92)
    const created = atIST(addDays(today, -daysAgo), t.weighted(hours), t.int(0, 59))
    if (ms(created) > now - 10 * MINUTE) continue
    const source = t.weighted(sources)
    const service = t.weighted(services)
    const sentiment = t.weighted([['casual', 62], ['urgent', 24], ['frustrated', 14]])
    const first = t.pick(FIRST_NAMES)
    const named = source !== 'instagram' || t.chance(0.45)
    const car = p.cars ? t.pick(p.cars) : null
    const pool = sentiment === 'urgent' && t.chance(0.5) ? p.urgent : sentiment === 'frustrated' && t.chance(0.6) ? p.frustrated : p.messages[service.key]
    made.push({
      created, source, service, sentiment, first,
      name: named ? `${first} ${t.pick(LAST_NAMES)}` : null,
      phone: source === 'whatsapp' || t.chance(source === 'instagram' ? 0.35 : 0.8) ? `9${String(t.int(100000000, 999999999))}` : null,
      car,
      text: fill(t.pick(pool), { car: car ?? '' }),
    })
  }
  made.sort((a, b) => ms(a.created) - ms(b.created))

  const speedPull = (min) => (min == null ? 0.08 : min < 5 ? 1.9 : min < 30 ? 1.2 : min < 120 ? 0.7 : min < 1440 ? 0.4 : 0.3)
  const tonePull = { urgent: 1.3, casual: 1, frustrated: 0.75 }

  for (const m of made) {
    const ageMin = (now - ms(m.created)) / MINUTE
    let reply = t.weighted([[t.between(1, 5), 28], [t.between(5, 30), 30], [t.between(30, 120), 20], [t.between(120, 1440), 13], [null, 9]])
    if (reply != null && reply > ageMin) reply = null

    // Which post brought them (Instagram and Google posts published in the 2 weeks before)
    let post = null
    if ((m.source === 'instagram' && t.chance(0.8)) || (m.source === 'google' && t.chance(0.25))) {
      const platform = m.source === 'google' ? 'google' : 'instagram'
      const recent = w.posts.filter((x) => x.status === 'published' && x.platform === platform
        && ms(x.published_at) < ms(m.created) && ms(m.created) - ms(x.published_at) < 14 * DAY)
      if (recent.length) post = t.weighted(recent.map((x) => [x, PILLAR_PULL[x.pillar]]))
    }

    const buys = (p.win[m.source] ?? 0.2) * speedPull(reply) * tonePull[m.sentiment] * (post ? PILLAR_BUYS[post.pillar] : 1)
    const wins = t.chance(Math.min(0.92, buys))
    const ageDays = ageMin / 1440
    let status
    if (reply == null) status = ageDays > 7 ? 'lost' : 'new'
    else if (ageDays > 12) status = wins ? 'won' : t.weighted([['lost', 80], ['quoted', 12], ['contacted', 8]])
    else if (ageDays > 3) status = wins ? t.weighted([['won', 65], ['booked', 35]]) : t.weighted([['lost', 40], ['quoted', 30], ['contacted', 30]])
    else status = wins ? t.weighted([['booked', 40], ['quoted', 35], ['won', 25]]) : t.weighted([['contacted', 70], ['quoted', 30]])

    let value = null
    if (status === 'won') {
      const [lo, hi] = m.service.price[1] > 0 ? m.service.price : [2500, 2500] // a free trial that joined pays the monthly fee
      value = Math.round((t.between(lo, hi) * (m.source === 'google' ? 1.15 : 1)) / 100) * 100
    }

    const lead = {
      id: nextId(w, 'lead'),
      business_id: w.business.id,
      name: m.name,
      phone: m.phone,
      source: m.source,
      first_message: m.text,
      car_model: m.car,
      service: m.service.name,
      status,
      job_value: value,
      created_at: iso(m.created),
      first_response_at: reply == null ? null : iso(ms(m.created) + reply * MINUTE),
      sentiment: m.sentiment,
      source_post_id: post?.id ?? null,
      messages: [{ id: nextId(w, 'message'), direction: 'in', text: m.text, sent_at: iso(m.created) }],
    }
    if (reply != null) {
      const price = m.service.price[0] ? m.service.price[0].toLocaleString('en-IN') : '0 (free)'
      lead.messages.push({
        id: nextId(w, 'message'), direction: 'out',
        text: fill(t.pick(p.replies), { name: m.first, service: m.service.name, price }),
        sent_at: lead.first_response_at,
      })
      const followAt = ms(lead.first_response_at) + t.between(5, 240) * MINUTE
      if (followAt < now && (status !== 'contacted' || t.chance(0.4)) && t.chance(0.6)) {
        const text = status === 'won' || status === 'booked' ? p.followups.at(-1) : t.pick(p.followups.slice(0, -1))
        lead.messages.push({ id: nextId(w, 'message'), direction: 'in', text, sent_at: iso(followAt) })
      }
    }

    lead.analysis = analyse(w, lead, t)
    w.leads.push(lead)
  }
}

// ---------------------------------------------------------------- reviews
const GENERIC_REVIEWS = {
  good: [
    ['Excellent service, highly recommended!', ['Service']],
    ['Very professional team. Will come again.', ['Professional team']],
    ['Value for money. Friendly staff.', ['Fair price', 'Friendly staff']],
    ['', []],
  ],
  ok: [['Decent experience, room to improve.', ['Service'], ['Consistency']], ['', [], []]],
  bad: [['Not happy with the experience.', ['Service']], ['', []]],
}

export function draftReplyFor(w, review) {
  const first = review.author.split(' ')[0]
  const shortName = w.business.name.split(' ').slice(0, 2).join(' ')
  const lower = (topic) => (topic && !/^[A-Z]{2,}$/.test(topic) ? topic.toLowerCase() : topic) // "AC" stays "AC"
  const praised = lower(review.praised[0])
  const complaint = lower(review.complaints[0])
  if (review.rating >= 4)
    return praised
      ? `Thank you so much, ${first}! 🙏 We're really happy you liked the ${praised}. See you again soon at ${shortName}!`
      : `Thank you for the lovely rating, ${first}! 🙏 See you again soon at ${shortName}.`
  if (review.rating === 3)
    return `Thanks for the honest feedback, ${first}. Glad you liked the ${praised ?? 'service'}. We're working on ${complaint ?? 'what you mentioned'} and hope your next visit is better.`
  return `${first}, we're really sorry about ${complaint ? `the ${complaint}` : 'your experience'}. That's not how we want anyone to feel. Please WhatsApp us on ${w.business.phone.replace(/(\d{5})(\d{5})/, '$1 $2')} so we can make it right.`
}

function buildReviews(w, t, now) {
  const templates = w.profile.reviews
  const used = new Set()
  const take = (band) => {
    const options = [...templates[band], ...GENERIC_REVIEWS[band]].filter((x) => !x[0] || !used.has(x[0]))
    const choice = t.pick(options) ?? ['', [], []]
    if (choice[0]) used.add(choice[0])
    return choice
  }
  for (let i = 0; i < 38; i++) {
    const daysAgo = Math.floor(Math.pow(t.r(), 1.3) * 170)
    const created = ms(atIST(istDay(now - daysAgo * DAY), t.int(9, 22), t.int(0, 59)))
    if (created > now) continue
    const rating = t.weighted([[5, 52], [4, 22], [3, 9], [2, 7], [1, 10]])
    const band = rating >= 4 ? 'good' : rating === 3 ? 'ok' : 'bad'
    const [text, first, second] = take(band)
    const review = {
      id: 0,
      business_id: w.business.id,
      platform: t.weighted([['google', 82], ['justdial', 10], ['facebook', 8]]),
      author: `${t.pick(FIRST_NAMES)} ${t.pick(LAST_NAMES).charAt(0)}.`,
      rating,
      text,
      praised: band === 'bad' ? [] : first,
      complaints: band === 'bad' ? first : band === 'ok' ? second : [],
      created_at: iso(created),
      reply_text: null,
      replied_at: null,
      draft_reply: null,
    }
    const replyChance = band === 'bad' ? (daysAgo > 30 ? 0.7 : 0.1) : daysAgo > 7 ? 0.65 : 0.25
    if (t.chance(replyChance)) {
      review.reply_text = draftReplyFor(w, review)
      review.replied_at = iso(Math.min(now - HOUR, created + t.between(2, 72) * HOUR))
    }
    w.reviews.push(review)
  }
  w.reviews.sort((a, b) => ms(a.created_at) - ms(b.created_at))
  for (const review of w.reviews) review.id = nextId(w, 'review')

  // Always a few fresh unhappy reviews waiting for a reply, one already drafted by the AI.
  const unhappy = w.reviews.filter((r) => r.rating <= 2 && r.text).reverse().slice(0, 3)
  unhappy.forEach((r, i) => {
    r.created_at = iso(now - (i * 4 + 1) * DAY - t.int(1, 10) * HOUR)
    r.reply_text = null
    r.replied_at = null
    if (i === 0) r.draft_reply = draftReplyFor(w, r)
  })
  w.reviews
    .filter((r) => !r.reply_text && r.rating >= 4 && t.chance(0.35))
    .forEach((r) => (r.draft_reply = draftReplyFor(w, r)))
}

function buildRequests(w, t, now) {
  const won = w.leads.filter((l) => l.status === 'won' && l.phone && now - ms(l.created_at) < 24 * DAY).slice(-14)
  won.forEach((lead, i) => {
    const doneAt = ms(lead.messages.at(-1).sent_at)
    const first = (lead.name ?? 'there').split(' ')[0]
    // The two most recent customers haven't been asked yet.
    const status = i >= won.length - 2 ? 'pending' : t.weighted([['sent', 55], ['reviewed', 30], ['skipped', 15]])
    const sendAt = atIST(istDay(doneAt + DAY), 11, 0)
    w.requests.push({
      id: nextId(w, 'request'),
      business_id: w.business.id,
      lead_id: lead.id,
      customer_name: lead.name ?? `Customer #${lead.id}`,
      phone: lead.phone,
      service: lead.service,
      channel: 'whatsapp',
      status,
      send_at: iso(ms(sendAt) < now && status === 'pending' ? now + 3 * HOUR : sendAt),
      sent_at: status === 'sent' || status === 'reviewed' ? iso(sendAt) : null,
      reviewed_at: status === 'reviewed' ? iso(ms(sendAt) + t.between(2, 40) * HOUR) : null,
      rating: status === 'reviewed' ? t.weighted([[5, 80], [4, 20]]) : null,
      message: `Hi ${first}, thank you for choosing ${w.business.name}! If you were happy, could you leave us a quick Google review? It really helps 🙏 ${w.business.google_review_link}`,
      created_at: iso(doneAt),
    })
  })
}

// -------------------------------------------------------------- analytics
export function leadsBetween(w, since, until) {
  return w.leads.filter((l) => ms(l.created_at) >= since && ms(l.created_at) < until)
}

const replyMinutes = (l) => (l.first_response_at ? (ms(l.first_response_at) - ms(l.created_at)) / MINUTE : null)

function median(values) {
  if (!values.length) return null
  const sorted = [...values].sort((a, b) => a - b)
  const mid = Math.floor(sorted.length / 2)
  return round1(sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2)
}

export function period(days, until = Date.now()) {
  return { since: until - days * DAY, until, days }
}

export function sourceStats(leads) {
  const totalRevenue = leads.reduce((s, l) => s + (l.status === 'won' ? l.job_value : 0), 0)
  const groups = Object.groupBy(leads, (l) => l.source)
  return Object.entries(groups)
    .map(([source, list]) => {
      const won = list.filter((l) => l.status === 'won')
      const revenue = won.reduce((s, l) => s + l.job_value, 0)
      return {
        source,
        leads: list.length,
        won: won.length,
        lost: list.filter((l) => l.status === 'lost').length,
        open: list.filter((l) => OPEN.includes(l.status)).length,
        conversion_pct: pct(won.length, list.length),
        revenue,
        avg_job_value: won.length ? Math.round(revenue / won.length) : null,
        revenue_per_lead: Math.round(revenue / list.length),
        lead_share_pct: pct(list.length, leads.length),
        revenue_share_pct: pct(revenue, totalRevenue),
        median_reply_minutes: median(list.map(replyMinutes).filter((m) => m != null)),
        unanswered: list.filter((l) => !l.first_response_at).length,
      }
    })
    .sort((a, b) => b.leads - a.leads)
}

const REPLY_BUCKETS = [['under 5 min', 5], ['5-30 min', 30], ['30 min-2 hrs', 120], ['2-24 hrs', 1440], ['over a day', Infinity]]

export function replySpeed(leads) {
  const rows = REPLY_BUCKETS.map(([bucket]) => ({ bucket, list: [] }))
  const none = { bucket: 'no reply', list: [] }
  for (const l of leads) {
    const m = replyMinutes(l)
    if (m == null) none.list.push(l)
    else rows[REPLY_BUCKETS.findIndex(([, limit]) => m < limit)].list.push(l)
  }
  return [...rows, none].map(({ bucket, list }) => {
    const won = list.filter((l) => l.status === 'won').length
    return { bucket, leads: list.length, won, win_rate_pct: pct(won, list.length) }
  })
}

function headline(w, leads, previous) {
  const won = leads.filter((l) => l.status === 'won')
  const revenue = won.reduce((s, l) => s + l.job_value, 0)
  const prevWon = previous.filter((l) => l.status === 'won')
  const prevRevenue = prevWon.reduce((s, l) => s + l.job_value, 0)
  const change = (now, before) => (before ? round1(((now - before) / before) * 100) : null)
  const replies = leads.map(replyMinutes).filter((m) => m != null)
  return {
    leads: leads.length,
    won: won.length,
    conversion_pct: pct(won.length, leads.length),
    revenue,
    avg_job_value: won.length ? Math.round(revenue / won.length) : null,
    median_reply_minutes: median(replies),
    replied_within_5_min_pct: pct(replies.filter((m) => m < 5).length, leads.length),
    unanswered: leads.filter((l) => !l.first_response_at).length,
    open_hot_leads: w.leads.filter((l) => l.analysis?.priority === 'hot' && OPEN.includes(l.status)).length,
    previous_leads: previous.length,
    previous_won: prevWon.length,
    previous_revenue: prevRevenue,
    leads_change_pct: change(leads.length, previous.length),
    revenue_change_pct: change(revenue, prevRevenue),
  }
}

/** Plain-English sentences about the period, most useful first. */
function highlightsFor(leads, s) {
  const out = []
  const sources = sourceStats(leads).filter((x) => x.leads >= 3)
  if (sources.length >= 2) {
    const money = [...sources].sort((a, b) => b.revenue - a.revenue)[0]
    const busiest = sources[0]
    if (money.source !== busiest.source)
      out.push(`${channelName(busiest.source)} brought the most enquiries (${busiest.leads}), but ${channelName(money.source)} brought the most money: ${rupees(money.revenue)} from ${money.leads} enquiries.`)
    else out.push(`${channelName(money.source)} is your best channel: ${money.leads} enquiries and ${rupees(money.revenue)} in sales.`)
  }
  const speed = replySpeed(leads)
  const fast = speed[0]
  const slow = speed.filter((b) => ['2-24 hrs', 'over a day'].includes(b.bucket))
  const slowLeads = slow.reduce((n, b) => n + b.leads, 0)
  const slowWon = slow.reduce((n, b) => n + b.won, 0)
  if (fast.leads >= 3 && slowLeads >= 3)
    out.push(`Enquiries you answered within 5 minutes bought ${fast.win_rate_pct}% of the time, against ${pct(slowWon, slowLeads)}% when you took over 2 hours.`)
  if (s.unanswered) out.push(`${s.unanswered} ${s.unanswered === 1 ? 'enquiry has' : 'enquiries have'} had no reply at all.`)
  if (s.open_hot_leads) out.push(`${s.open_hot_leads} hot ${s.open_hot_leads === 1 ? 'enquiry is' : 'enquiries are'} waiting. Call them first.`)
  return out
}

export function summaryFor(w, days, until = Date.now()) {
  const p = period(days, until)
  const leads = leadsBetween(w, p.since, p.until)
  const s = headline(w, leads, leadsBetween(w, p.since - days * DAY, p.since))
  return { period: { since: iso(p.since), until: iso(p.until), days }, ...s, highlights: highlightsFor(leads, s) }
}

const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

export function timingFor(leads) {
  const hours = Array.from({ length: 24 }, (_, hour) => ({ hour, leads: 0 }))
  const weekdays = WEEKDAYS.map((day) => ({ day, leads: 0 }))
  for (const l of leads) {
    hours[istHour(l.created_at)].leads++
    weekdays[istWeekday(l.created_at)].leads++
  }
  const busiest = [...hours].sort((a, b) => b.leads - a.leads).slice(0, 3).map((h) => h.hour).sort((a, b) => a - b)
  return { hours, weekdays, busiest_hours: busiest, reply_speed: replySpeed(leads) }
}

export function funnelFor(leads) {
  const by_status = Object.fromEntries(['new', 'contacted', 'quoted', 'booked', 'won', 'lost'].map((s) => [s, 0]))
  leads.forEach((l) => by_status[l.status]++)
  return { received: leads.length, replied: leads.filter((l) => l.first_response_at).length, won: by_status.won, by_status }
}

export function servicesFor(leads) {
  const groups = Object.groupBy(leads, (l) => l.service ?? 'Other')
  const services = Object.entries(groups)
    .map(([name, list]) => {
      const won = list.filter((l) => l.status === 'won')
      return { name, leads: list.length, won: won.length, revenue: won.reduce((s, l) => s + l.job_value, 0) }
    })
    .sort((a, b) => b.leads - a.leads)
  return { services }
}

export function trendFor(leads, p) {
  const days = []
  for (let day = istDay(p.since); day <= istDay(p.until); day = addDays(day, 1)) days.push({ date: day, leads: 0, won: 0 })
  const index = Object.fromEntries(days.map((d, i) => [d.date, i]))
  for (const l of leads) {
    const row = days[index[istDay(l.created_at)]]
    if (!row) continue
    row.leads++
    if (l.status === 'won') row.won++
  }
  return days
}

// --------------------------------------------------------- content stats
export function pillarStats(posts) {
  const groups = Object.groupBy(posts, (p) => p.pillar)
  return Object.entries(groups).map(([pillar, list]) => {
    const sum = (f) => list.reduce((s, p) => s + f(p), 0)
    const reach = sum((p) => p.metrics?.reach ?? 0)
    const enquiries = sum((p) => p.results?.enquiries ?? 0)
    const revenue = sum((p) => p.results?.revenue ?? 0)
    return {
      pillar,
      posts: list.length,
      reach,
      avg_reach: Math.round(reach / list.length),
      likes: sum((p) => p.metrics?.likes ?? 0),
      engagement_pct: round1(sum((p) => p.metrics?.engagement_pct ?? 0) / list.length),
      enquiries,
      customers: sum((p) => p.results?.customers ?? 0),
      revenue,
      enquiries_per_post: round1(enquiries / list.length),
      revenue_per_post: Math.round(revenue / list.length),
    }
  })
}

export function upcomingEvents(w, now = Date.now()) {
  const today = istDay(now)
  const ideas = EVENT_IDEAS[w.business.category] ?? {}
  return EVENTS.filter(([date]) => date >= today)
    .slice(0, 8)
    .map(([date, name, kind]) => ({
      date,
      name,
      kind,
      days_away: Math.round((ms(`${date}T00:00:00Z`) - ms(`${today}T00:00:00Z`)) / DAY),
      idea: ideas[name] ?? ideas.default,
    }))
}

// ---------------------------------------------------------- weekly review
const PRESENCE = {
  gym: { photos: 'ok', catalog: 'ok' },
  car_detailing: { photos: 'warn', catalog: 'missing' },
  dental_clinic: { photos: 'warn', catalog: 'ok' },
}

export function makeReport(w, at) {
  const until = ms(at)
  const since = until - 7 * DAY
  const leads = leadsBetween(w, since, until)
  const s = headline(w, leads, leadsBetween(w, since - 7 * DAY, since))
  const sources = sourceStats(leads).filter((x) => x.leads >= 2)
  const speed = replySpeed(leads)
  const slow = speed.filter((b) => ['2-24 hrs', 'over a day', 'no reply'].includes(b.bucket))
  const slowLeads = slow.reduce((n, b) => n + b.leads, 0)
  const weekPosts = w.posts.filter((p) => p.status === 'published' && ms(p.published_at) >= since && ms(p.published_at) < until)
  const unhappy = w.reviews.filter((r) => r.rating <= 3 && !r.reply_text && ms(r.created_at) < until)
  const instagramExpired = w.social.some((a) => a.platform === 'instagram' && a.status === 'expired')
  const pillars30 = pillarStats(w.posts.filter((p) => p.status === 'published' && ms(p.published_at) >= until - 30 * DAY && ms(p.published_at) < until))
  const bestPillar = [...pillars30].sort((a, b) => b.revenue - a.revenue)[0]

  const findings = []
  if (s.leads_change_pct != null)
    findings.push({
      kind: s.leads_change_pct >= 0 ? 'good' : 'bad',
      title: `Enquiries ${s.leads_change_pct >= 0 ? 'up' : 'down'} ${Math.abs(Math.round(s.leads_change_pct))}% on last week`,
      detail: `${s.leads} this week against ${s.previous_leads} the week before.`,
    })
  const money = [...sources].sort((a, b) => b.revenue - a.revenue)[0]
  if (money?.revenue)
    findings.push({ kind: 'good', title: `${channelName(money.source)} is your best money channel`, detail: `${rupees(money.revenue)} from ${money.leads} enquiries (${money.conversion_pct}% bought).` })
  const leaky = sources.find((x) => x.leads >= 5 && x.conversion_pct < 15)
  if (leaky)
    findings.push({ kind: 'bad', title: `${channelName(leaky.source)} brings enquiries but few customers`, detail: `${leaky.leads} enquiries, only ${leaky.won} bought. Reply faster there and share prices upfront.` })
  if (speed[0].leads >= 2)
    findings.push({ kind: 'good', title: `Fast replies won ${speed[0].win_rate_pct}% of the time`, detail: `${speed[0].leads} enquiries got a reply within 5 minutes.` })
  if (slowLeads >= 2)
    findings.push({ kind: 'bad', title: `${slowLeads} enquiries waited over 2 hours or got no reply`, detail: `Only ${slow.reduce((n, b) => n + b.won, 0)} of them bought.` })
  if (unhappy.length)
    findings.push({ kind: 'bad', title: `${unhappy.length} unhappy ${unhappy.length === 1 ? 'review has' : 'reviews have'} no reply`, detail: 'They are the first thing new customers read.' })

  const ig = weekPosts.filter((p) => p.platform === 'instagram').length
  const google = weekPosts.filter((p) => p.platform === 'google').length
  const looks = PRESENCE[w.business.category]
  const presence = [
    { platform: 'google', item: 'Google profile has 30+ recent photos', status: looks.photos, detail: looks.photos === 'ok' ? null : 'Add 10 photos of real work this week.' },
    { platform: 'google', item: 'A Google post every week', status: google ? 'ok' : 'warn', detail: google ? null : 'Post one offer or finished job on Google.' },
    { platform: 'google', item: 'Every review gets a reply', status: unhappy.length ? 'missing' : 'ok', detail: unhappy.length ? `${unhappy.length} unhappy reviews are waiting.` : null },
    { platform: 'instagram', item: '3 or more Instagram posts a week', status: ig >= 3 ? 'ok' : 'warn', detail: `${ig} this week.` },
    { platform: 'instagram', item: 'Instagram connected', status: instagramExpired ? 'missing' : 'ok', detail: instagramExpired ? 'The login expired, so scheduled posts can\'t go out.' : null },
    { platform: 'whatsapp', item: 'WhatsApp Business catalog with prices', status: looks.catalog, detail: looks.catalog === 'ok' ? null : 'Price questions need a manual reply every time.' },
    { platform: 'website', item: 'Chat-on-WhatsApp button on the website', status: 'ok', detail: null },
  ]

  const actions = []
  if (unhappy.length) actions.push({ title: `Reply to the ${unhappy.length} unhappy ${unhappy.length === 1 ? 'review' : 'reviews'} today`, why: 'People read 1–3 star reviews first. A calm, quick reply shows you care, and the AI has drafts ready.', link: '/reviews' })
  if (s.open_hot_leads)
    actions.push({
      title: `Call the ${s.open_hot_leads} hot ${s.open_hot_leads === 1 ? 'enquiry' : 'enquiries'} waiting for you`,
      why: speed[0].win_rate_pct
        ? `Enquiries answered within 5 minutes bought ${speed[0].win_rate_pct}% of the time this week.`
        : 'Hot enquiries go cold within hours. They are ready to buy now.',
      link: '/leads?priority=hot&sort=score',
    })
  if (instagramExpired) actions.push({ title: 'Reconnect Instagram', why: 'Your scheduled posts can\'t go out until Instagram is reconnected.', link: '/settings' })
  if (bestPillar?.revenue) actions.push({ title: `Post 2 ${PILLAR_NAMES[bestPillar.pillar].toLowerCase()} posts this week`, why: `${PILLAR_NAMES[bestPillar.pillar]} posts brought ${bestPillar.enquiries} enquiries and ${rupees(bestPillar.revenue)} in the last 30 days, more than any other type.`, link: '/content' })
  if (slowLeads >= 2) actions.push({ title: 'Reply within 5 minutes during your busiest hours', why: `${slowLeads} enquiries waited 2+ hours this week and most went cold.`, link: '/sources' })

  const change = s.leads_change_pct == null ? '' : `, ${s.leads_change_pct >= 0 ? 'up' : 'down'} ${Math.abs(Math.round(s.leads_change_pct))}% on last week`
  return {
    id: nextId(w, 'report'),
    business_id: w.business.id,
    run_id: null,
    created_at: iso(until),
    period_start: iso(since),
    period_end: iso(until),
    headline: `${s.leads} enquiries and ${rupees(s.revenue)} in sales this week${change}.`,
    summary: [findings.find((f) => f.kind === 'good')?.title, findings.find((f) => f.kind === 'bad')?.title]
      .filter(Boolean)
      .map((x) => `${x}.`)
      .join(' '),
    findings,
    presence,
    actions: actions.slice(0, 3),
  }
}

export function reportWhatsapp(w, report) {
  const lines = [`*Weekly review · ${w.business.name}*`, `_${new Date(report.period_start).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', timeZone: 'Asia/Kolkata' })} – ${new Date(report.period_end).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', timeZone: 'Asia/Kolkata' })}_`, '', report.headline]
  const good = report.findings.filter((f) => f.kind === 'good')
  const bad = report.findings.filter((f) => f.kind === 'bad')
  if (good.length) lines.push('', '✅ *Going well*', ...good.map((f) => `• ${f.title}`))
  if (bad.length) lines.push('', '⚠️ *Needs work*', ...bad.map((f) => `• ${f.title}`))
  lines.push('', '*Your 3 actions this week*', ...report.actions.map((a, i) => `${i + 1}. ${a.title}`))
  return lines.join('\n')
}

// ------------------------------------------------------------- AI diary
function step(agent, mode, msTaken, output, note = null) {
  return { agent, mode, ms: msTaken, output, note }
}

export function leadRun(w, lead, t = w.t, at = lead.analysis.analyzed_at) {
  const a = lead.analysis
  const fallback = t.chance(0.04)
  const start = ms(at) - 2000
  const run = {
    id: nextId(w, 'run'),
    business_id: w.business.id,
    workflow: 'lead',
    lead_id: lead.id,
    status: 'done',
    error: null,
    started_at: iso(start),
    finished_at: iso(ms(at)),
    steps: [
      step('intake', 'mock', t.int(10, 40), { service: lead.service, car_model: lead.car_model, shared_phone: Boolean(lead.phone), wants_soon: 'wants_soon' in a.score_breakdown }),
      step('sentiment', 'mock', t.int(2, 9), { sentiment: a.sentiment, reason: a.sentiment_reason }),
      step('scoring', fallback ? 'fallback' : 'mock', t.int(2, 12), { score: a.score, breakdown: a.score_breakdown, reason: a.score_reason },
        fallback ? 'The AI took too long, so the rule-based score was used.' : null),
      step('priority_router', 'rules', 0, { priority: a.priority, reason: a.priority === 'hot' ? `High score (${a.score}): likely to buy.` : `Score ${a.score}: normal follow-up.` }),
    ],
  }
  return run
}

function buildLeadRuns(w, t, now) {
  w.leads.filter((l) => now - ms(l.created_at) < 12 * DAY).forEach((l) => w.runs.push(leadRun(w, l, t)))
}

export function growthRun(w, report) {
  const t = w.t
  const start = ms(report.created_at) - t.int(4, 9) * 1000
  const run = {
    id: nextId(w, 'run'),
    business_id: w.business.id,
    workflow: 'growth',
    lead_id: null,
    status: 'done',
    error: null,
    started_at: iso(start),
    finished_at: report.created_at,
    steps: [
      step('data_analyst', 'mock', t.int(20, 60), { findings: report.findings.map((f) => f.title), weak_platforms: [] }),
      step('presence_auditor', 'mock', t.int(10, 40), { items: report.presence.filter((p) => p.status !== 'ok').map((p) => ({ platform: p.platform, issue: p.item, fix: p.detail })) }),
      step('strategy', 'mock', t.int(30, 90), { focus: report.actions.map((a) => a.title) }),
      step('report_writer', 'mock', t.int(20, 70), { headline: report.headline, top_actions: report.actions.map((a) => a.title) }),
    ],
  }
  report.run_id = run.id
  return run
}

export function contentRun(w, kind, at, posts) {
  const t = w.t
  return {
    id: nextId(w, 'run'),
    business_id: w.business.id,
    workflow: 'content',
    lead_id: null,
    status: 'done',
    error: null,
    started_at: iso(ms(at) - t.int(2, 6) * 1000),
    finished_at: iso(at),
    steps:
      kind === 'plan'
        ? [
            step('performance_reader', 'mock', t.int(10, 30), { best_pillars: pillarStats(w.posts.filter((p) => p.status === 'published')).sort((a, b) => b.revenue - a.revenue).slice(0, 2).map((p) => PILLAR_NAMES[p.pillar]) }),
            step('content_planner', 'mock', t.int(40, 120), { ideas: posts.map((p) => `${p.date}: ${p.title}`) }),
          ]
        : [step('caption_writer', 'mock', t.int(60, 180), { written: posts.map((p) => p.title) })],
  }
}

export function reviewsRun(w, at, drafted) {
  const t = w.t
  return {
    id: nextId(w, 'run'),
    business_id: w.business.id,
    workflow: 'reviews',
    lead_id: null,
    status: 'done',
    error: null,
    started_at: iso(ms(at) - t.int(2, 5) * 1000),
    finished_at: iso(at),
    steps: [step('review_replier', 'mock', t.int(40, 140), { drafted: drafted.map((r) => `${r.rating}★ ${r.author}`) })],
  }
}
