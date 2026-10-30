/*
  The meaning behind the colours: which colour, icon and label each
  channel, mood, status and post type gets, and how times and money are
  written. Every page uses these, so WhatsApp is the same green with the
  same icon everywhere, and every time is India time.

  CHANNELS is in the order the palette validator approved: charts that
  stack or place channels side by side should use this order, so
  neighbouring colours stay easy to tell apart (also for colour-blind
  readers). The colour is always shown WITH the channel's name.
*/
import {
  Briefcase,
  Building2,
  CalendarClock,
  Camera,
  CircleCheck,
  CircleX,
  Clapperboard,
  Flame,
  Frown,
  Globe,
  GraduationCap,
  Lightbulb,
  MapPin,
  MessageCircle,
  PartyPopper,
  PenLine,
  Phone,
  Play,
  Quote,
  Smile,
  Store,
  Tag,
  TrendingUp,
  TriangleAlert,
  Users,
  Zap,
} from 'lucide-react'

// ---------------------------------------------------------------- channels
export const CHANNELS = [
  { key: 'google', label: 'Google', icon: MapPin, color: 'var(--ch-google)' },
  { key: 'justdial', label: 'Justdial', icon: Phone, color: 'var(--ch-justdial)' },
  { key: 'indiamart', label: 'IndiaMART', icon: Building2, color: 'var(--ch-indiamart)' },
  { key: 'walkin', label: 'Walk-in', icon: Store, color: 'var(--ch-walkin)' },
  { key: 'instagram', label: 'Instagram', icon: Camera, color: 'var(--ch-instagram)' },
  { key: 'whatsapp', label: 'WhatsApp', icon: MessageCircle, color: 'var(--ch-whatsapp)' },
  { key: 'website', label: 'Website', icon: Globe, color: 'var(--ch-website)' },
]

export const CHANNEL = Object.fromEntries(CHANNELS.map((c) => [c.key, c]))

export function channel(key) {
  return CHANNEL[key] ?? { key, label: key, icon: Globe, color: 'var(--ink-3)' }
}

/* Where posts go and which accounts can be connected. */
export const PLATFORMS = {
  instagram: { label: 'Instagram', icon: Camera, color: 'var(--ch-instagram)' },
  facebook: { label: 'Facebook', icon: Users, color: 'var(--ch-website)' },
  google: { label: 'Google', icon: MapPin, color: 'var(--ch-google)' },
  google_business: { label: 'Google Business Profile', icon: MapPin, color: 'var(--ch-google)' },
  whatsapp: { label: 'WhatsApp', icon: MessageCircle, color: 'var(--ch-whatsapp)' },
  whatsapp_business: { label: 'WhatsApp Business', icon: MessageCircle, color: 'var(--ch-whatsapp)' },
  youtube: { label: 'YouTube', icon: Play, color: 'var(--critical)' },
  // Task 40: LinkedIn Company Page posting (B2B, coaching, real estate)
  linkedin: { label: 'LinkedIn', icon: Briefcase, color: 'var(--ch-indiamart)' },
}

export function platform(key) {
  return PLATFORMS[key] ?? { label: key, icon: Globe, color: 'var(--ink-3)' }
}

// ------------------------------------------------------------- enquiries
/* Moods use the fixed status colours, always with an icon and a word. */
export const SENTIMENTS = {
  frustrated: { label: 'Frustrated', icon: Frown, tone: 'critical' },
  urgent: { label: 'Urgent', icon: Zap, tone: 'serious' },
  casual: { label: 'Casual', icon: Smile, tone: 'neutral' },
}

export const PRIORITIES = {
  hot: { label: 'Hot', icon: Flame, tone: 'accent' },
  normal: { label: 'Normal', icon: null, tone: 'neutral' },
}

/* In the order an enquiry moves through them. */
export const STATUSES = {
  new: { label: 'New', tone: 'brand' },
  contacted: { label: 'Contacted', tone: 'neutral' },
  quoted: { label: 'Quoted', tone: 'warning' },
  booked: { label: 'Booked', tone: 'serious' },
  won: { label: 'Won', tone: 'good' },
  lost: { label: 'Lost', tone: 'critical' },
}

/* Service keys from the car-accessories server; newer servers send plain names. */
export const SERVICES = {
  android_stereo: 'Android screen',
  reverse_camera: 'Reverse camera',
  dashcam: 'Dashcam',
  ambient_lighting: 'Ambient lighting',
  speakers: 'Speakers',
  central_locking: 'Central locking',
  gps_tracker: 'GPS tracker',
  remote_start: 'Push start',
}

export const serviceLabel = (service) => (service ? (SERVICES[service] ?? service) : null)

