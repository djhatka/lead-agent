/*
  Home: the first thing the owner sees each morning, in the order they think.

  1. "How are we doing?"        enquiries, sales, ₹ and reply time this period (count up)
  2. "Who do I call right now?" 🔥 hot enquiries, highest score first, one tap to call or WhatsApp
     "Who went quiet?"         enquiries that need a follow-up, each with the reason (Task 30)
  3. "What happened?"           plain-English highlights
  4. "What should I do?"        the latest weekly review's 3 actions, each with its why

  Each block loads on its own, so a slow part never blanks the page.
  Numbers and hot enquiries refresh every 30 s (and instantly on the live feed).
*/
import { useGSAP } from '@gsap/react'
import clsx from 'clsx'
import { ArrowRight, BellRing, CheckCircle2, Clock, Flame, IndianRupee, Lightbulb, ListChecks, RefreshCw, ShoppingBag, Users } from 'lucide-react'
import { motion } from 'motion/react'
import { useRef, useState } from 'react'
import { Link } from 'react-router'

import { fadeUp, listItem, revealGrid, stagger } from '@/animations/presets'
import { StatTile } from '@/components/charts/StatTile'
import { PageHeader } from '@/components/layout/PageHeader'
import { ContactButtons } from '@/components/leads/ContactButtons'
import { ScoreRing } from '@/components/leads/ScoreRing'
import { WhyNote } from '@/components/ui/AiNote'
import { ChannelBadge, PriorityBadge, SentimentBadge } from '@/components/ui/Badge'
import { Card, CardHeader } from '@/components/ui/Card'
import { Skeleton } from '@/components/ui/Skeleton'
import { EmptyState, ErrorState, InlineError } from '@/components/ui/States'
import { useSources, useSummary } from '@/hooks/useAnalytics'
import { useBusiness } from '@/hooks/useBusiness'
import { useFollowups } from '@/hooks/useFollowups'
import { useRenewals } from '@/hooks/useRenewals'
import { useReports } from '@/hooks/useGrowth'
import { useLeads } from '@/hooks/useLeads'
import { usePeriod } from '@/hooks/usePeriod'
import { deriveHighlights } from '@/lib/highlights'
import { greeting, inr, IST, leadTitle, minutes, serviceLabel, shortDate, timeAgo } from '@/styles/tokens'

const linkStyle = 'inline-flex items-center gap-1 text-sm font-semibold text-brand hover:underline'

function Numbers({ days }) {
  const summary = useSummary(days)
  const ref = useRef(null)

  useGSAP(
    () => {
      if (ref.current) revealGrid(ref.current.children)
    },
    { dependencies: [Boolean(summary.data)], scope: ref },
  )

  if (summary.isPending) {
    return (
      <div className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4" aria-busy="true" aria-label="Loading numbers">
        {Array.from({ length: 4 }, (_, i) => (
          <Card key={i}>
            <Skeleton className="h-4 w-20" />
            <Skeleton className="mt-3 h-8 w-24" />
            <Skeleton className="mt-3 h-3 w-28" />
          </Card>
        ))}
      </div>
    )
  }
  if (summary.isError) return <ErrorState error={summary.error} onRetry={() => summary.refetch()} />

  const s = summary.data
  const before = `vs the ${days} days before`
  return (
    <div
      ref={ref}
      className={clsx('grid grid-cols-2 gap-3 transition-opacity duration-200 sm:gap-4 xl:grid-cols-4', summary.isPlaceholderData && 'opacity-60')}
    >
      <StatTile label="Enquiries" icon={Users} value={s.leads} change={s.leads_change_pct} hint={before} />
      <StatTile label="Sales" icon={ShoppingBag} value={s.won} hint={`${s.conversion_pct}% of enquiries bought`} />
      <StatTile
        label="Revenue"
        icon={IndianRupee}
        value={s.revenue}
        // In full up to ₹99,999 (₹62,900); above that it's ₹10.9 L so it fits a phone, with the full amount below.
        format={(n) => inr(Math.round(n), { short: s.revenue >= 100_000 })}
        change={s.revenue_change_pct}
        hint={[s.revenue >= 100_000 && inr(s.revenue), s.avg_job_value && `avg sale ${inr(s.avg_job_value)}`].filter(Boolean).join(' · ')}
      />
      <StatTile
        label="Typical reply time"
        icon={Clock}
        value={s.median_reply_minutes}
        format={minutes}
        hint={`${s.replied_within_5_min_pct}% answered within 5 min`}
      />
    </div>
  )
}

