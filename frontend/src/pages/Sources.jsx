/*
  Where customers come from: every channel side by side, so the owner sees
  which ones bring enquiries and which ones bring money.

  1. The key insight in one sentence, plus share of enquiries vs share of ₹
  2. Enquiries, sales and ₹ per channel as three small charts with the same
     rows (three units on one chart would invent a relationship)
  3. The full table (click a heading to sort)
  4. Enquiry → reply → sale, and "fast replies win"
  5. When enquiries arrive, what people ask for, and the daily trend

  Every block loads on its own, for the period chosen at the top.
*/
import clsx from 'clsx'
import { ArrowDown, ArrowUp, IndianRupee, Users } from 'lucide-react'
import { motion } from 'motion/react'
import { useState } from 'react'
import { Link } from 'react-router'

import { fadeUp, stagger } from '@/animations/presets'
import { BarList } from '@/components/charts/BarList'
import { HourColumns } from '@/components/charts/HourColumns'
import { ShareBars } from '@/components/charts/ShareBars'
import { TrendChart } from '@/components/charts/TrendChart'
import { PageHeader } from '@/components/layout/PageHeader'
import { ChannelBadge } from '@/components/ui/Badge'
import { Card } from '@/components/ui/Card'
import { QueryCard } from '@/components/ui/QueryCard'
import { Skeleton } from '@/components/ui/Skeleton'
import { EmptyState, InlineError } from '@/components/ui/States'
import { useFunnel, useServices, useSources, useTiming, useTrend } from '@/hooks/useAnalytics'
import { usePeriod } from '@/hooks/usePeriod'
import { channel, count, hourLabel, inr, minutes, plural, serviceLabel } from '@/styles/tokens'

const COLUMNS = [
  { key: 'leads', label: 'Enquiries', render: (s) => s.leads },
  { key: 'won', label: 'Sales', render: (s) => s.won },
  { key: 'conversion_pct', label: 'Bought', render: (s) => `${s.conversion_pct}%` },
  { key: 'revenue', label: 'Revenue', render: (s) => inr(s.revenue) },
  { key: 'revenue_per_lead', label: '₹ per enquiry', render: (s) => inr(s.revenue_per_lead) },
  { key: 'median_reply_minutes', label: 'Typical reply', render: (s) => minutes(s.median_reply_minutes) },
  { key: 'unanswered', label: 'Never answered', render: (s) => s.unanswered },
]