/* What each scoring rule means (keys come from the backend's score_breakdown). */
export const SCORE_RULES = {
  base: 'New enquiry',
  wants_soon: 'Wants it soon',
  phone_shared: 'Shared a phone number',
  service_named: 'Knows what they want',
  car_named: 'Gave the car model',
  fleet: 'Several vehicles',
  big_fleet: 'Fleet order (5+ vehicles)',
  urgent_tone: 'Urgent tone',
  frustrated_tone: 'Frustrated tone',
  two_messages: 'Replied again',
  three_plus_messages: 'Long conversation',
  price_only: 'Only asked the price',
  ai_adjustment: 'AI reading of the wording',
}

export function scoreRuleLabel(key) {
  if (key.startsWith('source_')) return `Came via ${channel(key.slice(7)).label}`
  const text = SCORE_RULES[key] ?? key.replaceAll('_', ' ')
  return text.charAt(0).toUpperCase() + text.slice(1)
}

/* How to name a lead: their name, else phone, else "Instagram user #12". */
export function leadTitle(lead) {
  if (lead.name) return lead.name
  if (lead.phone) return `+91 ${lead.phone}`
  return `${lead.source === 'instagram' ? 'Instagram user' : 'Customer'} #${lead.id}`
}

// ------------------------------------------------------------ social posts
export const POST_STATUSES = {
  idea: { label: 'Idea', tone: 'neutral', icon: Lightbulb },
  draft: { label: 'Draft', tone: 'warning', icon: PenLine },
  scheduled: { label: 'Scheduled', tone: 'brand', icon: CalendarClock },
  published: { label: 'Published', tone: 'good', icon: CircleCheck },
  failed: { label: "Couldn't post", tone: 'critical', icon: TriangleAlert },
}

/* The kinds of post ("content pillars"), in plain words. */
export const PILLARS = {
  offer: { label: 'Offer', icon: Tag },
  testimonial: { label: 'Customer story', icon: Quote },
  educational: { label: 'Tips', icon: GraduationCap },
  trend: { label: 'Trend', icon: TrendingUp },
  behind_the_scenes: { label: 'Behind the scenes', icon: Clapperboard },
  festival: { label: 'Festival', icon: PartyPopper },
}

export const pillar = (key) => PILLARS[key] ?? { label: key?.replaceAll('_', ' ') ?? 'Post', icon: Tag }

export const FORMATS = { reel: 'Reel', post: 'Post', story: 'Story', carousel: 'Carousel' }

// --------------------------------------------------------------- reviews
export const REQUEST_STATUSES = {
  pending: { label: 'Waiting to send', tone: 'warning' },
  sent: { label: 'Sent', tone: 'brand' },
  reviewed: { label: 'Reviewed', tone: 'good' },
  skipped: { label: 'Skipped', tone: 'neutral' },
}

/* The weekly review's online-presence checklist. */
export const PRESENCE = {
  ok: { label: 'Done', tone: 'good', icon: CircleCheck },
  warn: { label: 'Could be better', tone: 'warning', icon: TriangleAlert },
  missing: { label: 'Missing', tone: 'critical', icon: CircleX },
}

// ------------------------------------------------------------- AI team
export const AGENTS = {
  intake: 'Intake',
  sentiment: 'Tone reader',
  scoring: 'Scorer',
  priority_router: 'Hot-lead router',
  hot_lead: 'Hot-lead router',
  normal_lead: 'Hot-lead router',
  data_analyst: 'Analyst',
  presence_auditor: 'Presence checker',
  strategy: 'Strategist',
  report_writer: 'Report writer',
  performance_reader: 'Performance reader',
  content_planner: 'Content planner',
  caption_writer: 'Caption writer',
  review_replier: 'Review replier',
}

export const agentLabel = (key) => AGENTS[key] ?? key.replaceAll('_', ' ').replace(/^\w/, (c) => c.toUpperCase())

export const WORKFLOWS = {
  lead: 'New enquiry',
  insights: 'Weekly review',
  growth: 'Weekly review',
  content: 'Social posts',
  reviews: 'Review replies',
}

/* Where each answer came from. */
export const AI_MODES = {
  real: { label: 'Claude', tone: 'good' },
  mock: { label: 'Practice', tone: 'warning' },
  fallback: { label: 'Fallback', tone: 'serious' },
  rules: { label: 'Rules', tone: 'neutral' },
}

// ------------------------------------------------------- time (India)
// The backend sends UTC ("...Z"). The owner always sees India time.
export const IST = 'Asia/Kolkata'

/** 'YYYY-MM-DD' of a moment, in India. */
export const istDateKey = (value = Date.now()) => new Date(value).toLocaleDateString('en-CA', { timeZone: IST })

