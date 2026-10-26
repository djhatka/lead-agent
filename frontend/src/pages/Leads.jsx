/*
  Leads: every enquiry, scored by the AI team.

  /leads           the filtered, paged list
  /leads/42        the same list with lead 42's drawer open on top

  Filters live in the address bar (see hooks/useLeadFilters.js). The list
  refreshes by itself when the live feed reports a new or changed lead.
*/
import clsx from 'clsx'
import { ChevronLeft, ChevronRight, SearchX } from 'lucide-react'
import { AnimatePresence } from 'motion/react'
import { useCallback } from 'react'
import { useNavigate, useParams } from 'react-router'

import { PageHeader } from '@/components/layout/PageHeader'
import { LeadDrawer } from '@/components/leads/LeadDrawer'
import { LeadFilters } from '@/components/leads/LeadFilters'
import { LeadTable } from '@/components/leads/LeadTable'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { Skeleton } from '@/components/ui/Skeleton'
import { EmptyState, ErrorState } from '@/components/ui/States'
import { PAGE_SIZE, useLeadFilters } from '@/hooks/useLeadFilters'
import { useLeads } from '@/hooks/useLeads'

function TableSkeleton() {
  return (
    <div className="divide-y divide-line" aria-busy="true" aria-label="Loading leads">
      {Array.from({ length: 8 }, (_, i) => (
        <div key={i} className="flex items-center gap-4 px-5 py-4">
          <Skeleton className="size-9 rounded-full" />
          <div className="flex-1 space-y-2">
            <Skeleton className="h-4 w-40" />
            <Skeleton className="h-3 w-3/4" />
          </div>
          <Skeleton className="hidden h-6 w-20 md:block" />
        </div>
      ))}
    </div>
  )
}

export default function Leads() {
  const { leadId } = useParams()
  const navigate = useNavigate()
  const { filters, query, setFilter, clear, active, search } = useLeadFilters()
  const leads = useLeads(query)

  const closeDrawer = useCallback(() => navigate({ pathname: '/leads', search }), [navigate, search])

  const data = leads.data
  const pages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1
  const from = data && data.total ? (filters.page - 1) * PAGE_SIZE + 1 : 0
  const to = data ? Math.min(filters.page * PAGE_SIZE, data.total) : 0

  return (
    <div className="space-y-4">
      <PageHeader className="mb-2" />
      <LeadFilters filters={filters} setFilter={setFilter} clear={clear} active={active} total={data?.total} />

      {leads.isError ? (
        <ErrorState error={leads.error} onRetry={() => leads.refetch()} />
      ) : (
        <Card className={clsx('overflow-hidden p-0 transition-opacity duration-200', leads.isPlaceholderData && 'opacity-60')}>
          {leads.isPending ? (
            <TableSkeleton />
          ) : data.items.length === 0 ? (
            <EmptyState
              icon={SearchX}
              title={active ? 'No enquiries match these filters' : 'No enquiries yet'}
              action={active && <Button onClick={clear}>Clear filters</Button>}
            >
              {active
                ? 'Try a different channel, status or search word.'
                : 'Enquiries from WhatsApp, Instagram, your website, Justdial and Google will appear here.'}
            </EmptyState>
          ) : (
            <LeadTable leads={data.items} search={search} pageKey={`${search}`} />
          )}
        </Card>
      )}

      {data && data.total > PAGE_SIZE && (
        <nav aria-label="Pages" className="flex items-center justify-between gap-3 text-sm">
          <p className="text-ink-3">
            Showing <span className="num font-medium text-ink">{from}–{to}</span> of{' '}
            <span className="num font-medium text-ink">{data.total}</span>
          </p>
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              icon={ChevronLeft}
              disabled={filters.page <= 1}
              onClick={() => setFilter('page', filters.page - 1)}
            >
              Previous
            </Button>
            <span className="num text-ink-3">
              {filters.page} / {pages}
            </span>
            <Button size="sm" disabled={filters.page >= pages} onClick={() => setFilter('page', filters.page + 1)}>
              Next
              <ChevronRight aria-hidden className="size-4" />
            </Button>
          </div>
        </nav>
      )}

      <AnimatePresence>
        {leadId && <LeadDrawer key="drawer" leadId={leadId} onClose={closeDrawer} />}
      </AnimatePresence>
    </div>
  )
}