function HotLeads() {
  const hot = useLeads({ priority: 'hot', sort: 'score', page_size: 5 })
  const total = hot.data?.total ?? 0

  return (
    <Card className="h-full">
      <CardHeader
        title={
          <span className="inline-flex items-center gap-2">
            <Flame aria-hidden className="size-5 text-accent" /> Call these first
          </span>
        }
        subtitle="Hot enquiries, most likely to buy at the top"
        action={
          total > 5 && (
            <Link to="/leads?priority=hot&sort=score" className={linkStyle}>
              All {total} <ArrowRight aria-hidden className="size-4" />
            </Link>
          )
        }
      />
      {hot.isPending ? (
        <div className="space-y-4" aria-busy="true" aria-label="Loading hot enquiries">
          {Array.from({ length: 3 }, (_, i) => (
            <div key={i} className="flex items-center gap-3">
              <Skeleton className="size-11 rounded-full" />
              <div className="flex-1 space-y-2">
                <Skeleton className="h-4 w-40" />
                <Skeleton className="h-3 w-56" />
              </div>
            </div>
          ))}
        </div>
      ) : hot.isError ? (
        <InlineError error={hot.error} onRetry={() => hot.refetch()} />
      ) : total === 0 ? (
        <EmptyState icon={Flame} title="No hot enquiries right now" className="py-6">
          New ones pop up here the moment the AI flags them.
        </EmptyState>
      ) : (
        <motion.ul variants={stagger(0.05)} initial="hidden" animate="show" className="-mx-2 divide-y divide-line">
          {hot.data.items.map((lead) => (
            <motion.li key={lead.id} variants={listItem} className="flex items-center gap-3 px-2 py-3">
              <Link to={`/leads/${lead.id}`} className="group flex min-w-0 flex-1 items-center gap-3">
                <ScoreRing score={lead.analysis?.score} size={44} />
                <div className="min-w-0">
                  <p className="flex items-center gap-2">
                    <span className="truncate font-semibold text-ink group-hover:text-brand">{leadTitle(lead)}</span>
                    <PriorityBadge priority="hot" />
                  </p>
                  <p className="mt-0.5 truncate text-sm text-ink-2">
                    {[serviceLabel(lead.service), timeAgo(lead.created_at)].filter(Boolean).join(' · ')}
                  </p>
                  <p className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1">
                    <ChannelBadge source={lead.source} className="text-xs" />
                    {lead.analysis?.sentiment !== 'casual' && <SentimentBadge sentiment={lead.analysis?.sentiment} />}
                  </p>
                </div>
              </Link>
              <ContactButtons lead={lead} />
            </motion.li>
          ))}
        </motion.ul>
      )}
    </Card>
  )
}

