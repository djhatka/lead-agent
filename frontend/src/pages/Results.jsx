/*
  Your results: "what Lead Intel did for you" (Task 27).

  One month at a time (this month so far, or any earlier month):
    - the headline: new customers, ₹ in sales, and how many times the plan paid for itself
    - enquiries, customers, sales, and the sales that came straight from posts
    - where enquiries came from, and what the AI team did (posts, hot leads, reviews)
  The same report is emailed to owners on the 1st of every month. Every
  number is counted by the backend from the business's own records.
*/
import { useMutation, useQuery } from '@tanstack/react-query'
import { Copy, IndianRupee, Mail, ShoppingBag, Sparkles, Target, Users } from 'lucide-react'
import { useSearchParams } from 'react-router'

import { api } from '@/api/client'
import { StatTile } from '@/components/charts/StatTile'
import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/Button'
import { Card, CardHeader } from '@/components/ui/Card'
import { Skeleton } from '@/components/ui/Skeleton'
import { InlineError } from '@/components/ui/States'
import { toast } from '@/components/ui/toast'
import { useBusinessId } from '@/hooks/useBusiness'
import { count, inr } from '@/styles/tokens'

/** The last 12 months, newest first, as "2026-10" (India time). */
function lastMonths(n = 12) {
  const today = new Date(new Date().toLocaleString('en-US', { timeZone: 'Asia/Kolkata' }))
  return Array.from({ length: n }, (_, i) => {
    const d = new Date(today.getFullYear(), today.getMonth() - i, 1)
    const value = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
    const label = d.toLocaleDateString('en-IN', { month: 'long', year: 'numeric' })
    return { value, label: i === 0 ? `${label} (so far)` : label }
  })
}

function Line({ label, value }) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-2 first:pt-0 last:pb-0">
      <dt className="text-sm text-ink-2">{label}</dt>
      <dd className="num text-sm font-semibold text-ink">{value}</dd>
    </div>
  )
}

