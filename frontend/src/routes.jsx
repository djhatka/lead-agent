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
  title: 'Enquiries',
  subtitle: 'Every enquiry from every channel, scored by the AI',
  areas: ['leads'],
}

export const router = createBrowserRouter([
  {
    path: '/',
    element: <AppShell />,
    errorElement: <NotFound />,
    children: [
      { index: true, element: <Home />, handle: { title: 'Home', period: true, areas: ['analytics', 'leads', 'growth'] } },
      { path: 'leads', element: <Leads />, handle: leads },
      { path: 'leads/:leadId', element: <Leads />, handle: leads },
      {
        path: 'sources',
        lazy: page(() => import('@/pages/Sources')),
        handle: {
          title: 'Where customers come from',
          subtitle: 'Which channels bring enquiries, and which bring money',
          period: true,
          areas: ['analytics'],
        },
      },
      {
        path: 'payments',
        lazy: page(() => import('@/pages/Payments')),
        handle: { title: 'Payments', subtitle: 'Advances, fees and dues, paid straight to your UPI. Polite reminders included.' },
      },
      {
        path: 'renewals',
        lazy: page(() => import('@/pages/Renewals')),
        handle: { title: 'Renewals', subtitle: 'Memberships and services about to expire. A ready message for each, so nobody lapses.' },
      },
      {
        path: 'content',
        lazy: page(() => import('@/pages/ContentCalendar')),
        handle: { title: 'Content calendar', subtitle: 'Your next 7 days of posts. Nothing goes out until you schedule it.', areas: ['content'] },
      },
      {
        path: 'content/performance',
        lazy: page(() => import('@/pages/ContentPerformance')),
        handle: { title: "What's working", subtitle: 'Which posts bring customers and ₹, not just likes', areas: ['content'] },
      },
      {
        path: 'results',
        lazy: page(() => import('@/pages/Results')),
        handle: { title: 'Your results', subtitle: 'What Lead Intel did for you, month by month, in customers and ₹' },
      },
      {
        path: 'weekly-review',
        lazy: page(() => import('@/pages/WeeklyReview')),
        handle: { title: 'Weekly review', subtitle: 'What happened, what is missing, and your 3 actions', areas: ['growth'] },
      },
      {
        path: 'reviews',
        lazy: page(() => import('@/pages/Reviews')),
        handle: { title: 'Reviews', subtitle: 'Your Google rating, AI-drafted replies and review requests', areas: ['reviews'] },
      },
      {
        path: 'ai-team',
        lazy: page(() => import('@/pages/AgentRuns')),
        handle: { title: 'AI team', subtitle: 'What each AI helper did, step by step, and why', areas: ['ai'] },
      },
      {
        path: 'settings/connections',
        lazy: page(() => import('@/pages/Connections')),
        handle: { title: 'Connected apps', subtitle: 'Link your Instagram, Facebook, WhatsApp and Google so the AI can work with them' },
      },
      {
        path: 'settings',
        lazy: page(() => import('@/pages/Settings')),
        handle: { title: 'Settings', subtitle: 'Your business details (the AI writes from these) and social accounts', areas: ['settings'] },
      },
      { path: 'style-guide', lazy: page(() => import('@/pages/StyleGuide')), handle: { title: 'Style guide', subtitle: 'Design system reference' } },
      { path: '*', element: <NotFound /> },
    ],
  },
])