export function addDaysKey(key, n) {
  const d = new Date(`${key}T00:00:00Z`)
  d.setUTCDate(d.getUTCDate() + n)
  return d.toISOString().slice(0, 10)
}

const daysBetween = (fromKey, toKey) => Math.round((Date.parse(`${toKey}T00:00:00Z`) - Date.parse(`${fromKey}T00:00:00Z`)) / 86_400_000)

/** "7:30 pm" (or "7 pm" on the hour), India time. */
export function timeIST(value) {
  const text = new Date(value).toLocaleTimeString('en-IN', { hour: 'numeric', minute: '2-digit', hour12: true, timeZone: IST })
  return text.replace(':00', '').replace(/\s?([ap])\.?m\.?/i, ' $1m').toLowerCase()
}

/** "Today", "Tomorrow", "Yesterday", "Mon 19 Oct" (or "19 Oct 2025" in another year) for a 'YYYY-MM-DD' key. */
export function dayLabel(key, { weekday = true } = {}) {
  const diff = daysBetween(istDateKey(), key)
  if (diff === 0) return 'Today'
  if (diff === 1) return 'Tomorrow'
  if (diff === -1) return 'Yesterday'
  const date = new Date(`${key}T12:00:00Z`)
  const sameYear = key.slice(0, 4) === istDateKey().slice(0, 4)
  return date.toLocaleDateString('en-IN', {
    weekday: weekday && sameYear ? 'short' : undefined,
    day: 'numeric',
    month: 'short',
    year: sameYear ? undefined : 'numeric',
    timeZone: 'UTC',
  })
}

/** "Today, 7:30 pm", "Yesterday, 9 am", "Mon 12 Oct, 6 pm". */
export function when(value) {
  if (!value) return '—'
  return `${dayLabel(istDateKey(value))}, ${timeIST(value)}`
}

/** "12 Oct" or "12 Oct 2025", India time. */
export function shortDate(value) {
  if (!value) return '—'
  return dayLabel(istDateKey(value), { weekday: false })
}

/* "just now", "12 min ago", "3 hrs ago", "2 days ago", then the date. */
export function timeAgo(value) {
  if (!value) return '—'
  const seconds = (Date.now() - new Date(value).getTime()) / 1000
  const ago = (n, unit) => `${n} ${unit}${n === 1 ? '' : 's'} ago`
  if (seconds < 60) return 'just now'
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`
  if (seconds < 86400) return ago(Math.floor(seconds / 3600), 'hr')
  if (seconds < 86400 * 7) return ago(Math.floor(seconds / 86400), 'day')
  return shortDate(value)
}

/** Kept for older call sites: same as when(). */
export const dateTime = when

/* 0 → "12 am", 13 → "1 pm" */
export const hourLabel = (h) => `${h % 12 || 12} ${h < 12 ? 'am' : 'pm'}`

/** "Good morning" / "Good afternoon" / "Good evening", by India time. Pass lang="hi" for Hindi. */
export function greeting(lang = 'en') {
  const hour = Number(new Date().toLocaleString('en-US', { hour: 'numeric', hour12: false, timeZone: IST }))
  const words =
    lang === 'hi'
      ? { morning: 'सुप्रभात', afternoon: 'नमस्कार', evening: 'शुभ संध्या' }
      : { morning: 'Good morning', afternoon: 'Good afternoon', evening: 'Good evening' }
  if (hour < 12) return words.morning
  if (hour < 17) return words.afternoon
  return words.evening
}

/* Reply time in words: 3 → "3 min", 95 → "1.6 hrs", 3000 → "2.1 days". */
export function minutes(value) {
  if (value == null) return '—'
  if (value < 60) return `${Math.round(value)} min`
  if (value < 60 * 24) return `${(value / 60).toFixed(1)} hrs`
  return `${(value / 1440).toFixed(1)} days`
}

// ----------------------------------------------------------------- money
/* Indian number style: 145500 -> "₹1,45,500". `short` shortens only lakhs and crores ("₹1.5 L", "₹2.3 Cr"). */
export function inr(amount, { short = false } = {}) {
  if (amount == null) return '—'
  if (short && amount >= 10_000_000) return `₹${(amount / 10_000_000).toFixed(1)} Cr`
  if (short && amount >= 100_000) return `₹${(amount / 100_000).toFixed(1)} L`
  return `₹${Math.round(amount).toLocaleString('en-IN')}`
}

/* 1234567 -> "12,34,567" */
export const count = (n) => (n == null ? '—' : Math.round(n).toLocaleString('en-IN'))

/* "1 enquiry" / "3 enquiries" */
export const plural = (n, one, many = `${one}s`) => `${count(n)} ${n === 1 ? one : many}`
