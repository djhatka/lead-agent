/*
  The menu: every page, grouped the way an owner thinks about them.
  (Kept apart from routes.jsx so the menus and the router don't import each other.)

  Big screens show all of it in the sidebar. Phones show the four
  everyday pages in the bottom bar, and the rest under "More".
*/
import { Bot, CalendarDays, ChartColumn, ChartPie, House, Inbox, IndianRupee, ListChecks, Plug, RefreshCw, Settings, Star, Trophy } from 'lucide-react'

export const NAV_GROUPS = [
  {
    label: null,
    items: [
      { path: '/', label: 'Home', icon: House, end: true },
      { path: '/leads', label: 'Enquiries', icon: Inbox, badge: 'hot' },
      { path: '/payments', label: 'Payments', icon: IndianRupee, badge: 'payments' },
      { path: '/renewals', label: 'Renewals', icon: RefreshCw },
      { path: '/sources', label: 'Where customers come from', short: 'Sources', icon: ChartPie },
    ],
  },
  {
    label: 'Social media',
    items: [
      { path: '/content', label: 'Content calendar', short: 'Content', icon: CalendarDays, end: true },
      { path: '/content/performance', label: "What's working", icon: ChartColumn },
    ],
  },
  {
    label: 'Growth',
    items: [
      { path: '/results', label: 'Your results', short: 'Results', icon: Trophy },
      { path: '/weekly-review', label: 'Weekly review', icon: ListChecks },
      { path: '/reviews', label: 'Reviews', icon: Star, badge: 'reviews' },
    ],
  },
  {
    label: 'Behind the scenes',
    items: [
      { path: '/ai-team', label: 'AI team', icon: Bot },
      { path: '/settings/connections', label: 'Connected apps', short: 'Apps', icon: Plug },
      { path: '/settings', label: 'Settings', icon: Settings, end: true },
    ],
  },
]

export const NAV = NAV_GROUPS.flatMap((group) => group.items)

/* The phone's bottom bar (plus "More"). `match` = which addresses light it up. */
export const BOTTOM_NAV = [
  { path: '/', label: 'Home', icon: House, match: (p) => p === '/' },
  { path: '/leads', label: 'Enquiries', icon: Inbox, badge: 'hot', match: (p) => p.startsWith('/leads') },
  { path: '/content', label: 'Content', icon: CalendarDays, match: (p) => p.startsWith('/content') },
  { path: '/reviews', label: 'Reviews', icon: Star, badge: 'reviews', match: (p) => p.startsWith('/reviews') },
]