function ChannelTable({ sources }) {
  const [sort, setSort] = useState({ key: 'revenue', desc: true })
  const rows = [...sources].sort((a, b) => {
    const x = a[sort.key] ?? -1
    const y = b[sort.key] ?? -1
    return sort.desc ? y - x : x - y
  })

  return (
    <div className="-mx-5 overflow-x-auto px-5">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-line text-xs text-ink-3">
            <th className="py-3 pr-3 text-left font-medium">Channel</th>
            {COLUMNS.map((col) => {
              const active = sort.key === col.key
              return (
                <th key={col.key} className="px-3 py-3 text-right font-medium" aria-sort={active ? (sort.desc ? 'descending' : 'ascending') : 'none'}>
                  <button
                    type="button"
                    onClick={() => setSort({ key: col.key, desc: active ? !sort.desc : true })}
                    className={clsx('inline-flex cursor-pointer items-center gap-1 whitespace-nowrap hover:text-ink', active && 'text-ink')}
                  >
                    {col.label}
                    {active && (sort.desc ? <ArrowDown aria-hidden className="size-3" /> : <ArrowUp aria-hidden className="size-3" />)}
                  </button>
                </th>
              )
            })}
          </tr>
        </thead>
        <tbody className="num divide-y divide-line">
          {rows.map((s) => (
            <tr key={s.source} className="hover:bg-surface-sunken/60">
              <td className="py-3 pr-3 whitespace-nowrap">
                <Link to={`/leads?source=${s.source}`} className="hover:underline">
                  <ChannelBadge source={s.source} />
                </Link>
              </td>
              {COLUMNS.map((col) => (
                <td key={col.key} className={clsx('px-3 py-3 text-right whitespace-nowrap', col.key === sort.key ? 'font-semibold text-ink' : 'text-ink-2')}>
                  {col.render(s)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** "Instagram brings enquiries, Google brings money", worked out from the numbers. */
function KeyInsight({ sources }) {
  const totalLeads = sources.reduce((n, s) => n + s.leads, 0)
  const totalRevenue = sources.reduce((n, s) => n + s.revenue, 0)
  const busiest = sources.reduce((a, b) => (b.leads > a.leads ? b : a))
  const money = sources.reduce((a, b) => (b.revenue > a.revenue ? b : a))
  const name = (s) => channel(s.source).label
  const sentence =
    money.revenue === 0
      ? `${name(busiest)} brings the most enquiries. No sales recorded yet in this period.`
      : busiest.source === money.source
        ? `${name(money)} brings both the most enquiries and the most money.`
        : `${name(busiest)} brings enquiries, ${name(money)} brings money.`

  return (
    <Card>
      <p className="text-xs font-semibold tracking-wide text-ink-3 uppercase">The big picture</p>
      <h2 className="mt-1 text-xl font-bold tracking-tight sm:text-2xl">{sentence}</h2>
      <div className="mt-5 grid gap-3 sm:grid-cols-2">
        <div className="rounded-control border border-line bg-surface-raised p-4">
          <p className="flex items-center gap-1.5 text-sm text-ink-3">
            <Users aria-hidden className="size-4" /> Most enquiries
          </p>
          <ChannelBadge source={busiest.source} className="mt-2 text-base font-semibold text-ink" />
          <p className="mt-1 text-sm text-ink-2">
            {plural(busiest.leads, 'enquiry', 'enquiries')} ({busiest.lead_share_pct}%), {busiest.conversion_pct}% bought
          </p>
        </div>
        <div className="rounded-control border border-line bg-surface-raised p-4">
          <p className="flex items-center gap-1.5 text-sm text-ink-3">
            <IndianRupee aria-hidden className="size-4" /> Most money
          </p>
          <ChannelBadge source={money.source} className="mt-2 text-base font-semibold text-ink" />
          <p className="mt-1 text-sm text-ink-2">
            {inr(money.revenue)} ({money.revenue_share_pct}%), {inr(money.revenue_per_lead)} per enquiry
          </p>
        </div>
      </div>
      <div className="mt-6">
        <ShareBars sources={sources} totalLeads={totalLeads} totalRevenue={totalRevenue} />
      </div>
    </Card>
  )
}

/** Enquiries, sales and ₹ per channel: three small charts, the same rows in the same order. */
function ThreeWays({ sources }) {
  const rows = [...sources].sort((a, b) => b.leads - a.leads)
  const items = (value, display, sub) =>
    rows.map((s) => ({ key: s.source, label: channel(s.source).label, color: channel(s.source).color, value: value(s), display: display(s), sub: sub?.(s) }))
  return (
    <div className="grid gap-8 md:grid-cols-3">
      <div>
        <h3 className="mb-3 text-xs font-semibold tracking-wide text-ink-3 uppercase">Enquiries</h3>
        <BarList items={items((s) => s.leads, (s) => count(s.leads))} />
      </div>
      <div>
        <h3 className="mb-3 text-xs font-semibold tracking-wide text-ink-3 uppercase">Sales</h3>
        <BarList items={items((s) => s.won, (s) => count(s.won), (s) => `${s.conversion_pct}%`)} />
      </div>
      <div>
        <h3 className="mb-3 text-xs font-semibold tracking-wide text-ink-3 uppercase">Revenue</h3>
        <BarList items={items((s) => s.revenue, (s) => inr(s.revenue, { short: true }))} />
      </div>
    </div>
  )
}

function SourcesBlock({ days }) {
  const sources = useSources(days)
  if (sources.isPending) {
    return (
      <div className="space-y-6">
        <Card>
          <Skeleton className="h-8 w-2/3" />
          <Skeleton className="mt-5 h-40 w-full" />
        </Card>
        <Card>
          <Skeleton className="h-48 w-full" />
        </Card>
      </div>
    )
  }
  if (sources.isError) return <Card><InlineError error={sources.error} onRetry={() => sources.refetch()} /></Card>
  const list = sources.data.filter((s) => s.leads > 0)
  if (!list.length)
    return (
      <Card>
        <EmptyState title="No enquiries in this period">Try a longer period with the switch at the top.</EmptyState>
      </Card>
    )

  return (
    <div className={clsx('space-y-6 transition-opacity duration-200', sources.isPlaceholderData && 'opacity-60')}>
      <motion.div variants={fadeUp}>
        <KeyInsight sources={list} />
      </motion.div>
      <motion.div variants={fadeUp}>
        <Card>
          <h2 className="mb-1 text-base font-semibold text-ink">Enquiries, sales and money per channel</h2>
          <p className="mb-5 text-sm text-ink-3">Same channels, same order, so you can read across</p>
          <ThreeWays sources={list} />
        </Card>
      </motion.div>
      <motion.div variants={fadeUp}>
        <Card>
          <h2 className="mb-1 text-base font-semibold text-ink">Every channel, side by side</h2>
          <p className="mb-2 text-sm text-ink-3">Click a heading to sort · click a channel to see its enquiries</p>
          <ChannelTable sources={list} />
        </Card>
      </motion.div>
    </div>
  )
}

export default function Sources() {
  const { days } = usePeriod()
  const funnel = useFunnel(days)
  const timing = useTiming(days)
  const services = useServices(days)
  const trend = useTrend(days)

  return (
    <div>
      <PageHeader />
      <motion.div variants={stagger(0.07)} initial="hidden" animate="show" className="space-y-6">
        <SourcesBlock days={days} />

        <div className="grid gap-6 lg:grid-cols-2">
          <motion.div variants={fadeUp}>
            <QueryCard query={funnel} title="From enquiry to sale" subtitle="How many enquiries reach each step">
              {(f) => (
                <>
                  <BarList
                    items={[
                      { key: 'received', label: 'Enquiries received', value: f.received },
                      { key: 'replied', label: 'Got a reply', value: f.replied, sub: f.received ? `${Math.round((f.replied / f.received) * 100)}%` : null },
                      { key: 'won', label: 'Bought', value: f.won, sub: f.received ? `${Math.round((f.won / f.received) * 100)}%` : null },
                    ]}
                    max={f.received}
                  />
                  <dl className="mt-5 grid grid-cols-4 gap-2 border-t border-line pt-4 text-center text-xs">
                    {['contacted', 'quoted', 'booked', 'lost'].map((status) => (
                      <div key={status}>
                        <dt className="text-ink-3 capitalize">{status}</dt>
                        <dd className="num text-base font-semibold text-ink">{f.by_status?.[status] ?? 0}</dd>
                      </div>
                    ))}
                  </dl>
                </>
              )}
            </QueryCard>
          </motion.div>
          <motion.div variants={fadeUp}>
            <QueryCard
              query={timing}
              title="Fast replies win"
              subtitle="Share of enquiries that bought, by how fast you first replied"
            >
              {(t) => {
                const rows = (t.reply_speed ?? []).filter((b) => b.leads > 0)
                const best = rows.reduce((a, b) => (b.leads >= 3 && b.win_rate_pct > (a?.win_rate_pct ?? -1) ? b : a), null)
                return (
                  <BarList
                    items={rows.map((b) => ({
                      key: b.bucket,
                      label: b.bucket === 'no reply' ? 'Never replied' : `Replied ${b.bucket}`,
                      value: b.win_rate_pct,
                      display: `${b.win_rate_pct}%`,
                      sub: `${b.won} of ${b.leads}`,
                    }))}
                    max={100}
                    highlight={best?.bucket}
                  />
                )
              }}
            </QueryCard>
          </motion.div>
        </div>

        <motion.div variants={fadeUp}>
          <QueryCard
            query={timing}
            title="When enquiries arrive"
            subtitle={(t) => {
              const day = t.weekdays.reduce((a, b) => (b.leads > a.leads ? b : a))
              return `India time · busiest hours: ${t.busiest_hours.map(hourLabel).join(', ')} · busiest day: ${day.day}`
            }}
          >
            {(t) => {
              const day = t.weekdays.reduce((a, b) => (b.leads > a.leads ? b : a))
              return (
                <div className="grid gap-8 lg:grid-cols-[2fr_1fr]">
                  <HourColumns hours={t.hours} busiest={t.busiest_hours} />
                  <div>
                    <h3 className="mb-3 text-xs font-semibold tracking-wide text-ink-3 uppercase">By day</h3>
                    <BarList items={t.weekdays.map((d) => ({ key: d.day, label: d.day, value: d.leads }))} highlight={day.day} />
                  </div>
                </div>
              )
            }}
          </QueryCard>
        </motion.div>

        <div className="grid gap-6 lg:grid-cols-5">
          <motion.div variants={fadeUp} className="lg:col-span-2">
            <QueryCard
              query={services}
              title="What customers ask for"
              subtitle="Most requested, with sales"
              empty="No enquiries in this period"
              isEmpty={(d) => !d.services?.length}
            >
              {(d) => (
                <BarList
                  items={d.services.slice(0, 6).map((s) => ({
                    key: s.name,
                    label: serviceLabel(s.name),
                    value: s.leads,
                    sub: `${s.won} bought${s.revenue ? ` · ${inr(s.revenue, { short: true })}` : ''}`,
                  }))}
                />
              )}
            </QueryCard>
          </motion.div>
          <motion.div variants={fadeUp} className="lg:col-span-3">
            <QueryCard query={trend} title="Enquiries and sales per day" subtitle={`Last ${days} days, India time`} skeleton="h-60">
              {(points) => <TrendChart points={points} />}
            </QueryCard>
          </motion.div>
        </div>
      </motion.div>
    </div>
  )
}