export default function Results() {
  const b = useBusinessId()
  const [params, setParams] = useSearchParams()
  const months = lastMonths()
  const month = params.get('month') ?? months[0].value
  const me = useQuery({ queryKey: ['me'], queryFn: api.me, staleTime: 5 * 60_000 })
  const isOwner = ['owner', 'admin'].includes(me.data?.user?.role)

  const report = useQuery({
    queryKey: ['roi', b, month],
    queryFn: () => api.roi(b, month),
    enabled: Boolean(b),
    placeholderData: (previous) => previous,
  })

  const send = useMutation({
    mutationFn: () => api.sendRoiReport(b, months[1].value),
    onSuccess: () => toast({ title: `${months[1].label} report emailed`, body: 'Check your inbox in a minute.', tone: 'good' }),
    onError: (error) => toast({ title: "Couldn't send the report", body: error.message, tone: 'critical' }),
  })

  async function copy() {
    try {
      await navigator.clipboard.writeText(report.data.message)
      toast({ title: 'Copied', body: 'Paste it into WhatsApp to share it.', tone: 'good' })
    } catch {
      toast({ title: "Couldn't copy", body: 'Your browser blocked it. Select the text and copy it instead.', tone: 'critical' })
    }
  }

  const actions = (
    <div className="flex flex-wrap items-center gap-2">
      <label className="sr-only" htmlFor="results-month">
        Month
      </label>
      <select
        id="results-month"
        value={month}
        onChange={(e) => setParams({ month: e.target.value }, { replace: true })}
        className="h-11 rounded-control border border-line bg-surface-raised px-3 text-sm text-ink"
      >
        {months.map((m) => (
          <option key={m.value} value={m.value}>
            {m.label}
          </option>
        ))}
      </select>
      <Button icon={Copy} onClick={copy} disabled={!report.data}>
        Copy for WhatsApp
      </Button>
      {isOwner && (
        <Button icon={Mail} loading={send.isPending} onClick={() => send.mutate()}>
          Email me last month's report
        </Button>
      )}
    </div>
  )

  if (report.isError) {
    return (
      <div className="space-y-6">
        <PageHeader actions={actions} />
        <InlineError error={report.error} onRetry={() => report.refetch()} />
      </div>
    )
  }

  if (!report.data) {
    return (
      <div className="space-y-6">
        <PageHeader actions={actions} />
        <Skeleton className="h-40 rounded-card" />
        <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
          {Array.from({ length: 4 }, (_, i) => (
            <Skeleton key={i} className="h-28 rounded-card" />
          ))}
        </div>
      </div>
    )
  }

  const s = report.data.stats
  const { enquiries: e, sales, posts, hot_leads: hot, reviews, plan } = s
  const prevRevenue = s.previous?.revenue
  const revenueChange = !s.so_far && prevRevenue ? ((sales.revenue - prevRevenue) / prevRevenue) * 100 : null
  const top = e.by_source?.[0]?.count || 1

  return (
    <div className={`space-y-6 transition-opacity ${report.isPlaceholderData ? 'opacity-60' : ''}`}>
      <PageHeader actions={actions} />

      <Card className="bg-brand-soft">
        <p className="text-sm font-medium text-brand">
          {s.label}
          {s.so_far ? ' · so far' : ''}
        </p>
        {s.return_multiple ? (
          <p className="mt-1 text-4xl font-bold tracking-tight text-ink sm:text-5xl">
            <span className="num">{s.return_multiple}×</span>
            <span className="ml-2 align-middle text-base font-medium text-ink-2">
              your {plan.name} plan {plan.on_trial ? 'would pay' : 'paid'} for itself
            </span>
          </p>
        ) : null}
        <p className="mt-2 max-w-3xl text-lg font-semibold text-balance text-ink">
          {/* The big number already says "paid for itself", so drop that part of the sentence here. */}
          {s.return_multiple ? `${s.headline.split(': your ')[0].replace(/\.$/, '')}.` : s.headline}
        </p>
      </Card>

      <div className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
        <StatTile label="Enquiries" icon={Users} value={e.total} hint={e.by_source?.[0] ? `most from ${e.by_source[0].name}` : undefined} />
        <StatTile label="New customers" icon={ShoppingBag} value={sales.customers} hint={`${s.previous?.customers ?? 0} the month before`} />
        <StatTile
          label="Sales"
          icon={IndianRupee}
          value={sales.revenue}
          format={(n) => inr(Math.round(n), { short: sales.revenue >= 100_000 })}
          change={revenueChange}
          hint={sales.average_sale ? `avg sale ${inr(sales.average_sale)}` : undefined}
        />
        <StatTile
          label="Straight from your posts"
          icon={Target}
          value={posts.revenue}
          format={(n) => inr(Math.round(n), { short: posts.revenue >= 100_000 })}
          hint={`${count(posts.customers)} customer${posts.customers === 1 ? '' : 's'} from posts`}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader title="Where enquiries came from" subtitle={`${count(e.total)} in ${s.label}`} />
          {e.by_source?.length ? (
            <ul className="mt-3 space-y-2.5">
              {e.by_source.map((row) => (
                <li key={row.source}>
                  <div className="flex justify-between text-sm">
                    <span className="text-ink">{row.name}</span>
                    <span className="num font-semibold text-ink">{row.count}</span>
                  </div>
                  <div className="mt-1 h-2 rounded-full bg-surface-sunken">
                    <div className="h-2 rounded-full bg-brand" style={{ width: `${(row.count / top) * 100}%` }} />
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-3 text-sm text-ink-3">No enquiries this month yet.</p>
          )}
        </Card>

        <Card>
          <CardHeader title="What your AI team did" subtitle="Work you didn't have to do yourself" />
          <dl className="mt-3 divide-y divide-line">
            <Line label="Enquiries answered within 5 minutes" value={`${count(e.answered_within_5_min)} of ${count(e.total)}`} />
            <Line label="Posts published" value={`${count(posts.published)}${posts.published_by_ai ? ` (${posts.published_by_ai} planned by AI)` : ''}`} />
            <Line label="Hot leads flagged → bought" value={`${count(hot.flagged)} → ${count(hot.won)}`} />
            <Line label="New reviews" value={reviews.new ? `${reviews.new} · avg ${reviews.average_rating}★` : '0'} />
            <Line label="Review replies posted" value={count(reviews.replies_posted)} />
            <Line label="Review requests sent" value={count(reviews.requests_sent)} />
          </dl>
        </Card>
      </div>

      {posts.best && (
        <Card>
          <CardHeader title="Your best post this month" subtitle="The post whose enquiries turned into the most money" />
          <div className="mt-3 flex items-center gap-3">
            <Sparkles aria-hidden className="size-5 shrink-0 text-accent-ink" />
            <p className="text-ink">
              <b>{posts.best.title || `Post #${posts.best.id}`}</b> brought {posts.best.customers} customer
              {posts.best.customers === 1 ? '' : 's'} worth <b>{inr(posts.best.revenue)}</b>.
            </p>
          </div>
        </Card>
      )}

      <p className="text-xs text-ink-3">
        How we count: sales are customers marked "won" in {s.label}, from enquiries handled in this dashboard. "Straight from your posts"
        is the part whose enquiry came from one of your posts. Return on your plan = sales ÷ your plan's monthly price ({inr(plan.price)}).
        Customers imported from old registers are not counted.
      </p>
    </div>
  )
}
