/*
  Names for every piece of cached data.

  TanStack Query stores each answer under a "key". Keys are lists that
  start with the area and the business, e.g. ['leads', 2, 'detail', 2005],
  so telling it "leads changed" (['leads']) refreshes every lead view of
  every business at once, and switching business never shows another
  business's data.
*/
export const keys = {
  health: ['health'],
  aiStatus: ['ai-status'],
  businesses: ['businesses'],

  settings: ['settings'],
  business: (b) => ['settings', b, 'business'],
  social: (b) => ['settings', b, 'social'],

  analytics: ['analytics'],
  summary: (b, days) => ['analytics', b, 'summary', days],
  sources: (b, days) => ['analytics', b, 'sources', days],
  funnel: (b, days) => ['analytics', b, 'funnel', days],
  trend: (b, days) => ['analytics', b, 'trend', days],
  timing: (b, days) => ['analytics', b, 'timing', days],
  services: (b, days) => ['analytics', b, 'services', days],

  leads: ['leads'],
  leadList: (b, filters) => ['leads', b, 'list', filters],
  lead: (b, id) => ['leads', b, 'detail', Number(id)],

  followups: ['followups'],
  followupList: (b) => ['followups', b, 'list'],
  followup: (b, id) => ['followups', b, 'lead', Number(id)],

  dues: ['dues'],
  dueSettings: (b) => ['dues', b, 'settings'],
  dueSummary: (b) => ['dues', b, 'summary'],
  dueList: (b, status, leadId) => ['dues', b, 'list', status, leadId ?? null],
  due: (b, id) => ['dues', b, 'one', Number(id)],

  renewals: ['renewals'],
  renewalSettings: (b) => ['renewals', b, 'settings'],
  renewalList: (b) => ['renewals', b, 'list'],
  renewal: (b, id) => ['renewals', b, 'one', Number(id)],

  content: ['content'],
  calendar: (b, start) => ['content', b, 'calendar', start],
  posts: (b, filters) => ['content', b, 'posts', filters],
  topPosts: (b, by) => ['content', b, 'top', by],
  contentStats: (b, days) => ['content', b, 'stats', days],
  events: (b) => ['content', b, 'events'],

  growth: ['growth'],
  reports: (b, limit) => ['growth', b, 'reports', limit],
  report: (b, id) => ['growth', b, 'report', Number(id)],

  reviews: ['reviews'],
  reviewSummary: (b) => ['reviews', b, 'summary'],
  reviewList: (b, filters) => ['reviews', b, 'list', filters],
  reviewRequests: (b) => ['reviews', b, 'requests'],

  agentRuns: ['agent-runs'],
  agentRunList: (b, filters) => ['agent-runs', b, 'list', filters],
  agentRun: (b, id) => ['agent-runs', b, 'detail', Number(id)],
  workflow: (b, name) => ['agent-runs', b, 'workflow', name],
}

/** How often lists that change by themselves refresh (until the live feed covers every business). */
export const LIVE_REFRESH = 30_000

/**
 * For `placeholderData`: keep showing the previous answer while the next
 * one loads (new period, next page), but never another business's numbers.
 */
export const keepWithinBusiness = (b) => (previous, previousQuery) =>
  previousQuery?.queryKey[1] === b ? previous : undefined
