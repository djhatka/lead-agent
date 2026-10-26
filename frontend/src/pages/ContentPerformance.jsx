/*
  What's working: which posts bring customers and ₹, not just likes.

  1. The last 90 days in five numbers, money first
  2. Top posts by ₹ / enquiries / reach / engagement (tabs). Every row shows
     enquiries and ₹ next to reach and likes, whichever tab is open.
  3. What works per kind of post: enquiries, ₹ and reach per post, as three
     small charts with the same rows (three units on one chart would mislead)
  4. Upcoming festivals worth planning a post for
*/
import clsx from 'clsx'
import { ArrowRight, CalendarHeart, IndianRupee, Megaphone, ShoppingBag, Users } from 'lucide-react'
import { motion } from 'motion/react'
import { useState } from 'react'
import { Link } from 'react-router'

import { fadeUp, listItem, stagger } from '@/animations/presets'
import { BarList } from '@/components/charts/BarList'
import { StatTile } from '@/components/charts/StatTile'
import { PageHeader } from '@/components/layout/PageHeader'
import { Card, CardHeader } from '@/components/ui/Card'
import { QueryCard } from '@/components/ui/QueryCard'
import { Skeleton } from '@/components/ui/Skeleton'
import { EmptyState, InlineError } from '@/components/ui/States'
import { useContentStats, useEvents, useTopPosts } from '@/hooks/useContent'
import { addDaysKey, count, dayLabel, FORMATS, inr, pillar, platform, plural, shortDate } from '@/styles/tokens'

const TABS = [
  { key: 'revenue', label: 'Most ₹' },
  { key: 'enquiries', label: 'Most enquiries' },
  { key: 'reach', label: 'Most reach' },
  { key: 'engagement', label: 'Most engagement' },
]

function Totals({ stats }) {
  if (stats.isPending)
    return (
      <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
        {Array.from({ length: 4 }, (_, i) => (
          <Skeleton key={i} className="h-28 rounded-card" />
        ))}
      </div>
    )
  if (stats.isError) return <Card><InlineError error={stats.error} onRetry={() => stats.refetch()} /></Card>
  const t = stats.data.totals
  const days = stats.data.period_days ?? 90
  return (
    <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
      <StatTile label="Revenue from posts" icon={IndianRupee} value={t.revenue} format={(n) => inr(Math.round(n), { short: t.revenue >= 100_000 })} hint={`last ${days} days`} />
      <StatTile label="Customers" icon={ShoppingBag} value={t.customers} hint={`from ${plural(t.enquiries, 'enquiry', 'enquiries')}`} />
      <StatTile label="Enquiries" icon={Users} value={t.enquiries} hint={t.posts ? `${(t.enquiries / t.posts).toFixed(1)} per post` : null} />
      <StatTile label="Posts" icon={Megaphone} value={t.posts} hint={`${count(t.reach)} people reached`} />
    </div>
  )
}

function TopPosts() {
  const [by, setBy] = useState('revenue')
  const top = useTopPosts(by)

  return (
    <Card>
      <CardHeader title="Your best posts" subtitle="Customers and ₹ first. Likes are nice, sales pay the rent." />
      <div role="tablist" aria-label="Rank posts by" className="-mx-1 mb-4 flex gap-1 overflow-x-auto px-1">
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            role="tab"
            aria-selected={by === t.key}
            onClick={() => setBy(t.key)}
            className={clsx(
              'h-9 shrink-0 cursor-pointer rounded-full px-3.5 text-sm font-medium transition-colors',
              by === t.key ? 'bg-ink text-surface' : 'bg-surface-sunken text-ink-2 hover:text-ink',
            )}
          >
            {t.label}
          </button>
        ))}
      </div>
      {top.isPending ? (
        <div className="space-y-3">
          {Array.from({ length: 4 }, (_, i) => (
            <Skeleton key={i} className="h-14 w-full" />
          ))}
        </div>
      ) : top.isError ? (
        <InlineError error={top.error} onRetry={() => top.refetch()} />
      ) : top.data.length === 0 ? (
        <EmptyState icon={Megaphone} title="No published posts yet">Results show up here a day or two after your first post goes out.</EmptyState>
      ) : (
        <motion.ol key={by} variants={stagger(0.04)} initial="hidden" animate="show" className={clsx('divide-y divide-line transition-opacity', top.isPlaceholderData && 'opacity-60')}>
          {top.data.map((post, i) => {
            const where = platform(post.platform)
            const r = post.results ?? {}
            const m = post.metrics ?? {}
            return (
              <motion.li key={post.id} variants={listItem} className="flex items-center gap-3 py-3">
                <span className="num w-5 shrink-0 text-right text-sm font-semibold text-ink-3">{i + 1}</span>
                <span className="flex size-10 shrink-0 items-center justify-center rounded-control bg-surface-sunken" title={where.label}>
                  <where.icon aria-hidden className="size-5 text-ink-2" />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium text-ink">{post.title}</p>
                  <p className="truncate text-xs text-ink-3">
                    {[pillar(post.pillar).label, FORMATS[post.format], shortDate(post.published_at)].filter(Boolean).join(' · ')}
                  </p>
                </div>
                <div className="shrink-0 text-right">
                  <p className="text-sm">
                    <span className={clsx('font-semibold', by === 'revenue' ? 'text-ink' : 'text-ink-2')}>{inr(r.revenue ?? 0, { short: true })}</span>
                    <span className="text-ink-3"> · </span>
                    <span className={clsx(by === 'enquiries' ? 'font-semibold text-ink' : 'text-ink-2')}>{plural(r.enquiries ?? 0, 'enquiry', 'enquiries')}</span>
                  </p>
                  <p className="text-xs text-ink-3">
                    <span className={clsx(by === 'reach' && 'font-semibold text-ink')}>{count(m.reach ?? 0)} reach</span>
                    {' · '}
                    <span className={clsx(by === 'engagement' && 'font-semibold text-ink')}>{m.engagement_pct ?? 0}% engaged</span>
                  </p>
                </div>
              </motion.li>
            )
          })}
        </motion.ol>
      )}
    </Card>
  )
}

