/*
  The menu: every page, grouped the way an owner thinks about them.
  (Kept apart from routes.jsx so the menus and the router don't import each other.)

  Big screens show all of it in the sidebar. Phones show the four
  everyday pages in the bottom bar, and the rest under "More".
*/
import { Bot, CalendarDays, ChartColumn, ChartPie, House, Inbox, IndianRupee, ListChecks, Plug, Wallet, RefreshCw, Settings, Star, Trophy } from 'lucide-react'

export const NAV_GROUPS = [
  {
    labelKey: null,
    items: [
      { path: '/', labelKey: 'nav.home', icon: House, end: true },
      { path: '/leads', labelKey: 'nav.leads', icon: Inbox, badge: 'hot' },
      { path: '/payments', labelKey: 'nav.payments', icon: IndianRupee, badge: 'payments' },
      { path: '/renewals', labelKey: 'nav.renewals', icon: RefreshCw },
      { path: '/sources', labelKey: 'nav.sources', shortKey: 'nav.sources.short', icon: ChartPie },
    ],
  },
  {
    labelKey: 'nav.group.socialMedia',
    items: [
      { path: '/content', labelKey: 'nav.content', shortKey: 'nav.content.short', icon: CalendarDays, end: true },
      { path: '/content/performance', labelKey: 'nav.contentPerformance', icon: ChartColumn },
    ],
  },
  {
    labelKey: 'nav.group.growth',
    items: [
      { path: '/results', labelKey: 'nav.results', shortKey: 'nav.results.short', icon: Trophy },
      { path: '/weekly-review', labelKey: 'nav.weeklyReview', icon: ListChecks },
      { path: '/reviews', labelKey: 'nav.reviews', icon: Star, badge: 'reviews' },
    ],
  },
  {
    labelKey: 'nav.group.behindScenes',
    items: [
      { path: '/ai-team', labelKey: 'nav.aiTeam', icon: Bot },
      { path: '/settings/connections', labelKey: 'nav.connections', shortKey: 'nav.connections.short', icon: Plug, requires: 'connect_apps' },
      { path: '/billing', labelKey: 'nav.billing', icon: Wallet },
      { path: '/settings', labelKey: 'nav.settings', icon: Settings, end: true },
    ],
  },
]

export const NAV = NAV_GROUPS.flatMap((group) => group.items)

/* The phone's bottom bar (plus "More"). `match` = which addresses light it up. */
export const BOTTOM_NAV = [
  { path: '/', labelKey: 'nav.home', icon: House, match: (p) => p === '/' },
  { path: '/leads', labelKey: 'nav.leads', icon: Inbox, badge: 'hot', match: (p) => p.startsWith('/leads') },
  { path: '/content', labelKey: 'nav.content.short', icon: CalendarDays, match: (p) => p.startsWith('/content') },
  { path: '/reviews', labelKey: 'nav.reviews', icon: Star, badge: 'reviews', match: (p) => p.startsWith('/reviews') },
]

/* Hide the menu items whose feature the server hasn't switched on. */
export const visible = (items, on) => items.filter((item) => !item.requires || on(item.requires))
