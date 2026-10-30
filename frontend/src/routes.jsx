/*
  Every page of the dashboard and its address (URL).

  The menus live in nav.js. Each route's `handle` gives the page title and
  subtitle, whether it uses the 7 / 30 / 90-day period switch, and which
  parts of the API it reads (`areas`, for the "Sample data" pill).

  Home and Enquiries load with the app. The other pages download the first
  time they're opened, so a phone on mobile data starts up faster.
*/
import { createBrowserRouter } from 'react-router'

import { AppShell } from '@/components/layout/AppShell'
import Home from '@/pages/Home'
import Leads from '@/pages/Leads'
import NotFound from '@/pages/NotFound'

/** A page that downloads when first opened. */
const page = (load) => async () => ({ Component: (await load()).default })

const leads = {
  titleKey: 'route.leads.title',
  subtitleKey: 'route.leads.subtitle',
  areas: ['leads'],
}

export const router = createBrowserRouter([
  {
    path: '/',
    element: <AppShell />,
    errorElement: <NotFound />,
    children: [
      { index: true, element: <Home />, handle: { titleKey: 'nav.home', period: true, areas: ['analytics', 'leads', 'growth'] } },
      { path: 'leads', element: <Leads />, handle: leads },
      { path: 'leads/:leadId', element: <Leads />, handle: leads },
      {
        path: 'sources',
        lazy: page(() => import('@/pages/Sources')),
        handle: {
          titleKey: 'route.sources.title',
          subtitleKey: 'route.sources.subtitle',
          period: true,
          areas: ['analytics'],
        },
      },
      {
        path: 'payments',
        lazy: page(() => import('@/pages/Payments')),
        handle: { titleKey: 'route.payments.title', subtitleKey: 'route.payments.subtitle' },
      },
      {
        path: 'renewals',
        lazy: page(() => import('@/pages/Renewals')),
        handle: { titleKey: 'route.renewals.title', subtitleKey: 'route.renewals.subtitle' },
      },
      {
        path: 'content',
        lazy: page(() => import('@/pages/ContentCalendar')),
        handle: { titleKey: 'route.content.title', subtitleKey: 'route.content.subtitle', areas: ['content'] },
      },
      {
        path: 'content/performance',
        lazy: page(() => import('@/pages/ContentPerformance')),
        handle: { titleKey: 'route.contentPerformance.title', subtitleKey: 'route.contentPerformance.subtitle', areas: ['content'] },
      },
      {
        path: 'results',
        lazy: page(() => import('@/pages/Results')),
        handle: { titleKey: 'route.results.title', subtitleKey: 'route.results.subtitle' },
      },
      {
        path: 'weekly-review',
        lazy: page(() => import('@/pages/WeeklyReview')),
        handle: { titleKey: 'route.weeklyReview.title', subtitleKey: 'route.weeklyReview.subtitle', areas: ['growth'] },
      },
      {
        path: 'reviews',
        lazy: page(() => import('@/pages/Reviews')),
        handle: { titleKey: 'route.reviews.title', subtitleKey: 'route.reviews.subtitle', areas: ['reviews'] },
      },
      {
        path: 'ai-team',
        lazy: page(() => import('@/pages/AgentRuns')),
        handle: { titleKey: 'route.aiTeam.title', subtitleKey: 'route.aiTeam.subtitle', areas: ['ai'] },
      },
      {
        path: 'billing',
        lazy: page(() => import('@/pages/Billing')),
        handle: { titleKey: 'route.billing.title', subtitleKey: 'route.billing.subtitle' },
      },
      {
        path: 'settings/connections',
        lazy: page(() => import('@/pages/Connections')),
        handle: { titleKey: 'route.connections.title', subtitleKey: 'route.connections.subtitle' },
      },
      {
        path: 'settings',
        lazy: page(() => import('@/pages/Settings')),
        handle: { titleKey: 'route.settings.title', subtitleKey: 'route.settings.subtitle', areas: ['settings'] },
      },
      // Dev-only reference page: not translated.
      { path: 'style-guide', lazy: page(() => import('@/pages/StyleGuide')), handle: { title: 'Style guide', subtitle: 'Design system reference' } },
      { path: '*', element: <NotFound /> },
    ],
  },
])