function WhatWorks({ stats }) {
  return (
    <QueryCard
      query={stats}
      title="What works, by kind of post"
      subtitle="Average per post, last 90 days. Same rows in each chart, so you can read across."
      empty="No published posts yet"
      isEmpty={(d) => !d.pillars?.length}
    >
      {(d) => {
        const rows = [...d.pillars].sort((a, b) => b.revenue_per_post - a.revenue_per_post || b.enquiries_per_post - a.enquiries_per_post)
        const best = rows[0]
        const mostReach = [...rows].sort((a, b) => b.avg_reach - a.avg_reach)[0]
        const items = (value, display) => rows.map((p) => ({ key: p.pillar, label: pillar(p.pillar).label, value: value(p), display: display(p), sub: `${p.posts}×` }))
        return (
          <>
            {best && (
              <p className="mb-5 rounded-control bg-good-soft p-3 text-sm text-ink">
                <span className="font-semibold">{pillar(best.pillar).label} posts bring the most money</span>: {inr(best.revenue_per_post)} and{' '}
                {best.enquiries_per_post} enquiries a post.
                {mostReach && mostReach.pillar !== best.pillar && (
                  <> {pillar(mostReach.pillar).label} posts reach the most people ({count(mostReach.avg_reach)} a post) but bring {mostReach.enquiries_per_post} enquiries.</>
                )}
              </p>
            )}
            <div className="grid gap-8 md:grid-cols-3">
              <div>
                <h3 className="mb-3 text-xs font-semibold tracking-wide text-ink-3 uppercase">₹ per post</h3>
                <BarList items={items((p) => p.revenue_per_post, (p) => inr(p.revenue_per_post, { short: true }))} highlight={best?.pillar} />
              </div>
              <div>
                <h3 className="mb-3 text-xs font-semibold tracking-wide text-ink-3 uppercase">Enquiries per post</h3>
                <BarList items={items((p) => p.enquiries_per_post, (p) => p.enquiries_per_post)} />
              </div>
              <div>
                <h3 className="mb-3 text-xs font-semibold tracking-wide text-ink-3 uppercase">Reach per post</h3>
                <BarList items={items((p) => p.avg_reach, (p) => count(p.avg_reach))} color="var(--line-strong)" />
              </div>
            </div>
          </>
        )
      }}
    </QueryCard>
  )
}

function Festivals() {
  const events = useEvents()
  return (
    <QueryCard
      query={events}
      title={
        <span className="inline-flex items-center gap-2">
          <CalendarHeart aria-hidden className="size-5 text-accent" /> Coming up
        </span>
      }
      subtitle="Festivals and days worth a post. Plan a few days ahead."
      empty="No festivals coming up"
      isEmpty={(d) => !d.length}
      skeleton="h-64"
    >
      {(list) => (
        <ul className="space-y-2">
          {list.slice(0, 6).map((e) => {
            const days = e.days_away ?? 0
            return (
              <li key={`${e.date}-${e.name}`} className="flex items-center gap-3 rounded-control border border-line bg-surface-raised p-3">
                <div className="w-14 shrink-0 text-center">
                  <p className="text-xs text-ink-3 uppercase">{new Date(`${e.date}T12:00:00Z`).toLocaleDateString('en-IN', { month: 'short', timeZone: 'UTC' })}</p>
                  <p className="num text-xl font-bold text-ink">{Number(e.date.slice(8))}</p>
                </div>
                <div className="min-w-0 flex-1">
                  <p className="font-medium text-ink">
                    {e.name} <span className="text-xs font-normal text-ink-3">· {days === 0 ? 'today' : days === 1 ? 'tomorrow' : `in ${days} days`}</span>
                  </p>
                  {e.idea && <p className="text-sm text-ink-2">{e.idea}</p>}
                </div>
                <Link
                  to={`/content${days > 3 ? `?from=${addDaysKey(e.date, -3)}` : ''}`}
                  className="inline-flex shrink-0 items-center gap-1 text-sm font-semibold text-brand hover:underline"
                  aria-label={`Plan a post for ${e.name}, ${dayLabel(e.date)}`}
                >
                  Plan <ArrowRight aria-hidden className="size-4" />
                </Link>
              </li>
            )
          })}
        </ul>
      )}
    </QueryCard>
  )
}

export default function ContentPerformance() {
  const stats = useContentStats(90)
  return (
    <div>
      <PageHeader />
      <motion.div variants={stagger(0.07)} initial="hidden" animate="show" className="space-y-6">
        <motion.div variants={fadeUp}>
          <Totals stats={stats} />
        </motion.div>
        <div className="grid gap-6 xl:grid-cols-[3fr_2fr]">
          <motion.div variants={fadeUp}>
            <TopPosts />
          </motion.div>
          <motion.div variants={fadeUp}>
            <Festivals />
          </motion.div>
        </div>
        <motion.div variants={fadeUp}>
          <WhatWorks stats={stats} />
        </motion.div>
      </motion.div>
    </div>
  )
}
