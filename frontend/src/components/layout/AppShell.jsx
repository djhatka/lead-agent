/*
  The frame around every page.

    big screens:  [ sidebar | top bar + page ]
    phones:       [ top bar + page + bottom bar ]

  Pages wait for the list of businesses (every request needs one). If the
  server can't be reached at all, a friendly full-page message says so.
  A "Skip to content" link lets keyboard users jump past the menu.
*/
import { useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'
import { ScrollRestoration } from 'react-router'

import { isSampleOnlyBusiness } from '@/api/client'
import { AnimatedOutlet } from '@/components/layout/AnimatedOutlet'
import { BottomNav } from '@/components/layout/BottomNav'
import { Sidebar } from '@/components/layout/Sidebar'
import { TopBar } from '@/components/layout/TopBar'
import { Skeleton } from '@/components/ui/Skeleton'
import { ErrorState } from '@/components/ui/States'
import { toast } from '@/components/ui/toast'
import { Toaster } from '@/components/ui/Toaster'
import { useBusiness } from '@/hooks/useBusiness'
import { LiveFeedConnection, useLiveEvent } from '@/hooks/useLiveFeed'
import { useRouteHandle } from '@/hooks/useRouteHandle'
import { channel, serviceLabel } from '@/styles/tokens'

/** 🔥 A new hot enquiry pops up the moment the AI flags it (from the server's live feed). */
function HotLeadAlerts() {
  const { business } = useBusiness()
  useLiveEvent('hot_lead', (event) => {
    const lead = event.data ?? {}
    if (!business || isSampleOnlyBusiness(business.id)) return // the feed is the server's own business
    if (lead.business_id != null && lead.business_id !== business.id) return
    toast({
      title: 'New hot enquiry',
      body: [lead.name ?? 'Someone', `on ${channel(lead.source).label}`, serviceLabel(lead.service), `score ${lead.score}`]
        .filter(Boolean)
        .join(' · '),
      tone: 'accent',
      to: `/leads/${lead.lead_id}`,
      action: 'Open enquiry',
      seconds: 10,
    })
  })
  return null
}

/** 💰 A customer pressed "I've paid" on their payment page: check the UPI app and confirm. */
function PaymentAlerts() {
  const { business } = useBusiness()
  useLiveEvent('payment_claimed', (event) => {
    if (!business || event.data?.business_id !== business.id) return
    toast({ title: event.title, body: event.message, tone: 'good', to: '/payments', action: 'Confirm it', seconds: 10 })
  })
  return null
}

function PageSkeleton() {
  return (
    <div className="space-y-6" aria-busy="true" aria-label="Loading">
      <Skeleton className="h-9 w-56" />
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {Array.from({ length: 4 }, (_, i) => (
          <Skeleton key={i} className="h-28 rounded-card" />
        ))}
      </div>
      <Skeleton className="h-64 rounded-card" />
    </div>
  )
}

export function AppShell() {
  const { query: businesses } = useBusiness()
  const handle = useRouteHandle()
  const client = useQueryClient()

  useEffect(() => {
    document.title = handle.title ? `${handle.title} · Growth Partner` : 'Growth Partner'
  }, [handle.title])

  return (
    <div className="min-h-dvh lg:pl-64">
      <a
        href="#content"
        className="sr-only z-50 rounded-control bg-brand px-4 py-2 text-on-brand focus:not-sr-only focus:fixed focus:top-3 focus:left-3"
      >
        Skip to content
      </a>

      <aside className="glass fixed inset-y-0 left-0 z-30 hidden w-64 rounded-none border-y-0 border-l-0 lg:block">
        <Sidebar />
      </aside>

      <TopBar />

      <main id="content" tabIndex={-1} className="mx-auto max-w-7xl px-4 pt-6 pb-28 outline-none sm:px-6 lg:pb-12">
        {businesses.isError ? (
          <ErrorState
            title="Can't reach your dashboard's server"
            error={businesses.error}
            onRetry={() => client.invalidateQueries()}
          />
        ) : businesses.isPending ? (
          <PageSkeleton />
        ) : (
          <AnimatedOutlet />
        )}
      </main>

      <BottomNav />
      <Toaster />
      <HotLeadAlerts />
      <PaymentAlerts />
      <ScrollRestoration />
      <LiveFeedConnection />
    </div>
  )
}