function FollowUps() {
  const query = useFollowups()
  const [showAll, setShowAll] = useState(false)
  if (query.isPending) return <Skeleton className="h-40 rounded-card" />
  if (query.isError) return null // an older server without follow-up reminders
  const { items, count, settings } = query.data
  if (!settings.enabled) return null
  const shown = showAll ? items : items.slice(0, 5)

  return (
    <Card>
      <CardHeader
        title={
          <span className="inline-flex items-center gap-2">
            <BellRing aria-hidden className="size-5 text-accent" /> Follow up today
            {count > 0 && <span className="num rounded-full bg-accent-soft px-2 text-sm text-accent-ink">{count}</span>}
          </span>
        }
        subtitle={`Enquiries that went quiet for ${settings.after_days} day${settings.after_days === 1 ? '' : 's'} or more. Most sales are won on the follow-up.`}
        action={
          count > 5 && (
            <button type="button" onClick={() => setShowAll((v) => !v)} className={clsx(linkStyle, 'cursor-pointer')}>
              {showAll ? 'Show fewer' : `All ${count}`} <ArrowRight aria-hidden className="size-4" />
            </button>
          )
        }
      />
      {count === 0 ? (
        <p className="flex items-center gap-2 text-sm text-ink-2">
          <CheckCircle2 aria-hidden className="size-4 text-good" /> All caught up. Nobody is waiting for a follow-up.
        </p>
      ) : (
        <motion.ul variants={stagger(0.04)} initial="hidden" animate="show" className="-mx-2 divide-y divide-line">
          {shown.map((r) => (
            <motion.li key={r.lead_id} variants={listItem}>
              <Link to={`/leads/${r.lead_id}`} className="group flex items-center gap-3 px-2 py-3">
                <div className="min-w-0 flex-1">
                  <p className="flex items-center gap-2">
                    <span className="truncate font-semibold text-ink group-hover:text-brand">{r.customer}</span>
                    {r.priority === 'hot' && <PriorityBadge priority="hot" />}
                  </p>
                  <p className="mt-0.5 text-sm text-ink-2">{r.reason}</p>
                  <ChannelBadge source={r.source} className="mt-1 text-xs" />
                </div>
                <span className="shrink-0 text-sm font-semibold text-brand group-hover:underline">Follow up</span>
              </Link>
            </motion.li>
          ))}
        </motion.ul>
      )}
    </Card>
  )
}

function RenewalsDue() {
  const query = useRenewals()
  if (query.isPending) return <Skeleton className="h-40 rounded-card" />
  if (query.isError) return null // an older server without renewal reminders
  const { items, count, settings } = query.data
  if (!settings.enabled || count === 0) return null

  return (
    <Card>
      <CardHeader
        title={
          <span className="inline-flex items-center gap-2">
            <RefreshCw aria-hidden className="size-5 text-accent" /> Renewals
            <span className="num rounded-full bg-accent-soft px-2 text-sm text-accent-ink">{count}</span>
          </span>
        }
        subtitle={`Memberships or services expiring within ${settings.remind_days_before} days`}
        action={
          <a href="/renewals" className={clsx(linkStyle, 'cursor-pointer')}>
            View all <ArrowRight aria-hidden className="size-4" />
          </a>
        }
      />
      <motion.ul variants={stagger(0.04)} initial="hidden" animate="show" className="-mx-2 divide-y divide-line">
        {items.slice(0, 5).map((r) => (
          <motion.li key={r.id} variants={listItem}>
            <a href="/renewals" className="group flex items-center gap-3 px-2 py-3">
              <div className="min-w-0 flex-1">
                <p className="truncate font-semibold text-ink group-hover:text-brand">{r.customer}</p>
                <p className="mt-0.5 text-sm text-ink-2">{r.reason}</p>
              </div>
              <span className="shrink-0 text-sm font-semibold text-brand group-hover:underline">Renew</span>
            </a>
          </motion.li>
        ))}
      </motion.ul>
    </Card>
  )
}

function Highlights({ days }) {
  const summary = useSummary(days)
  const sources = useSources(days)
  const lines = summary.data ? deriveHighlights(summary.data, sources.data ?? []) : []

  return (
    <Card className="h-full">
      <CardHeader title="What happened" subtitle={`The last ${days} days in plain words`} />
      {summary.isPending ? (
        <div className="space-y-3">
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-5/6" />
          <Skeleton className="h-4 w-4/6" />
        </div>
      ) : summary.isError ? (
        <InlineError error={summary.error} onRetry={() => summary.refetch()} />
      ) : lines.length === 0 ? (
        <p className="text-sm text-ink-2">Nothing to report yet. Highlights appear once enquiries come in.</p>
      ) : (
        <ul className="space-y-3">
          {lines.map((line) => (
            <li key={line} className="flex gap-2.5 text-sm text-ink-2">
              <Lightbulb aria-hidden className="mt-0.5 size-4 shrink-0 text-accent" />
              <span>{line}</span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}

function Actions() {
  const reports = useReports(1)
  const report = reports.data?.[0]

  return (
    <Card>
      <CardHeader
        title={
          <span className="inline-flex items-center gap-2">
            <ListChecks aria-hidden className="size-5 text-brand" /> This week's 3 actions
          </span>
        }
        subtitle={report ? `From your weekly review of ${shortDate(report.created_at)}` : 'From your weekly review'}
        action={
          report && (
            <Link to="/weekly-review" className={linkStyle}>
              Full review <ArrowRight aria-hidden className="size-4" />
            </Link>
          )
        }
      />
      {reports.isPending ? (
        <div className="grid gap-3 md:grid-cols-3">
          {Array.from({ length: 3 }, (_, i) => (
            <Skeleton key={i} className="h-28 rounded-control" />
          ))}
        </div>
      ) : reports.isError ? (
        <InlineError error={reports.error} onRetry={() => reports.refetch()} />
      ) : !report ? (
        <EmptyState icon={ListChecks} title="No weekly review yet" className="py-6" action={<Link to="/weekly-review" className={linkStyle}>Run your first review <ArrowRight aria-hidden className="size-4" /></Link>}>
          The AI looks at your week and picks the 3 things that will bring the most customers.
        </EmptyState>
      ) : (
        <ol className="grid gap-3 md:grid-cols-3">
          {report.actions.slice(0, 3).map((action, i) => (
            <li key={action.title} className="flex flex-col gap-2 rounded-control border border-line bg-surface-raised p-4">
              <div className="flex items-start gap-3">
                <span className="num flex size-7 shrink-0 items-center justify-center rounded-full bg-brand text-sm font-bold text-on-brand">{i + 1}</span>
                <p className="font-semibold text-ink">{action.title}</p>
              </div>
              <WhyNote className="text-[13px]">{action.why}</WhyNote>
              {action.link && (
                <Link to={action.link} className={clsx(linkStyle, 'mt-auto pt-1')}>
                  Do it now <ArrowRight aria-hidden className="size-4" />
                </Link>
              )}
            </li>
          ))}
        </ol>
      )}
    </Card>
  )
}

export default function Home() {
  const { days } = usePeriod()
  const { business } = useBusiness()
  const [today] = useState(() => new Date().toLocaleDateString('en-IN', { weekday: 'long', day: 'numeric', month: 'long', timeZone: IST }))

  return (
    <div>
      <PageHeader title={greeting()} subtitle={`${today} · here's how ${business?.name ?? 'your business'} is doing`} />
      <motion.div variants={stagger(0.08)} initial="hidden" animate="show" className="space-y-6">
        <motion.div variants={fadeUp}>
          <Numbers days={days} />
        </motion.div>
        <div className="grid gap-6 lg:grid-cols-5">
          <motion.div variants={fadeUp} className="lg:col-span-3">
            <HotLeads />
          </motion.div>
          <motion.div variants={fadeUp} className="lg:col-span-2">
            <Highlights days={days} />
          </motion.div>
        </div>
        <motion.div variants={fadeUp}>
          <FollowUps />
        </motion.div>
        <motion.div variants={fadeUp}>
          <RenewalsDue />
        </motion.div>
        <motion.div variants={fadeUp}>
          <Actions />
        </motion.div>
      </motion.div>
    </div>
  )
}
